# -*- coding: utf-8 -*-
"""
SHEIN 账号验证 API（服务端）
- HMAC-SHA256 签名 + 时间戳防重放
- 参数化查询防 SQL 注入
- 连接池复用 + 自动重连
- 内存级速率限制
"""

import time
import hmac
import hashlib
import threading
import argparse
import os
import json
from typing import Optional
from datetime import datetime
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator

# ======================== 配置 ========================

SECURE_KEY = "ShEiN_2025!@xKz9#Qm7$wPv"  # 客户端与服务端共享密钥，部署时务必修改
ADMIN_KEY = "ChangeThis_AdminKey_2026"  # 管理端密钥，manager.py 需保持一致
DELETE_PASSWORD = "qwertyuiop[]"       # 删除记录二次确认密码
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
AUDIT_LOG_FILE = os.path.join(BASE_DIR, "admin_audit.log")
CHECK_LOG_FILE = os.path.join(BASE_DIR, "sever_log.txt")

DB_CONFIG = {
    "host": "127.0.0.1",
    "port": 3306,
    "user": "api_checker",
    "password": "Adq430483#_strong",
    "database": "shein",
    "charset": "utf8mb4",
    "cursorclass": DictCursor,
    "connect_timeout": 5,
    "read_timeout": 10,
    # 关键：开启 autocommit，避免连接池复用时保留旧事务快照导致读到旧数据
    "autocommit": True,
}

TIMESTAMP_TOLERANCE = 300          # 请求时间戳容差（秒）
RATE_LIMIT_WINDOW   = 60          # 速率窗口（秒）
RATE_LIMIT_MAX      = 30          # 每个 IP 每窗口最大请求数
POOL_SIZE           = 5           # 连接池大小

# ======================== 连接池 ========================

class SimplePool:
    """线程安全的 pymysql 连接池（每次请求实时读库，不做业务数据缓存）。"""

    def __init__(self, config: dict, size: int = 5):
        self._config = config
        self._size = size
        self._pool: list[pymysql.Connection] = []
        self._lock = threading.Lock()

    def _new_conn(self) -> pymysql.Connection:
        return pymysql.connect(**self._config)

    @contextmanager
    def connection(self):
        conn = None
        with self._lock:
            if self._pool:
                conn = self._pool.pop()
        if conn is not None:
            try:
                conn.ping(reconnect=True)
            except Exception:
                try:
                    conn.close()
                except Exception:
                    pass
                conn = None
        if conn is None:
            conn = self._new_conn()
        try:
            yield conn
        finally:
            # 防御性清理：即使后续某处意外开启事务，也在归还连接前结束事务上下文
            try:
                conn.rollback()
            except Exception:
                pass
            with self._lock:
                if len(self._pool) < self._size:
                    self._pool.append(conn)
                else:
                    try:
                        conn.close()
                    except Exception:
                        pass

pool = SimplePool(DB_CONFIG, POOL_SIZE)

# ======================== 速率限制 ========================

_rate_store: dict[str, list[float]] = {}
_rate_lock = threading.Lock()
_check_log_lock = threading.Lock()
_audit_log_lock = threading.Lock()

