# -*- coding: utf-8 -*-
"""
SHEIN ASIN 模块
通过 ASIN 从亚马逊爬取商品信息
"""
import re
import random
import io
import json
import time
import os
import threading
import difflib
from urllib.parse import urlparse
import requests
try:
    import cloudscraper
    _CLOUDSCRAPER_OK = True
except ImportError:
    _CLOUDSCRAPER_OK = False
from bs4 import BeautifulSoup
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from shein_sensitive_clean import SENSITIVE_WORDS, _filter_title

AMAZON_PRODUCT_URL = "https://www.amazon.com/dp/{asin}"

HEADERS_POOL = [
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36 Edg/130.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Microsoft Edge";v="130", "Chromium";v="130", "Not_A Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"macOS"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Connection": "keep-alive",
        "Cache-Control": "max-age=0",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:132.0) Gecko/20100101 Firefox/132.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.5",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Connection": "keep-alive",
        "TE": "trailers",
    },
    {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 14_2_1) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.2 Safari/605.1.15",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "Connection": "keep-alive",
        "upgrade-insecure-requests": "1",
    },
    {
        "User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Google Chrome";v="131", "Chromium";v="131", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Linux"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Connection": "keep-alive",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/129.0.0.0 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-GB,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Google Chrome";v="129", "Chromium";v="129", "Not_A Brand";v="24"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Connection": "keep-alive",
    },
    {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36 OPR/116.0.0.0",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
        "Accept-Encoding": "gzip, deflate, br",
        "sec-ch-ua": '"Chromium";v="131", "Not_A Brand";v="24", "Opera";v="116"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "document",
        "sec-fetch-mode": "navigate",
        "sec-fetch-site": "none",
        "sec-fetch-user": "?1",
        "upgrade-insecure-requests": "1",
        "Connection": "keep-alive",
    },
]

# 可选代理池（留空则不使用，格式: ["http://user:pass@host:port"]）
PROXY_POOL = []

_SESSION_LOCK = threading.Lock()
_SESSION_CACHE = {}
_REQUEST_PACE_LOCK = threading.Lock()
_REQUEST_PACE_STATE = {
    "next_ts": 0.0,          # 下一次允许发起请求的时间点
    "penalty_level": 0,      # 反爬压力级别，越高越慢
    "blocked_streak": 0,     # 连续命中反爬次数
    "last_block_ts": 0.0,    # 最近一次命中反爬时间
}


def _wait_request_slot(base_gap=0.22, jitter=(0.08, 0.35), extra_delay=0.0):
    """
    全局请求节流：跨线程串行化请求起点，避免突发流量。
    base_gap 为基础间隔，jitter 为随机抖动，extra_delay 用于临时降速。
    """
    wait_s = 0.0
    with _REQUEST_PACE_LOCK:
        now = time.time()
        gap = float(base_gap) + random.uniform(float(jitter[0]), float(jitter[1])) + float(extra_delay or 0.0)
        # 命中反爬后，提高请求间隔（上限约 2.8s，避免完全停滞）
        penalty = min(2.0, _REQUEST_PACE_STATE["penalty_level"] * 0.25)
        target_gap = min(2.8, gap + penalty)
        available_at = max(now, _REQUEST_PACE_STATE["next_ts"])
        wait_s = max(0.0, available_at - now)
        _REQUEST_PACE_STATE["next_ts"] = available_at + target_gap
    if wait_s > 0:
        time.sleep(wait_s)


def _record_request_feedback(blocked=False):
    """记录反爬反馈，用于动态升降速。"""
    with _REQUEST_PACE_LOCK:
        if blocked:
            _REQUEST_PACE_STATE["blocked_streak"] = min(
                10, _REQUEST_PACE_STATE["blocked_streak"] + 1
            )
            _REQUEST_PACE_STATE["penalty_level"] = min(
                10, _REQUEST_PACE_STATE["penalty_level"] + 1
            )
            _REQUEST_PACE_STATE["last_block_ts"] = time.time()
        else:
            _REQUEST_PACE_STATE["blocked_streak"] = 0
            # 成功请求逐步退火，避免长时间保持高惩罚
            if _REQUEST_PACE_STATE["penalty_level"] > 0:
                _REQUEST_PACE_STATE["penalty_level"] -= 1


def _recommend_worker_count(max_workers, task_count):
    """
    根据当前反爬压力动态收缩并发，降低中后段封禁概率。
    """
    workers = max(1, min(int(max_workers or 1), int(task_count or 1)))
    with _REQUEST_PACE_LOCK:
        penalty = int(_REQUEST_PACE_STATE.get("penalty_level", 0))
        streak = int(_REQUEST_PACE_STATE.get("blocked_streak", 0))
    if penalty >= 6 or streak >= 3:
        workers = min(workers, 2)
    elif penalty >= 3:
        workers = min(workers, 3)
    return max(1, workers)


def _should_fetch_sku_details():
    """
    高风控压力时降级：跳过 SKU 明细抓取，优先保证主信息抓取成功率。
    """
    with _REQUEST_PACE_LOCK:
        penalty = int(_REQUEST_PACE_STATE.get("penalty_level", 0))
        streak = int(_REQUEST_PACE_STATE.get("blocked_streak", 0))
    if streak >= 2 or penalty >= 5:
        return False
    if penalty >= 3 and random.random() < 0.6:
        return False
    return True


def _get_proxy():
    """随机返回代理配置字典，PROXY_POOL 为空时返回 None。"""
    if not PROXY_POOL:
        return None
    proxy = random.choice(PROXY_POOL)
    return {"http": proxy, "https": proxy}


def _make_browser_cookies(domain):
    """生成模拟浏览器的基础 Cookie。"""
    session_id = "".join(random.choices("0123456789abcdefghijklmnopqrstuvwxyz", k=15))
    ubid = "{}-{}-{}".format(
        random.randint(100, 999),
        random.randint(1000000, 9999999),
        random.randint(1000000, 9999999),
    )
    return {
        "i18n-prefs": "USD",
        "lc-main": "en_US",
        "session-id": session_id,
        "ubid-main": ubid,
    }


def _region_context(region):
    """
    构建地区抓取上下文：
    - 美国时强制使用 amazon.com，并尽量将配送地设为美国（ZIP: 30005）。
    """
    _REGION_DOMAINS = {
        "美国": "www.amazon.com",
        "英国": "www.amazon.co.uk",
        "德国": "www.amazon.de",
        "法国": "www.amazon.fr",
        "日本": "www.amazon.co.jp",
        "加拿大": "www.amazon.ca",
        "澳大利亚": "www.amazon.com.au",
        "意大利": "www.amazon.it",
        "西班牙": "www.amazon.es",
        "墨西哥": "www.amazon.com.mx",
    }
    region_name = str(region or "美国").strip() or "美国"
    domain = _REGION_DOMAINS.get(region_name, "www.amazon.com")
    is_us = (region_name == "美国")
    if is_us:
        domain = "www.amazon.com"
    return {
        "region": region_name,
        "domain": domain,
        "is_us": is_us,
        "ship_zip": "30005",  # Alpharetta, GA
    }


def _build_amazon_dp_url(domain, asin, is_us=False):
    base = "https://{}/dp/{}?language=en_US&currency=USD".format(domain, asin)
    if is_us:
        # 美国站补充常见参数，减少跳转到其它站点/币种的概率
        return base + "&psc=1"
    return base


