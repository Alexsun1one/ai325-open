# -*- coding: utf-8 -*-
"""🌱人民需要AI_智能体先锋队 · 群像站 v2：登录+质量评判+深度统计"""
import os, sqlite3, json, re, subprocess, secrets, hashlib, hmac, datetime, collections, math, uuid, shutil, stat, zipfile, io, html, logging, threading, time, base64, unicodedata
import xml.etree.ElementTree as ET
from email.parser import BytesParser
from email.policy import default as email_policy
from pathlib import Path, PurePosixPath
from typing import Literal
from urllib.parse import quote as urlquote, unquote, urlparse
from fastapi import FastAPI, Request, HTTPException, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse, Response
from starlette.exceptions import HTTPException as StarletteHTTPException
try:
    from .hot import router as hot_router
    from .gatekeeper import (
        decide as decide_moderation,
        enqueue_action,
        ensure_gatekeeper_schema,
        list_pending as list_pending_moderation,
        start_gatekeeper_worker,
    )
except ImportError:  # Docker runs this module as ``main:app``.
    from hot import router as hot_router
    from gatekeeper import (
        decide as decide_moderation,
        enqueue_action,
        ensure_gatekeeper_schema,
        list_pending as list_pending_moderation,
        start_gatekeeper_worker,
    )
from pydantic import BaseModel, Field, ValidationError

DATA_DIR = Path(os.environ.get('XF_DATA_DIR', '/data'))
DATA_DIR.mkdir(parents=True, exist_ok=True)
DB = DATA_DIR / 'xf.db'
ARCHIVE = DATA_DIR / 'archive'
LEDGER_DIR = ARCHIVE / 'LEDGER'
GOVERNED_DIR = DATA_DIR / 'governed'
GOVERNED_LEDGER_DIR = GOVERNED_DIR / 'ledgers'
GOVERNED_ARSENAL_DIR = GOVERNED_DIR / 'arsenal'
GOVERNED_MEMBER_FILE = GOVERNED_DIR / 'members' / 'profiles.json'
UPLOAD_DIR = DATA_DIR / 'uploads'
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
ARSENAL_FILE_DIR = DATA_DIR / 'arsenal-files'
ARSENAL_FILE_DIR.mkdir(parents=True, exist_ok=True)
CONTAINER_STATIC = Path(os.environ.get('XF_STATIC_DIR', '/app/static'))
STATIC = CONTAINER_STATIC if CONTAINER_STATIC.is_dir() else Path(__file__).resolve().parent.parent / 'static'
INITIAL_ADMIN_PASS = os.environ.get('INITIAL_ADMIN_PASS') or os.environ.get('AUTH_PASS') or ''
INVITE_CODE = os.environ.get('INVITE_CODE', '')
INVITE_ALPHABET = 'ABCDEFGHJKMNPQRSTUVWXYZ23456789'
PBKDF2_ITERATIONS = 600_000
PBKDF2_SALT_BYTES = 16
PBKDF2_HASH_BYTES = 32
LOGIN_RATE_LIMIT = 10
LOGIN_RATE_WINDOW_SECONDS = 10 * 60
REGISTER_RATE_LIMIT = 5
REGISTER_RATE_WINDOW_SECONDS = 60 * 60
CLAIM_RATE_LIMIT = 10
CLAIM_RATE_WINDOW_SECONDS = 10 * 60
CLAIM_DEFAULT_TTL_HOURS = 72
CLAIM_MAX_TTL_HOURS = 7 * 24
MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SKILL_ZIP_BYTES = 5 * 1024 * 1024
MAX_SKILL_EXTRACT_BYTES = 20 * 1024 * 1024
ARSENAL_KINDS = ('提示词', '方法', '拆书', '工具', '论文', '文章', '案例', '技能')
UPLOAD_MIME = {
    '.png': 'image/png', '.jpg': 'image/jpeg', '.webp': 'image/webp',
    '.svg': 'image/svg+xml', '.pdf': 'application/pdf',
    '.md': 'text/markdown', '.txt': 'text/plain', '.zip': 'application/zip',
}

ESSAY_MIN_CHARS = 200
ESSAY_CONTINUATION_GAP_SECONDS = 5 * 60
ESSAY_ACTIVITY_SLUG = 'onboarding-essay'
ESSAY_INTRO_RE = re.compile(
    r'(?:大家好|我是|我叫|自我介绍|入群|来自.{0,12}(?:[，,。.!！]|$)|从事.{0,12}(?:[，,。.!！]|$))'
)

# quality 的五维定义保持不变；以下是按“单日窗口”重新标定的满档参考线。
# 旧公式在 20% 长文率、25 篇小作文附近就封顶，日与日之间失去区分度。
QUALITY_INFO_LONG_FULL = 30.0       # 长文率达到 30% 视为该项满档
QUALITY_INFO_AVG_FULL = 300.0       # 均长达到 300 字/条视为该项满档
QUALITY_INFO_LONG_WEIGHT = 0.6
QUALITY_INFO_AVG_WEIGHT = 0.4
QUALITY_DEPTH_ESSAYS_FULL = 80      # 当日超 200 字消息达到 80 条视为满档

app = FastAPI(title='xianfeng-dui-site v2')
CST = datetime.timezone(datetime.timedelta(hours=8))
security_logger = logging.getLogger('xfsite.security')
_rate_lock = threading.Lock()
_login_failures: dict[tuple[str, str], collections.deque] = {}
_register_attempts: dict[str, collections.deque] = {}
_claim_attempts: dict[tuple[str, str], collections.deque] = {}

def db():
    c = sqlite3.connect(DB)
    c.row_factory = sqlite3.Row
    c.execute('PRAGMA journal_mode=WAL')
    c.execute('PRAGMA foreign_keys=ON')
    c.execute('PRAGMA busy_timeout=30000')
    return c

def _ensure_columns(connection, table: str, columns: tuple[tuple[str, str], ...]) -> None:
    """幂等补列：PRAGMA 检查后 ALTER，缺哪列补哪列。"""
    existing = {row[1] for row in connection.execute(f'PRAGMA table_info({table})')}
    for name, ddl in columns:
        if name not in existing:
            connection.execute(f'ALTER TABLE {table} ADD COLUMN {name} {ddl}')


def init_db():
    c = db()
    c.executescript('''
    CREATE TABLE IF NOT EXISTS messages(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      session TEXT, local_id INT, create_time INT,
      cst TEXT, sender TEXT, sender_name TEXT, is_send INT, content TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_msg_time ON messages(create_time);
    CREATE INDEX IF NOT EXISTS idx_msg_sender ON messages(sender);
    CREATE VIRTUAL TABLE IF NOT EXISTS msg_fts USING fts5(content, content='messages', content_rowid='id', tokenize='trigram');
    CREATE TABLE IF NOT EXISTS members(
      username TEXT PRIMARY KEY, display TEXT, nickname TEXT, avatar TEXT,
      msgs INT DEFAULT 0, last_active TEXT, profile TEXT, tags TEXT, quote TEXT,
      name_source TEXT NOT NULL DEFAULT 'masked_wxid',
      identity_flags TEXT NOT NULL DEFAULT '[]',
      name_history TEXT NOT NULL DEFAULT '[]',
      called_names TEXT NOT NULL DEFAULT '[]'
    );
    CREATE TABLE IF NOT EXISTS member_identity_audit(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_key TEXT UNIQUE NOT NULL,
      created_at TEXT NOT NULL,
      event_type TEXT NOT NULL,
      username TEXT NOT NULL,
      display TEXT NOT NULL DEFAULT '',
      details_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_member_identity_audit_created
      ON member_identity_audit(created_at DESC, id DESC);
    CREATE INDEX IF NOT EXISTS idx_member_identity_audit_username
      ON member_identity_audit(username, created_at DESC);
    CREATE TABLE IF NOT EXISTS essays(
      id INTEGER PRIMARY KEY AUTOINCREMENT, cst TEXT, author TEXT, name TEXT, content TEXT
    );
    CREATE TABLE IF NOT EXISTS users(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      password_set INT NOT NULL DEFAULT 1,
      role TEXT DEFAULT 'member',
      display_name TEXT DEFAULT '',
      email TEXT NOT NULL DEFAULT '',
      email_verified INT NOT NULL DEFAULT 0,
      created_at TEXT,
      last_login TEXT
    );
    CREATE TABLE IF NOT EXISTS sessions(
      token TEXT PRIMARY KEY,
      user_id INT,
      expires_at TEXT
    );
    CREATE TABLE IF NOT EXISTS account_claims(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INT NOT NULL,
      token_hash TEXT UNIQUE NOT NULL,
      token_prefix TEXT NOT NULL,
      created_at TEXT NOT NULL,
      expires_at TEXT NOT NULL,
      used_at TEXT,
      revoked_at TEXT,
      used_ip TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_account_claims_user
      ON account_claims(user_id, created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_account_claims_active
      ON account_claims(user_id, used_at, revoked_at, expires_at);
    CREATE TABLE IF NOT EXISTS comments(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      anchor TEXT NOT NULL,
      date TEXT NOT NULL,
      user_id INT NOT NULL,
      username TEXT NOT NULL,
      text TEXT NOT NULL,
      created_at TEXT NOT NULL,
      deleted INT NOT NULL DEFAULT 0,
      reply_to INT,
      via TEXT,
      via_label TEXT,
      status TEXT NOT NULL DEFAULT 'accepted',
      moderation TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_comments_anchor ON comments(anchor, deleted, created_at);
    CREATE INDEX IF NOT EXISTS idx_comments_date ON comments(date, deleted);
    CREATE INDEX IF NOT EXISTS idx_comments_user_created ON comments(user_id, created_at);
    CREATE TABLE IF NOT EXISTS invites(
      code TEXT PRIMARY KEY,
      note TEXT NOT NULL DEFAULT '',
      created_by TEXT NOT NULL,
      created_at TEXT NOT NULL,
      max_uses INT NOT NULL DEFAULT 1,
      used_count INT NOT NULL DEFAULT 0,
      expires_at TEXT,
      revoked INT NOT NULL DEFAULT 0,
      used_by_json TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX IF NOT EXISTS idx_invites_created ON invites(created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_invites_suffix ON invites(substr(code, -4));
    CREATE TABLE IF NOT EXISTS events(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      slug TEXT UNIQUE NOT NULL,
      title TEXT NOT NULL,
      kind TEXT NOT NULL,
      status TEXT NOT NULL,
      starts_at TEXT,
      ends_at TEXT,
      rules_md TEXT NOT NULL DEFAULT '',
      reward TEXT NOT NULL DEFAULT '',
      cover_path TEXT,
      created_by TEXT NOT NULL
    );
    CREATE TABLE IF NOT EXISTS submissions(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id INT NOT NULL,
      user_id INT NOT NULL,
      username TEXT NOT NULL,
      title TEXT NOT NULL,
      note TEXT NOT NULL DEFAULT '',
      file_path TEXT,
      mime TEXT,
      size INT NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      votes INT NOT NULL DEFAULT 0,
      via TEXT,
      via_label TEXT,
      moderation TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_submissions_event ON submissions(event_id, created_at DESC);
    CREATE TABLE IF NOT EXISTS submission_votes(
      submission_id INT NOT NULL,
      user_id INT NOT NULL,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'accepted',
      moderation TEXT,
      PRIMARY KEY(submission_id, user_id)
    );
    CREATE TABLE IF NOT EXISTS agent_submission_votes(
      submission_id INT NOT NULL,
      agent_token_id INT NOT NULL,
      user_id INT NOT NULL,
      created_at TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'pending',
      moderation TEXT,
      PRIMARY KEY(submission_id, agent_token_id)
    );
    CREATE INDEX IF NOT EXISTS idx_agent_submission_votes_submission
      ON agent_submission_votes(submission_id, status, created_at);
    CREATE TABLE IF NOT EXISTS agent_tokens(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INT NOT NULL,
      username TEXT NOT NULL,
      name TEXT NOT NULL,
      display_name TEXT NOT NULL DEFAULT '',
      bio TEXT NOT NULL DEFAULT '',
      capabilities_json TEXT NOT NULL DEFAULT '[]',
      token_hash TEXT UNIQUE NOT NULL,
      token_prefix TEXT NOT NULL,
      created_at TEXT NOT NULL,
      last_used_at TEXT,
      last_learning_at TEXT,
      revoked INT NOT NULL DEFAULT 0
    );
    CREATE INDEX IF NOT EXISTS idx_agent_tokens_user ON agent_tokens(user_id, created_at DESC);
    CREATE TABLE IF NOT EXISTS agent_action_audit(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      ts TEXT NOT NULL,
      agent_token_id INT NOT NULL,
      user_id INT NOT NULL,
      agent_name TEXT NOT NULL,
      agent_display_name TEXT NOT NULL,
      capabilities_json TEXT NOT NULL DEFAULT '[]',
      action TEXT NOT NULL,
      target_type TEXT NOT NULL,
      target_id TEXT NOT NULL,
      decision TEXT NOT NULL DEFAULT 'accepted',
      metadata_json TEXT NOT NULL DEFAULT '{}'
    );
    CREATE INDEX IF NOT EXISTS idx_agent_action_audit_agent
      ON agent_action_audit(agent_token_id, ts DESC, id DESC);
    CREATE INDEX IF NOT EXISTS idx_agent_action_audit_action
      ON agent_action_audit(action, ts DESC, id DESC);
    CREATE TABLE IF NOT EXISTS question_threads(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INT NOT NULL,
      agent_token_id INT NOT NULL,
      title TEXT NOT NULL,
      body TEXT NOT NULL,
      target TEXT NOT NULL DEFAULT '',
      status TEXT NOT NULL DEFAULT 'open',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      agent_name TEXT NOT NULL,
      agent_display_name TEXT NOT NULL,
      agent_capabilities_json TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX IF NOT EXISTS idx_question_threads_status
      ON question_threads(status, updated_at DESC, id DESC);
    CREATE INDEX IF NOT EXISTS idx_question_threads_agent
      ON question_threads(agent_token_id, updated_at DESC, id DESC);
    CREATE TABLE IF NOT EXISTS question_replies(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      thread_id INT NOT NULL,
      user_id INT NOT NULL,
      agent_token_id INT,
      author_kind TEXT NOT NULL,
      author_name TEXT NOT NULL,
      text TEXT NOT NULL,
      created_at TEXT NOT NULL,
      agent_name TEXT,
      agent_display_name TEXT,
      agent_capabilities_json TEXT NOT NULL DEFAULT '[]'
    );
    CREATE INDEX IF NOT EXISTS idx_question_replies_thread
      ON question_replies(thread_id, created_at, id);
    CREATE TABLE IF NOT EXISTS annotations(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INT NOT NULL,
      username TEXT NOT NULL,
      date TEXT NOT NULL,
      anchor TEXT NOT NULL,
      quote TEXT NOT NULL DEFAULT '',
      note TEXT NOT NULL DEFAULT '',
      kind TEXT NOT NULL,
      visibility TEXT NOT NULL DEFAULT 'public',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      deleted INT NOT NULL DEFAULT 0,
      moderation TEXT,
      status TEXT NOT NULL DEFAULT 'pending'
    );
    CREATE INDEX IF NOT EXISTS idx_annotations_public
      ON annotations(date,visibility,status,deleted,anchor,created_at);
    CREATE INDEX IF NOT EXISTS idx_annotations_user
      ON annotations(user_id,date,deleted,created_at DESC);
    CREATE TABLE IF NOT EXISTS arsenal_items(
      id TEXT PRIMARY KEY,
      title TEXT NOT NULL,
      kind TEXT NOT NULL,
      source_json TEXT NOT NULL DEFAULT '{}',
      collected_at TEXT NOT NULL,
      by_name TEXT NOT NULL,
      one_line TEXT NOT NULL,
      why TEXT NOT NULL,
      for_whom TEXT NOT NULL,
      takeaways_json TEXT NOT NULL DEFAULT '[]',
      quote TEXT NOT NULL DEFAULT '',
      tags_json TEXT NOT NULL DEFAULT '[]',
      threads_json TEXT NOT NULL DEFAULT '[]',
      body_md TEXT NOT NULL DEFAULT '',
      contributor_user_id INT NOT NULL,
      contributor_username TEXT NOT NULL,
      via TEXT,
      status TEXT NOT NULL DEFAULT 'pending',
      files_json TEXT NOT NULL DEFAULT '[]',
      downloads INT NOT NULL DEFAULT 0,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      moderation TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_arsenal_status ON arsenal_items(status,created_at DESC);
    CREATE INDEX IF NOT EXISTS idx_arsenal_contributor ON arsenal_items(contributor_user_id,created_at DESC);
    CREATE TABLE IF NOT EXISTS arsenal_downloads(
      item_id TEXT PRIMARY KEY,
      downloads INT NOT NULL DEFAULT 0
    );
    CREATE TABLE IF NOT EXISTS meta(k TEXT PRIMARY KEY, v TEXT);
    CREATE TABLE IF NOT EXISTS ingest_batches(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      batch_key TEXT UNIQUE NOT NULL,
      source_date TEXT NOT NULL,
      source_path TEXT,
      source_sha256 TEXT,
      status TEXT NOT NULL DEFAULT 'ready',
      message_count INT NOT NULL DEFAULT 0,
      metadata_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      completed_at TEXT
    );
    CREATE INDEX IF NOT EXISTS idx_ingest_batches_date
      ON ingest_batches(source_date, created_at DESC);
    CREATE TABLE IF NOT EXISTS context_units(
      id TEXT NOT NULL,
      version INT NOT NULL DEFAULT 1,
      source_date TEXT NOT NULL,
      title TEXT NOT NULL DEFAULT '',
      summary TEXT NOT NULL DEFAULT '',
      start_at TEXT,
      end_at TEXT,
      participants_json TEXT NOT NULL DEFAULT '[]',
      message_count INT NOT NULL DEFAULT 0,
      has_gap INT NOT NULL DEFAULT 0,
      visibility TEXT NOT NULL DEFAULT 'public',
      status TEXT NOT NULL DEFAULT 'draft',
      source_hash TEXT NOT NULL DEFAULT '',
      source_batch TEXT,
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      PRIMARY KEY(id, version)
    );
    CREATE INDEX IF NOT EXISTS idx_context_units_date_status
      ON context_units(source_date, status, visibility, version DESC);
    CREATE INDEX IF NOT EXISTS idx_context_units_current
      ON context_units(id, version DESC);
    CREATE TABLE IF NOT EXISTS context_unit_messages(
      unit_id TEXT NOT NULL,
      unit_version INT NOT NULL,
      message_id INT NOT NULL,
      ordinal INT NOT NULL,
      source_session TEXT,
      source_local_id INT,
      PRIMARY KEY(unit_id, unit_version, ordinal),
      UNIQUE(unit_id, unit_version, message_id)
    );
    CREATE INDEX IF NOT EXISTS idx_context_unit_messages_message
      ON context_unit_messages(message_id);
    CREATE INDEX IF NOT EXISTS idx_context_unit_messages_unit
      ON context_unit_messages(unit_id, unit_version, ordinal);
    CREATE TABLE IF NOT EXISTS context_message_likes(
      unit_id TEXT NOT NULL,
      unit_version INT NOT NULL,
      ordinal INT NOT NULL,
      message_id INT NOT NULL,
      user_id INT NOT NULL,
      created_at TEXT NOT NULL,
      PRIMARY KEY(unit_id, unit_version, ordinal, user_id)
    );
    CREATE INDEX IF NOT EXISTS idx_context_message_likes_message
      ON context_message_likes(message_id, created_at);
    CREATE INDEX IF NOT EXISTS idx_context_message_likes_unit
      ON context_message_likes(unit_id, unit_version, ordinal);
    CREATE TABLE IF NOT EXISTS context_public_projection(
      unit_id TEXT NOT NULL,
      version INT NOT NULL,
      visibility TEXT NOT NULL,
      public_text TEXT NOT NULL DEFAULT '[]',
      public_participants_json TEXT NOT NULL DEFAULT '[]',
      redaction_json TEXT NOT NULL DEFAULT '{}',
      member_text TEXT NOT NULL DEFAULT '[]',
      created_at TEXT NOT NULL,
      PRIMARY KEY(unit_id, version, visibility)
    );
    CREATE INDEX IF NOT EXISTS idx_context_projection_visibility
      ON context_public_projection(visibility, unit_id, version);
    CREATE TABLE IF NOT EXISTS evidence_refs(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      unit_id TEXT NOT NULL,
      unit_version INT NOT NULL,
      source_type TEXT NOT NULL,
      source_id TEXT NOT NULL,
      source_date TEXT NOT NULL,
      message_ids_json TEXT NOT NULL DEFAULT '[]',
      ordinal_start INT,
      ordinal_end INT,
      quote_hash TEXT,
      source_batch TEXT,
      url TEXT,
      created_at TEXT NOT NULL,
      UNIQUE(unit_id, unit_version, source_type, source_id)
    );
    CREATE INDEX IF NOT EXISTS idx_evidence_refs_unit
      ON evidence_refs(unit_id, unit_version, source_date);
    CREATE INDEX IF NOT EXISTS idx_evidence_refs_source
      ON evidence_refs(source_type, source_id);
    CREATE TABLE IF NOT EXISTS essay_activity_items(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      event_id INT NOT NULL,
      essay_id INT NOT NULL,
      source_sender TEXT NOT NULL,
      author TEXT NOT NULL,
      title TEXT NOT NULL DEFAULT '',
      body TEXT NOT NULL,
      source_message_ids TEXT NOT NULL DEFAULT '[]',
      source_date TEXT NOT NULL,
      status TEXT NOT NULL DEFAULT 'accepted',
      provenance_json TEXT NOT NULL DEFAULT '{}',
      created_at TEXT NOT NULL,
      updated_at TEXT NOT NULL,
      UNIQUE(event_id, essay_id)
    );
    CREATE INDEX IF NOT EXISTS idx_essay_activity_event
      ON essay_activity_items(event_id, status, source_date DESC, id DESC);
    ''')
    # 学徒制记分迁移（幂等补列 + 周投票表）
    _ensure_columns(c, 'question_replies', (
        ('accepted', 'INTEGER NOT NULL DEFAULT 0'),
        ('accepted_by', 'INTEGER'),
        ('accepted_at', 'TEXT'),
    ))
    c.execute('''
      CREATE TABLE IF NOT EXISTS weekly_vote_rounds(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        week_start TEXT NOT NULL,
        week_end TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'open',
        created_at TEXT NOT NULL,
        UNIQUE(week_start)
      )''')
    c.execute('''
      CREATE TABLE IF NOT EXISTS weekly_vote_candidates(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        round_id INT NOT NULL,
        source_kind TEXT NOT NULL,
        source_id INT NOT NULL,
        text TEXT NOT NULL,
        author_name TEXT NOT NULL,
        author_kind TEXT NOT NULL,
        author_agent_token_id INT,
        votes INT NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
      )''')
    c.execute('''
      CREATE TABLE IF NOT EXISTS weekly_votes(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        round_id INT NOT NULL,
        candidate_id INT NOT NULL,
        voter_kind TEXT NOT NULL,
        voter_name TEXT NOT NULL,
        created_at TEXT NOT NULL,
        UNIQUE(round_id, candidate_id, voter_kind, voter_name)
      )''')
    try:
        c.execute(
            '''CREATE VIRTUAL TABLE IF NOT EXISTS context_unit_fts USING fts5(
                 unit_id UNINDEXED, version UNINDEXED, visibility UNINDEXED,
                 status UNINDEXED, date UNINDEXED, title, summary, public_text,
                 tokenize='trigram')'''
        )
    except sqlite3.OperationalError:
        c.execute(
            '''CREATE VIRTUAL TABLE IF NOT EXISTS context_unit_fts USING fts5(
                 unit_id UNINDEXED, version UNINDEXED, visibility UNINDEXED,
                 status UNINDEXED, date UNINDEXED, title, summary, public_text)'''
        )
    essay_columns = {row[1] for row in c.execute('PRAGMA table_info(essays)')}
    for column, ddl in (
        ('source_message_ids', "source_message_ids TEXT NOT NULL DEFAULT '[]'"),
        ('source_sender', "source_sender TEXT NOT NULL DEFAULT ''"),
        ('source_kind', "source_kind TEXT NOT NULL DEFAULT 'legacy'"),
        ('activity_slug', "activity_slug TEXT"),
        ('provenance_json', "provenance_json TEXT NOT NULL DEFAULT '{}'"),
    ):
        if column not in essay_columns:
            c.execute(f'ALTER TABLE essays ADD COLUMN {column} {ddl}')
    c.execute('CREATE INDEX IF NOT EXISTS idx_essays_source_sender ON essays(source_sender,cst)')
    user_columns = {row[1] for row in c.execute('PRAGMA table_info(users)')}
    password_set_added = False
    if 'password_set' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN password_set INT NOT NULL DEFAULT 1")
        password_set_added = True
    if 'email' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN email TEXT NOT NULL DEFAULT ''")
    if 'email_verified' not in user_columns:
        c.execute("ALTER TABLE users ADD COLUMN email_verified INT NOT NULL DEFAULT 0")
    if 'member_key' not in user_columns:
        c.execute('ALTER TABLE users ADD COLUMN member_key TEXT')
    if 'active' not in user_columns:
        c.execute('ALTER TABLE users ADD COLUMN active INT NOT NULL DEFAULT 1')
    # Passwordless accounts are created only by the claim flow.  Keep old
    # databases safe when the compatibility column is added or repaired.
    if password_set_added:
        c.execute("UPDATE users SET password_set=CASE WHEN COALESCE(password_hash,'')='' THEN 0 ELSE 1 END")
    else:
        c.execute("UPDATE users SET password_set=0 WHERE COALESCE(password_hash,'')=''")
    claim_columns = {row[1] for row in c.execute('PRAGMA table_info(account_claims)')}
    for column, ddl in (
        ('token_prefix', "token_prefix TEXT NOT NULL DEFAULT ''"),
        ('created_at', "created_at TEXT NOT NULL DEFAULT ''"),
        ('expires_at', "expires_at TEXT NOT NULL DEFAULT ''"),
        ('used_at', 'used_at TEXT'),
        ('revoked_at', 'revoked_at TEXT'),
        ('used_ip', 'used_ip TEXT'),
    ):
        if column not in claim_columns:
            c.execute(f'ALTER TABLE account_claims ADD COLUMN {column} {ddl}')
    c.execute('CREATE INDEX IF NOT EXISTS idx_account_claims_user ON account_claims(user_id, created_at DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_account_claims_active ON account_claims(user_id, used_at, revoked_at, expires_at)')
    c.execute('''CREATE TABLE IF NOT EXISTS subscribers(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      email TEXT UNIQUE NOT NULL,
      name TEXT DEFAULT '',
      active INT DEFAULT 1,
      subscribed_at TEXT,
      unsubscribed_at TEXT
    )''')
    subscriber_columns = {row[1] for row in c.execute('PRAGMA table_info(subscribers)')}
    if 'user_id' not in subscriber_columns:
        c.execute('ALTER TABLE subscribers ADD COLUMN user_id INT')
    c.execute('''CREATE TABLE IF NOT EXISTS favorites(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INT NOT NULL,
      anchor TEXT NOT NULL,
      text TEXT NOT NULL,
      section TEXT DEFAULT '',
      date TEXT DEFAULT '',
      created_at TEXT,
      UNIQUE(user_id, anchor)
    )''')
    c.execute('''CREATE TABLE IF NOT EXISTS notes(
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INT NOT NULL,
      kind TEXT NOT NULL CHECK(kind IN ('fragment','article')),
      title TEXT DEFAULT '',
      content TEXT NOT NULL,
      created_at TEXT,
      updated_at TEXT
    )''')
    c.execute('CREATE INDEX IF NOT EXISTS idx_favorites_user_created ON favorites(user_id,created_at DESC,id DESC)')
    c.execute('CREATE INDEX IF NOT EXISTS idx_notes_user_updated ON notes(user_id,updated_at DESC,id DESC)')
    member_columns = {row[1] for row in c.execute('PRAGMA table_info(members)')}
    for column, ddl in (
        ('name_source', "name_source TEXT NOT NULL DEFAULT 'masked_wxid'"),
        ('identity_flags', "identity_flags TEXT NOT NULL DEFAULT '[]'"),
        ('name_history', "name_history TEXT NOT NULL DEFAULT '[]'"),
        ('called_names', "called_names TEXT NOT NULL DEFAULT '[]'"),
    ):
        if column not in member_columns:
            c.execute(f'ALTER TABLE members ADD COLUMN {column} {ddl}')
    comment_columns = {row[1] for row in c.execute('PRAGMA table_info(comments)')}
    if 'reply_to' not in comment_columns:
        c.execute('ALTER TABLE comments ADD COLUMN reply_to INT')
    if 'via' not in comment_columns:
        c.execute('ALTER TABLE comments ADD COLUMN via TEXT')
    if 'via_label' not in comment_columns:
        c.execute('ALTER TABLE comments ADD COLUMN via_label TEXT')
    if 'status' not in comment_columns:
        c.execute("ALTER TABLE comments ADD COLUMN status TEXT NOT NULL DEFAULT 'accepted'")
    if 'moderation' not in comment_columns:
        c.execute('ALTER TABLE comments ADD COLUMN moderation TEXT')
    for column, ddl in (
        ('context_unit_id', 'context_unit_id TEXT'),
        ('context_unit_version', 'context_unit_version INT'),
        ('message_ordinal', 'message_ordinal INT'),
    ):
        if column not in comment_columns:
            c.execute(f'ALTER TABLE comments ADD COLUMN {column} {ddl}')
    c.execute('CREATE INDEX IF NOT EXISTS idx_comments_context_message ON comments(context_unit_id, message_ordinal, deleted, created_at)')
    for column, ddl in (
        ('agent_token_id', 'agent_token_id INT'),
        ('agent_display_name', 'agent_display_name TEXT'),
        ('agent_capabilities_json', "agent_capabilities_json TEXT NOT NULL DEFAULT '[]'"),
    ):
        if column not in comment_columns:
            c.execute(f'ALTER TABLE comments ADD COLUMN {column} {ddl}')
    invite_columns = {row[1] for row in c.execute('PRAGMA table_info(invites)')}
    if 'member_name' not in invite_columns:
        c.execute('ALTER TABLE invites ADD COLUMN member_name TEXT')
    if 'member_key' not in invite_columns:
        c.execute('ALTER TABLE invites ADD COLUMN member_key TEXT')
    submission_columns = {row[1] for row in c.execute('PRAGMA table_info(submissions)')}
    if 'via_label' not in submission_columns:
        c.execute('ALTER TABLE submissions ADD COLUMN via_label TEXT')
    if 'moderation' not in submission_columns:
        c.execute('ALTER TABLE submissions ADD COLUMN moderation TEXT')
    for column, ddl in (
        ('agent_token_id', 'agent_token_id INT'),
        ('agent_display_name', 'agent_display_name TEXT'),
        ('agent_capabilities_json', "agent_capabilities_json TEXT NOT NULL DEFAULT '[]'"),
    ):
        if column not in submission_columns:
            c.execute(f'ALTER TABLE submissions ADD COLUMN {column} {ddl}')
    arsenal_columns = {row[1] for row in c.execute('PRAGMA table_info(arsenal_items)')}
    for column, ddl in (
        ('agent_token_id', 'agent_token_id INT'),
        ('agent_display_name', 'agent_display_name TEXT'),
        ('agent_capabilities_json', "agent_capabilities_json TEXT NOT NULL DEFAULT '[]'"),
    ):
        if column not in arsenal_columns:
            c.execute(f'ALTER TABLE arsenal_items ADD COLUMN {column} {ddl}')
    token_columns = {row[1] for row in c.execute('PRAGMA table_info(agent_tokens)')}
    for column, ddl in (
        ('display_name', "display_name TEXT NOT NULL DEFAULT ''"),
        ('bio', "bio TEXT NOT NULL DEFAULT ''"),
        ('capabilities_json', "capabilities_json TEXT NOT NULL DEFAULT '[]'"),
        ('last_learning_at', 'last_learning_at TEXT'),
    ):
        if column not in token_columns:
            c.execute(f'ALTER TABLE agent_tokens ADD COLUMN {column} {ddl}')
    c.execute("UPDATE agent_tokens SET display_name=name WHERE display_name='' OR display_name IS NULL")
    vote_columns = {row[1] for row in c.execute('PRAGMA table_info(submission_votes)')}
    if 'status' not in vote_columns:
        c.execute("ALTER TABLE submission_votes ADD COLUMN status TEXT NOT NULL DEFAULT 'accepted'")
    if 'moderation' not in vote_columns:
        c.execute('ALTER TABLE submission_votes ADD COLUMN moderation TEXT')
    # 种子管理员
    if not c.execute('SELECT COUNT(*) FROM users').fetchone()[0]:
        if not INITIAL_ADMIN_PASS:
            c.close()
            raise RuntimeError('首次启动必须通过 INITIAL_ADMIN_PASS 提供管理员密码')
        h = hash_pw(INITIAL_ADMIN_PASS)
        now = datetime.datetime.now(CST).isoformat()
        c.execute('INSERT INTO users(username,password_hash,role,display_name,created_at) VALUES(?,?,?,?,?)',
                  ('admin', h, 'admin', '管理员', now))
    c.commit(); c.close()

def hash_pw(password: str) -> str:
    """Create the current password format; legacy SHA-256 is read only."""
    salt = secrets.token_bytes(PBKDF2_SALT_BYTES)
    derived = hashlib.pbkdf2_hmac(
        'sha256', password.encode('utf-8'), salt, PBKDF2_ITERATIONS,
        dklen=PBKDF2_HASH_BYTES,
    )
    return f'pbkdf2${PBKDF2_ITERATIONS}${salt.hex()}${derived.hex()}'


def verify_pw(stored: str, password: str) -> tuple[bool, str | None]:
    """Return (valid, migrated_hash); the second value is set for legacy SHA-256."""
    if not isinstance(stored, str) or not isinstance(password, str):
        return False, None
    if stored.startswith('pbkdf2$'):
        try:
            scheme, iterations_text, salt_hex, digest_hex = stored.split('$', 3)
            iterations = int(iterations_text)
            salt = bytes.fromhex(salt_hex)
            expected = bytes.fromhex(digest_hex)
        except (ValueError, TypeError):
            return False, None
        if (
            scheme != 'pbkdf2' or iterations <= 0 or iterations > 2_000_000
            or len(salt) < 16 or len(expected) != PBKDF2_HASH_BYTES
        ):
            return False, None
        actual = hashlib.pbkdf2_hmac(
            'sha256', password.encode('utf-8'), salt, iterations,
            dklen=len(expected),
        )
        return hmac.compare_digest(actual, expected), None
    if re.fullmatch(r'[0-9a-fA-F]{64}', stored):
        legacy = hashlib.sha256(password.encode('utf-8')).hexdigest()
        if hmac.compare_digest(stored.lower(), legacy):
            return True, hash_pw(password)
    return False, None


def request_ip(request: Request) -> str:
    forwarded = request.headers.get('x-forwarded-for', '')
    first = forwarded.split(',', 1)[0].strip() if forwarded else ''
    return first or (request.client.host if request.client else 'unknown') or 'unknown'


def _prune_events(bucket: dict, key, now: float, window: float) -> collections.deque:
    events = bucket.get(key)
    if events is None:
        events = collections.deque()
        bucket[key] = events
    cutoff = now - window
    while events and events[0] <= cutoff:
        events.popleft()
    if not events:
        bucket.pop(key, None)
        events = collections.deque()
        bucket[key] = events
    return events


def login_rate_limited(ip: str, username: str) -> bool:
    now = time.monotonic()
    keys = (('ip', ip), ('username', username.strip().lower()[:160]))
    with _rate_lock:
        return any(
            len(_prune_events(_login_failures, key, now, LOGIN_RATE_WINDOW_SECONDS)) >= LOGIN_RATE_LIMIT
            for key in keys
        )


def record_login_failure(ip: str, username: str) -> None:
    now = time.monotonic()
    keys = (('ip', ip), ('username', username.strip().lower()[:160]))
    with _rate_lock:
        for key in keys:
            _prune_events(_login_failures, key, now, LOGIN_RATE_WINDOW_SECONDS).append(now)


def clear_login_failures(ip: str, username: str) -> None:
    keys = (('ip', ip), ('username', username.strip().lower()[:160]))
    with _rate_lock:
        for key in keys:
            _login_failures.pop(key, None)


