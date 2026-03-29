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
import requests
try:
    import cloudscraper
    _CLOUDSCRAPER_OK = True
except ImportError:
    _CLOUDSCRAPER_OK = False
from bs4 import BeautifulSoup
from PIL import Image
from concurrent.futures import ThreadPoolExecutor, as_completed
from shein_sensitive_clean import SENSITIVE_WORDS, _filter_sensitive, _filter_title

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


def _is_blocked(status_code, text):
    """判断响应是否被反爬拦截。
    仅在页面确实是拦截页（无商品内容）时返回 True。
    """
    if status_code == 503:
        return True
    if status_code == 404 and "automated" in text.lower():
        return True
    tl = text.lower()
    # 如果页面有正常商品内容，直接认为未被拦截
    if "productTitle" in text or "acrCustomerReviewText" in text:
        return False
    # 没有商品内容时，检查拦截特征
    if "captcha" in tl:
        return True
    if "robot check" in tl:
        return True
    if "api-services-support@amazon.com" in tl:
        return True
    if "sorry, we just need to make sure" in tl:
        return True
    if "automated access" in tl:
        return True
    return False

def _get_with_retry(session, url, max_attempts=3, base_timeout=12):
    """
    带指数退避 + 抖动的请求重试，每次随机换 UA 和代理。
    返回 (response, headers_used) 或 (None, None)。
    """
    shuffled = random.sample(HEADERS_POOL, len(HEADERS_POOL))
    attempts = min(max_attempts, len(shuffled))
    for attempt in range(attempts):
        hdrs = shuffled[attempt].copy()
        hdrs["Referer"] = "https://{}/".format(url.split("/")[2])
        proxies = _get_proxy()
        if attempt > 0:
            # 短暂退避：避免超长等待
            wait = min(2 ** attempt + random.uniform(0.3, 1.0), 8.0)
            time.sleep(wait)
        try:
            r = session.get(url, headers=hdrs, proxies=proxies, timeout=base_timeout)
            if not _is_blocked(r.status_code, r.text):
                return r, hdrs
        except (requests.exceptions.Timeout, requests.exceptions.ConnectionError):
            continue
        except Exception:
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


def _extract_color_initial_images(page_text, max_count=8):
    """
    从亚马逊页面的单引号JS格式中提取 colorImages.initial 数组，
    即当前颜色的所有角度图片（MAIN/PT01/PT02...）。
    返回 [url, ...] 列表。
    """
    idx = page_text.find("colorImages'")
    if idx < 0:
        return []
    init_idx = page_text.find("'initial'", idx)
    if init_idx < 0 or init_idx - idx > 500:
        return []
    arr_start = page_text.find('[', init_idx)
    if arr_start < 0:
        return []
    depth = 0
    in_str = False
    esc = False
    str_char = None
    end = -1
    for i in range(arr_start, min(arr_start + 200000, len(page_text))):
        ch = page_text[i]
        if esc:
            esc = False
            continue
        if ch == '\\':
            esc = True
            continue
        if not in_str and ch in ('"', "'"):
            in_str = True
            str_char = ch
            continue
        if in_str and ch == str_char:
            in_str = False
            continue
        if in_str:
            continue
        if ch == '[':
            depth += 1
        elif ch == ']':
            depth -= 1
            if depth == 0:
                end = i
                break
    if end < 0:
        return []
    try:
        items = json.loads(page_text[arr_start:end + 1])
    except Exception:
        return []
    urls = []
    for it in items:
        if not isinstance(it, dict):
            continue
        u = it.get("hiRes") or it.get("large") or it.get("mainUrl")
        if isinstance(u, str) and u and u not in urls:
            urls.append(_to_sx1500(u))
            if len(urls) >= max_count:
                break
    return urls