def _prepare_amazon_session(session, domain, ctx, warmup=False):
    """注入地区 Cookie，并在美国站预热首页/配送地。"""
    if session is None:
        return
    cache_key = "_amz_prepared_{}_{}".format(
        str(domain or "").replace(".", "_"),
        "us" if bool(ctx.get("is_us")) else "nonus"
    )
    if getattr(session, cache_key, False):
        return
    cookie_domain = domain if str(domain).startswith(".") else ".{}".format(domain)
    # 基础浏览器 cookie
    for k, v in _make_browser_cookies(domain).items():
        try:
            session.cookies.set(k, v, domain=domain)
            session.cookies.set(k, v, domain=cookie_domain)
        except Exception:
            pass
    # 地区偏好：美国地区强制美元 + 英文 + CDN 地区提示
    if bool(ctx.get("is_us")):
        zip_code = str(ctx.get("ship_zip") or "30005")
        us_pref = {
            "i18n-prefs": "USD",
            "lc-main": "en_US",
            "sp-cdn": "L5Z:{}".format(zip_code),
        }
        for k, v in us_pref.items():
            try:
                session.cookies.set(k, v, domain="www.amazon.com")
                session.cookies.set(k, v, domain=".amazon.com")
            except Exception:
                pass
        # 访问美国首页建立会话，再通过 POST 设置配送邮编
        if warmup and (not getattr(session, "_amz_us_warmed", False)):
            try:
                warm_headers = random.choice(HEADERS_POOL).copy()
                warm_headers["Referer"] = "https://www.amazon.com/"
                home_r = session.get(
                    "https://www.amazon.com/?language=en_US",
                    headers=warm_headers, timeout=10,
                )
                csrf_token = ""
                if home_r and hasattr(home_r, "text") and home_r.text:
                    for _csrf_pat in [
                        r'CSRF_TOKEN\s*:\s*["\']([^"\']+)',
                        r'anti-csrftoken-a2z["\s:]+([^"\']+)',
                        r'"csrfToken"\s*:\s*"([^"]+)"',
                    ]:
                        _csrf_m = re.search(_csrf_pat, home_r.text)
                        if _csrf_m:
                            csrf_token = _csrf_m.group(1).strip()
                            break
                post_headers = warm_headers.copy()
                post_headers["X-Requested-With"] = "XMLHttpRequest"
                post_headers["Content-Type"] = (
                    "application/x-www-form-urlencoded;charset=UTF-8"
                )
                if csrf_token:
                    post_headers["anti-csrftoken-a2z"] = csrf_token
                addr_r = session.post(
                    "https://www.amazon.com/gp/delivery/ajax/address-change.html",
                    data={
                        "locationType": "LOCATION_INPUT",
                        "zipCode": zip_code,
                        "storeContext": "generic",
                        "deviceType": "web",
                        "pageType": "Gateway",
                        "actionSource": "glow",
                        "almBrandId": "undefined",
                    },
                    headers=post_headers,
                    timeout=8,
                )
                if addr_r and addr_r.status_code == 200:
                    try:
                        _addr_json = addr_r.json()
                        if _addr_json.get("isValidAddress") == 1:
                            setattr(session, "_amz_zip_confirmed", True)
                    except Exception:
                        pass
                setattr(session, "_amz_us_warmed", True)
            except Exception:
                pass
    setattr(session, cache_key, True)


def _extract_domain_from_url(url):
    try:
        return (urlparse(str(url or "")).hostname or "").lower()
    except Exception:
        return ""


def _is_blocked(status_code, text):
    """判断响应是否被反爬拦截。"""
    tl = text.lower()
    return (
        status_code == 503
        or (status_code == 404 and "automated" in tl)
        or "captcha" in tl
        or ("sorry" in tl and "automated" in tl)
        or "robot check" in tl
        or "api-services-support@amazon.com" in tl
    )


def _get_with_retry(session, url, max_attempts=3, base_timeout=12):
    """
    带指数退避 + 抖动的请求重试，每次随机换 UA 和代理。
    返回 (response, headers_used) 或 (None, None)。
    """
    shuffled = random.sample(HEADERS_POOL, len(HEADERS_POOL))
    attempts = min(max_attempts, len(shuffled))
    for attempt in range(attempts):
        _wait_request_slot(base_gap=0.24, jitter=(0.10, 0.32))
        hdrs = shuffled[attempt].copy()
        hdrs["Referer"] = "https://{}/".format(url.split("/")[2])
        proxies = _get_proxy()
        if attempt > 0:
            # 失败退避：按尝试次数指数增长，命中反爬后可自动进一步放大
            wait = min(0.7 * (2 ** (attempt - 1)) + random.uniform(0.2, 0.8), 4.8)
            time.sleep(wait)
        try:
            r = session.get(url, headers=hdrs, proxies=proxies, timeout=(5, base_timeout))
            blocked = _is_blocked(r.status_code, r.text)
            _record_request_feedback(blocked=blocked)
            if not blocked:
                return r, hdrs
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            _record_request_feedback(blocked=True)
            continue
        except Exception:
            _record_request_feedback(blocked=True)
            continue
    return None, None


def _to_sx1500(img_src):
    """将亚马逊图片 URL 转换为 SX1500 高质量格式。"""
    if "images/I/" in img_src:
        match = re.search(r'images/I/([^._]+)', img_src)
        if match:
            img_id = match.group(1)
            img_src = f"https://m.media-amazon.com/images/I/{img_id}._SX1500_.jpg"
    for old in [
        "._SS40_", "._SS75_", "._SX38_", "._SY38_", "._SX75_",
        "._SX100_", "._SX200_", "._SX300_", "._SX500_", "._SX1000_",
        "._SL75_", "._SL100_", "._SL200_", "._SL300_", "._SL500_",
        "._SL1000_", "._AA50_", "._AA75_",
    ]:
        img_src = img_src.replace(old, "._SX1500_")
    return img_src


def _collect_main_images_from_soup(soup, max_count=None):
    main_images = []

    try:
        alt_images_container = soup.select_one("#altImages")
        if alt_images_container:
            for img_li in alt_images_container.select("li"):
                try:
                    img_el = img_li.select_one("img")
                    if img_el:
                        img_src = (img_el.get("data-old-hires")
                                   or img_el.get("data-a-hires")
                                   or img_el.get("src"))
                        if img_src and img_src.lower().endswith((".jpg", ".jpeg", ".png")):
                            img_src = _to_sx1500(img_src)
                            if img_src not in main_images:
                                main_images.append(img_src)
                                if max_count and len(main_images) >= max_count:
                                    return main_images
                except Exception:
                    pass
    except Exception:
        pass

    try:
        image_block = soup.select_one("#imageBlock, #imageBlockContainer")
        if image_block:
            for img_el in image_block.select("img"):
                try:
                    img_src = (img_el.get("data-old-hires")
                               or img_el.get("data-a-hires")
                               or img_el.get("src"))
                    if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                        if img_src.lower().endswith((".jpg", ".jpeg", ".png")):
                            img_src = _to_sx1500(img_src)
                            if img_src not in main_images:
                                main_images.append(img_src)
                                if max_count and len(main_images) >= max_count:
                                    return main_images
                except Exception:
                    pass
    except Exception:
        pass

    try:
        landing_img = soup.select_one("#landingImage, #imgBlkFront")
        if landing_img:
            img_src = (landing_img.get("data-old-hires")
                       or landing_img.get("data-a-hires")
                       or landing_img.get("src"))
            if img_src and img_src.lower().endswith((".jpg", ".jpeg", ".png")):
                img_src = _to_sx1500(img_src)
                if img_src not in main_images:
                    main_images.append(img_src)
    except Exception:
        pass

    return main_images[:max_count] if max_count else main_images


def _extract_json_object_by_key(text, key):
    marker = '"{}"'.format(key)
    start = text.find(marker)
    if start < 0:
        start = text.find(key)
    if start < 0:
        return None

    brace_start = text.find("{", start)
    if brace_start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(brace_start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[brace_start:i + 1])
                except Exception:
                    return None
    return None


def _extract_json_array_by_key(text, key):
    marker = '"{}"'.format(key)
    start = text.find(marker)
    if start < 0:
        start = text.find(key)
    if start < 0:
        return None

    arr_start = text.find("[", start)
    if arr_start < 0:
        return None

    depth = 0
    in_string = False
    escaped = False
    for i in range(arr_start, len(text)):
        ch = text[i]
        if escaped:
            escaped = False
            continue
        if ch == "\\":
            escaped = True
            continue
        if ch == '"':
            in_string = not in_string
            continue
        if in_string:
            continue
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                try:
                    return json.loads(text[arr_start:i + 1])
                except Exception:
                    return None
    return None


def _clean_dimension_name(name):
    n = str(name or "").strip().replace("_name", "")
    n = n.replace(" ", "_").lower()
    if n == "colour":
        n = "color"
    return n


def _split_dimension_parts(raw_dimension_key):
    """
    分割维度键。
    支持格式：
    - "0_0" -> ['0', '0']（数字索引）
    - "size=M_color=Red" -> ['size=M', 'color=Red']（键值对）
    - "M,Red" -> ['M', 'Red']（逗号分隔）
    """
    txt = str(raw_dimension_key or "").strip()
    
    # 如果包含 = 或 :，则按 ; | , 分隔
    if "=" in txt or ":" in txt:
        parts = txt.replace(";", ",").replace("|", ",").split(",")
        return [p.strip() for p in parts if p.strip()]
    
    # 否则按 _ 分隔（用于纯数字索引如 0_0）
    parts = txt.replace(";", "_").replace("|", "_").split("_")
    return [p.strip() for p in parts if p.strip()]


def _normalize_sku_attrs(raw_dimension_key, dimension_names=None, value_display_map=None):
    """
    将原始维度键转换为可读的规格文本。
    例如：0_0 -> "Size M / Color Red"
    """
    parts = _split_dimension_parts(raw_dimension_key)
    if not parts:
        return ""

    value_display_map = value_display_map or {}
    dimension_names = dimension_names or []
    values = []
    
    for idx, p in enumerate(parts):
        dim_name = ""
        raw_val = p

        # 尝试从键值对中提取
        if "=" in p:
            key, raw_val = p.split("=", 1)
            dim_name = _clean_dimension_name(key)
        elif ":" in p:
            key, raw_val = p.split(":", 1)
            dim_name = _clean_dimension_name(key)
        else:
            # 纯数字索引：使用 dimension_names 和 value_display_map
            raw_val = str(p).strip()
            if idx < len(dimension_names):
                dim_name = _clean_dimension_name(dimension_names[idx])

        raw_val = str(raw_val).strip()
        display_val = raw_val
        
        # 查找显示值
        if dim_name and dim_name in value_display_map:
            display_val = value_display_map[dim_name].get(raw_val, raw_val)
        elif "_index_" in value_display_map:
            display_val = value_display_map["_index_"].get(raw_val, raw_val)

        display_val = str(display_val).strip()
        if display_val:
            # 如果有维度名，则格式为 "DimName: Value"，否则只显示值
            if dim_name:
                values.append("{}: {}".format(dim_name.capitalize(), display_val))
            else:
                values.append(display_val)

    return " / ".join(values) if values else ""


