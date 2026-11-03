"""备份后定向整理旧初始化文案；默认只预览，--apply 才写入。不会删除记录。"""
import argparse
import json
import sqlite3
from collections import Counter
from contextlib import closing
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OLD_DESCRIPTION = '独立验收库中的虚构竞赛。用于演示周、王、陈的组队报名流程。'
NEW_DESCRIPTION = '围绕校园服务需求完成软件作品，提交功能说明、实现方案与测试结果。'
OLD_STATEMENT = '虚构参赛说明，仅用于本机课程验收。'
NEW_STATEMENT = '计划开发校园竞赛信息与组队管理作品，提交功能说明和测试结果。'
SUPPLEMENT = ' 已补充六个模块的实现和测试。'
BASE_SEEDS = [
    (1, '校园软件创意设计赛', '软件开发', '围绕校园真实问题，设计并实现一个可演示的软件原型。此条为课程演示数据。', '围绕校园问题，设计并实现一个软件原型。', 3, 3),
    (2, '大学生数据应用挑战赛', '数据分析', '选择一个公开数据集完成分析，提交分析说明和作品。此条为课程演示数据。', '选择一个公开数据集完成分析，提交分析说明和作品。', 1, 3),
    (3, '校园交互设计赛', '创新设计', '以校园服务为主题完成交互原型与设计说明。此条为课程演示数据。', '以校园服务为主题完成交互原型与设计说明。', 1, 4),
]
ACCEPTANCE_SEEDS = [
    (4, 1, '待审核', '校园应用开发挑战赛', '星火开发队'),
    (5, 2, '待补充', '校园服务创新赛', '青禾创作队'),
    (6, 3, '已通过', '校园软件实践赛', '远航实践队'),
]


