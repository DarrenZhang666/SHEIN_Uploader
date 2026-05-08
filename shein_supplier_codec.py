# -*- coding: utf-8 -*-
"""供方货号编码/反解析工具：ASIN <-> XYZ-16位字母数字码。"""

import hashlib
import json
import os
import re
import threading

_ASIN_RE = re.compile(r"^B[A-Z0-9]{9}$", re.I)
_TEN_DIGIT_RE = re.compile(r"^\d{10}$")
_ALNUM16_RE = re.compile(r"^[A-Z0-9]{16}$", re.I)
_SUPPLIER_PREFIX = "XYZ"
_BASE36_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"
_CODE_LEN = 16
_CODE_SPACE = 36 ** _CODE_LEN
_MAX_COLLISION_STEPS = 20000
_CODE_FILE_LOCK = threading.Lock()


def _mapping_file_path():
    base_dir = os.path.join(os.path.expanduser("~"), ".shein_profiles")
    try:
        os.makedirs(base_dir, exist_ok=True)
    except Exception:
        # 若目录创建失败，回退到当前脚本目录
        base_dir = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_dir, "asin_code_map.json")


def _empty_mapping():
    return {"version": 1, "asin_to_code": {}, "code_to_asin": {}}


def _load_mapping():
    path = _mapping_file_path()
    try:
        if not os.path.exists(path):
            return _empty_mapping()
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f) or {}
        asin_to_code = data.get("asin_to_code", {})
        code_to_asin = data.get("code_to_asin", {})
        if not isinstance(asin_to_code, dict) or not isinstance(code_to_asin, dict):
            return _empty_mapping()
        return {
            "version": 1,
            "asin_to_code": {str(k).upper(): str(v) for k, v in asin_to_code.items()},
            "code_to_asin": {str(k): str(v).upper() for k, v in code_to_asin.items()},
        }
    except Exception:
        return _empty_mapping()


def _save_mapping(data):
    path = _mapping_file_path()
    tmp = path + ".tmp"
    payload = {
        "version": 1,
        "asin_to_code": data.get("asin_to_code", {}),
        "code_to_asin": data.get("code_to_asin", {}),
    }
    try:
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass


def _normalize_asin(asin):
    txt = str(asin or "").strip().upper()
    if _ASIN_RE.match(txt):
        return txt
    return ""


def _to_base36_fixed(num, width):
    n = int(num)
    w = int(width)
    if w <= 0:
        return ""
    chars = []
    for _ in range(w):
        n, rem = divmod(n, 36)
        chars.append(_BASE36_ALPHABET[rem])
    return "".join(reversed(chars))


def _base_code_from_asin(asin):
    digest = hashlib.sha256(asin.encode("utf-8")).hexdigest()
    value = int(digest[:20], 16) % _CODE_SPACE
    return _to_base36_fixed(value, _CODE_LEN)


def encode_asin_to_16code(asin):
    """
    将 ASIN 编码成 16 位字母数字字符串（大写）。
    说明：使用本地持久映射保证可反解析。
    """
    asin_txt = _normalize_asin(asin)
    if not asin_txt:
        return ""
    with _CODE_FILE_LOCK:
        data = _load_mapping()
        asin_to_code = data["asin_to_code"]
        code_to_asin = data["code_to_asin"]
        existing = str(asin_to_code.get(asin_txt, "")).strip()
        if _ALNUM16_RE.match(existing):
            return existing.upper()

        # 旧映射（10位纯数字）保留在 code_to_asin 里用于反解析，
        # 但正向生成统一切换为 16 位字母数字。
        base = int(_base_code_from_asin(asin_txt), 36)
        for step in range(_MAX_COLLISION_STEPS):
            code_num = (base + step * 7919) % _CODE_SPACE
            code = _to_base36_fixed(code_num, _CODE_LEN)
            old_asin = str(code_to_asin.get(code, "")).strip().upper()
            if not old_asin or old_asin == asin_txt:
                asin_to_code[asin_txt] = code
                code_to_asin[code] = asin_txt
                _save_mapping(data)
                return code
    return ""


def encode_asin_to_10digit(asin):
    """
    兼容旧函数名：当前返回 16 位字母数字码。
    """
    return encode_asin_to_16code(asin)


def decode_code_to_asin(code):
    """将编码（10位数字/16位字母数字）反解析成 ASIN。"""
    code_txt = str(code or "").strip()
    if not (_TEN_DIGIT_RE.match(code_txt) or _ALNUM16_RE.match(code_txt)):
        return ""
    code_txt = code_txt.upper()
    with _CODE_FILE_LOCK:
        data = _load_mapping()
        asin = str(data.get("code_to_asin", {}).get(code_txt, "")).strip().upper()
        if _ASIN_RE.match(asin):
            return asin
    return ""


def decode_10digit_to_asin(code):
    """兼容旧函数名：支持10位数字和16位字母数字反解析。"""
    return decode_code_to_asin(code)


def build_supplier_no_from_asin(asin, prefix=_SUPPLIER_PREFIX):
    """构建上传到 SHEIN 的供方货号，格式：XYZ-16位字母数字码。"""
    asin_txt = _normalize_asin(asin)
    if not asin_txt:
        return ""
    code = encode_asin_to_16code(asin_txt)
    if code:
        return "{}-{}".format(prefix, code)
    # 映射写入失败时兜底，保持可用性
    return "{}-{}".format(prefix, asin_txt)


def resolve_asin_from_supplier_no(raw_supplier_no, prefix=_SUPPLIER_PREFIX):
    """
    从供方货号中反解析 ASIN。
    支持：
    - XYZ-ABCDEFGH12345678（16位字母数字）
    - XYZ-1234567890（优先按映射反解析）
    - XYZ-B0XXXXXXX（老格式）
    - 任意文本内直接包含 ASIN
    """
    raw = str(raw_supplier_no or "").strip()
    if not raw:
        return ""

    direct = re.search(r"\b(B[A-Z0-9]{9})\b", raw.upper())
    if direct:
        return direct.group(1)

    cleaned = re.sub(r"^(供方货号|货号)\s*[:：]\s*", "", raw, flags=re.I).strip()
    m = re.match(r"^{}\s*-\s*([A-Za-z0-9]+)$".format(re.escape(str(prefix or _SUPPLIER_PREFIX))), cleaned, flags=re.I)
    if not m:
        return ""

    token = str(m.group(1) or "").strip().upper()
    if _ASIN_RE.match(token):
        return token
    if _TEN_DIGIT_RE.match(token) or _ALNUM16_RE.match(token):
        return decode_code_to_asin(token)
    return ""
