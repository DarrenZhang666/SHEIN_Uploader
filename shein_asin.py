# -*- coding: utf-8 -*-
"""
SHEIN ASIN 模块
通过 ASIN 从亚马逊爬取商品信息
"""
import re
import random
import io
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


def fetch_amazon_product(asin, region="\u7f8e\u56fd"):
    _REGION_DOMAINS = {
        "\u7f8e\u56fd": "www.amazon.com",
        "\u82f1\u56fd": "www.amazon.co.uk",
        "\u5fb7\u56fd": "www.amazon.de",
        "\u6cd5\u56fd": "www.amazon.fr",
        "\u65e5\u672c": "www.amazon.co.jp",
        "\u52a0\u62ff\u5927": "www.amazon.ca",
        "\u6fb3\u5927\u5229\u4e9a": "www.amazon.com.au",
        "\u610f\u5927\u5229": "www.amazon.it",
        "\u897f\u73ed\u7259": "www.amazon.es",
        "\u58a8\u897f\u54e5": "www.amazon.com.mx",
    }
    domain = _REGION_DOMAINS.get(region, "www.amazon.com")
    # \u5f3a\u5236\u7f8e\u56fd\u5730\u533a+\u7f8e\u5143\u8d27\u5e01\uff0c\u4e0d\u53d7VPN\u5f71\u54cd
    url = "https://{}/dp/{}?language=en_US&currency=USD".format(domain, asin)
    hdrs = random.choice(HEADERS_POOL).copy()
    hdrs["Referer"] = "https://{}/".format(domain)
    hdrs["Accept-Language"] = "en-US,en;q=0.9"
    res = {"asin": asin, "title": "\u83b7\u53d6\u5931\u8d25", "price": "N/A", "rating": "N/A",
           "reviews": "N/A", "brand": "N/A", "image_url": "",
           "description": "", "features": [], "url": url,
           "description_images": [], "main_images": []}
    try:
        sess = requests.Session()
        # \u8bbe\u7f6e\u7f8e\u56fd\u5730\u533a cookie\uff0c\u5f3a\u5236\u4e9a\u9a6c\u900a\u8fd4\u56de\u7f8e\u5143\u4ef7\u683c
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

        # \u6293\u53d6\u4ef7\u683c\u5e76\u8f6c\u6362\u4e3a\u7f8e\u5143\u683c\u5f0f
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

        # ===== \u4e3b\u9875\u56fe\uff08SX1500\u683c\u5f0f\uff09=====
        main_images = []

        # \u65b9\u6cd51\uff1a\u4ece #altImages \u8f6e\u64ad\u56fe\u4e2d\u83b7\u53d6
        try:
            alt_images_container = s.select_one("#altImages")
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
                    except Exception:
                        pass
        except Exception:
            pass

        # \u65b9\u6cd52\uff1a\u4ece #imageBlock \u83b7\u53d6
        if not main_images:
            try:
                image_block = s.select_one("#imageBlock, #imageBlockContainer")
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
                        except Exception:
                            pass
            except Exception:
                pass

        # \u65b9\u6cd53\uff1a\u4ece #landingImage \u83b7\u53d6\u4e3b\u56fe
        if not main_images:
            try:
                landing_img = s.select_one("#landingImage, #imgBlkFront")
                if landing_img:
                    img_src = (landing_img.get("data-old-hires")
                               or landing_img.get("data-a-hires")
                               or landing_img.get("src"))
                    if img_src and img_src.lower().endswith((".jpg", ".jpeg", ".png")):
                        main_images.append(_to_sx1500(img_src))
            except Exception:
                pass

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

        # ===== \u6293\u53d6 Product description \u4e2d\u7684\u56fe\u7247\uff08\u8fc7\u6ee4 GIF\uff09=====
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
    except Exception as e:
        res["title"] = "\u9519\u8bef: {}".format(e)
    return res


def download_image(url):
    """\u4e0b\u8f7d\u56fe\u7247\u5e76\u8fd4\u56de PIL Image \u5bf9\u8c61\u3002"""
    if not url:
        return None
    try:
        r = requests.get(url, headers=random.choice(HEADERS_POOL).copy(), timeout=10)
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content))
    except Exception:
        pass
    return None