def plan_changes(db):
    """只匹配已知编号、完整来源指纹和字段原值；任何自定义字段都保持原样。"""
    changes = []

    def matches(table, row_id, expected):
        row = db.execute(f'SELECT * FROM {table} WHERE id=?', (row_id,)).fetchone()
        return row is not None and all(row[key] == value for key, value in expected.items())

    def change(table, row_id, field, old, new):
        if matches(table, row_id, {field: old}):
            changes.append((table, row_id, field, old, new))

    def registration_text(team_id, replacements):
        tables = {r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        for record in db.execute('SELECT id FROM registrations WHERE team_id=?', (team_id,)):
            for field, pairs in replacements.items():
                for old, new in pairs:
                    change('registrations', record['id'], field, old, new)
            if 'registration_history' in tables:
                for event in db.execute('SELECT id,actor_id FROM registration_history WHERE registration_id=?', (record['id'],)):
                    for field, pairs in replacements.items():
                        for old, new in pairs:
                            change('registration_history', event['id'], field, old, new)
                    if event['actor_id'] == 1 and seeded_admin:
                        change('registration_history', event['id'], 'actor_name', '演示管理员', '管理员')

    seeded_admin = matches('users', 1, {'username': 'admin', 'role': 'admin', 'name': '演示管理员',
                                       'major': '', 'grade': '2024级', 'skills': ''})
    if seeded_admin:
        change('users', 1, 'name', '演示管理员', '管理员')
    # 核对队长和成员的身份，不覆盖这些账号的专业、技能、密码等资料。
    seed_members = all(matches('users', uid, {'username': username, 'role': 'student'})
                       for uid, username in [(2, 'zhou'), (3, 'wang'), (4, 'chen')])

    def known_members(team_id):
        return seed_members and {r[0] for r in db.execute('SELECT user_id FROM team_members WHERE team_id=?', (team_id,))} == {2, 3, 4}

    for cid, title, category, old_desc, new_desc, minimum, maximum in BASE_SEEDS:
        if not matches('competitions', cid, {'title': title + '（演示）', 'category': category,
                                             'description': old_desc, 'min_members': minimum,
                                             'max_members': maximum, 'official_url': ''}):
            continue
        change('competitions', cid, 'title', title + '（演示）', title)
        change('competitions', cid, 'description', old_desc, new_desc)
        # 原业务库在2026-10-20建立的已知课程实践队，只修改两段固定报名文案。
        if cid == 1 and known_members(1) and matches('teams', 1, {
            'competition_id': 1, 'captain_id': 2, 'name': '周王陈 · 课程实践队',
            'intro': '围绕校园竞赛信息与组队需求，共同完成软件工程课程项目。',
            'requirements': '欢迎熟悉需求分析、页面开发或测试的同学加入。',
            'created_at': '2026-10-20T20:40:20',
        }):
            registration_text(1, {
                'statement': [('课程演示报名：开发大学生竞赛信息与组队管理系统，三人分别负责用户竞赛、队伍招募和报名审核。',
                               '开发大学生竞赛信息与组队管理系统，三人分别负责用户竞赛、队伍招募和报名审核。')],
                'review_note': [('课程演示审核通过，三名成员报名信息齐全。', '三名成员报名信息齐全，报名审核通过。')],
            })

    for cid, tid, label, title, team_name in ACCEPTANCE_SEEDS:
        old_title = f'验收演示 · {label}软件实践赛'
        if not matches('competitions', cid, {'title': old_title, 'category': '软件开发',
                                             'description': OLD_DESCRIPTION, 'min_members': 3,
                                             'max_members': 3, 'official_url': ''}):
            continue
        change('competitions', cid, 'title', old_title, title)
        change('competitions', cid, 'description', OLD_DESCRIPTION, NEW_DESCRIPTION)
        old_name = f'周王陈 · {label}演示队'
        if not known_members(tid) or not matches('teams', tid, {
            'competition_id': cid, 'captain_id': 2, 'name': old_name,
            'intro': '三名同学的课程实践队伍',
            'requirements': '周负责用户竞赛，王负责队伍招募，陈负责报名审核',
        }):
            continue
        change('teams', tid, 'name', old_name, team_name)
        change('teams', tid, 'intro', '三名同学的课程实践队伍', '围绕校园需求开展软件设计与开发。')
        change('teams', tid, 'requirements', '周负责用户竞赛，王负责队伍招募，陈负责报名审核', '欢迎愿意参与需求分析、开发与测试的同学。')
        for row in db.execute('SELECT id FROM applications WHERE team_id=? AND user_id IN (3,4)', (tid,)):
            change('applications', row['id'], 'message', '申请加入课程演示队', '希望参与软件开发与测试。')
        registration_text(tid, {
            'contact_name': [('周（演示）', '周')],
            'statement': [(OLD_STATEMENT, NEW_STATEMENT), (OLD_STATEMENT + SUPPLEMENT, NEW_STATEMENT + SUPPLEMENT)],
            'review_note': [('请补充作品范围说明（演示）', '请补充作品范围说明，列出拟实现的功能。'),
                            ('材料完整（演示）', '材料完整，报名审核通过。')],
        })
    return changes


def migrate(path, apply=False, backup_dir=None):
    path = Path(path).resolve()
    with closing(sqlite3.connect(path.as_uri() + '?mode=rw', uri=True, timeout=15)) as db:
        db.row_factory = sqlite3.Row
        db.execute('PRAGMA foreign_keys=ON')
        # 写锁覆盖指纹检查、备份、更新，防止同时提交的用户修改被覆盖。
        db.execute('BEGIN IMMEDIATE')
        try:
            changes = plan_changes(db)
            report = {'database': str(path), 'applied': apply, 'fields': len(changes),
                      'by_table': dict(Counter(c[0] for c in changes)), 'backup': None}
            if apply and changes:
                directory = Path(backup_dir or ROOT / 'output' / 'backups').resolve()
                directory.mkdir(parents=True, exist_ok=True)
                backup = directory / f'{path.stem}-before-content-{datetime.now():%Y%m%d-%H%M%S-%f}.db'
                # 独立只读连接在源库写锁内取得一致快照；备份完成才执行任何 UPDATE。
                with closing(sqlite3.connect(path.as_uri() + '?mode=ro', uri=True)) as src:
                    with closing(sqlite3.connect(backup)) as dst:
                        src.backup(dst)
                        if dst.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
                            raise RuntimeError('备份完整性校验失败，未更新源库')
                report['backup'] = str(backup)
                for table, row_id, field, old, new in changes:
                    db.execute(f'UPDATE {table} SET {field}=? WHERE id=? AND {field}=?', (new, row_id, old))
                if db.execute('PRAGMA integrity_check').fetchone()[0] != 'ok' or db.execute('PRAGMA foreign_key_check').fetchall():
                    raise RuntimeError('更新后完整性校验失败，已回滚')
                db.commit()
            else:
                db.rollback()
            return report
        except Exception:
            db.rollback()
            raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, action='append', help='可重复指定；默认检查app.db和acceptance.db')
    parser.add_argument('--apply', action='store_true', help='先备份，再应用定向更新')
    args = parser.parse_args()
    paths = args.db or [p for p in (ROOT / 'data' / 'app.db', ROOT / 'data' / 'acceptance.db') if p.exists()]
    for path in paths:
        print(json.dumps(migrate(path, args.apply), ensure_ascii=False))


if __name__ == '__main__':
    main()
