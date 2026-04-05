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
from contextlib import contextmanager

import pymysql
from pymysql.cursors import DictCursor
from fastapi import FastAPI, HTTPException, Request
from pydantic import BaseModel, field_validator

# ======================== 配置 ========================

SECURE_KEY = "ShEiN_2025!@xKz9#Qm7$wPv"  # 客户端与服务端共享密钥，部署时务必修改

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

def _check_rate(ip: str) -> bool:
    now = time.time()
    with _rate_lock:
        stamps = _rate_store.setdefault(ip, [])
        stamps[:] = [t for t in stamps if now - t < RATE_LIMIT_WINDOW]
        if len(stamps) >= RATE_LIMIT_MAX:
            return False
        stamps.append(now)
        return True

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

def _make_sign(shein_id: str, timestamp: int) -> str:
    """HMAC-SHA256 签名：与客户端算法一致。"""
    message = f"{shein_id}:{timestamp}"
    return hmac.new(
        SECURE_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()

@app.post("/check_auth")
async def check_auth(req: CheckRequest, request: Request):
    client_ip = request.client.host if request.client else "unknown"
    if not _check_rate(client_ip):
        raise HTTPException(status_code=429, detail="请求过于频繁")

    now_ts = int(time.time())
    if abs(now_ts - req.timestamp) > TIMESTAMP_TOLERANCE:
        raise HTTPException(status_code=403, detail="请求已过期")

    expected = _make_sign(req.shein_id, req.timestamp)
    if not hmac.compare_digest(req.sign, expected):
        raise HTTPException(status_code=403, detail="签名验证失败")

    try:
        with pool.connection() as conn:
            with conn.cursor() as cur:
                sql = (
                    "SELECT start_time, end_time FROM sheinuploader_software "
                    "WHERE shein_id = %s "
                    "AND CURDATE() BETWEEN start_time AND end_time "
                    "LIMIT 1"
                )
                cur.execute(sql, (req.shein_id,))
                row = cur.fetchone()
    except Exception:
        raise HTTPException(status_code=500, detail="服务器内部错误")

    if row is None:
        return {"success": False}

    return {
        "success": True,
        "start_time": str(row["start_time"]),
        "end_time": str(row["end_time"]),
    }


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
