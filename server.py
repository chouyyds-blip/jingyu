"""本地课程演示服务器，仅使用 Python 标准库。"""
import argparse
import json
import secrets
import sqlite3
import traceback
from datetime import datetime, timedelta
from http import cookies
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlsplit

from modules import users, teams, registrations

ROOT = Path(__file__).resolve().parent
DB_PATH = ROOT / 'data' / 'app.db'
SESSIONS = {}


def connect():
    db = sqlite3.connect(DB_PATH, timeout=15)
    db.row_factory = sqlite3.Row
    db.execute('PRAGMA foreign_keys=ON')
    return db


def initialize():
    DB_PATH.parent.mkdir(exist_ok=True)
    with connect() as db:
        db.executescript('''
        CREATE TABLE IF NOT EXISTS users (
          id INTEGER PRIMARY KEY, username TEXT NOT NULL UNIQUE,
          password_hash TEXT NOT NULL, name TEXT NOT NULL,
          major TEXT NOT NULL DEFAULT '', grade TEXT NOT NULL DEFAULT '',
          skills TEXT NOT NULL DEFAULT '', role TEXT NOT NULL DEFAULT 'student');
        CREATE TABLE IF NOT EXISTS competitions (
          id INTEGER PRIMARY KEY, title TEXT NOT NULL, category TEXT NOT NULL,
          description TEXT NOT NULL, deadline TEXT NOT NULL,
          min_members INTEGER NOT NULL, max_members INTEGER NOT NULL,
          official_url TEXT NOT NULL DEFAULT '', active INTEGER NOT NULL DEFAULT 1);
        CREATE TABLE IF NOT EXISTS teams (
          id INTEGER PRIMARY KEY, competition_id INTEGER NOT NULL REFERENCES competitions(id),
          captain_id INTEGER NOT NULL REFERENCES users(id), name TEXT NOT NULL,
          intro TEXT NOT NULL DEFAULT '', requirements TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        CREATE TABLE IF NOT EXISTS team_members (
          team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id), PRIMARY KEY(team_id,user_id));
        CREATE TABLE IF NOT EXISTS applications (
          id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL REFERENCES teams(id) ON DELETE CASCADE,
          user_id INTEGER NOT NULL REFERENCES users(id), message TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending', created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
          UNIQUE(team_id,user_id));
        CREATE TABLE IF NOT EXISTS registrations (
          id INTEGER PRIMARY KEY, team_id INTEGER NOT NULL UNIQUE REFERENCES teams(id),
          contact_name TEXT NOT NULL, contact_phone TEXT NOT NULL, statement TEXT NOT NULL DEFAULT '',
          status TEXT NOT NULL DEFAULT 'pending', review_note TEXT NOT NULL DEFAULT '',
          created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP);
        ''')
        for username, name, role, major in [('admin','演示管理员','admin',''), ('zhou','周','student','计算机科学与技术'), ('wang','王','student','软件工程'), ('chen','陈','student','信息管理')]:
            db.execute('INSERT OR IGNORE INTO users(username,password_hash,name,role,major,grade) VALUES(?,?,?,?,?,?)',
                       (username, users.hash_password('Demo123456'), name, role, major, '2024级'))
        if not db.execute('SELECT 1 FROM competitions').fetchone():
            deadline = (datetime.now() + timedelta(days=60)).strftime('%Y-%m-%dT23:59')
            db.executemany('INSERT INTO competitions(title,category,description,deadline,min_members,max_members) VALUES(?,?,?,?,?,?)', [
                ('校园软件创意设计赛（演示）','软件开发','围绕校园真实问题，设计并实现一个可演示的软件原型。此条为课程演示数据。',deadline,3,3),
                ('大学生数据应用挑战赛（演示）','数据分析','选择一个公开数据集完成分析，提交分析说明和作品。此条为课程演示数据。',deadline,1,3),
                ('校园交互设计赛（演示）','创新设计','以校园服务为主题完成交互原型与设计说明。此条为课程演示数据。',deadline,1,4)])


