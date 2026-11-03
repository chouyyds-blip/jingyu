"""周负责模块的真实 HTTP 验收测试；不修改本机演示数据库。"""
from urllib.parse import quote

from support import SystemTestCase, Client


class ZhouModulesTest(SystemTestCase):
    def test_password_change_revokes_other_sessions(self):
        first, second = Client(self.base), Client(self.base)
        payload = {"username": "password_case", "name": "改密测试", "password": "Password123"}
        self.assertEqual(first.call('/register', 'POST', payload)[0], 200)
        self.assertEqual(second.call('/login', 'POST', payload)[0], 200)
        self.assertEqual(self.guest.call('/password', 'PUT', {})[0], 403)
        for changes in (
            {'old_password': 'wrong', 'new_password': 'NewPassword123'},
            {'old_password': 'Password123', 'new_password': 'short'},
            {'old_password': 'Password123', 'new_password': 'Password123'},
            {'old_password': [], 'new_password': 'NewPassword123'},
        ):
            self.assertEqual(first.call('/password', 'PUT', changes)[0], 400)
            self.assertIsNotNone(second.call('/me')[1]['user'])
        code, result = first.call('/password', 'PUT', {
            'old_password': 'Password123', 'new_password': 'NewPassword123'})
        self.assertEqual(code, 200, result)
        self.assertIsNotNone(first.call('/me')[1]['user'])
        self.assertIsNone(second.call('/me')[1]['user'])
        self.assertEqual(second.call('/profile', 'PUT', {'name': '无权限'})[0], 403)
        self.assertEqual(second.call('/login', 'POST', payload)[0], 400)
        payload['password'] = 'NewPassword123'
        self.assertEqual(second.call('/login', 'POST', payload)[0], 200)

    def test_competition_rules_protect_existing_teams(self):
        cid = self.competition(min_members=1, max_members=4)
        tid = self.team(cid)
        aid = self.wang.call(f'/teams/{tid}/apply', 'POST', {})[1]['application_id']
        self.assertEqual(self.zhou.call(f'/applications/{aid}/review', 'POST', {'status': 'approved'})[0], 200)
        # 提高最低人数允许队伍继续招募；不能把现有两人队伍变为超员。
        self.assertEqual(self.admin.call(f'/competitions/{cid}', 'PUT', {'min_members': 3})[0], 200)
        code, _ = self.admin.call(f'/competitions/{cid}', 'PUT', {'min_members': 1, 'max_members': 1})
        self.assertEqual(code, 400)
        c = self.admin.call(f'/competitions/{cid}')[1]['competition']
        self.assertEqual((c['min_members'], c['max_members']), (3, 4))

    def test_registration_freezes_eligibility_rules(self):
        cid = self.competition(min_members=1, max_members=3)
        tid = self.team(cid)
        code, result = self.zhou.call('/registrations', 'POST', {
            'team_id': tid, 'contact_name': '周', 'contact_phone': '13800000000', 'statement': '验收测试'})
        self.assertEqual(code, 200, result)
        for changes in ({'min_members': 2}, {'max_members': 4}, {'deadline': '2099-12-31'}):
            self.assertEqual(self.admin.call(f'/competitions/{cid}', 'PUT', changes)[0], 400)
        self.assertEqual(self.admin.call(f'/competitions/{cid}', 'PUT', {'title': '修订后的名称', 'active': 0})[0], 200)
        self.assertNotIn(cid, [c['id'] for c in self.guest.call('/competitions')[1]['competitions']])
        record = next(r for r in self.zhou.call('/registrations')[1]['registrations'] if r['team_id'] == tid)
        self.assertEqual(record['status'], 'pending')

    def test_category_and_query_filters_compose(self):
        cid = self.competition(title='周分类组合筛选', category='测试分类甲')
        self.competition(title='周分类组合筛选', category='测试分类乙')
        query = '/competitions?category=' + quote('测试分类甲') + '&q=' + quote('组合筛选')
        results = self.guest.call(query)[1]['competitions']
        self.assertEqual([c['id'] for c in results], [cid])
        self.assertEqual(self.guest.call('/competitions?category=' + quote('甲' * 31))[0], 400)
        self.assertEqual(self.guest.call('/competitions?category=' + quote("' OR 1=1 --"))[1]['competitions'], [])
