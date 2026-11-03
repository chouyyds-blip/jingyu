"""陈任务包：报名历史、报名快照、导出权限及旧库迁移的真实 HTTP 测试。"""
import csv
import io
import unittest
from contextlib import closing

from support import Client, SystemTestCase, server


class ChenRegistrationTest(SystemTestCase):
    def submit(self, client=None, **changes):
        cid = self.competition(min_members=1, max_members=3)
        tid = self.team(cid, client)
        data = {'team_id': tid, 'contact_name': '周', 'contact_phone': '13800000000',
                'statement': '报名说明第一版'}
        data.update(changes)
        code, result = (client or self.zhou).call('/registrations', 'POST', data)
        self.assertEqual(code, 200, result)
        return tid, result['registration_id'], data

    def record(self, rid, client=None):
        code, result = (client or self.zhou).call('/registrations')
        self.assertEqual(code, 200, result)
        return next(r for r in result['registrations'] if r['id'] == rid)

    def test_history_full_state_cycle_and_failed_reviews(self):
        tid, rid, data = self.submit()
        self.assertEqual(self.wang.call(f'/registrations/{rid}/review', 'POST', {'status': 'approved'})[0], 403)
        self.assertEqual(self.admin.call(f'/registrations/{rid}/review', 'POST', {'status': 'rejected'})[0], 400)
        self.assertEqual(len(self.record(rid)['history']), 1)
        self.assertEqual(self.admin.call(f'/registrations/{rid}/review', 'POST', {'status': 'rejected', 'review_note': '请补充作品内容'})[0], 200)
        self.assertEqual(self.zhou.call('/registrations', 'POST', {**data, 'statement': '补充后的第二版'})[0], 200)
        self.assertEqual(self.admin.call(f'/registrations/{rid}/review', 'POST', {'status': 'approved', 'review_note': '材料完整'})[0], 200)
        self.assertEqual(self.admin.call(f'/registrations/{rid}/review', 'POST', {'status': 'rejected', 'review_note': '重复审核'})[0], 400)
        record = self.record(rid)
        history = record['history']
        self.assertEqual([e['action'] for e in history], ['submitted', 'rejected', 'resubmitted', 'approved'])
        self.assertEqual([e['status'] for e in history], ['pending', 'rejected', 'pending', 'approved'])
        self.assertEqual(history[0]['statement'], '报名说明第一版')
        self.assertEqual(history[1]['review_note'], '请补充作品内容')
        self.assertEqual(history[2]['review_note'], '')
        self.assertEqual(history[3]['statement'], '补充后的第二版')
        self.assertEqual(history[0]['actor_id'], record['captain_id'])
        self.assertEqual(history[1]['actor_name'], '演示管理员')
        self.assertTrue(all(e['occurred_at'] for e in history))
        with closing(server.connect()) as db, db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM registration_history WHERE registration_id=?', (rid,)).fetchone()[0], 4)

    def test_member_and_actor_snapshots_survive_profile_changes(self):
        original = self.zhou.call('/me')[1]['user']
        tid, rid, data = self.submit()
        try:
            self.assertEqual(self.zhou.call('/profile', 'PUT', {'name': '改名后的队长', 'major': '改后的专业'})[0], 200)
            self.admin.call(f'/registrations/{rid}/review', 'POST', {'status': 'rejected', 'review_note': '补充'})
            self.zhou.call('/registrations', 'POST', data)
            record = self.record(rid)
            self.assertEqual(record['members'][0]['name'], original['name'])
            self.assertEqual(record['members'][0]['major'], original['major'])
            self.assertEqual(record['history'][0]['actor_name'], original['name'])
            self.assertEqual(record['history'][-1]['actor_name'], '改名后的队长')
            self.assertEqual(record['history'][-1]['members'][0]['name'], original['name'])
        finally:
            self.zhou.call('/profile', 'PUT', original)

    def test_history_and_export_access_control(self):
        tid, rid, data = self.submit()
        other_tid, other_rid, _ = self.submit(self.wang, contact_phone='13900000000')
        self.assertEqual(self.guest.call('/registrations/export')[0], 403)
        outsider_records = self.chen.call('/registrations')[1]['registrations']
        self.assertNotIn(rid, [r['id'] for r in outsider_records])
        code, output = self.chen.call('/registrations/export')
        self.assertEqual(code, 200)
        self.assertNotIn(data['contact_phone'], output['content'])
        rows = list(csv.reader(io.StringIO(self.zhou.call('/registrations/export')[1]['content'].lstrip('\ufeff'))))
        ids = {row[0] for row in rows[1:]}
        self.assertIn(str(rid), ids)
        self.assertNotIn(str(other_rid), ids)
        admin_rows = list(csv.reader(io.StringIO(self.admin.call('/registrations/export')[1]['content'].lstrip('\ufeff'))))
        self.assertTrue({str(rid), str(other_rid)} <= {row[0] for row in admin_rows[1:]})

    def test_export_formula_escaping_and_csv_quoting(self):
        statement = '=HYPERLINK("bad","点击"),\n第二行'
        tid, rid, data = self.submit(contact_name='@危险单元格', contact_phone='+8613800000000', statement=statement)
        exported = self.zhou.call('/registrations/export')[1]
        self.assertEqual(exported['filename'], '报名记录.csv')
        self.assertTrue(exported['content'].startswith('\ufeff'))
        rows = list(csv.reader(io.StringIO(exported['content'].lstrip('\ufeff'))))
        row = next(row for row in rows[1:] if row[0] == str(rid))
        self.assertEqual(row[3], "'@危险单元格")
        self.assertEqual(row[4], "'+8613800000000")
        self.assertEqual(row[5], "'" + statement)
        # 仅导出转换；数据库里的原始文本必须保留。
        self.assertEqual(self.record(rid)['statement'], statement)

    def test_legacy_migration_is_idempotent_and_honest(self):
        cid = self.competition(min_members=1)
        tid = self.team(cid)
        with closing(server.connect()) as db, db:
            rid = db.execute('''INSERT INTO registrations
                (team_id,contact_name,contact_phone,statement,status,review_note)
                VALUES (?, '旧联系人', '13800000000', '旧说明', 'approved', '原意见')''', (tid,)).lastrowid
        with closing(server.connect()) as db, db:
            server.registrations.initialize(db)
            server.registrations.initialize(db)
        record = self.record(rid)
        self.assertEqual(len(record['history']), 1)
        event = record['history'][0]
        self.assertEqual(event['action'], 'migrated')
        self.assertEqual(event['status'], 'approved')
        self.assertIsNone(event['actor_id'])
        self.assertIn('未知', event['actor_name'])
        self.assertEqual(event['review_note'], '原意见')


if __name__ == '__main__':
    unittest.main(verbosity=2)
