"""王任务包：通过真实 HTTP 验证成员管理、申请撤回和并发边界。"""
from concurrent.futures import ThreadPoolExecutor
from support import Client, SystemTestCase


class WangTest(SystemTestCase):
    def apply(self, tid, client=None):
        code, result = (client or self.wang).call(f'/teams/{tid}/apply', 'POST', {'message': '申请协作'})
        self.assertEqual(code, 200, result)
        return result['application_id']

    def approve(self, aid, client=None):
        code, result = (client or self.zhou).call(f'/applications/{aid}/review', 'POST', {'status': 'approved'})
        self.assertEqual(code, 200, result)

    def current_team(self, tid, client=None):
        return next(t for t in (client or self.zhou).call('/teams')[1]['teams'] if t['id'] == tid)

    def test_member_leave_remove_and_reapply(self):
        tid = self.team(self.competition(min_members=1))
        aid = self.apply(tid)
        self.approve(aid)
        self.assertEqual(self.wang.call(f'/teams/{tid}/members/me', 'DELETE')[0], 200)
        self.assertEqual(self.current_team(tid)['member_count'], 1)
        self.assertEqual(self.current_team(tid, self.wang)['my_application']['status'], 'rejected')
        self.approve(self.apply(tid))
        wang_id = self.wang.call('/me')[1]['user']['id']
        self.assertEqual(self.zhou.call(f'/teams/{tid}/members/{wang_id}', 'DELETE')[0], 200)
        self.assertEqual(self.current_team(tid)['member_count'], 1)
        self.assertEqual(self.apply(tid), aid)

    def test_member_permissions_and_registration_lock(self):
        tid = self.team(self.competition(min_members=1))
        self.approve(self.apply(tid))
        zhou_id = self.zhou.call('/me')[1]['user']['id']
        wang_id = self.wang.call('/me')[1]['user']['id']
        self.assertEqual(self.guest.call(f'/teams/{tid}/members/me', 'DELETE')[0], 403)
        self.assertEqual(self.chen.call(f'/teams/{tid}/members/{wang_id}', 'DELETE')[0], 400)
        self.assertEqual(self.chen.call(f'/teams/{tid}/members/me', 'DELETE')[0], 400)
        self.assertEqual(self.zhou.call(f'/teams/{tid}/members/me', 'DELETE')[0], 400)
        self.assertEqual(self.zhou.call(f'/teams/{tid}/members/{zhou_id}', 'DELETE')[0], 400)
        code, result = self.zhou.call('/registrations', 'POST', {
            'team_id': tid, 'contact_name': '周', 'contact_phone': '13800000000', 'statement': '成员名单锁定测试'})
        self.assertEqual(code, 200, result)
        self.assertEqual(self.wang.call(f'/teams/{tid}/members/me', 'DELETE')[0], 400)
        self.assertEqual(self.zhou.call(f'/teams/{tid}/members/{wang_id}', 'DELETE')[0], 400)
        self.assertEqual(self.current_team(tid)['member_count'], 2)

    def test_withdraw_own_pending_only_and_reapply(self):
        cid = self.competition(min_members=1)
        tid = self.team(cid)
        aid = self.apply(tid)
        self.assertEqual(self.guest.call(f'/applications/{aid}', 'DELETE')[0], 403)
        self.assertEqual(self.zhou.call(f'/applications/{aid}', 'DELETE')[0], 400)
        self.assertEqual(self.chen.call(f'/applications/{aid}', 'DELETE')[0], 400)
        self.assertEqual(self.wang.call(f'/applications/{aid}', 'DELETE')[0], 200)
        self.assertIsNone(self.current_team(tid, self.wang)['my_application'])
        aid = self.apply(tid)
        self.approve(aid)
        self.assertEqual(self.wang.call(f'/applications/{aid}', 'DELETE')[0], 400)
        self.assertEqual(self.current_team(tid)['member_count'], 2)

    def test_closed_competition_allows_cleanup_but_no_new_members(self):
        cid = self.competition(min_members=1)
        tid = self.team(cid)
        self.approve(self.apply(tid))
        chen_application = self.apply(tid, self.chen)
        code, result = self.admin.call(f'/competitions/{cid}', 'PUT', {'deadline': '2000-01-01', 'active': 0})
        self.assertEqual(code, 200, result)
        # 下架后待审申请者仍能在页面的数据源中找到撤回入口；不扩大到访客。
        pending_team = self.current_team(tid, self.chen)
        self.assertFalse(pending_team['is_member'])
        self.assertEqual(pending_team['my_application']['id'], chen_application)
        self.assertEqual(pending_team['my_application']['status'], 'pending')
        self.assertNotIn(tid, [t['id'] for t in self.guest.call('/teams')[1]['teams']])
        outsider = Client(self.base)
        code, result = outsider.call('/register', 'POST', {
            'username': 'unrelated_student', 'name': '无关学生', 'password': 'Password123'})
        self.assertEqual(code, 200, result)
        self.assertNotIn(tid, [t['id'] for t in outsider.call('/teams')[1]['teams']])
        self.assertEqual(self.zhou.call(f'/applications/{chen_application}/review', 'POST', {'status': 'approved'})[0], 400)
        self.assertEqual(self.chen.call(f'/applications/{chen_application}', 'DELETE')[0], 200)
        self.assertNotIn(tid, [t['id'] for t in self.chen.call('/teams')[1]['teams']])
        self.assertEqual(self.wang.call(f'/teams/{tid}/members/me', 'DELETE')[0], 200)
        self.assertNotIn(tid, [t['id'] for t in self.wang.call('/teams')[1]['teams']])
        self.assertEqual(self.wang.call(f'/teams/{tid}/apply', 'POST', {})[0], 400)

    def test_create_team_rejects_other_pending_applications(self):
        cid = self.competition(min_members=1)
        tid = self.team(cid)
        self.apply(tid)
        own_tid = self.team(cid, self.wang)
        self.assertEqual(self.current_team(tid, self.wang)['my_application']['status'], 'rejected')
        self.assertEqual(self.current_team(own_tid, self.wang)['member_count'], 1)

    def test_concurrent_approval_has_one_capacity_winner(self):
        tid = self.team(self.competition(min_members=1, max_members=2))
        aids = [self.apply(tid, client) for client in (self.wang, self.chen)]
        captain_session = Client(self.base)
        captain_session.login('zhou')
        clients = [self.zhou, captain_session]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda item: item[0].call(f'/applications/{item[1]}/review', 'POST', {'status': 'approved'}), zip(clients, aids)))
        self.assertEqual(sorted(code for code, _ in results), [200, 400])
        team = self.current_team(tid)
        self.assertEqual(team['member_count'], 2)
        self.assertEqual(sorted(app['status'] for app in team['applications']), ['approved', 'pending'])

    def test_concurrent_approval_cannot_join_two_teams(self):
        cid = self.competition(min_members=1)
        tids = [self.team(cid, client) for client in (self.zhou, self.chen)]
        aids = [self.apply(tid) for tid in tids]
        with ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda item: item[0].call(f'/applications/{item[1]}/review', 'POST', {'status': 'approved'}), zip((self.zhou, self.chen), aids)))
        self.assertEqual(sorted(code for code, _ in results), [200, 400])
        teams = [self.current_team(tid) for tid in tids]
        self.assertEqual(sum(t['is_member'] for t in self.wang.call('/teams')[1]['teams'] if t['competition_id'] == cid), 1)
        self.assertEqual(sorted(t['member_count'] for t in teams), [1, 2])
