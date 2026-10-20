"""周：用户管理与竞赛信息管理。仅使用 Python 标准库。"""

import hashlib
import hmac
import re
import secrets
import sqlite3
from datetime import datetime
from urllib.parse import urlsplit


PUBLIC_USER_FIELDS = "id, username, name, major, grade, skills, role"


def hash_password(password):
    salt = secrets.token_hex(16)
    rounds = 260000
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), rounds)
    return f"pbkdf2_sha256${rounds}${salt}${digest.hex()}"


def verify_password(password, encoded):
    try:
        algorithm, rounds, salt, expected = encoded.split("$")
        if algorithm != "pbkdf2_sha256":
            return False
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("ascii"), int(rounds))
        return hmac.compare_digest(digest.hex(), expected)
    except (ValueError, TypeError, AttributeError):
        return False


def _text(data, key, label, maximum, required=False):
    value = data.get(key, "")
    if not isinstance(value, str):
        raise ValueError(f"{label}必须是文本")
    value = value.strip()
    if required and not value:
        raise ValueError(f"请填写{label}")
    if len(value) > maximum:
        raise ValueError(f"{label}不能超过 {maximum} 字")
    return value


def _competition_data(data, existing=None):
    values = dict(existing or {})
    values.update(data)
    result = {}
    for key, label, limit, required in (
        ("title", "竞赛名称", 100, True),
        ("category", "竞赛类别", 30, True),
        ("description", "竞赛简介", 5000, True),
        ("deadline", "报名截止时间", 40, True),
        ("official_url", "官方网站链接", 500, False),
    ):
        result[key] = _text(values, key, label, limit, required)
    try:
        datetime.fromisoformat(result["deadline"])
    except ValueError:
        raise ValueError("报名截止时间格式应为 YYYY-MM-DD 或 ISO 日期时间") from None
    for key, label in (("min_members", "最少人数"), ("max_members", "最多人数")):
        value = values.get(key)
        if isinstance(value, bool) or not re.fullmatch(r"\d+", str(value)):
            raise ValueError(f"{label}必须是整数")
        result[key] = int(value)
    if not 1 <= result["min_members"] <= result["max_members"] <= 20:
        raise ValueError("队伍人数需满足 1 ≤ 最少人数 ≤ 最多人数 ≤ 20")
    if result["official_url"]:
        try:
            parsed = urlsplit(result["official_url"])
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                raise ValueError
        except ValueError:
            raise ValueError("官方网站链接须为有效的 http 或 https 地址") from None
    active = values.get("active", 1)
    if active not in (0, 1, False, True):
        raise ValueError("竞赛上架状态无效")
    result["active"] = int(active)
    return result


def handle(ctx, method, path, data):
    if path == "/api/register" and method == "POST":
        username = _text(data, "username", "用户名", 30, True)
        if not re.fullmatch(r"[A-Za-z0-9_]{3,30}", username):
            raise ValueError("用户名须为 3 至 30 位字母、数字或下划线")
        password = data.get("password", "")
        if not isinstance(password, str) or not 8 <= len(password) <= 128:
            raise ValueError("密码长度须为 8 至 128 位")
        name = _text(data, "name", "姓名", 30, True)
        try:
            cursor = ctx.db.execute(
                "INSERT INTO users (username,password_hash,name,major,grade,skills,role) VALUES (?,?,?,'','','','student')",
                (username, hash_password(password), name),
            )
        except sqlite3.IntegrityError:
            raise ValueError("用户名已被使用") from None
        return {"user": ctx.session_user(cursor.lastrowid), "message": "注册成功"}

    if path == "/api/login" and method == "POST":
        username = _text(data, "username", "用户名", 30, True)
        password = data.get("password", "")
        if not isinstance(password, str) or len(password) > 128:
            raise ValueError("用户名或密码错误")
        row = ctx.db.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        if row is None or not verify_password(password, row["password_hash"]):
            raise ValueError("用户名或密码错误")
        return {"user": ctx.session_user(row["id"]), "message": "登录成功"}

    if path == "/api/logout" and method == "POST":
        ctx.logout()
        return {"message": "已退出登录"}

    if path == "/api/me" and method == "GET":
        if ctx.user is None:
            return {"user": None}
        return {"user": {field: ctx.user.get(field, "") for field in PUBLIC_USER_FIELDS.split(", ")}}

    if path == "/api/profile" and method == "PUT":
        user = ctx.require_user()
        values = dict(user)
        values.update(data)
        name = _text(values, "name", "姓名", 30, True)
        major = _text(values, "major", "专业", 60)
        grade = _text(values, "grade", "年级", 30)
        skills = _text(values, "skills", "技能简介", 500)
        ctx.db.execute("UPDATE users SET name=?,major=?,grade=?,skills=? WHERE id=?", (name, major, grade, skills, user["id"]))
        row = ctx.db.execute(f"SELECT {PUBLIC_USER_FIELDS} FROM users WHERE id=?", (user["id"],)).fetchone()
        return {"user": dict(row), "message": "个人资料已保存"}

    if path == "/api/competitions" and method == "GET":
        is_admin = bool(ctx.user and ctx.user["role"] == "admin")
        query = ctx.query.get("q", [""])[0].strip()
        if len(query) > 100:
            raise ValueError("搜索词不能超过 100 字")
        conditions = [] if is_admin else ["active=1"]
        arguments = []
        if query:
            conditions.append("(title LIKE ? OR category LIKE ?)")
            arguments.extend([f"%{query}%", f"%{query}%"])
        sql = "SELECT * FROM competitions"
        if conditions:
            sql += " WHERE " + " AND ".join(conditions)
        rows = ctx.db.execute(sql + " ORDER BY deadline,id DESC", arguments).fetchall()
        return {"competitions": [dict(row) for row in rows]}

    if path == "/api/competitions" and method == "POST":
        ctx.require_admin()
        fields = _competition_data(data)
        keys = list(fields)
        cursor = ctx.db.execute(
            f"INSERT INTO competitions ({','.join(keys)}) VALUES ({','.join('?' for _ in keys)})",
            tuple(fields.values()),
        )
        row = ctx.db.execute("SELECT * FROM competitions WHERE id=?", (cursor.lastrowid,)).fetchone()
        return {"competition": dict(row), "message": "竞赛已发布"}

    match = re.fullmatch(r"/api/competitions/(\d+)", path)
    if match and method in ("GET", "PUT"):
        competition_id = int(match.group(1))
        if method == "PUT":
            ctx.require_admin()
        row = ctx.db.execute("SELECT * FROM competitions WHERE id=?", (competition_id,)).fetchone()
        is_admin = bool(ctx.user and ctx.user["role"] == "admin")
        if row is None or (not row["active"] and not is_admin):
            raise ValueError("竞赛不存在或已下架")
        if method == "GET":
            return {"competition": dict(row)}
        fields = _competition_data(data, dict(row))
        ctx.db.execute(
            "UPDATE competitions SET " + ",".join(f"{key}=?" for key in fields) + " WHERE id=?",
            (*fields.values(), competition_id),
        )
        updated = ctx.db.execute("SELECT * FROM competitions WHERE id=?", (competition_id,)).fetchone()
        return {"competition": dict(updated), "message": "竞赛信息已保存"}
    return None
