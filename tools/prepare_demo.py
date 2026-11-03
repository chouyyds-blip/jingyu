"""通过真实 HTTP 生成独立验收库；拒绝覆盖已有文件。"""
import argparse
import http.cookiejar
import json
import sys
import threading
from datetime import datetime, timedelta
from pathlib import Path
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
import server


class Client:
    def __init__(self, base, username):
        self.base = base
        self.opener = build_opener(HTTPCookieProcessor(http.cookiejar.CookieJar()))
        self.call('/login', {'username': username, 'password': 'Demo123456'})

    def call(self, path, data):
        req = Request(self.base + '/api' + path, data=json.dumps(data).encode(),
                      headers={'Content-Type': 'application/json'})
        with self.opener.open(req, timeout=15) as response:
            return json.load(response)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--db', type=Path, default=ROOT / 'data' / 'acceptance.db')
    args = parser.parse_args()
    target = args.db.resolve()
    if target.exists():
        parser.exit(1, f'文件已存在，未修改：{target}\n请用 --db 指定新的验收库路径。\n')
    target.parent.mkdir(parents=True, exist_ok=True)
    server.DB_PATH = target
    server.initialize()
    http = server.ThreadingHTTPServer(('127.0.0.1', 0), server.Handler)
    thread = threading.Thread(target=http.serve_forever, daemon=True)
    thread.start()
    try:
        base = f'http://127.0.0.1:{http.server_port}'
        admin, zhou, wang, chen = [Client(base, user) for user in ('admin', 'zhou', 'wang', 'chen')]
        deadline = (datetime.now() + timedelta(days=60)).isoformat(timespec='minutes')
        for status, label in [('pending', '待审核'), ('rejected', '待补充'), ('approved', '已通过')]:
            cid = admin.call('/competitions', {
                'title': f'验收演示 · {label}软件实践赛', 'category': '软件开发',
                'description': '独立验收库中的虚构竞赛。用于演示周、王、陈的组队报名流程。',
                'deadline': deadline, 'min_members': 3, 'max_members': 3,
            })['competition']['id']
            tid = zhou.call('/teams', {'competition_id': cid, 'name': f'周王陈 · {label}演示队',
                                      'intro': '三名同学的课程实践队伍', 'requirements': '周负责用户竞赛，王负责队伍招募，陈负责报名审核'})['team_id']
            for client in (wang, chen):
                aid = client.call(f'/teams/{tid}/apply', {'message': '申请加入课程演示队'})['application_id']
                zhou.call(f'/applications/{aid}/review', {'status': 'approved'})
            form = {'team_id': tid, 'contact_name': '周（演示）', 'contact_phone': '13800000000',
                    'statement': '虚构参赛说明，仅用于本机课程验收。'}
            rid = zhou.call('/registrations', form)['registration_id']
            if status != 'pending':
                admin.call(f'/registrations/{rid}/review', {'status': 'rejected', 'review_note': '请补充作品范围说明（演示）'})
            if status == 'approved':
                zhou.call('/registrations', {**form, 'statement': form['statement'] + ' 已补充六个模块的实现和测试。'})
                admin.call(f'/registrations/{rid}/review', {'status': 'approved', 'review_note': '材料完整（演示）'})
        print(f'验收库已创建：{target}')
        print(f'启动命令：python server.py --db "{target}"')
    finally:
        http.shutdown()
        http.server_close()
        thread.join()
        server.SESSIONS.clear()


if __name__ == '__main__':
    main()
