#!/usr/bin/env python3
"""按 messages 事实重建小作文，并把消息来源挂到 onboarding-essay。

默认只读预览；生产修正必须显式传 --replace，脚本会先生成 SQLite backup。
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sqlite3
import sys
from pathlib import Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', required=True, type=Path, help='xf.db 路径')
    parser.add_argument('--replace', action='store_true', help='备份后替换 pipeline 生成的旧 essays')
    parser.add_argument('--backup', type=Path, help='--replace 时的 SQLite backup 路径')
    parser.add_argument('--json', action='store_true', dest='as_json', help='输出机器可读 JSON')
    return parser.parse_args()


def snapshot(connection: sqlite3.Connection) -> dict:
    long_rows = connection.execute(
        '''SELECT sender,COALESCE(NULLIF(sender_name,''),sender) AS sender_name,COUNT(*) AS count
           FROM messages WHERE LENGTH(content)>200 GROUP BY sender,sender_name ORDER BY count DESC,sender'''
    ).fetchall()
    essays = connection.execute(
        '''SELECT author,COUNT(*) AS count FROM essays GROUP BY author ORDER BY count DESC,author'''
    ).fetchall()
    fan = connection.execute(
        '''SELECT id,cst,sender,sender_name,LENGTH(content) AS length,content
           FROM messages
           WHERE sender='fanzhenhua666' OR sender_name LIKE '%范振华%'
           ORDER BY create_time,id'''
    ).fetchall()
    fan_essays = connection.execute(
        '''SELECT id,cst,author,LENGTH(content) AS length,content,source_message_ids
           FROM essays WHERE author LIKE '%范振华%' ORDER BY cst,id'''
    ).fetchall()
    activity = connection.execute(
        '''SELECT e.slug,COUNT(ai.id) AS count
           FROM events e LEFT JOIN essay_activity_items ai
             ON ai.event_id=e.id AND ai.status='accepted'
           WHERE e.slug='onboarding-essay' GROUP BY e.slug'''
    ).fetchone()
    return {
        'long_messages': [dict(row) for row in long_rows],
        'long_message_total': sum(row['count'] for row in long_rows),
        'essays_by_author': [dict(row) for row in essays],
        'essay_total': connection.execute('SELECT COUNT(*) FROM essays').fetchone()[0],
        'fanzhenhua_messages': [dict(row) for row in fan],
        'fanzhenhua_essays': [dict(row) for row in fan_essays],
        'onboarding_activity_count': activity['count'] if activity else 0,
    }


def compact(value: str, limit: int = 80) -> str:
    value = ' '.join(str(value or '').split())
    return value[:limit] + ('…' if len(value) > limit else '')


def source_coverage(connection: sqlite3.Connection) -> dict:
    expected = {
        row['id'] for row in connection.execute('SELECT id FROM messages WHERE LENGTH(content)>200')
    }
    covered = set()
    for row in connection.execute("SELECT source_message_ids FROM essays WHERE source_kind='message'"):
        try:
            covered.update(json.loads(row['source_message_ids'] or '[]'))
        except (TypeError, json.JSONDecodeError):
            continue
    return {
        'expected_long_message_ids': len(expected),
        'covered_long_message_ids': len(expected & covered),
        'missing_long_message_ids': sorted(expected - covered),
        'orphan_source_ids': sorted(covered - expected),
    }


def main() -> int:
    args = parse_args()
    db_path = args.db.expanduser().resolve()
    if not db_path.is_file():
        raise SystemExit(f'数据库不存在: {db_path}')
    os.environ['XF_DATA_DIR'] = str(db_path.parent)
    # app.main 在导入时会挂载静态目录；脚本只做数据修正，数据库目录即可作为安全占位。
    os.environ.setdefault('XF_STATIC_DIR', str(db_path.parent))
    # 复用应用中唯一的微信 XML 清洗、身份映射与候选生成实现。
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from app import main as app_main  # noqa: PLC0415
    app_main.DB = db_path
    app_main.DATA_DIR = db_path.parent
    app_main.ARCHIVE = db_path.parent / 'archive'
    app_main.init_db()

    connection = sqlite3.connect(db_path)
    connection.row_factory = sqlite3.Row
    before = snapshot(connection)
    candidates = app_main.essay_candidates(connection)
    result = {
        'db': str(db_path),
        'mode': 'replace' if args.replace else 'preview',
        'before': before,
        'candidate_total': len(candidates),
        'candidate_by_author': {},
        'coverage_before': source_coverage(connection),
    }
    for candidate in candidates:
        result['candidate_by_author'][candidate['author']] = result['candidate_by_author'].get(candidate['author'], 0) + 1

    if args.replace:
        stamp = dt.datetime.now().strftime('%Y%m%d-%H%M%S')
        backup_path = (args.backup or db_path.with_name(f'{db_path.stem}.pre-essays-fix-{stamp}{db_path.suffix}')).resolve()
        if backup_path == db_path:
            raise SystemExit('--backup 不能与 --db 相同')
        backup_path.parent.mkdir(parents=True, exist_ok=True)
        source = sqlite3.connect(db_path)
        target = sqlite3.connect(backup_path)
        try:
            source.backup(target)
        finally:
            target.close()
            source.close()
        result['backup'] = str(backup_path)
        result['rebuild'] = app_main.rebuild_essays(connection, replace=True)
        connection.commit()
        result['after'] = snapshot(connection)
        result['coverage_after'] = source_coverage(connection)
    else:
        result['after'] = None
        result['coverage_after'] = None
    connection.close()

    if args.as_json:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"mode={result['mode']} long_messages={before['long_message_total']} candidates={result['candidate_total']}")
        if args.replace:
            print(f"backup={result['backup']}")
            print(f"essays {before['essay_total']} -> {result['after']['essay_total']}; "
                  f"onboarding-essay {before['onboarding_activity_count']} -> {result['after']['onboarding_activity_count']}")
            coverage = result['coverage_after']
            print(f"long-message coverage {coverage['covered_long_message_ids']}/{coverage['expected_long_message_ids']}; "
                  f"missing={coverage['missing_long_message_ids']}")
        print('candidate_by_author=' + json.dumps(result['candidate_by_author'], ensure_ascii=False, sort_keys=True))
        for row in (result['after'] or before)['fanzhenhua_messages']:
            print(f"范振华消息 {row['cst']} sender={row['sender']} len={row['length']} 首行={compact(row['content'])}")
        for row in (result['after'] or before)['fanzhenhua_essays']:
            print(f"范振华essay {row['cst']} len={row['length']} 首行={compact(row['content'])} source={row['source_message_ids']}")
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
