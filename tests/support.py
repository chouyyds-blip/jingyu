"""真实 HTTP 集成测试，使用临时数据库，不修改演示数据。"""
import http.cookiejar
import json
import sys
import shutil
import uuid
import threading
import unittest
from datetime import datetime, timedelta
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import server


def scratch_path():
    return (Path(__file__).resolve().parents[1] / 'tmp').resolve()


class Client:
    def __init__(self, base):
        self.base = base
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, method='GET', data=None, headers=None):
        body = json.dumps(data).encode() if data is not None else None
        req = Request(self.base + '/api' + path, data=body, method=method,
                      headers={'Content-Type':'application/json', **(headers or {})})
        try:
            with self.opener.open(req) as res:
                return res.status, json.load(res)
        except HTTPError as exc:
            return exc.code, json.load(exc)

    def login(self, username):
        code, result = self.call('/login', 'POST', {'username':username,'password':'Demo123456'})
        assert code == 200, result


class SystemTestCase(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        scratch = Path(__file__).resolve().parents[1] / 'tmp'
        scratch.mkdir(exist_ok=True)
        cls.temp_path = scratch / ('test-' + uuid.uuid4().hex)
        cls.temp_path.mkdir()
        cls.old_db = server.DB_PATH
        server.DB_PATH = cls.temp_path / 'app.db'
        server.initialize()
        cls.http = server.ThreadingHTTPServer(('127.0.0.1',0),server.Handler)
        cls.thread = threading.Thread(target=cls.http.serve_forever,daemon=True)
        cls.thread.start()
        cls.base = f'http://127.0.0.1:{cls.http.server_port}'

    @classmethod
    def tearDownClass(cls):
        cls.http.shutdown()
        cls.http.server_close()
        cls.thread.join()
        server.DB_PATH = cls.old_db
        server.SESSIONS.clear()
        if cls.temp_path.resolve().parent != scratch_path():
            raise RuntimeError('测试清理路径越界')
        shutil.rmtree(cls.temp_path)

    def setUp(self):
        self.admin, self.zhou, self.wang, self.chen, self.guest = [Client(self.base) for _ in range(5)]
        for client,name in [(self.admin,'admin'),(self.zhou,'zhou'),(self.wang,'wang'),(self.chen,'chen')]:
            client.login(name)

    def competition(self, **changes):
        data = {'title':'集成测试竞赛','category':'软件开发','description':'用于自动化测试',
                'deadline':(datetime.now()+timedelta(days=5)).isoformat(timespec='minutes'),
                'min_members':3,'max_members':3,'official_url':'','active':1}
        data.update(changes)
        code,result = self.admin.call('/competitions','POST',data)
        self.assertEqual(code,200,result)
        return result['competition']['id']

    def team(self, competition_id, client=None):
        code,result = (client or self.zhou).call('/teams','POST',{'competition_id':competition_id,'name':'测试队伍','requirements':'欢迎加入'})
        self.assertEqual(code,200,result)
        return result['team_id']