def _extract_dimension_basis(raw_dimension_key, dimension_names=None):
    parts = _split_dimension_parts(raw_dimension_key)
    basis = []

    for idx, p in enumerate(parts):
        if "=" in p:
            k = _clean_dimension_name(p.split("=", 1)[0])
        elif ":" in p:
            k = _clean_dimension_name(p.split(":", 1)[0])
        elif isinstance(dimension_names, list) and idx < len(dimension_names):
            k = _clean_dimension_name(dimension_names[idx])
        else:
            k = ""

        if k and k not in basis:
            basis.append(k)

    return basis


def _build_variation_value_maps(page_text):
    dimension_names = []
    value_display_map = {}

    variation_values = _extract_json_object_by_key(page_text, "variationValues")
    if isinstance(variation_values, dict):
        for dim_name, dim_values in variation_values.items():
            dim_key = _clean_dimension_name(dim_name)
            if dim_key and dim_key not in dimension_names:
                dimension_names.append(dim_key)
            if isinstance(dim_values, list):
                value_display_map[dim_key] = {
                    str(i): str(v).strip()
                    for i, v in enumerate(dim_values)
                    if str(v).strip()
                }

    display_data = _extract_json_object_by_key(page_text, "dimensionValuesDisplayData")
    if isinstance(display_data, dict):
        idx_map = {}
        for k, v in display_data.items():
            kk = str(k).strip()
            vv = str(v).strip()
            if kk and vv:
                idx_map[kk] = vv
        if idx_map:
            value_display_map["_index_"] = idx_map

    return dimension_names, value_display_map


def _extract_color_images_map(page_text):
    color_images = _extract_json_object_by_key(page_text, "colorImages")
    if not isinstance(color_images, dict):
        return {}

    result = {}
    for color_key, items in color_images.items():
        urls = []
        if isinstance(items, list):
            for it in items:
                if not isinstance(it, dict):
                    continue
                u = (it.get("hiRes") or it.get("large") or it.get("mainUrl")
                     or it.get("thumb") or it.get("variant"))
                if isinstance(u, str) and u:
                    uu = _to_sx1500(u) if "images/I/" in u else u
                    if uu not in urls:
                        urls.append(uu)
        if urls:
            result[str(color_key).strip()] = urls
    return result



def _extract_non_color_specs(soup):
    """
    从亚马逊商品页面提取非 color 维度的所有规格选项。
    返回 {"size": ["65L", "96L"], ...} 格式的字典。
    """
    result = {}
    # 查找所有 inline-twister-row-XXX_name 区块，排除 color
    for row in soup.select("[id^='inline-twister-row-']"):
        row_id = row.get("id", "")
        if "color" in row_id.lower() or "colour" in row_id.lower():
            continue
        # 提取维度名称
        dim_label_el = row.select_one(".a-color-secondary")
        if dim_label_el:
            dim_name = dim_label_el.get_text(strip=True).rstrip(":：").strip()
        else:
            # 从 id 推断：inline-twister-row-size_name -> size
            dim_name = row_id.replace("inline-twister-row-", "").replace("_name", "").capitalize()
        if not dim_name:
            continue
        # 收集文字选项值
        values = []
        for li in row.select("li[data-asin]"):
            # 文字型 swatch
            txt_el = li.select_one(".swatch-title-text-display")
            if txt_el:
                v = txt_el.get_text(strip=True)
                if v and v not in values:
                    values.append(v)
                continue
            # 图片型 swatch（img alt）
            img_el = li.select_one("img[alt]")
            if img_el:
                v = img_el.get("alt", "").strip()
                if v and v not in values:
                    values.append(v)
        if values:
            result[dim_name] = values
    return result

def _extract_twister_dimension_skus(soup):
    """
    从亚马逊 Twister 区域提取 SKU 维度信息（HTML 兜底）：
    - 返回 (asin_dim_map, dim_order)
    - asin_dim_map: {asin: {dim_name: dim_value, ...}, ...}
    - dim_order: 页面出现顺序的维度名列表（如 ["color", "size"]）
    """
    asin_dim_map = {}
    dim_order = []
    if soup is None:
        return asin_dim_map, dim_order

    def _extract_dim_name_from_row(row, row_id):
        # 先尝试标签文案
        try:
            label = row.select_one(".a-form-label, .a-color-secondary")
            if label:
                txt = str(label.get_text(" ", strip=True) or "").strip().rstrip(":：")
                if txt:
                    return _clean_dimension_name(txt)
        except Exception:
            pass
        # 再从 id 推断
        rid = str(row_id or "")
        rid = rid.replace("inline-twister-row-", "").replace("_name", "").strip()
        return _clean_dimension_name(rid)

    def _extract_value_from_li(li):
        # 文字型
        for sel in [".swatch-title-text-display", ".a-button-text", ".a-size-base"]:
            try:
                el = li.select_one(sel)
                if el:
                    txt = str(el.get_text(" ", strip=True) or "").strip()
                    if txt and txt not in ("Currently unavailable.",):
                        return txt
            except Exception:
                continue
        # 图片型
        try:
            img = li.select_one("img[alt]")
            if img:
                txt = str(img.get("alt") or "").strip()
                if txt:
                    return txt
        except Exception:
            pass
        # 属性兜底
        for attr in ["title", "aria-label", "data-defaultasin"]:
            try:
                txt = str(li.get(attr) or "").strip()
                if txt:
                    return txt
            except Exception:
                continue
        return ""

    for row in soup.select("[id^='inline-twister-row-']"):
        try:
            row_id = row.get("id", "")
            dim_name = _extract_dim_name_from_row(row, row_id)
            if not dim_name:
                continue
            if dim_name not in dim_order:
                dim_order.append(dim_name)
            for li in row.select("li[data-asin]"):
                asin_val = str(li.get("data-asin") or "").strip()
                if not asin_val:
                    continue
                dim_value = _extract_value_from_li(li)
                if not dim_value:
                    continue
                if asin_val not in asin_dim_map:
                    asin_dim_map[asin_val] = {}
                # 同一维度保留首次非空值
                if not asin_dim_map[asin_val].get(dim_name):
                    asin_dim_map[asin_val][dim_name] = dim_value
        except Exception:
            continue

    return asin_dim_map, dim_order

def _extract_color_only_asins(soup):
    """
    从亚马逊商品页面直接解析 Color 维度的 SKU ASIN 列表。
    查找 id='inline-twister-row-color_name' 下所有 <li data-asin> 元素。
    返回有序的 [(asin, color_name), ...] 列表，找不到则返回空列表。
    """
    result = []
    seen = set()
    color_row = soup.select_one(
        "#inline-twister-row-color_name, "
        "[id*='twister'][id*='color']"
    )
    if color_row:
        for li in color_row.select("li[data-asin]"):
            asin_val = li.get("data-asin", "").strip()
            if not asin_val or asin_val in seen:
                continue
            seen.add(asin_val)
            # 尝试获取颜色名称（img alt 属性）
            img = li.select_one("img[alt]")
            color_name = img["alt"].strip() if img and img.get("alt") else ""
            result.append((asin_val, color_name))
    return result


def _split_color_candidates(color_name):
    """
    将颜色名拆分为候选颜色（按优先级排序）。
    规则：
    1) 含 '&' 时优先取 '&' 前面的颜色；
    2) 支持空格/斜杠/逗号等分隔（如 "orange blue"）；
    3) 去重并保序。
    """
    raw = str(color_name or "").strip().lower()
    if not raw:
        return []

    # 先按 & 分段，确保 "& 前优先"
    amp_parts = [p.strip() for p in raw.split("&") if p.strip()]
    if not amp_parts:
        amp_parts = [raw]

    candidates = []
    for part in amp_parts:
        # 先加入整段连写词，提升“相近标准色”匹配准确率（如 dusty purple -> dustypurple）
        packed = re.sub(r"[^a-z0-9]", "", part)
        if packed and packed not in candidates:
            candidates.append(packed)
        # 将其它连接符统一为空格
        norm = re.sub(r"[/|,+\-]+", " ", part)
        tokens = [t for t in re.split(r"\s+", norm) if t]
        # 优先加入分段首词（如 "orange blue" 优先 orange）
        if tokens:
            first = re.sub(r"[^a-z]", "", tokens[0])
            if first and first not in candidates:
                candidates.append(first)
        # 其余词作为次级候选
        for tk in tokens[1:]:
            c = re.sub(r"[^a-z]", "", tk)
            if c and c not in candidates:
                candidates.append(c)
    return candidates


