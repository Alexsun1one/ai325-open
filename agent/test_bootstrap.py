"""Isolated installer tests. Real venv smoke: AI325_INSTALLER_SMOKE=1 python3 -m unittest discover -s agent -p test_bootstrap.py -v

No real client mutation: all client processes are fixture executables; HOME and
client/config/install roots are temporary. The HTTP fixture never opens a browser.
"""
from __future__ import annotations

from contextlib import redirect_stdout, redirect_stderr
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import io
import json
import os
from pathlib import Path
import secrets
import shutil
import stat
import subprocess
import sys
import tempfile
import threading
import unittest
from unittest.mock import patch

import bootstrap as installer
import launch

SOURCE = Path(__file__).resolve().parent

# Deliberately emulates only the help-confirmed commands, not a real agent session.
FAKE_CLI = r'''
import json, os, pathlib, re, sys
client = pathlib.Path(sys.argv[0]).name
args = sys.argv[1:]
assert args[0] == 'mcp'
assert 'ai325' in args
assert 'AI325_TOKEN' not in os.environ
log = pathlib.Path(os.environ['FAKE_LOG'])
with log.open('a') as f:
    f.write(json.dumps([client, *args]) + '\n')
if client == 'codex':
    path = pathlib.Path(os.environ['CODEX_HOME']) / 'config.toml'
    raw = path.read_text() if path.exists() else ''
    if args[1] == 'get':
        assert '[mcp_servers.ai325]' in raw
        print(json.dumps({'name':'ai325'}))
        sys.exit(0)
    assert args[1:3] == ['add','ai325']
    command = args[args.index('--')+1:]
    raw = re.sub(r'(?ms)^\[mcp_servers\.ai325\]\n.*?(?=^\[|\Z)', '', raw)
    raw = raw.rstrip() + '\n\n[mcp_servers.ai325]\ncommand = ' + json.dumps(command[0]) + '\nargs = ' + json.dumps(command[1:]) + '\n'
else:
    assert args[2:4] == ['--scope','user']
    path = pathlib.Path(os.environ['CLAUDE_CONFIG_DIR']) / '.claude.json'
    data = json.loads(path.read_text()) if path.exists() else {}
    servers = data.setdefault('mcpServers',{})
    if args[1] == 'remove':
        servers.pop('ai325',None)
    else:
        assert args[1] == 'add' and 'ai325' not in servers
        command = args[args.index('--')+1:]
        servers['ai325'] = {'command':command[0], 'args':command[1:]}
    raw = json.dumps(data)
path.parent.mkdir(parents=True, exist_ok=True)
path.write_text(raw)
if os.environ.get('FAKE_FAIL') == args[1]:
    print('synthetic child output suppressed', file=sys.stderr)
    sys.exit(9)
'''