def _extract_color_images_map(page_text):
    """
    从页面中提取按颜色分组的图片映射。
    解析双引号JSON格式的 colorImages 块（key 格式为 'Color Size'，如 'Black 65L'），
    将颜色部分（去掉尺码后缀）作为 key 存入结果。
    返回 {color_name: [url, ...]} 字典，每色至少1张 hiRes 主图。
    """
    result = {}
    for m in re.finditer(r'colorImages"\s*:\s*\{', page_text):
        brace_start = page_text.find('{', m.start())
        depth = 0
        in_str = False
        esc = False
        str_char = None
        end = -1
        for i in range(brace_start, min(brace_start + 500000, len(page_text))):
            ch = page_text[i]
            if esc:
                esc = False
                continue
            if ch == '\\':
                esc = True
                continue
            if not in_str and ch in ('"', "'"):
                in_str = True
                str_char = ch
                continue
            if in_str and ch == str_char:
                in_str = False
                continue
            if in_str:
                continue
            if ch == '{':
                depth += 1
            elif ch == '}':
                depth -= 1
                if depth == 0:
                    end = i
                    break
        if end < 0:
            continue
        try:
            color_map = json.loads(page_text[brace_start:end + 1])
        except Exception:
            continue
        for full_key, items in color_map.items():
            # full_key 形如 "Black 65L" 或 "Jute&Black 96L"
            # 提取颜色部分：去掉末尾的尺码（数字+字母，如 65L/96L 或 S/M/XL）
            color_key = re.sub(
                r'\s+\d+[A-Za-z]+$|\s+(XS|S|M|L|XL|XXL|3XL)$',
                '',
                full_key.strip()
            ).strip()
            if not color_key:
                color_key = full_key.strip()
            if not isinstance(items, list):
                continue
            for it in items:
                if not isinstance(it, dict):
                    continue
                u = it.get("hiRes") or it.get("large") or it.get("mainUrl")
                if isinstance(u, str) and u:
                    uu = _to_sx1500(u)
                    # 以颜色名存储（去重）
                    if color_key not in result:
                        result[color_key] = []
                    if uu not in result[color_key]:
                        result[color_key].append(uu)
                    # 同时以完整 key 存储，便于精确匹配
                    fk = full_key.strip()
                    if fk not in result:
                        result[fk] = []
                    if uu not in result[fk]:
                        result[fk].append(uu)
        break  # 只需解析第一个双引号JSON格式的 colorImages
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


def _fetch_page_with_selenium(url, timeout=20):
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
            driver.get(url)
            time.sleep(3)  # 等待 JS 渲染
            html = driver.page_source
            return html
        finally:
            try:
                driver.quit()
            except Exception:
                pass
    except Exception:
        return None


def _fetch_sku_images(session, domain, sku_asin, headers):
    """拉取单个 SKU 页面的主图，优先从 colorImages.initial 提取全部角度图，失败时返回空列表。"""
    try:
        sku_url = "https://{}/dp/{}?language=en_US&currency=USD".format(domain, sku_asin)
        # 优先用传入的 session（可能是 cloudscraper），直接单次请求
        try:
            _hdrs = random.choice(HEADERS_POOL).copy()
            _hdrs["Referer"] = "https://{}/".format(domain)
            r = session.get(sku_url, headers=_hdrs, timeout=10)
            if r and not _is_blocked(r.status_code, r.text):
                # 优先：从 colorImages.initial 提取当前颜色的完整多图
                imgs = _extract_color_initial_images(r.text, max_count=8)
                if imgs:
                    return imgs
                # 兜底：从 #altImages 等DOM结构提取
                sku_soup = BeautifulSoup(r.text, "html.parser")
                imgs = _collect_main_images_from_soup(sku_soup, max_count=8)
                if imgs:
                    return imgs
        except Exception:
            pass
        # 回退：用 _get_with_retry
        r2, _ = _get_with_retry(session, sku_url, max_attempts=1, base_timeout=8)
        if r2 is None:
            return []
        imgs2 = _extract_color_initial_images(r2.text, max_count=8)
        if imgs2:
            return imgs2
        sku_soup = BeautifulSoup(r2.text, "html.parser")
        return _collect_main_images_from_soup(sku_soup, max_count=8)
    except Exception:
        return []

def _fetch_all_sku_images_concurrently(session, domain, sku_asins, hdrs, max_workers=6):
    """并发拉取多个 SKU 的图片，返回 {sku_asin: [img_url, ...]} 字典。"""
    results = {}
    if not sku_asins:
        return results
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_asin = {
            executor.submit(_fetch_sku_images, session, domain, asin, hdrs): asin
            for asin in sku_asins
        }
        for future in as_completed(future_to_asin):
            asin = future_to_asin[future]
            try:
                results[asin] = future.result()
            except Exception:
                results[asin] = []
    return results


