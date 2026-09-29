"""Versioned, independent checkpoints for the two public learning feeds."""
import base64
import datetime
import json

CST = datetime.timezone(datetime.timedelta(hours=8))
PREFIX = 'learn1.'


def legacy_date(value: str) -> str:
    if not value:
        return ''
    parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
    if parsed.tzinfo is not None:
        parsed = parsed.astimezone(CST)
    return parsed.date().isoformat()


def decode(value: str | None) -> dict:
    value = (value or '').strip()
    if len(value) > 2048:
        raise ValueError('学习游标过长')
    if not value.startswith(PREFIX):
        floor = legacy_date(value)
        return {'base': floor, 'ledger': floor, 'arsenal': None, 'at': value}
    try:
        raw = value[len(PREFIX):]
        data = json.loads(base64.urlsafe_b64decode(raw + '=' * (-len(raw) % 4)))
        if not isinstance(data, dict) or set(data) != {'base', 'ledger', 'arsenal', 'at'}:
            raise ValueError('invalid cursor fields')
        for field in ('base', 'ledger', 'at'):
            if not isinstance(data[field], str):
                raise ValueError('invalid cursor value')
            if data[field]:
                legacy_date(data[field])
        key = data['arsenal']
        if key is not None and (not isinstance(key, list) or len(key) != 2 or any(not isinstance(v, str) or len(v) > 512 for v in key)):
            raise ValueError('invalid arsenal position')
        return data
    except (ValueError, TypeError, KeyError, UnicodeError) as error:
        raise ValueError('无效的学习游标') from error


def encode(data: dict) -> str:
    raw = json.dumps(data, separators=(',', ':'), ensure_ascii=False).encode()
    return PREFIX + base64.urlsafe_b64encode(raw).decode().rstrip('=')


def arsenal_position(item: dict) -> tuple[str, str]:
    value = str(item.get('created_at') or item.get('collected_at') or '')
    if value:
        try:
            parsed = datetime.datetime.fromisoformat(value.replace('Z', '+00:00'))
            if parsed.tzinfo is None:
                parsed = parsed.replace(tzinfo=CST)
            value = parsed.astimezone(CST).isoformat(timespec='microseconds')
        except ValueError:
            # Undated legacy material remains discoverable, ordered by stable ID.
            value = ''
    return value, str(item.get('id') or '')


def last_read_at(value: str | None) -> str | None:
    if value and value.startswith(PREFIX):
        try:
            return decode(value)['at'] or None
        except ValueError:
            return None
    return value
