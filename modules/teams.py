"""王：队伍管理、招募申请管理。写入事务由 HTTP 层统一提交。"""

from datetime import date, datetime
import re


def _text(data, key, limit, required=False):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError("请输入有效的文字内容")
    value = value.strip()
    if required and not value:
        raise ValueError("队伍名称不能为空")
    if len(value) > limit:
        raise ValueError(f"{key} 内容不能超过 {limit} 个字符")
    return value


def _id(value):
    if isinstance(value, bool):
        raise ValueError("编号格式不正确")
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        raise ValueError("编号格式不正确") from None
    if parsed <= 0 or str(parsed) != str(value):
        raise ValueError("编号格式不正确")
    return parsed


def _competition(db, competition_id):
    row = db.execute("SELECT * FROM competitions WHERE id = ?", (competition_id,)).fetchone()
    if row is None:
        raise ValueError("竞赛不存在")
    return row


def _require_open(competition):
    if not competition["active"]:
        raise ValueError("该竞赛已下架")
    raw = competition["deadline"]
    try:
        if len(raw) == 10:
            expired = date.today() > date.fromisoformat(raw)
        else:
            deadline = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            now = datetime.now(deadline.tzinfo) if deadline.tzinfo else datetime.now()
            expired = now > deadline
    except (TypeError, ValueError):
        raise ValueError("竞赛截止时间无效，请联系管理员") from None
    if expired:
        raise ValueError("该竞赛已经截止")


def _team(db, team_id):
    row = db.execute("SELECT * FROM teams WHERE id = ?", (team_id,)).fetchone()
    if row is None:
        raise ValueError("队伍不存在")
    return row


def _require_captain(ctx, team):
    user = ctx.require_user()
    if team["captain_id"] != user["id"]:
        raise ValueError("只有队长可以进行此操作")
    return user


def _require_unregistered(db, team_id):
    if db.execute("SELECT id FROM registrations WHERE team_id = ?", (team_id,)).fetchone():
        raise ValueError("队伍已经提交过报名，成员和队伍信息已锁定")


def _has_team(db, competition_id, user_id):
    return db.execute(
        "SELECT t.id FROM teams t JOIN team_members m ON m.team_id = t.id "
        "WHERE t.competition_id = ? AND m.user_id = ? LIMIT 1",
        (competition_id, user_id),
    ).fetchone() is not None


def _member_count(db, team_id):
    return db.execute("SELECT COUNT(*) FROM team_members WHERE team_id = ?", (team_id,)).fetchone()[0]


def _list(ctx):
    clauses = []
    args = []
    filter_id = ctx.query.get("competition_id", [])
    if filter_id:
        clauses.append("t.competition_id = ?")
        args.append(_id(filter_id[0]))
    # 已下架竞赛的队伍仅对本队成员和管理员可见。
    if not ctx.user or ctx.user["role"] != "admin":
        if ctx.user:
            clauses.append("(c.active = 1 OR EXISTS (SELECT 1 FROM team_members own WHERE own.team_id = t.id AND own.user_id = ?))")
            args.append(ctx.user["id"])
        else:
            clauses.append("c.active = 1")
    sql = (
        "SELECT t.*, c.title AS competition_title, c.min_members, c.max_members, "
        "c.deadline, c.active AS competition_active, u.name AS captain_name, "
        "r.status AS registration_status FROM teams t "
        "JOIN competitions c ON c.id = t.competition_id "
        "JOIN users u ON u.id = t.captain_id "
        "LEFT JOIN registrations r ON r.team_id = t.id"
    )
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    rows = ctx.db.execute(sql + " ORDER BY t.id DESC", args).fetchall()
    result = []
    for row in rows:
        team = dict(row)
        members = ctx.db.execute(
            "SELECT u.id, u.name, u.major, u.grade, u.skills FROM users u "
            "JOIN team_members m ON m.user_id = u.id WHERE m.team_id = ? ORDER BY u.id",
            (team["id"],),
        ).fetchall()
        team["members"] = [dict(member) for member in members]
        team["member_count"] = len(members)
        team["is_member"] = bool(ctx.user and any(m["id"] == ctx.user["id"] for m in members))
        team["applications"] = []
        team["my_application"] = None
        if ctx.user and team["captain_id"] == ctx.user["id"]:
            team["applications"] = [dict(app) for app in ctx.db.execute(
                "SELECT a.id, a.user_id, u.name, a.message, a.status, a.created_at "
                "FROM applications a JOIN users u ON u.id = a.user_id "
                "WHERE a.team_id = ? ORDER BY a.id DESC", (team["id"],)
            ).fetchall()]
        if ctx.user:
            own_app = ctx.db.execute(
                "SELECT id, status, message FROM applications WHERE team_id = ? AND user_id = ?",
                (team["id"], ctx.user["id"]),
            ).fetchone()
            team["my_application"] = dict(own_app) if own_app else None
        result.append(team)
    return {"teams": result}