def fetch_amazon_product(asin, region="美国"):
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
    domain = _REGION_DOMAINS.get(region, "www.amazon.com")
    url = "https://{}/dp/{}?language=en_US&currency=USD".format(domain, asin)
    res = {"asin": asin, "title": "获取失败", "price": "N/A", "rating": "N/A",
           "reviews": "N/A", "brand": "N/A", "image_url": "",
           "description": "", "features": [], "url": url,
           "description_images": [], "main_images": [], "sku_list": [], "other_specs": {}}
    try:
        # 三层抓取策略：cloudscraper > requests > Selenium
        # 第1层：cloudscraper（内置 JS 挑战绕过）
        if _CLOUDSCRAPER_OK:
            sess = cloudscraper.create_scraper(
                browser={"browser": "chrome", "platform": "windows", "mobile": False},
                delay=3,
            )
        else:
            sess = requests.Session()
        # 注入模拟浏览器 Cookie
        for k, v in _make_browser_cookies(domain).items():
            sess.cookies.set(k, v, domain=domain)

        # 主页面请求：cloudscraper/requests 带重试
        r, hdrs = _get_with_retry(sess, url, max_attempts=3, base_timeout=15)
        page_html = None
        if r is not None and r.status_code in (200, 301, 302) and not _is_blocked(r.status_code, r.text):
            page_html = r.text
        else:
            # 第2层：cloudscraper 直接单次请求（不经过重试，换新 scraper 实例）
            if _CLOUDSCRAPER_OK:
                try:
                    _scraper2 = cloudscraper.create_scraper(
                        browser={"browser": "firefox", "platform": "windows", "mobile": False},
                    )
                    for k, v in _make_browser_cookies(domain).items():
                        _scraper2.cookies.set(k, v, domain=domain)
                    _hdrs2 = random.choice(HEADERS_POOL).copy()
                    _r2 = _scraper2.get(url, headers=_hdrs2, timeout=15)
                    if not _is_blocked(_r2.status_code, _r2.text):
                        page_html = _r2.text
                        hdrs = _hdrs2
                except Exception:
                    pass

            # 第3层：Selenium 无头浏览器（最终保底）
            if not page_html:
                page_html = _fetch_page_with_selenium(url, timeout=25)
                hdrs = random.choice(HEADERS_POOL).copy()
                r = None

        if not page_html:
            res["title"] = "被亚马逊反爬拦截，请稍后重试"
            return res
        s = BeautifulSoup(page_html, "html.parser")

        t = s.select_one("#productTitle")
        if t:
            res["title"] = _filter_title(t.get_text(strip=True))

        price_raw = "N/A"
        for sel in ["#priceblock_ourprice", ".a-price .a-offscreen",
                    "#priceblock_dealprice", ".apexPriceToPay .a-offscreen"]:
            p = s.select_one(sel)
            if p:
                price_raw = p.get_text(strip=True)
                break
        if price_raw != "N/A":
            price_match = re.search(r'[\d,]+\.?\d*', price_raw.replace(',', ''))
            res["price"] = "${:.2f}".format(float(price_match.group())) if price_match else "N/A"
        else:
            res["price"] = "N/A"

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

        main_images = _extract_color_initial_images(page_html, max_count=8)
        if not main_images:
            main_images = _collect_main_images_from_soup(s)
        res["main_images"] = main_images
        if main_images:
            res["image_url"] = main_images[0]

        feats = [li.get_text(strip=True)
                 for li in s.select("#feature-bullets li span.a-list-item")
                 if li.get_text(strip=True)]
        feats = [f for f in feats if not any(w.lower() in f.lower() for w in SENSITIVE_WORDS)]
        res["features"] = feats[:6]

        d = s.select_one("#productDescription p")
        if d:
            res["description"] = _filter_sensitive(d.get_text(strip=True))[:300]

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

        sku_list = []
        sku_seen = set()
        dimension_map = _extract_json_object_by_key(page_html, "dimensionToAsinMap")
        color_image_map = _extract_color_images_map(page_html)
        dimension_names, value_display_map = _build_variation_value_maps(page_html)
        fallback_images = main_images[:5] if main_images else ([res["image_url"]] if res.get("image_url") else [])

        # 检测是否同时存在 color 和 size 两个维度
        # 若同时存在，则只爬取 color 维度下的 SKU，忽略 size
        _all_dim_names_lower = [str(d).lower() for d in dimension_names]
        _has_color = any("color" in d or "colour" in d for d in _all_dim_names_lower)
        _has_size  = any("size" in d for d in _all_dim_names_lower)
        _color_only_mode = _has_color and _has_size

        # 提取「其他规格」：color_only_mode 下，收集非 color 维度的所有选项值
        # 格式：{"size": ["65L", "96L"], ...}
        other_specs = {}
        if _color_only_mode:
            other_specs = _extract_non_color_specs(s)
        res["other_specs"] = other_specs

        # 优先从 HTML 直接解析 color 维度的 ASIN（#inline-twister-row-color_name）
        _color_asins_from_html = _extract_color_only_asins(s) if _color_only_mode else []

        if _color_only_mode and _color_asins_from_html:
            # 路径 A：HTML 解析到 color ASIN 列表，直接使用
            sku_asin_list = [a for a, _ in _color_asins_from_html if a and a != asin]
            sku_image_cache = _fetch_all_sku_images_concurrently(
                sess, domain, sku_asin_list, hdrs, max_workers=4
            )
            _cur_initial = _extract_color_initial_images(page_html, max_count=8)
            sku_image_cache[asin] = _cur_initial if _cur_initial else fallback_images[:]

            for ca, color_name in _color_asins_from_html:
                if not ca or ca in sku_seen:
                    continue
                sku_seen.add(ca)
                sku_images = sku_image_cache.get(ca, [])
                if not sku_images:
                    sku_images = _pick_images_from_color_map(
                        color_image_map, color_name, ca, max_count=5
                    )
                if not sku_images:
                    sku_images = fallback_images[:]
                attr_text = "Color: {}".format(color_name) if color_name else "默认规格"
                sku_list.append({
                    "sku_asin": ca,
                    "sku_attributes": attr_text,
                    "dimension_basis": ["color"],
                    "images": sku_images[:8]
                })
        else:
            # 路径 B：从 dimensionToAsinMap 构建 SKU 列表
            # color_only_mode 时只保留含 color 维度的条目
            sku_asin_list = []
            if isinstance(dimension_map, dict):
                for dim_key, sku_asin in dimension_map.items():
                    if not sku_asin:
                        continue
                    sku_asin = str(sku_asin).strip()
                    if not sku_asin or sku_asin in sku_seen:
                        continue
                    if _color_only_mode:
                        basis = _extract_dimension_basis(dim_key, dimension_names=dimension_names)
                        if not any("color" in b or "colour" in b for b in basis):
                            continue
                    sku_seen.add(sku_asin)
                    if sku_asin != asin:
                        sku_asin_list.append(sku_asin)

            sku_image_cache = _fetch_all_sku_images_concurrently(
                sess, domain, sku_asin_list, hdrs, max_workers=4
            )
            _cur_initial = _extract_color_initial_images(page_html, max_count=8)
            sku_image_cache[asin] = _cur_initial if _cur_initial else fallback_images[:]

            sku_seen2 = set()
            if isinstance(dimension_map, dict):
                for dim_key, sku_asin in dimension_map.items():
                    if not sku_asin:
                        continue
                    sku_asin = str(sku_asin).strip()
                    if not sku_asin or sku_asin in sku_seen2:
                        continue
                    basis = _extract_dimension_basis(dim_key, dimension_names=dimension_names)
                    if _color_only_mode:
                        if not any("color" in b or "colour" in b for b in basis):
                            continue
                    sku_seen2.add(sku_asin)

                    sku_images = sku_image_cache.get(sku_asin, [])
                    if not sku_images:
                        sku_images = _pick_images_from_color_map(
                            color_image_map, dim_key, sku_asin, max_count=5
                        )
                    if not sku_images:
                        sku_images = fallback_images[:]

                    sku_attr_text = _normalize_sku_attrs(
                        dim_key, dimension_names=dimension_names,
                        value_display_map=value_display_map
                    ) or "默认规格"

                    sku_list.append({
                        "sku_asin": sku_asin,
                        "sku_attributes": sku_attr_text,
                        "dimension_basis": basis,
                        "images": sku_images[:8]
                    })

        if not sku_list:
            sku_list.append({
                "sku_asin": asin,
                "sku_attributes": "默认规格",
                "dimension_basis": [],
                "images": fallback_images[:5]
            })

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
