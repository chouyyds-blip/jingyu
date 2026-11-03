"""陈：队伍报名提交、报名记录查询和管理员审核。"""

from datetime import date, datetime
import csv
import io
import json
import re


def initialize(db):
    """升级旧库时仅记录可证实的现状，不补造过去的提交或审核事件。"""
    db.execute('''CREATE TABLE IF NOT EXISTS registration_history (
        id INTEGER PRIMARY KEY,
        registration_id INTEGER NOT NULL REFERENCES registrations(id) ON DELETE CASCADE,
        action TEXT NOT NULL, status TEXT NOT NULL,
        actor_id INTEGER REFERENCES users(id), actor_name TEXT NOT NULL,
        occurred_at TEXT NOT NULL, review_note TEXT NOT NULL DEFAULT '',
        contact_name TEXT NOT NULL, contact_phone TEXT NOT NULL,
        statement TEXT NOT NULL, members_json TEXT NOT NULL)''')
    db.execute('''CREATE INDEX IF NOT EXISTS idx_registration_history_record
                  ON registration_history(registration_id, id)''')
    rows = db.execute('''SELECT r.* FROM registrations r WHERE NOT EXISTS
                      (SELECT 1 FROM registration_history h WHERE h.registration_id = r.id)''').fetchall()
    for row in rows:
        _history(db, dict(row), 'migrated', None, '旧数据迁移（原审核人未知）',
                 datetime.now().isoformat(timespec='seconds'), _members(db, row['team_id']))


def _members(db, team_id):
    return [dict(row) for row in db.execute('''
        SELECT u.id, u.name, u.major FROM users u
        JOIN team_members tm ON tm.user_id = u.id
        WHERE tm.team_id = ? ORDER BY u.id''', (team_id,)).fetchall()]


def _history(db, record, action, actor_id, actor_name, occurred_at, members):
    db.execute('''INSERT INTO registration_history
        (registration_id, action, status, actor_id, actor_name, occurred_at,
         review_note, contact_name, contact_phone, statement, members_json)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)''',
        (record['id'], action, record['status'], actor_id, actor_name, occurred_at,
         record['review_note'], record['contact_name'], record['contact_phone'],
         record['statement'], json.dumps(members, ensure_ascii=False)))


def _text(data, key, label, maximum, required=True):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{label}格式不正确")
    value = value.strip()
    if required and not value:
        raise ValueError(f"请填写{label}")
    if len(value) > maximum:
        raise ValueError(f"{label}不能超过{maximum}字")
    return value


def _identifier(value):
    if isinstance(value, bool):
        raise ValueError("队伍编号不正确")
    try:
        number = int(str(value))
    except (ValueError, TypeError):
        raise ValueError("队伍编号不正确") from None
    if number < 1:
        raise ValueError("队伍编号不正确")
    return number


def _check_deadline(value):
    """日期截止时间包括当天；精确时间则直接比较。"""
    try:
        value = str(value)
        if len(value) == 10:
            expired = date.today() > date.fromisoformat(value)
        else:
            deadline = datetime.fromisoformat(value.replace("Z", "+00:00"))
            now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
            expired = now > deadline
    except (ValueError, TypeError):
        raise ValueError("竞赛截止时间无效，请联系管理员") from None
    if expired:
        raise ValueError("该竞赛报名已截止")


def _list_registrations(ctx):
    user = ctx.require_user()
    sql = """
        SELECT r.*, t.name AS team_name, t.captain_id,
               t.competition_id, c.title AS competition_title
        FROM registrations r
        JOIN teams t ON t.id = r.team_id
        JOIN competitions c ON c.id = t.competition_id
    """
    values = []
    if user["role"] != "admin":
        sql += """ WHERE EXISTS (
            SELECT 1 FROM team_members tm
            WHERE tm.team_id = r.team_id AND tm.user_id = ?
        )"""
        values.append(user["id"])
    sql += " ORDER BY r.updated_at DESC, r.id DESC"
    registrations = []
    for row in ctx.db.execute(sql, values).fetchall():
        record = dict(row)
        record["history"] = []
        for event in ctx.db.execute(
            "SELECT * FROM registration_history WHERE registration_id = ? ORDER BY id", (record['id'],)
        ).fetchall():
            item = dict(event)
            item['members'] = json.loads(item.pop('members_json'))
            record['history'].append(item)
        record['members'] = record['history'][-1]['members'] if record['history'] else _members(ctx.db, record['team_id'])
        registrations.append(record)
    return {"registrations": registrations}


def _csv_cell(value):
    value = str(value)
    # Excel/WPS 会把以这些字符开头的单元格解释为公式；空白也可能被跳过。
    if value.lstrip().startswith(('=', '+', '-', '@')) or value.startswith(('\t', '\r', '\n')):
        return "'" + value
    return value


def _export(ctx):
    records = _list_registrations(ctx)['registrations']
    output = io.StringIO(newline='')
    writer = csv.writer(output)
    writer.writerow(['报名编号', '竞赛', '队伍', '联系人', '联系电话', '参赛说明', '成员', '状态', '审核意见', '提交时间', '更新时间'])
    labels = {'pending': '待审核', 'approved': '已通过', 'rejected': '已驳回'}
    for r in records:
        writer.writerow([_csv_cell(v) for v in (
            r['id'], r['competition_title'], r['team_name'], r['contact_name'],
            r['contact_phone'], r['statement'], '、'.join(m['name'] for m in r['members']),
            labels[r['status']], r['review_note'], r['created_at'], r['updated_at'])])
    return {'filename': '报名记录.csv', 'content': '\ufeff' + output.getvalue()}