def _normalize_color_token(txt):
    """颜色词标准化：去空格/连接符/非字母数字并转小写。"""
    t = str(txt or "").strip().lower()
    if not t:
        return ""
    return re.sub(r"[^a-z0-9]", "", t)


# SHEIN 标准颜色（英文规范词），用于过滤非标准颜色 SKU。
# 说明：包含用户提供的标准色及常见别名/连写形式，统一按标准化后匹配。
_SHEIN_STANDARD_COLOR_TOKENS = {
    # 基础色
    "apricot", "black", "white", "grey", "gray", "red", "blue", "green", "yellow",
    "pink", "purple", "brown", "orange", "gold", "silver", "beige", "khaki",
    "camel", "clear", "multicolor", "maroon",
    # 组合/深浅/常见扩展
    "blackand", "redand", "blueand", "blackandwhite",
    "dark grey", "light grey", "dark green", "navy blue", "teal blue", "mint blue",
    "mint green", "baby pink", "baby blue", "dusty blue", "dusty pink",
    "dusty purple", "rose", "rose red", "hot pink", "coral pink", "coral orange",
    "army green", "royal blue", "olive green", "lime green",
    "burgundy", "ginger", "burnt orange", "redwood", "lilac purple", "violet purple",
    "mauve purple", "mustard yellow", "rust brown", "rusty rose", "red violet",
    "coffee brown", "chocolate brown", "mocha brown", "champagne", "bronze",
    "cadet blue", "watermelon pink",
}

# 颜色别名（键=归一化后的候选词，值=归一化后的标准词）
_SHEIN_COLOR_ALIASES = {
    "blackandwhite": "blackand",
    "darkgray": "dark grey",
    "lightgray": "light grey",
    "navy": "navy blue",
    "teal": "teal blue",
    "mint": "mint green",
    "baby": "baby pink",
    "dusty": "dusty pink",
    "lilac": "lilac purple",
    "violet": "violet purple",
    "mauve": "mauve purple",
    "mustard": "mustard yellow",
    "coffee": "coffee brown",
    "chocolate": "chocolate brown",
    "mocha": "mocha brown",
    "coral": "coral pink",
    "burntora": "burnt orange",
}

_NON_COLOR_WORD_TOKENS = {
    "pack", "packs", "pc", "pcs", "piece", "pieces", "set", "sets",
    "count", "qty", "unit", "units", "assorted", "mix", "mixed",
}


def _canonicalize_shein_color(color_token):
    """将颜色候选词映射为 SHEIN 标准颜色词；非标准返回空字符串。"""
    key = _normalize_color_token(color_token)
    if not key:
        return ""
    # 先剔除明显不是颜色的噪音词（如 2|1pack / 3pcs / set）
    if _is_obviously_non_color_token(color_token):
        return ""
    key = _SHEIN_COLOR_ALIASES.get(key, key)
    if key in _SHEIN_STANDARD_COLOR_TOKENS:
        return key
    # 前缀兼容：处理页面省略号截断（如 lilac pur... / waterm...）
    for token in _SHEIN_STANDARD_COLOR_TOKENS:
        if (len(key) >= 4 and token.startswith(key)) or (len(token) >= 4 and key.startswith(token)):
            return token
    # 相近词匹配：处理拼写误差/截断/连接词差异（如 chocola... -> chocolatebrown）
    best_token = ""
    best_score = 0.0
    for token in _SHEIN_STANDARD_COLOR_TOKENS:
        # 仅对“长度足够且非数字噪音”的词做相近匹配，避免 pack/1pack 误判
        if len(key) < 5 or re.search(r"\d", key):
            continue
        score = difflib.SequenceMatcher(None, key, token).ratio()
        if score > best_score:
            best_score = score
            best_token = token
    if best_token and best_score >= 0.80:
        return best_token
    return ""


def _is_obviously_non_color_token(color_token):
    """
    判断候选值是否明显不是颜色（包装数量/纯数字/单位类文本）。
    例如：2|1pack、3pcs、10set、12count。
    """
    raw = str(color_token or "").strip().lower()
    if not raw:
        return True
    compact = _normalize_color_token(raw)
    if not compact:
        return True

    letters = re.sub(r"[^a-z]", "", compact)
    digits = re.sub(r"[^0-9]", "", compact)

    # 纯数字/无字母，直接视为非颜色
    if not letters:
        return True

    # pack/pcs/set/count 等关键词，通常是包装数量而非颜色
    for word in _NON_COLOR_WORD_TOKENS:
        if word in letters:
            return True

    # 数字+很短字母（如 1bk / 2pc）通常不是有效颜色名
    if digits and len(letters) <= 3:
        return True
    return False


def _filter_nonstandard_color_skus(sku_list):
    """
    对颜色 SKU 执行 SHEIN 标准色规范：
    1) 能映射到标准色时，优先替换为 SHEIN 标准色；
    2) 若替换后会导致颜色重复，则回退保留原颜色（不替换）；
    3) 非标准色不丢弃，保留抓取并在 sku_attributes 末尾追加提示；
    4) 同一商品最终颜色不重复，无法避免重复时跳过该 SKU。
    返回：(processed_sku_list, marked_nonstandard_count, replaced_count)
    """
    if not sku_list:
        return sku_list, 0, 0

    def _replace_color_in_attrs(attr_text, new_color):
        t = str(attr_text or "").strip()
        if not t:
            return "Color: {}".format(new_color)
        if re.search(r"(?:color|colour|颜色)\s*:", t, flags=re.IGNORECASE):
            return re.sub(
                r"((?:color|colour|颜色)\s*:\s*)([^/]+)",
                lambda m: "{}{}".format(m.group(1), new_color),
                t,
                count=1,
                flags=re.IGNORECASE
            ).strip()
        # 没有显式 Color 字段时，尽量保留其它规格并补首段颜色
        parts = [p.strip() for p in t.split("/") if str(p).strip()]
        if not parts:
            return "Color: {}".format(new_color)
        parts[0] = "Color: {}".format(new_color)
        return " / ".join(parts)

    kept = []
    marked_nonstandard = 0
    replaced = 0
    used_final_colors = set()
    for sku in sku_list:
        basis = [str(b).lower() for b in (sku.get("dimension_basis") or [])]
        is_color_sku = any("color" in b or "colour" in b for b in basis)
        if not is_color_sku:
            kept.append(sku)
            continue
        raw_color = _extract_color_from_attrs(sku.get("sku_attributes", ""))
        cands = _split_color_candidates(raw_color)
        # 追加整句归一化候选，避免仅按首词导致误匹配
        packed_raw = _normalize_color_token(raw_color)
        if packed_raw and packed_raw not in cands:
            cands.append(packed_raw)
        if not cands and raw_color:
            cands = [packed_raw] if packed_raw else []
        canon = ""
        for c in cands:
            canon = _canonicalize_shein_color(c)
            if canon:
                break

        sku2 = dict(sku)
        old_raw = _normalize_color_token(raw_color)
        final_color = raw_color
        replaced_ok = False

        # 能替换时优先替换；若替换后颜色冲突，则回退到原色不替换
        if canon:
            if canon not in used_final_colors:
                final_color = canon
                replaced_ok = bool(old_raw and old_raw != canon)
            else:
                final_color = raw_color

        final_key = _normalize_color_token(final_color)
        if final_key and final_key in used_final_colors:
            # 最终颜色仍冲突，跳过该 SKU，确保同商品颜色不重复
            continue

        if canon and final_key == canon:
            sku2["sku_attributes"] = _replace_color_in_attrs(sku2.get("sku_attributes", ""), canon)
            if replaced_ok:
                replaced += 1
        else:
            # 保留原色并标注：该颜色未能替换为标准色
            cur_attr = str(sku2.get("sku_attributes", "") or "").strip()
            tip = "此颜色不是SHEIN标准颜色"
            if tip not in cur_attr:
                sku2["sku_attributes"] = "{} / {}".format(cur_attr, tip) if cur_attr else tip
            marked_nonstandard += 1

        if final_key:
            used_final_colors.add(final_key)
        kept.append(sku2)
    return kept, marked_nonstandard, replaced


def _extract_color_from_attrs(attr_text):
    """从 sku_attributes 中抽取颜色值文本。"""
    t = str(attr_text or "").strip()
    if not t:
        return ""
    m = re.search(r"(?:color|colour|颜色)\s*:\s*([^/]+)", t, flags=re.IGNORECASE)
    if m:
        return m.group(1).strip()
    # 回退：取第一个片段
    return t.split("/", 1)[0].strip()