class FixtureServer:
    def __init__(self, assets: Path = SOURCE):
        self.assets = assets
        self.token = secrets.token_urlsafe(32)
        self.device = secrets.token_urlsafe(24)
        self.polls = self.starts = self.reads = 0
        self.poll_error = 0
        self.expiry = 20
        self.pending_forever = False
        self.bad_uri = False
        self.bad_base = False
        self.auth_error = False
        self.auth_kind = 'agent'
        self.malformed_agent = False
        self.missing_asset = False
        fixture = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def respond(self, data, status=200):
                self.send_response(status)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode())

            def do_GET(self):
                if self.path.startswith('/agent/client/') or self.path == '/agent/install.sh':
                    name = self.path.rsplit('/', 1)[-1]
                    path = fixture.assets / name
                    if name not in (*installer.ASSETS, 'install.sh') or fixture.missing_asset:
                        self.respond({}, 404)
                        return
                    self.send_response(200)
                    self.end_headers()
                    self.wfile.write(path.read_bytes())
                elif self.path == '/api/events':
                    assert self.headers.get('Authorization') is None
                    fixture.reads += 1
                    self.respond({'events': []})
                elif self.path == '/api/auth/me':
                    if not fixture.auth_error and self.headers.get('Authorization') == 'Bearer ' + fixture.token:
                        agent = None if fixture.malformed_agent else {
                            'id': 1, 'name': 'fixture agent', 'display_name': 'fixture agent',
                            'mentor': {'id': 7, 'name': 'fixture mentor'},
                        }
                        self.respond({'name': 'fixture agent', 'role': 'agent',
                                      'auth_kind': fixture.auth_kind,
                                      'agent': agent if fixture.auth_kind == 'agent' else None,
                                      'agent_profile': agent if fixture.auth_kind == 'agent' else None})
                    else:
                        self.respond({'detail': 'fixture unauthorized'}, 401)
                elif self.path == '/redirect':
                    self.send_response(302)
                    self.send_header('Location', '/api/events')
                    self.end_headers()
                else:
                    self.respond({}, 404)

            def do_POST(self):
                body = json.loads(self.rfile.read(int(self.headers['Content-Length'])))
                if self.path == '/api/agent/connect/start':
                    assert set(body) == {'name', 'client'}
                    fixture.starts += 1
                    self.respond({'device_code': fixture.device, 'user_code': 'ABCD-2345',
                                  'verification_uri': 'https://other.invalid/' if fixture.bad_uri else '/agents/join/?connect=ABCD-2345',
                                  'expires_in': fixture.expiry, 'interval': .01})
                elif self.path == '/api/agent/connect/poll':
                    assert body == {'device_code': fixture.device}
                    fixture.polls += 1
                    if fixture.poll_error:
                        self.respond({'detail': fixture.token}, fixture.poll_error)
                    elif fixture.polls == 1 or fixture.pending_forever:
                        self.respond({'status': 'pending', 'interval': .01})
                    else:
                        self.respond({'status': 'approved', 'token': fixture.token, 'name': 'fixture agent',
                                      'base_url': 'https://other.invalid' if fixture.bad_base else fixture.base})
                else:
                    self.respond({}, 404)

        self.server = ThreadingHTTPServer(('127.0.0.1', 0), Handler)
        self.base = f'http://127.0.0.1:{self.server.server_port}'
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)

    def __enter__(self):
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join()


class InstallerTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='ai325 test space-')
        self.root = Path(self.temp.name)
        self.home = self.root / 'client home'
        self.home.mkdir()
        self.bin = self.root / 'bin'
        self.bin.mkdir()
        for client in ('codex', 'claude'):
            cli = self.bin / client
            cli.write_text(f'#!{sys.executable}\n' + FAKE_CLI)
            cli.chmod(0o700)
        env = {**os.environ, 'HOME': str(self.home), 'USERPROFILE': str(self.home),
               'CODEX_HOME': str(self.home / '.codex'), 'CLAUDE_CONFIG_DIR': str(self.home / '.claude'),
               'XDG_CONFIG_HOME': str(self.home / '.config'), 'FAKE_LOG': str(self.root / 'calls.jsonl'),
               'PATH': str(self.bin) + os.pathsep + os.environ['PATH'], 'PYTHONDONTWRITEBYTECODE': '1',
               'PIP_CACHE_DIR': str(self.root / 'pip-cache')}
        env.pop('AI325_TOKEN', None)
        env.pop('AI325_BASE_URL', None)
        env.pop('AI325_AGENT_NAME', None)
        env.pop('FAKE_FAIL', None)
        self.env = patch.dict(os.environ, env, clear=True)
        self.env.start()
        self.addCleanup(self.env.stop)
        self.addCleanup(self.temp.cleanup)
        self.args = installer.parser().parse_args([
            '--install-dir', str(self.root / 'install'), '--config-dir', str(self.root / 'credentials'),
            '--client-home', str(self.home), '--client', 'none', '--no-browser'])
        installer.private_dir(self.args.install_dir)

    def seed_release(self):
        release = self.args.install_dir / 'releases/fixture'
        release.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(SOURCE / 'launch.py', release / 'launch.py')
        current = self.args.install_dir / 'current'
        if not current.is_symlink():
            current.symlink_to(release)
        return release

    def credentials(self, token='fixture-only', **overrides):
        installer.private_dir(self.args.config_dir)
        data = {'token': token, 'base_url': self.args.base_url, 'name': 'fixture agent', **overrides}
        installer.atomic_write(self.args.config_dir / 'credentials.json', json.dumps(data).encode())

    def capture(self, function, *args):
        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output):
            value = function(*args)
        return value, output.getvalue()

    def test_launcher_private_credentials_and_environment_priority(self):
        self.credentials()
        env = launch.launch_environment(self.args.config_dir, self.args.base_url)
        self.assertTrue(env['AI325_TOKEN'] == 'fixture-only')
        self.assertEqual(stat.S_IMODE(self.args.config_dir.stat().st_mode), 0o700)
        self.assertEqual(stat.S_IMODE((self.args.config_dir / 'credentials.json').stat().st_mode), 0o600)
        with patch.dict(os.environ, {'AI325_TOKEN': 'explicit-fixture'}):
            self.assertTrue(launch.launch_environment(self.args.config_dir, self.args.base_url)['AI325_TOKEN'] == 'explicit-fixture')
        with patch.dict(os.environ, {'AI325_TOKEN': ''}):
            self.assertEqual(launch.launch_environment(self.args.config_dir, self.args.base_url)['AI325_TOKEN'], '')
        self.assertNotIn('AI325_TOKEN', launch.launch_environment(self.args.config_dir, self.args.base_url, True))

    def test_launcher_rejects_permissions_symlink_and_foreign_origin(self):
        self.credentials()
        path = self.args.config_dir / 'credentials.json'
        path.chmod(0o644)
        with self.assertRaises(ValueError):
            launch.read_credentials(self.args.config_dir)
        path.chmod(0o600)
        with patch.dict(os.environ, {'AI325_BASE_URL': 'https://other.invalid'}):
            with self.assertRaises(ValueError):
                launch.launch_environment(self.args.config_dir, self.args.base_url)
        path.rename(self.root / 'elsewhere')
        path.symlink_to(self.root / 'elsewhere')
        with self.assertRaises(OSError):
            launch.read_credentials(self.args.config_dir)
        with self.assertRaises(installer.InstallError):
            installer.atomic_write(path, b'{}')

    def test_launcher_exec_forwards_args_without_token_in_command(self):
        self.credentials()
        with patch.object(launch.os, 'execve') as execute:
            self.assertEqual(launch.main(['--config-dir', str(self.args.config_dir), 'cli', 'events', '--json']), 0)
        _, command, env = execute.call_args.args
        self.assertEqual(command[-2:], ['events', '--json'])
        self.assertTrue('fixture-only' not in ' '.join(command))
        self.assertTrue(env['AI325_TOKEN'] == 'fixture-only')

    def test_malformed_credentials_no_document_in_error(self):
        installer.private_dir(self.args.config_dir)
        installer.atomic_write(self.args.config_dir / 'credentials.json', b'{broken fixture private data')
        code, output = self.capture(launch.main, ['--config-dir', str(self.args.config_dir), 'cli', 'events'])
        self.assertEqual(code, 1)
        self.assertNotIn('broken fixture private data', output)

    def test_cli_registration_repeat_preserves_other_entries(self):
        for client in ('codex', 'claude'):
            with self.subTest(client=client):
                path = installer.config_path(client, self.args)
                path.parent.mkdir(parents=True, exist_ok=True)
                if client == 'codex':
                    original = 'model = "keep-me"\n[mcp_servers.other]\ncommand = "other"\n'
                else:
                    original = json.dumps({'theme': 'keep-me', 'mcpServers': {'other': {'command': 'other'}}})
                path.write_text(original)
                with patch.dict(os.environ, {'AI325_TOKEN': 'must-not-reach-registration'}):
                    self.capture(installer.register_client, client, self.args)
                    first = path.read_text()
                    self.capture(installer.register_client, client, self.args)
                self.assertEqual(first, path.read_text())
                self.assertIn('keep-me', first)
                self.assertIn('other', first)
                self.assertNotIn('AI325_TOKEN', first)
                self.assertIn('current', first)
        calls = (self.root / 'calls.jsonl').read_text()
        self.assertNotIn('must-not-reach-registration', calls)
        self.assertIn('"--scope", "user"', calls)

    def test_json_registration_preserves_only_replaces_ai325(self):
        for client in ('cursor', 'desktop'):
            with self.subTest(client=client), patch.object(installer.platform, 'system', return_value='Darwin'):
                path = installer.config_path(client, self.args)
                path.parent.mkdir(parents=True, exist_ok=True)
                original = {'preferences': {'keep': True}, 'mcpServers': {'other': {'command': 'other'}, 'ai325': {'command': 'old'}}}
                path.write_text(json.dumps(original))
                self.capture(installer.register_client, client, self.args)
                first = path.read_bytes()
                self.capture(installer.register_client, client, self.args)
                self.assertEqual(first, path.read_bytes())
                actual = json.loads(first)
                self.assertEqual(actual['preferences'], original['preferences'])
                self.assertEqual(actual['mcpServers']['other'], original['mcpServers']['other'])
                self.assertNotIn('env', actual['mcpServers']['ai325'])

    def test_public_registration_passes_public_to_registered_mcp(self):
        self.args.public = True
        for client in ('codex', 'cursor'):
            with self.subTest(client=client):
                self.capture(installer.register_client, client, self.args)
                self.assertIn('--public', installer.config_path(client, self.args).read_text())

    def test_registration_failure_restores_config_and_active_release(self):
        for client in ('codex', 'claude'):
            with self.subTest(client=client):
                previous = self.seed_release()
                path = installer.config_path(client, self.args)
                path.parent.mkdir(parents=True, exist_ok=True)
                before = b'model="original"\n' if client == 'codex' else b'{"mcpServers":{"ai325":{"command":"old"},"other":{"command":"keep"}}}'
                path.write_bytes(before)
                candidate = self.args.install_dir / 'releases/new'
                candidate.mkdir()
                with patch.dict(os.environ, {'FAKE_FAIL': 'add'}):
                    with self.assertRaises(installer.InstallError):
                        installer.activate(candidate, self.args, client)
                self.assertEqual(path.read_bytes(), before)
                self.assertEqual((self.args.install_dir / 'current').resolve(), previous.resolve())
                self.assertFalse(candidate.exists())

    def test_new_registration_failure_leaves_no_active_or_config(self):
        release = self.args.install_dir / 'new'
        release.mkdir()
        with patch.dict(os.environ, {'FAKE_FAIL': 'add'}):
            with self.assertRaises(installer.InstallError):
                installer.activate(release, self.args, 'codex')
        self.assertFalse((self.args.install_dir / 'current').exists())
        self.assertFalse(installer.config_path('codex', self.args).exists())

    def test_invalid_json_config_untouched(self):
        path = installer.config_path('cursor', self.args)
        path.parent.mkdir(parents=True)
        path.write_bytes(b'{invalid')
        with self.assertRaises(ValueError):
            installer.register_client('cursor', self.args)
        self.assertEqual(path.read_bytes(), b'{invalid')

    def test_pending_approved_and_repeat_binding(self):
        self.seed_release()
        with FixtureServer() as server:
            self.args.base_url = server.base
            _, output = self.capture(installer.bind, self.args, 'codex')
            self.assertIn('身份绑定成功', output)
            self.assertTrue(server.token not in output and server.device not in output)
            self.assertEqual(server.polls, 2)
            data = launch.read_credentials(self.args.config_dir)
            self.assertTrue(data['token'] == server.token)
            _, output2 = self.capture(installer.bind, self.args, 'codex')
            self.assertEqual(server.starts, 1)
            self.assertIn('已有绑定已验证', output2)

    def test_public_never_requests_or_overwrites_credentials(self):
        self.credentials()
        before = (self.args.config_dir / 'credentials.json').read_bytes()
        self.args.public = True
        with patch.object(installer, 'api', side_effect=AssertionError('unexpected request')):
            self.capture(installer.bind, self.args, 'none')
        self.assertEqual(before, (self.args.config_dir / 'credentials.json').read_bytes())

    def test_poll_errors_expiry_and_same_origin_guard(self):
        self.seed_release()
        with FixtureServer() as server:
            self.args.base_url = server.base
            for status in (404, 409, 410, 429):
                server.poll_error = status
                output = io.StringIO()
                with redirect_stdout(output), self.assertRaises(installer.InstallError) as error:
                    installer.bind(self.args, 'none')
                self.assertIn(str(status), str(error.exception))
                self.assertTrue(server.token not in str(error.exception) + output.getvalue())
            server.poll_error = 0
            server.expiry = .025
            server.pending_forever = True
            with redirect_stdout(io.StringIO()), self.assertRaisesRegex(installer.InstallError, '超时'):
                installer.bind(self.args, 'none')
            server.expiry = 20
            server.pending_forever = False
            server.bad_uri = True
            with self.assertRaises(installer.InstallError):
                installer.bind(self.args, 'none')
            server.bad_uri = False
            server.bad_base = True
            with redirect_stdout(io.StringIO()), self.assertRaises(installer.InstallError):
                installer.bind(self.args, 'none')
            self.assertFalse((self.args.config_dir / 'credentials.json').exists())

    def test_approved_token_retained_if_whoami_fails(self):
        self.seed_release()
        with FixtureServer() as server:
            self.args.base_url = server.base
            server.auth_error = True
            with redirect_stdout(io.StringIO()), self.assertRaises(installer.InstallError):
                installer.bind(self.args, 'none')
            self.assertTrue(launch.read_credentials(self.args.config_dir)['token'] == server.token)
            server.auth_error = False
            self.capture(installer.bind, self.args, 'none')
            self.assertEqual(server.starts, 1)

    def test_environment_token_skips_device_flow(self):
        self.seed_release()
        with FixtureServer() as server, patch.dict(os.environ, {'AI325_TOKEN': server.token}):
            self.args.base_url = server.base
            self.capture(installer.bind, self.args, 'none')
            self.assertEqual(server.starts, 0)
            self.assertFalse((self.args.config_dir / 'credentials.json').exists())

    def test_bind_rejects_human_or_malformed_agent_identity(self):
        self.seed_release()
        with FixtureServer() as server:
            self.args.base_url = server.base
            server.auth_kind = 'session'
            with patch.dict(os.environ, {'AI325_TOKEN': server.token}):
                with self.assertRaisesRegex(installer.InstallError, '不是有效 Agent token'):
                    installer.bind(self.args, 'none')
            self.assertEqual(server.starts, 0)

            self.credentials(server.token)
            server.auth_kind = 'agent'
            server.malformed_agent = True
            with self.assertRaisesRegex(installer.InstallError, '不是有效 Agent token'):
                installer.bind(self.args, 'none')
            self.assertEqual(server.starts, 0)

    def test_download_and_dependency_failures_clean_candidate(self):
        with FixtureServer() as server:
            self.args.base_url = server.base
            server.missing_asset = True
            with self.assertRaises(installer.InstallError):
                installer.prepare_release(self.args)
            self.assertEqual(list((self.args.install_dir / 'releases').iterdir()), [])
            server.missing_asset = False
            with patch.object(installer, 'run', side_effect=installer.InstallError('venv fixture failure')):
                with self.assertRaises(installer.InstallError):
                    installer.prepare_release(self.args)
            self.assertEqual(list((self.args.install_dir / 'releases').iterdir()), [])

    def test_main_failure_nonzero_no_false_success(self):
        argv = ['--install-dir', str(self.args.install_dir), '--config-dir', str(self.args.config_dir),
                '--client-home', str(self.home), '--client', 'codex', '--public']
        with patch.object(installer, 'prepare_release', side_effect=installer.InstallError('fixture failure')):
            code, output = self.capture(installer.main, argv)
        self.assertEqual(code, 1)
        self.assertIn('重试：', output)
        self.assertNotIn('安装完成。', output)
        self.assertFalse((self.args.install_dir / 'current').exists())

    def test_binding_failure_main_reports_install_separately(self):
        release = self.seed_release()
        argv = ['--install-dir', str(self.args.install_dir), '--config-dir', str(self.args.config_dir),
                '--client-home', str(self.home), '--client', 'none', '--no-browser']
        with patch.object(installer, 'prepare_release', return_value=release), \
                patch.object(installer, 'bind', side_effect=installer.InstallError('设备请求已过期')):
            code, output = self.capture(installer.main, argv)
        self.assertEqual(code, 1)
        self.assertIn('客户端安装已完成', output)
        self.assertNotIn('身份绑定成功', output)
        self.assertNotIn('安装完成。CLI', output)

    def test_shell_asset_failure_nonzero_and_no_client_writes(self):
        with FixtureServer() as server:
            server.missing_asset = True
            result = subprocess.run(['bash', str(SOURCE / 'install.sh'), '--base-url', server.base,
                                     '--install-dir', str(self.args.install_dir), '--config-dir', str(self.args.config_dir),
                                     '--client-home', str(self.home), '--client', 'codex', '--public'],
                                    capture_output=True, text=True, timeout=60)
        self.assertNotEqual(result.returncode, 0)
        self.assertIn('下载/校验安装器失败', result.stderr)
        self.assertFalse((self.args.install_dir / 'current').exists())
        self.assertFalse(installer.config_path('codex', self.args).exists())

    def test_origin_lock_and_redirect_guards(self):
        for url in ('http://other.invalid', 'https://user:pass@example.com', 'https://example.com/path', 'https://example.com?token=x'):
            with self.assertRaises(installer.InstallError):
                installer.origin(url)
        with installer.install_lock(self.args.install_dir):
            with self.assertRaises(installer.InstallError):
                with installer.install_lock(self.args.install_dir):
                    pass
        with FixtureServer() as server:
            with self.assertRaises(installer.InstallError):
                installer.fetch(server.base, '/redirect')
            self.assertEqual(server.reads, 0)

    def test_asset_copy_matches_canonical_sources(self):
        dest = self.root / 'export'
        result = subprocess.run(['node', str(SOURCE.parent / 'site/scripts/copy-agent-client.mjs'),
                                 '--output-dir', str(dest)], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        for name in ('install.sh', *installer.ASSETS):
            target = dest / 'agent' / name if name == 'install.sh' else dest / 'agent/client' / name
            self.assertEqual(target.read_bytes(), (SOURCE / name).read_bytes())

    @unittest.skipUnless(os.environ.get('AI325_INSTALLER_SMOKE') == '1', 'opt-in real pip/venv smoke')
    def test_real_venv_shell_download_mcp_cli_and_binding(self):
        with FixtureServer() as server:
            args = ['--base-url', server.base, '--install-dir', str(self.args.install_dir),
                    '--config-dir', str(self.args.config_dir), '--client-home', str(self.home),
                    '--client', 'codex', '--no-browser']
            result = subprocess.run(['bash', '-o', 'pipefail', '-c',
                                     'curl -fsSL "$1/agent/install.sh" | bash -s -- "${@:2}"',
                                     'fixture-install', server.base, *args], capture_output=True,
                                    text=True, timeout=720)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('MCP ', result.stdout)
            self.assertIn('身份绑定成功', result.stdout)
            self.assertTrue(server.token not in result.stdout + result.stderr)
            self.assertTrue(server.device not in result.stdout + result.stderr)
            for line in result.stdout.splitlines():
                if line.startswith('连通检查通过：'):
                    print('REAL SMOKE: ' + line)
            current = self.args.install_dir / 'current'
            self.assertTrue((current / 'venv/pyvenv.cfg').exists())
            self.assertGreater(server.reads, 0)
            credentials = launch.read_credentials(self.args.config_dir)
            self.assertTrue(credentials['token'] == server.token)
            self.args.base_url = server.base
            # Launcher actually execs the CLI with private credentials, not a mocked exec.
            whoami = subprocess.run(installer.launcher_command(current, self.args, mode='cli') + ['whoami', '--json'],
                                    capture_output=True, text=True, timeout=60)
            self.assertEqual(whoami.returncode, 0, whoami.stderr)
            self.assertEqual(json.loads(whoami.stdout)['role'], 'agent')
            self.assertTrue(server.token not in whoami.stdout + whoami.stderr)
            # Optional read-only public endpoint; never binds a production test agent.
            if os.environ.get('AI325_PUBLIC_SMOKE_URL'):
                live = installer.origin(os.environ['AI325_PUBLIC_SMOKE_URL'])
                public_command = [str(current / 'venv/bin/python'), str(current / 'launch.py'),
                                  '--config-dir', str(self.args.config_dir), '--base-url', live,
                                  '--public', 'cli', 'events', '--json']
                public = subprocess.run(public_command, capture_output=True, text=True, timeout=60)
                self.assertEqual(public.returncode, 0, public.stderr)
                self.assertIsInstance(json.loads(public.stdout), (list, dict))
                print('REAL SMOKE: live public CLI GET /api/events JSON PASS (no binding request)')
            # Public re-install builds another real venv; only ai325 changes, credentials stay.
            path = installer.config_path('codex', self.args)
            path.write_text('model = "keep-on-reinstall"\n' + path.read_text())
            credential_bytes = (self.args.config_dir / 'credentials.json').read_bytes()
            repeated = subprocess.run(['bash', str(SOURCE / 'install.sh'), *args, '--public'],
                                      capture_output=True, text=True, timeout=720)
            self.assertEqual(repeated.returncode, 0, repeated.stderr)
            self.assertIn('keep-on-reinstall', path.read_text())
            self.assertEqual((self.args.config_dir / 'credentials.json').read_bytes(), credential_bytes)
            self.assertEqual(server.starts, 1)
            print('REAL SMOKE: shell download + 2 venv installs + stdio list_tools + public CLI + device binding + launcher whoami + repeat install PASS')


if __name__ == '__main__':
    unittest.main()