def handle(ctx, method, path, data):
    if path == "/api/teams" and method == "GET":
        return _list(ctx)

    if path == "/api/teams" and method == "POST":
        user = ctx.require_user()
        if user["role"] != "student":
            raise ValueError("请使用学生账号创建队伍")
        competition_id = _id(data.get("competition_id"))
        competition = _competition(ctx.db, competition_id)
        _require_open(competition)
        if _has_team(ctx.db, competition_id, user["id"]):
            raise ValueError("你已经加入该竞赛的一支队伍")
        cursor = ctx.db.execute(
            "INSERT INTO teams (competition_id, captain_id, name, intro, requirements, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (competition_id, user["id"], _text(data, "name", 50, True),
             _text(data, "intro", 1000), _text(data, "requirements", 500), datetime.now().isoformat(timespec="seconds")),
        )
        team_id = cursor.lastrowid
        ctx.db.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)", (team_id, user["id"]))
        return {"team_id": team_id, "message": "队伍创建成功，你已成为队长"}

    match = re.fullmatch(r"/api/teams/(\d+)", path)
    if match and method in ("PUT", "DELETE"):
        team = _team(ctx.db, int(match.group(1)))
        _require_captain(ctx, team)
        _require_unregistered(ctx.db, team["id"])
        if method == "DELETE":
            ctx.db.execute("DELETE FROM applications WHERE team_id = ?", (team["id"],))
            ctx.db.execute("DELETE FROM team_members WHERE team_id = ?", (team["id"],))
            ctx.db.execute("DELETE FROM teams WHERE id = ?", (team["id"],))
            return {"message": "队伍已解散"}
        ctx.db.execute(
            "UPDATE teams SET name = ?, intro = ?, requirements = ? WHERE id = ?",
            (_text(data, "name", 50, True), _text(data, "intro", 1000),
             _text(data, "requirements", 500), team["id"]),
        )
        return {"message": "队伍信息已更新"}

    match = re.fullmatch(r"/api/teams/(\d+)/apply", path)
    if match and method == "POST":
        user = ctx.require_user()
        if user["role"] != "student":
            raise ValueError("请使用学生账号申请加入队伍")
        team = _team(ctx.db, int(match.group(1)))
        competition = _competition(ctx.db, team["competition_id"])
        _require_open(competition)
        _require_unregistered(ctx.db, team["id"])
        if _has_team(ctx.db, team["competition_id"], user["id"]):
            raise ValueError("你已经加入该竞赛的一支队伍")
        if _member_count(ctx.db, team["id"]) >= competition["max_members"]:
            raise ValueError("队伍人数已满")
        previous = ctx.db.execute(
            "SELECT id, status FROM applications WHERE team_id = ? AND user_id = ?",
            (team["id"], user["id"]),
        ).fetchone()
        if previous and previous["status"] in ("pending", "approved"):
            raise ValueError("你已提交申请，请勿重复申请")
        message = _text(data, "message", 500)
        now = datetime.now().isoformat(timespec="seconds")
        if previous:
            ctx.db.execute("UPDATE applications SET message = ?, status = 'pending', created_at = ? WHERE id = ?",
                           (message, now, previous["id"]))
            application_id = previous["id"]
        else:
            application_id = ctx.db.execute(
                "INSERT INTO applications (team_id, user_id, message, status, created_at) VALUES (?, ?, ?, 'pending', ?)",
                (team["id"], user["id"], message, now),
            ).lastrowid
        return {"application_id": application_id, "message": "入队申请已提交"}

    match = re.fullmatch(r"/api/applications/(\d+)/review", path)
    if match and method == "POST":
        ctx.require_user()
        app = ctx.db.execute("SELECT * FROM applications WHERE id = ?", (int(match.group(1)),)).fetchone()
        if app is None:
            raise ValueError("入队申请不存在")
        team = _team(ctx.db, app["team_id"])
        _require_captain(ctx, team)
        _require_unregistered(ctx.db, team["id"])
        if app["status"] != "pending":
            raise ValueError("该申请已经处理")
        status = data.get("status")
        if status not in ("approved", "rejected"):
            raise ValueError("请选择同意或拒绝")
        if status == "approved":
            competition = _competition(ctx.db, team["competition_id"])
            _require_open(competition)
            if _has_team(ctx.db, team["competition_id"], app["user_id"]):
                raise ValueError("该学生已经加入此竞赛的其他队伍")
            if _member_count(ctx.db, team["id"]) >= competition["max_members"]:
                raise ValueError("队伍人数已满")
            ctx.db.execute("INSERT INTO team_members (team_id, user_id) VALUES (?, ?)",
                           (team["id"], app["user_id"]))
            # 同一竞赛的其余待审申请自动拒绝，避免留下无法通过的申请。
            ctx.db.execute(
                "UPDATE applications SET status = 'rejected' WHERE user_id = ? AND status = 'pending' "
                "AND id != ? AND team_id IN (SELECT id FROM teams WHERE competition_id = ?)",
                (app["user_id"], app["id"], team["competition_id"]),
            )
        ctx.db.execute("UPDATE applications SET status = ? WHERE id = ?", (status, app["id"]))
        return {"message": "已同意入队申请" if status == "approved" else "已拒绝入队申请"}

    return None
