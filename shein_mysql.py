# -*- coding: utf-8 -*-
"""
SHEIN 账号验证（客户端）
通过 HMAC-SHA256 签名访问服务器 auth_api，验证 shein_id 是否有效。
本地不保存任何数据库凭据。
"""

import time
import hmac
import hashlib
import requests

# ====== 与服务端共享的密钥（必须和 auth_api.py 中的 SECURE_KEY 一致）======
_SECURE_KEY = "ShEiN_2025!@xKz9#Qm7$wPv"

# ====== 服务器地址 ======
_AUTH_API_URL = "http://39.103.78.67:8000/check_auth"

_REQUEST_TIMEOUT = 10  # 秒


def _make_sign(shein_id: str, timestamp: int) -> str:
    """HMAC-SHA256 签名，算法与服务端一致。"""
    message = f"{shein_id}:{timestamp}"
    return hmac.new(
        _SECURE_KEY.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def verify_shein_account_detail(shein_id: str):
    """
    向服务器验证 shein_id 是否授权，并返回授权有效期。

    Returns:
        (ok, msg, start_time, end_time)
        start_time / end_time 可能为空字符串（取决于服务端返回）
    """
    shein_id = shein_id.strip()
    if not shein_id:
        return False, "账号不能为空", "", ""

    timestamp = int(time.time())
    sign = _make_sign(shein_id, timestamp)

    payload = {
        "shein_id": shein_id,
        "timestamp": timestamp,
        "sign": sign,
    }

    try:
        resp = requests.post(_AUTH_API_URL, json=payload, timeout=_REQUEST_TIMEOUT)
    except requests.ConnectionError:
        return False, "无法连接验证服务器，请检查网络", "", ""
    except requests.Timeout:
        return False, "验证服务器响应超时，请稍后重试", "", ""
    except Exception as e:
        return False, f"网络异常: {str(e)[:80]}", "", ""

    if resp.status_code == 429:
        return False, "请求过于频繁，请稍后再试", "", ""
    if resp.status_code == 403:
        return False, "验证请求被拒绝（签名或时间戳异常）", "", ""
    if resp.status_code != 200:
        return False, f"服务器错误 (HTTP {resp.status_code})", "", ""

    try:
        data = resp.json()
    except Exception:
        return False, "服务器返回数据格式异常", "", ""

    if data.get("success") is True:
        payload_data = data.get("data") if isinstance(data.get("data"), dict) else {}
        start_time = (
            data.get("start_time")
            or data.get("start")
            or payload_data.get("start_time")
            or payload_data.get("start")
            or ""
        )
        end_time = (
            data.get("end_time")
            or data.get("end")
            or payload_data.get("end_time")
            or payload_data.get("end")
            or ""
        )
        return True, "验证通过", str(start_time or ""), str(end_time or "")

    err_msg = (
        data.get("message")
        or data.get("msg")
        or "该SHEIN账号未授权或已过期，请联系管理员"
    )
    return False, str(err_msg), "", ""


def verify_shein_account(shein_id: str) -> tuple[bool, str]:
    """
    向服务器验证 shein_id 是否授权。

    Returns:
        (True,  "验证通过")       — 账号有效
        (False, "账号未授权...")   — 账号无效或过期
        (False, "网络错误...")     — 无法连接服务器
    """
    ok, msg, _, _ = verify_shein_account_detail(shein_id)
    return ok, msg


if __name__ == "__main__":
    test_id = input("请输入要验证的 SHEIN 账号: ").strip()
    ok, msg = verify_shein_account(test_id)
    print(f"结果: {'通过' if ok else '未通过'} — {msg}")
