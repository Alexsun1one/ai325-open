#!/usr/bin/env python3
"""幂等写入 site/content 已有事实对应的三项活动。"""

try:
    from .main import db
except ImportError:
    from main import db


EVENTS = [
    {
        'slug': 'vi-design-2026-08-23',
        'title': '第一期群基建：给先锋队做一套 VI',
        'kind': 'contest',
        'status': 'open',
        'starts_at': '2026-08-23T17:25:00+08:00',
        'ends_at': None,
        'rules_md': '把一个模糊的 VI 需求跑成交付物；已有记录包括纸片人名片、钢印质感与字体修改。',
        'reward': '50 · 覆盖 TOKEN 成本',
        'cover_path': '/art/poster-vi.png',
    },
    {
        'slug': 'onboarding-essay',
        'title': '小作文入群仪式',
        'kind': 'essay',
        'status': 'open',
        'starts_at': '2026-08-22T23:16:00+08:00',
        'ends_at': None,
        'rules_md': '介绍自己、对 AI 的理解、擅长什么、想了解什么、对未来的展望。入群即交，跨期挂账。',
        'reward': '',
        'cover_path': '/art/poster-essay.png',
    },
    {
        'slug': 'badge-wall',
        'title': '纪念徽章墙',
        'kind': 'custom',
        'status': 'upcoming',
        'starts_at': None,
        'ends_at': None,
        'rules_md': '12 枚铭牌的触发条件已定义；获得者计算尚未接线，因此当前不宣称任何人已点亮。',
        'reward': '',
        'cover_path': '/art/poster-badges.png',
    },
]


def seed_events() -> int:
    connection = db()
    try:
        for event in EVENTS:
            connection.execute(
                '''INSERT INTO events(slug,title,kind,status,starts_at,ends_at,rules_md,reward,cover_path,created_by)
                   VALUES(:slug,:title,:kind,:status,:starts_at,:ends_at,:rules_md,:reward,:cover_path,'seed:site/content')
                   ON CONFLICT(slug) DO UPDATE SET
                     title=excluded.title,kind=excluded.kind,status=excluded.status,
                     starts_at=excluded.starts_at,ends_at=excluded.ends_at,
                     rules_md=excluded.rules_md,reward=excluded.reward,cover_path=excluded.cover_path''',
                event,
            )
        connection.commit()
        return len(EVENTS)
    finally:
        connection.close()


if __name__ == '__main__':
    print(f'seeded {seed_events()} events')
