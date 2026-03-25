# -*- coding: utf-8 -*-
"""
SHEIN ASIN 模块
通过 ASIN 从亚马逊爬取商品信息
"""
import re
import random
import io
import json
import requests
from bs4 import BeautifulSoup
from PIL import Image
from shein_sensitive_clean import SENSITIVE_WORDS, _filter_sensitive, _filter_title

AMAZON_PRODUCT_URL = "https://www.amazon.com/dp/{asin}"

HEADERS_POOL = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
     "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"},
]


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


def _normalize_sku_attrs(raw_dimension_key):
    if not raw_dimension_key:
        return ""
    txt = str(raw_dimension_key).replace("_name", "")
    txt = txt.replace(";", ",").replace("|", ",")
    txt = txt.replace(":", "=")
    parts = [p.strip() for p in txt.split(",") if p.strip()]
    return " / ".join(parts)


def _extract_dimension_basis(raw_dimension_key):
    if not raw_dimension_key:
        return []
    txt = str(raw_dimension_key).replace(";", ",").replace("|", ",")
    parts = [p.strip() for p in txt.split(",") if p.strip()]
    basis = []
    for p in parts:
        if "=" in p:
            k = p.split("=", 1)[0].strip().replace("_name", "")
        elif ":" in p:
            k = p.split(":", 1)[0].strip().replace("_name", "")
        else:
            k = p.strip().replace("_name", "")
        if k and k.lower() not in [x.lower() for x in basis]:
            basis.append(k)
    return basis


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


def _fetch_sku_images(session, domain, sku_asin, headers):
    try:
        sku_url = "https://{}/dp/{}?language=en_US&currency=USD".format(domain, sku_asin)
        r = session.get(sku_url, headers=headers, timeout=15)
        if r.status_code != 200:
            return []
        sku_soup = BeautifulSoup(r.text, "html.parser")
        return _collect_main_images_from_soup(sku_soup, max_count=5)
    except Exception:
        return []


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
    hdrs = random.choice(HEADERS_POOL).copy()
    hdrs["Referer"] = "https://{}/".format(domain)
    hdrs["Accept-Language"] = "en-US,en;q=0.9"
    res = {"asin": asin, "title": "获取失败", "price": "N/A", "rating": "N/A",
           "reviews": "N/A", "brand": "N/A", "image_url": "",
           "description": "", "features": [], "url": url,
           "description_images": [], "main_images": [], "sku_list": []}
    try:
        sess = requests.Session()
        sess.cookies.set("i18n-prefs", "USD", domain=domain)
        sess.cookies.set("lc-main", "en_US", domain=domain)
        sess.cookies.set("x-main", "1", domain=domain)
        r = sess.get(url, headers=hdrs, timeout=15)
        if r.status_code != 200:
            res["title"] = "HTTP {}".format(r.status_code)
            return res
        s = BeautifulSoup(r.text, "html.parser")

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
        sku_image_cache = {}
        dimension_map = _extract_json_object_by_key(r.text, "dimensionToAsinMap")
        color_image_map = _extract_color_images_map(r.text)
        fallback_images = main_images[:5] if main_images else ([res["image_url"]] if res.get("image_url") else [])

        if isinstance(dimension_map, dict):
            for dim_key, sku_asin in dimension_map.items():
                if not sku_asin:
                    continue
                sku_asin = str(sku_asin).strip()
                if not sku_asin or sku_asin in sku_seen:
                    continue
                sku_seen.add(sku_asin)

                if sku_asin == asin:
                    sku_images = main_images[:5]
                else:
                    if sku_asin not in sku_image_cache:
                        sku_image_cache[sku_asin] = _fetch_sku_images(sess, domain, sku_asin, hdrs)
                    sku_images = sku_image_cache.get(sku_asin, [])

                if not sku_images:
                    sku_images = _pick_images_from_color_map(color_image_map, dim_key, sku_asin, max_count=5)

                if not sku_images:
                    sku_images = main_images[:5]

                basis = _extract_dimension_basis(dim_key)

                sku_list.append({
                    "sku_asin": sku_asin,
                    "sku_attributes": _normalize_sku_attrs(dim_key) or "默认规格",
                    "dimension_basis": basis,
                    "images": sku_images[:5]
                })

        if not sku_list:
            sku_list.append({
                "sku_asin": asin,
                "sku_attributes": "默认规格",
                "dimension_basis": [],
                "images": main_images[:5]
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
