#!/usr/bin/env python3
"""Run external curation under an exclusive lock; publish a truthful atomic snapshot."""
import argparse
import fcntl
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))
from app.external_article import fetch_article
from app.external_curation import Model, Pipeline, connect, validate_policy
from collect_external_sources import atomic_write


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--input', type=Path, default=ROOT / 'site/public/data/external-knowledge.json')
    parser.add_argument('--output', type=Path, default=ROOT / 'site/public/data/external-curated.json')
    parser.add_argument('--policy', type=Path, default=ROOT / 'config/external-curation.json')
    parser.add_argument('--state', type=Path, default=Path(os.environ.get('EXTERNAL_CURATION_STATE', '/opt/xfsite/data/external-curation/state.db')))
    parser.add_argument('--retry-failed', action='store_true', help='Reset failed attempts under the lock; stage caches and budgets remain in force')
    args = parser.parse_args()
    args.state.parent.mkdir(parents=True, exist_ok=True)
    with args.state.with_suffix('.lock').open('a') as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            print(json.dumps({'status': 'locked'}))
            return 75
        db = None
        try:
            policy = json.loads(args.policy.read_text())
            validate_policy(policy)
            source = json.loads(args.input.read_text())
            db = connect(args.state)
            if args.retry_failed:
                db.execute("UPDATE articles SET attempts=0,next_retry=NULL WHERE state='failed'")
                db.commit()
            pipeline = Pipeline(db, policy, Model(policy), datetime.now(timezone.utc), enricher=fetch_article)
            run = pipeline.run(source)
            snapshot = pipeline.snapshot(run)
            atomic_write(args.output, json.dumps(snapshot, ensure_ascii=False, indent=2) + '\n')
            print(json.dumps({**run, 'events': len(snapshot['events']), 'editions': len(snapshot['editions'])}))
            return 0 if run['status'] == 'ok' else 1
        except Exception as exc:
            # Preserve old selections but never let an old success masquerade as this run.
            if args.output.exists():
                try:
                    previous = json.loads(args.output.read_text())
                    previous['run'] = {'status': 'failed', 'attemptedAt': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'), 'counts': {}, 'failedSources': 0}
                    atomic_write(args.output, json.dumps(previous, ensure_ascii=False, indent=2) + '\n')
                except Exception:
                    pass
            print(json.dumps({'status': 'failed', 'errorClass': type(exc).__name__}))
            return 2
        finally:
            if db is not None:
                db.close()


if __name__ == '__main__':
    raise SystemExit(main())
