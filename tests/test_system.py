"""完整课程业务链路的 HTTP 集成回归。"""
import unittest
from support import SystemTestCase, Client, server


class SystemTest(SystemTestCase):
    def test_01_auth_and_permissions(self):
        self.assertIsNone(self.guest.call('/me')[1]['user'])
        self.assertEqual(self.guest.call('/registrations')[0],403)
        self.assertEqual(self.wang.call('/competitions','POST',{})[0],403)
        self.assertEqual(self.guest.call('/login','POST',{'username':'zhou','password':'wrong'})[0],400)
        code,result=self.guest.call('/register','POST',{'username':'new_student','name':'新同学','password':'Password123','role':'admin'})
        self.assertEqual(code,200,result)
        self.assertEqual(result['user']['role'],'student')
        self.assertNotIn('password_hash',result['user'])
        self.assertEqual(self.guest.call('/register','POST',{'username':'new_student','name':'新同学','password':'Password123'})[0],400)
        self.assertEqual(self.guest.call('/profile','PUT',{'name':'新名字','role':'admin'})[0],200)
        self.assertEqual(self.guest.call('/me')[1]['user']['role'],'student')
        self.guest.call('/logout','POST',{})
        self.assertIsNone(self.guest.call('/me')[1]['user'])

    def test_02_complete_workflow(self):
        cid=self.competition()
        tid=self.team(cid)
        self.assertEqual(self.zhou.call('/teams','POST',{'competition_id':cid,'name':'重复队伍'})[0],400)
        self.assertEqual(self.zhou.call('/registrations','POST',{'team_id':tid,'contact_name':'周','contact_phone':'13800000000','statement':'作品说明'})[0],400)
        for client in (self.wang,self.chen):
            code,result=client.call(f'/teams/{tid}/apply','POST',{'message':'我来负责开发'})
            self.assertEqual(code,200,result)
            aid=result['application_id']
            self.assertEqual(client.call(f'/teams/{tid}/apply','POST',{})[0],400)
            self.assertEqual(client.call(f'/applications/{aid}/review','POST',{'status':'approved'})[0],400)
            self.assertEqual(self.zhou.call(f'/applications/{aid}/review','POST',{'status':'approved'})[0],200)
        teams=self.zhou.call('/teams')[1]['teams']
        current=next(t for t in teams if t['id']==tid)
        self.assertEqual(current['member_count'],3)
        self.assertEqual(next(t for t in self.guest.call('/teams')[1]['teams'] if t['id']==tid)['applications'],[])
        payload={'team_id':tid,'contact_name':'周','contact_phone':'13800000000','statement':'软件工程课程实践作品'}
        self.assertEqual(self.wang.call('/registrations','POST',payload)[0],400)
        code,result=self.zhou.call('/registrations','POST',payload)
        self.assertEqual(code,200,result)
        rid=result['registration_id']
        self.assertEqual(self.zhou.call('/registrations','POST',payload)[0],400)
        self.assertEqual(self.zhou.call(f'/teams/{tid}','DELETE')[0],400)
        self.assertEqual(self.wang.call(f'/registrations/{rid}/review','POST',{'status':'approved'})[0],403)
        self.assertEqual(self.admin.call(f'/registrations/{rid}/review','POST',{'status':'rejected','review_note':''})[0],400)
        self.assertEqual(self.admin.call(f'/registrations/{rid}/review','POST',{'status':'rejected','review_note':'请补充说明'})[0],200)
        self.assertEqual(self.zhou.call('/registrations','POST',payload)[0],200)
        self.assertEqual(self.admin.call(f'/registrations/{rid}/review','POST',{'status':'approved'})[0],200)
        for client in (self.zhou,self.wang,self.chen):
            record=next(r for r in client.call('/registrations')[1]['registrations'] if r['id']==rid)
            self.assertEqual(record['status'],'approved')
            self.assertEqual(len(record['members']),3)
        outsider=Client(self.base)
        outsider.call('/register','POST',{'username':'outsider','name':'其他同学','password':'Password123'})
        self.assertNotIn(rid,[r['id'] for r in outsider.call('/registrations')[1]['registrations']])
        with server.connect() as db:
            self.assertEqual(db.execute('SELECT status FROM registrations WHERE id=?',(rid,)).fetchone()[0],'approved')

    def test_03_deadline_capacity_and_unpublish(self):
        expired=self.competition(deadline='2000-01-01')
        self.assertEqual(self.zhou.call('/teams','POST',{'competition_id':expired,'name':'过期队伍'})[0],400)
        cid=self.competition(min_members=1,max_members=1)
        tid=self.team(cid)
        self.assertEqual(self.wang.call(f'/teams/{tid}/apply','POST',{'message':'加入'})[0],400)
        self.assertEqual(self.admin.call(f'/competitions/{cid}','PUT',{'active':0})[0],200)
        self.assertNotIn(cid,[c['id'] for c in self.guest.call('/competitions')[1]['competitions']])
        self.assertEqual(self.guest.call(f'/competitions/{cid}')[0],400)
        self.assertEqual(self.zhou.call('/registrations','POST',{'team_id':tid,'contact_name':'周','contact_phone':'13800000000','statement':'参赛'})[0],400)

    def test_04_input_and_origin_validation(self):
        self.assertEqual(self.zhou.call('/profile','PUT',{'name':{'invalid':'type'}})[0],400)
        self.assertEqual(self.admin.call('/competitions','POST',{'title':'无效竞赛','category':'测试','description':'test','deadline':'bad','min_members':1,'max_members':3})[0],400)
        self.assertEqual(self.zhou.call('/profile','PUT',{'name':'周'},headers={'Origin':'https://other.example'})[0],403)


if __name__=='__main__':
    unittest.main(verbosity=2)