def _check_rate(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        stamps = _rate_store.setdefault(ip, [])
        stamps[:] = [t for t in stamps if now - t < RATE_LIMIT_WINDOW]
        if len(stamps) >= RATE_LIMIT_MAX:
            return False
        stamps.append(now)
        return True


def _append_text_line(file_path: str, line: str, lock: Optional[threading.Lock] = None) -> None:
    """线程安全追加一行文本，目录不存在时自动创建。"""
    target_dir = os.path.dirname(file_path)
    if target_dir:
        os.makedirs(target_dir, exist_ok=True)
    if lock is None:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
        return
    with lock:
        with open(file_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")

# ======================== FastAPI ========================

app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)

class CheckRequest(BaseModel):
    shein_id: str
    timestamp: int
    sign: str

    @field_validator("shein_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("shein_id 无效")
        return v


class AdminUpsertRequest(BaseModel):
    shein_id: str
    start_time: str
    end_time: str
    operator: str = ""

    @field_validator("shein_id")
    @classmethod
    def _validate_shein_id(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("shein_id 无效")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_date_text(cls, v: str) -> str:
        v = v.strip()
        datetime.strptime(v, "%Y-%m-%d")
        return v


class AdminDeleteRequest(BaseModel):
    shein_id: str
    delete_password: str
    operator: str = ""

    @field_validator("shein_id")
    @classmethod
    def _validate_shein_id(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("shein_id 无效")
        return v

def _make_sign(shein_id: str, timestamp: int) -> str:
    """HMAC-SHA256 签名：与客户端算法一致。"""
    message = f"{shein_id}:{timestamp}"
    return hmac.new(
        SECURE_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _require_admin(request: Request) -> None:
    key = request.headers.get("x-admin-key", "").strip()
    if not key or not hmac.compare_digest(key, ADMIN_KEY):
        raise HTTPException(status_code=403, detail="管理员认证失败")


def _write_audit_log(
    action: str,
    shein_id: str,
    operator: str,
    client_ip: str,
    success: bool,
    detail: str,
) -> None:
    """写入管理操作审计日志（JSON Lines）。"""
    log_item = {
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "action": action,
        "shein_id": shein_id,
        "operator": operator or "unknown",
        "client_ip": client_ip or "unknown",
        "success": bool(success),
        "detail": detail[:200],
    }
    try:
        _append_text_line(
            AUDIT_LOG_FILE,
            json.dumps(log_item, ensure_ascii=False),
            _audit_log_lock,
        )
    except Exception:
        # 审计日志失败不影响主流程
        pass


def _write_check_request_log(
    shein_id: str,
    start_time: str,
    end_time: str,
    allowed: bool,
) -> None:
    """记录账号校验请求日志（每次请求一条）。"""
    request_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    account = str(shein_id or "").strip() or "unknown"
    start_text = str(start_time or "-")
    end_text = str(end_time or "-")
    result_text = "允许" if allowed else "不允许"
    line = "{}    {}    {}    {}    {}".format(
        request_time,
        account,
        start_text,
        end_text,
        result_text,
    )
    try:
        _append_text_line(CHECK_LOG_FILE, line, _check_log_lock)
    except Exception:
        # 日志写入失败不影响主流程
        pass
    try:
        print("[CHECK_AUTH] {}".format(line))
    except Exception:
        pass

@app.post("/check_auth")
async def check_auth(req: CheckRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate(client_ip):
        _write_check_request_log(req.shein_id, "", "", False)
        raise HTTPException(status_code=429, detail="请求过于频繁")

    now_ts = int(time.time())
    if abs(now_ts - req.timestamp) > TIMESTAMP_TOLERANCE:
        _write_check_request_log(req.shein_id, "", "", False)
        raise HTTPException(status_code=403, detail="请求已过期")

    expected = _make_sign(req.shein_id, req.timestamp)
    if not hmac.compare_digest(req.sign, expected):
        _write_check_request_log(req.shein_id, "", "", False)
        raise HTTPException(status_code=403, detail="签名验证失败")

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                sql = (
                    "SELECT start_time, end_time FROM sheinuploader_software "
                    "WHERE shein_id = %s "
                    "AND CURDATE() BETWEEN DATE(start_time) AND DATE(end_time) "
                    "LIMIT 1"
                )
                cur.execute(sql, (req.shein_id,))
                row = cur.fetchone()
    except Exception:
        _write_check_request_log(req.shein_id, "", "", False)
        raise HTTPException(status_code=500, detail="服务器内部错误")

    if row is None:
        _write_check_request_log(req.shein_id, "", "", False)
        return {"success": False}

    start_time = str(row["start_time"])
    end_time = str(row["end_time"])
    _write_check_request_log(req.shein_id, start_time, end_time, True)

    return {
        "success": True,
        "start_time": start_time,
        "end_time": end_time,
    }


@app.post("/admin/upsert_record")
async def admin_upsert_record(req: AdminUpsertRequest, request: Request):
    """新增或更新一条授权记录。"""
    _require_admin(request)
    client_ip = request.client.host if request.client else "unknown"
    operator = (req.operator or "").strip()

    try:
        start_date = datetime.strptime(req.start_time, "%Y-%m-%d").date()
        end_date = datetime.strptime(req.end_time, "%Y-%m-%d").date()
    except Exception:
        _write_audit_log("upsert", req.shein_id, operator, client_ip, False, "日期格式错误")
        raise HTTPException(status_code=400, detail="日期格式必须为 YYYY-MM-DD")
    if start_date > end_date:
        _write_audit_log("upsert", req.shein_id, operator, client_ip, False, "开始时间晚于结束时间")
        raise HTTPException(status_code=400, detail="开始时间不能晚于结束时间")
    # 按需求统一写入 datetime，时间部分固定为 00:00:00
    start_dt_text = "{} 00:00:00".format(req.start_time)
    end_dt_text = "{} 00:00:00".format(req.end_time)

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM sheinuploader_software WHERE shein_id = %s LIMIT 1",
                    (req.shein_id,),
                )
                exists = cur.fetchone() is not None
                if exists:
                    cur.execute(
                        """
                        UPDATE sheinuploader_software
                        SET start_time = %s, end_time = %s
                        WHERE shein_id = %s
                        """,
                        (start_dt_text, end_dt_text, req.shein_id),
                    )
                    action = "updated"
                else:
                    cur.execute(
                        """
                        INSERT INTO sheinuploader_software (shein_id, start_time, end_time)
                        VALUES (%s, %s, %s)
                        """,
                        (req.shein_id, start_dt_text, end_dt_text),
                    )
                    action = "inserted"
    except Exception as e:
        err = str(e)[:300]
        _write_audit_log("upsert", req.shein_id, operator, client_ip, False, "数据库写入失败: {}".format(err))
        raise HTTPException(status_code=500, detail="写入数据库失败: {}".format(err))

    _write_audit_log("upsert", req.shein_id, operator, client_ip, True, action)

    return {
        "success": True,
        "action": action,
        "record": {
            "shein_id": req.shein_id,
            "start_time": start_dt_text,
            "end_time": end_dt_text,
        },
    }


@app.post("/admin/delete_record")
async def admin_delete_record(req: AdminDeleteRequest, request: Request):
    """按 shein_id 删除授权记录（需删除密码）。"""
    _require_admin(request)
    client_ip = request.client.host if request.client else "unknown"
    operator = (req.operator or "").strip()
    if not hmac.compare_digest(req.delete_password or "", DELETE_PASSWORD):
        _write_audit_log("delete", req.shein_id, operator, client_ip, False, "删除密码错误")
        raise HTTPException(status_code=403, detail="删除密码错误")

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute(
                    "DELETE FROM sheinuploader_software WHERE shein_id = %s",
                    (req.shein_id,),
                )
                deleted = int(cur.rowcount or 0)
    except Exception as e:
        err = str(e)[:300]
        _write_audit_log("delete", req.shein_id, operator, client_ip, False, "数据库删除失败: {}".format(err))
        raise HTTPException(status_code=500, detail="删除数据库记录失败: {}".format(err))

    _write_audit_log(
        "delete",
        req.shein_id,
        operator,
        client_ip,
        True,
        "deleted={}".format(deleted),
    )

    return {
        "success": True,
        "deleted": deleted,
        "shein_id": req.shein_id,
    }


@app.get("/admin/list_records")
async def admin_list_records(
    request: Request,
    shein_id: str = "",
    limit: int = 100,
    offset: int = 0,
):
    """查询记录（支持按 shein_id 精确过滤 + 分页）。"""
    _require_admin(request)

    limit = max(1, min(limit, 1000))
    offset = max(0, offset)
    shein_id = shein_id.strip()

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                if shein_id:
                    cur.execute(
                        "SELECT COUNT(1) AS cnt FROM sheinuploader_software WHERE shein_id = %s",
                        (shein_id,),
                    )
                    total = int(cur.fetchone()["cnt"])
                    cur.execute(
                        """
                        SELECT shein_id, start_time, end_time
                        FROM sheinuploader_software
                        WHERE shein_id = %s
                        ORDER BY start_time DESC
                        LIMIT %s OFFSET %s
                        """,
                        (shein_id, limit, offset),
                    )
                else:
                    cur.execute("SELECT COUNT(1) AS cnt FROM sheinuploader_software")
                    total = int(cur.fetchone()["cnt"])
                    cur.execute(
                        """
                        SELECT shein_id, start_time, end_time
                        FROM sheinuploader_software
                        ORDER BY start_time DESC
                        LIMIT %s OFFSET %s
                        """,
                        (limit, offset),
                    )
                rows = cur.fetchall()
    except Exception:
        raise HTTPException(status_code=500, detail="查询数据库失败")

    items = [
        {
            "shein_id": str(r.get("shein_id", "")),
            "start_time": str(r.get("start_time", "")),
            "end_time": str(r.get("end_time", "")),
        }
        for r in rows
    ]
    return {"success": True, "total": total, "limit": limit, "offset": offset, "items": items}


def _print_db_records(limit: int = 20, offset: int = 0) -> None:
    """本地调试：分页查询并打印数据库中的账号记录。"""
    print("[TEST] 开始测试数据库连接...")
    print(
        "[TEST] DB => host={host} port={port} user={user} database={db}".format(
            host=DB_CONFIG.get("host"),
            port=DB_CONFIG.get("port"),
            user=DB_CONFIG.get("user"),
            db=DB_CONFIG.get("database"),
        )
    )
    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT COUNT(1) AS cnt FROM sheinuploader_software")
                total = int(cur.fetchone()["cnt"])
                cur.execute(
                    """
                    SELECT shein_id, start_time, end_time
                    FROM sheinuploader_software
                    ORDER BY start_time DESC
                    LIMIT %s OFFSET %s
                    """,
                    (limit, offset),
                )
                rows = cur.fetchall()
    except Exception as e:
        print("[TEST] 数据库连接失败：{}".format(str(e)))
        return

    print("[TEST] 数据库连接成功，总记录数: {}".format(total))
    print("[TEST] 当前页: offset={} limit={}".format(offset, limit))
    if not rows:
        print("[TEST] 表中暂无数据。")
        return

    print("-" * 85)
    print("{:<35} {:<22} {:<22}".format("shein_id", "start_time", "end_time"))
    print("-" * 85)
    for row in rows:
        print(
            "{:<35} {:<22} {:<22}".format(
                str(row.get("shein_id", "")),
                str(row.get("start_time", "")),
                str(row.get("end_time", "")),
            )
        )
    print("-" * 85)
    shown = offset + len(rows)
    if total > shown:
        print("[TEST] 仅显示第 {} 到 {} 条记录。".format(offset + 1, shown))


def _print_all_db_records(batch_size: int = 200) -> None:
    """本地调试：按批次打印全量记录，避免一次性加载过多数据。"""
    if batch_size <= 0:
        batch_size = 200
    print("[TEST] 全量打印模式，批次大小: {}".format(batch_size))
    offset = 0
    while True:
        print("\n[TEST] ===== 批次 offset={} =====".format(offset))
        try:
            with pool.connection() as conn:
                with conn.cursor() as cur:
                    cur.execute(
                        """
                        SELECT shein_id, start_time, end_time
                        FROM sheinuploader_software
                        ORDER BY start_time DESC
                        LIMIT %s OFFSET %s
                        """,
                        (batch_size, offset),
                    )
                    rows = cur.fetchall()
        except Exception as e:
            print("[TEST] 数据库连接失败：{}".format(str(e)))
            return

        if not rows:
            if offset == 0:
                print("[TEST] 表中暂无数据。")
            break

        print("-" * 85)
        print("{:<35} {:<22} {:<22}".format("shein_id", "start_time", "end_time"))
        print("-" * 85)
        for row in rows:
            print(
                "{:<35} {:<22} {:<22}".format(
                    str(row.get("shein_id", "")),
                    str(row.get("start_time", "")),
                    str(row.get("end_time", "")),
                )
            )
        print("-" * 85)
        offset += len(rows)


def _parse_args():
    parser = argparse.ArgumentParser(description="auth_api.py 数据库连通性测试")
    parser.add_argument(
        "--limit", type=int, default=20, help="单页打印条数（默认 20）"
    )
    parser.add_argument(
        "--offset", type=int, default=0, help="分页起始偏移（默认 0）"
    )
    parser.add_argument(
        "--all", action="store_true", help="全量打印（按批次）"
    )
    parser.add_argument(
        "--batch-size", type=int, default=200, help="全量打印时每批条数（默认 200）"
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    if args.all:
        _print_all_db_records(batch_size=args.batch_size)
    else:
        _print_db_records(limit=max(1, args.limit), offset=max(0, args.offset))