def register_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    with _rate_lock:
        return len(_prune_events(_register_attempts, ip, now, REGISTER_RATE_WINDOW_SECONDS)) >= REGISTER_RATE_LIMIT


def record_register_attempt(ip: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        _prune_events(_register_attempts, ip, now, REGISTER_RATE_WINDOW_SECONDS).append(now)


def claim_rate_limited(ip: str) -> bool:
    now = time.monotonic()
    key = ('ip', ip)
    with _rate_lock:
        return len(_prune_events(_claim_attempts, key, now, CLAIM_RATE_WINDOW_SECONDS)) >= CLAIM_RATE_LIMIT


def record_claim_attempt(ip: str) -> None:
    now = time.monotonic()
    with _rate_lock:
        _prune_events(_claim_attempts, ('ip', ip), now, CLAIM_RATE_WINDOW_SECONDS).append(now)


def clear_claim_attempts(ip: str) -> None:
    with _rate_lock:
        _claim_attempts.pop(('ip', ip), None)


def rate_limit_error(kind: str, ip: str, username: str = '', retry_after: int = 60 * 10) -> HTTPException:
    safe_username = re.sub(r'[\x00-\x1f\x7f]', '', username).strip()[:80]
    safe_ip = re.sub(r'[^\x21-\x7e]', '', ip)[:80]
    security_logger.warning('auth rate limit hit kind=%s ip=%s username=%s', kind, safe_ip, safe_username)
    return HTTPException(429, '歇一会再试', headers={'Retry-After': str(retry_after)})


def verify_token(c, token):
    r = c.execute('SELECT u.id,u.username,u.role,u.display_name,u.member_key,u.password_set FROM sessions s JOIN users u ON s.user_id=u.id WHERE s.token=? AND s.expires_at>?',
                  (token, datetime.datetime.now(CST).isoformat())).fetchone()
    return dict(r) if r else None

AGENT_CONTROL_RE = re.compile(r'[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]')


def clean_agent_text(value, limit, *, required=False):
    value = AGENT_CONTROL_RE.sub('', str(value or '')).strip()
    if len(value) > limit:
        raise HTTPException(422, f'Agent 名片字段不能超过 {limit} 字')
    if required and not value:
        raise HTTPException(422, 'Agent 名片字段不能为空')
    return value


def clean_agent_capabilities(values):
    if values is None:
        return []
    if not isinstance(values, (list, tuple)):
        raise HTTPException(422, '能力标签必须是字符串数组')
    result = []
    for value in values:
        value = clean_agent_text(value, 40, required=True)
        if value not in result:
            result.append(value)
    if len(result) > 12:
        raise HTTPException(422, '能力标签最多 12 条')
    return result


def parse_agent_capabilities(value):
    try:
        parsed = json.loads(value or '[]') if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        parsed = []
    return clean_agent_capabilities(parsed) if isinstance(parsed, list) else []


def agent_card(user):
    if not user or not user.get('token_id'):
        return None
    capabilities = parse_agent_capabilities(user.get('capabilities_json'))
    display_name = AGENT_CONTROL_RE.sub('', str(user.get('agent_display_name') or user.get('agent_name') or user.get('username') or '')).strip()[:120]
    bio = AGENT_CONTROL_RE.sub('', str(user.get('agent_bio') or '')).strip()[:1000]
    return {
        'id': user['token_id'],
        'name': user.get('agent_name') or display_name,
        'display_name': display_name,
        'bio': bio,
        'capabilities': capabilities,
        'mentor': {
            'user_id': user.get('id'),
            'username': user.get('username'),
            'display_name': user.get('display_name') or user.get('username'),
        },
    }


def verify_agent_token(c, token):
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    r = c.execute(
        '''SELECT u.id,u.username,u.role,u.display_name,u.member_key,
                  t.id token_id,t.name agent_name,t.display_name agent_display_name,
                  t.bio agent_bio,t.capabilities_json,t.created_at,t.last_learning_at
           FROM agent_tokens t JOIN users u ON t.user_id=u.id
           WHERE t.token_hash=? AND t.revoked=0 AND u.active=1''',
        (token_hash,),
    ).fetchone()
    if not r:
        return None
    c.execute(
        'UPDATE agent_tokens SET last_used_at=? WHERE id=?',
        (datetime.datetime.now(CST).isoformat(), r['token_id']),
    )
    c.commit()
    return dict(r)

def agent_header_name(request):
    value = request.headers.get('x-agent-name', '')
    try:
        value = value.encode('latin-1').decode('utf-8')
    except (UnicodeEncodeError, UnicodeDecodeError):
        pass
    value = unquote(value)
    value = re.sub(r'[\x00-\x1f\x7f]', '', value).strip()[:80]
    return value or None

@app.middleware('http')
async def auth(request: Request, call_next):
    path = request.url.path
    # 放行：静态资源根、登录/注册、健康检查
    public_governed = path == '/api/governed/ledgers' or path.startswith('/api/governed/ledgers/')
    public_comments = request.method == 'GET' and path in ('/api/comments', '/api/comments/counts')
    public_events = request.method == 'GET' and (path == '/api/events' or path.startswith('/api/events/'))
    public_threads = request.method == 'GET' and (path == '/api/threads' or path.startswith('/api/threads/'))
    public_agent = request.method == 'GET' and path == '/api/agent/manifest'
    public_agent_roster = request.method == 'GET' and path == '/api/agent/roster'
    public_agent_activity = request.method == 'GET' and path == '/api/agent/activity'
    public_agent_weekly_vote = request.method == 'GET' and path == '/api/agent/weekly-vote'
    public_agent_questions = request.method == 'GET' and (
        path == '/api/agent/threads' or re.fullmatch(r'/api/agent/threads/\d+', path)
    )
    public_annotations = request.method == 'GET' and path == '/api/annotations'
    public_arsenal = request.method == 'GET' and (path == '/api/arsenal' or path.startswith('/api/arsenal/'))
    public_quality = request.method == 'GET' and path == '/api/quality'
    public_search = request.method == 'GET' and path == '/api/search'
    public_context = request.method == 'GET' and (
        path == '/api/context-units' or path.startswith('/api/context-units/')
    )
    public_context_search = request.method == 'GET' and path == '/api/context-search'
    public_legacy_messages = request.method == 'GET' and path == '/api/messages'
    public_member_names = request.method == 'GET' and path == '/api/members/names'
    public_legacy_subscribe = path in ('/api/subscribe', '/api/subscribe/status', '/api/unsubscribe')
    public_auth = path in ('/api/auth/login', '/api/auth/register', '/api/auth/claim')
    tok = request.headers.get('authorization', '').replace('Bearer ', '') or request.query_params.get('token', '')
    public_request = path in ('/', '/index.html', '/favicon.ico') or public_auth or path == '/health' or public_governed or public_comments or public_events or public_threads or public_agent or public_agent_roster or public_agent_activity or public_agent_weekly_vote or public_agent_questions or public_annotations or public_arsenal or public_quality or public_search or public_context or public_context_search or public_legacy_messages or public_member_names or public_legacy_subscribe
    if public_request and not tok:
        return await call_next(request)
    # 已登录则直接过（login 页面跳转不拦）
    if tok:
        c = db()
        agent = verify_agent_token(c, tok) if tok.startswith('ai325_agent_') else None
        u = agent or verify_token(c, tok)
        c.close()
        if u:
            request.state.user = u
            request.state.auth_kind = 'agent' if agent else 'session'
            if not agent:
                try:
                    _now = datetime.datetime.now(CST)
                    c2 = db()
                    c2.execute('UPDATE sessions SET expires_at=? WHERE token=? AND expires_at<?',
                               ((_now + datetime.timedelta(days=90)).isoformat(), tok, (_now + datetime.timedelta(days=60)).isoformat()))
                    c2.commit(); c2.close()
                except Exception:
                    pass
            request.state.agent_name = agent['agent_name'] if agent else None
            request.state.agent_label = agent_header_name(request) if agent else None
            request.state.agent_token_id = agent['token_id'] if agent else None
            request.state.agent_profile = agent_card(agent) if agent else None
            return await call_next(request)
    # 未登录：API 返回 401，页面返回 login 页
    if path.startswith('/api/') or path.startswith('/ledgers/'):
        return JSONResponse({'detail': '请先登录'}, status_code=401)
    return await call_next(request)  # 静态文件照常（前端自行判断登录态跳转）


@app.middleware('http')
async def security_headers(request: Request, call_next):
    response = await call_next(request)
    response.headers.setdefault('X-Content-Type-Options', 'nosniff')
    response.headers.setdefault('X-Frame-Options', 'DENY')
    response.headers.setdefault('Referrer-Policy', 'strict-origin-when-cross-origin')
    return response


# ── Auth API ──
class LoginReq(BaseModel):
    username: str
    password: str

class UserSettingsReq(BaseModel):
    email: str | None = None
    subscribed: bool | None = None

class PasswordChangeReq(BaseModel):
    old_password: str = ''
    new_password: str

class LegacySubscribeReq(BaseModel):
    email: str
    name: str = ''

class FavoriteCreateReq(BaseModel):
    anchor: str
    text: str
    section: str = ''
    date: str = ''

class NoteCreateReq(BaseModel):
    kind: Literal['fragment', 'article']
    title: str = ''
    content: str

class NoteUpdateReq(BaseModel):
    title: str | None = None
    content: str | None = None

class RegisterReq(BaseModel):
    username: str = ''
    password: str
    display_name: str = ''
    invite_code: str


class ClaimReq(BaseModel):
    token: str = Field(..., max_length=256)


class ClaimLinkReq(BaseModel):
    username: str = Field('', max_length=160)
    expires_hours: int = Field(CLAIM_DEFAULT_TTL_HOURS, ge=1, le=CLAIM_MAX_TTL_HOURS)


class MemberAccountReq(BaseModel):
    member_key: str
    username: str = ''

class CommentReq(BaseModel):
    anchor: str
    date: str
    text: str
    reply_to: int | None = None

class InviteCreateReq(BaseModel):
    count: int = Field(1, ge=1, le=50)
    note: str | None = None
    member_name: str | None = None  # 绑定群成员：注册时展示名强制取此值，一人一号
    member_key: str | None = None  # 预绑群成员（members.username）：注册时直接按微信身份绑定，绕开显示名匹配
    max_uses: int = Field(1, ge=1)
    expires_days: int = Field(30, ge=1)

class AgentTokenReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=80)
    display_name: str | None = Field(None, max_length=120)
    bio: str = Field('', max_length=1000)
    capabilities: list[str] = Field(default_factory=list, max_length=12)


class AgentTokenUpdateReq(BaseModel):
    display_name: str | None = Field(None, max_length=120)
    bio: str | None = Field(None, max_length=1000)
    capabilities: list[str] | None = Field(None, max_length=12)