def _enforce_unique_color_skus(sku_list):
    """
    对 color 维度 SKU 执行唯一化规则：
    1) 含 '&' 优先取前色；
    2) 前色冲突则尝试后色；
    3) 前后都冲突则随机删重（不保留该重复 SKU）。
    """
    if not sku_list:
        return sku_list

    color_indices = []
    for i, sku in enumerate(sku_list):
        basis = [str(b).lower() for b in (sku.get("dimension_basis") or [])]
        if any("color" in b or "colour" in b for b in basis):
            color_indices.append(i)

    if not color_indices:
        return sku_list

    used_colors = set()
    chosen_by_idx = {}
    dropped = set()
    # 随机顺序决定冲突保留者，满足“随机删重”
    process_order = list(color_indices)
    random.shuffle(process_order)

    for idx in process_order:
        sku = sku_list[idx]
        raw_color = _extract_color_from_attrs(sku.get("sku_attributes", ""))
        candidates = _split_color_candidates(raw_color)
        if not candidates and raw_color:
            c = re.sub(r"[^a-z]", "", raw_color.lower())
            if c:
                candidates = [c]

        chosen = ""
        for c in candidates:
            if c and c not in used_colors:
                chosen = c
                break
        if chosen:
            chosen_by_idx[idx] = chosen
            used_colors.add(chosen)
        else:
            dropped.add(idx)

    result = []
    for i, sku in enumerate(sku_list):
        if i in dropped:
            continue
        if i in chosen_by_idx:
            sku = dict(sku)
            sku["sku_attributes"] = "Color: {}".format(chosen_by_idx[i])
        result.append(sku)

    # 兜底：避免全部被删空
    if not result and sku_list:
        first = dict(sku_list[0])
        raw = _extract_color_from_attrs(first.get("sku_attributes", ""))
        cands = _split_color_candidates(raw)
        first["sku_attributes"] = "Color: {}".format(cands[0] if cands else (raw or "default"))
        return [first]
    return result


def _pick_images_from_color_map(color_image_map, *candidate_texts, max_count=5):
    if not color_image_map:
        return []

    candidates = [str(x).lower() for x in candidate_texts if x]
    for key, imgs in color_image_map.items():
        k = str(key).lower().strip()
        for raw in candidates:
            if k and raw and (k in raw or raw in k):
                return imgs[:max_count]

    if len(color_image_map) == 1:
        return list(color_image_map.values())[0][:max_count]

    return []


def _fetch_page_with_selenium(url, timeout=20, region="美国", ship_zip="30005"):
    """
    使用 Selenium 无头 Chrome 抓取页面 HTML，绕过亚马逊反爬。
    返回页面 HTML 字符串，失败返回 None。
    """
    try:
        from selenium import webdriver
        from selenium.webdriver.chrome.options import Options
        from selenium.webdriver.chrome.service import Service
        opts = Options()
        opts.add_argument("--headless=new")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        ua = random.choice(HEADERS_POOL)["User-Agent"]
        opts.add_argument("--user-agent={}".format(ua))
        opts.add_argument("--lang=en-US")
        opts.add_argument("--window-size=1280,800")

        # 优先使用已知的 chromedriver 路径
        _base = os.path.dirname(os.path.abspath(__file__))
        _known = os.path.join(_base, ".wdm", "drivers", "chromedriver", "win64", "146.0.7680.80", "chromedriver-win32", "chromedriver.exe")
        if os.path.exists(_known):
            driver_path = _known
        else:
            driver_path = None
            for _root, _dirs, _files in os.walk(_base):
                _dirs[:] = [d for d in _dirs if d != "__pycache__"]
                if "chromedriver.exe" in _files:
                    driver_path = os.path.join(_root, "chromedriver.exe")
                    break
        if driver_path:
            driver = webdriver.Chrome(service=Service(driver_path), options=opts)
        else:
            driver = webdriver.Chrome(options=opts)

        try:
            driver.set_page_load_timeout(timeout)
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined})"})
            # 美国地区：先打开美国站并尝试设置配送地为美国，再抓取详情页
            if str(region or "").strip() == "美国":
                try:
                    driver.get("https://www.amazon.com/?language=en_US")
                    time.sleep(1.5)
                    try:
                        trigger = driver.find_element(
                            "css selector", "#nav-global-location-popover-link"
                        )
                        trigger.click()
                        # 等待邮编输入框出现
                        zip_input = None
                        for _wi in range(12):
                            try:
                                zip_input = driver.find_element(
                                    "css selector", "#GLUXZipUpdateInput"
                                )
                                if zip_input.is_displayed():
                                    break
                            except Exception:
                                pass
                            time.sleep(0.3)
                        if zip_input:
                            zip_input.clear()
                            zip_input.send_keys(str(ship_zip or "30005"))
                            time.sleep(0.3)
                            # 点击 Apply 按钮
                            try:
                                _apply = driver.find_element(
                                    "css selector",
                                    "#GLUXZipUpdate input[type='submit']",
                                )
                                _apply.click()
                            except Exception:
                                try:
                                    driver.find_element(
                                        "css selector", "#GLUXZipUpdate"
                                    ).click()
                                except Exception:
                                    pass
                            time.sleep(1.5)
                            # 点击 Done/Continue/Close 确认按钮
                            for _dsel in [
                                "#GLUXConfirmClose",
                                ".a-popover-footer .a-button-primary",
                                "[name='glowDoneButton']",
                                ".a-popover-close",
                            ]:
                                try:
                                    _done = driver.find_element("css selector", _dsel)
                                    if _done.is_displayed():
                                        _done.click()
                                        time.sleep(0.5)
                                        break
                                except Exception:
                                    continue
                            time.sleep(1.0)
                    except Exception:
                        pass
                except Exception:
                    pass
            driver.get(url)
            time.sleep(3)
            html = driver.page_source
            return html
        finally:
            try:
                driver.quit()
            except Exception:
                pass
    except Exception:
        return None


def _fetch_sku_images(session, domain, sku_asin, headers, max_count=5):
    """拉取单个 SKU 页面的主图，失败时返回空列表。"""
    try:
        sku_url = _build_amazon_dp_url(domain, sku_asin, is_us=("amazon.com" in str(domain).lower()))
        # 只发起一次请求，避免 SKU 链路请求量过大触发风控
        r, _ = _get_with_retry(session, sku_url, max_attempts=1, base_timeout=8)
        if r is None:
            return []
        sku_soup = BeautifulSoup(r.text, "html.parser")
        return _collect_main_images_from_soup(sku_soup, max_count=max_count)
    except Exception:
        return []


def _fetch_all_sku_images_concurrently(session, domain, sku_asins, hdrs, max_workers=6, max_count=5):
    """并发拉取多个 SKU 的图片，返回 {sku_asin: [img_url, ...]} 字典。"""
    results = {}
    if not sku_asins:
        return results
    worker_count = _recommend_worker_count(max_workers, len(sku_asins))
    with ThreadPoolExecutor(max_workers=worker_count) as executor:
        future_to_asin = {
            executor.submit(_fetch_sku_images, session, domain, asin, hdrs, max_count): asin
            for asin in sku_asins
        }
        for future in as_completed(future_to_asin):
            asin = future_to_asin[future]
            try:
                results[asin] = future.result()
            except Exception:
                results[asin] = []
    return results


def _normalize_image_list(images, max_count=None):
    """清洗并去重图片列表，保持原有顺序。"""
    out = []
    for u in (images or []):
        uu = str(u or "").strip()
        if not uu or uu in out:
            continue
        out.append(uu)
        if max_count and len(out) >= int(max_count):
            break
    return out


def _filter_skus_by_min_images(sku_list, min_images=2):
    """
    过滤图片不足的 SKU：
    - 每个 SKU 至少需要 min_images 张图
    - 图片会先去重后再计数
    返回 (filtered_sku_list, dropped_count)
    """
    kept = []
    dropped = 0
    for sku in (sku_list or []):
        sku2 = dict(sku or {})
        imgs = _normalize_image_list(sku2.get("images", []))
        if len(imgs) < int(min_images or 0):
            dropped += 1
            continue
        sku2["images"] = imgs
        kept.append(sku2)
    return kept, dropped


_SENSITIVE_REPLACEMENT_MAP = {
    "sales": "popular",
    "on sale": "special offer",
    "clearance": "special selection",
    "flash sale": "limited offer",
    "cheapest": "affordable",
    "lowest price": "great value",
    "free": "included",
    "best seller": "customer favorite",
    "bestselling": "popular",
    "top": "high-quality",
    "best": "quality",
    "no.1": "leading",
    "first": "premium",
    "only": "selected",
    "perfect": "well-made",
    "ultimate": "enhanced",
    "extreme": "strong",
    "100%": "high",
    "never": "rarely",
    "unique": "distinctive",
    "eco-friendly": "environment-conscious",
    "organic": "natural-style",
    "handmade": "carefully crafted",
    "medical": "wellness",
    "therapeutic": "comfort",
    "cure": "help",
    "treat": "care for",
    "heal": "soothe",
    "weight loss": "lightweight support",
    "slimming": "streamlined fit",
    "whitening": "brightening",
    "anti-aging": "care",
    "anti-wrinkle": "smooth-look",
}


