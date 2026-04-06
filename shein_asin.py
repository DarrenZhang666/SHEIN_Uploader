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
import difflib
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


def _canonicalize_shein_color(color_token):
    """将颜色候选词映射为 SHEIN 标准颜色词；非标准返回空字符串。"""
    key = _normalize_color_token(color_token)
    if not key:
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
        score = difflib.SequenceMatcher(None, key, token).ratio()
        if score > best_score:
            best_score = score
            best_token = token
    if best_token and best_score >= 0.74:
        return best_token
    return ""


def _filter_nonstandard_color_skus(sku_list):
    """
    仅保留颜色在 SHEIN 标准色白名单中的 SKU。
    返回：(filtered_sku_list, removed_count, replaced_count)
    """
    if not sku_list:
        return sku_list, 0, 0
    kept = []
    removed = 0
    replaced = 0
    used_standard_colors = set()
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
        if canon:
            # 标准化后再次保证“一个颜色仅一个 SKU”
            if canon in used_standard_colors:
                removed += 1
                continue
            sku2 = dict(sku)
            old_raw = _normalize_color_token(raw_color)
            sku2["sku_attributes"] = "Color: {}".format(canon)
            if old_raw and old_raw != canon:
                replaced += 1
            kept.append(sku2)
            used_standard_colors.add(canon)
        else:
            removed += 1
    return kept, removed, replaced


def _extract_color_from_attrs(attr_text):
    """从 sku_attributes 中抽取颜色值文本。"""
    t = str(attr_text or "").strip()
    if not t:
        return ""
    m = re.search(r"color\s*:\s*([^/]+)", t, flags=re.IGNORECASE)
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
    """拉取单个 SKU 页面的主图，失败时返回空列表。"""
    try:
        sku_url = "https://{}/dp/{}?language=en_US&currency=USD".format(domain, sku_asin)
        # 优先用传入的 session（可能是 cloudscraper），直接单次请求
        try:
            _hdrs = random.choice(HEADERS_POOL).copy()
            _hdrs["Referer"] = "https://{}/".format(domain)
            r = session.get(sku_url, headers=_hdrs, timeout=10)
            if r and not _is_blocked(r.status_code, r.text):
                sku_soup = BeautifulSoup(r.text, "html.parser")
                imgs = _collect_main_images_from_soup(sku_soup, max_count=5)
                if imgs:
                    return imgs
        except Exception:
            pass
        # 回退：用 _get_with_retry
        r2, _ = _get_with_retry(session, sku_url, max_attempts=1, base_timeout=8)
        if r2 is None:
            return []
        sku_soup = BeautifulSoup(r2.text, "html.parser")
        return _collect_main_images_from_soup(sku_soup, max_count=5)
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
        def _is_low_stock_message(_text):
            t = str(_text or "").strip().lower()
            if not t:
                return False
            # 例如：Only 12 left in stock - order soon.
            return bool(re.search(r"\bonly\s+\d+\s+left\s+in\s+stock\b", t))

        def _has_in_stock_message(_text):
            t = str(_text or "").strip().lower()
            return "in stock" in t

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
            # 路径 A：HTML 解析到 color ASIN 列表，直接使用
            sku_asin_list = [a for a, _ in _color_asins_from_html if a and a != asin]
            sku_image_cache = _fetch_all_sku_images_concurrently(
                sess, domain, sku_asin_list, hdrs, max_workers=4
            )
            sku_image_cache[asin] = fallback_images[:]

            used_colors = set()
            color_to_idx = {}
            for ca, color_name in _color_asins_from_html:
                if not ca or ca in sku_seen:
                    continue
                sku_images = sku_image_cache.get(ca, [])
                if not sku_images:
                    sku_images = _pick_images_from_color_map(
                        color_image_map, color_name, ca, max_count=5
                    )
                if not sku_images:
                    sku_images = fallback_images[:]

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
                                "images": sku_images[:5]
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
                    "images": sku_images[:5]
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

            sku_asin_list = [sku_asin for _, sku_asin, _ in candidate_entries if sku_asin != asin]

            sku_image_cache = _fetch_all_sku_images_concurrently(
                sess, domain, sku_asin_list, hdrs, max_workers=4
            )
            sku_image_cache[asin] = fallback_images[:]

            for idx, (dim_key, sku_asin, basis) in enumerate(candidate_entries):
                sku_images = sku_image_cache.get(sku_asin, [])
                if not sku_images:
                    sku_images = _pick_images_from_color_map(
                        color_image_map, dim_key, sku_asin, max_count=5
                    )
                if not sku_images:
                    sku_images = fallback_images[:]

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
                    "images": sku_images[:5]
                })

        # 对所有 color SKU 执行统一颜色唯一化（覆盖所有构建路径）
        sku_list = _enforce_unique_color_skus(sku_list)

        # 主规格含 color 时：过滤掉非 SHEIN 标准颜色 SKU
        if _main_spec_has_color:
            sku_list, _removed_nonstandard, _replaced_to_standard = _filter_nonstandard_color_skus(sku_list)
            if _replaced_to_standard > 0:
                res["standard_color_replaced"] = int(_replaced_to_standard)
            if _removed_nonstandard > 0:
                res["nonstandard_color_filtered"] = int(_removed_nonstandard)
                # 若页面 color SKU 全被过滤，避免回退默认规格导致误上品
                if not sku_list:
                    res["nonstandard_color_only"] = True
                    res["no_suitable_sku"] = True

        if not sku_list and not bool(res.get("nonstandard_color_only")):
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
