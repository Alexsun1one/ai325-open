"""Normalize edition ranks and numeric cross-references in publication staging."""
import json
import os
from pathlib import Path
import re
import tempfile


def normalize_issues(directory: str, incoming: str) -> int:
    root = Path(directory)
    rows = {}
    for path in root.glob('*.json'):
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', path.stem):
            row = json.loads(path.read_text(encoding='utf-8'))
            if row.get('date') != path.stem:
                raise ValueError('edition date does not match filename')
            rows[path.stem] = (path, row)
    ranks = {day: index + 1 for index, day in enumerate(sorted(set(rows) | {incoming}))}
    mapping = {}
    # An interrupted legacy backfill may already have assigned incoming the
    # same rank as its successor. Only that known incoming collision is repairable.
    for day, (_, row) in rows.items():
        if day == incoming:
            continue
        old = row['issue']
        if old in mapping:
            raise ValueError('ambiguous existing edition numbers')
        mapping[old] = ranks[day]
    updates = []
    for day, (path, row) in rows.items():
        before = json.dumps(row, ensure_ascii=False)
        old_issue = row['issue']
        row['issue'] = ranks[day]
        def reference(value):
            if day == incoming and value == old_issue:
                return ranks[day]
            return mapping.get(value, value)
        for thread in row.get('threads', []):
            for key in ('first_issue', 'prev_issue'):
                if thread.get(key) is not None:
                    thread[key] = reference(thread[key])
        for item in row.get('docket', []):
            if item.get('carried_from') is not None:
                item['carried_from'] = reference(item['carried_from'])
        if json.dumps(row, ensure_ascii=False) != before:
            updates.append((path, row))
    for path, row in updates:
        fd, temporary = tempfile.mkstemp(dir=root, prefix='.issue-', suffix='.tmp')
        try:
            with os.fdopen(fd, 'w', encoding='utf-8') as handle:
                json.dump(row, handle, ensure_ascii=False, indent=1)
                handle.flush()
                os.fsync(handle.fileno())
            os.replace(temporary, path)
        finally:
            if os.path.exists(temporary):
                os.unlink(temporary)
    return ranks[incoming]
