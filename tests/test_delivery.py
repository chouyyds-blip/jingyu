"""交付质量：异常请求、日期边界、持久化和本机小样本响应时间。"""
import json
import time
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import Request, urlopen

from support import Client, SystemTestCase, server


class DeliveryTest(SystemTestCase):
    def test_invalid_payload_is_rejected_without_write(self):
        for payload in (b'[]', b'{broken', b'null', b'{"name":"\xff"}'):
            request = Request(self.base + '/api/profile', data=payload, method='PUT',
                              headers={'Content-Type': 'application/json'})
            with self.assertRaises(HTTPError) as error:
                urlopen(request, timeout=5)
            self.assertEqual(error.exception.code, 400)
            self.assertIn('error', json.load(error.exception))
        self.assertEqual(self.zhou.call('/me')[1]['user']['name'], '周')

    def test_deadline_date_includes_today_and_offset_is_compared(self):
        cid = self.competition(deadline=date.today().isoformat(), min_members=1)
        tid = self.team(cid)
        code, result = self.zhou.call('/registrations', 'POST', {
            'team_id': tid, 'contact_name': '周', 'contact_phone': '13800000000', 'statement': '当天可报名'})
        self.assertEqual(code, 200, result)
        past = (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()
        expired = self.competition(deadline=past)
        self.assertEqual(self.zhou.call('/teams', 'POST', {'competition_id': expired, 'name': '过期'})[0], 400)

    def test_persistence_and_database_integrity(self):
        cid = self.competition(min_members=1)
        tid = self.team(cid)
        with closing(server.connect()) as db:
            self.assertEqual(db.execute('PRAGMA integrity_check').fetchone()[0], 'ok')
            self.assertEqual(db.execute('SELECT captain_id FROM teams WHERE id=?', (tid,)).fetchone()[0],
                             self.zhou.call('/me')[1]['user']['id'])
            self.assertEqual(db.execute('PRAGMA foreign_key_check').fetchall(), [])
        # 初始化函数可再次运行，已保存业务不被重置。
        server.initialize()
        self.assertTrue(any(t['id'] == tid for t in self.zhou.call('/teams')[1]['teams']))

    def test_static_delivery_does_not_expose_sources(self):
        for path, expected in [('/', b'lang="zh-CN"'), ('/app.js', b'use strict'), ('/style.css', b':root')]:
            with urlopen(self.base + path, timeout=5) as response:
                self.assertEqual(response.status, 200)
                self.assertIn(expected, response.read())
        for path in ('/server.py', '/../server.py', '/data/app.db'):
            with self.assertRaises(HTTPError) as error:
                urlopen(self.base + path, timeout=5)
            self.assertEqual(error.exception.code, 404)

    def test_small_local_read_latency(self):
        def read(_):
            started = time.perf_counter()
            code, result = Client(self.base).call('/competitions')
            self.assertEqual(code, 200, result)
            return time.perf_counter() - started
        with ThreadPoolExecutor(max_workers=5) as pool:
            samples = sorted(pool.map(read, range(40)))
        p95 = samples[37]
        report = {'scope': '本机临时数据库竞赛列表，小样本，不代表互联网或大数据量负载',
                  'requests': len(samples), 'workers': 5, 'p95_seconds': round(p95, 4),
                  'max_seconds': round(max(samples), 4), 'target_p95_seconds': 2,
                  'passed': p95 < 2}
        output = Path(__file__).resolve().parents[1] / 'output' / 'acceptance'
        output.mkdir(parents=True, exist_ok=True)
        (output / 'performance.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
        self.assertLess(p95, 2, report)
