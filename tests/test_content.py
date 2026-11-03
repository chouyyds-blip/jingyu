"""初始化文案整理：验证备份、业务事实保留、精确范围及重复执行。"""
import json
import shutil
import sqlite3
import subprocess
import sys
import unittest
import uuid
from contextlib import closing
from pathlib import Path

from support import server, scratch_path
from tools import migrate_seed_content as migration


class ContentMigrationTest(unittest.TestCase):
    def setUp(self):
        self.folder = scratch_path() / ('content-' + uuid.uuid4().hex)
        self.folder.mkdir(parents=True)
        self.path = self.folder / 'legacy.db'
        previous = server.DB_PATH
        try:
            server.DB_PATH = self.path
            server.initialize()
        finally:
            server.DB_PATH = previous
        with self.connect() as db:
            db.execute("UPDATE users SET name='演示管理员' WHERE id=1")
            for cid, title, _, old_desc, _, _, _ in migration.BASE_SEEDS:
                db.execute('UPDATE competitions SET title=?,description=? WHERE id=?', (title + '（演示）', old_desc, cid))
            for cid, tid, label, _, _ in migration.ACCEPTANCE_SEEDS:
                db.execute('''INSERT INTO competitions
                    (id,title,category,description,deadline,min_members,max_members)
                    VALUES (?,?,'软件开发',?,'2099-12-31',3,3)''',
                           (cid, f'验收演示 · {label}软件实践赛', migration.OLD_DESCRIPTION))
                db.execute('''INSERT INTO teams(id,competition_id,captain_id,name,intro,requirements)
                    VALUES (?,?,2,?,'三名同学的课程实践队伍','周负责用户竞赛，王负责队伍招募，陈负责报名审核')''',
                           (tid, cid, f'周王陈 · {label}演示队'))
                for uid in (2, 3, 4):
                    db.execute('INSERT INTO team_members VALUES (?,?)', (tid, uid))
                    if uid != 2:
                        db.execute("INSERT INTO applications(team_id,user_id,message,status) VALUES (?,?,'申请加入课程演示队','approved')", (tid, uid))
                statuses = [('submitted', 'pending', ''), ('rejected', 'rejected', '请补充作品范围说明（演示）'),
                            ('resubmitted', 'pending', ''), ('approved', 'approved', '材料完整（演示）')]
                events = statuses[:{1: 1, 2: 2, 3: 4}[tid]]
                action, status, note = events[-1]
                statement = migration.OLD_STATEMENT + (migration.SUPPLEMENT if tid == 3 else '')
                db.execute('''INSERT INTO registrations(id,team_id,contact_name,contact_phone,statement,status,review_note)
                    VALUES (?,?,'周（演示）','13800000000',?,?,?)''', (tid, tid, statement, status, note))
                for action, status, note in events:
                    actor = 1 if action in ('rejected', 'approved') else 2
                    record = dict(db.execute('SELECT * FROM registrations WHERE id=?', (tid,)).fetchone())
                    record.update(status=status, review_note=note, statement=migration.OLD_STATEMENT + (migration.SUPPLEMENT if action in ('resubmitted', 'approved') else ''))
                    server.registrations._history(db, record, action, actor, '演示管理员' if actor == 1 else '周',
                                                  '2026-11-03T16:02:12', server.registrations._members(db, tid))

    def connect(self):
        db = sqlite3.connect(self.path)
        db.row_factory = sqlite3.Row
        self.addCleanup(db.close)
        return db

    def snapshot(self, path=None):
        with closing(sqlite3.connect(path or self.path)) as db:
            tables = [r[0] for r in db.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
            return {t: db.execute(f'SELECT * FROM {t} ORDER BY id' if t != 'team_members' else f'SELECT * FROM {t} ORDER BY team_id,user_id').fetchall() for t in tables}

    def tearDown(self):
        # Windows删除前关闭本测试注册的连接。
        self.doCleanups()
        if self.folder.resolve().parent != scratch_path():
            raise RuntimeError('测试清理路径越界')
        shutil.rmtree(self.folder)

    def test_backup_history_and_business_facts_survive_idempotent_migration(self):
        before = self.snapshot()
        with self.connect() as db:
            facts = [tuple(r) for r in db.execute('SELECT id,registration_id,action,status,actor_id,occurred_at,members_json FROM registration_history')]
            records = [tuple(r) for r in db.execute('SELECT id,team_id,status,created_at,updated_at,contact_phone FROM registrations')]
        report = migration.migrate(self.path, True, self.folder / 'backups')
        self.assertGreater(report['fields'], 0)
        self.assertEqual(self.snapshot(report['backup']), before)
        with self.connect() as db:
            self.assertEqual([tuple(r) for r in db.execute('SELECT id,registration_id,action,status,actor_id,occurred_at,members_json FROM registration_history')], facts)
            self.assertEqual([tuple(r) for r in db.execute('SELECT id,team_id,status,created_at,updated_at,contact_phone FROM registrations')], records)
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
            self.assertEqual([r[0] for r in db.execute('SELECT name FROM teams ORDER BY id')], ['星火开发队', '青禾创作队', '远航实践队'])
        after = self.snapshot()
        for table in ('team_members', 'users'):
            if table == 'users':
                self.assertEqual([row[:3] + row[4:] for row in before[table]], [row[:3] + row[4:] for row in after[table]])
            else:
                self.assertEqual(after[table], before[table])
        self.assertNotIn('演示', json.dumps(after, ensure_ascii=False))
        again = migration.migrate(self.path, True, self.folder / 'backups')
        self.assertEqual(again['fields'], 0)
        self.assertIsNone(again['backup'])
        self.assertEqual(self.snapshot(), after)

    def test_custom_content_and_similar_user_records_are_untouched(self):
        with self.connect() as db:
            db.execute("UPDATE users SET skills='用户已填写的技能' WHERE id=2")
            db.execute("UPDATE registrations SET statement='用户自己的参赛说明（演示）',review_note='用户自己的审核意见' WHERE id=2")
            db.execute("UPDATE competitions SET description='管理员自写简介' WHERE id=4")
            db.execute("INSERT INTO competitions SELECT 99,title,category,description,deadline,min_members,max_members,official_url,active FROM competitions WHERE id=5")
            custom = tuple(db.execute('SELECT * FROM competitions WHERE id=99').fetchone())
            team = tuple(db.execute('SELECT * FROM teams WHERE id=1').fetchone())
        migration.migrate(self.path, True, self.folder / 'backups')
        with self.connect() as db:
            self.assertEqual(tuple(db.execute('SELECT * FROM competitions WHERE id=99').fetchone()), custom)
            self.assertEqual(tuple(db.execute('SELECT * FROM teams WHERE id=1').fetchone()), team)
            self.assertEqual(db.execute('SELECT skills FROM users WHERE id=2').fetchone()[0], '用户已填写的技能')
            record = db.execute('SELECT statement,review_note FROM registrations WHERE id=2').fetchone()
            self.assertEqual(tuple(record), ('用户自己的参赛说明（演示）', '用户自己的审核意见'))

    def test_preview_never_writes_or_creates_backup(self):
        before = self.snapshot()
        report = migration.migrate(self.path, False, self.folder / 'backups')
        self.assertGreater(report['fields'], 0)
        self.assertIsNone(report['backup'])
        self.assertEqual(self.snapshot(), before)
        self.assertFalse((self.folder / 'backups').exists())

    def test_new_seed_has_natural_names_and_real_status_history(self):
        target = self.folder / 'fresh.db'
        result = subprocess.run([sys.executable, str(server.ROOT / 'tools' / 'prepare_demo.py'), '--db', str(target)],
                                capture_output=True, text=True, encoding='utf-8')
        self.assertEqual(result.returncode, 0, result.stderr)
        content = json.dumps(self.snapshot(target), ensure_ascii=False)
        for word in ('演示', '虚构', '待补充', '验收演示'):
            self.assertNotIn(word, content)
        with closing(sqlite3.connect(target)) as db:
            self.assertEqual(db.execute('SELECT status FROM registrations ORDER BY id').fetchall(), [('pending',), ('rejected',), ('approved',)])
            self.assertEqual(db.execute('SELECT action FROM registration_history WHERE registration_id=3 ORDER BY id').fetchall(),
                             [('submitted',), ('rejected',), ('resubmitted',), ('approved',)])
            for title, in db.execute('SELECT title FROM competitions UNION ALL SELECT name FROM teams'):
                self.assertFalse(any(word in title for word in ('待审核', '待补充', '已通过', '演示')))


if __name__ == '__main__':
    unittest.main()