class Context:
    def __init__(self, handler, db, query):
        self.db, self.query, self.handler = db, query, handler
        self.token = None
        try:
            jar = cookies.SimpleCookie(handler.headers.get('Cookie',''))
            self.token = jar['sid'].value if 'sid' in jar else None
        except cookies.CookieError:
            pass
        session = SESSIONS.get(self.token)
        self.user = None
        if session and session[1] > datetime.now():
            row = db.execute('SELECT id,username,name,major,grade,skills,role FROM users WHERE id=?',(session[0],)).fetchone()
            self.user = dict(row) if row else None
        elif session:
            SESSIONS.pop(self.token, None)
        self.cookie = None

    def require_user(self):
        if not self.user:
            raise PermissionError('请先登录')
        return self.user

    def require_admin(self):
        user = self.require_user()
        if user['role'] != 'admin':
            raise PermissionError('需要管理员权限')
        return user

    def session_user(self, user_id):
        if self.token:
            SESSIONS.pop(self.token, None)
        token = secrets.token_urlsafe(32)
        SESSIONS[token] = (user_id, datetime.now() + timedelta(hours=8))
        self.cookie = f'sid={token}; HttpOnly; SameSite=Strict; Path=/; Max-Age=28800'
        row = self.db.execute('SELECT id,username,name,major,grade,skills,role FROM users WHERE id=?',(user_id,)).fetchone()
        self.user = dict(row)
        return self.user

    def logout(self):
        SESSIONS.pop(self.token, None)
        self.cookie = 'sid=; HttpOnly; SameSite=Strict; Path=/; Max-Age=0'
        self.user = None


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(ROOT / 'static'), **kwargs)

    def do_GET(self):
        if urlsplit(self.path).path.startswith('/api/'):
            self.api('GET')
        else:
            super().do_GET()

    def do_POST(self): self.api('POST')
    def do_PUT(self): self.api('PUT')
    def do_DELETE(self): self.api('DELETE')

    def api(self, method):
        ctx = None
        status = 200
        try:
            origin = self.headers.get('Origin')
            if origin and urlsplit(origin).netloc != self.headers.get('Host'):
                raise PermissionError('不允许跨站请求')
            parsed = urlsplit(self.path)
            size = int(self.headers.get('Content-Length', '0'))
            if size < 0 or size > 65536:
                raise ValueError('请求内容过大')
            data = json.loads(self.rfile.read(size)) if size else {}
            if not isinstance(data, dict):
                raise ValueError('请求必须是JSON对象')
            db = connect()
            try:
                with db:
                    if method != 'GET':
                        db.execute('BEGIN IMMEDIATE')
                    ctx = Context(self, db, parse_qs(parsed.query))
                    result = None
                    for module in (users, teams, registrations):
                        result = module.handle(ctx, method, parsed.path, data)
                        if result is not None:
                            break
                    if result is None:
                        status, result = 404, {'error':'接口不存在'}
            finally:
                db.close()
        except PermissionError as exc:
            status, result = 403, {'error':str(exc)}
        except (ValueError, TypeError, KeyError) as exc:
            status, result = 400, {'error':str(exc) or '输入有误'}
        except sqlite3.IntegrityError:
            status, result = 400, {'error':'数据重复或关联数据不存在'}
        except Exception:
            traceback.print_exc()
            status, result = 500, {'error':'服务器处理失败，请查看终端日志'}
        payload = json.dumps(result, ensure_ascii=False).encode('utf-8')
        self.send_response(status)
        self.send_header('Content-Type','application/json; charset=utf-8')
        self.send_header('Cache-Control','no-store')
        self.send_header('X-Content-Type-Options','nosniff')
        if ctx and ctx.cookie and status == 200:
            self.send_header('Set-Cookie',ctx.cookie)
        self.send_header('Content-Length',str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port',type=int,default=8000)
    args = parser.parse_args()
    initialize()
    print(f'课程演示系统: http://127.0.0.1:{args.port}', flush=True)
    print('账号: admin / zhou / wang / chen，演示密码: Demo123456', flush=True)
    ThreadingHTTPServer(('127.0.0.1',args.port), Handler).serve_forever()
