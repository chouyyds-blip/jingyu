"""陈：队伍报名提交、报名记录查询和管理员审核。"""

from datetime import date, datetime
import re


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
        record["members"] = [
            dict(member)
            for member in ctx.db.execute(
                """SELECT u.id, u.name, u.major FROM users u
                   JOIN team_members tm ON tm.user_id = u.id
                   WHERE tm.team_id = ? ORDER BY u.id""",
                (record["team_id"],),
            ).fetchall()
        ]
        registrations.append(record)
    return {"registrations": registrations}


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
    return {"registration_id": registration_id, "status": "pending", "message": "报名已提交，等待审核"}


def _review(ctx, registration_id, data):
    ctx.require_admin()
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
    ctx.db.execute(
        "UPDATE registrations SET status = ?, review_note = ?, updated_at = ? WHERE id = ?",
        (status, note, datetime.now().isoformat(timespec="seconds"), registration_id),
    )
    return {"registration_id": registration_id, "status": status, "message": "审核结果已保存"}


def handle(ctx, method, path, data):
    if path == "/api/registrations":
        if method == "GET":
            return _list_registrations(ctx)
        if method == "POST":
            return _submit(ctx, data)
    match = re.fullmatch(r"/api/registrations/(\d+)/review", path)
    if match and method == "POST":
        return _review(ctx, int(match.group(1)), data)
    return None