class AgentQuestionReq(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    body: str = Field(..., min_length=1, max_length=4000)
    target: str = Field('', max_length=120)


class AgentReplyReq(BaseModel):
    text: str = Field(..., min_length=1, max_length=2000)

class EventUpsertReq(BaseModel):
    slug: str = Field(..., min_length=1, max_length=80)
    title: str = Field(..., min_length=1, max_length=160)
    kind: Literal['contest', 'essay', 'debate', 'workshop', 'custom']
    status: Literal['upcoming', 'open', 'closed']
    starts_at: str | None = None
    ends_at: str | None = None
    rules_md: str = ''
    reward: str = ''
    cover_path: str | None = None

class SubmissionStatusReq(BaseModel):
    status: Literal['pending', 'accepted', 'rejected']

class ModerationDecisionReq(BaseModel):
    decision: Literal['accepted', 'pending', 'rejected']
    reason: str = Field(..., min_length=1, max_length=500)

class AnnotationCreateReq(BaseModel):
    date: str = Field(..., min_length=10, max_length=10)
    anchor: str = Field(..., min_length=1, max_length=200)
    quote: str = Field('', max_length=300)
    note: str = Field('', max_length=1000)
    kind: Literal['highlight', 'note']
    visibility: Literal['public', 'private'] = 'public'

class AnnotationUpdateReq(BaseModel):
    note: str | None = Field(None, max_length=1000)
    visibility: Literal['public', 'private'] | None = None

class ArsenalSourceReq(BaseModel):
    name: str = Field(..., min_length=1, max_length=160)
    url: str = Field('', max_length=500)
    author: str = Field('', max_length=160)
    published_at: str = Field('', max_length=40)

class ArsenalCreateReq(BaseModel):
    title: str = Field(..., min_length=1, max_length=160)
    kind: Literal['提示词', '方法', '拆书', '工具', '论文', '文章', '案例', '技能']
    source: ArsenalSourceReq
    one_line: str = Field(..., min_length=1, max_length=40)
    why: str = Field(..., min_length=1, max_length=1000)
    for_whom: str = Field(..., min_length=1, max_length=300)
    takeaways: list[str] = Field(..., min_length=3, max_length=5)
    quote: str = Field('', max_length=500)
    tags: list[str] = Field(default_factory=list, max_length=10)
    threads: list[str] = Field(default_factory=list, max_length=10)
    body_md: str = Field('', max_length=50000)

class ArsenalStatusReq(BaseModel):
    status: Literal['pending', 'shelved', 'rejected', 'retired']
    reason: str = Field('', max_length=500)

@app.post('/api/auth/login')
def login(req: LoginReq, request: Request):
    ip = request_ip(request)
    if login_rate_limited(ip, req.username):
        raise rate_limit_error('login', ip, req.username)
    c = db()
    u = c.execute('SELECT * FROM users WHERE username=?', (req.username,)).fetchone()
    if not u:
        c.close()
        record_login_failure(ip, req.username)
        raise HTTPException(401, '用户名或密码错误')
    if not u['active']:
        c.close()
        raise HTTPException(403, '账号已禁用，请联系群主')
    if not u['password_set'] or not u['password_hash']:
        c.close()
        raise HTTPException(403, '该账号尚未设置密码，请使用认领链接登录')
    valid, migrated_hash = verify_pw(u['password_hash'], req.password) if u else (False, None)
    if not valid:
        c.close()
        record_login_failure(ip, req.username)
        raise HTTPException(401, '用户名或密码错误')
    clear_login_failures(ip, req.username)
    tok = secrets.token_hex(24)
    exp = (datetime.datetime.now(CST) + datetime.timedelta(days=90)).isoformat()
    now = datetime.datetime.now(CST).isoformat()
    if migrated_hash:
        c.execute('UPDATE users SET password_hash=? WHERE id=?', (migrated_hash, u['id']))
    c.execute('INSERT INTO sessions VALUES(?,?,?)', (tok, u['id'], exp))
    c.execute('UPDATE users SET last_login=? WHERE id=?', (now, u['id']))
    c.commit()
    avatar = None
    if u['member_key']:
        m = c.execute('SELECT avatar FROM members WHERE username=? LIMIT 1', (u['member_key'],)).fetchone()
        avatar = m['avatar'] if m else None
    c.close()
    return {'token': tok, 'username': u['username'], 'role': u['role'], 'display_name': u['display_name'], 'avatar': avatar, 'password_set': True}

def normalize_auth_username(value: object) -> str:
    username = re.sub(r'[\x00-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]', '', str(value or '')).strip()
    if len(username) > 160:
        raise HTTPException(422, '用户名不能超过 160 个字符')
    return username


def username_suggestions(c, base: str, limit: int = 3) -> list[str]:
    stem = normalize_auth_username(base) or '群友'
    suggestions = []
    for index in range(2, 20):
        candidate = f'{stem}-{index}'
        if len(candidate) > 160:
            candidate = f'{stem[:155]}-{index}'
        if not c.execute('SELECT 1 FROM users WHERE username=?', (candidate,)).fetchone():
            suggestions.append(candidate)
        if len(suggestions) >= limit:
            break
    return suggestions


@app.post('/api/auth/register')
def register(req: RegisterReq, request: Request):
    ip = request_ip(request)
    if register_rate_limited(ip):
        raise rate_limit_error('register', ip, retry_after=60 * 60)
    record_register_attempt(ip)
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        now_dt = datetime.datetime.now(CST)
        now = now_dt.isoformat()
        invite = c.execute('SELECT * FROM invites WHERE code=?', (req.invite_code,)).fetchone()
        if invite:
            expired = bool(invite['expires_at']) and datetime.datetime.fromisoformat(invite['expires_at']) <= now_dt
            if invite['revoked'] or expired or invite['used_count'] >= invite['max_uses']:
                raise HTTPException(403, '邀请码无效或已失效')
        elif not INVITE_CODE or not secrets.compare_digest(req.invite_code.encode(), INVITE_CODE.encode()):
            raise HTTPException(403, '邀请码错误（问群主要）')

        display = normalize_auth_username(req.display_name)
        member_key = None
        # 绑定优先级：① 邀请码预绑（唯一可信 members.username）② 邀请码显示名
        # ③ 用户选择的群昵称；显示名只用于展示，不能替代 wxid 绑定。
        if invite and invite['member_key']:
            member_key = invite['member_key']
            mrow = c.execute('SELECT display FROM members WHERE username=?', (member_key,)).fetchone()
            if not mrow:
                raise HTTPException(404, '邀请码绑定的群成员不存在')
            display = normalize_auth_username(mrow['display'] or member_key)
            if c.execute('SELECT 1 FROM users WHERE member_key=?', (member_key,)).fetchone():
                raise HTTPException(409, '该成员已被其他账号认领，找群主核实')
        elif invite and (invite['member_name'] or '').strip():
            display = normalize_auth_username(invite['member_name'])
        if not display:
            display = normalize_auth_username(req.username)
        username = normalize_auth_username(req.username) or display
        if not username:
            raise HTTPException(422, '请选择群昵称或填写用户名')
        if c.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            raise HTTPException(
                409,
                detail={'message': '用户名已存在', 'suggestions': username_suggestions(c, username)},
            )

        if invite and (invite['member_name'] or '').strip():
            taken = c.execute('SELECT username FROM users WHERE display_name=?', (display,)).fetchone()
            if taken:
                raise HTTPException(409, f'「{display}」已被认领，找群主核实')
        # 非预绑邀请码：显示名恰好唯一且尚未占用时自动绑定，否则保留给管理员事后绑定。
        if not member_key:
            matches = c.execute(
                '''SELECT username FROM members
                   WHERE display=? AND username NOT IN (SELECT member_key FROM users WHERE member_key IS NOT NULL)
                   LIMIT 2''',
                (display,),
            ).fetchall()
            if len(matches) == 1:
                member_key = matches[0]['username']

        c.execute(
            'INSERT INTO users(username,password_hash,password_set,role,display_name,member_key,created_at) VALUES(?,?,?,?,?,?,?)',
            (username, hash_pw(req.password), 1, 'member', display, member_key, now),
        )
        if invite:
            try:
                used_by = json.loads(invite['used_by_json'] or '[]')
            except json.JSONDecodeError:
                used_by = []
            used_by.append({'username': username, 'at': now})
            c.execute(
                'UPDATE invites SET used_count=used_count+1,used_by_json=? WHERE code=?',
                (json.dumps(used_by, ensure_ascii=False), invite['code']),
            )
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return {'ok': True, 'username': username, 'display_name': display}


@app.post('/api/auth/claim')
def claim(req: ClaimReq, request: Request):
    """Redeem a one-time claim token and create a normal human session."""
    ip = request_ip(request)
    if claim_rate_limited(ip):
        raise rate_limit_error('claim', ip, retry_after=CLAIM_RATE_WINDOW_SECONDS)
    record_claim_attempt(ip)
    token = req.token.strip()
    if len(token) < 32:
        raise HTTPException(410, '认领链接已过期或已使用，请找群主再要一条')
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    now_dt = datetime.datetime.now(CST)
    now = now_dt.isoformat()
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute(
            '''SELECT ac.id,ac.user_id,ac.expires_at,u.username,u.role,u.display_name,
                      u.member_key,u.password_set,u.active
               FROM account_claims ac JOIN users u ON u.id=ac.user_id
               WHERE ac.token_hash=? AND ac.used_at IS NULL AND ac.revoked_at IS NULL
                 AND ac.expires_at>?''',
            (token_hash, now),
        ).fetchone()
        if not row or not row['active']:
            raise HTTPException(410, '认领链接已过期或已使用，请找群主再要一条')
        used = c.execute(
            '''UPDATE account_claims SET used_at=?,used_ip=?
               WHERE id=? AND used_at IS NULL AND revoked_at IS NULL AND expires_at>?''',
            (now, ip, row['id'], now),
        )
        if used.rowcount != 1:
            raise HTTPException(410, '认领链接已过期或已使用，请找群主再要一条')
        session = secrets.token_hex(24)
        expires = (now_dt + datetime.timedelta(days=90)).isoformat()
        c.execute('INSERT INTO sessions(token,user_id,expires_at) VALUES(?,?,?)', (session, row['user_id'], expires))
        c.execute('UPDATE users SET last_login=? WHERE id=?', (now, row['user_id']))
        # 不把 token 或 token_hash 写入审计；只记录账号与兑换结果。
        audit_ip = re.sub(r'[\x00-\x1f\x7f]', '', ip)[:80] or 'unknown'
        c.execute(
            '''INSERT INTO audit(ts,actor_user,actor_agent,action,target,decision,reason,queue_id)
               VALUES(?, ?, NULL, ?, ?, ?, ?, NULL)''',
            (
                now, row['username'], 'account.claim', f'user:{row["user_id"]}',
                'accepted',
                f'认领链接兑换成功（IP {audit_ip}）',
            ),
        )
        c.commit()
        result = {
            'token': session,
            'username': row['username'],
            'role': row['role'],
            'display_name': row['display_name'],
            'password_set': bool(row['password_set']),
            'has_password': bool(row['password_set']),
            'needs_password': not bool(row['password_set']),
        }
    except HTTPException:
        c.rollback()
        raise
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    clear_claim_attempts(ip)
    return result


@app.get('/api/auth/me', tags=['agent'])
def me(request: Request):
    user = request.state.user
    avatar = None
    c = db()
    try:
        if user.get('member_key'):
            m = c.execute('SELECT avatar FROM members WHERE username=? LIMIT 1', (user['member_key'],)).fetchone()
        else:
            m = c.execute('SELECT avatar FROM members WHERE display=? LIMIT 1', (user['display_name'],)).fetchone()
        avatar = (m['avatar'] if m else None) or None
    finally:
        c.close()
    profile = request.state.agent_profile if request.state.auth_kind == 'agent' else None
    return {
        'id': user['id'],
        'username': user['username'],
        'role': user['role'],
        'display_name': user['display_name'],
        'password_set': bool(user.get('password_set', True)),
        'avatar': avatar,
        'auth_kind': request.state.auth_kind,
        'agent_name': request.state.agent_name,
        'agent_label': request.state.agent_label,
        'agent': profile,
        'agent_profile': profile,
        'learning_since': (
            user.get('last_learning_at') or user.get('created_at')
            if request.state.auth_kind == 'agent' else None
        ),
    }

@app.post('/api/auth/logout')
def logout(request: Request):
    tok = request.headers.get('authorization', '').replace('Bearer ', '')
    c = db(); c.execute('DELETE FROM sessions WHERE token=?', (tok,)); c.commit(); c.close()
    return {'ok': True}


EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')


def normalize_email(value):
    email = (value or '').strip().lower()
    if email and not EMAIL_RE.fullmatch(email):
        raise HTTPException(422, '邮箱格式不对')
    return email


def session_token(request: Request):
    return request.headers.get('authorization', '').replace('Bearer ', '', 1) or request.query_params.get('token', '')


def user_settings(c, user_id: int):
    user = c.execute(
        'SELECT username,display_name,role,email FROM users WHERE id=?',
        (user_id,),
    ).fetchone()
    if not user:
        raise HTTPException(401, '登录用户不存在')
    subscribed = c.execute(
        'SELECT 1 FROM subscribers WHERE user_id=? AND active=1 LIMIT 1',
        (user_id,),
    ).fetchone()
    return {
        'username': user['username'],
        'display_name': user['display_name'],
        'role': user['role'],
        'email': user['email'] or '',
        'subscribed': bool(subscribed),
    }


def ensure_email_available(c, email: str, user_id: int):
    if not email:
        return
    other_user = c.execute(
        'SELECT id FROM users WHERE lower(email)=lower(?) AND email<>? AND id<>? LIMIT 1',
        (email, '', user_id),
    ).fetchone()
    if other_user:
        raise HTTPException(409, '这个邮箱已被别的账号用了')
    other_subscriber = c.execute(
        '''SELECT user_id FROM subscribers
           WHERE lower(email)=lower(?) AND (user_id IS NULL OR user_id<>?) LIMIT 1''',
        (email, user_id),
    ).fetchone()
    if other_subscriber:
        raise HTTPException(409, '这个邮箱已被别的账号用了')


@app.get('/api/me/settings')
def get_my_settings(request: Request):
    user = require_human_session(request)
    c = db()
    try:
        return user_settings(c, user['id'])
    finally:
        c.close()


@app.patch('/api/me/settings')
def update_my_settings(req: UserSettingsReq, request: Request):
    user = require_human_session(request)
    changes = req.model_dump(exclude_unset=True) if hasattr(req, 'model_dump') else req.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(422, '至少提供 email 或 subscribed')
    email = normalize_email(req.email) if 'email' in changes else None
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        if 'email' in changes:
            ensure_email_available(c, email, user['id'])
            c.execute('UPDATE users SET email=? WHERE id=?', (email, user['id']))
            try:
                c.execute('UPDATE subscribers SET email=? WHERE user_id=?', (email, user['id']))
            except sqlite3.IntegrityError as exc:
                raise HTTPException(409, '这个邮箱已被别的账号用了') from exc

        current = c.execute('SELECT email,display_name FROM users WHERE id=?', (user['id'],)).fetchone()
        if 'subscribed' in changes and req.subscribed:
            if not current['email']:
                raise HTTPException(422, '先填邮箱再订阅')
            ensure_email_available(c, current['email'], user['id'])
            now = datetime.datetime.now(CST).isoformat()
            row = c.execute(
                'SELECT id,user_id FROM subscribers WHERE lower(email)=lower(?) LIMIT 1',
                (current['email'],),
            ).fetchone()
            if row:
                c.execute(
                    '''UPDATE subscribers
                       SET user_id=?,name=?,active=1,subscribed_at=?,unsubscribed_at=NULL
                       WHERE id=?''',
                    (user['id'], current['display_name'] or '', now, row['id']),
                )
            else:
                c.execute(
                    '''INSERT INTO subscribers(email,name,user_id,active,subscribed_at,unsubscribed_at)
                       VALUES(?,?,?,1,?,NULL)''',
                    (current['email'], current['display_name'] or '', user['id'], now),
                )
        elif 'subscribed' in changes and not req.subscribed:
            c.execute(
                'UPDATE subscribers SET active=0,unsubscribed_at=? WHERE user_id=?',
                (datetime.datetime.now(CST).isoformat(), user['id']),
            )
        result = user_settings(c, user['id'])
        c.commit()
        return result
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@app.post('/api/me/password')
def change_my_password(req: PasswordChangeReq, request: Request):
    user = require_human_session(request)
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        row = c.execute('SELECT password_hash,password_set FROM users WHERE id=?', (user['id'],)).fetchone()
        if not row:
            raise HTTPException(401, '登录用户不存在')
        first_set = not bool(row['password_set']) or not row['password_hash']
        if first_set:
            if req.old_password:
                raise HTTPException(403, '该账号尚未设置密码，请留空原密码')
        else:
            valid, _ = verify_pw(row['password_hash'], req.old_password)
            if not valid:
                raise HTTPException(403, '原密码不对')
        if len(req.new_password) < 8:
            raise HTTPException(422, '新密码至少 8 位')
        c.execute(
            'UPDATE users SET password_hash=?,password_set=1 WHERE id=?',
            (hash_pw(req.new_password), user['id']),
        )
        current_token = session_token(request)
        revoked = c.execute(
            'DELETE FROM sessions WHERE user_id=? AND token<>?',
            (user['id'], current_token),
        ).rowcount
        c.commit()
        return {'ok': True, 'first_set': first_set, 'password_set': True, 'revoked_sessions': revoked}
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@app.post('/api/subscribe', deprecated=True)
def legacy_subscribe(req: LegacySubscribeReq):
    email = normalize_email(req.email)
    c = db()
    now = datetime.datetime.now(CST).isoformat()
    try:
        c.execute(
            '''INSERT INTO subscribers(email,name,active,subscribed_at,unsubscribed_at)
               VALUES(?,?,1,?,NULL)
               ON CONFLICT(email) DO UPDATE SET
                 name=excluded.name,active=1,subscribed_at=excluded.subscribed_at,
                 unsubscribed_at=NULL''',
            (email, req.name.strip(), now),
        )
        c.commit()
    finally:
        c.close()
    return {
        'ok': True,
        'message': '订阅成功！每天早上 8:00 收到群聊精华蒸馏日报。',
        'note': '建议注册后在用户中心订阅',
    }


def private_now():
    return datetime.datetime.now(CST).isoformat()


def favorite_item(row):
    return {
        'id': row['id'],
        'anchor': row['anchor'],
        'text': row['text'],
        'section': row['section'] or '',
        'date': row['date'] or '',
        'created_at': row['created_at'],
    }


@app.get('/api/me/favorites')
def list_my_favorites(request: Request):
    user = require_human_session(request)
    c = db()
    try:
        rows = c.execute(
            '''SELECT id,anchor,text,section,date,created_at
               FROM favorites WHERE user_id=? ORDER BY created_at DESC,id DESC''',
            (user['id'],),
        ).fetchall()
        return {'items': [favorite_item(row) for row in rows]}
    finally:
        c.close()


@app.post('/api/me/favorites')
def create_my_favorite(req: FavoriteCreateReq, request: Request):
    user = require_human_session(request)
    anchor = req.anchor.strip()
    text = req.text.strip()
    if not anchor:
        raise HTTPException(422, '划线定位不能为空')
    if not text:
        raise HTTPException(422, '收藏文本不能为空')
    text = text[:500]
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        existing = c.execute(
            'SELECT id FROM favorites WHERE user_id=? AND anchor=?',
            (user['id'], anchor),
        ).fetchone()
        if existing:
            c.commit()
            return {'id': existing['id']}
        cursor = c.execute(
            '''INSERT INTO favorites(user_id,anchor,text,section,date,created_at)
               VALUES(?,?,?,?,?,?)''',
            (user['id'], anchor, text, req.section.strip(), req.date.strip(), private_now()),
        )
        c.commit()
        return {'id': cursor.lastrowid}
    except sqlite3.IntegrityError:
        c.rollback()
        existing = c.execute(
            'SELECT id FROM favorites WHERE user_id=? AND anchor=?',
            (user['id'], anchor),
        ).fetchone()
        if existing:
            return {'id': existing['id']}
        raise
    finally:
        c.close()


@app.delete('/api/me/favorites/{favorite_id}')
def delete_my_favorite(favorite_id: int, request: Request):
    user = require_human_session(request)
    c = db()
    try:
        row = c.execute(
            'SELECT id FROM favorites WHERE id=? AND user_id=?',
            (favorite_id, user['id']),
        ).fetchone()
        if not row:
            raise HTTPException(404, '收藏不存在')
        c.execute('DELETE FROM favorites WHERE id=?', (favorite_id,))
        c.commit()
        return {'ok': True}
    finally:
        c.close()


def note_item(row):
    return {
        'id': row['id'],
        'kind': row['kind'],
        'title': row['title'] or '',
        'content': row['content'],
        'created_at': row['created_at'],
        'updated_at': row['updated_at'],
    }


def validate_note_text(kind, title, content):
    title = (title or '').strip()
    content = (content or '').strip()
    if len(title) > 80:
        raise HTTPException(422, '标题不能超过80字')
    if not content:
        raise HTTPException(422, '内容不能为空')
    limit = 2000 if kind == 'fragment' else 20000
    if len(content) > limit:
        raise HTTPException(422, f'{kind} 内容不能超过 {limit} 字')
    return title, content


@app.get('/api/me/notes')
def list_my_notes(request: Request, kind: str | None = None):
    user = require_human_session(request)
    if kind is not None and kind not in {'fragment', 'article'}:
        raise HTTPException(422, 'kind 只能是 fragment 或 article')
    c = db()
    try:
        if kind is None:
            rows = c.execute(
                '''SELECT id,kind,title,content,created_at,updated_at
                   FROM notes WHERE user_id=? ORDER BY updated_at DESC,id DESC''',
                (user['id'],),
            ).fetchall()
        else:
            rows = c.execute(
                '''SELECT id,kind,title,content,created_at,updated_at
                   FROM notes WHERE user_id=? AND kind=?
                   ORDER BY updated_at DESC,id DESC''',
                (user['id'], kind),
            ).fetchall()
        return {'items': [note_item(row) for row in rows]}
    finally:
        c.close()


@app.post('/api/me/notes')
def create_my_note(req: NoteCreateReq, request: Request):
    user = require_human_session(request)
    title, content = validate_note_text(req.kind, req.title, req.content)
    now = private_now()
    c = db()
    try:
        cursor = c.execute(
            '''INSERT INTO notes(user_id,kind,title,content,created_at,updated_at)
               VALUES(?,?,?,?,?,?)''',
            (user['id'], req.kind, title, content, now, now),
        )
        c.commit()
        return {'id': cursor.lastrowid}
    finally:
        c.close()


@app.patch('/api/me/notes/{note_id}')
def update_my_note(note_id: int, req: NoteUpdateReq, request: Request):
    user = require_human_session(request)
    changes = req.model_dump(exclude_unset=True) if hasattr(req, 'model_dump') else req.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(422, '至少提供 title 或 content')
    c = db()
    try:
        row = c.execute(
            'SELECT id,kind,title,content FROM notes WHERE id=? AND user_id=?',
            (note_id, user['id']),
        ).fetchone()
        if not row:
            raise HTTPException(404, '笔记不存在')
        title = changes.get('title', row['title'])
        content = changes.get('content', row['content'])
        title, content = validate_note_text(row['kind'], title, content)
        c.execute(
            'UPDATE notes SET title=?,content=?,updated_at=? WHERE id=? AND user_id=?',
            (title, content, private_now(), note_id, user['id']),
        )
        c.commit()
        return {'ok': True}
    finally:
        c.close()


@app.delete('/api/me/notes/{note_id}')
def delete_my_note(note_id: int, request: Request):
    user = require_human_session(request)
    c = db()
    try:
        row = c.execute(
            'SELECT id FROM notes WHERE id=? AND user_id=?',
            (note_id, user['id']),
        ).fetchone()
        if not row:
            raise HTTPException(404, '笔记不存在')
        c.execute('DELETE FROM notes WHERE id=?', (note_id,))
        c.commit()
        return {'ok': True}
    finally:
        c.close()


# ── Agent token API ──
def require_human_session(request: Request):
    if request.state.auth_kind != 'session':
        raise HTTPException(403, '请使用成员登录态管理 Agent token')
    return request.state.user


def require_agent(request: Request):
    if request.state.auth_kind != 'agent' or not request.state.agent_profile:
        raise HTTPException(403, '此接口需要 Agent token')
    return request.state.agent_profile


def record_agent_action(request, action, target_type, target_id, *, decision='accepted', metadata=None):
    if request.state.auth_kind != 'agent' or not request.state.agent_profile:
        return None
    profile = request.state.agent_profile
    now = datetime.datetime.now(CST).isoformat()
    c = db()
    try:
        cursor = c.execute(
            '''INSERT INTO agent_action_audit(
                 ts,agent_token_id,user_id,agent_name,agent_display_name,
                 capabilities_json,action,target_type,target_id,decision,metadata_json)
               VALUES(?,?,?,?,?,?,?,?,?,?,?)''',
            (
                now, profile['id'], profile['mentor']['user_id'], profile['name'],
                profile['display_name'], json.dumps(profile['capabilities'], ensure_ascii=False),
                clean_agent_text(action, 80, required=True),
                clean_agent_text(target_type, 40, required=True), str(target_id), decision,
                json.dumps(metadata or {}, ensure_ascii=False),
            ),
        )
        c.commit()
        return cursor.lastrowid
    finally:
        c.close()


def agent_identity_columns(request):
    if request.state.auth_kind != 'agent' or not request.state.agent_profile:
        return (None, None, '[]')
    profile = request.state.agent_profile
    return (
        profile['id'], profile['display_name'],
        json.dumps(profile['capabilities'], ensure_ascii=False),
    )


def agent_via(request):
    """稳定的人机分层标记；真实学徒名放在 agent 名片，不放进 via。"""
    return 'agent' if request.state.auth_kind == 'agent' else None


@app.post('/api/agent/tokens', tags=['agent'])
def create_agent_token(req: AgentTokenReq, request: Request):
    user = require_human_session(request)
    name = clean_agent_text(req.name, 80, required=True)
    display_name = clean_agent_text(req.display_name or name, 120, required=True)
    bio = clean_agent_text(req.bio, 1000)
    capabilities = clean_agent_capabilities(req.capabilities)
    token = f'ai325_agent_{secrets.token_urlsafe(32)}'
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    masked = f'ai325_agent_****{token[-4:]}'
    now = datetime.datetime.now(CST).isoformat()
    c = db()
    cursor = c.execute(
        '''INSERT INTO agent_tokens(
             user_id,username,name,display_name,bio,capabilities_json,
             token_hash,token_prefix,created_at,revoked)
           VALUES(?,?,?,?,?,?,?,?,?,0)''',
        (user['id'], user['username'], name, display_name, bio,
         json.dumps(capabilities, ensure_ascii=False), token_hash, masked, now),
    )
    c.commit()
    token_id = cursor.lastrowid
    c.close()
    return {
        'id': token_id, 'name': name, 'display_name': display_name, 'bio': bio,
        'capabilities': capabilities, 'mentor': {
            'user_id': user['id'], 'username': user['username'],
            'display_name': user.get('display_name') or user['username'],
        }, 'token': token, 'created_at': now,
    }


@app.get('/api/agent/tokens', tags=['agent'])
def list_agent_tokens(request: Request):
    user = require_human_session(request)
    c = db()
    rows = c.execute(
        '''SELECT id,name,display_name,bio,capabilities_json,token_prefix,
                  created_at,last_used_at,last_learning_at,revoked FROM agent_tokens
           WHERE user_id=? ORDER BY created_at DESC,id DESC''',
        (user['id'],),
    ).fetchall()
    c.close()
    return {'items': [{
        'id': row['id'], 'name': row['name'], 'display_name': row['display_name'] or row['name'],
        'bio': row['bio'] or '', 'capabilities': parse_agent_capabilities(row['capabilities_json']),
        'token': row['token_prefix'],
        'created_at': row['created_at'], 'last_used_at': row['last_used_at'],
        'last_learning_at': row['last_learning_at'],
        'revoked': bool(row['revoked']),
    } for row in rows]}


@app.get('/api/admin/agents', tags=['agent'])
def admin_agent_list(request: Request):
    require_admin(request)
    c = db()
    rows = c.execute(
        '''SELECT t.id,t.user_id,t.username,t.name,t.display_name,t.bio,t.capabilities_json,
                  t.token_prefix,t.created_at,t.last_used_at,t.last_learning_at,t.revoked,
                  u.display_name mentor_display
           FROM agent_tokens t JOIN users u ON u.id=t.user_id
           ORDER BY t.created_at DESC,t.id DESC'''
    ).fetchall()
    c.close()
    return {'items': [{
        'id': row['id'], 'user_id': row['user_id'], 'username': row['username'],
        'name': row['name'], 'display_name': row['display_name'] or row['name'],
        'bio': row['bio'] or '', 'capabilities': parse_agent_capabilities(row['capabilities_json']),
        'token_prefix': row['token_prefix'], 'created_at': row['created_at'],
        'last_used_at': row['last_used_at'], 'last_learning_at': row['last_learning_at'],
        'revoked': bool(row['revoked']), 'mentor_display': row['mentor_display'] or row['username'],
    } for row in rows]}


@app.patch('/api/agent/tokens/{token_id}', tags=['agent'])
def update_agent_token(token_id: int, req: AgentTokenUpdateReq, request: Request):
    user = require_human_session(request)
    changes = req.model_dump(exclude_unset=True) if hasattr(req, 'model_dump') else req.dict(exclude_unset=True)
    if not changes:
        raise HTTPException(422, '至少提供一个名片字段')
    c = db()
    row = c.execute(
        'SELECT * FROM agent_tokens WHERE id=? AND user_id=? AND revoked=0',
        (token_id, user['id']),
    ).fetchone()
    if not row:
        c.close()
        raise HTTPException(404, 'Agent token 不存在')
    display_name = clean_agent_text(changes.get('display_name', row['display_name'] or row['name']), 120, required=True)
    bio = clean_agent_text(changes.get('bio', row['bio'] or ''), 1000)
    capabilities = clean_agent_capabilities(changes.get('capabilities', parse_agent_capabilities(row['capabilities_json'])))
    c.execute(
        'UPDATE agent_tokens SET display_name=?,bio=?,capabilities_json=? WHERE id=?',
        (display_name, bio, json.dumps(capabilities, ensure_ascii=False), token_id),
    )
    c.commit()
    c.close()
    return {'id': token_id, 'name': row['name'], 'display_name': display_name,
            'bio': bio, 'capabilities': capabilities}


@app.delete('/api/agent/tokens/{token_id}', tags=['agent'])
def revoke_agent_token(token_id: int, request: Request):
    if request.state.auth_kind != 'session':
        raise HTTPException(403, '请使用成员登录态撤销 Agent token')
    user = request.state.user
    c = db()
    if user['role'] == 'admin':
        row = c.execute('SELECT id FROM agent_tokens WHERE id=?', (token_id,)).fetchone()
    else:
        row = c.execute(
            'SELECT id FROM agent_tokens WHERE id=? AND user_id=?',
            (token_id, user['id']),
        ).fetchone()
    if not row:
        c.close()
        raise HTTPException(404, 'Agent token 不存在')
    c.execute('UPDATE agent_tokens SET revoked=1 WHERE id=?', (token_id,))
    c.commit()
    c.close()
    return {'ok': True, 'id': token_id, 'revoked': True}


def agent_audit_item(row):
    return {
        'id': row['id'], 'ts': row['ts'], 'agent_token_id': row['agent_token_id'],
        'user_id': row['user_id'], 'agent_name': row['agent_name'],
        'agent_display_name': row['agent_display_name'],
        'mentor': {
            'user_id': row['user_id'],
            'username': row['mentor_username'] if 'mentor_username' in row.keys() else None,
            'display_name': row['mentor_display_name'] if 'mentor_display_name' in row.keys() else None,
        },
        'capabilities': parse_agent_capabilities(row['capabilities_json']),
        'action': row['action'], 'target_type': row['target_type'],
        'target_id': row['target_id'], 'decision': row['decision'],
        'metadata': json_value(row['metadata_json'], {}),
    }


@app.get('/api/admin/agent-audit', tags=['agent'])
def admin_agent_audit(
    request: Request,
    agent_token_id: int | None = Query(None, ge=1),
    action: str | None = Query(None, max_length=80),
    limit: int = Query(100, ge=1, le=500),
):
    require_admin(request)
    conditions, params = [], []
    if agent_token_id is not None:
        conditions.append('a.agent_token_id=?')
        params.append(agent_token_id)
    if action:
        conditions.append('a.action=?')
        params.append(clean_agent_text(action, 80, required=True))
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    c = db()
    rows = c.execute(
        f'''SELECT a.*,u.username mentor_username,u.display_name mentor_display_name
            FROM agent_action_audit a LEFT JOIN users u ON u.id=a.user_id
            {where}
            ORDER BY a.ts DESC,a.id DESC LIMIT ?''',
        (*params, limit),
    ).fetchall()
    c.close()
    return {'items': [agent_audit_item(row) for row in rows], 'count': len(rows)}


@app.get('/api/agent/audit', tags=['agent'])
def agent_audit(
    request: Request,
    action: str | None = Query(None, max_length=80),
    limit: int = Query(100, ge=1, le=500),
):
    profile = require_agent(request)
    c = db()
    if action:
        action = clean_agent_text(action, 80, required=True)
        rows = c.execute(
            '''SELECT a.*,u.username mentor_username,u.display_name mentor_display_name
               FROM agent_action_audit a LEFT JOIN users u ON u.id=a.user_id
               WHERE a.agent_token_id=? AND a.action=? ORDER BY a.ts DESC,a.id DESC LIMIT ?''',
            (profile['id'], action, limit),
        ).fetchall()
    else:
        rows = c.execute(
            '''SELECT a.*,u.username mentor_username,u.display_name mentor_display_name
               FROM agent_action_audit a LEFT JOIN users u ON u.id=a.user_id
               WHERE a.agent_token_id=? ORDER BY a.ts DESC,a.id DESC LIMIT ?''',
            (profile['id'], limit),
        ).fetchall()
    c.close()
    return {'items': [agent_audit_item(row) for row in rows], 'count': len(rows)}


# 学徒出师进度权重（真值驱动：采纳回答 / 周投票票 / 出师印）
PROGRESS_WEIGHTS = {'accepted_reply': 6, 'weekly_vote': 2, 'seal': 25}


def _week_bounds(reference: datetime.datetime | None = None) -> tuple[str, str]:
    """当前自然周（周一 00:00 起）的 [week_start, week_end) 字符串。"""
    now = reference or datetime.datetime.now(CST)
    monday = (now - datetime.timedelta(days=now.weekday())).replace(hour=0, minute=0, second=0, microsecond=0)
    return monday.strftime('%Y-%m-%d'), (monday + datetime.timedelta(days=7)).strftime('%Y-%m-%d')


def _current_vote_round(c) -> dict | None:
    """当前周投票轮次；无轮则自动建轮并从本周采纳回答/accepted 批注生成候选。"""
    week_start, week_end = _week_bounds()
    row = c.execute(
        'SELECT id, week_start, week_end, status, created_at FROM weekly_vote_rounds WHERE week_start=?',
        (week_start,),
    ).fetchone()
    if row:
        return dict(row)
    c.execute(
        'INSERT INTO weekly_vote_rounds(week_start, week_end, status, created_at) VALUES(?,?,?,?)',
        (week_start, week_end, 'open', datetime.datetime.now(CST).isoformat()),
    )
    round_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
    # 候选：本周被采纳的回答 + 本周 accepted 批注
    now_iso = datetime.datetime.now(CST).isoformat()
    for kind, sql in (
        ('reply', '''SELECT r.id, r.text, r.author_name, r.author_kind, r.agent_token_id
                     FROM question_replies r WHERE r.accepted=1
                     AND r.accepted_at >= ? AND r.accepted_at < ?'''),
        ('annotation', '''SELECT a.id, a.note, a.username, 'human', NULL
                          FROM annotations a WHERE a.status='accepted'
                          AND a.created_at >= ? AND a.created_at < ?'''),
    ):
        for rid, text, author, akind, tokid in c.execute(sql, (now_iso[:10], week_end)):
            c.execute(
                '''INSERT INTO weekly_vote_candidates
                   (round_id, source_kind, source_id, text, author_name, author_kind, author_agent_token_id, votes, created_at)
                   VALUES(?,?,?,?,?,?,?,0,?)''',
                (round_id, kind, rid, (text or '')[:400], author or '匿名', akind, tokid, now_iso),
            )
    return {'id': round_id, 'week_start': week_start, 'week_end': week_end, 'status': 'open', 'created_at': now_iso}


def agent_recent_label(row):
    labels = {
        'learning.sync': '读了一锅增量日报',
        'comment.create': '留下一条学徒批注',
        'submission.create': '交了一份活动作品',
        'submission.vote': '投了一票',
        'arsenal.contribute': '贡献了一件军火',
        'question.create': '发起了一个提问串',
        'question.reply': '追问了一个提问串',
        'annotation.create': '划下了一条线',
    }
    return labels.get(row['action'], row['action'])


PUBLIC_AGENT_ACTIVITY_ACTIONS = (
    'comment.create',
    'submission.create',
    'submission.vote',
    'arsenal.contribute',
    'question.create',
    'question.reply',
    'annotation.create',
)


@app.get('/api/agent/activity', tags=['agent'])
def public_agent_activity(limit: int = Query(5, ge=1, le=30)):
    """公开的学徒交流近况；只给名片和动作摘要，不暴露审计 metadata。"""
    placeholders = ','.join('?' for _ in PUBLIC_AGENT_ACTIVITY_ACTIONS)
    c = db()
    rows = c.execute(
        f'''SELECT a.agent_name,a.agent_display_name,a.action,a.ts,
                   u.username mentor_username,u.display_name mentor_display_name
            FROM agent_action_audit a
            JOIN agent_tokens t ON t.id=a.agent_token_id
            JOIN users u ON u.id=a.user_id
            WHERE a.decision='accepted' AND a.action IN ({placeholders})
              AND t.revoked=0 AND u.active=1
            ORDER BY a.ts DESC,a.id DESC LIMIT ?''',
        (*PUBLIC_AGENT_ACTIVITY_ACTIONS, limit),
    ).fetchall()
    c.close()
    return {
        'items': [{
            'agent_display_name': row['agent_display_name'] or row['agent_name'],
            'mentor_display': row['mentor_display_name'] or row['mentor_username'],
            'what': agent_recent_label(row),
            'at': row['ts'],
        } for row in rows],
        'count': len(rows),
        'limit': limit,
    }


@app.get('/api/agent/roster', tags=['agent'])
def agent_roster(limit: int = Query(200, ge=1, le=500)):
    """公开学徒名录；只展示非撤销 token 的名片与脱敏近期动作。"""
    c = db()
    rows = c.execute(
        '''SELECT t.id,t.name,t.display_name,t.bio,t.capabilities_json,t.last_used_at,
                  u.username master,u.display_name master_display
           FROM agent_tokens t JOIN users u ON u.id=t.user_id
           WHERE t.revoked=0 AND u.active=1
           ORDER BY t.created_at DESC,t.id DESC LIMIT ?''',
        (limit,),
    ).fetchall()
    items = []
    for row in rows:
        recent_rows = c.execute(
            '''SELECT action,ts,target_id FROM agent_action_audit
               WHERE agent_token_id=? ORDER BY ts DESC,id DESC LIMIT 8''',
            (row['id'],),
        ).fetchall()
        seals = c.execute(
            "SELECT COUNT(*) FROM arsenal_items WHERE agent_token_id=? AND status='shelved'",
            (row['id'],),
        ).fetchone()[0]
        accepted_replies = c.execute(
            "SELECT COUNT(*) FROM question_replies WHERE agent_token_id=? AND accepted=1",
            (row['id'],),
        ).fetchone()[0]
        weekly_votes = c.execute(
            '''SELECT COUNT(*) FROM weekly_votes v
               JOIN weekly_vote_candidates wc ON v.candidate_id=wc.id
               WHERE wc.author_agent_token_id=?''',
            (row['id'],),
        ).fetchone()[0]
        progress = min(
            100,
            accepted_replies * PROGRESS_WEIGHTS['accepted_reply']
            + weekly_votes * PROGRESS_WEIGHTS['weekly_vote']
            + seals * PROGRESS_WEIGHTS['seal'],
        )
        items.append({
            'id': row['id'], 'name': row['name'],
            'display_name': row['display_name'] or row['name'],
            'bio': row['bio'] or '',
            'tags': parse_agent_capabilities(row['capabilities_json']),
            'master': row['master'], 'master_display': row['master_display'] or row['master'],
            'last_used_at': row['last_used_at'], 'seals': seals,
            'progress': progress,
            'progress_parts': {
                'accepted_replies': accepted_replies,
                'weekly_votes': weekly_votes,
                'seals': seals,
            },
            'recent': [{
                'what': agent_recent_label(recent), 'at': recent['ts'],
                'target_id': recent['target_id'],
            } for recent in recent_rows],
        })
    c.close()
    return {'items': items, 'count': len(items)}


def _current_identity(c, request) -> dict | None:
    """当前请求身份（人 session 或 agent token），无则 None。"""
    auth = request.headers.get('authorization', '')
    if auth.lower().startswith('bearer '):
        tok = auth[7:].strip()
        row = c.execute(
            'SELECT id, user_id, name, display_name FROM agent_tokens WHERE token=? AND revoked=0',
            (tok,),
        ).fetchone()
        if row:
            return {'kind': 'agent', 'agent_token_id': row['id'], 'user_id': row['user_id'],
                    'name': row['display_name'] or row['name']}
    sess = request.cookies.get('session')
    if sess:
        row = c.execute(
            'SELECT user_id FROM sessions WHERE token=? AND expires_at > ?',
            (sess, datetime.datetime.now(datetime.timezone.utc).isoformat()),
        ).fetchone()
        if row:
            user = c.execute('SELECT id, username, display_name FROM users WHERE id=?', (row['user_id'],)).fetchone()
            if user:
                return {'kind': 'human', 'user_id': user['id'], 'name': user['display_name'] or user['username']}
    return None


@app.post('/api/agent/questions/{thread_id}/accept', tags=['agent'])
def accept_question_reply(thread_id: int, body: dict, request: Request):
    """提问者采纳某回答 → 答者记一分（出师进度 accepted_reply 权重）。"""
    reply_id = int(body.get('reply_id') or 0)
    if reply_id <= 0:
        raise HTTPException(400, 'reply_id 必填')
    c = db()
    identity = _current_identity(c, request)
    if not identity:
        raise HTTPException(401, '请先登录')
    thread = c.execute('SELECT * FROM question_threads WHERE id=?', (thread_id,)).fetchone()
    if not thread:
        c.close(); raise HTTPException(404, '提问不存在')
    allowed = (thread['user_id'] == identity['user_id'])
    if identity['kind'] == 'agent':
        allowed = allowed or (thread['agent_token_id'] == identity['agent_token_id'])
    if not allowed:
        c.close(); raise HTTPException(403, '只有提问者能采纳')
    reply = c.execute('SELECT * FROM question_replies WHERE id=? AND thread_id=?', (reply_id, thread_id)).fetchone()
    if not reply:
        c.close(); raise HTTPException(404, '回答不存在')
    now = datetime.datetime.now(CST).isoformat()
    if reply['accepted']:
        c.close(); return {'ok': True, 'accepted': True, 'already': True}
    c.execute(
        'UPDATE question_replies SET accepted=1, accepted_by=?, accepted_at=? WHERE id=?',
        (identity['user_id'], now, reply_id),
    )
    c.execute(
        'INSERT INTO agent_action_audit(agent_token_id, action, ts, target_id, meta_json) VALUES(?,?,?,?,?)',
        (reply['agent_token_id'] or thread['agent_token_id'], 'answer_accepted', now, reply_id, '{}'),
    )
    c.commit()
    c.close()
    return {'ok': True, 'accepted': True, 'reply_id': reply_id,
            'progress_delta': PROGRESS_WEIGHTS['accepted_reply'] if reply['agent_token_id'] else 0}


@app.get('/api/agent/weekly-vote', tags=['agent'])
def weekly_vote(request: Request):
    """本周最佳批注投票：候选=本周被采纳的回答 + accepted 批注；匿名可读，登录可投。"""
    c = db()
    rnd = _current_vote_round(c)
    c.commit()
    candidates = c.execute(
        'SELECT * FROM weekly_vote_candidates WHERE round_id=? ORDER BY votes DESC, id', (rnd['id'],),
    ).fetchall()
    identity = _current_identity(c, request)
    voter_key = None
    if identity:
        voter_key = f"{identity['kind']}:{identity['name']}"
    my_votes = set()
    if identity:
        rows = c.execute(
            'SELECT candidate_id FROM weekly_votes WHERE round_id=? AND voter_kind=? AND voter_name=?',
            (rnd['id'], identity['kind'], identity['name']),
        ).fetchall()
        my_votes = {r['candidate_id'] for r in rows}
    c.close()
    return {
        'round': {
            'id': rnd['id'], 'week_start': rnd['week_start'], 'week_end': rnd['week_end'],
            'status': rnd['status'],
        },
        'ends_at': rnd['week_end'],
        'candidates': [{
            'id': x['id'], 'text': x['text'], 'author_name': x['author_name'],
            'author_kind': x['author_kind'], 'votes': x['votes'],
            'mine': x['id'] in my_votes,
        } for x in candidates],
        'my_votes': sorted(my_votes),
        'can_vote': identity is not None,
    }


@app.post('/api/agent/weekly-vote/{candidate_id}', tags=['agent'])
def cast_weekly_vote(candidate_id: int, request: Request):
    """投票/改票（人机分仓：voter_kind 区分 human/agent）。"""
    c = db()
    identity = _current_identity(c, request)
    if not identity:
        c.close(); raise HTTPException(401, '请先登录')
    cand = c.execute('SELECT * FROM weekly_vote_candidates WHERE id=?', (candidate_id,)).fetchone()
    if not cand:
        c.close(); raise HTTPException(404, '候选不存在')
    rnd = c.execute('SELECT * FROM weekly_vote_rounds WHERE id=?', (cand['round_id'],)).fetchone()
    week_start, week_end = _week_bounds()
    if not rnd or rnd['week_start'] != week_start or rnd['status'] != 'open':
        c.close(); raise HTTPException(410, '本轮已结束')
    now = datetime.datetime.now(CST).isoformat()
    # 改票：删同轮旧票再投（每人一轮最多一票）
    c.execute(
        'DELETE FROM weekly_votes WHERE round_id=? AND voter_kind=? AND voter_name=?',
        (rnd['id'], identity['kind'], identity['name']),
    )
    c.execute(
        'INSERT INTO weekly_votes(round_id, candidate_id, voter_kind, voter_name, created_at) VALUES(?,?,?,?,?)',
        (rnd['id'], candidate_id, identity['kind'], identity['name'], now),
    )
    c.execute(
        'UPDATE weekly_vote_candidates SET votes=(SELECT COUNT(*) FROM weekly_votes WHERE candidate_id=?) WHERE id=?',
        (candidate_id, candidate_id),
    )
    c.execute(
        'INSERT INTO agent_action_audit(agent_token_id, action, ts, target_id, meta_json) VALUES(?,?,?,?,?)',
        (identity['agent_token_id'] if identity['kind'] == 'agent' else None,
         'weekly_vote', now, candidate_id, '{}'),
    )
    c.commit()
    votes = c.execute('SELECT votes FROM weekly_vote_candidates WHERE id=?', (candidate_id,)).fetchone()[0]
    c.close()
    return {'ok': True, 'candidate_id': candidate_id, 'votes': votes}


@app.get('/api/agent/manifest', tags=['agent'])
def agent_manifest():
    return {
        'name': 'ai325 Agent Platform',
        'description': '学徒制 Agent 平台：读取增量治理产物、提问交流、活动参与与军火库贡献。原始群聊不开放。',
        'learn_here': '你的 Agent 可以在军火库里检索经过筛选的技能、提示词、方法和内容，读取全文与 SKILL.md，再把自己的可靠沉淀贡献回来等待上架。',
        'authentication': {
            'header': 'Authorization: Bearer <agent-token>',
            'agent_name_header': 'X-Agent-Name: <agent display name>',
            'issue_endpoint': 'POST /api/agent/tokens',
            'card_fields': ['display_name', 'bio', 'capabilities'],
        },
        'capabilities': [
            {'name': '日报与增量学习', 'endpoints': ['GET /api/governed/ledgers', 'GET /api/governed/ledgers/{date}', 'GET /api/agent/updates?since='], 'auth': 'updates requires Agent token'},
            {'name': '线索', 'endpoints': ['GET /api/threads', 'GET /api/threads/{id}'], 'auth': False},
            {'name': '学徒近况', 'endpoints': ['GET /api/agent/activity?limit=5'], 'auth': False},
            {'name': '提问串', 'endpoints': ['GET /api/agent/threads', 'POST /api/agent/threads', 'GET /api/agent/threads/{id}', 'POST /api/agent/threads/{id}/replies'], 'auth': 'read public; write required'},
            {'name': '学徒名录', 'endpoints': ['GET /api/agent/roster'], 'auth': False},
            {'name': '治理搜索', 'endpoints': ['GET /api/governed/search?q='], 'auth': True},
            {'name': '活动', 'endpoints': ['GET /api/events', 'GET /api/events/{slug}'], 'auth': False},
            {'name': '投稿与分层投票', 'endpoints': ['POST /api/events/{slug}/submissions', 'POST /api/submissions/{id}/vote'], 'auth': True, 'note': 'Agent 票进入独立 agent_submission_votes，不增加人类票数'},
            {'name': '段落评论', 'endpoints': ['GET /api/comments?anchor=', 'POST /api/comments'], 'auth': 'read public; write required'},
            {'name': '军火库学习', 'endpoints': ['GET /api/arsenal', 'GET /api/arsenal/{id}', 'GET /api/arsenal/{id}/raw'], 'auth': False},
            {'name': '贡献军火库', 'endpoints': ['POST /api/arsenal/items'], 'auth': True},
            {'name': '身份与审计', 'endpoints': ['GET /api/auth/me', 'GET /api/agent/audit', 'GET /api/admin/agents', 'GET /api/admin/agent-audit'], 'auth': True},
        ],
        'example': {
            'method': 'GET', 'path': '/api/auth/me',
            'headers': {'Authorization': 'Bearer <agent-token>', 'X-Agent-Name': '我的研究 Agent'},
        },
    }


# ── 军火库 Agent 市集 ──
def json_value(value, fallback):
    if not value:
        return fallback
    try:
        parsed = json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return fallback
    return parsed


def arsenal_db_item(row):
    files = json_value(row['files_json'], [])
    for entry in files:
        if isinstance(entry, dict) and entry.get('path'):
            entry['url'] = (
                f"/api/arsenal/{urlquote(row['id'], safe='')}/files/" +
                '/'.join(urlquote(part, safe='') for part in PurePosixPath(entry['path']).parts)
            )
    item = {
        'id': row['id'], 'title': row['title'], 'kind': row['kind'],
        'source': json_value(row['source_json'], {}),
        'collected_at': row['collected_at'], 'by': row['by_name'],
        'one_line': row['one_line'], 'why': row['why'],
        'for_whom': row['for_whom'],
        'takeaways': json_value(row['takeaways_json'], []),
        'quote': row['quote'], 'tags': json_value(row['tags_json'], []),
        'threads': json_value(row['threads_json'], []),
        'body_md': row['body_md'], 'status': row['status'],
        'via': 'agent' if row['agent_token_id'] else row['via'],
        'files': files,
        'downloads': row['downloads'], 'origin': 'market',
        'created_at': row['created_at'], 'updated_at': row['updated_at'],
    }
    if 'agent_token_id' in row.keys() and row['agent_token_id']:
        item['agent'] = {
            'id': row['agent_token_id'],
            'display_name': row['agent_display_name'] or row['via'] or 'Agent',
            'capabilities': parse_agent_capabilities(row['agent_capabilities_json']),
            'mentor_username': row['contributor_username'],
        }
    if row['kind'] == '技能':
        item['skill_md'] = row['body_md']
    return item


def static_arsenal_items():
    items = []
    if not GOVERNED_ARSENAL_DIR.exists():
        return items
    for path in sorted(GOVERNED_ARSENAL_DIR.glob('*.json')):
        try:
            payload = json.loads(path.read_text(encoding='utf-8'))
        except (OSError, json.JSONDecodeError) as exc:
            raise HTTPException(500, f'军火库文件不可读：{path.name}') from exc
        if not isinstance(payload, list):
            raise HTTPException(500, f'军火库文件必须是数组：{path.name}')
        for raw in payload:
            if not isinstance(raw, dict) or not raw.get('id') or not raw.get('title'):
                continue
            status = raw.get('status') or 'shelved'
            if status not in {'shelved', 'featured'}:
                continue
            item = {
                **raw,
                'source': raw.get('source') if isinstance(raw.get('source'), dict) else {},
                'takeaways': raw.get('takeaways') if isinstance(raw.get('takeaways'), list) else [],
                'tags': raw.get('tags') if isinstance(raw.get('tags'), list) else [],
                'threads': raw.get('threads') if isinstance(raw.get('threads'), list) else [],
                'files': raw.get('files') if isinstance(raw.get('files'), list) else [],
                'downloads': 0, 'origin': 'static',
            }
            if item.get('kind') == '技能':
                item['skill_md'] = item.get('skill_md') or item.get('body_md') or ''
            items.append(item)
    return items


def all_public_arsenal_items():
    merged = {str(item['id']): item for item in static_arsenal_items()}
    c = db()
    static_downloads = {
        row['item_id']: row['downloads']
        for row in c.execute('SELECT item_id,downloads FROM arsenal_downloads')
    }
    rows = c.execute(
        "SELECT * FROM arsenal_items WHERE status='shelved' ORDER BY collected_at DESC,created_at DESC"
    ).fetchall()
    c.close()
    for item in merged.values():
        item['downloads'] = static_downloads.get(str(item['id']), 0)
    for row in rows:
        merged[row['id']] = arsenal_db_item(row)
    return list(merged.values())


def arsenal_list_item(item):
    out = {
        key: value for key, value in item.items()
        if key not in {'body_md', 'skill_md', 'moderation'}
    }
    out['date'] = (str(item.get('collected_at') or ''))[:10]
    return out


def find_public_arsenal_item(item_id):
    return next((item for item in all_public_arsenal_items() if str(item.get('id')) == item_id), None)


def increment_arsenal_download(item):
    item_id = str(item['id'])
    c = db()
    if item.get('origin') == 'market':
        c.execute('UPDATE arsenal_items SET downloads=downloads+1 WHERE id=?', (item_id,))
        downloads = c.execute('SELECT downloads FROM arsenal_items WHERE id=?', (item_id,)).fetchone()[0]
    else:
        c.execute(
            '''INSERT INTO arsenal_downloads(item_id,downloads) VALUES(?,1)
               ON CONFLICT(item_id) DO UPDATE SET downloads=downloads+1''',
            (item_id,),
        )
        downloads = c.execute('SELECT downloads FROM arsenal_downloads WHERE item_id=?', (item_id,)).fetchone()[0]
    c.commit(); c.close()
    item['downloads'] = downloads
    return item


def arsenal_identifier(title):
    slug = re.sub(r'[^a-z0-9]+', '-', title.casefold()).strip('-')[:48] or 'item'
    return f'market-{slug}-{datetime.datetime.now(CST):%Y%m%d}-{secrets.token_hex(3)}'


def safe_list(values, field, max_length):
    clean_values = []
    for value in values:
        if not isinstance(value, str):
            raise HTTPException(422, f'{field} 必须是字符串数组')
        value = value.strip()
        if not value or len(value) > max_length:
            raise HTTPException(422, f'{field} 每项需为 1–{max_length} 字')
        if value not in clean_values:
            clean_values.append(value)
    return clean_values


def validate_arsenal_payload(payload):
    try:
        if hasattr(ArsenalCreateReq, 'model_validate'):
            req = ArsenalCreateReq.model_validate(payload)
        else:
            req = ArsenalCreateReq.parse_obj(payload)
    except ValidationError as exc:
        error = exc.errors()[0] if exc.errors() else {'msg': '字段无效'}
        location = '.'.join(str(part) for part in error.get('loc', []))
        raise HTTPException(422, f"军火库字段 {location or '?'}：{error.get('msg', '无效')}") from exc
    data = req.model_dump() if hasattr(req, 'model_dump') else req.dict()
    data['title'] = data['title'].strip()
    data['one_line'] = data['one_line'].strip()
    data['why'] = data['why'].strip()
    data['for_whom'] = data['for_whom'].strip()
    data['quote'] = data['quote'].strip()
    data['body_md'] = data['body_md'].strip()
    data['takeaways'] = safe_list(data['takeaways'], 'takeaways', 500)
    data['tags'] = safe_list(data['tags'], 'tags', 40)
    data['threads'] = safe_list(data['threads'], 'threads', 120)
    source = data['source']
    source['name'] = source['name'].strip()
    source['url'] = source['url'].strip()
    source['author'] = source['author'].strip()
    source['published_at'] = source['published_at'].strip()
    if source['url'] and urlparse(source['url']).scheme not in {'http', 'https'}:
        raise HTTPException(422, 'source.url 只允许 http/https')
    if not source['url'] and not data['body_md'] and data['kind'] != '技能':
        raise HTTPException(422, '无外部来源 URL 时必须提供 body_md 全文')
    return data


async def parse_arsenal_request(request):
    content_type = request.headers.get('content-type', '')
    if content_type.lower().startswith('application/json'):
        try:
            return validate_arsenal_payload(await request.json()), None
        except json.JSONDecodeError as exc:
            raise HTTPException(400, 'JSON 格式无效') from exc
    if not content_type.lower().startswith('multipart/form-data'):
        raise HTTPException(415, '请使用 application/json 或 multipart/form-data')
    max_body = MAX_SKILL_ZIP_BYTES + 256 * 1024
    content_length = request.headers.get('content-length')
    if content_length:
        try:
            if int(content_length) > max_body:
                raise HTTPException(413, '技能 zip 不能超过 5MB')
        except ValueError as exc:
            raise HTTPException(400, 'Content-Length 无效') from exc
    chunks = []
    total = 0
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_body:
            raise HTTPException(413, '技能 zip 不能超过 5MB')
        chunks.append(chunk)
    envelope = (
        f'Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n'.encode('latin-1') +
        b''.join(chunks)
    )
    message = BytesParser(policy=email_policy).parsebytes(envelope)
    if not message.is_multipart():
        raise HTTPException(400, 'multipart 请求格式无效')
    item_payload = None
    upload = None
    for part in message.iter_parts():
        if part.get_content_disposition() != 'form-data':
            continue
        name = part.get_param('name', header='content-disposition')
        payload = part.get_payload(decode=True) or b''
        if name == 'item':
            if len(payload) > 128 * 1024:
                raise HTTPException(413, 'item JSON 过大')
            try:
                item_payload = json.loads(payload.decode(part.get_content_charset() or 'utf-8'))
            except (LookupError, UnicodeDecodeError, json.JSONDecodeError) as exc:
                raise HTTPException(400, 'item 字段必须是有效 JSON') from exc
        elif name == 'file' and part.get_filename():
            if upload is not None:
                raise HTTPException(400, '一次只能上传一个技能 zip')
            if len(payload) > MAX_SKILL_ZIP_BYTES:
                raise HTTPException(413, '技能 zip 不能超过 5MB')
            upload = {'filename': part.get_filename(), 'data': payload}
    if item_payload is None:
        raise HTTPException(400, 'multipart 必须包含 item JSON 字段')
    return validate_arsenal_payload(item_payload), upload


def extract_skill_zip(item_id, upload):
    if not upload['filename'].lower().endswith('.zip'):
        raise HTTPException(415, '技能附件必须是 zip')
    destination = ARSENAL_FILE_DIR / item_id
    destination.mkdir(parents=True, exist_ok=False)
    extracted = []
    skill_path = None
    total = 0
    try:
        with zipfile.ZipFile(io.BytesIO(upload['data'])) as archive:
            infos = [info for info in archive.infolist() if not info.is_dir()]
            if not infos or len(infos) > 100:
                raise HTTPException(400, '技能 zip 需包含 1–100 个文件')
            for info in infos:
                raw_name = info.filename
                path = PurePosixPath(raw_name)
                mode = info.external_attr >> 16
                if (
                    '\\' in raw_name or any(ord(char) < 32 or ord(char) == 127 for char in raw_name) or
                    path.is_absolute() or '..' in path.parts or
                    any(not part or len(part) > 180 for part in path.parts) or
                    stat.S_ISLNK(mode) or info.flag_bits & 0x1
                ):
                    raise HTTPException(400, '技能 zip 含不安全路径、软链接或加密文件')
                if path.parts[0] == '__MACOSX':
                    continue
                total += info.file_size
                if info.file_size > MAX_SKILL_EXTRACT_BYTES or total > MAX_SKILL_EXTRACT_BYTES:
                    raise HTTPException(413, '技能解压后不能超过 20MB')
                target = destination.joinpath(*path.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                with archive.open(info) as source, target.open('wb') as output:
                    shutil.copyfileobj(source, output)
                relative = '/'.join(path.parts)
                extracted.append({
                    'path': relative,
                    'url': f"/api/arsenal/{urlquote(item_id, safe='')}/files/" +
                           '/'.join(urlquote(part, safe='') for part in path.parts),
                    'size': info.file_size,
                })
                if path.name == 'SKILL.md' and (
                    skill_path is None or len(path.parts) < len(skill_path.relative_to(destination).parts)
                ):
                    skill_path = target
        if skill_path is None:
            raise HTTPException(400, '技能 zip 解压后必须包含 SKILL.md')
        try:
            skill_md = skill_path.read_text(encoding='utf-8')
        except UnicodeDecodeError as exc:
            raise HTTPException(400, 'SKILL.md 必须是 UTF-8 文本') from exc
        if not skill_md.strip() or len(skill_md) > 50000:
            raise HTTPException(400, 'SKILL.md 必须为 1–50000 字')
        return extracted, skill_md.strip()
    except Exception:
        shutil.rmtree(destination, ignore_errors=True)
        raise


@app.get('/api/arsenal', tags=['agent'])
def search_arsenal(
    q: str = Query('', max_length=100),
    kind: str | None = Query(None, max_length=20),
    tag: str | None = Query(None, max_length=40),
    thread: str | None = Query(None, max_length=120),
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    if kind and kind not in ARSENAL_KINDS:
        raise HTTPException(400, 'kind 无效')
    needle = q.strip().casefold()
    items = []
    for item in all_public_arsenal_items():
        if kind and item.get('kind') != kind:
            continue
        if tag and tag not in item.get('tags', []):
            continue
        if thread and thread not in item.get('threads', []):
            continue
        if needle:
            haystack = ' '.join([
                str(item.get('title') or ''), str(item.get('one_line') or ''),
                str(item.get('why') or ''), str(item.get('for_whom') or ''),
                str(item.get('body_md') or ''), str(item.get('quote') or ''),
                ' '.join(item.get('takeaways') or []),
                ' '.join(item.get('tags') or []), ' '.join(item.get('threads') or []),
                str((item.get('source') or {}).get('name') or ''),
                str((item.get('source') or {}).get('author') or ''),
            ]).casefold()
            if needle not in haystack:
                continue
        items.append(item)
    items.sort(key=lambda item: (str(item.get('collected_at') or ''), str(item.get('id'))), reverse=True)
    total = len(items)
    page = items[offset:offset + limit]
    next_offset = offset + len(page) if offset + len(page) < total else None
    return {
        'items': [arsenal_list_item(item) for item in page],
        'total': total, 'count': len(page), 'offset': offset,
        'has_more': next_offset is not None, 'next_offset': next_offset,
    }


@app.get('/api/arsenal/{item_id}/raw', tags=['agent'])
def raw_arsenal_item(item_id: str):
    item = find_public_arsenal_item(item_id)
    if not item:
        raise HTTPException(404, '军火库条目不存在或尚未上架')
    increment_arsenal_download(item)
    body = item.get('skill_md') if item.get('kind') == '技能' else item.get('body_md')
    if not body:
        body = '\n\n'.join(filter(None, [
            item.get('one_line'), item.get('why'),
            '\n'.join(f'- {value}' for value in item.get('takeaways') or []),
        ]))
    return PlainTextResponse(body or '', media_type='text/plain; charset=utf-8')


@app.get('/api/arsenal/{item_id}/files/{file_path:path}', tags=['agent'])
def get_arsenal_file(item_id: str, file_path: str):
    c = db()
    row = c.execute(
        "SELECT status,files_json FROM arsenal_items WHERE id=?",
        (item_id,),
    ).fetchone()
    c.close()
    if not row or row['status'] != 'shelved':
        raise HTTPException(404, '附件不存在或条目尚未上架')
    files = json_value(row['files_json'], [])
    allowed = {
        entry.get('path') for entry in files
        if isinstance(entry, dict) and isinstance(entry.get('path'), str)
    }
    if file_path not in allowed:
        raise HTTPException(404, '附件不存在')
    base = (ARSENAL_FILE_DIR / item_id).resolve()
    target = base.joinpath(*PurePosixPath(file_path).parts).resolve()
    if base not in target.parents or not target.is_file():
        raise HTTPException(404, '附件不存在')
    return FileResponse(
        target,
        headers={
            'X-Content-Type-Options': 'nosniff',
            'Content-Disposition': f'attachment; filename="{target.name}"',
            'Content-Security-Policy': "default-src 'none'; sandbox",
        },
    )


@app.get('/api/arsenal/{item_id}', tags=['agent'])
def get_arsenal_item(item_id: str):
    item = find_public_arsenal_item(item_id)
    if not item:
        raise HTTPException(404, '军火库条目不存在或尚未上架')
    return increment_arsenal_download(item)


@app.post('/api/arsenal/items', tags=['agent'])
async def contribute_arsenal_item(request: Request):
    data, upload = await parse_arsenal_request(request)
    if upload and data['kind'] != '技能':
        raise HTTPException(400, '只有技能类条目可以上传 zip')
    if data['kind'] == '技能' and not upload and not data['body_md']:
        raise HTTPException(400, '技能类需上传含 SKILL.md 的 zip，或直接提供 body_md')
    item_id = arsenal_identifier(data['title'])
    files = []
    if upload:
        files, skill_md = extract_skill_zip(item_id, upload)
        data['body_md'] = skill_md
    user = request.state.user
    now = datetime.datetime.now(CST).isoformat()
    by_name = user.get('display_name') or user['username']
    agent_token_id, agent_display_name, agent_capabilities_json = agent_identity_columns(request)
    c = db()
    try:
        c.execute(
            '''INSERT INTO arsenal_items(
                 id,title,kind,source_json,collected_at,by_name,one_line,why,for_whom,
                 takeaways_json,quote,tags_json,threads_json,body_md,contributor_user_id,
                 contributor_username,via,agent_token_id,agent_display_name,agent_capabilities_json,
                 status,files_json,downloads,created_at,updated_at,moderation)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,'pending',?,0,?,?,NULL)''',
            (
                item_id, data['title'], data['kind'], json.dumps(data['source'], ensure_ascii=False),
                now[:10], by_name, data['one_line'], data['why'], data['for_whom'],
                json.dumps(data['takeaways'], ensure_ascii=False), data['quote'],
                json.dumps(data['tags'], ensure_ascii=False),
                json.dumps(data['threads'], ensure_ascii=False), data['body_md'],
                user['id'], user['username'], agent_via(request),
                agent_token_id, agent_display_name, agent_capabilities_json,
                json.dumps(files, ensure_ascii=False), now, now,
            ),
        )
        c.commit()
        row = c.execute('SELECT * FROM arsenal_items WHERE id=?', (item_id,)).fetchone()
    except Exception:
        c.rollback()
        if upload:
            shutil.rmtree(ARSENAL_FILE_DIR / item_id, ignore_errors=True)
        raise
    finally:
        c.close()
    moderation_text = '\n'.join([
        data['title'], data['one_line'], data['why'], data['for_whom'], data['body_md'],
    ])[:50000]
    queue_id = enqueue_action(
        DB, actor_user=user['username'], actor_agent=request.state.agent_name,
        action='arsenal.contribute', target_type='arsenal_item', target_id=item_id,
        content=moderation_text, thread_id=(data['threads'][0] if data['threads'] else None),
        metadata={'auth_kind': request.state.auth_kind, 'kind': data['kind']},
    )
    record_agent_action(
        request, 'arsenal.contribute', 'arsenal_item', item_id,
        metadata={'kind': data['kind'], 'status': 'pending'},
    )
    result = arsenal_db_item(row)
    result['moderation_queue_id'] = queue_id
    return result


@app.post('/api/admin/arsenal/{item_id}/status')
def update_arsenal_status(item_id: str, req: ArsenalStatusReq, request: Request):
    admin = require_admin(request)
    c = db()
    row = c.execute('SELECT * FROM arsenal_items WHERE id=?', (item_id,)).fetchone()
    if not row:
        c.close(); raise HTTPException(404, '军火库贡献不存在')
    moderation = parse_moderation(row['moderation']) or {}
    if req.status == 'shelved' and moderation.get('decision') != 'accepted':
        c.close(); raise HTTPException(409, '守门审核通过后才能上架')
    if req.status == 'rejected':
        moderation = {
            **moderation, 'source': 'admin', 'decision': 'rejected',
            'reason': req.reason.strip() or '管理员未上架该条目',
            'decided_at': datetime.datetime.now(CST).isoformat(),
            'actor': admin['username'],
        }
    now = datetime.datetime.now(CST).isoformat()
    c.execute(
        'UPDATE arsenal_items SET status=?,moderation=?,updated_at=? WHERE id=?',
        (req.status, json.dumps(moderation, ensure_ascii=False), now, item_id),
    )
    c.commit()
    updated = c.execute('SELECT * FROM arsenal_items WHERE id=?', (item_id,)).fetchone()
    c.close()
    audit_direct(
        request, 'arsenal.status', f'arsenal_item:{item_id}',
        f"status={req.status}; {req.reason.strip()[:200] or '管理员状态变更'}",
        decision=req.status,
    )
    return arsenal_db_item(updated)


# ── 邀请码后台 API ──
def require_admin(request: Request):
    user = request.state.user
    if request.state.auth_kind != 'session' or user['role'] != 'admin':
        raise HTTPException(403, '仅管理员登录态可操作后台')


@app.get('/api/admin/alerts')
def list_admin_alerts(request: Request, limit: int = Query(20, ge=1, le=100)):
    """站内值守台：读 ops-alerts jsonl（免凭证通道落盘），admin 专属。
    返回最近 N 条 + unread（近 24h 的 ERROR/CRITICAL 条数，供私窖红点）。"""
    require_admin(request)
    alert_dir = DATA_DIR / 'ops-alerts'
    now = datetime.datetime.now(CST)
    cutoff = (now - datetime.timedelta(hours=24)).isoformat()
    items: list[dict] = []
    unread = 0
    if alert_dir.is_dir():
        files = sorted(alert_dir.glob('*.jsonl'), reverse=True)[:14]
        for f in files:
            try:
                lines = f.read_text(encoding='utf-8').splitlines()
            except OSError:
                continue
            for raw in lines:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    rec = json.loads(raw)
                except json.JSONDecodeError:
                    continue
                if not isinstance(rec, dict) or not rec.get('ts'):
                    continue
                items.append({
                    'ts': rec.get('ts'),
                    'status': rec.get('status', ''),
                    'level': rec.get('level', 'INFO'),
                    'source': rec.get('source', ''),
                    'summary': rec.get('summary', ''),
                    'incident': rec.get('incident', ''),
                    'count': int(rec.get('count') or 0),
                })
                if rec.get('ts', '') >= cutoff and rec.get('level') in ('ERROR', 'CRITICAL'):
                    unread += 1
    items.sort(key=lambda r: r['ts'], reverse=True)
    return {'items': items[:limit], 'unread': unread, 'total': len(items)}


def admin_basic_auth_ok(request: Request) -> bool:
    """早班备料链（morning-chain）用 Basic auth 调 /admin/import/{day}。
    凭证：env ADMIN_AUTH（user:pass 内联），否则读 ADMIN_AUTH_FILE（默认 /data/.admin-auth，data 卷内）。
    与 morning-chain 的 `curl -u "$(cat /opt/xfsite/.admin-auth)"` 对齐；比对用 secrets.compare_digest。"""
    header = request.headers.get('authorization', '')
    if not header.startswith('Basic '):
        return False
    try:
        decoded = base64.b64decode(header[6:]).decode('utf-8')
    except Exception:
        return False
    expected = os.environ.get('ADMIN_AUTH') or ''
    if not expected:
        try:
            f = Path(os.environ.get('ADMIN_AUTH_FILE', '/data/.admin-auth'))
            expected = f.read_text(encoding='utf-8').strip()
        except OSError:
            return False
    return bool(expected) and secrets.compare_digest(decoded, expected)


# ── 成员账号管理 API（admin：群成员 ↔ 站内账号一一对应）──
@app.get('/api/admin/member-accounts')
def list_member_accounts(request: Request):
    require_admin(request)
    c = db()
    members = c.execute(
        '''SELECT username,display,nickname,msgs,last_active,name_source,
                  identity_flags,name_history,called_names
           FROM members ORDER BY msgs DESC,username'''
    ).fetchall()
    # Historical rows keyed by a display name remain for account recovery, but
    # must not appear as a second member in the admin roster.
    members = [
        row for row in members
        if 'legacy_display_key' not in _member_json_list(row['identity_flags'])
    ]
    accounts = {r['member_key']: dict(r) for r in c.execute(
        '''SELECT id,username,display_name,role,created_at,last_login,active,member_key,password_set
           FROM users WHERE member_key IS NOT NULL''')}
    unbound = [dict(r) for r in c.execute(
        '''SELECT id,username,display_name,created_at,last_login,active,password_set
           FROM users WHERE role='member' AND member_key IS NULL ORDER BY created_at DESC''')]
    c.close()
    return {
        'items': [{
            'member_key': m['username'],
            'display': m['display'],
            'nickname': m['nickname'],
            'msgs': m['msgs'],
            'last_active': m['last_active'],
            'name_source': m['name_source'] or 'masked_wxid',
            'identity_flags': _member_json_list(m['identity_flags']),
            'name_history': _member_json_list(m['name_history']),
            'called_names': _member_json_list(m['called_names']),
            'account': accounts.get(m['username']),
        } for m in members],
        'unbound': unbound,
    }


@app.post('/api/admin/member-accounts')
def create_member_account(req: MemberAccountReq, request: Request):
    require_admin(request)
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        member = c.execute('SELECT username,display FROM members WHERE username=?', (req.member_key,)).fetchone()
        if not member:
            raise HTTPException(404, '群成员不存在')
        if c.execute('SELECT 1 FROM users WHERE member_key=?', (req.member_key,)).fetchone():
            raise HTTPException(409, '该成员已有账号')
        username = (req.username or '').strip()
        if not username:
            raise HTTPException(422, '请填写用户名')
        if c.execute('SELECT 1 FROM users WHERE username=?', (username,)).fetchone():
            raise HTTPException(409, '用户名已存在')
        display = (member['display'] or member['username']).strip()
        if display and c.execute('SELECT 1 FROM users WHERE display_name=?', (display,)).fetchone():
            raise HTTPException(409, f'「{display}」已被其他账号使用')
        password = secrets.token_urlsafe(9)
        now = datetime.datetime.now(CST).isoformat()
        cur = c.execute(
            'INSERT INTO users(username,password_hash,role,display_name,member_key,created_at) VALUES(?,?,?,?,?,?)',
            (username, hash_pw(password), 'member', display, req.member_key, now),
        )
        user_id = cur.lastrowid
        c.commit()
        audit_direct(request, 'account.create', f'user:{user_id}', f'按成员生成账号 {username}（成员 {req.member_key}）')
        return {'ok': True, 'username': username, 'display_name': display, 'password': password, 'user_id': user_id}
    finally:
        c.close()


def claim_username(c, member_key: str, display: str, requested: str = '') -> str:
    """Pick an internal login name without exposing or overwriting another account."""
    base = normalize_auth_username(requested) or normalize_auth_username(display)
    if not base or base.startswith('群友·'):
        base = normalize_auth_username(member_key)
    if not base:
        raise HTTPException(422, '该成员没有可用的默认用户名')
    if not c.execute('SELECT 1 FROM users WHERE username=?', (base,)).fetchone():
        return base
    return (username_suggestions(c, base, limit=1) or [f'{base}-{secrets.randbelow(9000) + 1000}'])[0]


def issue_claim_link(c, user_id: int, now: str, expires_at: str) -> str:
    """Store one hashed, single-use claim token and return its plaintext once."""
    token = f'xfclaim_{secrets.token_urlsafe(32)}'
    token_hash = hashlib.sha256(token.encode('utf-8')).hexdigest()
    c.execute(
        '''UPDATE account_claims SET revoked_at=?
           WHERE user_id=? AND used_at IS NULL AND revoked_at IS NULL''',
        (now, user_id),
    )
    c.execute(
        '''INSERT INTO account_claims(user_id,token_hash,token_prefix,created_at,expires_at)
           VALUES(?,?,?,?,?)''',
        (user_id, token_hash, f'xfclaim_****{token[-4:]}', now, expires_at),
    )
    return token


@app.post('/api/admin/member-accounts/{member_ref}/claim-link')
def create_member_claim_link(
    member_ref: str,
    request: Request,
    req: ClaimLinkReq | None = None,
):
    """Issue a one-time claim link; plaintext token is returned only in this response."""
    admin = require_admin(request)
    ref = unquote(member_ref).strip()
    requested_username = req.username if req else ''
    ttl_hours = req.expires_hours if req else CLAIM_DEFAULT_TTL_HOURS
    now_dt = datetime.datetime.now(CST)
    now = now_dt.isoformat()
    expires_at = (now_dt + datetime.timedelta(hours=ttl_hours)).isoformat()
    c = db()
    created = False
    try:
        c.execute('BEGIN IMMEDIATE')
        account = None
        if ref.isdigit():
            account = c.execute(
                'SELECT id,username,password_set,active,display_name,member_key FROM users WHERE id=? AND role=?',
                (int(ref), 'member'),
            ).fetchone()
        if not account:
            account = c.execute(
                'SELECT id,username,password_set,active,display_name,member_key FROM users WHERE member_key=? AND role=?',
                (ref, 'member'),
            ).fetchone()
        if account:
            if not account['active']:
                raise HTTPException(409, '账号已禁用，不能生成认领链接')
            user_id = account['id']
            username = account['username']
            display = account['display_name'] or username
            password_set = bool(account['password_set'])
            member_key = account['member_key']
        else:
            member = c.execute(
                'SELECT username,display,nickname FROM members WHERE username=?', (ref,)
            ).fetchone()
            if not member:
                raise HTTPException(404, '群成员或账号不存在')
            member_key = member['username']
            display = normalize_auth_username(member['display'] or member['nickname'] or member_key)
            username = claim_username(c, member_key, display, requested_username)
            display = display or username
            cur = c.execute(
                '''INSERT INTO users(username,password_hash,password_set,role,display_name,member_key,created_at)
                   VALUES(?,?,0,'member',?,?,?)''',
                (username, '', display, member_key, now),
            )
            user_id = cur.lastrowid
            password_set = False
            created = True

        token = issue_claim_link(c, user_id, now, expires_at)
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    audit_direct(
        request,
        'account.claim_link',
        f'user:{user_id}',
        f'生成一次性认领链接（有效期至 {expires_at}）',
    )
    return {
        'ok': True,
        'created': created,
        'user_id': user_id,
        'username': username,
        'display_name': display,
        'password_set': password_set,
        'expires_at': expires_at,
        'claim_token': token,
        'claim_url': f'/claim/?t={urlquote(token, safe="")}',
    }


@app.post('/api/admin/member-accounts/{user_id}/reset-password')
def reset_member_password(user_id: int, request: Request):
    require_admin(request)
    c = db()
    u = c.execute('SELECT id,username FROM users WHERE id=? AND role=?', (user_id, 'member')).fetchone()
    if not u:
        c.close()
        raise HTTPException(404, '账号不存在')
    password = secrets.token_urlsafe(9)
    c.execute('UPDATE users SET password_hash=?,password_set=1 WHERE id=?', (hash_pw(password), user_id))
    c.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    c.execute('UPDATE agent_tokens SET revoked=1 WHERE user_id=? AND revoked=0', (user_id,))
    c.commit()
    audit_direct(request, 'account.reset_pw', f'user:{user_id}', f'重置 {u["username"]} 密码，旧登录与 agent token 已吊销')
    c.close()
    return {'ok': True, 'username': u['username'], 'password': password}


@app.post('/api/admin/member-accounts/{user_id}/revoke')
def revoke_member_account(user_id: int, request: Request):
    require_admin(request)
    c = db()
    u = c.execute('SELECT id FROM users WHERE id=? AND role=?', (user_id, 'member')).fetchone()
    if not u:
        c.close()
        raise HTTPException(404, '账号不存在')
    c.execute('UPDATE users SET active=0 WHERE id=?', (user_id,))
    c.execute('DELETE FROM sessions WHERE user_id=?', (user_id,))
    c.execute('UPDATE agent_tokens SET revoked=1 WHERE user_id=? AND revoked=0', (user_id,))
    c.commit()
    audit_direct(request, 'account.revoke', f'user:{user_id}', '禁用账号，会话与 agent token 已吊销')
    c.close()
    return {'ok': True}


@app.post('/api/admin/member-accounts/{user_id}/activate')
def activate_member_account(user_id: int, request: Request):
    require_admin(request)
    c = db()
    u = c.execute('SELECT id FROM users WHERE id=? AND role=?', (user_id, 'member')).fetchone()
    if not u:
        c.close()
        raise HTTPException(404, '账号不存在')
    c.execute('UPDATE users SET active=1 WHERE id=?', (user_id,))
    c.commit()
    audit_direct(request, 'account.activate', f'user:{user_id}', '启用账号')
    c.close()
    return {'ok': True}


class MemberBindReq(BaseModel):
    member_key: str


@app.post('/api/admin/member-accounts/{user_id}/bind')
def bind_member_account(user_id: int, req: MemberBindReq, request: Request):
    """管理员事后绑定：把已注册但没对上微信身份的账号，绑到某个群成员。"""
    require_admin(request)
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        u = c.execute('SELECT id FROM users WHERE id=? AND role=?', (user_id, 'member')).fetchone()
        if not u:
            raise HTTPException(404, '账号不存在')
        mem = c.execute('SELECT display FROM members WHERE username=?', (req.member_key,)).fetchone()
        if not mem:
            raise HTTPException(404, '群成员不存在')
        if c.execute('SELECT 1 FROM users WHERE member_key=? AND id<>?', (req.member_key, user_id)).fetchone():
            raise HTTPException(409, '该成员已被其他账号绑定')
        display = (mem['display'] or req.member_key).strip()
        c.execute('UPDATE users SET member_key=?, display_name=? WHERE id=?', (req.member_key, display, user_id))
        c.commit()
        audit_direct(request, 'account.bind', f'user:{user_id}', f'绑定成员 {req.member_key} → 显示名 {display}')
        return {'ok': True, 'display_name': display}
    finally:
        c.close()


def new_invite_code():
    raw = ''.join(secrets.choice(INVITE_ALPHABET) for _ in range(8))
    return f'XF-{raw[:4]}-{raw[4:]}'


def mask_invite_code(code):
    return f'XF-****-{code[-4:]}'


def invite_status(row, now):
    if row['revoked']:
        return 'revoked'
    if row['expires_at'] and datetime.datetime.fromisoformat(row['expires_at']) <= now:
        return 'expired'
    if row['used_count'] >= row['max_uses']:
        return 'exhausted'
    return 'active'


@app.post('/api/admin/invites')
def create_invites(req: InviteCreateReq, request: Request):
    user = require_admin(request)
    note = (req.note or '').strip()
    member = (req.member_name or '').strip() or None
    member_key = (req.member_key or '').strip() or None
    now = datetime.datetime.now(CST)
    expires_at = (now + datetime.timedelta(days=req.expires_days)).isoformat()
    codes = []
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        if member or member_key:
            if req.count != 1:
                raise HTTPException(422, '绑定成员的邀请码一次只发一张')
        if member:
            if c.execute('SELECT 1 FROM users WHERE display_name=?', (member,)).fetchone():
                raise HTTPException(409, f'「{member}」已注册过账号')
            dup = c.execute("SELECT code FROM invites WHERE member_name=? AND revoked=0 AND used_count<max_uses", (member,)).fetchone()
            if dup:
                raise HTTPException(409, f'「{member}」已有一张未用的邀请码，先撤销再发')
        if member_key:
            mem = c.execute('SELECT display FROM members WHERE username=?', (member_key,)).fetchone()
            if not mem:
                raise HTTPException(404, f'群成员不存在：{member_key}')
            if c.execute('SELECT 1 FROM users WHERE member_key=?', (member_key,)).fetchone():
                raise HTTPException(409, '该成员已有账号，先撤销旧邀请码或直接重置密码')
            dup = c.execute("SELECT code FROM invites WHERE member_key=? AND revoked=0 AND used_count<max_uses", (member_key,)).fetchone()
            if dup:
                raise HTTPException(409, f'该成员已有一张未用的邀请码，先撤销再发')
            # member_key 是唯一可信绑定：即使同时传了 member_name，display 也以成员表回填为准，防显示名与微信身份错绑
            member = mem['display'] or member_key
        while len(codes) < req.count:
            code = new_invite_code()
            try:
                c.execute(
                    '''INSERT INTO invites(code,note,created_by,created_at,max_uses,used_count,expires_at,revoked,used_by_json,member_name,member_key)
                       VALUES(?,?,?,?,?,0,?,0,'[]',?,?)''',
                    (code, note, user['username'], now.isoformat(), req.max_uses, expires_at, member, member_key),
                )
                codes.append(code)
            except sqlite3.IntegrityError:
                continue
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    return {'count': len(codes), 'codes': codes}


@app.get('/api/admin/invites')
def list_invites(request: Request):
    require_admin(request)
    now = datetime.datetime.now(CST)
    c = db()
    rows = c.execute('SELECT * FROM invites ORDER BY created_at DESC,code').fetchall()
    c.close()
    return {'items': [{
        'code': mask_invite_code(row['code']),
        'note': row['note'],
        'member_name': row['member_name'],
        'used': row['used_count'],
        'max': row['max_uses'],
        'status': invite_status(row, now),
        'created_by': row['created_by'],
        'created_at': row['created_at'],
        'expires_at': row['expires_at'],
    } for row in rows]}


@app.post('/api/admin/invites/{code}/revoke')
def revoke_invite(code: str, request: Request):
    require_admin(request)
    c = db()
    row = c.execute('SELECT code FROM invites WHERE code=?', (code,)).fetchone()
    if not row and re.fullmatch(r'XF-\*{4}-[A-Z2-9]{4}', code):
        matches = c.execute('SELECT code FROM invites WHERE substr(code,-4)=?', (code[-4:],)).fetchall()
        if len(matches) > 1:
            c.close()
            raise HTTPException(409, '邀请码后四位不唯一，请使用创建时返回的完整码')
        row = matches[0] if matches else None
    if not row:
        c.close()
        raise HTTPException(404, '邀请码不存在')
    c.execute('UPDATE invites SET revoked=1 WHERE code=?', (row['code'],))
    c.commit()
    masked = mask_invite_code(row['code'])
    c.close()
    return {'ok': True, 'code': masked, 'status': 'revoked'}


# ── 活动、投稿与投票 API ──
def validate_event_time(value, field):
    if not value:
        return None
    try:
        datetime.datetime.fromisoformat(value)
    except ValueError as exc:
        raise HTTPException(400, f'{field} 必须是 ISO 8601 时间') from exc
    return value


def submission_item(row):
    file_path = row['file_path']
    agent_token_id = row['agent_token_id'] if 'agent_token_id' in row.keys() else None
    agent_display_name = row['agent_display_name'] if 'agent_display_name' in row.keys() else None
    agent_capabilities_json = row['agent_capabilities_json'] if 'agent_capabilities_json' in row.keys() else '[]'
    if 'agent_votes' in row.keys():
        agent_votes = row['agent_votes'] or 0
    else:
        c = db()
        extra = c.execute(
            "SELECT agent_token_id,agent_display_name,agent_capabilities_json FROM submissions WHERE id=?",
            (row['id'],),
        ).fetchone()
        if extra:
            agent_token_id = extra['agent_token_id']
            agent_display_name = extra['agent_display_name']
            agent_capabilities_json = extra['agent_capabilities_json']
        agent_votes = c.execute(
            "SELECT COUNT(*) FROM agent_submission_votes WHERE submission_id=? AND status<>'rejected'",
            (row['id'],),
        ).fetchone()[0]
        c.close()
    item = {
        'id': row['id'], 'username': row['username'], 'title': row['title'],
        'note': row['note'], 'file_url': f'/uploads/{file_path}' if file_path else None,
        'mime': row['mime'], 'size': row['size'], 'created_at': row['created_at'],
        'status': row['status'], 'votes': row['votes'], 'human_votes': row['votes'],
        'agent_votes': agent_votes, 'via': 'agent' if agent_token_id else row['via'],
        'via_label': row['via_label'],
    }
    if agent_token_id:
        item['agent'] = {
            'id': agent_token_id,
            'display_name': agent_display_name or row['via'] or 'Agent',
            'capabilities': parse_agent_capabilities(agent_capabilities_json),
            'mentor_username': row['username'],
        }
    if 'moderation' in row.keys():
        item['moderation'] = parse_moderation(row['moderation'])
    return item


def parse_moderation(value):
    if not value:
        return None
    try:
        return json.loads(value)
    except (TypeError, json.JSONDecodeError):
        return {'reason': str(value)}


def event_item(row):
    item = {
        'id': row['id'], 'slug': row['slug'], 'title': row['title'],
        'kind': row['kind'], 'status': row['status'],
        'starts_at': row['starts_at'], 'ends_at': row['ends_at'],
        'rules_md': row['rules_md'], 'reward': row['reward'],
        'cover_path': row['cover_path'], 'created_by': row['created_by'],
    }
    if 'submission_count' in row.keys():
        item['submission_count'] = row['submission_count']
    if 'group_essay_count' in row.keys():
        item['group_essay_count'] = row['group_essay_count']
    return item


async def parse_submission_form(request):
    content_type = request.headers.get('content-type', '')
    if not content_type.lower().startswith('multipart/form-data'):
        raise HTTPException(415, '投稿必须使用 multipart/form-data')
    max_body = MAX_UPLOAD_BYTES + 128 * 1024
    content_length = request.headers.get('content-length')
    if content_length and int(content_length) > max_body:
        raise HTTPException(413, '文件不能超过 10MB')
    chunks = []
    body_size = 0
    async for chunk in request.stream():
        body_size += len(chunk)
        if body_size > max_body:
            raise HTTPException(413, '文件不能超过 10MB')
        chunks.append(chunk)
    body = b''.join(chunks)
    envelope = (
        f'Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n'.encode('latin-1') + body
    )
    message = BytesParser(policy=email_policy).parsebytes(envelope)
    if not message.is_multipart():
        raise HTTPException(400, 'multipart 请求格式无效')
    fields = {}
    upload = None
    for part in message.iter_parts():
        if part.get_content_disposition() != 'form-data':
            continue
        name = part.get_param('name', header='content-disposition')
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b''
        if name == 'file' and filename:
            if upload is not None:
                raise HTTPException(400, '一次只能上传一个文件')
            upload = {'filename': filename, 'data': payload}
        elif name in {'title', 'note'}:
            charset = part.get_content_charset() or 'utf-8'
            try:
                fields[name] = payload.decode(charset)
            except (LookupError, UnicodeDecodeError) as exc:
                raise HTTPException(400, f'{name} 不是有效文本') from exc
    return fields, upload


@app.post('/api/admin/events')
def upsert_event(req: EventUpsertReq, request: Request):
    user = require_admin(request)
    slug = req.slug.strip()
    title = req.title.strip()
    if not re.fullmatch(r'[a-z0-9]+(?:-[a-z0-9]+)*', slug):
        raise HTTPException(400, 'slug 只允许小写字母、数字和单连字符')
    if not title:
        raise HTTPException(400, '活动标题不能为空')
    starts_at = validate_event_time(req.starts_at, 'starts_at')
    ends_at = validate_event_time(req.ends_at, 'ends_at')
    c = db()
    c.execute(
        '''INSERT INTO events(slug,title,kind,status,starts_at,ends_at,rules_md,reward,cover_path,created_by)
           VALUES(?,?,?,?,?,?,?,?,?,?)
           ON CONFLICT(slug) DO UPDATE SET
             title=excluded.title,kind=excluded.kind,status=excluded.status,
             starts_at=excluded.starts_at,ends_at=excluded.ends_at,
             rules_md=excluded.rules_md,reward=excluded.reward,cover_path=excluded.cover_path''',
        (slug, title, req.kind, req.status, starts_at, ends_at,
         req.rules_md.strip(), req.reward.strip(), req.cover_path, user['username']),
    )
    c.commit()
    row = c.execute('SELECT * FROM events WHERE slug=?', (slug,)).fetchone()
    c.close()
    return event_item(row)


@app.get('/api/events', tags=['agent'])
def list_events():
    c = db()
    rows = c.execute(
        '''SELECT e.*,
                  COUNT(s.id) + COALESCE((
                    SELECT COUNT(*) FROM essay_activity_items ai
                    WHERE ai.event_id=e.id AND ai.status='accepted'
                  ),0) submission_count,
                  COALESCE((
                    SELECT COUNT(*) FROM essay_activity_items ai2
                    WHERE ai2.event_id=e.id AND ai2.status='accepted'
                  ),0) group_essay_count
           FROM events e
           LEFT JOIN submissions s ON s.event_id=e.id AND s.status='accepted'
           GROUP BY e.id
           ORDER BY CASE e.status WHEN 'open' THEN 0 WHEN 'upcoming' THEN 1 ELSE 2 END,
                    COALESCE(e.starts_at,'') DESC,e.id'''
    ).fetchall()
    c.close()
    return {'items': [event_item(row) for row in rows]}


@app.get('/api/events/{slug}', tags=['agent'])
def get_event(slug: str, request: Request):
    c = db()
    event = c.execute('SELECT * FROM events WHERE slug=?', (slug,)).fetchone()
    if not event:
        c.close()
        raise HTTPException(404, '活动不存在')
    rows = c.execute(
        '''SELECT id,username,title,note,file_path,mime,size,created_at,status,votes,via,via_label,moderation
           FROM submissions WHERE event_id=? AND status='accepted'
           ORDER BY created_at DESC,id DESC''',
        (event['id'],),
    ).fetchall()
    group_rows = c.execute(
        '''SELECT id,essay_id,author,title,body,source_message_ids,source_date,status
           FROM essay_activity_items WHERE event_id=? AND status='accepted'
           ORDER BY source_date DESC,id DESC''',
        (event['id'],),
    ).fetchall()
    c.close()
    out = event_item(event)
    out['submissions'] = [submission_item(row) for row in rows]
    authenticated = getattr(request.state, 'auth_kind', None) == 'session'
    out['group_essays'] = [_essay_activity_item(row, include_body=authenticated) for row in group_rows]
    out['group_essay_count'] = len(group_rows)
    out['submission_count'] = len(rows) + len(group_rows)
    return out


@app.get('/api/events/{slug}/essays', tags=['agent'])
def event_group_essays(slug: str, request: Request):
    """群内小作文的独立投影；匿名只给清单，登录后才给正文，避免活动公开端泄露窖藏内容。"""
    c = db()
    event = c.execute('SELECT * FROM events WHERE slug=?', (slug,)).fetchone()
    if not event:
        c.close()
        raise HTTPException(404, '活动不存在')
    rows = c.execute(
        '''SELECT id,essay_id,author,title,body,source_message_ids,source_date,status
           FROM essay_activity_items WHERE event_id=? AND status='accepted'
           ORDER BY source_date DESC,id DESC''',
        (event['id'],),
    ).fetchall()
    c.close()
    authenticated = getattr(request.state, 'auth_kind', None) == 'session'
    return {
        'event': event_item(event),
        'items': [_essay_activity_item(row, include_body=authenticated) for row in rows],
        'count': len(rows),
    }


@app.get('/api/admin/events/{slug}/submissions')
def admin_event_submissions(slug: str, request: Request):
    require_admin(request)
    c = db()
    event = c.execute('SELECT id FROM events WHERE slug=?', (slug,)).fetchone()
    if not event:
        c.close()
        raise HTTPException(404, '活动不存在')
    rows = c.execute(
        '''SELECT id,username,title,note,file_path,mime,size,created_at,status,votes,via,via_label,moderation
           FROM submissions WHERE event_id=? ORDER BY created_at DESC,id DESC''',
        (event['id'],),
    ).fetchall()
    group_rows = c.execute(
        '''SELECT id,essay_id,author,title,body,source_message_ids,source_date,status
           FROM essay_activity_items WHERE event_id=? ORDER BY source_date DESC,id DESC''',
        (event['id'],),
    ).fetchall()
    c.close()
    return {
        'items': [submission_item(row) for row in rows],
        'group_essays': [_essay_activity_item(row, include_body=True) for row in group_rows],
    }


@app.post('/api/admin/submissions/{submission_id}/status')
def moderate_submission(submission_id: int, req: SubmissionStatusReq, request: Request):
    require_admin(request)
    c = db()
    row = c.execute('SELECT id FROM submissions WHERE id=?', (submission_id,)).fetchone()
    if not row:
        c.close()
        raise HTTPException(404, '投稿不存在')
    moderation = json.dumps({
        'rule': 'manual', 'llm': 'not_run', 'decision': req.status,
        'reason': '管理员从活动后台改判',
    }, ensure_ascii=False)
    c.execute('UPDATE submissions SET status=?,moderation=? WHERE id=?',
              (req.status, moderation, submission_id))
    c.commit()
    row = c.execute(
        '''SELECT id,username,title,note,file_path,mime,size,created_at,status,votes,via,via_label,moderation
           FROM submissions WHERE id=?''',
        (submission_id,),
    ).fetchone()
    c.close()
    return submission_item(row)


@app.post(
    '/api/events/{slug}/submissions',
    tags=['agent'],
    openapi_extra={
        'requestBody': {
            'required': True,
            'content': {'multipart/form-data': {'schema': {
                'type': 'object', 'required': ['title'],
                'properties': {
                    'title': {'type': 'string'},
                    'note': {'type': 'string'},
                    'file': {'type': 'string', 'format': 'binary'},
                },
            }}},
        },
    },
)
async def submit_event_entry(slug: str, request: Request):
    fields, upload = await parse_submission_form(request)
    title = fields.get('title', '').strip()
    note = fields.get('note', '').strip()
    if not 1 <= len(title) <= 160:
        raise HTTPException(400, '投稿标题需为 1–160 字')
    if len(note) > 4000:
        raise HTTPException(400, '投稿说明不能超过 4000 字')
    c = db()
    event = c.execute('SELECT * FROM events WHERE slug=?', (slug,)).fetchone()
    c.close()
    if not event:
        raise HTTPException(404, '活动不存在')
    if event['status'] != 'open':
        raise HTTPException(409, '活动当前不接受投稿')

    relative_path = None
    mime = None
    size = 0
    saved_path = None
    if upload:
        ext = Path(upload['filename']).suffix.lower()
        if ext not in UPLOAD_MIME:
            raise HTTPException(415, '仅允许 png/jpg/webp/svg/pdf/md/txt/zip')
        size = len(upload['data'])
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(413, '文件不能超过 10MB')
        event_dir = UPLOAD_DIR / event['slug']
        event_dir.mkdir(parents=True, exist_ok=True)
        saved_path = event_dir / f'{uuid.uuid4().hex}{ext}'
        try:
            with saved_path.open('wb') as output:
                output.write(upload['data'])
        except Exception:
            saved_path.unlink(missing_ok=True)
            raise
        relative_path = f'{event["slug"]}/{saved_path.name}'
        mime = UPLOAD_MIME[ext]

    user = request.state.user
    created_at = datetime.datetime.now(CST).isoformat()
    agent_token_id, agent_display_name, agent_capabilities_json = agent_identity_columns(request)
    c = db()
    try:
        cursor = c.execute(
            '''INSERT INTO submissions(
                 event_id,user_id,username,title,note,file_path,mime,size,created_at,status,votes,
                 via,via_label,agent_token_id,agent_display_name,agent_capabilities_json,moderation)
               VALUES(?,?,?,?,?,?,?,?,?,'pending',0,?,?,?,?,?,NULL)''',
            (event['id'], user['id'], user['username'], title, note,
             relative_path, mime, size, created_at,
             request.state.agent_name, request.state.agent_label,
             agent_token_id, agent_display_name, agent_capabilities_json),
        )
        c.commit()
        submission_id = cursor.lastrowid
        row = c.execute(
            '''SELECT id,username,title,note,file_path,mime,size,created_at,status,votes,via,via_label,moderation
               FROM submissions WHERE id=?''',
            (submission_id,),
        ).fetchone()
    except Exception:
        if saved_path:
            saved_path.unlink(missing_ok=True)
        raise
    finally:
        c.close()
    queue_id = enqueue_action(
        DB, actor_user=user['username'], actor_agent=request.state.agent_name,
        action='submission.create', target_type='submission', target_id=submission_id,
        content=f'{title}\n{note}', anchor=f'event:{slug}',
        metadata={'auth_kind': request.state.auth_kind, 'event': slug},
    )
    record_agent_action(
        request, 'submission.create', 'submission', submission_id,
        metadata={'event': slug, 'title': title},
    )
    result = submission_item(row)
    result['moderation_queue_id'] = queue_id
    return result


@app.post('/api/submissions/{submission_id}/vote', tags=['agent'])
def vote_submission(submission_id: int, request: Request):
    user = request.state.user
    now = datetime.datetime.now(CST).isoformat()
    is_agent = request.state.auth_kind == 'agent'
    c = db()
    try:
        c.execute('BEGIN IMMEDIATE')
        submission = c.execute(
            '''SELECT s.id,s.status,e.status event_status FROM submissions s
               JOIN events e ON s.event_id=e.id WHERE s.id=?''',
            (submission_id,),
        ).fetchone()
        if not submission:
            raise HTTPException(404, '投稿不存在')
        if submission['event_status'] != 'open':
            raise HTTPException(409, '活动当前不接受投票')
        if submission['status'] != 'accepted':
            raise HTTPException(409, '投稿审核通过后才能投票')
        if is_agent:
            agent_token_id = request.state.agent_token_id
            cursor = c.execute(
                '''INSERT OR IGNORE INTO agent_submission_votes
                   (submission_id,agent_token_id,user_id,created_at,status,moderation)
                   VALUES(?,?,?,?,'pending',NULL)''',
                (submission_id, agent_token_id, user['id'], now),
            )
            added = cursor.rowcount == 1
            vote = c.execute(
                '''SELECT status,moderation FROM agent_submission_votes
                   WHERE submission_id=? AND agent_token_id=?''',
                (submission_id, agent_token_id),
            ).fetchone()
            agent_votes = c.execute(
                "SELECT COUNT(*) FROM agent_submission_votes WHERE submission_id=? AND status<>'rejected'",
                (submission_id,),
            ).fetchone()[0]
        else:
            cursor = c.execute(
                '''INSERT OR IGNORE INTO submission_votes
                   (submission_id,user_id,created_at,status,moderation) VALUES(?,?,?,'pending',NULL)''',
                (submission_id, user['id'], now),
            )
            added = cursor.rowcount == 1
            vote = c.execute(
                'SELECT status,moderation FROM submission_votes WHERE submission_id=? AND user_id=?',
                (submission_id, user['id']),
            ).fetchone()
            agent_votes = c.execute(
                "SELECT COUNT(*) FROM agent_submission_votes WHERE submission_id=? AND status<>'rejected'",
                (submission_id,),
            ).fetchone()[0]
        votes = c.execute('SELECT votes FROM submissions WHERE id=?', (submission_id,)).fetchone()[0]
        c.commit()
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()
    queue_id = None
    if added:
        queue_id = enqueue_action(
            DB, actor_user=user['username'], actor_agent=request.state.agent_name,
            action='submission.vote', target_type=('agent_action' if is_agent else 'vote'), target_id=submission_id,
            content='', anchor=f'submission:{submission_id}',
            metadata={'auth_kind': request.state.auth_kind, 'user_id': user['id'],
                      'agent_token_id': request.state.agent_token_id if is_agent else None},
        )
    record_agent_action(
        request, 'submission.vote', 'submission', submission_id,
        metadata={'already_voted': not added, 'vault': 'agent' if is_agent else 'human'},
    )
    return {
        'ok': True, 'id': submission_id, 'votes': votes,
        'human_votes': votes, 'agent_votes': agent_votes,
        'vault': 'agent' if is_agent else 'human',
        'already_voted': not added, 'status': vote['status'],
        'moderation': parse_moderation(vote['moderation']),
        'moderation_queue_id': queue_id,
    }


# ── 跨期线索 API ──
def ledger_files():
    return sorted(GOVERNED_LEDGER_DIR.glob('*.json')) if GOVERNED_LEDGER_DIR.exists() else []


@app.get('/api/threads', tags=['agent'])
def list_threads():
    threads = {}
    for path in ledger_files():
        data = load_governed_ledger(path)
        for thread in data.get('threads') or []:
            threads[thread['id']] = {
                **thread, 'latest_date': data.get('date'), 'latest_issue': data.get('issue'),
            }
    return {'items': sorted(threads.values(), key=lambda item: item['id'])}


@app.get('/api/threads/{thread_id}', tags=['agent'])
def get_thread(thread_id: str):
    latest = None
    issues = []
    for path in ledger_files():
        data = load_governed_ledger(path)
        thread = next((item for item in data.get('threads') or [] if item.get('id') == thread_id), None)
        if not thread:
            continue
        latest = {**thread, 'latest_date': data.get('date'), 'latest_issue': data.get('issue')}
        theme = next((item for item in data.get('themes') or [] if item.get('h') == thread.get('theme')), None)
        issues.append({
            'date': data.get('date'), 'issue': data.get('issue'),
            'ledger_title': data.get('title'), 'theme': theme,
        })
    if not latest:
        raise HTTPException(404, '线索不存在')
    return {'thread': latest, 'issues': issues}


# ── 学徒提问串 API ──
def question_thread_item(c, row, *, include_replies=True, include_internal=True):
    agent = {
        'name': row['agent_name'],
        'display_name': row['agent_display_name'],
        'capabilities': parse_agent_capabilities(row['agent_capabilities_json']),
        'mentor': {
            'username': row['mentor_username'] if 'mentor_username' in row.keys() else None,
            'display_name': row['mentor_display_name'] if 'mentor_display_name' in row.keys() else None,
        },
    }
    if include_internal:
        agent['id'] = row['agent_token_id']
        agent['mentor']['user_id'] = row['user_id']
    item = {
        'id': row['id'], 'title': row['title'], 'body': row['body'],
        'target': row['target'], 'status': row['status'],
        'created_at': row['created_at'], 'updated_at': row['updated_at'],
        'reply_count': int(row['reply_count'] or 0) if 'reply_count' in row.keys() else 0,
        'agent': agent,
    }
    if include_replies:
        replies = c.execute(
            '''SELECT id,thread_id,user_id,agent_token_id,author_kind,author_name,text,
                      created_at,agent_name,agent_display_name,agent_capabilities_json,
                      accepted,accepted_by,accepted_at
               FROM question_replies WHERE thread_id=? ORDER BY created_at,id''',
            (row['id'],),
        ).fetchall()
        reply_items = []
        for reply in replies:
            reply_agent = None
            if reply['agent_token_id']:
                reply_agent = {
                    'name': reply['agent_name'],
                    'display_name': reply['agent_display_name'],
                    'capabilities': parse_agent_capabilities(reply['agent_capabilities_json']),
                }
                if include_internal:
                    reply_agent['id'] = reply['agent_token_id']
            reply_items.append({
                'id': reply['id'], 'thread_id': reply['thread_id'],
                'author_kind': reply['author_kind'], 'author_name': reply['author_name'],
                'text': reply['text'], 'created_at': reply['created_at'],
                'accepted': bool(reply['accepted']), 'accepted_at': reply['accepted_at'],
                'agent': reply_agent,
            })
        item['replies'] = reply_items
    return item


def question_thread_row(c, thread_id):
    return c.execute(
        '''SELECT qt.*,u.username AS mentor_username,u.display_name AS mentor_display_name,
                  (SELECT COUNT(*) FROM question_replies qr WHERE qr.thread_id=qt.id) AS reply_count
           FROM question_threads qt LEFT JOIN users u ON u.id=qt.user_id
           WHERE qt.id=?''',
        (thread_id,),
    ).fetchone()


@app.get('/api/agent/threads', tags=['agent'])
def list_agent_question_threads(
    request: Request,
    status: str = Query('open', pattern='^(open|closed|all)$'),
    limit: int = Query(50, ge=1, le=100),
    mine: bool = Query(False),
):
    auth_kind = getattr(request.state, 'auth_kind', None)
    if auth_kind == 'agent':
        require_agent(request)
    elif mine:
        raise HTTPException(401, 'mine=true 需要 Agent token')
    c = db()
    conditions = []
    params = []
    if auth_kind == 'agent' and mine:
        conditions.append('agent_token_id=?')
        params.append(request.state.agent_token_id)
    if status != 'all':
        conditions.append('status=?')
        params.append(status)
    where = (' WHERE ' + ' AND '.join(conditions)) if conditions else ''
    rows = c.execute(
        f'''SELECT qt.*,u.username AS mentor_username,u.display_name AS mentor_display_name,
                   (SELECT COUNT(*) FROM question_replies qr WHERE qr.thread_id=qt.id) AS reply_count
            FROM question_threads qt LEFT JOIN users u ON u.id=qt.user_id{where}
            ORDER BY qt.updated_at DESC,qt.id DESC LIMIT ?''',
        (*params, limit),
    ).fetchall()
    include_internal = auth_kind in {'agent', 'session'}
    items = [
        question_thread_item(
            c, row, include_replies=False, include_internal=include_internal,
        )
        for row in rows
    ]
    c.close()
    return {'items': items, 'count': len(items), 'status': status, 'mine': mine}


@app.post('/api/agent/threads', tags=['agent'])
def create_agent_question_thread(req: AgentQuestionReq, request: Request):
    profile = require_agent(request)
    title = clean_agent_text(req.title, 160, required=True)
    body = clean_agent_text(req.body, 4000, required=True)
    target = clean_agent_text(req.target, 120)
    now = datetime.datetime.now(CST).isoformat()
    c = db()
    try:
        cursor = c.execute(
            '''INSERT INTO question_threads(
                 user_id,agent_token_id,title,body,target,status,created_at,updated_at,
                 agent_name,agent_display_name,agent_capabilities_json)
               VALUES(?,?,?,?,?,'open',?,?,?,?,?)''',
            (
                request.state.user['id'], profile['id'], title, body, target, now, now,
                profile['name'], profile['display_name'],
                json.dumps(profile['capabilities'], ensure_ascii=False),
            ),
        )
        thread_id = cursor.lastrowid
        c.commit()
        row = question_thread_row(c, thread_id)
        result = question_thread_item(c, row)
    finally:
        c.close()
    record_agent_action(
        request, 'question.create', 'question_thread', thread_id,
        metadata={'target': target},
    )
    return result


@app.get('/api/agent/threads/{thread_id}', tags=['agent'])
def get_agent_question_thread(thread_id: int, request: Request):
    include_internal = getattr(request.state, 'auth_kind', None) in {'agent', 'session'}
    c = db()
    row = question_thread_row(c, thread_id)
    if not row:
        c.close()
        raise HTTPException(404, '提问串不存在')
    result = question_thread_item(c, row, include_internal=include_internal)
    if getattr(request.state, 'auth_kind', None) == 'session':
        result['is_mine'] = int(row['user_id']) == int(request.state.user['id'])
    else:
        result['is_mine'] = False
    c.close()
    return result


@app.post('/api/agent/threads/{thread_id}/replies', tags=['agent'])
def reply_agent_question_thread(thread_id: int, req: AgentReplyReq, request: Request):
    if request.state.auth_kind not in {'agent', 'session'}:
        raise HTTPException(401, '请先登录')
    text = clean_agent_text(req.text, 2000, required=True)
    c = db()
    row = question_thread_row(c, thread_id)
    if not row:
        c.close()
        raise HTTPException(404, '提问串不存在')
    if row['status'] == 'closed':
        c.close()
        raise HTTPException(409, '提问串已关闭')
    if request.state.auth_kind == 'agent':
        author_kind = 'agent'
        profile = request.state.agent_profile
        author_name = profile['display_name']
        agent_token_id = profile['id']
        agent_name = profile['name']
        agent_display_name = profile['display_name']
        capabilities_json = json.dumps(profile['capabilities'], ensure_ascii=False)
    else:
        author_kind = 'human'
        profile = None
        author_name = request.state.user.get('display_name') or request.state.user['username']
        agent_token_id = None
        agent_name = None
        agent_display_name = None
        capabilities_json = '[]'
    now = datetime.datetime.now(CST).isoformat()
    try:
        cursor = c.execute(
            '''INSERT INTO question_replies(
                 thread_id,user_id,agent_token_id,author_kind,author_name,text,created_at,
                 agent_name,agent_display_name,agent_capabilities_json)
               VALUES(?,?,?,?,?,?,?,?,?,?)''',
            (thread_id, request.state.user['id'], agent_token_id, author_kind, author_name,
             text, now, agent_name, agent_display_name, capabilities_json),
        )
        c.execute('UPDATE question_threads SET updated_at=? WHERE id=?', (now, thread_id))
        c.commit()
        result = question_thread_item(c, question_thread_row(c, thread_id))
        reply_id = cursor.lastrowid
    finally:
        c.close()
    record_agent_action(
        request, 'question.reply', 'question_thread', thread_id,
        metadata={'reply_id': reply_id, 'author_kind': author_kind},
    )
    return result


# ── 原子语境 API / 单消息 anchor ──
CONTEXT_ANCHOR_RE = re.compile(r'^atom:(?P<unit_id>cu-\d{8}-\d{4}):(?P<ordinal>[1-9]\d*)$')
CONTEXT_MACHINE_ID_RE = re.compile(r'(?:wxid_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|gh_[A-Za-z0-9_-]+)')


def parse_context_anchor(anchor: str):
    match = CONTEXT_ANCHOR_RE.fullmatch(str(anchor or '').strip())
    if not match:
        return None
    return match.group('unit_id'), int(match.group('ordinal'))


def _json_value(raw, default):
    try:
        value = json.loads(raw) if isinstance(raw, str) else raw
    except (TypeError, json.JSONDecodeError):
        return default
    return value


def _context_public_redact(value):
    return CONTEXT_MACHINE_ID_RE.sub('群友', clean_wechat_content(str(value or '')))


def current_context_unit(c, unit_id):
    return c.execute(
        '''SELECT * FROM context_units
           WHERE id=? ORDER BY version DESC LIMIT 1''',
        (unit_id,),
    ).fetchone()


def context_row_visible(request, row, *, requested=None):
    if not row or row['status'] != 'published':
        return False
    visibility = requested or row['visibility'] or 'public'
    auth_kind = getattr(request.state, 'auth_kind', None)
    user = getattr(request.state, 'user', None)
    if visibility == 'public':
        return row['visibility'] == 'public'
    if visibility == 'member':
        return auth_kind == 'session' and row['visibility'] in {'public', 'member'}
    if visibility == 'private':
        return auth_kind == 'session' and user and user.get('role') == 'admin' and row['visibility'] == 'private'
    return False


def resolve_context_anchor(c, anchor, request, *, expected_date=None):
    parsed = parse_context_anchor(anchor)
    if not parsed:
        return None
    unit_id, ordinal = parsed
    row = current_context_unit(c, unit_id)
    if not context_row_visible(request, row):
        raise HTTPException(404, '语境块或消息不存在')
    if expected_date and row['source_date'] != expected_date:
        raise HTTPException(400, 'anchor 必须与评论日期一致')
    message = c.execute(
        '''SELECT * FROM context_unit_messages
           WHERE unit_id=? AND unit_version=? AND ordinal=?''',
        (unit_id, row['version'], ordinal),
    ).fetchone()
    if not message:
        raise HTTPException(404, '语境消息不存在')
    return row, message


def context_summary(c, row):
    evidence_count = c.execute(
        'SELECT COUNT(*) FROM evidence_refs WHERE unit_id=? AND unit_version=?',
        (row['id'], row['version']),
    ).fetchone()[0]
    return {
        'id': row['id'],
        'date': row['source_date'],
        'version': row['version'],
        'status': row['status'],
        'visibility': row['visibility'],
        'title': row['title'],
        'summary': row['summary'],
        'start_at': row['start_at'],
        'end_at': row['end_at'],
        'participants': [_context_public_redact(item) for item in _json_value(row['participants_json'], [])],
        'message_count': row['message_count'],
        'has_gap': bool(row['has_gap']),
        'evidence_count': evidence_count,
        'detail_url': f"/api/context-units/{row['id']}",
    }


def _context_projection(c, row, visibility):
    projection = c.execute(
        '''SELECT * FROM context_public_projection
           WHERE unit_id=? AND version=? AND visibility=?''',
        (row['id'], row['version'], visibility),
    ).fetchone()
    if not projection and visibility != 'public':
        projection = c.execute(
            '''SELECT * FROM context_public_projection
               WHERE unit_id=? AND version=? AND visibility='public' ''',
            (row['id'], row['version']),
        ).fetchone()
    return projection


def _context_messages(c, row, request):
    visibility = 'member' if getattr(request.state, 'auth_kind', None) == 'session' else 'public'
    projection = _context_projection(c, row, visibility)
    if not projection:
        return []
    like_rows = c.execute(
        '''SELECT message_id,COUNT(*) AS likes,
                  MAX(CASE WHEN user_id=? THEN 1 ELSE 0 END) AS liked
           FROM context_message_likes
           WHERE unit_id=? AND unit_version=?
           GROUP BY message_id''',
        (
            (getattr(getattr(request, 'state', None), 'user', {}) or {}).get('id'),
            row['id'],
            row['version'],
        ),
    ).fetchall()
    likes_by_message = {
        item['message_id']: {'likes': item['likes'], 'liked': bool(item['liked'])}
        for item in like_rows
    }
    raw = projection['member_text'] if visibility == 'member' else projection['public_text']
    messages = _json_value(raw, [])
    if not isinstance(messages, list):
        return []
    out = []
    for entry in messages:
        if not isinstance(entry, dict):
            continue
        try:
            ordinal = int(entry.get('ordinal'))
        except (TypeError, ValueError):
            continue
        entry = dict(entry)
        entry['ordinal'] = ordinal
        entry.setdefault('comment_anchor', f"atom:{row['id']}:{ordinal}")
        entry.setdefault('message_id', None)
        entry.setdefault('at', None)
        entry['sender_name'] = _context_public_redact(entry.get('sender_name', '群友'))
        entry['text'] = _context_public_redact(entry.get('text', ''))
        like_state = likes_by_message.get(entry['message_id'], {})
        out.append({
            # Keep the compact UI names alongside the explicit API names so
            # older cellar clients can roll forward without a data shim.
            'id': entry['message_id'],
            'ordinal': entry['ordinal'],
            'message_id': entry['message_id'],
            'time': entry['at'],
            'at': entry['at'],
            'sender': entry['sender_name'],
            'sender_name': entry['sender_name'],
            'text': entry['text'],
            'comment_anchor': entry['comment_anchor'],
            'likes': int(like_state.get('likes') or 0),
            'liked': bool(like_state.get('liked')),
        })
    return sorted(out, key=lambda item: item['ordinal'])


def _context_cursor(value):
    if not value:
        return None
    try:
        decoded = base64.urlsafe_b64decode(str(value) + '=' * (-len(str(value)) % 4))
        date, unit_id = decoded.decode('utf-8').split('|', 1)
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', date) and unit_id.startswith('cu-'):
            return date, unit_id
    except (ValueError, TypeError, UnicodeDecodeError, base64.binascii.Error):
        pass
    raise HTTPException(400, 'cursor 无效')


def _make_context_cursor(row):
    raw = f"{row['source_date']}|{row['id']}".encode('utf-8')
    return base64.urlsafe_b64encode(raw).decode('ascii').rstrip('=')


@app.get('/api/context-units', tags=['context'])
def list_context_units(
    request: Request,
    date: str | None = None,
    visibility: str = Query('auto', pattern='^(auto|public|member|private)$'),
    limit: int = Query(24, ge=1, le=100),
    cursor: str | None = None,
):
    if date and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise HTTPException(400, 'date 格式必须是 YYYY-MM-DD')
    decoded_cursor = _context_cursor(cursor)
    c = db()
    rows = c.execute(
        '''SELECT u.* FROM context_units u
           JOIN (SELECT id,MAX(version) AS version FROM context_units GROUP BY id) latest
             ON latest.id=u.id AND latest.version=u.version
           WHERE u.status='published'
           ORDER BY u.source_date DESC,u.id ASC''',
    ).fetchall()
    items = []
    visible_rows = []
    for row in rows:
        if date and row['source_date'] != date:
            continue
        if decoded_cursor:
            last_date, last_id = decoded_cursor
            if row['source_date'] > last_date or (row['source_date'] == last_date and row['id'] <= last_id):
                continue
        requested = None if visibility == 'auto' else visibility
        if requested == 'auto':
            requested = 'member' if getattr(request.state, 'auth_kind', None) == 'session' else 'public'
        if not context_row_visible(request, row, requested=requested):
            continue
        visible_rows.append(row)
        items.append(context_summary(c, row))
        if len(items) >= limit + 1:
            break
    c.close()
    has_more = len(items) > limit
    items = items[:limit]
    return {
        'items': items,
        'next_cursor': _make_context_cursor(visible_rows[limit - 1]) if has_more and len(visible_rows) >= limit else None,
        'count': len(items),
    }


@app.get('/api/context-units/{unit_id}/evidence', tags=['context'])
def context_unit_evidence(unit_id: str, request: Request):
    c = db()
    row = current_context_unit(c, unit_id)
    if not context_row_visible(request, row):
        c.close()
        raise HTTPException(404, '语境块不存在')
    rows = c.execute(
        '''SELECT source_type,source_id,source_date,message_ids_json,
                  ordinal_start,ordinal_end,quote_hash,url
           FROM evidence_refs WHERE unit_id=? AND unit_version=?
           ORDER BY id''',
        (unit_id, row['version']),
    ).fetchall()
    c.close()
    items = []
    for evidence in rows:
        ordinal_range = None
        if evidence['ordinal_start'] is not None and evidence['ordinal_end'] is not None:
            ordinal_range = [evidence['ordinal_start'], evidence['ordinal_end']]
        items.append({
            'source_type': evidence['source_type'],
            'source_id': evidence['source_id'],
            'date': evidence['source_date'],
            'message_ids': _json_value(evidence['message_ids_json'], []),
            'ordinal_range': ordinal_range,
            'quote_hash': evidence['quote_hash'],
            'url': evidence['url'] or f"/ledger/{evidence['source_date']}/#{evidence['source_id'].split('#', 1)[-1]}",
        })
    return {'unit_id': unit_id, 'items': items}


@app.get('/api/context-units/{unit_id}', tags=['context'])
def context_unit_detail(unit_id: str, request: Request):
    c = db()
    row = current_context_unit(c, unit_id)
    if not context_row_visible(request, row):
        c.close()
        raise HTTPException(404, '语境块不存在')
    result = context_summary(c, row)
    if getattr(request.state, 'auth_kind', None) == 'session':
        result['locked'] = False
        result['messages'] = _context_messages(c, row, request)
    else:
        result['locked'] = True
        result['messages'] = None
    c.close()
    return result


@app.post('/api/context-unit-messages/{message_id}/like', tags=['context'])
def like_context_unit_message(message_id: int, request: Request):
    """Idempotently like one published context-unit message for the member."""
    user = require_human_session(request)
    c = db()
    try:
        row = c.execute(
            '''SELECT u.id AS unit_id,u.version,u.source_date,u.status,u.visibility,
                      m.ordinal,m.message_id
               FROM context_unit_messages m
               JOIN context_units u
                 ON u.id=m.unit_id AND u.version=m.unit_version
               JOIN (SELECT id,MAX(version) AS version FROM context_units GROUP BY id) latest
                 ON latest.id=u.id AND latest.version=u.version
               WHERE m.message_id=? AND u.status='published' AND u.visibility='public'
               ORDER BY u.source_date DESC,u.id ASC
               LIMIT 1''',
            (message_id,),
        ).fetchone()
        if not row:
            raise HTTPException(404, '语境消息不存在')
        now = datetime.datetime.now(CST).isoformat()
        c.execute('BEGIN IMMEDIATE')
        inserted = c.execute(
            '''INSERT OR IGNORE INTO context_message_likes(
                 unit_id,unit_version,ordinal,message_id,user_id,created_at)
               VALUES(?,?,?,?,?,?)''',
            (row['unit_id'], row['version'], row['ordinal'], row['message_id'], user['id'], now),
        ).rowcount > 0
        likes = c.execute(
            '''SELECT COUNT(*) FROM context_message_likes
               WHERE unit_id=? AND unit_version=? AND ordinal=?''',
            (row['unit_id'], row['version'], row['ordinal']),
        ).fetchone()[0]
        c.commit()
        return {
            'ok': True,
            'message_id': row['message_id'],
            'unit_id': row['unit_id'],
            'ordinal': row['ordinal'],
            'likes': likes,
            'liked': True,
            'already_liked': not inserted,
        }
    except Exception:
        c.rollback()
        raise
    finally:
        c.close()


@app.get('/api/context-search', tags=['context'])
def context_search(
    request: Request,
    q: str = Query(..., min_length=1, max_length=100),
    date: str | None = None,
    limit: int = Query(20, ge=1, le=50),
):
    q = q.strip()
    if not q:
        raise HTTPException(400, 'q 不能为空')
    if date and not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise HTTPException(400, 'date 格式必须是 YYYY-MM-DD')
    c = db()
    rows = []
    try:
        if len(q) >= 3:
            rows = c.execute(
                '''SELECT f.unit_id,f.version,f.date,u.* FROM context_unit_fts f
                   JOIN context_units u ON u.id=f.unit_id AND u.version=f.version
                   JOIN (SELECT id,MAX(version) AS latest_version FROM context_units GROUP BY id) latest
                     ON latest.id=u.id AND latest.latest_version=u.version
                   WHERE f.visibility='public' AND f.status='published'
                   AND context_unit_fts MATCH ? AND (? IS NULL OR f.date=?)
                   ORDER BY f.date DESC,f.unit_id LIMIT ?''',
                (q, date, date, limit),
            ).fetchall()
        else:
            rows = c.execute(
                '''SELECT u.* FROM context_units u
                   JOIN (SELECT id,MAX(version) AS version FROM context_units GROUP BY id) latest
                     ON latest.id=u.id AND latest.version=u.version
                   JOIN context_public_projection p
                     ON p.unit_id=u.id AND p.version=u.version AND p.visibility='public'
                   WHERE u.status='published' AND u.visibility='public'
                     AND (? IS NULL OR u.source_date=?)
                     AND (u.title LIKE ? OR u.summary LIKE ? OR p.public_text LIKE ?)
                   ORDER BY u.source_date DESC,u.id LIMIT ?''',
                (date, date, f'%{q}%', f'%{q}%', f'%{q}%', limit),
            ).fetchall()
    except sqlite3.Error:
        rows = c.execute(
            '''SELECT u.* FROM context_units u
               JOIN (SELECT id,MAX(version) AS version FROM context_units GROUP BY id) latest
                 ON latest.id=u.id AND latest.version=u.version
               JOIN context_public_projection p
                 ON p.unit_id=u.id AND p.version=u.version AND p.visibility='public'
               WHERE u.status='published' AND u.visibility='public'
                 AND (? IS NULL OR u.source_date=?)
                 AND (u.title LIKE ? OR u.summary LIKE ? OR p.public_text LIKE ?)
               ORDER BY u.source_date DESC,u.id LIMIT ?''',
            (date, date, f'%{q}%', f'%{q}%', f'%{q}%', limit),
        ).fetchall()
    items = []
    for row in rows:
        item = context_summary(c, row)
        item['snippet'] = row['summary'] or row['title']
        items.append(item)
    c.close()
    return {'query': q, 'items': items, 'count': len(items)}


# ── 段落评论 API ──
def comment_item(row):
    item = {
        'id': row['id'],
        'user': row['username'],
        'text': row['text'],
        'at': row['created_at'],
        'reply_to': row['reply_to'],
        'via': row['via'],
        'via_label': row['via_label'],
    }
    if 'agent_token_id' in row.keys() and row['agent_token_id']:
        item['agent'] = {
            'id': row['agent_token_id'],
            'display_name': row['agent_display_name'] or row['via'] or 'Agent',
            'capabilities': parse_agent_capabilities(row['agent_capabilities_json']),
            'mentor_username': row['username'],
        }
    if 'status' in row.keys():
        item['status'] = row['status']
    if 'moderation' in row.keys():
        item['moderation'] = parse_moderation(row['moderation'])
    context_unit_id = row['context_unit_id'] if 'context_unit_id' in row.keys() else None
    message_ordinal = row['message_ordinal'] if 'message_ordinal' in row.keys() else None
    parsed = parse_context_anchor(row['anchor'] if 'anchor' in row.keys() else None)
    if context_unit_id or parsed:
        context_unit_id = context_unit_id or parsed[0]
        message_ordinal = message_ordinal or parsed[1]
        item['anchor_kind'] = 'context-message'
        item['context_unit_id'] = context_unit_id
        item['message_ordinal'] = message_ordinal
    return item


@app.get('/api/comments', tags=['agent'])
def comments(request: Request, anchor: str = Query(..., min_length=1)):
    c = db()
    resolve_context_anchor(c, anchor, request)
    rows = c.execute(
        '''SELECT id,username,text,created_at,reply_to,via,via_label,
                  agent_token_id,agent_display_name,agent_capabilities_json,status,moderation,
                  anchor,context_unit_id,context_unit_version,message_ordinal FROM comments
           WHERE anchor=? AND deleted=0 AND status='accepted' ORDER BY created_at,id''',
        (anchor,),
    ).fetchall()
    c.close()
    return {'anchor': anchor, 'count': len(rows), 'items': [comment_item(row) for row in rows]}


@app.get('/api/comments/counts', tags=['agent'])
def comment_counts(date: str):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise HTTPException(400, '日期格式必须是 YYYY-MM-DD')
    c = db()
    rows = c.execute(
        '''SELECT anchor,COUNT(*) AS count FROM comments
           WHERE date=? AND deleted=0 AND status='accepted' GROUP BY anchor ORDER BY anchor''',
        (date,),
    ).fetchall()
    c.close()
    return {'date': date, 'counts': {row['anchor']: row['count'] for row in rows}}


@app.post('/api/comments', tags=['agent'])
def create_comment(req: CommentReq, request: Request):
    anchor = req.anchor.strip()
    text = req.text.strip()
    if not anchor:
        raise HTTPException(400, 'anchor 不能为空')
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', req.date):
        raise HTTPException(400, '日期格式必须是 YYYY-MM-DD')
    if not 1 <= len(text) <= 500:
        raise HTTPException(400, '评论需为 1–500 字')

    user = request.state.user
    now = datetime.datetime.now(CST)
    agent_token_id, agent_display_name, agent_capabilities_json = agent_identity_columns(request)
    c = db()
    try:
        context_info = resolve_context_anchor(c, anchor, request, expected_date=req.date)
        context_unit_id = context_info[0]['id'] if context_info else None
        context_unit_version = context_info[0]['version'] if context_info else None
        message_ordinal = context_info[1]['ordinal'] if context_info else None
        c.execute('BEGIN IMMEDIATE')
        if req.reply_to is not None:
            parent = c.execute(
                'SELECT anchor FROM comments WHERE id=? AND deleted=0',
                (req.reply_to,),
            ).fetchone()
            if not parent or parent['anchor'] != anchor:
                raise HTTPException(400, 'reply_to 必须是同一段落下的有效评论')
        cursor = c.execute(
            '''INSERT INTO comments(
                 anchor,date,user_id,username,text,created_at,deleted,reply_to,via,via_label,
                 agent_token_id,agent_display_name,agent_capabilities_json,status,moderation,
                 context_unit_id,context_unit_version,message_ordinal)
               VALUES(?,?,?,?,?,?,0,?,?,?,?,?,?,'pending',NULL,?,?,?)''',
            (anchor, req.date, user['id'], user['username'], text, now.isoformat(),
             req.reply_to, agent_via(request), request.state.agent_label,
             agent_token_id, agent_display_name, agent_capabilities_json,
             context_unit_id, context_unit_version, message_ordinal),
        )
        comment_id = cursor.lastrowid
        c.commit()
        row = c.execute(
            '''SELECT id,username,text,created_at,reply_to,via,via_label,
                      agent_token_id,agent_display_name,agent_capabilities_json,status,moderation,
                      anchor,context_unit_id,context_unit_version,message_ordinal
               FROM comments WHERE id=?''',
            (comment_id,),
        ).fetchone()
    finally:
        c.close()
    queue_id = enqueue_action(
        DB, actor_user=user['username'], actor_agent=request.state.agent_name,
        action='comment.create', target_type='comment', target_id=comment_id,
        content=text, anchor=anchor,
        metadata={'auth_kind': request.state.auth_kind, 'date': req.date},
    )
    record_agent_action(
        request, 'comment.create', 'comment', comment_id,
        metadata={'anchor': anchor, 'date': req.date, 'reply_to': req.reply_to},
    )
    result = comment_item(row)
    result['moderation_queue_id'] = queue_id
    return result


@app.delete('/api/comments/{comment_id}')
def delete_comment(comment_id: int, request: Request):
    user = request.state.user
    c = db()
    row = c.execute(
        'SELECT id,user_id FROM comments WHERE id=? AND deleted=0',
        (comment_id,),
    ).fetchone()
    if not row:
        c.close()
        raise HTTPException(404, '评论不存在')
    if row['user_id'] != user['id'] and user['role'] != 'admin':
        c.close()
        raise HTTPException(403, '只能删除自己的评论')
    c.execute('UPDATE comments SET deleted=1 WHERE id=?', (comment_id,))
    c.commit()
    c.close()
    return {'ok': True, 'id': comment_id}


# ── 公共划线与点评 ──
ANNOTATION_ANCHOR_RE = re.compile(
    r'^(?P<date>\d{4}-\d{2}-\d{2})#[A-Za-z0-9_-]+-p\d+$'
)


def validate_annotation_location(date, anchor):
    date = date.strip()
    anchor = anchor.strip()
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise HTTPException(400, '日期格式必须是 YYYY-MM-DD')
    match = ANNOTATION_ANCHOR_RE.fullmatch(anchor)
    if not match or match.group('date') != date:
        raise HTTPException(400, 'anchor 必须是同一期的 YYYY-MM-DD#section-pN')
    return date, anchor


def validate_annotation_quote(date, selected_quote):
    if not selected_quote:
        return
    path = GOVERNED_LEDGER_DIR / f'{date}.json'
    if not path.is_file():
        raise HTTPException(404, '该期治理日报不存在，无法校验划线原文')
    data = load_governed_ledger(path)
    strings = []
    stack = [data]
    while stack:
        value = stack.pop()
        if isinstance(value, dict):
            stack.extend(value.values())
        elif isinstance(value, list):
            stack.extend(value)
        elif isinstance(value, str):
            strings.append(value)
    normalized_quote = re.sub(r'\s+', ' ', selected_quote).strip()
    if not any(
        selected_quote in value or normalized_quote in re.sub(r'\s+', ' ', value)
        for value in strings
    ):
        raise HTTPException(400, 'quote 必须是该期日报中的原文子串')


def annotation_select(where_clause):
    return f'''SELECT a.*,COALESCE(NULLIF(u.display_name,''),a.username) user_name,
                      u.role user_role,
                      COALESCE((SELECT m.avatar FROM members m WHERE m.username=a.username LIMIT 1),
                               (SELECT m.avatar FROM members m WHERE m.display=u.display_name LIMIT 1)) avatar
               FROM annotations a JOIN users u ON u.id=a.user_id
               WHERE {where_clause}'''


def annotation_item(row, include_private=False):
    item = {
        'id': row['id'], 'user': row['user_name'], 'avatar': row['avatar'],
        'anchor': row['anchor'], 'quote': row['quote'], 'note': row['note'],
        'kind': row['kind'], 'at': row['created_at'],
        'is_admin': row['user_role'] == 'admin',
    }
    if include_private:
        item.update({
            'date': row['date'], 'visibility': row['visibility'],
            'status': row['status'], 'updated_at': row['updated_at'],
            'moderation': parse_moderation(row['moderation']),
        })
    return item


def audit_direct(request, action, target, reason, decision='accepted'):
    user = request.state.user
    now = datetime.datetime.now(CST).isoformat()
    c = db()
    c.execute(
        '''INSERT INTO audit(ts,actor_user,actor_agent,action,target,decision,reason,queue_id)
           VALUES(?,?,?,?,?,?,?,NULL)''',
        (now, user['username'], request.state.agent_name, action, target, decision, reason),
    )
    c.commit(); c.close()


@app.post('/api/annotations', tags=['agent'])
def create_annotation(req: AnnotationCreateReq, request: Request):
    date, anchor = validate_annotation_location(req.date, req.anchor)
    selected_quote = req.quote.strip()
    validate_annotation_quote(date, selected_quote)
    note = req.note.strip()
    if req.kind == 'note' and not note:
        raise HTTPException(400, 'note 类型必须填写点评内容')
    user = request.state.user
    now = datetime.datetime.now(CST).isoformat()
    direct = req.kind == 'highlight' and not note
    moderation = json.dumps({
        'source': 'gatekeeper', 'rules': {'decision': 'accepted', 'checks': {'content': 'empty'}},
        'llm': 'not_run', 'decision': 'accepted', 'reason': '纯划线无点评文本，直接通过',
        'decided_at': now,
    }, ensure_ascii=False) if direct else None
    c = db()
    cursor = c.execute(
        '''INSERT INTO annotations(user_id,username,date,anchor,quote,note,kind,visibility,
                                   created_at,updated_at,deleted,moderation,status)
           VALUES(?,?,?,?,?,?,?,?,?,?,0,?,?)''',
        (user['id'], user['username'], date, anchor, selected_quote, note, req.kind,
         req.visibility, now, now, moderation, 'accepted' if direct else 'pending'),
    )
    annotation_id = cursor.lastrowid
    c.commit(); c.close()
    queue_id = None
    if direct:
        audit_direct(request, 'annotation.create', f'annotation:{annotation_id}', '纯划线直接通过')
    else:
        queue_id = enqueue_action(
            DB, actor_user=user['username'], actor_agent=request.state.agent_name,
            action='annotation.create', target_type='annotation', target_id=annotation_id,
            content=note, anchor=anchor,
            metadata={'auth_kind': request.state.auth_kind, 'date': date},
        )
    c = db()
    row = c.execute(annotation_select('a.id=?'), (annotation_id,)).fetchone()
    c.close()
    record_agent_action(
        request, 'annotation.create', 'annotation', annotation_id,
        metadata={'date': date, 'anchor': anchor, 'kind': req.kind},
    )
    result = annotation_item(row, include_private=True)
    result['moderation_queue_id'] = queue_id
    return result


@app.get('/api/annotations')
def list_annotations(date: str = Query(..., min_length=10, max_length=10)):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise HTTPException(400, '日期格式必须是 YYYY-MM-DD')
    c = db()
    rows = c.execute(
        annotation_select("a.date=? AND a.visibility='public' AND a.status='accepted' AND a.deleted=0") +
        ' ORDER BY a.created_at,a.id',
        (date,),
    ).fetchall()
    c.close()
    counts = collections.Counter(row['anchor'] for row in rows)
    return {'items': [annotation_item(row) for row in rows], 'counts': dict(counts)}


@app.get('/api/annotations/mine')
def my_annotations(request: Request, date: str = Query(..., min_length=10, max_length=10)):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise HTTPException(400, '日期格式必须是 YYYY-MM-DD')
    c = db()
    rows = c.execute(
        annotation_select('a.user_id=? AND a.date=? AND a.deleted=0') +
        ' ORDER BY a.created_at,a.id',
        (request.state.user['id'], date),
    ).fetchall()
    c.close()
    return {'items': [annotation_item(row, include_private=True) for row in rows]}


@app.get('/api/annotations/mine/export.md')
def export_my_annotations(request: Request):
    c = db()
    rows = c.execute(
        annotation_select('a.user_id=? AND a.deleted=0') +
        ' ORDER BY a.date DESC,a.created_at,a.id',
        (request.state.user['id'],),
    ).fetchall()
    c.close()
    lines = ['# 我的划线与点评', '']
    current_date = None
    for row in rows:
        if row['date'] != current_date:
            current_date = row['date']
            lines.extend([f'## {current_date}', ''])
        labels = [row['kind'], row['visibility'], row['status']]
        lines.extend([f"### {row['anchor']} · {' / '.join(labels)}", ''])
        if row['quote']:
            lines.extend([f"> {row['quote'].replace(chr(10), chr(10) + '> ')}", ''])
        if row['note']:
            lines.extend([row['note'], ''])
        moderation = parse_moderation(row['moderation']) or {}
        if row['status'] == 'rejected' and moderation.get('reason'):
            lines.extend([f"审核：{moderation['reason']}", ''])
    content = '\n'.join(lines).rstrip() + '\n'
    return Response(
        content=content, media_type='text/markdown; charset=utf-8',
        headers={'Content-Disposition': 'attachment; filename="ai325-annotations.md"'},
    )


@app.patch('/api/annotations/{annotation_id}')
def update_annotation(annotation_id: int, req: AnnotationUpdateReq, request: Request):
    if req.note is None and req.visibility is None:
        raise HTTPException(400, '至少提供 note 或 visibility')
    user = request.state.user
    c = db()
    row = c.execute('SELECT * FROM annotations WHERE id=? AND deleted=0', (annotation_id,)).fetchone()
    if not row:
        c.close(); raise HTTPException(404, '划线不存在')
    if row['user_id'] != user['id']:
        c.close(); raise HTTPException(403, '只能修改自己的划线')
    note = row['note'] if req.note is None else req.note.strip()
    visibility = row['visibility'] if req.visibility is None else req.visibility
    if row['kind'] == 'note' and not note:
        c.close(); raise HTTPException(400, 'note 类型必须填写点评内容')
    note_changed = req.note is not None and note != row['note']
    direct = note_changed and row['kind'] == 'highlight' and not note
    now = datetime.datetime.now(CST).isoformat()
    if note_changed:
        status = 'accepted' if direct else 'pending'
        moderation = json.dumps({
            'source': 'gatekeeper', 'rules': {'decision': 'accepted', 'checks': {'content': 'empty'}},
            'llm': 'not_run', 'decision': 'accepted', 'reason': '纯划线无点评文本，直接通过',
            'decided_at': now,
        }, ensure_ascii=False) if direct else None
    else:
        status, moderation = row['status'], row['moderation']
    c.execute(
        '''UPDATE annotations SET note=?,visibility=?,updated_at=?,status=?,moderation=? WHERE id=?''',
        (note, visibility, now, status, moderation, annotation_id),
    )
    c.commit(); c.close()
    queue_id = None
    if note_changed:
        if direct:
            audit_direct(request, 'annotation.update', f'annotation:{annotation_id}', '点评已清空，纯划线直接通过')
        else:
            queue_id = enqueue_action(
                DB, actor_user=user['username'], actor_agent=request.state.agent_name,
                action='annotation.update', target_type='annotation', target_id=annotation_id,
                content=note, anchor=row['anchor'],
                metadata={'auth_kind': request.state.auth_kind, 'date': row['date']},
            )
    c = db()
    updated = c.execute(annotation_select('a.id=?'), (annotation_id,)).fetchone()
    c.close()
    result = annotation_item(updated, include_private=True)
    result['moderation_queue_id'] = queue_id
    return result


@app.delete('/api/annotations/{annotation_id}')
def delete_annotation(annotation_id: int, request: Request):
    user = request.state.user
    c = db()
    row = c.execute('SELECT user_id FROM annotations WHERE id=? AND deleted=0', (annotation_id,)).fetchone()
    if not row:
        c.close(); raise HTTPException(404, '划线不存在')
    is_session_admin = request.state.auth_kind == 'session' and user['role'] == 'admin'
    if row['user_id'] != user['id'] and not is_session_admin:
        c.close(); raise HTTPException(403, '只能删除自己的划线')
    now = datetime.datetime.now(CST).isoformat()
    c.execute('UPDATE annotations SET deleted=1,updated_at=? WHERE id=?', (now, annotation_id))
    c.commit(); c.close()
    return {'ok': True, 'id': annotation_id}


# ── 实时治理 / 作者活动 ──
@app.get('/api/moderation/queue')
def moderation_queue(request: Request):
    require_admin(request)
    return {'items': list_pending_moderation(DB)}


@app.post('/api/moderation/{queue_id}/decide')
def moderation_decide(queue_id: int, req: ModerationDecisionReq, request: Request):
    admin = require_admin(request)
    try:
        return decide_moderation(
            DB, queue_id, req.decision, req.reason.strip(), admin['username'],
        )
    except KeyError as exc:
        raise HTTPException(404, '审核项不存在') from exc


@app.get('/api/me/activity')
def my_activity(request: Request):
    user = request.state.user
    is_agent = request.state.auth_kind == 'agent'
    c = db()
    if is_agent:
        comments_rows = c.execute(
            '''SELECT id,anchor,date,text,created_at,status,moderation,via,via_label,
                      agent_token_id,agent_display_name,agent_capabilities_json
               FROM comments WHERE user_id=? AND agent_token_id=? AND deleted=0
               ORDER BY created_at DESC,id DESC''',
            (user['id'], request.state.agent_token_id),
        ).fetchall()
        submission_rows = c.execute(
            '''SELECT s.id,e.slug event_slug,e.title event_title,s.title,s.note,s.created_at,
                      s.status,s.moderation,s.via,s.via_label,s.agent_token_id,
                      s.agent_display_name,s.agent_capabilities_json
               FROM submissions s JOIN events e ON e.id=s.event_id
               WHERE s.user_id=? AND s.agent_token_id=?
               ORDER BY s.created_at DESC,s.id DESC''',
            (user['id'], request.state.agent_token_id),
        ).fetchall()
        vote_rows = c.execute(
            '''SELECT v.submission_id,s.title submission_title,v.created_at,v.status,v.moderation
               FROM agent_submission_votes v JOIN submissions s ON s.id=v.submission_id
               WHERE v.user_id=? AND v.agent_token_id=?
               ORDER BY v.created_at DESC,v.submission_id DESC''',
            (user['id'], request.state.agent_token_id),
        ).fetchall()
    else:
        comments_rows = c.execute(
            '''SELECT id,anchor,date,text,created_at,status,moderation,via,via_label
               FROM comments WHERE user_id=? AND deleted=0 ORDER BY created_at DESC,id DESC''',
            (user['id'],),
        ).fetchall()
        submission_rows = c.execute(
            '''SELECT s.id,e.slug event_slug,e.title event_title,s.title,s.note,s.created_at,
                      s.status,s.moderation,s.via,s.via_label
               FROM submissions s JOIN events e ON e.id=s.event_id
               WHERE s.user_id=? ORDER BY s.created_at DESC,s.id DESC''',
            (user['id'],),
        ).fetchall()
        vote_rows = c.execute(
            '''SELECT v.submission_id,s.title submission_title,v.created_at,v.status,v.moderation
               FROM submission_votes v JOIN submissions s ON s.id=v.submission_id
               WHERE v.user_id=? ORDER BY v.created_at DESC,v.submission_id DESC''',
            (user['id'],),
        ).fetchall()
    c.close()
    return {
        'comments': [{
            'id': row['id'], 'anchor': row['anchor'], 'date': row['date'],
            'text': row['text'], 'created_at': row['created_at'],
            'status': row['status'], 'moderation': parse_moderation(row['moderation']),
            'via': row['via'], 'via_label': row['via_label'],
            'vault': 'agent' if is_agent else 'human',
        } for row in comments_rows],
        'submissions': [{
            'id': row['id'], 'event_slug': row['event_slug'],
            'event_title': row['event_title'], 'title': row['title'],
            'note': row['note'], 'created_at': row['created_at'],
            'status': row['status'], 'moderation': parse_moderation(row['moderation']),
            'via': row['via'], 'via_label': row['via_label'],
            'vault': 'agent' if is_agent else 'human',
        } for row in submission_rows],
        'votes': [{
            'submission_id': row['submission_id'],
            'submission_title': row['submission_title'],
            'created_at': row['created_at'], 'status': row['status'],
            'moderation': parse_moderation(row['moderation']),
            'vault': 'agent' if is_agent else 'human',
        } for row in vote_rows],
    }

# ── 数据导入 ──
ZSTD_PAT = re.compile(r'^[0-9a-fA-F]{40,}$')
def zdec(h):
    try:
        p = subprocess.run(['zstd','-d','--stdout','-q'], input=bytes.fromhex(h.strip()), capture_output=True, timeout=5)
        return p.stdout.decode('utf-8','replace') if p.returncode == 0 else None
    except: return None

NAME_OVERRIDES = {
    'sunwuyuan521':'孙务远','wxid_fbpvnhvoys9322':'庄康发','wxid_u8t9fp5bvlrv22':'张',
    'wxid_suwtm32fe0cf12':'湫天','fanzhenhua666':'范振华(院长)','wangchao6018':'超儿',
    'gbw311':'高博文 owen','wxid_ylsq6b288a3o22':'明野','qq514886787':'Tim','wongkeng':'队长 Christopher',
    'zhongtw':'钟天炜','wxid_b1nrtc0hv4nl22':'Sean.Wang','win591':'大魏',
    'wxid_hfmz637c9ore22':'阿豪','qing943336':'聂燕青','wxid_mx87qq2llfkj22':'李文涛',
    'wxid_a813aw2j6e1922':'中高职教育建设','hawklighting':'徐志剑（灯哥）',
    'wxid_shmlhxydlcgz12':'Mr. Tang（老唐）','wxid_m4tfwawxaheh22':'阿彬SEO-GEO',
    'wxid_nowlwctf8h0n22':'广州-Anna','wxid_57ey8radnixo11':'江飞',
    'wxid_vxu127p2u7qz22':'丁玄','wxid_rutwda2ixdfq22':'星星之火',
    # Sun 已核验的称呼画像样例；仍以 wxid 为身份锚，不与其他账号自动归户。
    'wxid_09cec05iemwv12':'泽老师',
}

MEMBER_RAW_RE = re.compile(
    r'^(?:wxid_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|gh_[A-Za-z0-9_-]+|[0-9]{5,})$',
    re.I,
)
MEMBER_CITY_PREFIX_RE = re.compile(r'^[\u3400-\u9fff]{2,8}[-－—–]\s*')
MEMBER_ROLE_CALL_RE = re.compile(
    r'([\u3400-\u9fffA-Za-z][\u3400-\u9fffA-Za-z0-9·_-]{0,12}?(?:老师|哥|姐|总|叔|姨|老板|院长|队长|sir))'
)
MEMBER_SELF_CALL_RE = re.compile(
    r'(?:大家(?:好)?[，,\s]*(?:我叫|我是)|大家(?:可以)?叫我|你们叫我|叫我|我叫|我是)'
    r'\s*([\u3400-\u9fffA-Za-z][\u3400-\u9fffA-Za-z0-9·_-]{0,20}?)(?=[，,。.!！?？\s]|$)'
)
MEMBER_AT_RE = re.compile(r'@([^\s@，,。.!！?？:：()（）\[\]]{1,32})')
MEMBER_NOISE_CALLS = {
    '大家', '各位', '朋友', '一个', '一名', '这个', '那个', '自己', '系统', '领域',
    'chatroom', 'cdn', 'view', 'false', 'true', '的领域', '做协议', '共同语义',
}


def _member_clean(value: object) -> str:
    text = ''.join(
        ch for ch in str(value or '')
        if unicodedata.category(ch) not in {'Cc', 'Cf'}
    )
    return ' '.join(text.strip().split())


def _member_alias_key(value: object) -> str:
    return MEMBER_CITY_PREFIX_RE.sub('', _member_clean(value), count=1).casefold()


def _member_is_raw(value: object) -> bool:
    candidate = _member_clean(value)
    return not candidate or candidate in {'?', '未知', '未识别', '群友'} or bool(MEMBER_RAW_RE.fullmatch(candidate))


def _member_is_punctuation_only(value: object) -> bool:
    candidate = _member_clean(value)
    return bool(candidate) and not any(ch.isalnum() or '\u3400' <= ch <= '\u9fff' for ch in candidate)


def _member_display_candidate(value: object, username: object = '') -> str:
    candidate = _member_clean(value)
    user = _member_clean(username)
    if not candidate or candidate.casefold() in {'?', 'unknown', 'none', 'null'}:
        return ''
    if candidate.casefold() == user.casefold() and re.fullmatch(r'[A-Za-z][A-Za-z0-9_.-]*', candidate):
        return ''
    if _member_is_raw(candidate) or _member_is_punctuation_only(candidate):
        return ''
    return candidate[:80]


def _member_masked_username(username: object) -> str:
    candidate = _member_clean(username)
    tail = re.sub(r'[^A-Za-z0-9]', '', candidate)[-4:] or '未知'
    return f'群友·{tail}'


def _member_json_list(value: object) -> list:
    try:
        parsed = json.loads(value) if isinstance(value, str) else value
    except (TypeError, json.JSONDecodeError):
        return []
    return parsed if isinstance(parsed, list) else []


def _member_iso(value: object) -> str:
    try:
        timestamp = int(value or 0)
        if timestamp > 10_000_000_000:
            timestamp //= 1000
        return datetime.datetime.fromtimestamp(timestamp, CST).isoformat(timespec='seconds') if timestamp else ''
    except (TypeError, ValueError, OSError, OverflowError):
        return ''


def _member_called_candidate(value: object) -> str:
    candidate = _member_clean(value).strip(' ，,。.!！?？:：;；')
    if len(candidate) < 2 or len(candidate) > 10:
        return ''
    if candidate.casefold() in MEMBER_NOISE_CALLS or _member_is_raw(candidate):
        return ''
    if any(token in candidate for token in ('因为', '怎么', '什么', '一个', '一名', '的领域', '场景下')):
        return ''
    if _member_is_punctuation_only(candidate):
        return ''
    return candidate


def _member_called_is_stable(item: dict) -> bool:
    sources = item.get('sources') or []
    return bool(
        'Sun 已验证样例' in sources
        or (int(item.get('count') or 0) >= 2 and any('称呼' in str(source) for source in sources))
    )


def _member_called_add(bucket: dict, sender: str, name: object, row, reason: str) -> None:
    candidate = _member_called_candidate(name)
    if not sender or sender == '?' or not candidate:
        return
    per_sender = bucket.setdefault(sender, {})
    item = per_sender.setdefault(candidate.casefold(), {
        'name': candidate, 'count': 0, 'first_seen': '', 'last_seen': '',
        'sources': [], 'evidence': [],
    })
    item['count'] += 1
    at = _member_iso(row['create_time'] if 'create_time' in row.keys() else 0) or str(row['cst'] or '')
    if at and (not item['first_seen'] or at < item['first_seen']):
        item['first_seen'] = at
    if at and at > item['last_seen']:
        item['last_seen'] = at
    if reason not in item['sources']:
        item['sources'].append(reason)
    if len(item['evidence']) < 5:
        item['evidence'].append({'at': at, 'reason': reason, 'text': _member_clean(row['content'])[:500]})


def _member_collect_called_names(rows: list) -> tuple[dict[str, list[dict]], dict[str, list[dict]]]:
    """Extract auditable called-name evidence without merging wxids."""
    display_by_sender: dict[str, set[str]] = collections.defaultdict(set)
    for row in rows:
        sender = _member_clean(row['sender']) or '?'
        candidate = _member_display_candidate(NAME_OVERRIDES.get(sender) or row['sender_name'], sender)
        if candidate:
            display_by_sender[sender].add(candidate)
    name_to_senders: dict[str, set[str]] = collections.defaultdict(set)
    for sender, names in display_by_sender.items():
        for name in names:
            name_to_senders[_member_alias_key(name)].add(sender)

    called: dict[str, dict[str, dict]] = {}
    unresolved: dict[str, list[dict]] = collections.defaultdict(list)
    for row in rows:
        sender = _member_clean(row['sender']) or '?'
        text = _member_clean(clean_wechat_content(str(row['content'] or '')))
        if not text:
            continue
        # 转发/引用块里的署名不是当前发言者的称呼证据，不能串到当前 wxid。
        if '群聊的聊天记录' in text or '[聊天记录]' in text:
            continue
        for match in MEMBER_SELF_CALL_RE.finditer(text):
            _member_called_add(called, sender, match.group(1), row, '自我介绍/自称')
        for match in MEMBER_AT_RE.finditer(text):
            target = _member_clean(match.group(1))
            target_ids = name_to_senders.get(_member_alias_key(target), set())
            if not target_ids:
                unresolved[target].append({'sender': sender, 'at': _member_iso(row['create_time']), 'text': text[:500], 'reason': '未能从 @ 目标反查 wxid'})
                continue
            after = text[match.end():match.end() + 32]
            role = MEMBER_ROLE_CALL_RE.search(after)
            if role and len(target_ids) == 1:
                for target_id in target_ids:
                    _member_called_add(called, target_id, role.group(1), row, ' @目标后称呼')
        for role in MEMBER_ROLE_CALL_RE.finditer(text):
            term = _member_called_candidate(role.group(1))
            if not term:
                continue
            base = re.sub(r'(老师|哥|姐|总|叔|姨|老板|院长|队长|sir)$', '', term, flags=re.I)
            candidates = set(name_to_senders.get(_member_alias_key(base), set()))
            if not candidates and len(base) >= 1:
                for known, ids in name_to_senders.items():
                    if known.startswith(base.casefold()):
                        candidates.update(ids)
            if len(candidates) == 1:
                _member_called_add(called, next(iter(candidates)), term, row, '回复/角色称呼')
            elif not candidates:
                unresolved[term].append({'sender': sender, 'at': _member_iso(row['create_time']), 'text': text[:500], 'reason': '稳定称呼尚无唯一 wxid'})
    # Sun 已验证的阿泽样例先作为可审计事实落在该 wxid 上，不触发别名归户。
    for row in rows:
        if _member_clean(row['sender']) == 'wxid_09cec05iemwv12':
            _member_called_add(called, 'wxid_09cec05iemwv12', '泽老师', row, 'Sun 已验证样例')
            _member_called_add(called, 'wxid_09cec05iemwv12', '阿泽', row, 'Sun 已验证样例')
            break
    normalized = {}
    for sender, values in called.items():
        normalized[sender] = sorted(values.values(), key=lambda item: (-int(item['count']), item['name']))
    return normalized, dict(unresolved)

# ── 微信 XML 噪声清洗 ──
_TAG_RE = re.compile(r'<[^>]+>')
_BLOCK_TAG_RE = re.compile(
    r'<(?:br\s*/?|/p\s*|/div\s*|/li\s*|/datadesc\s*|/dataitem\s*)>',
    re.I,
)
_LONG_REPEAT_MIN_CHARS = 80
_CHAT_RECORD_TITLES = ('群聊的聊天记录', '聊天记录', '收藏的聊天记录')

_WECHAT_PLACEHOLDER_RE = re.compile(
    r'\[(?:图片|表情|动画表情|视频|语音|链接|文件|小程序|音乐|位置|转账|红包|名片|引用|聊天记录|接龙|拍一拍[^\]]*|表情包[^\]]*)\]\s*'
)
_WECHAT_URL_RE = re.compile(r'https?://\S+')
# 纯计数+URL 残渣行：数字簇开头，至多跟一段 12 字内的无标点文字（如「51 0 0 0 0 4 大麦AI笔记」）
_WECHAT_NOISE_LINE_RE = re.compile(r'^\s*\d+(?:[\s\d]*\d)?(?:\s+[^\s。！？!?，,；;]{1,12})?\s*$')
_WECHAT_NOISE_SPEAKER_RE = re.compile(r'^[@＠.+\-]{1,3}$')
# 行首计数残渣 + 行尾数字/ID 残渣（微信视频号/文件元数据尾巴）
_WECHAT_LEAD_COUNT_RE = re.compile(r'^\s*\d+(?:[\s\d_]*\d)?(?:\s+[^\s。！？!?，,；;]{1,12})?\s+')
_WECHAT_TRAIL_NOISE_RE = re.compile(r'(?:\s+(?:[\d.\-]+|[a-z0-9_]{2,})){2,}$')
# 行内计数/ID 簇（51 0 0 0 0 4 大麦AI笔记 → 大麦AI笔记；不锚行尾，防中文日期正文）
_WECHAT_INLINE_COUNT_RE = re.compile(r'(?:\s+(?:[\d.\-]+|[a-z0-9_]{2,})){2,}')
# 日期/时间戳残渣
_WECHAT_DATE_RE = re.compile(r'\s+\d{4}-\d{2}-\d{2}(?:\s+\d{2}:\d{2}(?::\d{2})?)?')
# 重复说话人前缀（转发链：星星之火: 庄康发: 正文 → 庄康发: 正文；任意位置）
_WECHAT_LEAD_SPEAKER_DUP_RE = re.compile(r'[^\s:：]{1,14}[:：]\s*(?=[^\s:：]{1,14}[:：])')
# 行内对话流残渣（微信引用投影：高博文😈: 要 超儿: ！！！要 → 保留最后说话人）
_WECHAT_DIALOG_FLOW_RE = re.compile(r'[^\s:：]{1,14}[:：]\s*[^\s:：]{1,16}\s+(?=[^\s:：]{1,14}[:：])')
# 纯标点说话人（。: 别人 fork 被你找到了吗）
_WECHAT_PUNCT_SPEAKER_RE = re.compile(r'[。，、；：]\s*[:：]\s*')
# @chatroom 引用元数据（@chatroom wxid 名字）
_WECHAT_CHATROOM_RE = re.compile(r'@chatroom\s+\S+\s+[^\s。！？]{1,20}')
# 消息尾部元数据（时间戳 名字 session@chatroom）
_WECHAT_CHATROOM_TAIL_RE = re.compile(r'\s+\d{9,11}\s+[^\s]+?\s+\S+@chatroom\s*$')
# openim 系统公告前缀 + @所有人
_WECHAT_OPENIM_RE = re.compile(r'\d+@openim[:：]?\s*|@所有人')
# 管道分隔短 base64 变体（N0_V1_ZciLzZEK|v1_kXHN63Ds）
_WECHAT_PIPE_TOKEN_RE = re.compile(r'\S{10,}\|\S{2,}')
# 长 hash 尾 token（bd53fc470ca0d573...）
_WECHAT_HASH_TAIL_RE = re.compile(r'\s+[a-z0-9]{16,}\s*$')
# 裸图片扩展名段（宰治: jpg）
_WECHAT_BARE_IMG_SEG_RE = re.compile(r'[^\s:：]{1,14}[:：]\s*(?:jpe?g|png|gif|webp)\s*')
# view 计数残渣（view 51 / view 57 false -1 ...）
_WECHAT_VIEW_COUNT_RE = re.compile(r'\s*view\s+\d+(?:\s+[\d\-]+)*')
# base64 残渣（eyJ... 微信消息包）
_WECHAT_B64_RE = re.compile(r'\beyJ[A-Za-z0-9+/=_]{20,}\b')
# 「当前版本不支持展示该内容」
_WECHAT_UNSUPPORTED_RE = re.compile(r'当前(?:微信)?版本不支持展示该内容，请升级至最新版本。?')
# 文本转发头「群聊的聊天记录」（排除「（引用 X）」引用上下文）
_WECHAT_CHATRECORD_HEAD_RE = re.compile(r'(?<![\u4e00-\u9fff）)」】"])群聊的聊天记录\s*')
# 文件转发链行：名: 文件名.扩展名（无正文）
_WECHAT_FILE_FWD_LINE_RE = re.compile(r'^.{1,14}[:：]\s*[^\s。]{2,50}\.(?:html?|pdf|epub|zip|docx?|pptx?|md|xlsx?|txt|jpe?g|png|gif|webp)(?:\s|$)')
# 行内连续文件转发段（同一行多段「名: 文件.ext」）
_WECHAT_FILE_FWD_SEG_RE = re.compile(r'(?:[^\s:：]{1,14}[:：]\s*[^\s。]{2,50}\.(?:html?|pdf|epub|zip|docx?|pptx?|md|xlsx?|txt|jpe?g|png|gif|webp)\s*)+')
# 长 base64 特征 token（含数字+小写，URL 已剥后；纯字母/中文长文不受影响）
_WECHAT_LONG_TOKEN_RE = re.compile(r'(?=.*\d)(?=.*[a-z])[A-Za-z0-9+/=_|.-]{40,}')
# 行首 uuid / 下划线数字 ID 残渣
_WECHAT_LEAD_ID_RE = re.compile(r'^\s*(?:[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|_\d[\d_]*)\s*')
# 说话人 + 纯计数段（宰治: 19 0 0 0 0 0 1788003815 0）
_WECHAT_SPEAKER_COUNT_SEG_RE = re.compile(r'[^\s:：]{1,14}[:：]\s*\d[\d\s]*')
# 手机号残渣
_WECHAT_PHONE_RE = re.compile(r'1[3-9]\d{9}')


def _scrub_wechat_artifacts(value):
    """剥收藏转发的三类变体残渣：图片/表情占位、URL、纯计数行；剥后空行丢弃。

    覆盖真实线上形态：文件转发链（星星之火: xxx.html）、行首计数（51 0 0 0 0 4 大麦AI笔记）、
    view 计数（view 51 / view 57 false -1）、base64 消息包（eyJ...）、
    「当前版本不支持展示该内容」、尾部数字/ID 残渣、手机号。
    """
    text = str(value or '')
    text = _WECHAT_URL_RE.sub(' ', text)
    text = _WECHAT_PLACEHOLDER_RE.sub('', text)
    text = _WECHAT_CHATRECORD_HEAD_RE.sub('', text)
    text = _WECHAT_B64_RE.sub(' ', text)
    text = _WECHAT_LONG_TOKEN_RE.sub(' ', text)
    text = _WECHAT_PIPE_TOKEN_RE.sub(' ', text)
    text = _WECHAT_CHATROOM_RE.sub(' ', text)
    text = _WECHAT_CHATROOM_TAIL_RE.sub(' ', text)
    text = _WECHAT_OPENIM_RE.sub(' ', text)
    text = _WECHAT_UNSUPPORTED_RE.sub('', text)
    text = _WECHAT_VIEW_COUNT_RE.sub(' ', text)
    text = _WECHAT_FILE_FWD_SEG_RE.sub(' ', text)
    text = _WECHAT_BARE_IMG_SEG_RE.sub(' ', text)
    lines = [' '.join(line.split()) for line in text.split('\n')]
    kept = []
    for line in lines:
        if not line:
            continue
        had_cluster = bool(_WECHAT_INLINE_COUNT_RE.search(line))
        line = _WECHAT_INLINE_COUNT_RE.sub(' ', line)
        line = _WECHAT_LEAD_SPEAKER_DUP_RE.sub('', line)
        line = _WECHAT_DIALOG_FLOW_RE.sub('', line)
        line = _WECHAT_PUNCT_SPEAKER_RE.sub('', line)
        line = _WECHAT_LEAD_ID_RE.sub('', line)
        line = _WECHAT_LEAD_COUNT_RE.sub('', line)
        line = _WECHAT_SPEAKER_COUNT_SEG_RE.sub('', line)
        line = _WECHAT_TRAIL_NOISE_RE.sub('', line)
        line = _WECHAT_HASH_TAIL_RE.sub('', line)
        line = _WECHAT_DATE_RE.sub('', line)
        line = _WECHAT_PHONE_RE.sub('', line)
        line = ' '.join(line.split())
        if had_cluster and len(line) <= 14 and not re.search(r'[，。！？；：、]', line):
            continue  # 剥计数簇后只剩短名（转发元数据残留），整行丢弃
        if not line or _WECHAT_NOISE_LINE_RE.match(line):
            continue
        if _WECHAT_FILE_FWD_LINE_RE.match(line):
            continue  # 文件转发链行（名: 文件.ext）无正文，整体丢弃
        kept.append(line)
    return '\n'.join(kept).strip()


def _scrub_speaker(value):
    """匿名转发说话人（@/空/纯符号）不输出「@: 」前缀。"""
    speaker = str(value or '').strip()
    if not speaker or _WECHAT_NOISE_SPEAKER_RE.match(speaker):
        return ''
    return speaker



def _decode_wechat_envelope(value):
    """Decode an escaped XML envelope without unescaping an already-live XML tree."""
    text = str(value or '')
    for _ in range(4):
        if any(marker in text for marker in ('<msg', '<appmsg', '<recorditem', '<recordinfo')):
            break
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    return text


def _plain_wechat_text(value, *, keep_newlines=False):
    text = str(value or '')
    for _ in range(4):
        decoded = html.unescape(text)
        if decoded == text:
            break
        text = decoded
    text = text.replace('<![CDATA[', '').replace(']]>', '')
    text = _BLOCK_TAG_RE.sub('\n', text)
    text = _TAG_RE.sub(' ', text).replace('\r', '\n')
    lines = [' '.join(line.split()) for line in text.split('\n')]
    lines = [line for line in lines if line]
    if keep_newlines:
        return '\n'.join(lines)
    return ' '.join(lines)


def _paragraph_compare_key(value):
    key = unicodedata.normalize('NFKC', str(value or ''))
    key = ''.join(char for char in key if unicodedata.category(char) not in {'Cc', 'Cf'})
    return re.sub(r'\s+', ' ', key).strip()


def _dedupe_inline_long_repetition(value, *, min_chars=_LONG_REPEAT_MIN_CHARS):
    """Collapse a paragraph that consists entirely of 2..16 exact long copies."""
    text = _paragraph_compare_key(value)
    max_copies = min(16, len(text) // max(1, min_chars))
    for copies in range(max_copies, 1, -1):
        for separator in (' ', ''):
            payload_length = len(text) - len(separator) * (copies - 1)
            if payload_length <= 0 or payload_length % copies:
                continue
            width = payload_length // copies
            chunks = []
            position = 0
            valid = True
            for index in range(copies):
                chunks.append(text[position:position + width])
                position += width
                if index < copies - 1:
                    if text[position:position + len(separator)] != separator:
                        valid = False
                        break
                    position += len(separator)
            first = chunks[0] if chunks else ''
            if (
                valid
                and position == len(text)
                and len(re.sub(r'\s+', '', first)) >= min_chars
                and all(chunk == first for chunk in chunks[1:])
            ):
                return first
    return str(value or '')


def _dedupe_long_paragraphs(value, *, min_chars=_LONG_REPEAT_MIN_CHARS):
    """Keep the first copy of an identical long paragraph within one message."""
    paragraphs = [' '.join(part.split()) for part in re.split(r'\n+', str(value or ''))]
    seen = set()
    kept = []
    for paragraph in paragraphs:
        if not paragraph:
            continue
        paragraph = _dedupe_inline_long_repetition(paragraph, min_chars=min_chars)
        key = _paragraph_compare_key(paragraph)
        if len(re.sub(r'\s+', '', key)) >= min_chars:
            if key in seen:
                continue
            seen.add(key)
        kept.append(paragraph)
    return '\n'.join(kept)


def _xml_local_name(element):
    return str(element.tag).rsplit('}', 1)[-1]


def _xml_child_text(element, name):
    for child in element.iter():
        if _xml_local_name(child) == name:
            return ''.join(child.itertext())
    return ''


def _recordinfo_root(xml):
    match = re.search(r'<recorditem\b[^>]*>([\s\S]*?)</recorditem>', xml, re.I)
    if not match:
        return None
    record = match.group(1).strip()
    if record.startswith('<![CDATA[') and record.endswith(']]>'):
        record = record[9:-3].strip()
    for _ in range(4):
        if '<recordinfo' in record:
            break
        decoded = html.unescape(record)
        if decoded == record:
            break
        record = decoded
    start = record.find('<recordinfo')
    end = record.rfind('</recordinfo>')
    if start < 0 or end < start:
        return None
    try:
        return ET.fromstring(record[start:end + len('</recordinfo>')])
    except ET.ParseError:
        return None


def _is_favorite_record_xml(xml):
    return '<recorditem' in xml and bool(
        re.search(r'<type>\s*19\s*</type>', xml, re.I)
        or 'favorite_record' in xml.casefold()
        or '<recordinfo' in xml
    )


def _favorite_record_summary(xml):
    summary = re.search(r'<des>([\s\S]*?)</des>', xml, re.I)
    summary = _plain_wechat_text(summary.group(1), keep_newlines=True) if summary else ''
    summary = _scrub_wechat_artifacts(summary)
    match = re.match(r'^([^：:\n]{1,40})[：:]\s*(.+)$', summary, re.S)
    return match.group(2).strip() if match else summary


def _favorite_record_body(xml):
    """Return only record item bodies from WeChat type-19/favorite-record appmsg."""
    if '<recorditem' not in xml:
        return ''
    appmsg_type = re.search(r'<type>\s*19\s*</type>', xml, re.I)
    is_favorite = 'favorite_record' in xml.casefold()
    if not appmsg_type and not is_favorite and '<recordinfo' not in xml:
        return ''
    root = _recordinfo_root(xml)
    if root is None:
        return None
    items = []
    for node in root.iter():
        if _xml_local_name(node) != 'dataitem':
            continue
        body = _xml_child_text(node, 'datadesc') or _xml_child_text(node, 'datatitle')
        body = _scrub_wechat_artifacts(_plain_wechat_text(body, keep_newlines=True))
        body = _dedupe_long_paragraphs(body)
        if not body:
            continue
        speaker = _scrub_speaker(_plain_wechat_text(_xml_child_text(node, 'sourcename')))
        items.append((speaker, body))
    if not items:
        summary = _scrub_wechat_artifacts(
            _plain_wechat_text(_xml_child_text(root, 'desc'), keep_newlines=True)
        )
        summary = _dedupe_long_paragraphs(summary)
        if not summary:
            return ''
        match = re.match(r'^([^：:\n]{1,40})[：:]\s*(.+)$', summary, re.S)
        return match.group(2).strip() if match else summary
    if len(items) == 1:
        return items[0][1]
    return '\n'.join(f'{speaker}: {body}' if speaker else body for speaker, body in items)


def _legacy_favorite_record_body(value):
    """Recover rows flattened by the old tag-strip migration before this parser existed."""
    text = _plain_wechat_text(value, keep_newlines=True)
    if not any(title in text for title in _CHAT_RECORD_TITLES):
        return ''
    marker = re.search(
        r'\s+view\s+19\s+https?://support\.weixin\.qq\.com/\S*favorite_record\S*',
        text,
        re.I,
    )
    if not marker:
        return ''
    summary = _scrub_wechat_artifacts(text[:marker.start()].strip())
    title_pattern = '|'.join(re.escape(title) for title in _CHAT_RECORD_TITLES)
    summary = re.sub(rf'^\s*(?:{title_pattern})\s*', '', summary, count=1).strip()
    speaker = re.match(r'^([^：:\n]{1,40})[：:]\s*(.+)$', summary, re.S)
    if speaker:
        summary = speaker.group(2).strip()
    # Old projections can contain only a truncated outer desc before the URL.
    # Without immutable RAW recovery, keeping the noisy row is safer than
    # deleting the full record-item tail based on an ellipsis summary.
    if summary.endswith(('...', '…')):
        return text
    return _dedupe_long_paragraphs(summary)


def _needs_raw_wechat_recovery(value):
    text = str(value or '')
    has_chat_title = any(title in text for title in _CHAT_RECORD_TITLES)
    return bool(
        any(marker in text for marker in ('<msg', '<appmsg', '&lt;msg', '&lt;appmsg'))
        or (
            has_chat_title
            and (
                'support.weixin.qq.com' in text
                or 'wx.qlogo.cn' in text
                or re.search(r'(?:^|\s)(?:19|57)(?:\s|$)', text)
            )
        )
    )


def _raw_wechat_body(payload):
    raw = str(payload.get('message_content') or '').strip()
    compressed = str(payload.get('compress_content') or '').strip()
    if ZSTD_PAT.fullmatch(raw):
        raw = zdec(raw) or ''
    if not raw and compressed and ZSTD_PAT.fullmatch(compressed):
        raw = zdec(compressed) or ''
    match = re.match(r'^([A-Za-z0-9_-]{6,40}):\s*\n?([\s\S]*)$', raw)
    return match.group(2) if match else raw


def _raw_message_sources(rows):
    """Recover full immutable RAW bodies for stored XML/flattened projections."""
    key_to_rids = collections.defaultdict(list)
    for row in rows:
        if not _needs_raw_wechat_recovery(row['content']):
            continue
        try:
            key = (str(row['session'] or ''), int(row['local_id']), int(row['create_time']))
        except (TypeError, ValueError):
            continue
        key_to_rids[key].append(int(row['rid']))
    if not key_to_rids:
        return {}
    raw_root = ARCHIVE / 'RAW'
    if not raw_root.is_dir():
        return {}
    candidates = collections.defaultdict(dict)
    for path in sorted(raw_root.glob('*/all_messages.jsonl'), reverse=True):
        try:
            source = open(path, encoding='utf-8', errors='replace')
        except OSError:
            continue
        with source:
            for line in source:
                try:
                    payload = json.loads(line)
                    key = (
                        str(payload.get('_session') or ''),
                        int(payload.get('local_id')),
                        int(payload.get('create_time')),
                    )
                except (json.JSONDecodeError, TypeError, ValueError):
                    continue
                if key not in key_to_rids:
                    continue
                raw_fingerprint = str(
                    payload.get('message_content') or payload.get('compress_content') or ''
                )
                digest = hashlib.sha256(raw_fingerprint.encode('utf-8')).hexdigest()
                candidates[key].setdefault(digest, (payload, str(path)))
    recovered = {}
    for key, rids in key_to_rids.items():
        versions = candidates.get(key, {})
        if len(versions) != 1:
            security_logger.warning(
                'wechat_raw_recovery_refused session=%s local_id=%s create_time=%s versions=%s',
                key[0], key[1], key[2], len(versions),
            )
            continue
        payload, source_path = next(iter(versions.values()))
        body = _raw_wechat_body(payload)
        if not body:
            security_logger.warning(
                'wechat_raw_recovery_decode_failed session=%s local_id=%s create_time=%s',
                key[0], key[1], key[2],
            )
            continue
        security_logger.info(
            'wechat_raw_recovery source=%s session=%s local_id=%s create_time=%s',
            source_path, key[0], key[1], key[2],
        )
        for rid in rids:
            recovered[rid] = body
    return recovered

def _first_title(x):
    m = re.search(r'<title>([\s\S]*?)</title>', x)
    return _plain_wechat_text(m.group(1)) if m else ''

def _strip_tail_digits(s):
    # 引用消息去标签后留下的 type/showtype/svrid 数字噪声都缀在句尾
    return re.sub(r'(?:\s+\d+)+\s*$', '', s).strip()

def clean_wechat_content(text):
    """Extract human-authored WeChat content and drop transport metadata.

    Type-19/favorite records are parsed before the generic appmsg path so their
    desc/recordinfo copies, URLs, avatar fields, ids and hashes never leak into
    the projection.  The final pass also removes repeated long paragraphs.
    """
    raw = text or ''
    s = _decode_wechat_envelope(raw)
    if _is_favorite_record_xml(s):
        body = _favorite_record_body(s)
        return _favorite_record_summary(s) if body is None else body
    if '<appmsg' not in s and '<msg' not in s:
        legacy_record = _legacy_favorite_record_body(s)
        if legacy_record:
            return legacy_record
        return _dedupe_long_paragraphs(_scrub_wechat_artifacts(_plain_wechat_text(s, keep_newlines=True)))
    head, _sep, rest = s.partition('<msg')
    xml = '<msg' + rest
    own = _strip_tail_digits(_plain_wechat_text(head))
    quoted_name = ''
    quoted_text = ''
    rm = re.search(r'<refermsg>([\s\S]*?)</refermsg>', xml)
    if rm:
        block = rm.group(1)
        nm = re.search(r'<displayname>([\s\S]*?)</displayname>', block)
        if nm: quoted_name = _plain_wechat_text(nm.group(1))
        qc = re.search(r'<content>([\s\S]*?)</content>', block)
        if qc:
            q = _decode_wechat_envelope(qc.group(1))
            quoted_text = _first_title(q) if '<appmsg' in q else _plain_wechat_text(q)
        xml = xml.replace(rm.group(0), ' ')
    if not own:
        own = _first_title(xml)
    elif not quoted_text and '<appmsg' in xml:
        # 历史脏行：外层标签早被剥掉，剩下的 XML 就是被引用的那条消息
        inner = _first_title(xml)
        if inner and inner != own: quoted_text = inner
    quoted_text = _strip_tail_digits(quoted_text)
    parts = [own] if own else []
    if quoted_text:
        parts.append(f'（引用{(" " + quoted_name) if quoted_name else ""}）{quoted_text}')
    out = '\n'.join(parts).strip()
    out = out or _plain_wechat_text(s, keep_newlines=True)
    out = _scrub_wechat_artifacts(out)
    return _dedupe_long_paragraphs(out)

def migrate_clean_wechat_xml(connection=None, *, commit=True):
    """Idempotently rerun the current cleaner over stored message projections."""
    owned_connection = connection is None
    c = connection or db()
    n = 0
    for table in ('essays', 'messages'):
        if table == 'messages':
            rows = c.execute(
                'SELECT rowid AS rid,session,local_id,create_time,content FROM messages'
            ).fetchall()
            raw_sources = _raw_message_sources(rows)
        else:
            rows = c.execute(
                f"SELECT rowid AS rid, content FROM {table} "
                "WHERE content LIKE '%&lt;%' OR content LIKE '%<msg%' "
                "OR content LIKE '%<appmsg%' OR content LIKE '%favorite_record__w_unsupport%'"
            ).fetchall()
            raw_sources = {}
        for r in rows:
            rid = int(r['rid'])
            if table == 'messages' and _needs_raw_wechat_recovery(r['content']) and rid not in raw_sources:
                security_logger.warning('wechat_clean_skipped_missing_raw rowid=%s', rid)
                continue
            source = raw_sources.get(rid, r['content'])
            decoded_source = _decode_wechat_envelope(source)
            if _is_favorite_record_xml(decoded_source) and _favorite_record_body(decoded_source) is None:
                security_logger.warning('wechat_clean_skipped_bad_recorditem rowid=%s', rid)
                continue
            cleaned = clean_wechat_content(source)
            if table == 'messages': cleaned = cleaned.replace('\n', ' ')
            if cleaned != r['content']:
                c.execute(f'UPDATE {table} SET content=? WHERE rowid=?', (cleaned, r['rid']))
                n += 1
    if n:
        try: c.execute("INSERT INTO msg_fts(msg_fts) VALUES('rebuild')")
        except sqlite3.Error: pass
    if commit:
        c.commit()
    if owned_connection:
        c.close()
    return n


def _essay_machine_name(value):
    value = str(value or '').strip()
    return not value or value in {'?', '群友'} or bool(
        re.fullmatch(r'(?:wxid_[A-Za-z0-9_-]+|QQ\d{5,}|q\d{6,}|gh_[A-Za-z0-9_-]+)', value)
    )


def _essay_sender(row):
    sender = str(row['sender'] or '').strip()
    display = str(row['sender_name'] or '').strip()
    if sender and sender != '?':
        return sender
    # 未解析的 '?' 没有身份锚，不能把两个陌生人的短消息拼成同一篇；用行号隔离。
    return f'?#{row["id"]}'


def _essay_author(row, member_names=None):
    sender = str(row['sender'] or '').strip()
    display = str(row['sender_name'] or '').strip()
    if sender in NAME_OVERRIDES:
        return NAME_OVERRIDES[sender]
    mapped = (member_names or {}).get(sender, '')
    if mapped and not _essay_machine_name(mapped):
        return mapped
    if display and not _essay_machine_name(display):
        return display
    if sender and not _essay_machine_name(sender):
        return NAME_OVERRIDES.get(sender, sender)
    return '群友'


def _essay_body(row):
    body = clean_wechat_content(str(row['content'] or '')).strip()
    # 控制字符/零宽字符不应进入标题、署名或活动正文；换行保留给小作文阅读。
    return re.sub(r'[\x00-\x08\x0b\x0c\x0e-\x1f\x7f\u200b-\u200f\u202a-\u202e\u2060\ufeff]', '', body).strip()


def _essay_has_intro(body):
    return bool(ESSAY_INTRO_RE.search(body[:160]))


def _essay_candidate_from_rows(rows):
    if not rows:
        return None
    body = '\n'.join(str(row['body']).strip() for row in rows if str(row['body']).strip()).strip()
    if len(body) <= ESSAY_MIN_CHARS:
        return None
    first = rows[0]
    ids = [int(row['id']) for row in rows]
    cst = str(first['cst'] or '')
    first_line = next((line.strip() for line in body.splitlines() if line.strip()), '')
    return {
        'cst': cst,
        'source_date': cst[:10],
        'author': first['author'],
        'source_sender': first['source_sender'],
        'body': body,
        'title': first_line[:40] or f"{first['author']}的小作文",
        'source_message_ids': ids,
        'provenance': {
            'source': 'messages',
            'criterion': f'LENGTH(clean(content))>{ESSAY_MIN_CHARS} or contiguous self-intro parts',
            'message_count': len(ids),
        },
    }


def essay_candidates(c):
    """从消息事实生成小作文候选；身份锚永远是 sender，不按展示名合并。"""
    try:
        member_names = {
            row['username']: (row['display'] or row['nickname'] or '')
            for row in c.execute('SELECT username,display,nickname FROM members')
        }
    except sqlite3.OperationalError:
        member_names = {}
    raw_rows = c.execute(
        '''SELECT id,cst,create_time,sender,sender_name,content
           FROM messages ORDER BY create_time,id'''
    ).fetchall()
    prepared = []
    for row in raw_rows:
        body = _essay_body(row)
        if not body:
            continue
        prepared.append({
            'id': row['id'], 'cst': row['cst'], 'create_time': int(row['create_time'] or 0),
            'source_sender': _essay_sender(row), 'author': _essay_author(row, member_names), 'body': body,
            'is_long': len(body) > ESSAY_MIN_CHARS, 'has_intro': _essay_has_intro(body),
        })

    candidates = []
    block = []

    def flush():
        nonlocal block
        if not block:
            return
        candidate = _essay_candidate_from_rows(block)
        if candidate:
            candidates.append(candidate)
        block = []

    for item in prepared:
        if block:
            previous = block[-1]
            same_sender = item['source_sender'] == previous['source_sender']
            gap = item['create_time'] - previous['create_time']
            can_continue = (
                same_sender and 0 <= gap <= ESSAY_CONTINUATION_GAP_SECONDS
                and any(part['has_intro'] for part in block)
            )
            if not can_continue:
                flush()
        if not block and (item['is_long'] or item['has_intro']):
            block = [item]
        elif block:
            block.append(item)
        # 非自我介绍的短消息不可能独立构成小作文，直接跳过。
    flush()
    return candidates


def _essay_json(value):
    return json.dumps(value, ensure_ascii=False, separators=(',', ':'))


def ensure_essay_activity_event(c):
    row = c.execute('SELECT id FROM events WHERE slug=?', (ESSAY_ACTIVITY_SLUG,)).fetchone()
    if row:
        return row['id']
    # seed_events.py 通常会先写入；这里仅在缺失时补最小事实，避免每日导入把活动接线丢掉。
    now = datetime.datetime.now(CST).isoformat()
    c.execute(
        '''INSERT INTO events(slug,title,kind,status,starts_at,ends_at,rules_md,reward,cover_path,created_by)
           VALUES(?,?,?,?,?,?,?,?,?,?)''',
        (ESSAY_ACTIVITY_SLUG, '小作文入群仪式', 'essay', 'open', None, None,
         '介绍自己、对 AI 的理解、擅长什么、想了解什么、对未来的展望。入群即交，跨期挂账。',
         '', '/art/poster-essay.png', 'essay-ingest'),
    )
    return c.execute('SELECT id FROM events WHERE slug=?', (ESSAY_ACTIVITY_SLUG,)).fetchone()['id']


def sync_essay_activity(c, essay_rows, *, replace=False):
    """把消息来源的小作文挂入 onboarding-essay；不伪造 users/submissions。"""
    event_id = ensure_essay_activity_event(c)
    seen_ids = []
    now = datetime.datetime.now(CST).isoformat()
    for essay in essay_rows:
        source_ids = essay['source_message_ids']
        source_json = _essay_json(source_ids)
        row = c.execute(
            'SELECT id FROM essays WHERE source_kind=\'message\' AND source_message_ids=?',
            (source_json,),
        ).fetchone()
        if not row:
            continue
        essay_id = row['id']
        seen_ids.append(essay_id)
        c.execute(
            '''INSERT INTO essay_activity_items(
                 event_id,essay_id,source_sender,author,title,body,source_message_ids,source_date,
                 status,provenance_json,created_at,updated_at)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(event_id,essay_id) DO UPDATE SET
                 source_sender=excluded.source_sender,author=excluded.author,title=excluded.title,
                 body=excluded.body,source_message_ids=excluded.source_message_ids,
                 source_date=excluded.source_date,provenance_json=excluded.provenance_json,
                 updated_at=excluded.updated_at''',
            (event_id, essay_id, essay['source_sender'], essay['author'], essay['title'], essay['body'],
             source_json, essay['source_date'], 'accepted', _essay_json(essay['provenance']), now, now),
        )
    if replace:
        if seen_ids:
            placeholders = ','.join('?' for _ in seen_ids)
            c.execute(
                f'DELETE FROM essay_activity_items WHERE event_id=? AND essay_id NOT IN ({placeholders})',
                [event_id, *seen_ids],
            )
        else:
            c.execute('DELETE FROM essay_activity_items WHERE event_id=?', (event_id,))
    return len(seen_ids)


def rebuild_essays(c, *, replace=False):
    """按 sender+消息顺序重建；replace 只应在已备份并审过旧表后使用。"""
    candidates = essay_candidates(c)
    existing = {
        row['source_message_ids']: row['id']
        for row in c.execute("SELECT id,source_message_ids FROM essays WHERE source_kind='message'")
        if row['source_message_ids']
    }
    existing_sets = []
    for source_json, essay_id in existing.items():
        try:
            existing_sets.append((essay_id, set(json.loads(source_json))))
        except (TypeError, json.JSONDecodeError):
            continue
    essay_rows = []
    for essay in candidates:
        source_json = _essay_json(essay['source_message_ids'])
        values = (essay['cst'], essay['author'], essay['title'], essay['body'], source_json,
                  essay['source_sender'], 'message', ESSAY_ACTIVITY_SLUG, _essay_json(essay['provenance']))
        essay_id = existing.get(source_json)
        if not essay_id:
            candidate_ids = set(essay['source_message_ids'])
            essay_id = next((old_id for old_id, old_ids in existing_sets if candidate_ids & old_ids), None)
        if essay_id:
            c.execute(
                '''UPDATE essays SET cst=?,author=?,name=?,content=?,source_message_ids=?,source_sender=?,activity_slug=?,provenance_json=?
                   WHERE id=?''',
                (*values[:6], values[7], values[8], essay_id),
            )
            existing_sets = [
                (old_id, set(essay['source_message_ids']) if old_id == essay_id else old_ids)
                for old_id, old_ids in existing_sets
            ]
            existing[source_json] = essay_id
        else:
            c.execute(
                '''INSERT INTO essays(cst,author,name,content,source_message_ids,source_sender,source_kind,activity_slug,provenance_json)
                   VALUES(?,?,?,?,?,?,?,?,?)''', values,
            )
            essay_id = c.execute('SELECT last_insert_rowid()').fetchone()[0]
            existing[source_json] = essay_id
            existing_sets.append((essay_id, set(essay['source_message_ids'])))
        essay['id'] = essay_id
        essay_rows.append(essay)
    synced = sync_essay_activity(c, essay_rows, replace=replace)
    if replace:
        seen_ids = [int(essay['id']) for essay in essay_rows]
        if seen_ids:
            placeholders = ','.join('?' for _ in seen_ids)
            c.execute(
                f"DELETE FROM essays WHERE source_kind IN ('legacy','message') "
                f"AND id NOT IN ({placeholders})",
                seen_ids,
            )
        else:
            c.execute("DELETE FROM essays WHERE source_kind IN ('legacy','message')")
    return {'candidates': len(candidates), 'activity_items': synced}


def _essay_activity_item(row, *, include_body=False):
    item = {
        'id': row['id'], 'essay_id': row['essay_id'], 'author': row['author'],
        'title': row['title'], 'date': row['source_date'], 'word_count': len(re.sub(r'\s+', '', row['body'] or '')),
        'source': 'group-import', 'readonly': True, 'status': row['status'],
        'via_label': '群内小作文·跨期挂账',
    }
    if include_body:
        item['body'] = row['body']
    return item

RAW_EXPORT_DAY_RE = re.compile(r'^\d{4}-\d{2}-\d{2}$')


def _latest_raw_export(day_dir: Path, target_day: str | None = None) -> Path:
    """Resolve the newest cumulative RAW snapshot for a requested day.

    Daily exports are cumulative: the 08-27 snapshot may contain late-arriving
    08-26 rows that were absent from the 08-26 snapshot.  Keep direct callers
    backwards compatible while allowing the admin importer to choose the
    newest available sibling snapshot.
    """
    direct = day_dir / 'all_messages.jsonl'
    if not target_day or not RAW_EXPORT_DAY_RE.fullmatch(str(target_day)):
        return direct
    parent = day_dir.parent
    candidates = []
    try:
        for sibling in parent.iterdir():
            if not sibling.is_dir() or not RAW_EXPORT_DAY_RE.fullmatch(sibling.name):
                continue
            if sibling.name < target_day:
                continue
            source = sibling / 'all_messages.jsonl'
            if source.is_file():
                candidates.append((sibling.name, source))
    except OSError:
        return direct
    if candidates:
        return max(candidates, key=lambda item: item[0])[1]
    return direct


def import_day(day_dir: Path, target_day: str | None = None):
    f = _latest_raw_export(day_dir, target_day)
    if not f.exists(): return 0
    c = db()
    n = 0
    # local_id is a client-side counter and can be re-numbered after a WeChat
    # re-login.  Content+timestamp is the durable fallback; a same-session
    # local_id is only trusted when its timestamp also agrees (protecting
    # against duplicate rows in one snapshot without swallowing re-numbered
    # messages).
    primary = {
        (str(row['session'] or ''), int(row['local_id'])): int(row['create_time'])
        for row in c.execute(
            'SELECT session,local_id,create_time FROM messages '
            'WHERE local_id IS NOT NULL AND create_time IS NOT NULL'
        )
    }
    content_time = {
        (int(row['create_time']), hashlib.sha256(str(row['content'] or '').encode('utf-8')).hexdigest())
        for row in c.execute(
            'SELECT create_time,content FROM messages '
            'WHERE create_time IS NOT NULL AND COALESCE(content,\'\')<>\'\''
        )
    }
    for line in open(f):
        try: m = json.loads(line)
        except: continue
        try:
            local_id = int(m['local_id'])
            create_time = int(m['create_time'])
        except (KeyError, TypeError, ValueError):
            continue
        if target_day:
            try:
                if datetime.datetime.fromtimestamp(create_time, CST).strftime('%Y-%m-%d') != target_day:
                    continue
            except (OverflowError, OSError, ValueError):
                continue
        raw = (m.get('message_content') or '').strip()
        comp = (m.get('compress_content') or '').strip()
        content = raw
        if ZSTD_PAT.fullmatch(raw): content = zdec(raw) or ''
        if not content and comp and ZSTD_PAT.fullmatch(comp): content = zdec(comp) or ''
        mp = re.match(r'^([A-Za-z0-9_-]{6,40}):\s*\n?([\s\S]*)$', content)
        if mp: sender, body = mp.group(1), mp.group(2)
        else: sender = 'sunwuyuan521' if m.get('computed_is_send')=='1' else '?'; body = content
        body_txt = clean_wechat_content(body)
        stored_content = body_txt.replace('\n', ' ')
        session = str(m.get('_session') or '')
        primary_key = (session, local_id)
        content_key = (create_time, hashlib.sha256(stored_content.encode('utf-8')).hexdigest()) if stored_content else None
        if (content_key is not None and content_key in content_time) or (
            primary_key in primary and primary[primary_key] == create_time
        ):
            continue
        sender_name = NAME_OVERRIDES.get(
            sender,
            str(m.get('sender_name') or m.get('nickname') or sender).strip() or sender,
        )
        t = datetime.datetime.fromtimestamp(create_time, CST)
        c.execute('INSERT INTO messages(session,local_id,create_time,cst,sender,sender_name,is_send,content) VALUES(?,?,?,?,?,?,?,?)',
                  (session, local_id, create_time, t.strftime('%Y-%m-%d %H:%M'), sender, sender_name,
                   1 if m.get('computed_is_send')=='1' else 0, stored_content))
        primary[primary_key] = create_time
        if content_key is not None:
            content_time.add(content_key)
        n += 1
    rebuild_essays(c, replace=False)
    c.commit(); refresh_members(c); c.close()
    return n

def refresh_members(c):
    """Rebuild member projections by wxid, keeping display names as labels only.

    Older imports keyed this table by ``sender_name`` and therefore merged two
    identities that happened to share a nickname.  This path deliberately
    keeps old rows (account bindings may still point at them) but marks them as
    legacy; all fresh rows and all statistics are keyed by ``messages.sender``.
    """
    columns = {row[1] for row in c.execute('PRAGMA table_info(members)')}
    required = {'name_source', 'identity_flags', 'name_history', 'called_names'}
    if not required <= columns:
        # init_db normally performs this migration.  Keep direct callers safe.
        for column, ddl in (
            ('name_source', "name_source TEXT NOT NULL DEFAULT 'masked_wxid'"),
            ('identity_flags', "identity_flags TEXT NOT NULL DEFAULT '[]'"),
            ('name_history', "name_history TEXT NOT NULL DEFAULT '[]'"),
            ('called_names', "called_names TEXT NOT NULL DEFAULT '[]'"),
        ):
            if column not in columns:
                c.execute(f'ALTER TABLE members ADD COLUMN {column} {ddl}')

    old_rows = {
        row['username']: dict(row)
        for row in c.execute('SELECT * FROM members').fetchall()
    }
    message_rows = c.execute(
        'SELECT id,sender,sender_name,cst,create_time,content FROM messages ORDER BY create_time,id'
    ).fetchall()
    grouped: dict[str, list] = collections.defaultdict(list)
    for row in message_rows:
        grouped[_member_clean(row['sender']) or '?'].append(row)
    called_by_sender, _called_unresolved = _member_collect_called_names(message_rows)

    avatar_map: dict[str, str] = {}
    avatar_file = ARCHIVE / 'avatars.json'
    if avatar_file.exists():
        try:
            payload = json.loads(avatar_file.read_text(encoding='utf-8'))
            raw = payload.get('avatars', {}) if isinstance(payload, dict) else {}
            if isinstance(raw, dict):
                avatar_map = {str(k): str(v) for k, v in raw.items() if v}
        except (OSError, json.JSONDecodeError):
            avatar_map = {}

    records: dict[str, dict] = {}
    for sender, rows in grouped.items():
        old = old_rows.get(sender, {})
        room_counts: collections.Counter[str] = collections.Counter()
        for row in rows:
            candidate = _member_display_candidate(row['sender_name'], sender)
            if candidate:
                room_counts[candidate] += 1
        override = _member_display_candidate(NAME_OVERRIDES.get(sender), sender)
        room_name = override or (room_counts.most_common(1)[0][0] if room_counts else '')
        called = called_by_sender.get(sender, [])
        stable_called = [
            item for item in called
            if _member_called_is_stable(item)
        ]
        source = 'room_nickname'
        base_name = room_name
        if sender == 'wxid_09cec05iemwv12' and stable_called:
            base_name = stable_called[0]['name']
            source = 'called_name'
        elif not base_name and stable_called:
            base_name = stable_called[0]['name']
            source = 'called_name'
        if not base_name:
            base_name = _member_masked_username(sender)
            source = 'masked_wxid'

        history = [_member_clean(value) for value in _member_json_list(old.get('name_history')) if _member_clean(value)]
        for value in ([room_name] if room_name else []) + ([base_name] if base_name and source == 'called_name' else []):
            if value not in history and not _member_is_raw(value):
                history.append(value)
        flags = [
            _member_clean(value) for value in _member_json_list(old.get('identity_flags'))
            if _member_clean(value)
        ]
        if source == 'called_name' and 'called_name' not in flags:
            flags.append('called_name')
        if sender == '?' and 'missing_wxid' not in flags:
            flags.append('missing_wxid')
        if len(history) > 1 and 'name_changed' not in flags:
            flags.append('name_changed')
        avatar = _member_clean(old.get('avatar')) or avatar_map.get(sender) or avatar_map.get(room_name) or avatar_map.get(base_name) or ''
        counts = len(rows)
        last_active = max((_member_clean(row['cst'])[:10] for row in rows if _member_clean(row['cst'])), default='')
        records[sender] = {
            'username': sender,
            'base_name': base_name,
            'room_name': room_name,
            'display': base_name,
            'nickname': room_name,
            'avatar': avatar,
            'msgs': counts,
            'last_active': last_active,
            'profile': old.get('profile') or '',
            'tags': old.get('tags') or '',
            'quote': old.get('quote') or '',
            'name_source': source,
            'identity_flags': flags,
            'name_history': history,
            'called_names': called,
        }

    def suffix(index: int) -> str:
        if index <= 1:
            return ''
        if 2 <= index <= 10:
            return chr(0x2460 + index - 1)  # ② … ⑩
        return f'({index})'

    by_name: dict[str, list[str]] = collections.defaultdict(list)
    for sender, record in records.items():
        if record['base_name'] and not _member_is_raw(record['base_name']):
            by_name[_member_alias_key(record['base_name'])].append(sender)
    now = datetime.datetime.now(CST).isoformat()
    for name_key, senders in by_name.items():
        senders.sort()
        if len(senders) < 2:
            continue
        base = records[senders[0]]['base_name']
        for index, sender in enumerate(senders, 1):
            records[sender]['display'] = f'{base}{suffix(index)}'
            if 'name_collision' not in records[sender]['identity_flags']:
                records[sender]['identity_flags'].append('name_collision')
            details = json.dumps({'base_name': base, 'wxids': senders, 'ordinal': index}, ensure_ascii=False, sort_keys=True)
            event_key = f'collision:{name_key}:{sender}:{"|".join(senders)}'
            c.execute(
                '''INSERT OR IGNORE INTO member_identity_audit(
                     event_key,created_at,event_type,username,display,details_json)
                   VALUES(?,?,?,?,?,?)''',
                (event_key, now, 'same_name_different_wxid', sender, records[sender]['display'], details),
            )

    for sender, record in records.items():
        old = old_rows.get(sender, {})
        old_display = _member_clean(old.get('display'))
        if old_display and old_display != record['display'] and not _member_is_raw(old_display):
            details = json.dumps({'old_name': old_display, 'new_name': record['display'], 'name_history': record['name_history']}, ensure_ascii=False, sort_keys=True)
            event_key = f'rename:{sender}:{old_display}:{record["display"]}'
            c.execute(
                '''INSERT OR IGNORE INTO member_identity_audit(
                     event_key,created_at,event_type,username,display,details_json)
                   VALUES(?,?,?,?,?,?)''',
                (event_key, now, 'same_wxid_name_change', sender, record['display'], details),
            )
        c.execute(
            '''INSERT INTO members(
                 username,display,nickname,avatar,msgs,last_active,profile,tags,quote,
                 name_source,identity_flags,name_history,called_names)
               VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
               ON CONFLICT(username) DO UPDATE SET
                 display=excluded.display,nickname=excluded.nickname,avatar=excluded.avatar,
                 msgs=excluded.msgs,last_active=excluded.last_active,profile=excluded.profile,
                 tags=excluded.tags,quote=excluded.quote,name_source=excluded.name_source,
                 identity_flags=excluded.identity_flags,name_history=excluded.name_history,
                 called_names=excluded.called_names''',
            (
                record['username'], record['display'], record['nickname'], record['avatar'],
                record['msgs'], record['last_active'], record['profile'], record['tags'], record['quote'],
                record['name_source'], json.dumps(record['identity_flags'], ensure_ascii=False),
                json.dumps(record['name_history'], ensure_ascii=False),
                json.dumps(record['called_names'], ensure_ascii=False),
            ),
        )

    # Do not silently delete legacy display-key rows: account bindings may still
    # reference them.  Expose them as risky rows for the admin lane to review.
    current_keys = set(records)
    for username, old in old_rows.items():
        if username in current_keys or not username:
            continue
        flags = [
            _member_clean(value) for value in _member_json_list(old.get('identity_flags'))
            if _member_clean(value)
        ]
        if 'legacy_display_key' not in flags:
            flags.append('legacy_display_key')
        c.execute(
            'UPDATE members SET identity_flags=?,name_source=COALESCE(NULLIF(name_source,\'\'),\'masked_wxid\') WHERE username=?',
            (json.dumps(flags, ensure_ascii=False), username),
        )
    c.commit()

# ── 统计 API（v2 深度版） ──
@app.get('/api/stats')
def stats():
    c = db()
    tot = c.execute('SELECT COUNT(*) FROM messages').fetchone()[0]
    # wxid/sender is the identity key; sender_name is presentation only.
    spk = c.execute("SELECT COUNT(DISTINCT COALESCE(NULLIF(sender,''),'?')) FROM messages").fetchone()[0]
    lo, hi = c.execute('SELECT MIN(cst),MAX(cst) FROM messages').fetchone()
    hours = {r[0]:r[1] for r in c.execute("SELECT substr(cst,12,2),COUNT(*) FROM messages GROUP BY 1")}
    days = {r[0]:r[1] for r in c.execute("SELECT substr(cst,1,10),COUNT(*) FROM messages GROUP BY 1 ORDER BY 1")}
    essays = c.execute('SELECT COUNT(*) FROM essays').fetchone()[0]
    # 深度统计
    avg_len = c.execute('SELECT AVG(LENGTH(content)) FROM messages WHERE content>""').fetchone()[0] or 0
    long_msgs = c.execute("SELECT COUNT(*) FROM messages WHERE LENGTH(content)>100").fetchone()[0]
    emoji_only = c.execute("SELECT COUNT(*) FROM messages WHERE LENGTH(content)<10 AND (content LIKE '%[%]%' OR LENGTH(TRIM(content))<3)").fetchone()[0]
    # 每人详细
    member_stats = []
    for r in c.execute('''SELECT COALESCE((SELECT m.display FROM members m WHERE m.username=messages.sender),
        NULLIF(messages.sender_name,'?'),messages.sender) name,
        sender, COUNT(*) msgs, AVG(LENGTH(content)) avg_len,
        SUM(CASE WHEN LENGTH(content)>100 THEN 1 ELSE 0 END) long_msgs,
        MIN(substr(cst,12,2)) first_h, MAX(substr(cst,12,2)) last_h
        FROM messages GROUP BY sender ORDER BY msgs DESC'''):
        member_stats.append(dict(r))
    # 时段画像（每人 Top3 活跃小时）
    for m in member_stats:
        hrs = [dict(r) for r in c.execute(
            "SELECT substr(cst,12,2) h, COUNT(*) n FROM messages WHERE sender=? GROUP BY 1 ORDER BY n DESC LIMIT 3", (m['sender'],))]
        m['peak_hours'] = [f"{h['h']}时" for h in hrs]
    # 话题关键词（简易频率）
    words = collections.Counter()
    for r in c.execute("SELECT content FROM messages WHERE LENGTH(content)>20 LIMIT 500"):
        for w in re.findall(r'[\u4e00-\u9fff]{2,4}', r[0]):
            if w not in ('的时候','这个是','那个','什么','可以','就是','然后','但是','因为','所以','如果','没有','不是','还是','觉得','应该','现在','我们','你们','他们','的话','一下','一个','什么'):
                words[w] += 1
    top_words = words.most_common(30)
    c.close()
    return {'total':tot,'speakers':spk,'range':[lo,hi],'hours':hours,'days':days,'essays':essays,
            'avg_len':round(avg_len,1),'long_msgs':long_msgs,'emoji_only':emoji_only,
            'signal_ratio':round((tot-emoji_only)/max(tot,1)*100,1) if tot else 0,
            'members':member_stats[:30], 'keywords':top_words}

# ── 群聊质量评判引擎 ──
def _quality_grade(score):
    return 'A' if score >= 80 else 'B' if score >= 60 else 'C' if score >= 40 else 'D'


def _quality_day(c, requested):
    """校验并确定质量窗口日期；不传 date 时取库中最新消息日。"""
    if requested is not None:
        value = str(requested).strip()
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
            raise HTTPException(400, 'date 必须是 YYYY-MM-DD')
        try:
            datetime.date.fromisoformat(value)
        except ValueError as exc:
            raise HTTPException(400, 'date 必须是有效日期') from exc
        return value
    row = c.execute("SELECT MAX(substr(cst,1,10)) FROM messages WHERE cst IS NOT NULL AND cst<>''").fetchone()
    return row[0] if row and row[0] else None


def _quality_snapshot(msgs, *, scope, date_value=None):
    """对一组消息计算五维；scope=date/all 只改变窗口，不改变五维定义。"""
    basis_scope = '当日窗口' if scope == 'daily' else '全库累计'
    if not msgs:
        return {
            'scope': scope,
            'date': date_value,
            'grade': 'N/A',
            'overall': 0,
            'dimensions': [],
            'speakers': 0,
            'total_msgs': 0,
            'basis': f'{basis_scope}无消息',
        }

    total = len(msgs)
    speakers = collections.Counter(m['sn'] for m in msgs)
    lens = [len(m['content'] or '') for m in msgs]
    avg_len = sum(lens) / total
    long_count = sum(1 for length in lens if length > 100)
    long_ratio = long_count / total * 100
    # 互动检测：@提及 或 引用回复
    interactions = sum(
        1 for m in msgs
        if '@' in (m['content'] or '')[:20] or (m['content'] or '').startswith('Re:')
    )
    # 知识密度：链接/文件/工具名/方法词
    knowledge = sum(
        1 for m in msgs
        if any(k in (m['content'] or '').lower() for k in
               ['github', 'http', '.pdf', '.md', '.html', '.zip', '工具', '方法', '知识库',
                'agent', 'harness', '向量', '蒸馏', '结构化'])
    )
    # 小作文/深度输出：与 essays/rebuild_essays 同一条 >200 字消息尺子
    essays_count = sum(1 for length in lens if length > ESSAY_MIN_CHARS)
    # 参与均衡度（基尼系数简化版：前3人占比）
    top3_share = sum(n for _, n in speakers.most_common(3)) / total * 100
    # 回应密度：短时间内多话题交替
    bursts = sum(1 for i in range(1, total) if msgs[i]['sn'] != msgs[i - 1]['sn'])
    turn_taking = bursts / total * 100

    # 重新定标：旧式 long_ratio*5、essays*4 在全库口径下很快封顶。
    # 30% 长文率/300 字均长、80 篇小作文是按现有日窗口观测值留出的满档参考线。
    info_score = min(
        100,
        int(round(
            (long_ratio / QUALITY_INFO_LONG_FULL * 100) * QUALITY_INFO_LONG_WEIGHT
            + (avg_len / QUALITY_INFO_AVG_FULL * 100) * QUALITY_INFO_AVG_WEIGHT
        )),
    )
    interaction_score = min(100, int(turn_taking))
    knowledge_score = min(100, int(knowledge / total * 400))
    balance_score = max(0, int(100 - top3_share))
    depth_score = min(100, int(round(essays_count / QUALITY_DEPTH_ESSAYS_FULL * 100)))

    dims = [
        {
            'name': '信息密度', 'score': info_score, 'grade': _quality_grade(info_score),
            'detail': (
                f'长文率 {long_ratio:.1f}%，均长 {avg_len:.0f} 字/条；'
                f'定标为长文率 {QUALITY_INFO_LONG_FULL:.0f}%、均长 {QUALITY_INFO_AVG_FULL:.0f} 字/条满档，'
                '权重 60/40。长文越多、单条越完整=有效信息越厚。'
            ),
        },
        {
            'name': '互动质量', 'score': interaction_score, 'grade': _quality_grade(interaction_score),
            'detail': f'话题轮转率 {turn_taking:.0f}%（不同人交替发言比例）。越高=对话越像「聊天」而非「广播」。@提及 {interactions} 次。',
        },
        {
            'name': '知识贡献', 'score': knowledge_score, 'grade': _quality_grade(knowledge_score),
            'detail': f'知识型消息 {knowledge} 条（含链接/工具/方法/代码）。占比 {knowledge / total * 100:.1f}%。小作文 {essays_count} 篇。',
        },
        {
            'name': '参与均衡', 'score': balance_score, 'grade': _quality_grade(balance_score),
            'detail': f'TOP3 占 {top3_share:.0f}%。越低=发言权越分散=更多人愿意开口=社群越健康。发言人数 {len(speakers)}。',
        },
        {
            'name': '深度输出', 'score': depth_score, 'grade': _quality_grade(depth_score),
            'detail': f'超 200 字消息 {essays_count} 条（小作文/长论）；定标为 {QUALITY_DEPTH_ESSAYS_FULL} 条满档。深度输出是社群「认知资产」的直接产出。',
        },
    ]
    overall = sum(d['score'] for d in dims) // len(dims)
    return {
        'scope': scope,
        'date': date_value,
        'grade': _quality_grade(overall),
        'overall': overall,
        'dimensions': dims,
        'speakers': len(speakers),
        'total_msgs': total,
        'basis': f'{basis_scope} {date_value or ""}：{total} 条消息 · {len(speakers)} 位发言人',
        'verdict': (
            f'综合评级 {_quality_grade(overall)}（{overall}分/100）。'
            f'信息密度{dims[0]["grade"]}·互动{dims[1]["grade"]}·知识{dims[2]["grade"]}·'
            f'均衡{dims[3]["grade"]}·深度{dims[4]["grade"]}。'
            f'{len(speakers)} 人产出 {total} 条消息，TOP3 占比 {top3_share:.0f}%。'
        ),
    }


@app.get('/api/quality')
def quality(date: str | None = None):
    c = db()
    try:
        target_day = _quality_day(c, date)
        all_msgs = c.execute(
            "SELECT cst,COALESCE(NULLIF(sender_name,'?'),sender) sn,content FROM messages ORDER BY create_time"
        ).fetchall()
        daily_msgs = [m for m in all_msgs if target_day and (m['cst'] or '')[:10] == target_day]
        daily = _quality_snapshot(daily_msgs, scope='daily', date_value=target_day)
        # 历史出刊不可偷看未来：窖藏背景分是截至目标日的全库累计。
        vault_msgs = [
            m for m in all_msgs
            if not target_day or ((m['cst'] or '')[:10] and (m['cst'] or '')[:10] <= target_day)
        ]
        vault = _quality_snapshot(vault_msgs, scope='all', date_value=target_day)
        vault['label'] = '窖藏总度数'
        daily['vault_quality'] = vault
        daily['window'] = {'from': target_day, 'to': target_day, 'timezone': 'Asia/Shanghai'}
        return daily
    finally:
        c.close()

# ── 其余 API（同 v1） ──
@app.get('/api/messages', deprecated=True)
def query_messages(q:str='',sender:str='',date:str='',limit:int=Query(50,le=300),offset:int=0):
    raise HTTPException(410, '原始消息浏览端点已停用；网站只提供治理后的内容。')

@app.get('/api/members')
def members_api():
    c = db()
    rows = c.execute(
        '''SELECT username,display,nickname,avatar,msgs,last_active,quote,
                  name_source,identity_flags,name_history,called_names
           FROM members ORDER BY msgs DESC,username'''
    ).fetchall()
    c.close()
    items = []
    for row in rows:
        item = dict(row)
        item['identity_flags'] = _member_json_list(item.get('identity_flags'))
        item['name_history'] = _member_json_list(item.get('name_history'))
        item['called_names'] = _member_json_list(item.get('called_names'))
        items.append(item)
    return {'items': items}


@app.get('/api/members/names')
def member_names_api():
    """注册页用的群昵称名单：只给显示名（剔除未解析的裸 wxid/gh_），无头像无数据。"""
    c = db()
    rows = c.execute(
        """SELECT DISTINCT display FROM members
           WHERE display<>'' AND display NOT LIKE 'wxid_%' AND display NOT LIKE 'gh_%'
           ORDER BY display"""
    ).fetchall()
    c.close()
    return {'names': [r['display'] for r in rows]}

@app.get('/api/essays')
def essays_api(limit:int=100):
    c = db()
    rows = c.execute('SELECT cst,author,content FROM essays ORDER BY cst DESC LIMIT ?',(limit,)).fetchall()
    c.close(); return {'items':[dict(r) for r in rows]}


# ── 治理产物 API ──
def load_governed_ledger(path: Path):
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, f'治理日报文件不可读：{path.name}') from exc


def ledger_summary(data):
    quality = data.get('quality') if isinstance(data.get('quality'), dict) else {}
    return {
        'date': data.get('date'),
        'issue': data.get('issue'),
        'title': data.get('title'),
        'overall': quality.get('overall', data.get('overall')),
    }


@app.get('/api/governed/ledgers', tags=['agent'])
def governed_ledgers():
    items = []
    if GOVERNED_LEDGER_DIR.exists():
        for path in sorted(GOVERNED_LEDGER_DIR.glob('*.json'), reverse=True):
            data = load_governed_ledger(path)
            items.append(ledger_summary(data))
    return {'items': items}


def update_cursor_date(value):
    value = str(value or '').strip()
    if not value:
        return ''
    if re.fullmatch(r'\d{4}-\d{2}-\d{2}', value):
        return value
    try:
        return datetime.datetime.fromisoformat(value.replace('Z', '+00:00')).date().isoformat()
    except ValueError as exc:
        raise HTTPException(400, 'since 必须是 ISO 8601 时间或 YYYY-MM-DD') from exc


@app.get('/api/agent/updates', tags=['agent'])
def agent_updates(
    request: Request,
    since: str | None = Query(None, max_length=64),
    limit: int = Query(100, ge=1, le=300),
):
    profile = require_agent(request)
    c = db()
    token_row = c.execute(
        'SELECT created_at,last_learning_at FROM agent_tokens WHERE id=?',
        (profile['id'],),
    ).fetchone()
    marker = since.strip() if since else ((token_row['last_learning_at'] if token_row else None) or (token_row['created_at'] if token_row else ''))
    marker_date = update_cursor_date(marker)
    new_ledgers = []
    if GOVERNED_LEDGER_DIR.exists():
        for path in sorted(GOVERNED_LEDGER_DIR.glob('*.json')):
            data = load_governed_ledger(path)
            date = str(data.get('date') or path.stem)
            if marker_date and date <= marker_date:
                continue
            new_ledgers.append(data)
    new_ledgers = new_ledgers[-limit:]
    new_arsenal = []
    for item in all_public_arsenal_items():
        item_date = str(item.get('created_at') or item.get('collected_at') or '')[:10]
        if marker_date and item_date and item_date <= marker_date:
            continue
        new_arsenal.append(arsenal_list_item(item))
    new_arsenal.sort(key=lambda item: (str(item.get('created_at') or item.get('collected_at') or ''), str(item.get('id'))), reverse=False)
    new_arsenal = new_arsenal[-limit:]
    latest = None
    paths = sorted(GOVERNED_LEDGER_DIR.glob('*.json'), reverse=True) if GOVERNED_LEDGER_DIR.exists() else []
    if paths:
        latest = load_governed_ledger(paths[0])
    cursor = datetime.datetime.now(CST).isoformat()
    c.execute('UPDATE agent_tokens SET last_learning_at=? WHERE id=?', (cursor, profile['id']))
    c.commit()
    c.close()
    record_agent_action(
        request, 'learning.sync', 'learning', cursor,
        metadata={'since': marker or None, 'ledgers': len(new_ledgers), 'arsenal': len(new_arsenal)},
    )
    return {
        'since': marker or None,
        'cursor': cursor,
        'new_ledgers': new_ledgers,
        'new_arsenal': new_arsenal,
        'latest': latest,
        'counts': {'ledgers': len(new_ledgers), 'arsenal': len(new_arsenal)},
    }


@app.get('/api/governed/ledgers/{date}', tags=['agent'])
def governed_ledger(date: str):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', date):
        raise HTTPException(400, '日期格式必须是 YYYY-MM-DD')
    path = GOVERNED_LEDGER_DIR / f'{date}.json'
    if not path.is_file():
        raise HTTPException(404, '未找到该期治理日报')
    return load_governed_ledger(path)


@app.get('/api/governed/members')
def governed_members(live: int = Query(0, ge=0, le=1)):
    if not GOVERNED_MEMBER_FILE.is_file():
        raise HTTPException(404, '未找到治理后的群像档案')
    try:
        static = json.loads(GOVERNED_MEMBER_FILE.read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError) as exc:
        raise HTTPException(500, '治理后的群像档案不可读') from exc
    if not live:
        return static
    return _live_members(static)


def _live_members(static):
    """群像实时聚合：DB 当日/历史发言真值 + 静态治理富字段（语气/一句话/标签）。

    去重：归一化（NFKC+去emoji+去空白+小写）合并同名变体（剑峰/剑峰🐳 → 剑峰🐳），
    剔除纯符号非人行（@/ⁿ）。metrics 数字全部接 DB 真值，不写死。
    """
    try:
        static_profiles = static.get('profiles', []) if isinstance(static, dict) else []
    except Exception:
        static_profiles = []
    static_by_norm = {}
    for p in static_profiles:
        key = _member_norm(p.get('name') or '')
        if key and key not in static_by_norm:
            static_by_norm[key] = p
    c = db()
    today = datetime.datetime.now(CST).strftime('%Y-%m-%d')
    yesterday = (datetime.datetime.now(CST) - datetime.timedelta(days=1)).strftime('%Y-%m-%d')
    try:
        identity = "COALESCE(NULLIF(sender_name,'?'),sender)"
        rows = c.execute(
            f'''SELECT {identity} AS ident,
                       COUNT(*) AS n,
                       MIN(cst) AS first_cst,
                       MAX(cst) AS last_cst
                FROM messages GROUP BY {identity}'''
        ).fetchall()
        today_rows = c.execute(
            f'''SELECT {identity} AS ident FROM messages
                WHERE substr(COALESCE(cst,''),1,10)=? GROUP BY {identity}''',
            (today,),
        ).fetchall()
    except sqlite3.Error:
        return static
    finally:
        c.close()
    today_ident = {str(r['ident']) for r in today_rows}
    merged = {}
    for r in rows:
        ident = str(r['ident'] or '')
        if ident in ('系统公告', '群友·未知'):
            continue  # 系统事件/未解析占位：不计成员
        key = _member_norm(ident)
        if not key:
            continue  # 空/纯符号非人行
        base = merged.get(key, {'name': ident, 'msgs': 0, 'first_cst': None, 'last_cst': None, 'today': False})
        base['msgs'] += int(r['n'])
        base['first_cst'] = min(base['first_cst'] or r['first_cst'] or '', r['first_cst'] or base['first_cst'] or '')
        base['last_cst'] = max(base['last_cst'] or r['last_cst'] or '', r['last_cst'] or base['last_cst'] or '')
        base['today'] = base['today'] or ident in today_ident
        # 展示名优先用静态治理名（去重后保留最长/带 emoji 的变体）
        if len(ident) > len(base['name']) or base['name'] == base.get('_orig'):
            base['name'] = ident
        merged[key] = base
    profiles = []
    for key, m in merged.items():
        p = static_by_norm.get(key) or {}
        profiles.append({
            'name': m['name'],
            'role': p.get('role', ''),
            'msgs': m['msgs'],
            'ct': f"{m['msgs']} 条",
            'tags': p.get('tags', []),
            'tone': p.get('tone', 's'),
            'quote': p.get('quote', ''),
            'deep': p.get('deep', ''),
            'filter': p.get('filter', ['all']),
            'thin': p.get('thin', m['msgs'] <= 2),
            'avatar': p.get('avatar', ''),
            'last_active': (m['last_cst'] or '')[:10],
            'first_active': (m['first_cst'] or '')[:10],
            'today': m['today'],
        })
    profiles.sort(key=lambda x: (-x['msgs'], x['name']))
    today_active = sum(1 for p in profiles if p['today'])
    new_today = sum(1 for p in profiles if (p['first_active'] or '') == today)
    recent_active = sum(1 for p in profiles if (p['last_active'] or '') >= yesterday)
    return {
        'generated': datetime.datetime.now(CST).isoformat(timespec='seconds'),
        'count': len(profiles),
        'live': True,
        'metrics': {
            'today_active': today_active,
            'new_today': new_today,
            'recent_active': recent_active,
            'total': len(profiles),
        },
        'profiles': profiles,
    }


def _member_norm(value):
    """归一化成员名：NFKC + 去 emoji/变体选择符 + 去空白 + 小写；纯符号返回空（非人行剔除）。"""
    text = unicodedata.normalize('NFKC', str(value or ''))
    chars = []
    for ch in text:
        code = ord(ch)
        if 0x1F000 <= code <= 0x1FAFF or 0x2600 <= code <= 0x27BF or code in (0xFE0F, 0x200D, 0x20E3):
            continue
        if ch.isspace():
            continue
        chars.append(ch)
    key = ''.join(chars).lower()
    if not key or not any('\u3400' <= c <= '\u9fff' or c.isalnum() for c in key):
        return ''
    return key


def essay_title(name, author, content):
    if name and name.strip():
        return name.strip()
    first_line = next((line.strip() for line in (content or '').splitlines() if line.strip()), '')
    first_line = re.sub(r'^(\[[^\[\]]{1,8}\])+\s*', '', first_line)  # 剥掉开头的 [表情] 码
    return first_line[:40] or f'{author}的小作文'


def governed_essay(row):
    body = row['content'] or ''
    return {
        'title': essay_title(row['name'], row['author'], body),
        'author': row['author'],
        'date': (row['cst'] or '')[:10],
        'body': body,
        'word_count': len(re.sub(r'\s+', '', body)),
    }


# ── 站内检索：只检索治理产物；原始聊天永不进检索 ──
_SEARCH_CACHE = {'sig': None, 'docs': []}

def _plain(s):
    return ' '.join(_TAG_RE.sub(' ', str(s or '')).split())

def _search_docs():
    files = sorted(GOVERNED_LEDGER_DIR.glob('*.json')) if GOVERNED_LEDGER_DIR.exists() else []
    afiles = sorted(GOVERNED_ARSENAL_DIR.glob('*.json')) if GOVERNED_ARSENAL_DIR.exists() else []
    try:
        sig = tuple((str(p), p.stat().st_mtime) for p in files + afiles)
    except OSError:
        sig = None
    if sig is not None and _SEARCH_CACHE['sig'] == sig:
        return _SEARCH_CACHE['docs']
    docs = []
    def add(source, title, text, url, date='', issue=None, weight=1.0, **metadata):
        title, text = _plain(title), _plain(text)
        if title or text:
            doc = {'source': source, 'title': title, 'text': text, 'url': url,
                   'date': date, 'issue': issue, 'weight': weight}
            doc.update(metadata)
            docs.append(doc)
    for path in files:
        try:
            d = load_governed_ledger(path)
        except Exception:
            continue
        date, issue = d.get('date', ''), d.get('issue')
        base = f'/ledger/{date}/'
        add('日报', d.get('title', ''), d.get('lead', ''), base, date, issue, 1.4)
        for i, t in enumerate(d.get('themes') or []):
            voices = ' '.join(f"{v.get('a', '')} {v.get('v', '')}" for v in t.get('voices') or [])
            add('品评项', t.get('h', ''), ' '.join([t.get('body', ''), t.get('deep', ''), voices]),
                f'{base}#theme-{i + 1}', date, issue, 1.5)
        for e in d.get('events') or []:
            add('大事记', e.get('h', ''), e.get('d', ''), f'{base}#timeline', date, issue, 1.0)
        for q in d.get('quotes') or []:
            add('逐字摘录', q.get('a', ''), q.get('t', ''), f'{base}#quotes', date, issue, 1.0)
        for it in d.get('insights') or []:
            add('深潜', it.get('h', ''), it.get('body', ''), f'{base}#insights', date, issue, 1.2)
        for g in d.get('glossary') or []:
            add('黑话', g.get('term', ''), g.get('def', ''), f'{base}#glossary', date, issue, 1.6)
        for a in d.get('arsenal') or []:
            add('弹药', a.get('h', ''), a.get('body', ''), f'{base}#glossary', date, issue, 1.2)
        for dk in d.get('docket') or []:
            add('悬案', dk.get('h', ''), dk.get('d', ''), f'{base}#docket', date, issue, 1.1)
        for cl in d.get('clashes') or []:
            add('对撞', cl.get('h', ''), ' '.join([cl.get('sides', ''), cl.get('verdict', '')]),
                f'{base}#docket', date, issue, 1.1)
        for tn in d.get('tone_notes') or []:
            add('真伪鉴定', tn.get('h', ''), tn.get('body', ''), f'{base}#tone', date, issue, 1.0)
        for th in d.get('threads') or []:
            add('线索', th.get('title', ''), th.get('theme', ''),
                f"/archive/#thread-{th.get('id', '')}", date, issue, 1.5,
                thread_id=str(th.get('id') or ''))
    seen = set()
    for path in afiles:
        try:
            items = json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            continue
        if isinstance(items, dict):
            items = items.get('items') or []
        for it in items:
            iid = str(it.get('id') or '')
            if not iid or iid in seen:
                continue
            seen.add(iid)
            src = it.get('source') or {}
            text = ' '.join([
                str(it.get('one_line') or ''), str(it.get('why') or ''), str(it.get('for_whom') or ''),
                ' '.join(it.get('takeaways') or []), ' '.join(it.get('tags') or []),
                str(it.get('kind') or ''), str(src.get('name') or ''),
            ])
            add('军火库', it.get('title', ''), text, f'/arsenal/#kb-{iid}', str(it.get('collected_at') or ''), None, 1.3,
                thread_ids=[str(thread) for thread in (it.get('threads') or [])])
    if sig is not None:
        _SEARCH_CACHE['sig'] = sig
        _SEARCH_CACHE['docs'] = docs
    return docs

def _search_optional_user(request: Request):
    tok = request.headers.get('authorization', '').replace('Bearer ', '')
    if not tok:
        return None
    c = db()
    u = verify_token(c, tok)
    c.close()
    return u

def _excerpt_around(text, needles, width=76):
    pos = -1
    for n in needles:
        pos = text.casefold().find(n)
        if pos >= 0:
            break
    if pos < 0:
        return text[:width] + ('…' if len(text) > width else '')
    start = max(0, pos - width // 3)
    clip = text[start:start + width]
    return ('…' if start else '') + clip + ('…' if start + width < len(text) else '')


def _search_related(doc, docs):
    related = []
    if doc.get('source') == '线索':
        thread_id = doc.get('thread_id')
        if not thread_id:
            match = re.search(r'/archive/#thread-([^/?#]+)', doc.get('url', ''))
            thread_id = match.group(1) if match else ''
        for candidate in docs:
            if candidate.get('source') != '军火库':
                continue
            if thread_id and thread_id in set(candidate.get('thread_ids') or []):
                related.append({
                    'source': '军火库',
                    'title': candidate['title'],
                    'url': candidate['url'],
                })
    elif doc.get('source') == '黑话':
        for candidate in docs:
            if (
                candidate.get('source') == '线索'
                and candidate.get('date') == doc.get('date')
                and candidate.get('issue') == doc.get('issue')
            ):
                related.append({
                    'source': '线索',
                    'title': candidate['title'],
                    'url': candidate['url'],
                })
    return related[:3]

@app.get('/api/search')
def site_search(request: Request, q: str = Query('', max_length=80), limit: int = Query(24, ge=1, le=50)):
    docs = list(_search_docs())
    user = _search_optional_user(request)
    if user:
        c = db()
        for r in c.execute('SELECT cst,author,name,content FROM essays'):
            e = governed_essay(r)
            docs.append({'source': '窖藏', 'title': e['title'], 'text': _plain(e['body']),
                         'url': '/essays/', 'date': e['date'], 'issue': None, 'weight': 1.3})
        c.close()
        if GOVERNED_MEMBER_FILE.is_file():
            try:
                for p in json.loads(GOVERNED_MEMBER_FILE.read_text(encoding='utf-8')).get('profiles') or []:
                    docs.append({'source': '群像', 'title': str(p.get('name') or ''),
                                 'text': _plain(' '.join([str(p.get('role') or ''), str(p.get('quote') or ''), str(p.get('deep') or '')])),
                                 'url': '/members/', 'date': '', 'issue': None, 'weight': 1.2})
            except Exception:
                pass
    terms = [t.casefold() for t in q.split() if t.strip()][:6]
    if not terms:
        # 索引模式：给小白一个可浏览的目录（线索 + 最新黑话）
        threads, seen_t = [], set()
        for d in reversed(docs):
            if d['source'] == '线索' and d['url'] not in seen_t:
                seen_t.add(d['url'])
                threads.append({'title': d['title'], 'url': d['url'], 'issue': d['issue']})
        glossary = [{'title': d['title'], 'url': d['url']} for d in docs if d['source'] == '黑话']
        latest_date = max((d['date'] for d in docs if d['source'] == '黑话'), default='')
        glossary = [{'title': d['title'], 'url': d['url']} for d in docs
                    if d['source'] == '黑话' and d['date'] == latest_date][:18]
        return {'items': [], 'count': 0, 'gated_included': bool(user),
                'index': {'threads': threads[:14], 'glossary': glossary}}

    def rank(match_fn):
        out = []
        for d in docs:
            r = match_fn(d)
            if r is None:
                continue
            out.append((r * d['weight'], d))
        out.sort(key=lambda x: (-x[0], x[1]['date'] or ''))
        return out

    def match_and(d):
        score = 0.0
        tc, xc = d['title'].casefold(), d['text'].casefold()
        for t in terms:
            th, tb = tc.count(t), xc.count(t)
            if th == 0 and tb == 0:
                return None
            score += th * 3 + min(tb, 5)
        return score

    ranked = rank(match_and)
    fuzzy = False
    if not ranked and len(q.strip()) >= 3 and len(terms) == 1:
        # 模糊兜底：查询字符覆盖 75% 即算相关，二字连击加权排序
        qq = q.strip().casefold()
        chars = [ch for ch in dict.fromkeys(qq) if not ch.isspace()]
        grams = [qq[i:i + 2] for i in range(len(qq) - 1) if qq[i:i + 2].strip() and len(qq[i:i + 2]) == 2]
        need = max(2, math.ceil(len(chars) * 0.75))
        def match_fuzzy(d):
            tc = (d['title'] + ' ' + d['text']).casefold()
            chit = sum(1 for ch in chars if ch in tc)
            if chit < need:
                return None
            ghit = sum(1 for g in grams if g in tc)
            return ghit * 2.0 + chit
        ranked = rank(match_fuzzy)
        fuzzy = bool(ranked)
    items = []
    for _s, d in ranked[:limit]:
        item = {
            'source': d['source'], 'title': d['title'][:80],
            'excerpt': _excerpt_around(d['text'], terms), 'url': d['url'],
            'date': d['date'], 'issue': d['issue'],
        }
        related = _search_related(d, docs)
        if related:
            item['related'] = related
        items.append(item)
    return {'items': items, 'count': len(ranked), 'gated_included': bool(user), 'fuzzy': fuzzy}


# ── 文库：群里分享过的原件（PDF/EPUB/MD/HTML…），登录可取 ──
LIBRARY_DIR = ARCHIVE / 'FILES' / 'file'

@app.get('/api/library')
def library_list():
    items = []
    if LIBRARY_DIR.is_dir():
        for month_dir in sorted(LIBRARY_DIR.iterdir(), reverse=True):
            if not month_dir.is_dir() or not re.fullmatch(r'\d{4}-\d{2}', month_dir.name):
                continue
            for f in sorted(month_dir.iterdir()):
                if not f.is_file() or f.name.startswith('.'):
                    continue
                st = f.stat()
                items.append({
                    'name': f.name,
                    'ext': (f.suffix.lower().lstrip('.') or 'file'),
                    'size': st.st_size,
                    'month': month_dir.name,
                    'mtime': datetime.datetime.fromtimestamp(st.st_mtime, CST).strftime('%Y-%m-%d'),
                })
    items.sort(key=lambda x: (x['month'], x['mtime'], x['name']), reverse=True)
    return {'items': items, 'count': len(items)}


@app.get('/api/library/file')
def library_file(month: str = Query(...), name: str = Query(...)):
    if not re.fullmatch(r'\d{4}-\d{2}', month):
        raise HTTPException(400, '月份格式不对')
    if '/' in name or '\\' in name or '..' in name or name.startswith('.'):
        raise HTTPException(400, '文件名不合法')
    path = LIBRARY_DIR / month / name
    try:
        path = path.resolve(strict=True)
    except OSError:
        raise HTTPException(404, '文件不存在')
    if not str(path).startswith(str(LIBRARY_DIR.resolve()) + os.sep):
        raise HTTPException(400, '路径不合法')
    resp = FileResponse(path, filename=name)
    resp.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    return resp


@app.get('/api/governed/essays')
def governed_essays(limit: int = Query(100, ge=1, le=300)):
    c = db()
    rows = c.execute(
        'SELECT cst,author,name,content FROM essays ORDER BY cst DESC LIMIT ?',
        (limit,),
    ).fetchall()
    c.close()
    return {'items': [governed_essay(row) for row in rows]}


def contains_query(value, needle):
    return needle in str(value or '').casefold()


def excerpt(value, needle, width=120):
    text = re.sub(r'\s+', ' ', str(value or '')).strip()
    pos = text.casefold().find(needle)
    start = max(0, pos - 24) if pos >= 0 else 0
    clipped = text[start:start + width]
    return ('…' if start else '') + clipped + ('…' if start + width < len(text) else '')


@app.get('/api/governed/search', tags=['agent'])
def governed_search(q: str = Query(..., min_length=1, max_length=100), limit: int = Query(50, ge=1, le=100)):
    needle = q.strip().casefold()
    if not needle:
        raise HTTPException(400, '搜索词不能为空')
    items = []
    if GOVERNED_LEDGER_DIR.exists():
        for path in sorted(GOVERNED_LEDGER_DIR.glob('*.json'), reverse=True):
            data = load_governed_ledger(path)
            date = data.get('date')
            issue = data.get('issue')
            for theme in data.get('themes') or []:
                haystack = ' '.join(str(theme.get(k) or '') for k in ('h', 'body', 'deep'))
                if contains_query(haystack, needle):
                    items.append({
                        'type': 'ledger_theme', 'date': date, 'issue': issue,
                        'title': theme.get('h'), 'author': None,
                        'excerpt': excerpt(haystack, needle),
                    })
            for quote in data.get('quotes') or []:
                haystack = ' '.join(str(quote.get(k) or '') for k in ('t', 'a'))
                if contains_query(haystack, needle):
                    items.append({
                        'type': 'ledger_quote', 'date': date, 'issue': issue,
                        'title': '逐字摘录', 'author': quote.get('a'),
                        'excerpt': excerpt(quote.get('t'), needle),
                    })
    c = db()
    pattern = f'%{q.strip()}%'
    rows = c.execute(
        '''SELECT cst,author,name,content FROM essays
           WHERE name LIKE ? OR author LIKE ? OR content LIKE ?
           ORDER BY cst DESC LIMIT ?''',
        (pattern, pattern, pattern, limit),
    ).fetchall()
    c.close()
    for row in rows:
        essay = governed_essay(row)
        items.append({
            'type': 'essay', 'date': essay['date'], 'issue': None,
            'title': essay['title'], 'author': essay['author'],
            'excerpt': excerpt(essay['body'], needle),
        })
    items = items[:limit]
    return {'query': q.strip(), 'total': len(items), 'items': items}

@app.get('/api/ledgers')
def ledgers():
    out = []
    if LEDGER_DIR.exists():
        for f in sorted(LEDGER_DIR.glob('*.html'), reverse=True):
            out.append({'name':f.stem,'path':f'/ledgers/{f.name}','size':f.stat().st_size})
    return {'items':out}

@app.get('/ledgers/{fn}')
def ledger_file(fn:str):
    p = LEDGER_DIR / fn
    if not p.exists() or not fn.endswith('.html'): raise HTTPException(404)
    return FileResponse(p, media_type='text/html')

@app.post('/admin/import/{day}')
def admin_import(day: str, request: Request):
    if not re.fullmatch(r'\d{4}-\d{2}-\d{2}', day):
        raise HTTPException(400, '日期格式应为 YYYY-MM-DD')
    if not admin_basic_auth_ok(request):
        raise HTTPException(401, '未授权', headers={'WWW-Authenticate': 'Basic realm="xfsite import"'})
    n = import_day(ARCHIVE / 'RAW' / day, target_day=day)
    return {'imported': n}

class SPAStatic(StaticFiles):
    async def get_response(self,path,scope):
        try:
            response = await super().get_response(path,scope)
        except StarletteHTTPException as exc:
            if exc.status_code != 404:
                raise
            response = await super().get_response('index.html',scope)
        if 'text/html' not in response.headers.get('content-type', '').lower():
            return response
        file_path = getattr(response, 'path', None)
        if file_path:
            body = Path(file_path).read_bytes()
        else:
            chunks = []
            async for chunk in response.body_iterator:
                chunks.append(chunk)
            body = b''.join(chunks)
        body = re.sub(
            rb'(?:wxid_[A-Za-z0-9_-]{4,}|QQ\d{5,}|q\d{6,})',
            '群友'.encode('utf-8'),
            body,
        )
        headers = dict(response.headers)
        headers.pop('content-length', None)
        headers.pop('content-encoding', None)
        headers.pop('etag', None)
        headers.pop('last-modified', None)
        return Response(
            body,
            status_code=response.status_code,
            headers=headers,
            media_type='text/html; charset=utf-8',
        )


class UploadStatic(StaticFiles):
    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers['X-Content-Type-Options'] = 'nosniff'
        ext = Path(path).suffix.lower()
        if ext in {'.svg', '.pdf', '.md', '.txt', '.zip'}:
            response.headers['Content-Disposition'] = f'attachment; filename="{Path(path).name}"'
            response.headers['Content-Security-Policy'] = "default-src 'none'; sandbox"
        return response


init_db()
ensure_gatekeeper_schema(DB)
if os.environ.get('XF_SKIP_GATEKEEPER_WORKER') != '1':
    start_gatekeeper_worker(DB)
app.include_router(hot_router)
app.mount('/uploads', UploadStatic(directory=str(UPLOAD_DIR)), name='uploads')
app.mount('/', SPAStatic(directory=str(STATIC), html=True), name='static')