def _submit(ctx, data):
    user = ctx.require_user()
    team_id = _identifier(data.get("team_id"))
    team = ctx.db.execute(
        """SELECT t.*, c.active, c.deadline, c.min_members, c.max_members
           FROM teams t JOIN competitions c ON c.id = t.competition_id
           WHERE t.id = ?""",
        (team_id,),
    ).fetchone()
    if team is None:
        raise ValueError("队伍不存在")
    if team["captain_id"] != user["id"]:
        raise ValueError("只有队长可以提交或修改报名")
    if not team["active"]:
        raise ValueError("该竞赛已下架，不能报名")
    _check_deadline(team["deadline"])
    count = ctx.db.execute(
        "SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,)
    ).fetchone()[0]
    if not team["min_members"] <= count <= team["max_members"]:
        raise ValueError(
            f"报名人数须为{team['min_members']}至{team['max_members']}人，当前{count}人"
        )
    existing = ctx.db.execute(
        "SELECT id, status FROM registrations WHERE team_id = ?", (team_id,)
    ).fetchone()
    if existing and existing["status"] != "rejected":
        raise ValueError("该队伍已提交报名，待审核或已通过的报名不能修改")

    contact_name = _text(data, "contact_name", "联系人姓名", 40)
    contact_phone = _text(data, "contact_phone", "联系电话", 30)
    if not re.fullmatch(r"\+?[0-9()\-\s]{6,30}", contact_phone) or not (
        6 <= sum(character.isdigit() for character in contact_phone) <= 20
    ):
        raise ValueError("请输入有效联系电话，支持数字、空格、括号和短横线")
    statement = _text(data, "statement", "参赛说明", 2000)
    now = datetime.now().isoformat(timespec="seconds")
    if existing:
        ctx.db.execute(
            """UPDATE registrations SET contact_name = ?, contact_phone = ?,
               statement = ?, status = 'pending', review_note = '', updated_at = ?
               WHERE id = ?""",
            (contact_name, contact_phone, statement, now, existing["id"]),
        )
        registration_id = existing["id"]
    else:
        cursor = ctx.db.execute(
            """INSERT INTO registrations
               (team_id, contact_name, contact_phone, statement, status,
                review_note, created_at, updated_at)
               VALUES (?, ?, ?, ?, 'pending', '', ?, ?)""",
            (team_id, contact_name, contact_phone, statement, now, now),
        )
        registration_id = cursor.lastrowid
    record = dict(ctx.db.execute('SELECT * FROM registrations WHERE id = ?', (registration_id,)).fetchone())
    # 重提继续沿用首次提交的名单快照，个人资料修改不能改写报名事实。
    previous = ctx.db.execute('''SELECT members_json FROM registration_history
                                 WHERE registration_id = ? ORDER BY id LIMIT 1''', (registration_id,)).fetchone()
    members = json.loads(previous['members_json']) if previous else _members(ctx.db, team_id)
    _history(ctx.db, record, 'resubmitted' if existing else 'submitted', user['id'], user['name'], now, members)
    return {"registration_id": registration_id, "status": "pending", "message": "报名已提交，等待审核"}


def _review(ctx, registration_id, data):
    user = ctx.require_admin()
    status = data.get("status")
    if status not in ("approved", "rejected"):
        raise ValueError("审核结果必须是通过或驳回")
    note = _text(data, "review_note", "审核说明", 1000, required=status == "rejected")
    record = ctx.db.execute(
        "SELECT id, status FROM registrations WHERE id = ?", (registration_id,)
    ).fetchone()
    if record is None:
        raise ValueError("报名记录不存在")
    if record["status"] != "pending":
        raise ValueError("只能审核待审核状态的报名")
    now = datetime.now().isoformat(timespec="seconds")
    ctx.db.execute(
        "UPDATE registrations SET status = ?, review_note = ?, updated_at = ? WHERE id = ?",
        (status, note, now, registration_id),
    )
    record = dict(ctx.db.execute('SELECT * FROM registrations WHERE id = ?', (registration_id,)).fetchone())
    previous = ctx.db.execute('''SELECT members_json FROM registration_history
                                 WHERE registration_id = ? ORDER BY id DESC LIMIT 1''', (registration_id,)).fetchone()
    members = json.loads(previous['members_json']) if previous else _members(ctx.db, record['team_id'])
    _history(ctx.db, record, status, user['id'], user['name'], now, members)
    return {"registration_id": registration_id, "status": status, "message": "审核结果已保存"}


def handle(ctx, method, path, data):
    if path == '/api/registrations/export' and method == 'GET':
        return _export(ctx)
    if path == "/api/registrations":
        if method == "GET":
            return _list_registrations(ctx)
        if method == "POST":
            return _submit(ctx, data)
    match = re.fullmatch(r"/api/registrations/(\d+)/review", path)
    if match and method == "POST":
        return _review(ctx, int(match.group(1)), data)
    return None