def _replace_sensitive_words(text):
    """将敏感词替换为中性表达，避免整句删除导致文案缺失。"""
    if not text:
        return ""
    result = str(text)
    for word in sorted(SENSITIVE_WORDS, key=len, reverse=True):
        w = str(word or "").strip()
        if not w:
            continue
        replacement = _SENSITIVE_REPLACEMENT_MAP.get(w.lower(), "quality")
        pattern = re.compile(
            r"(?<![A-Za-z0-9]){}(?![A-Za-z0-9])".format(re.escape(w)),
            re.IGNORECASE
        )
        result = pattern.sub(replacement, result)
    result = re.sub(r"\s+([,.;:!?])", r"\1", result)
    result = re.sub(r"\s{2,}", " ", result).strip(" ,;-\n\t")
    return result


def _build_intro_from_title(title):
    """当无商品特点时，根据标题生成一句简短介绍。"""
    clean_title = _replace_sensitive_words(_filter_title(title or ""))
    clean_title = re.sub(r"\s{2,}", " ", clean_title).strip(" -_,.;")
    if not clean_title:
        return "Designed for everyday use with comfortable and practical details."
    short_title = " ".join(clean_title.split()[:12]).strip()
    if not short_title:
        return "Designed for everyday use with comfortable and practical details."
    return "{} with practical details for everyday comfort and easy styling.".format(short_title)


def fetch_amazon_product(asin, region="美国"):
    ctx = _region_context(region)
    domain = ctx["domain"]
    url = _build_amazon_dp_url(domain, asin, is_us=ctx["is_us"])
    res = {"asin": asin, "title": "获取失败", "price": "N/A", "rating": "N/A",
           "reviews": "N/A", "brand": "N/A", "image_url": "",
           "description": "", "features": [], "url": url,
           "description_images": [], "main_images": [], "sku_list": [], "other_specs": {}}
    res["requested_region"] = ctx["region"]
    res["requested_domain"] = domain
    res["requested_zip"] = ctx.get("ship_zip", "")
    res["final_url"] = url
    res["final_domain"] = _extract_domain_from_url(url)
    res["fetch_channel"] = ""
    res["zip_applied_hint"] = False
    try:
        def _is_low_stock_message(_text):
            t = str(_text or "").strip().lower()
            if not t:
                return False
            # 例如：Only 12 left in stock - order soon.
            return bool(re.search(r"\bonly\s+\d+\s+left\s+in\s+stock\b", t))

        def _has_in_stock_message(_text):
            t = str(_text or "").strip().lower()
            return "in stock" in t

        # 抓取策略（提速版）：
        # - 先走 requests/cloudscraper（连接复用 + 低开销）
        # - 美国地区仅在必要时做一次轻量预热，再请求
        # - 最后再走 Selenium 保底
        page_html = None
        hdrs = None
        # 第1层：cloudscraper（内置 JS 挑战绕过）；不可用则退回 requests.Session
        with _SESSION_LOCK:
            session_key = (domain, threading.get_ident())
            sess = _SESSION_CACHE.get(session_key)
            if sess is None:
                if _CLOUDSCRAPER_OK:
                    sess = cloudscraper.create_scraper(
                        browser={"browser": "chrome", "platform": "windows", "mobile": False},
                        delay=0,
                    )
                else:
                    sess = requests.Session()
                _SESSION_CACHE[session_key] = sess
        # 美国区首次请求即做地址预热（POST 设邮编），确保价格按 US 区域返回
        _prepare_amazon_session(sess, domain, ctx, warmup=ctx["is_us"])

        if not page_html:
            # 主页面请求：cloudscraper/requests 带重试
            r, hdrs_req = _get_with_retry(sess, url, max_attempts=2, base_timeout=10)
            if r is not None and r.status_code in (200, 301, 302) and not _is_blocked(r.status_code, r.text):
                final_url = str(getattr(r, "url", "") or url)
                final_domain = _extract_domain_from_url(final_url)
                # 美国地区严格要求在 amazon.com（含子域）范围内
                if (not ctx["is_us"]) or final_domain.endswith("amazon.com"):
                    page_html = r.text
                    hdrs = hdrs_req
                    res["final_url"] = final_url
                    res["final_domain"] = final_domain
                    res["fetch_channel"] = "requests_retry"
            # 第2层：cloudscraper 直接单次请求（不经过重试，换新 scraper 实例）
            if (not page_html) and _CLOUDSCRAPER_OK:
                try:
                    _scraper2 = cloudscraper.create_scraper(
                        browser={"browser": "firefox", "platform": "windows", "mobile": False},
                    )
                    _prepare_amazon_session(_scraper2, domain, ctx, warmup=False)
                    _hdrs2 = random.choice(HEADERS_POOL).copy()
                    _r2 = _scraper2.get(url, headers=_hdrs2, timeout=10)
                    if not _is_blocked(_r2.status_code, _r2.text):
                        final_url2 = str(getattr(_r2, "url", "") or url)
                        final_domain2 = _extract_domain_from_url(final_url2)
                        if (not ctx["is_us"]) or final_domain2.endswith("amazon.com"):
                            page_html = _r2.text
                            hdrs = _hdrs2
                            res["final_url"] = final_url2
                            res["final_domain"] = final_domain2
                            res["fetch_channel"] = "cloudscraper_single"
                except Exception:
                    pass

            # 第3层（仅美国）：做一次轻量预热后再请求，避免无条件 Selenium
            if (not page_html) and ctx["is_us"]:
                try:
                    _prepare_amazon_session(sess, domain, ctx, warmup=True)
                    r3, hdrs3 = _get_with_retry(sess, url, max_attempts=1, base_timeout=10)
                    if r3 is not None and r3.status_code in (200, 301, 302) and not _is_blocked(r3.status_code, r3.text):
                        final_url3 = str(getattr(r3, "url", "") or url)
                        final_domain3 = _extract_domain_from_url(final_url3)
                        if final_domain3.endswith("amazon.com"):
                            page_html = r3.text
                            hdrs = hdrs3
                            res["final_url"] = final_url3
                            res["final_domain"] = final_domain3
                            res["fetch_channel"] = "requests_us_warmup"
                except Exception:
                    pass

            # 第3层：Selenium 无头浏览器（最终保底）
            if not page_html:
                page_html = _fetch_page_with_selenium(
                    url, timeout=20, region=ctx["region"], ship_zip=ctx.get("ship_zip", "30005")
                )
                hdrs = random.choice(HEADERS_POOL).copy()
                if page_html:
                    res["final_url"] = url
                    res["final_domain"] = _extract_domain_from_url(url)
                    res["fetch_channel"] = "selenium_fallback"
                    zip_code_txt = str(ctx.get("ship_zip", "") or "").strip()
                    if zip_code_txt and zip_code_txt in page_html:
                        res["zip_applied_hint"] = True

        if hdrs is None:
            hdrs = random.choice(HEADERS_POOL).copy()

        if not page_html:
            res["title"] = "被亚马逊反爬拦截，请稍后重试"
            return res
        zip_code_txt = str(ctx.get("ship_zip", "") or "").strip()
        if (not res.get("zip_applied_hint")) and zip_code_txt and (zip_code_txt in page_html):
            res["zip_applied_hint"] = True
        s = BeautifulSoup(page_html, "html.parser")

        t = s.select_one("#productTitle")
        if t:
            res["title"] = _filter_title(t.get_text(strip=True))

        def _parse_usd_from_text(_txt):
            t = str(_txt or "").strip()
            if not t:
                return None
            # 仅提取 $ 后面的数字，兼容 "$12.99" / "US$ 12.99" / "$1,299.00"
            m = re.search(r"(?:US)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)", t, flags=re.I)
            if not m:
                return None
            try:
                return float(m.group(1).replace(",", ""))
            except Exception:
                return None

        def _extract_price_usd(_soup, _html):
            # 1) 先走高优先级价格节点（避免抓到划线价/原价）
            primary_selectors = [
                "#corePrice_feature_div .a-price .a-offscreen",
                "#corePriceDisplay_desktop_feature_div .a-price .a-offscreen",
                ".apexPriceToPay .a-offscreen",
                "#priceblock_dealprice",
                "#priceblock_saleprice",
                "#priceblock_ourprice",
                "#price_inside_buybox",
                "#tp_price_block_total_price_ww .a-offscreen",
                ".reinventPricePriceToPayMargin .a-price .a-offscreen",
                ".a-price.aok-align-center.reinventPricePriceToPayMargin .a-offscreen",
            ]
            for sel in primary_selectors:
                node = _soup.select_one(sel)
                if not node:
                    continue
                v = _parse_usd_from_text(node.get_text(" ", strip=True))
                if v is not None:
                    return v

            # 2) 处理价格被拆成 whole/fraction 的结构
            whole_nodes = _soup.select(
                "#corePrice_feature_div .a-price-whole, "
                "#corePriceDisplay_desktop_feature_div .a-price-whole, "
                ".apexPriceToPay .a-price-whole, "
                "#tp_price_block_total_price_ww .a-price-whole"
            )
            for wn in whole_nodes:
                whole = re.sub(r"[^\d]", "", wn.get_text(" ", strip=True) or "")
                if not whole:
                    continue
                parent = wn.find_parent(class_=lambda c: c and "a-price" in c)
                frac_node = parent.select_one(".a-price-fraction") if parent else None
                frac = re.sub(r"[^\d]", "", frac_node.get_text(" ", strip=True) if frac_node else "")
                frac = (frac[:2] if frac else "00").ljust(2, "0")
                try:
                    return float("{}.{}".format(whole, frac))
                except Exception:
                    pass

            # 3) 页面文本兜底：优先从价格相关区域提取 $ 数字
            fallback_regions = [
                "#corePrice_feature_div",
                "#corePriceDisplay_desktop_feature_div",
                ".apexPriceToPay",
                "#buybox",
                "#centerCol",
            ]
            for reg in fallback_regions:
                box = _soup.select_one(reg)
                if not box:
                    continue
                v = _parse_usd_from_text(box.get_text(" ", strip=True))
                if v is not None:
                    return v

            # 4) 最后兜底：从脚本/整页 HTML 里提取 displayPrice / priceAmount 等字段
            text_blob = str(_html or "")
            for pat in [
                r'"displayPrice"\s*:\s*"(?:US)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"',
                r'"priceToPay"\s*:\s*"(?:US)?\$\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)"',
                r'"priceAmount"\s*:\s*([0-9][0-9,]*(?:\.[0-9]{1,2})?)',
            ]:
                mm = re.search(pat, text_blob, flags=re.I)
                if not mm:
                    continue
                try:
                    return float(mm.group(1).replace(",", ""))
                except Exception:
                    continue
            return None

        price_value = _extract_price_usd(s, page_html)
        res["price"] = "${:.2f}".format(price_value) if price_value is not None else "N/A"

        # 美国区价格重试：若首次未获取到价格，尝试强制预热后重新抓取
        if price_value is None and ctx["is_us"]:
            _retry_html = None
            try:
                if not getattr(sess, "_amz_us_warmed", False):
                    _ck = "_amz_prepared_{}_us".format(
                        str(domain or "").replace(".", "_")
                    )
                    setattr(sess, _ck, False)
                    _prepare_amazon_session(sess, domain, ctx, warmup=True)
                _rr, _ = _get_with_retry(sess, url, max_attempts=2, base_timeout=12)
                if _rr and not _is_blocked(_rr.status_code, _rr.text):
                    _retry_html = _rr.text
            except Exception:
                pass
            if not _retry_html:
                try:
                    _retry_html = _fetch_page_with_selenium(
                        url, timeout=25, region=ctx["region"],
                        ship_zip=ctx.get("ship_zip", "30005"),
                    )
                except Exception:
                    pass
            if _retry_html:
                _rs = BeautifulSoup(_retry_html, "html.parser")
                _rp = _extract_price_usd(_rs, _retry_html)
                if _rp is not None:
                    price_value = _rp
                    res["price"] = "${:.2f}".format(price_value)
                    res["fetch_channel"] = (
                        str(res.get("fetch_channel", "")) + "+price_retry"
                    )
                    page_html = _retry_html
                    s = _rs

        rt = s.select_one("span[data-hook='rating-out-of-text']")
        if rt:
            m = re.search(r"[\d.]+", rt.get_text())
            if m:
                res["rating"] = m.group()
        rv = s.select_one("#acrCustomerReviewText")
        if rv:
            res["reviews"] = rv.get_text(strip=True)
        br = s.select_one("#bylineInfo")
        if br:
            res["brand"] = br.get_text(strip=True)

        main_images = _collect_main_images_from_soup(s)
        res["main_images"] = main_images
        if main_images:
            res["image_url"] = main_images[0]

        feats = [li.get_text(strip=True)
                 for li in s.select("#feature-bullets li span.a-list-item")
                 if li.get_text(strip=True)]
        cleaned_feats = []
        seen_feat = set()
        for f in feats:
            cleaned = _replace_sensitive_words(f)
            cleaned = re.sub(r"\s{2,}", " ", cleaned).strip(" -_;,")
            if not cleaned:
                continue
            key = cleaned.lower()
            if key in seen_feat:
                continue
            seen_feat.add(key)
            cleaned_feats.append(cleaned[:220])
        res["features"] = cleaned_feats[:6]

        d = s.select_one("#productDescription p")
        if d:
            res["description"] = _replace_sensitive_words(d.get_text(strip=True))[:300]
        if not res["description"]:
            if res["features"]:
                desc = " ".join(res["features"][:2]).strip()
                if desc and desc[-1] not in ".!?":
                    desc += "."
                res["description"] = desc[:300]
            else:
                res["description"] = _build_intro_from_title(res.get("title", ""))[:300]
        if not res["features"]:
            fallback_intro = res["description"] or _build_intro_from_title(res.get("title", ""))
            if fallback_intro:
                res["features"] = [fallback_intro[:220]]

        desc_images = []
        h2_tags = s.select("h2")
        for h2 in h2_tags:
            if "Product description" in h2.get_text():
                current = h2.find_next()
                while current and len(desc_images) < 5:
                    if current.name == "h2":
                        break
                    if current.name == "img":
                        try:
                            img_src = (current.get("src")
                                       or current.get("data-old-hires")
                                       or current.get("data-a-hires"))
                            if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                                if not img_src.lower().endswith(".gif"):
                                    desc_images.append(img_src)
                        except Exception:
                            pass
                    for img_el in current.select("img"):
                        try:
                            img_src = (img_el.get("src")
                                       or img_el.get("data-old-hires")
                                       or img_el.get("data-a-hires"))
                            if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                                if not img_src.lower().endswith(".gif") and img_src not in desc_images:
                                    desc_images.append(img_src)
                        except Exception:
                            pass
                    current = current.find_next()
                break

        if not desc_images:
            prod_desc = s.select_one("#productDescription")
            if prod_desc:
                for img_el in prod_desc.select("img"):
                    try:
                        img_src = (img_el.get("src")
                                   or img_el.get("data-old-hires")
                                   or img_el.get("data-a-hires"))
                        if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                            if not img_src.lower().endswith(".gif"):
                                desc_images.append(img_src)
                    except Exception:
                        pass

        res["description_images"] = desc_images[:5]

        # 库存门槛：库存告急(Only X left in stock - order soon.)时直接停止后续抓取
        availability_text = ""
        try:
            availability_candidates = [
                s.select_one("#availabilityInsideBuyBox_feature_div #availability"),
                s.select_one("#availability #availability"),
                s.select_one("#availability"),
                s.select_one("#availabilityInsideBuyBox_feature_div"),
            ]
            for node in availability_candidates:
                if node:
                    availability_text = " ".join(node.get_text(" ", strip=True).split())
                    if availability_text:
                        break
        except Exception:
            availability_text = ""
        if not availability_text:
            try:
                availability_text = " ".join((s.get_text(" ", strip=True) or "").split())
            except Exception:
                availability_text = ""

        if _is_low_stock_message(availability_text):
            res["stock_low"] = True
            res["stock_text"] = availability_text
            res["sku_list"] = []
            return res
        if _has_in_stock_message(availability_text):
            res["stock_ok"] = True

        sku_list = []
        sku_seen = set()
        dimension_map = _extract_json_object_by_key(page_html, "dimensionToAsinMap")
        color_image_map = _extract_color_images_map(page_html)
        dimension_names, value_display_map = _build_variation_value_maps(page_html)
        fallback_images = main_images[:5] if main_images else ([res["image_url"]] if res.get("image_url") else [])
        def _get_sku_image_limit(sku_count):
            # 需求：SKU >= 5 时，每个 SKU 最多抓取 3 张；否则最多 5 张
            return 3 if int(sku_count or 0) >= 5 else 5
        def _basis_has_style(_basis):
            return any("style" in str(_b).lower() for _b in (_basis or []))

        # 检测是否同时存在 color 和 size 两个维度
        # 若同时存在，则只爬取 color 维度下的 SKU，忽略 size
        _all_dim_names_lower = [str(d).lower() for d in dimension_names]
        _has_color = any("color" in d or "colour" in d for d in _all_dim_names_lower)
        _has_size  = any("size" in d for d in _all_dim_names_lower)
        _color_only_mode = _has_color and _has_size
        _main_spec_has_color = _has_color

        # 提取「其他规格」：color_only_mode 下，收集非 color 维度的所有选项值
        # 格式：{"size": ["65L", "96L"], ...}
        other_specs = {}
        if _color_only_mode:
            other_specs = _extract_non_color_specs(s)
        res["other_specs"] = other_specs

        # 高风控压力下直接降级，减少后续请求爆发
        if not _should_fetch_sku_details():
            default_images = _normalize_image_list(fallback_images[:5])
            res["sku_fetch_degraded"] = True
            if len(default_images) >= 2:
                res["sku_list"] = [{
                    "sku_asin": asin,
                    "sku_attributes": "默认规格",
                    "dimension_basis": [],
                    "images": default_images
                }]
            else:
                res["sku_list"] = []
                res["no_suitable_sku"] = True
            return res

        # SKU 过多时跳过 SKU 明细抓取，仅保留主信息
        max_sku_fetch = 10
        def _mark_sku_too_many(count):
            res["sku_too_many"] = True
            res["sku_count"] = int(count or 0)
            res["sku_list"] = []

        # 优先从 HTML 直接解析 color 维度的 ASIN（#inline-twister-row-color_name）
        _color_asins_from_html = _extract_color_only_asins(s) if _color_only_mode else []

        if _color_only_mode and _color_asins_from_html:
            unique_color_asins = {str(a).strip() for a, _ in _color_asins_from_html if str(a or "").strip()}
            if len(unique_color_asins) > max_sku_fetch:
                _mark_sku_too_many(len(unique_color_asins))
                return res
            image_limit = _get_sku_image_limit(len(unique_color_asins))
            # 路径 A：HTML 解析到 color ASIN 列表，直接使用
            sku_asin_list = [a for a, _ in _color_asins_from_html if a and a != asin]
            sku_image_cache = _fetch_all_sku_images_concurrently(
                sess, domain, sku_asin_list, hdrs, max_workers=2, max_count=image_limit
            )
            sku_image_cache[asin] = fallback_images[:image_limit]

            used_colors = set()
            color_to_idx = {}
            for ca, color_name in _color_asins_from_html:
                if not ca or ca in sku_seen:
                    continue
                sku_images = sku_image_cache.get(ca, [])
                if not sku_images:
                    sku_images = _pick_images_from_color_map(
                        color_image_map, color_name, ca, max_count=image_limit
                    )
                if not sku_images:
                    sku_images = fallback_images[:image_limit]

                # 颜色唯一性策略：
                # 1) 优先 "&" 前颜色；2) 冲突时尝试后颜色；3) 都冲突则随机删重
                candidates = _split_color_candidates(color_name)
                chosen_color = ""
                for c in candidates:
                    if c and c not in used_colors:
                        chosen_color = c
                        break
                if not chosen_color:
                    # 所有候选都冲突：随机决定是否替换已有冲突 SKU（实现随机删重）
                    if candidates:
                        conflict_color = candidates[0]
                        old_idx = color_to_idx.get(conflict_color, -1)
                        if old_idx >= 0 and random.choice([True, False]):
                            # 用当前 SKU 替换已存在同色 SKU
                            old_sku_asin = sku_list[old_idx].get("sku_asin")
                            if old_sku_asin in sku_seen:
                                sku_seen.discard(old_sku_asin)
                            sku_list[old_idx] = {
                                "sku_asin": ca,
                                "sku_attributes": "Color: {}".format(conflict_color),
                                "dimension_basis": ["color"],
                                "images": sku_images[:image_limit]
                            }
                            sku_seen.add(ca)
                        # 不替换则随机删除当前重复项（直接跳过）
                    continue

                sku_seen.add(ca)
                used_colors.add(chosen_color)
                color_to_idx[chosen_color] = len(sku_list)
                sku_list.append({
                    "sku_asin": ca,
                    "sku_attributes": "Color: {}".format(chosen_color),
                    "dimension_basis": ["color"],
                    "images": sku_images[:image_limit]
                })
        else:
            # 路径 B：从 dimensionToAsinMap 构建 SKU 列表
            # color_only_mode 时只保留含 color 维度的条目
            candidate_entries = []
            if isinstance(dimension_map, dict):
                for dim_key, sku_asin in dimension_map.items():
                    if not sku_asin:
                        continue
                    sku_asin = str(sku_asin).strip()
                    if not sku_asin or sku_asin in sku_seen:
                        continue
                    basis = _extract_dimension_basis(dim_key, dimension_names=dimension_names)
                    if _color_only_mode:
                        if not any("color" in b or "colour" in b for b in basis):
                            continue
                    sku_seen.add(sku_asin)
                    candidate_entries.append((dim_key, sku_asin, basis))
            if len(candidate_entries) > max_sku_fetch:
                _mark_sku_too_many(len(candidate_entries))
                return res

            # style 依据时，仅保留前 3 个 SKU 并在后续将规格重写为 A/B/C
            style_mode = any(_basis_has_style(_basis) for _, _, _basis in candidate_entries)
            if style_mode:
                style_entries = [e for e in candidate_entries if _basis_has_style(e[2])]
                if style_entries:
                    candidate_entries = style_entries[:3]
                else:
                    candidate_entries = candidate_entries[:3]

            image_limit = _get_sku_image_limit(len(candidate_entries))
            sku_asin_list = [sku_asin for _, sku_asin, _ in candidate_entries if sku_asin != asin]

            sku_image_cache = _fetch_all_sku_images_concurrently(
                sess, domain, sku_asin_list, hdrs, max_workers=2, max_count=image_limit
            )
            sku_image_cache[asin] = fallback_images[:image_limit]

            for idx, (dim_key, sku_asin, basis) in enumerate(candidate_entries):
                sku_images = sku_image_cache.get(sku_asin, [])
                if not sku_images:
                    sku_images = _pick_images_from_color_map(
                        color_image_map, dim_key, sku_asin, max_count=image_limit
                    )
                if not sku_images:
                    sku_images = fallback_images[:image_limit]

                if style_mode:
                    sku_attr_text = ["A", "B", "C"][idx] if idx < 3 else "默认规格"
                else:
                    sku_attr_text = _normalize_sku_attrs(
                        dim_key, dimension_names=dimension_names,
                        value_display_map=value_display_map
                    ) or "默认规格"

                sku_list.append({
                    "sku_asin": sku_asin,
                    "sku_attributes": sku_attr_text,
                    "dimension_basis": basis,
                    "images": sku_images[:image_limit]
                })

            # 路径 C（兜底）：dimensionToAsinMap 缺失/失效时，从 HTML Twister 直接提取
            if not sku_list:
                tw_map, tw_dims = _extract_twister_dimension_skus(s)
                if isinstance(tw_map, dict) and tw_map:
                    tw_asins = [a for a in tw_map.keys() if str(a).strip()]
                    if len(tw_asins) > max_sku_fetch:
                        _mark_sku_too_many(len(tw_asins))
                        return res
                    image_limit = _get_sku_image_limit(len(tw_asins))
                    sku_asin_list = [a for a in tw_asins if a != asin]
                    sku_image_cache = _fetch_all_sku_images_concurrently(
                        sess, domain, sku_asin_list, hdrs, max_workers=2, max_count=image_limit
                    )
                    sku_image_cache[asin] = fallback_images[:image_limit]

                    for sku_asin in tw_asins:
                        dim_vals = tw_map.get(sku_asin) or {}
                        basis = [d for d in tw_dims if d in dim_vals]
                        parts = []
                        for d in tw_dims:
                            v = str(dim_vals.get(d) or "").strip()
                            if v:
                                parts.append("{}: {}".format(d.capitalize(), v))
                        sku_attr_text = " / ".join(parts) if parts else "默认规格"

                        sku_images = sku_image_cache.get(sku_asin, [])
                        if not sku_images:
                            # 尝试按已提取维度值从 colorImages 映射图片
                            sku_images = _pick_images_from_color_map(
                                color_image_map,
                                dim_vals.get("color", ""),
                                dim_vals.get("colour", ""),
                                sku_asin,
                                max_count=image_limit
                            )
                        if not sku_images:
                            sku_images = fallback_images[:image_limit]

                        sku_list.append({
                            "sku_asin": sku_asin,
                            "sku_attributes": sku_attr_text,
                            "dimension_basis": basis,
                            "images": sku_images[:image_limit]
                        })
                    res["sku_parse_fallback"] = "html_twister"

        # 对所有 color SKU 执行统一颜色唯一化（覆盖所有构建路径）
        sku_list = _enforce_unique_color_skus(sku_list)

        # 业务规则：每个 SKU 必须至少 2 张图；不足 2 张的 SKU 直接删除。
        sku_list, dropped_by_images = _filter_skus_by_min_images(sku_list, min_images=2)
        if dropped_by_images:
            res["sku_removed_for_few_images"] = dropped_by_images

        # 注意：颜色替换仅在上传 SHEIN 主规格时处理，不在抓取阶段改写 sku_attributes，
        # 以保证 GUI 展示保持原始抓取颜色。
        if _main_spec_has_color:
            pass

        if not sku_list and not bool(res.get("nonstandard_color_only")):
            default_images = _normalize_image_list(fallback_images[:5])
            if len(default_images) >= 2:
                sku_list.append({
                    "sku_asin": asin,
                    "sku_attributes": "默认规格",
                    "dimension_basis": [],
                    "images": default_images
                })
            else:
                res["no_suitable_sku"] = True

        res["sku_list"] = sku_list
    except Exception as e:
        res["title"] = "错误: {}".format(e)
    return res


def download_image(url):
    """下载图片并返回 PIL Image 对象。"""
    if not url:
        return None
    try:
        r = requests.get(url, headers=random.choice(HEADERS_POOL).copy(), timeout=10)
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content))
    except Exception:
        pass
    return None
