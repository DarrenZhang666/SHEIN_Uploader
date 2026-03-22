# -*- coding: utf-8 -*-
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import threading
import requests
from bs4 import BeautifulSoup
import webbrowser
import re
from PIL import Image, ImageTk
import io
import time
import random
import os
import tempfile
import json

try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    try:
        from webdriver_manager.chrome import ChromeDriverManager
        WEBDRIVER_MANAGER = True
    except ImportError:
        WEBDRIVER_MANAGER = False
    SELENIUM_OK = True
except ImportError:
    SELENIUM_OK = False
    WEBDRIVER_MANAGER = False

SHEIN_LOGIN_URL = "https://sso.geiwohuo.com/#/login"
SHEIN_HOME_URL  = "https://sso.geiwohuo.com/#/home"
SHEIN_PUBLISH_URL = "https://sso.geiwohuo.com/#/spmc/commodities-category/followsales-pro/list?externalSystem=spmp"
AMAZON_PRODUCT_URL = "https://www.amazon.com/dp/{asin}"

# ── 从 shein_categories.json 加载分类树 ──────────────────────────
def _load_shein_categories():
    """加载同目录下的 shein_categories.json，返回分类列表。"""
    json_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "shein_categories.json")
    try:
        with open(json_path, "r", encoding="utf-8") as f:
            return json.load(f).get("categories", [])
    except Exception:
        return []

SHEIN_CATEGORIES = _load_shein_categories()

def _collect_all_nodes(categories):
    """将分类树展平为 [(node, path_list), ...] 列表，path_list 是从根到该节点的名称路径。"""
    result = []
    def _walk(nodes, path):
        for node in nodes:
            current_path = path + [node["name"]]
            result.append((node, current_path))
            if node.get("children"):
                _walk(node["children"], current_path)
    _walk(categories, [])
    return result

ALL_CATEGORY_NODES = _collect_all_nodes(SHEIN_CATEGORIES)

def auto_match_category(info):
    """
    根据商品信息自动匹配 SHEIN 分类节点。
    返回 dict: {"name": 最终分类名, "path": [一级, 二级, 三级, ...], "id": node_id}
    如匹配失败返回 {"name": "其他", "path": [], "id": ""}
    """
    parts = [
        info.get("title", ""),
        info.get("brand", ""),
        info.get("description", ""),
        info.get("category", ""),
    ] + info.get("features", [])
    combined = " ".join(parts).lower()

    best_node = None
    best_path = []
    best_score = 0
    best_depth = 0

    for node, path in ALL_CATEGORY_NODES:
        score = 0
        for kw in node.get("keywords", []):
            if kw.lower() in combined:
                # 较长关键词权重更高，避免单字误匹配
                score += len(kw)
        if score > best_score or (score == best_score and len(path) > best_depth):
            best_score = score
            best_depth = len(path)
            best_node = node
            best_path = path

    if best_node and best_score > 0:
        return {"name": best_node["name"], "path": best_path, "id": best_node.get("id", "")}
    return {"name": "其他", "path": [], "id": ""}
HEADERS_POOL = [
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
     "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"},
    {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 Chrome/122.0.0.0 Safari/537.36",
     "Accept-Language": "en-US,en;q=0.9", "Accept": "text/html,*/*;q=0.8"},
]
BG_DARK="#1a1d2e"; BG_PANEL="#23263a"; BG_CARD="#2c2f45"
ACCENT="#e84393"; ACCENT2="#ff6bae"; TEXT_MAIN="#f0f0f0"
TEXT_SUB="#a0a3b1"; BORDER="#3a3d55"; GREEN="#4cde96"
YELLOW="#ffc857"; RED="#ff5f57"

def fetch_amazon_product(asin):
    url = AMAZON_PRODUCT_URL.format(asin=asin)
    hdrs = random.choice(HEADERS_POOL).copy()
    hdrs["Referer"] = "https://www.amazon.com/"
    res = {"asin":asin,"title":"获取失败","price":"N/A","rating":"N/A",
           "reviews":"N/A","brand":"N/A","image_url":"",
           "description":"","features":[],"url":url,"description_images":[],"main_images":[]}
    try:
        r = requests.Session().get(url, headers=hdrs, timeout=15)
        if r.status_code != 200:
            res["title"] = "HTTP {}".format(r.status_code); return res
        s = BeautifulSoup(r.text, "html.parser")
        t = s.select_one("#productTitle")
        if t: res["title"] = t.get_text(strip=True)
        
        # 抓取价格并转换为美元格式
        price_raw = "N/A"
        for sel in ["#priceblock_ourprice",".a-price .a-offscreen",
                    "#priceblock_dealprice",".apexPriceToPay .a-offscreen"]:
            p = s.select_one(sel)
            if p: 
                price_raw = p.get_text(strip=True)
                break
        
        # 转换价格为美元格式
        if price_raw != "N/A":
            # 检测货币类型并转换
            if "¥" in price_raw or "JPY" in price_raw.upper():
                # 日元转美元（汇率：1 USD ≈ 150 JPY，可根据实际调整）
                price_match = re.search(r'[\d,]+\.?\d*', price_raw.replace(',', ''))
                if price_match:
                    jpy_price = float(price_match.group())
                    usd_price = jpy_price / 150.0  # 汇率转换
                    res["price"] = "${:.2f}".format(usd_price)
                else:
                    res["price"] = "N/A"
            elif "$" in price_raw:
                # 已经是美元，直接提取
                price_match = re.search(r'[\d,]+\.?\d*', price_raw.replace(',', ''))
                if price_match:
                    res["price"] = "${}".format(price_match.group())
                else:
                    res["price"] = price_raw
            else:
                # 其他货币，提取数字并加上$
                price_match = re.search(r'[\d,]+\.?\d*', price_raw.replace(',', ''))
                if price_match:
                    res["price"] = "${}".format(price_match.group())
                else:
                    res["price"] = "N/A"
        else:
            res["price"] = "N/A"
        
        rt = s.select_one("span[data-hook='rating-out-of-text']")
        if rt:
            m = re.search(r"[\d.]+", rt.get_text())
            if m: res["rating"] = m.group()
        rv = s.select_one("#acrCustomerReviewText")
        if rv: res["reviews"] = rv.get_text(strip=True)
        br = s.select_one("#bylineInfo")
        if br: res["brand"] = br.get_text(strip=True)
        
        # ===== 优化：爬取Amazon产品标题旁边的高质量主页图（SX1500格式） =====
        main_images = []
        
        # 方法1：从 #altImages 轮播图中获取所有图片，并转换为SX1500格式
        try:
            alt_images_container = s.select_one("#altImages")
            if alt_images_container:
                for img_li in alt_images_container.select("li"):
                    try:
                        img_el = img_li.select_one("img")
                        if img_el:
                            # 优先获取高质量属性
                            img_src = img_el.get("data-old-hires") or img_el.get("data-a-hires") or img_el.get("src")
                            if img_src and img_src.lower().endswith((".jpg", ".jpeg", ".png")):
                                # 提取ASIN或图片ID，重新构建SX1500 URL
                                # Amazon URL格式: https://m.media-amazon.com/images/I/XXXXX.jpg
                                if "images/I/" in img_src:
                                    # 提取图片ID
                                    match = re.search(r'images/I/([^._]+)', img_src)
                                    if match:
                                        img_id = match.group(1)
                                        # 构建高质量URL
                                        img_src = f"https://m.media-amazon.com/images/I/{img_id}._SX1500_.jpg"
                                
                                # 确保是SX1500格式
                                img_src = img_src.replace("._SS40_", "._SX1500_")
                                img_src = img_src.replace("._SS75_", "._SX1500_")
                                img_src = img_src.replace("._SX38_", "._SX1500_")
                                img_src = img_src.replace("._SY38_", "._SX1500_")
                                img_src = img_src.replace("._SX75_", "._SX1500_")
                                img_src = img_src.replace("._SX100_", "._SX1500_")
                                img_src = img_src.replace("._SX200_", "._SX1500_")
                                img_src = img_src.replace("._SX300_", "._SX1500_")
                                img_src = img_src.replace("._SX500_", "._SX1500_")
                                img_src = img_src.replace("._SX1000_", "._SX1500_")
                                img_src = img_src.replace("._SL75_", "._SX1500_")
                                img_src = img_src.replace("._SL100_", "._SX1500_")
                                img_src = img_src.replace("._SL200_", "._SX1500_")
                                img_src = img_src.replace("._SL300_", "._SX1500_")
                                img_src = img_src.replace("._SL500_", "._SX1500_")
                                img_src = img_src.replace("._SL1000_", "._SX1500_")
                                img_src = img_src.replace("._AA50_", "._SX1500_")
                                img_src = img_src.replace("._AA75_", "._SX1500_")
                                
                                if img_src not in main_images:
                                    main_images.append(img_src)
                    except Exception:
                        pass
        except Exception:
            pass
        
        # 方法2：如果没找到，从 #imageBlock 中获取
        if not main_images or len(main_images) < 1:
            try:
                image_block = s.select_one("#imageBlock, #imageBlockContainer")
                if image_block:
                    for img_el in image_block.select("img"):
                        try:
                            img_src = img_el.get("data-old-hires") or img_el.get("data-a-hires") or img_el.get("src")
                            if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                                if img_src.lower().endswith((".jpg", ".jpeg", ".png")):
                                    # 提取图片ID，重新构建SX1500 URL
                                    if "images/I/" in img_src:
                                        match = re.search(r'images/I/([^._]+)', img_src)
                                        if match:
                                            img_id = match.group(1)
                                            img_src = f"https://m.media-amazon.com/images/I/{img_id}._SX1500_.jpg"
                                    
                                    # 确保是SX1500格式
                                    img_src = img_src.replace("._SS40_", "._SX1500_")
                                    img_src = img_src.replace("._SS75_", "._SX1500_")
                                    img_src = img_src.replace("._SX38_", "._SX1500_")
                                    img_src = img_src.replace("._SY38_", "._SX1500_")
                                    img_src = img_src.replace("._SX75_", "._SX1500_")
                                    img_src = img_src.replace("._SX100_", "._SX1500_")
                                    img_src = img_src.replace("._SX200_", "._SX1500_")
                                    img_src = img_src.replace("._SX300_", "._SX1500_")
                                    img_src = img_src.replace("._SX500_", "._SX1500_")
                                    img_src = img_src.replace("._SX1000_", "._SX1500_")
                                    img_src = img_src.replace("._SL75_", "._SX1500_")
                                    img_src = img_src.replace("._SL100_", "._SX1500_")
                                    img_src = img_src.replace("._SL200_", "._SX1500_")
                                    img_src = img_src.replace("._SL300_", "._SX1500_")
                                    img_src = img_src.replace("._SL500_", "._SX1500_")
                                    img_src = img_src.replace("._SL1000_", "._SX1500_")
                                    img_src = img_src.replace("._AA50_", "._SX1500_")
                                    img_src = img_src.replace("._AA75_", "._SX1500_")
                                    
                                    if img_src not in main_images:
                                        main_images.append(img_src)
                        except Exception:
                            pass
            except Exception:
                pass
        
        # 方法3：从 #landingImage 获取主图
        if not main_images:
            try:
                landing_img = s.select_one("#landingImage, #imgBlkFront")
                if landing_img:
                    img_src = landing_img.get("data-old-hires") or landing_img.get("data-a-hires") or landing_img.get("src")
                    if img_src and img_src.lower().endswith((".jpg", ".jpeg", ".png")):
                        # 提取图片ID，重新构建SX1500 URL
                        if "images/I/" in img_src:
                            match = re.search(r'images/I/([^._]+)', img_src)
                            if match:
                                img_id = match.group(1)
                                img_src = f"https://m.media-amazon.com/images/I/{img_id}._SX1500_.jpg"
                        
                        # 确保是SX1500格式
                        img_src = img_src.replace("._SS40_", "._SX1500_")
                        img_src = img_src.replace("._SS75_", "._SX1500_")
                        img_src = img_src.replace("._SX38_", "._SX1500_")
                        img_src = img_src.replace("._SY38_", "._SX1500_")
                        img_src = img_src.replace("._SX75_", "._SX1500_")
                        img_src = img_src.replace("._SX100_", "._SX1500_")
                        img_src = img_src.replace("._SX200_", "._SX1500_")
                        img_src = img_src.replace("._SX300_", "._SX1500_")
                        img_src = img_src.replace("._SX500_", "._SX1500_")
                        img_src = img_src.replace("._SX1000_", "._SX1500_")
                        img_src = img_src.replace("._SL75_", "._SX1500_")
                        img_src = img_src.replace("._SL100_", "._SX1500_")
                        img_src = img_src.replace("._SL200_", "._SX1500_")
                        img_src = img_src.replace("._SL300_", "._SX1500_")
                        img_src = img_src.replace("._SL500_", "._SX1500_")
                        img_src = img_src.replace("._SL1000_", "._SX1500_")
                        img_src = img_src.replace("._AA50_", "._SX1500_")
                        img_src = img_src.replace("._AA75_", "._SX1500_")
                        
                        main_images.append(img_src)
            except Exception:
                pass
        
        # 保存所有主图到 main_images（只需5张）
        res["main_images"] = main_images
        if main_images:
            res["image_url"] = main_images[0]
        
        feats = [li.get_text(strip=True)
                 for li in s.select("#feature-bullets li span.a-list-item") if li.get_text(strip=True)]
        res["features"] = feats[:6]
        d = s.select_one("#productDescription p")
        if d: res["description"] = d.get_text(strip=True)[:300]
        
        # 抓取商品描述中的图片（仅 Product description 部分，过滤 GIF）
        desc_images = []
        # 方法1：查找 <h2>Product description</h2> 标签，然后获取后续的图片
        h2_tags = s.select("h2")
        for h2 in h2_tags:
            if "Product description" in h2.get_text():
                # 找到 Product description 标题后，获取后续的所有图片
                current = h2.find_next()
                while current and len(desc_images) < 5:
                    if current.name == "h2":  # 遇到下一个 h2 标签，停止
                        break
                    if current.name == "img":
                        try:
                            img_src = current.get("src") or current.get("data-old-hires") or current.get("data-a-hires")
                            if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                                # 过滤掉 GIF 格式
                                if not img_src.lower().endswith(".gif"):
                                    desc_images.append(img_src)
                        except Exception:
                            pass
                    # 查找当前元素内的所有图片
                    for img_el in current.select("img"):
                        try:
                            img_src = img_el.get("src") or img_el.get("data-old-hires") or img_el.get("data-a-hires")
                            if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                                # 过滤掉 GIF 格式
                                if not img_src.lower().endswith(".gif") and img_src not in desc_images:
                                    desc_images.append(img_src)
                        except Exception:
                            pass
                    current = current.find_next()
                break
        
        # 方法2：如果方法1没找到，尝试查找 #productDescription
        if not desc_images:
            prod_desc = s.select_one("#productDescription")
            if prod_desc:
                for img_el in prod_desc.select("img"):
                    try:
                        img_src = img_el.get("src") or img_el.get("data-old-hires") or img_el.get("data-a-hires")
                        if img_src and ("amazon" in img_src.lower() or "images-" in img_src.lower()):
                            # 过滤掉 GIF 格式
                            if not img_src.lower().endswith(".gif"):
                                desc_images.append(img_src)
                    except Exception:
                        pass
        
        res["description_images"] = desc_images[:5]  # 最多5张
    except Exception as e:
        res["title"] = "错误: {}".format(e)
    return res

def download_image(url):
    if not url: return None
    try:
        r = requests.get(url, headers=random.choice(HEADERS_POOL).copy(), timeout=10)
        if r.status_code == 200: return Image.open(io.BytesIO(r.content))
    except: pass
    return None

class SheinApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("SHEIN 商品采集 & 发布工具")
        self.geometry("1280x800"); self.minsize(1000,680)
        self.configure(bg=BG_DARK)
        self.asin_list=[]; self.asin_vars={}; self.asin_dots={}
        self.product_cache={}; self.current_asin=None
        self.select_all_var=tk.BooleanVar(value=False)
        self.price_multiplier=tk.StringVar(value="3")
        self._fetch_thread=None; self._photo_ref=None
        self._shein_publisher=None   # 持久化浏览器实例
        self._stop_publish=False      # 停止上品标志
        self._driver_ready=False      # 驱动预热完成标志
        
        # 初始化日志文件
        self._init_log_file()
        
        self._build_ui(); self._apply_styles()

    def _init_log_file(self):
        """初始化日志文件（保存到桌面）。"""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        log_dir = os.path.join(desktop, "SHEIN_Logs")
        os.makedirs(log_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(log_dir, "log_{}.txt".format(timestamp))
        self._write_log("=== SHEIN 商品采集工具日志 ===")
        self._write_log("启动时间: {}".format(time.strftime("%Y-%m-%d %H:%M:%S")))
        self._write_log("")

    def _write_log(self, msg):
        """写入日志文件。"""
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("[{}] {}\n".format(time.strftime("%H:%M:%S"), msg))
        except Exception:
            pass

    def _warmup_chrome(self):
        """后台预热 Chrome，程序启动时自动运行。"""
        try:
            self._pub_log("后台预热 Chrome 中...")
            pub = SheinPublisher(log_cb=self._pub_log)
            pub.start_browser()
            self._shein_publisher = pub
            self._driver_ready = True
            self._pub_log("Chrome 已预热完成，可直接使用")
        except Exception as e:
            self._pub_log("预热失败: {}".format(str(e)[:50]))
            self._driver_ready = False

    def _build_ui(self):
        self._build_topbar()
        body=tk.Frame(self,bg=BG_DARK)
        body.pack(fill="both",expand=True,padx=12,pady=(0,12))
        body.columnconfigure(0,weight=0,minsize=265)
        body.columnconfigure(1,weight=1)
        body.rowconfigure(0,weight=1)
        self._build_left(body); self._build_right(body)

    def _build_topbar(self):
        bar=tk.Frame(self,bg=BG_PANEL,height=60)
        bar.pack(fill="x"); bar.pack_propagate(False)
        lg=tk.Frame(bar,bg=BG_PANEL); lg.pack(side="left",padx=20)
        tk.Label(lg,text="SHEIN",font=("Segoe UI",18,"bold"),fg=ACCENT,bg=BG_PANEL).pack(side="left")
        tk.Label(lg,text=" 商品采集 & 发布工具",font=("Segoe UI",13),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        bf=tk.Frame(bar,bg=BG_PANEL); bf.pack(side="right",padx=20,pady=10)
        # 售价倍数输入框（在最后添加，寄弹出效果为最左侧）
        pm_frame=tk.Frame(bf,bg=BG_PANEL)
        pm_frame.pack(side="left",padx=(0,10))
        tk.Label(pm_frame,text="售价倍数:",font=("Segoe UI",10),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        tk.Entry(pm_frame,textvariable=self.price_multiplier,width=4,font=("Segoe UI",10),bg=BG_CARD,fg=TEXT_MAIN,insertbackground=TEXT_MAIN,relief="flat",bd=2).pack(side="left",padx=(4,0))
        self._btn(bf,"导入 ASIN 文本",ACCENT,self._import_txt).pack(side="left",padx=5)
        self._btn(bf,"抓取选中商品","#2563eb",self._fetch_sel).pack(side="left",padx=5)
        self._btn(bf,"开始上品","#7c3aed",self._open_publish_page).pack(side="left",padx=5)
        self._btn(bf,"抓取页面信息","#8b5cf6",self._dump_page_info_btn).pack(side="left",padx=5)
        self._btn(bf,"停止","#dc2626",self._stop_publish_action).pack(side="left",padx=5)
        self._btn(bf,"登录 SHEIN","#059669",self._open_shein).pack(side="left",padx=5)

    def _build_left(self,parent):
        f=tk.Frame(parent,bg=BG_PANEL,width=265)
        f.grid(row=0,column=0,sticky="nsew",padx=(0,8),pady=4)
        f.pack_propagate(False)
        h=tk.Frame(f,bg=BG_PANEL); h.pack(fill="x",padx=12,pady=(12,4))
        tk.Label(h,text="ASIN 列表",font=("Segoe UI",11,"bold"),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        self.cnt_lbl=tk.Label(h,text="(0)",font=("Segoe UI",10),fg=TEXT_SUB,bg=BG_PANEL)
        self.cnt_lbl.pack(side="left",padx=4)
        sr=tk.Frame(f,bg=BG_PANEL); sr.pack(fill="x",padx=12,pady=(0,6))
        tk.Checkbutton(sr,text="全选",variable=self.select_all_var,command=self._sel_all,
            bg=BG_PANEL,fg=TEXT_MAIN,selectcolor=BG_CARD,activebackground=BG_PANEL,
            activeforeground=ACCENT2,font=("Segoe UI",10),cursor="hand2").pack(side="left")
        self.sel_lbl=tk.Label(sr,text="已选 0",font=("Segoe UI",9),fg=TEXT_SUB,bg=BG_PANEL)
        self.sel_lbl.pack(side="right")
        tk.Frame(f,bg=BORDER,height=1).pack(fill="x",padx=8,pady=(0,4))
        c=tk.Frame(f,bg=BG_PANEL); c.pack(fill="both",expand=True,padx=4,pady=4)
        cv=tk.Canvas(c,bg=BG_PANEL,highlightthickness=0,bd=0)
        sb=ttk.Scrollbar(c,orient="vertical",command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); cv.pack(side="left",fill="both",expand=True)
        self.lf=tk.Frame(cv,bg=BG_PANEL)
        self._lw=cv.create_window((0,0),window=self.lf,anchor="nw")
        self.lf.bind("<Configure>",lambda e:cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Configure>",lambda e:cv.itemconfig(self._lw,width=e.width))
        cv.bind_all("<MouseWheel>",lambda e:cv.yview_scroll(int(-1*(e.delta/120)),"units"))
        self.acv=cv

    def _build_right(self,parent):
        f=tk.Frame(parent,bg=BG_PANEL)
        f.grid(row=0,column=1,sticky="nsew",pady=4)
        tp=tk.Frame(f,bg=BG_PANEL); tp.pack(fill="x",padx=16,pady=(12,6))
        tk.Label(tp,text="商品详情",font=("Segoe UI",12,"bold"),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        self.status_lbl=tk.Label(tp,text="请先导入 ASIN 文件",font=("Segoe UI",9),fg=TEXT_SUB,bg=BG_PANEL)
        self.status_lbl.pack(side="right")
        self.progress=ttk.Progressbar(f,mode="indeterminate")
        self.progress.pack(fill="x",padx=16,pady=(0,8))
        dc=tk.Canvas(f,bg=BG_PANEL,highlightthickness=0)
        ds=ttk.Scrollbar(f,orient="vertical",command=dc.yview)
        dc.configure(yscrollcommand=ds.set)
        ds.pack(side="right",fill="y")
        dc.pack(side="left",fill="both",expand=True,padx=(12,0),pady=(0,8))
        self.df=tk.Frame(dc,bg=BG_PANEL)
        self._dw=dc.create_window((0,0),window=self.df,anchor="nw")
        self.df.bind("<Configure>",lambda e:dc.configure(scrollregion=dc.bbox("all")))
        dc.bind("<Configure>",lambda e:dc.itemconfig(self._dw,width=e.width))
        self.dc=dc; self._welcome()

    def _welcome(self):
        for w in self.df.winfo_children(): w.destroy()
        tk.Label(self.df,
            text=("\n\n\n  SHEIN 商品采集工具\n\n"
                  "  1. 点击顶部【导入 ASIN 文本】载入商品列表\n\n"
                  "  2. 勾选 ASIN 后点击【抓取选中商品】\n\n"
                  "  3. 点击左侧 ASIN 行查看商品详情\n\n"
                  "  4. 点击【登录 SHEIN】进入店主后台发布商品"),
            font=("Segoe UI",12),fg=TEXT_SUB,bg=BG_PANEL,
            justify="left",wraplength=600).pack(pady=20,padx=30)

    def _apply_styles(self):
        st=ttk.Style(self); st.theme_use("clam")
        st.configure("Vertical.TScrollbar",background=BG_CARD,troughcolor=BG_PANEL,
                     arrowcolor=TEXT_SUB,bordercolor=BG_PANEL)
        st.configure("TProgressbar",troughcolor=BG_CARD,background=ACCENT,
                     darkcolor=ACCENT,lightcolor=ACCENT2)

    def _btn(self,parent,text,color,cmd):
        b=tk.Button(parent,text=text,bg=color,fg="white",
            font=("Segoe UI",10,"bold"),relief="flat",bd=0,
            padx=14,pady=7,cursor="hand2",command=cmd,
            activebackground=ACCENT2,activeforeground="white")
        b.bind("<Enter>",lambda e,x=b,c=color:x.config(bg=self._lit(c)))
        b.bind("<Leave>",lambda e,x=b,c=color:x.config(bg=c))
        return b

    @staticmethod
    def _lit(hx):
        h=hx.lstrip("#"); r,g,b=(int(h[i:i+2],16) for i in (0,2,4))
        return "#{:02x}{:02x}{:02x}".format(min(255,r+30),min(255,g+30),min(255,b+30))

    def _import_txt(self):
        path=filedialog.askopenfilename(title="选择 ASIN 文本文件",
            filetypes=[("文本文件","*.txt"),("所有文件","*.*")])
        if not path: return
        try:
            with open(path,"r",encoding="utf-8") as f:
                lines=[l.strip() for l in f]
            asins=[l for l in lines if re.match(r"^B[A-Z0-9]{9}$",l)]
            if not asins:
                messagebox.showwarning("提示","未找到有效 ASIN 码"); return
            self.asin_list=asins; self.asin_vars={}; self.asin_dots={}
            self._render_list()
            self.status_lbl.config(text="已载入 {} 个 ASIN".format(len(asins)))
            self._welcome()
        except Exception as e:
            messagebox.showerror("读取失败",str(e))

    def _render_list(self):
        for w in self.lf.winfo_children(): w.destroy()
        for idx,asin in enumerate(self.asin_list):
            var=tk.BooleanVar(value=False)
            self.asin_vars[asin]=var
            bg=BG_CARD if idx%2==0 else BG_PANEL
            row=tk.Frame(self.lf,bg=bg,cursor="hand2")
            row.pack(fill="x",pady=1)
            tk.Checkbutton(row,variable=var,bg=bg,selectcolor=BG_DARK,
                activebackground=bg,command=self._upd_cnt).pack(side="left",padx=(8,2))
            dot=tk.Label(row,text="\u25cf",font=("Segoe UI",8),fg=TEXT_SUB,bg=bg)
            dot.pack(side="left"); self.asin_dots[asin]=dot
            lbl=tk.Label(row,text=asin,font=("Consolas",10),fg=TEXT_MAIN,bg=bg,anchor="w",cursor="hand2")
            lbl.pack(side="left",padx=4,pady=5)
            lbl.bind("<Button-1>",lambda e,a=asin:self._click(a))
            row.bind("<Button-1>",lambda e,a=asin:self._click(a))
        self.cnt_lbl.config(text="({})".format(len(self.asin_list)))
        self._upd_cnt(); self.select_all_var.set(False)

    def _click(self,asin):
        self.current_asin=asin
        if asin in self.product_cache: self._show(self.product_cache[asin])
        else: self._placeholder(asin)

    def _placeholder(self,asin):
        for w in self.df.winfo_children(): w.destroy()
        tk.Label(self.df,text="ASIN: {}\n\n尚未抓取。\n请勾选后点击【抓取选中商品】。".format(asin),
            font=("Segoe UI",12),fg=TEXT_SUB,bg=BG_PANEL,justify="center").pack(pady=60)

    def _sel_all(self):
        v=self.select_all_var.get()
        for var in self.asin_vars.values(): var.set(v)
        self._upd_cnt()

    def _upd_cnt(self):
        cnt=sum(1 for v in self.asin_vars.values() if v.get())
        self.sel_lbl.config(text="已选 {}".format(cnt))
        if len(self.asin_vars)>0:
            self.select_all_var.set(cnt==len(self.asin_vars))

    def _open_shein(self):
        """打开 SHEIN 登录页面（用 Chrome 浏览器）。"""
        self.status_lbl.config(text='正在启动 Chrome...')
        
        def _launch_chrome():
            try:
                pub = SheinPublisher(log_cb=self._pub_log)
                
                # 先尝试连接已打开的 Chrome
                try:
                    self.status_lbl.config(text='尝试连接已打开的 Chrome...')
                    pub._connect_chrome_only()
                    self._shein_publisher = pub
                    self.status_lbl.config(text='已连接到 Chrome，打开登录页...')
                    pub.driver.get(SHEIN_LOGIN_URL)
                    time.sleep(1)
                    self.status_lbl.config(text='已打开 SHEIN 登录页，请手动登录')
                    return
                except Exception as e:
                    self._pub_log("[DEBUG] 连接已打开的 Chrome 失败，启动新 Chrome...")
                
                # 如果连接失败，启动新 Chrome
                self.status_lbl.config(text='启动新 Chrome 浏览器...')
                pub.start_chrome_browser()
                self._shein_publisher = pub
                self.status_lbl.config(text='Chrome 已启动，打开登录页...')
                pub.driver.get(SHEIN_LOGIN_URL)
                time.sleep(1)
                self.status_lbl.config(text='已打开 SHEIN 登录页，请手动登录')
            except Exception as e:
                self.status_lbl.config(text='启动失败: ' + str(e)[:40])
                self.after(0, lambda err=str(e): messagebox.showerror('失败', err[:100]))
        
        threading.Thread(target=_launch_chrome, daemon=True).start()

    def _open_publish_page(self):
        """打开 SHEIN 商品发布页面，自动上传选中商品的图片。"""
        # 检查是否选中了商品
        if self.current_asin is None:
            messagebox.showwarning('提示', '请先在左侧选择一个商品')
            return
        
        # 检查商品是否有图片
        product_info = self.product_cache.get(self.current_asin)
        if not product_info or not product_info.get('image_url'):
            messagebox.showwarning('提示', '该商品没有图片信息，请先抓取商品')
            return
        
        # 如果已经有 Chrome 实例，直接用
        if self._shein_publisher is not None and self._shein_publisher.is_alive():
            self.status_lbl.config(text='已有 Chrome 实例，打开商品发布页...')
            try:
                self._shein_publisher.driver.get(SHEIN_PUBLISH_URL)
                time.sleep(2)
                self.status_lbl.config(text='正在上传商品图片...')
                self._auto_upload_image()
                return
            except Exception as e:
                self._pub_log('打开页面失败: ' + str(e)[:40])
                self._shein_publisher = None
        
        # 否则尝试连接已打开的 Chrome
        self.status_lbl.config(text='正在连接到 Chrome 浏览器...')
        
        # 创建 Selenium 实例以便后续操作
        def _init_selenium():
            try:
                pub = SheinPublisher(log_cb=self._pub_log)
                
                # 先尝试连接已打开的 Chrome
                try:
                    self.status_lbl.config(text='尝试连接已打开的 Chrome...')
                    pub._connect_chrome_only()
                    self._shein_publisher = pub
                    self.status_lbl.config(text='已连接到已打开的 Chrome')
                    # 导航到商品发布页
                    pub.driver.get(SHEIN_PUBLISH_URL)
                    time.sleep(2)
                    self.status_lbl.config(text='正在上传商品图片...')
                    self._auto_upload_image()
                    return
                except Exception as e:
                    self._pub_log("[DEBUG] 连接已打开的 Chrome 失败: {}".format(str(e)[:40]))
                
                # 如果连接失败，启动新 Chrome
                self.status_lbl.config(text='启动新 Chrome 浏览器...')
                pub.start_chrome_browser()
                self._shein_publisher = pub
                self.status_lbl.config(text='Chrome 已启动，正在打开商品发布页...')
                pub.driver.get(SHEIN_PUBLISH_URL)
                time.sleep(2)
                self.status_lbl.config(text='正在上传商品图片...')
                self._auto_upload_image()
            except Exception as e:
                self.status_lbl.config(text='操作失败: ' + str(e)[:40])
                self._pub_log('操作失败: ' + str(e))
                self.after(0, lambda err=str(e): messagebox.showerror('失败', err[:100]))
        
        threading.Thread(target=_init_selenium, daemon=True).start()

    def _auto_upload_image(self):
        """自动上传商品图片、选择推荐类目、填写基础信息（在后台线程中调用）。"""
        try:
            if self.current_asin is None or self._shein_publisher is None:
                return

            product_info = self.product_cache.get(self.current_asin)
            if not product_info or not product_info.get('image_url'):
                return

            # 先关闭可能弹出的公告弹窗，避免影响后续操作
            try:
                self._shein_publisher._dismiss_announcements()
            except Exception:
                pass

            # 点击"识图发品"按钮
            self.status_lbl.config(text='点击"识图发品"按钮...')
            if not self._shein_publisher.click_identify_image_button():
                self.status_lbl.config(text='未找到"识图发品"按钮')
                return
            
            # 下载图片到临时目录
            image_url = product_info.get('image_url')
            temp_dir = os.path.join(tempfile.gettempdir(), 'shein_images')
            os.makedirs(temp_dir, exist_ok=True)
            temp_image = os.path.join(temp_dir, '{}.jpg'.format(self.current_asin))
            
            self.status_lbl.config(text='下载商品图片...')
            try:
                response = requests.get(image_url, timeout=10)
                with open(temp_image, 'wb') as f:
                    f.write(response.content)
            except Exception as e:
                self.status_lbl.config(text='下载图片失败: ' + str(e)[:40])
                return
            
            # 上传图片
            self.status_lbl.config(text='上传图片到 SHEIN...')
            if not self._shein_publisher.upload_product_image(temp_image):
                self.status_lbl.config(text='✗ 图片上传失败')
                return
            
            self.status_lbl.config(text='✓ 图片上传成功，等待识别中...')
            self._pub_log('图片已上传，等待 SHEIN 识别（5秒）...')
            
            # 等待 5 秒让图片识别完成
            for i in range(5, 0, -1):
                self.status_lbl.config(text='✓ 图片上传成功，等待识别中... {}s'.format(i))
                time.sleep(1)
            
            # 选择第一个推荐类目
            self.status_lbl.config(text='选择第一个推荐类目...')
            if not self._shein_publisher.select_first_category():
                self.status_lbl.config(text='✗ 选择类目失败')
                return
            
            self.status_lbl.config(text='✓ 已选择推荐类目，点击确认...')
            time.sleep(1)
            
            # 点击"确认，下一步"按钮
            if not self._shein_publisher.click_confirm_button():
                self.status_lbl.config(text='✗ 点击确认按钮失败')
                return
            
            self.status_lbl.config(text='✓ 商品类目确认成功，等待页面加载...')
            self._pub_log('商品 {} 类目确认成功'.format(self.current_asin))
            time.sleep(3)
            
            # 填写基础信息
            self.status_lbl.config(text='填写商品基础信息...')
            if self._shein_publisher.fill_product_info(product_info):
                self.status_lbl.config(text='✓ 商品基础信息填写完成')
                self._pub_log('商品 {} 基础信息填写完成'.format(self.current_asin))

                # 等待页面稳定后继续填写规格及供应信息
                self.status_lbl.config(text='等待页面加载，准备填写规格及供应信息...')
                self._pub_log('[DEBUG] 等待2秒后开始填写规格及供应信息...')
                time.sleep(2)

                # 填写规格及供应信息
                self.status_lbl.config(text='填写规格及供应信息...')
                self._pub_log('[DEBUG] 开始填写规格及供应信息...')
                try:
                    # 应用售价倍数到价格
                    try:
                        mult = float(self.price_multiplier.get())
                    except Exception:
                        mult = 3.0
                    import copy as _copy
                    product_info_pub = _copy.copy(product_info)
                    price_raw = product_info_pub.get("price", "N/A")
                    import re as _re
                    if price_raw and price_raw != "N/A":
                        _m = _re.search(r"[\d]+\.?[\d]*", price_raw.replace(",",""))
                        if _m:
                            _orig = float(_m.group())
                            _new_price = round(_orig * mult, 2)
                            product_info_pub["price"] = str(_new_price)
                            self._pub_log("[DEBUG] 售价倍数{}, 价格 {} -> {}".format(mult, _orig, _new_price))
                    self._shein_publisher.fill_spec_and_supply_info(product_info_pub)
                    self.status_lbl.config(text='✓ 规格及供应信息填写完成')
                    self._pub_log('商品 {} 规格及供应信息填写完成'.format(self.current_asin))
                except Exception as spec_e:
                    self._pub_log('[ERROR] 规格及供应信息填写异常: {}'.format(str(spec_e)[:80]))
                    self.status_lbl.config(text='规格及供应信息填写遇到问题，请手动检查')
            else:
                self.status_lbl.config(text='✗ 基础信息填写失败')
        except Exception as e:
            self.status_lbl.config(text='上传出错: ' + str(e)[:40])
            self._pub_log('上传出错: ' + str(e))

    def _dump_page_info_btn(self):
        """抓取当前浏览器页面的元素信息，帮助定位'识图发品'按钮。"""
        if self._shein_publisher is None or not self._shein_publisher.is_alive():
            messagebox.showwarning('提示', '浏览器未打开，请先点击【开始上品】')
            return
        
        self.status_lbl.config(text='正在抓取页面信息...')
        
        def _do_dump():
            try:
                info = self._shein_publisher.dump_page_elements()
                self.after(0, lambda: self.status_lbl.config(text='页面信息已抓取，查看日志'))
                # 显示信息窗口
                self.after(0, lambda i=info: messagebox.showinfo('页面元素信息', i[:500] + '\n...(更多信息见日志)'))
            except Exception as e:
                self.after(0, lambda err=str(e): self.status_lbl.config(text='抓取失败: ' + err[:40]))
        
        threading.Thread(target=_do_dump, daemon=True).start()

    def _upload_product_image_btn(self):
        """上传商品图片按钮回调。"""
        if self._shein_publisher is None or not self._shein_publisher.is_alive():
            messagebox.showwarning('提示', '浏览器未打开，请先点击【开始上品】')
            return
        
        if self.current_asin is None:
            messagebox.showwarning('提示', '请先在左侧选择一个商品')
            return
        
        # 获取商品的图片
        product_info = self.product_cache.get(self.current_asin)
        if not product_info or not product_info.get('image_url'):
            messagebox.showwarning('提示', '该商品没有图片信息，请先抓取商品')
            return
        
        self.status_lbl.config(text='正在上传商品图片...')
        
        def _do_upload():
            try:
                # 先关闭可能弹出的公告弹窗
                try:
                    self._shein_publisher._dismiss_announcements()
                except Exception:
                    pass
                # 点击"识图发品"按钮
                self.status_lbl.config(text='点击"识图发品"按钮...')
                if not self._shein_publisher.click_identify_image_button():
                    self.after(0, lambda: messagebox.showwarning('失败', '未找到"识图发品"按钮'))
                    return
                
                # 下载图片到临时目录
                image_url = product_info.get('image_url')
                temp_dir = os.path.join(tempfile.gettempdir(), 'shein_images')
                os.makedirs(temp_dir, exist_ok=True)
                temp_image = os.path.join(temp_dir, '{}.jpg'.format(self.current_asin))
                
                self.status_lbl.config(text='下载图片...')
                try:
                    response = requests.get(image_url, timeout=10)
                    with open(temp_image, 'wb') as f:
                        f.write(response.content)
                except Exception as e:
                    self.after(0, lambda err=str(e): messagebox.showerror('下载失败', err[:100]))
                    return
                
                # 上传图片
                self.status_lbl.config(text='上传图片到 SHEIN...')
                if self._shein_publisher.upload_product_image(temp_image):
                    self.after(0, lambda: self.status_lbl.config(text='图片上传成功'))
                    self.after(0, lambda: messagebox.showinfo('成功', '商品图片已上传'))
                else:
                    self.after(0, lambda: messagebox.showerror('失败', '图片上传失败'))
            except Exception as e:
                self.after(0, lambda err=str(e): self.status_lbl.config(text='上传出错: ' + err[:40]))
                self.after(0, lambda err=str(e): messagebox.showerror('错误', err[:100]))
        
        threading.Thread(target=_do_upload, daemon=True).start()

    def _fetch_sel(self):
        sel=[a for a,v in self.asin_vars.items() if v.get()]
        if not sel: messagebox.showinfo("提示","请先勾选要抓取的 ASIN"); return
        if self._fetch_thread and self._fetch_thread.is_alive():
            messagebox.showinfo("提示","正在抓取中，请稍候..."); return
        self.progress.start(12)
        self.status_lbl.config(text="正在抓取 {} 个商品...".format(len(sel)))
        self._fetch_thread=threading.Thread(target=self._worker,args=(sel,),daemon=True)
        self._fetch_thread.start()

    def _worker(self,asins):
        for i,asin in enumerate(asins):
            msg="抓取中 {}/{}：{}".format(i+1,len(asins),asin)
            self.after(0,lambda m=msg:self.status_lbl.config(text=m))
            info=fetch_amazon_product(asin)
            self.product_cache[asin]=info
            dot=self.asin_dots.get(asin)
            if dot:
                ok=info["title"] not in ("获取失败","") and not info["title"].startswith("错误")
                self.after(0,lambda d=dot,c=GREEN if ok else RED:d.config(fg=c))
            if self.current_asin==asin:
                self.after(0,lambda inf=info:self._show(inf))
            time.sleep(random.uniform(1.5,3.5))
        self.after(0,self._done)

    def _done(self):
        self.progress.stop()
        self.status_lbl.config(text="抓取完成，共缓存 {} 个商品".format(len(self.product_cache)))
        if self.current_asin and self.current_asin in self.product_cache:
            self._show(self.product_cache[self.current_asin])

    def _show(self,info):
        for w in self.df.winfo_children(): w.destroy()
        top=tk.Frame(self.df,bg=BG_PANEL); top.pack(fill="x",pady=(16,8))
        imgf=tk.Frame(top,bg=BG_CARD,width=220,height=220)
        imgf.pack(side="left",padx=20); imgf.pack_propagate(False)
        self.img_lbl=tk.Label(imgf,text="加载图片中...",fg=TEXT_SUB,bg=BG_CARD,font=("Segoe UI",9))
        self.img_lbl.pack(expand=True)
        inf=tk.Frame(top,bg=BG_PANEL); inf.pack(side="left",fill="both",expand=True,padx=(0,20))
        def row(t,sz=10,col=TEXT_MAIN,bold=False):
            tk.Label(inf,text=t,font=("Segoe UI",sz,"bold" if bold else "normal"),
                fg=col,bg=BG_PANEL,wraplength=560,justify="left",anchor="w").pack(fill="x",padx=4,pady=2)
        row(info.get("title",""),13,TEXT_MAIN,True)
        row("ASIN: {}  货号: XYZ-{}".format(info.get("asin",""), info.get("asin","")),10,TEXT_SUB)
        row("品牌: {}".format(info.get("brand","N/A")),10,YELLOW)
        row("价格: {}".format(info.get("price","N/A")),12,GREEN,True)
        row("评分: {}  评论数: {}".format(info.get("rating","N/A"),info.get("reviews","N/A")),10,TEXT_SUB)
        url=info.get("url","")
        if url:
            tk.Button(inf,text="在亚马逊中查看",bg=BG_CARD,fg=ACCENT2,
                font=("Segoe UI",9),relief="flat",bd=0,cursor="hand2",
                command=lambda u=url:webbrowser.open(u)).pack(anchor="w",padx=4,pady=4)
        feats=info.get("features",[])
        if feats:
            tk.Frame(self.df,bg=BORDER,height=1).pack(fill="x",padx=20,pady=6)
            tk.Label(self.df,text="商品特点",font=("Segoe UI",11,"bold"),fg=ACCENT2,bg=BG_PANEL).pack(anchor="w",padx=20)
            for ft in feats:
                fr=tk.Frame(self.df,bg=BG_PANEL); fr.pack(fill="x",padx=20,pady=1)
                tk.Label(fr,text=">",fg=ACCENT,bg=BG_PANEL,font=("Segoe UI",10)).pack(side="left")
                tk.Label(fr,text=ft,font=("Segoe UI",10),fg=TEXT_MAIN,bg=BG_PANEL,
                    wraplength=660,justify="left",anchor="w").pack(side="left",padx=6)
        desc=info.get("description","")
        if desc:
            tk.Frame(self.df,bg=BORDER,height=1).pack(fill="x",padx=20,pady=6)
            tk.Label(self.df,text="商品描述",font=("Segoe UI",11,"bold"),fg=ACCENT2,bg=BG_PANEL).pack(anchor="w",padx=20)
            tk.Label(self.df,text=desc,font=("Segoe UI",10),fg=TEXT_MAIN,bg=BG_PANEL,
                wraplength=700,justify="left",anchor="w").pack(fill="x",padx=24,pady=4)
        tk.Frame(self.df,bg=BORDER,height=1).pack(fill="x",padx=20,pady=10)
        self._btn(self.df,"发布此商品到 SHEIN",ACCENT,
            lambda i=info:self._publish(i)).pack(anchor="w",padx=20,pady=(0,16))
        if info.get("image_url"):
            threading.Thread(target=self._load_img,args=(info["image_url"],),daemon=True).start()
        
        # 显示主页图片（Amazon产品标题旁边的1:1或4:3方形图）
        main_images = info.get("main_images", [])
        tk.Frame(self.df,bg=BORDER,height=1).pack(fill="x",padx=20,pady=10)
        tk.Label(self.df,text="商品详情图片（Ctrl+点击打开）",font=("Segoe UI",11,"bold"),fg=ACCENT2,bg=BG_PANEL).pack(anchor="w",padx=20)
        if main_images:
            for idx, img_url in enumerate(main_images):
                fr=tk.Frame(self.df,bg=BG_PANEL); fr.pack(fill="x",padx=20,pady=2)
                tk.Label(fr,text="图片 {}:".format(idx+1),fg=TEXT_SUB,bg=BG_PANEL,font=("Segoe UI",9)).pack(side="left")
                # 创建可点击的链接标签
                link_lbl=tk.Label(fr,text=img_url[:60]+"...",fg=ACCENT,bg=BG_PANEL,font=("Segoe UI",9),
                    wraplength=600,justify="left",anchor="w",cursor="hand2")
                link_lbl.pack(side="left",padx=6)
                # 绑定 Ctrl+点击事件
                link_lbl.bind("<Control-Button-1>",lambda e,url=img_url:webbrowser.open(url))
        else:
            tk.Label(self.df,text="暂无主页图片数据",font=("Segoe UI",10),fg=TEXT_SUB,bg=BG_PANEL).pack(anchor="w",padx=24,pady=4)

    def _load_img(self,url):
        img=download_image(url)
        if img:
            img.thumbnail((220,220),Image.LANCZOS)
            ph=ImageTk.PhotoImage(img)
            self.after(0,lambda p=ph:self._set_img(p))

    def _set_img(self,photo):
        self._photo_ref=photo
        if hasattr(self,"img_lbl"): self.img_lbl.config(image=photo,text="")

    def _pub_log(self, msg):
        """发布日志回调，可在子线程中安全调用。同时保存到日志文件。"""
        m = str(msg)[:100] if msg else ""
        # 写入日志文件
        self._write_log(msg)
        # 更新状态栏
        if hasattr(self, "status_lbl"):
            self.after(0, lambda m=m: self.status_lbl.config(text=m))
  

    def _publish_worker(self,asins):
        pub = self._shein_publisher
        success_list = []
        fail_list = []
        total = len(asins)
        self._stop_publish = False  # 确保开始时标志为 False
        for i,asin in enumerate(asins):
            # 检查停止标志
            if self._stop_publish:
                self._pub_log("上品已停止，共完成 {}/{}".format(i, total))
                break
            info = self.product_cache.get(asin,{})
            cat_result = auto_match_category(info)
            cat_name = cat_result["name"]
            cat_path = cat_result["path"]  # e.g. ["女装", "连衣裙", "迷你裙"]
            self.after(0, lambda m="上品中 {}/{}：{} [{}]".format(
                i+1, total, asin, " > ".join(cat_path) if cat_path else cat_name): self.status_lbl.config(text=m))
            try:
                result = pub.publish_product(info, cat_path if cat_path else [cat_name])
                if result:
                    success_list.append(asin)
                    dot = self.asin_dots.get(asin)
                    if dot: self.after(0, lambda d=dot: d.config(fg="#00ffcc"))
                    self._pub_log("[OK {}/{}] {} -> {} 上品成功".format(
                        len(success_list), total, asin, " > ".join(cat_path) if cat_path else cat_name))
                else:
                    raise Exception("发布流程未能确认成功")
            except Exception as e:
                fail_list.append((asin, str(e)))
                self._pub_log("[FAIL {}/{}] {} 失败: {}".format(
                    len(fail_list), total, asin, e))
                dot = self.asin_dots.get(asin)
                if dot: self.after(0, lambda d=dot: d.config(fg=RED))
            time.sleep(random.uniform(2, 4))
        self.after(0, lambda: self._publish_done(success_list, fail_list))

    def _publish_done(self, success_list, fail_list):
        self.progress.stop()
        self._stop_publish = False  # 重置停止标志，允许再次上品
        total = len(success_list) + len(fail_list)
        msg = "上品完成！\n\n成功：{} 个\n失败：{} 个\n共计：{} 个".format(
            len(success_list), len(fail_list), total)
        if fail_list:
            msg += "\n\n失败列表：\n"
            msg += "\n".join("  {} - {}".format(a, e[:40]) for a,e in fail_list[:10])
            if len(fail_list) > 10:
                msg += "\n  ...(共 {} 个失败)".format(len(fail_list))
        self.status_lbl.config(text="上品完成 成功:{} 失败:{}".format(
            len(success_list), len(fail_list)))
        messagebox.showinfo("上品结果", msg)

    def _stop_publish_action(self):
        """停止上品进程。"""
        if not self._stop_publish:
            self._stop_publish = True
            self.progress.stop()
            self.status_lbl.config(text="正在停止上品，等待当前商品处理完毕...")
            messagebox.showinfo("停止上品",
                "已发送停止信号。\n"
                "当前商品处理完毕后将停止，\n"
                "再次点击【开始上品】可重新开始。")
        else:
            messagebox.showinfo("提示", "上品已经停止，可点击【开始上品】重新开始。")



# ── 品类选择对话框 ──────────────────────────
class CategoryDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("选择上品品类"); self.configure(bg=BG_PANEL)
        self.resizable(False, False); self.result = None
        self.grab_set(); self.transient(parent)
        # 从 JSON 加载分类名（取一、二级）
        self.CATEGORIES = self._load_categories()
        self._build(); self.geometry("360x520")

    @staticmethod
    def _load_categories():
        cats = []
        for top in SHEIN_CATEGORIES:
            cats.append(top["name"])
            for child in top.get("children", []):
                cats.append("  {} > {}".format(top["name"], child["name"]))
        if not cats:
            cats = ["女装","男装","童装","鞋靴","包袋","配饰",
                    "内衣睡衣","运动户外","美妆个护","家居生活",
                    "电子数码","宠物用品","其他"]
        return cats

    def _build(self):
        tk.Label(self, text="请选择商品品类", font=("Segoe UI", 13, "bold"),
                 fg=TEXT_MAIN, bg=BG_PANEL).pack(pady=(20, 4))
        tk.Label(self, text="将用于 SHEIN 后台分类选择",
                 font=("Segoe UI", 9), fg=TEXT_SUB, bg=BG_PANEL).pack(pady=(0, 10))
        self.var = tk.StringVar(value=self.CATEGORIES[0] if self.CATEGORIES else "")
        # 滚动列表
        frame = tk.Frame(self, bg=BG_PANEL); frame.pack(fill="both", expand=True, padx=24)
        canvas = tk.Canvas(frame, bg=BG_PANEL, highlightthickness=0)
        sb = ttk.Scrollbar(frame, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(canvas, bg=BG_PANEL)
        canvas.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        for cat in self.CATEGORIES:
            tk.Radiobutton(inner, text=cat, variable=self.var, value=cat,
                bg=BG_PANEL, fg=TEXT_MAIN, selectcolor=BG_DARK,
                activebackground=BG_PANEL, activeforeground=ACCENT2,
                font=("Segoe UI", 10), cursor="hand2", anchor="w").pack(
                fill="x", pady=1)
        tk.Label(self, text="或手动输入品类：", font=("Segoe UI", 9),
                 fg=TEXT_SUB, bg=BG_PANEL).pack(anchor="w", padx=24)
        self.custom = tk.StringVar()
        tk.Entry(self, textvariable=self.custom, bg=BG_CARD, fg=TEXT_MAIN,
                 insertbackground=TEXT_MAIN, font=("Segoe UI", 10),
                 relief="flat").pack(fill="x", padx=24, pady=(2, 12))
        bf = tk.Frame(self, bg=BG_PANEL); bf.pack(pady=(0, 16))
        tk.Button(bf, text="确认", bg=ACCENT, fg="white", font=("Segoe UI", 10, "bold"),
                  relief="flat", padx=20, pady=6, cursor="hand2",
                  command=self._ok).pack(side="left", padx=8)
        tk.Button(bf, text="取消", bg=BG_CARD, fg=TEXT_MAIN, font=("Segoe UI", 10),
                  relief="flat", padx=20, pady=6, cursor="hand2",
                  command=self.destroy).pack(side="left", padx=8)

    def _ok(self):
        c = self.custom.get().strip()
        self.result = c if c else self.var.get().strip()
        self.destroy()


# ── SHEIN 自动上品核心类 ────────────────────
class SheinPublisher:
    HOME_URL    = "https://sso.geiwohuo.com/#/home"
    LOGIN_URL   = "https://sso.geiwohuo.com/#/login"
    PUBLISH_URL = "https://sso.geiwohuo.com/#/spmc/commodities-category/followsales-pro/list?externalSystem=spmp"
    DEBUG_PORT  = 9222  # Chrome 远程调试端口

    def __init__(self, log_cb=None):
        self.driver = None
        self.wait   = None
        self.log    = log_cb or print

    def _connect_chrome_only(self):
        """只尝试连接已打开的 Chrome，不启动新浏览器。"""
        self.log("[DEBUG] 尝试连接已打开的 Chrome (1s超时)...")
        import threading as _th
        _conn_result = [None]
        _error = [None]
        
        def _try_connect():
            try:
                _o = Options()
                _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(self.DEBUG_PORT))
                _d = webdriver.Chrome(options=_o)
                _d.current_url
                _conn_result[0] = _d
            except Exception as e:
                _error[0] = str(e)[:60]
        
        _conn_thread = _th.Thread(target=_try_connect, daemon=True)
        _conn_thread.start()
        _conn_thread.join(timeout=1)  # 最多等1秒
        
        if _conn_result[0] is not None:
            self.driver = _conn_result[0]
            self.wait = WebDriverWait(self.driver, 20)
            self.log("[OK] 已连接到 Chrome")
            return True
        else:
            if _error[0]:
                self.log("[DEBUG] 连接失败: {}".format(_error[0]))
            else:
                self.log("[DEBUG] 连接超时")
            raise RuntimeError("无法连接到 Chrome 浏览器")

    def start_chrome_browser(self):
        """启动 Chrome 浏览器（用调试模式，保存用户数据）。"""
        import shutil as _shutil
        self.log("[DEBUG] 启动 Chrome 浏览器...")
        
        # 查找 chromedriver
        _candidates = []
        _path_driver = _shutil.which("chromedriver")
        if _path_driver:
            self.log("[DEBUG] 找到 PATH chromedriver")
            _candidates.append(_path_driver)
        
        _candidates += [
            r"C:\chromedriver\chromedriver.exe",
            r"D:\Work\Project\Python\Shein上品软件\工具\chromedriver-win64\chromedriver.exe",
        ]
        
        # 设置用户数据目录（保存登录信息、cookies 等）
        user_data_dir = os.path.join(os.path.expanduser("~"), ".shein_chrome_profile")
        os.makedirs(user_data_dir, exist_ok=True)
        
        opts = Options()
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--mute-audio")
        opts.add_argument("--remote-debugging-port={}".format(self.DEBUG_PORT))
        opts.add_argument("--user-data-dir={}".format(user_data_dir))
        opts.add_experimental_option("excludeSwitches", ["enable-automation"])
        opts.add_experimental_option("useAutomationExtension", False)
        
        for _cp in [p for p in _candidates if os.path.isfile(p)]:
            try:
                self.log("[DEBUG] 使用 chromedriver: {}".format(os.path.basename(_cp)))
                self.driver = webdriver.Chrome(service=Service(_cp), options=opts)
                self.wait = WebDriverWait(self.driver, 20)
                self.log("[OK] Chrome 启动成功")
                return
            except Exception as e:
                self.log("[DEBUG] 启动失败: {}".format(str(e)[:60]))
        
        # 如果找不到驱动，尝试用默认方式启动
        try:
            self.log("[DEBUG] 尝试用默认方式启动 Chrome (30s超时)...")
            import threading as _th
            _result = [None]
            _error = [None]
            
            def _start_default():
                try:
                    _result[0] = webdriver.Chrome(options=opts)
                except Exception as e:
                    _error[0] = str(e)
            
            _thread = _th.Thread(target=_start_default, daemon=True)
            _thread.start()
            _thread.join(timeout=30)
            
            if _result[0] is not None:
                self.driver = _result[0]
                self.wait = WebDriverWait(self.driver, 20)
                self.log("[OK] Chrome 启动成功")
                return
            elif _error[0]:
                raise RuntimeError("启动失败: {}".format(_error[0][:100]))
            else:
                raise RuntimeError("启动超时（30秒）。请确保已安装 Chrome 浏览器和 chromedriver")
        except Exception as e:
            raise RuntimeError("无法启动 Chrome: {}".format(str(e)[:100]))

    # ── 尝试连接已存在的 Chrome 实例
    def try_connect_existing(self):
        """尝试连接已在运行的 Chrome 实例（通过 debugging port）。"""
        try:
            opts = Options()
            opts.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(self.DEBUG_PORT))
            self.driver = webdriver.Chrome(options=opts)
            self.wait = WebDriverWait(self.driver, 20)
            self.log("已连接到现有 Chrome 实例")
            return True
        except Exception:
            return False

    # ── 查找本地已缓存的 chromedriver（跳过联网检查）
    def start_browser(self):
        """启动浏览器。优先用 Edge，其次用 Chrome。"""
        import glob as _glob
        import shutil as _shutil
        _t0 = time.time()

        # 策略0：连接已有 Edge 调试端口（秒级，超时0.5秒跳过）
        self.log("[DEBUG] 尝试连接已有 Edge (0.5s超时)...")
        import threading as _th
        _conn_result = [None]
        def _try_connect():
            try:
                _o = EdgeOptions()
                _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(self.DEBUG_PORT))
                _d = webdriver.Edge(options=_o)
                _d.current_url
                _conn_result[0] = _d
            except Exception as _e:
                self.log("[DEBUG] Edge 连接失败: {}".format(str(_e)[:40]))
        _conn_thread = _th.Thread(target=_try_connect, daemon=True)
        _conn_thread.start()
        _conn_thread.join(timeout=0.5)
        if _conn_result[0] is not None:
            self.driver = _conn_result[0]
            self.wait = WebDriverWait(self.driver, 20)
            _t1 = time.time()
            self.log("[OK] 已连接到现有 Edge ({:.1f}s)".format(_t1 - _t0))
            return
        else:
            self.log("[DEBUG] Edge 连接超时或失败，启动新 Edge...")

        # Edge 选项
        opts = EdgeOptions()
        opts.add_argument("--disable-blink-features=AutomationControlled")
        opts.add_argument("--no-sandbox")
        opts.add_argument("--disable-dev-shm-usage")
        opts.add_argument("--disable-gpu")
        opts.add_argument("--disable-extensions")
        opts.add_argument("--no-first-run")
        opts.add_argument("--disable-translate")
        opts.add_argument("--mute-audio")
        opts.add_argument("--password-store=basic")
        opts.add_argument("--disable-background-networking")
        opts.add_argument("--disk-cache-size=0")
        opts.add_argument("--media-cache-size=0")
        opts.add_argument("--disable-application-cache")
        opts.add_argument("--disable-infobars")
        opts.add_argument("--disable-notifications")
        opts.add_argument("--remote-debugging-port={}".format(self.DEBUG_PORT))
        opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        opts.add_experimental_option("useAutomationExtension", False)

        import tempfile as _tmp
        _profile = os.path.join(_tmp.gettempdir(), ".shein_edge")
        os.makedirs(_profile, exist_ok=True)
        opts.add_argument("--user-data-dir={}".format(_profile))

        def _cdp_hide_webdriver(drv):
            try:
                drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                    """
                })
            except Exception:
                pass

        # 查找本地 Edge 驱动
        _candidates = []
        self.log("[DEBUG] 查找本地 Edge 驱动...")
        _path_driver = _shutil.which("msedgedriver")
        if _path_driver:
            self.log("[DEBUG] 找到 PATH msedgedriver: {}".format(_path_driver))
            _candidates.append(_path_driver)
        
        _candidates += [
            r"C:\msedgedriver\msedgedriver.exe",
            r"C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe",
        ]

        for _cp in [p for p in _candidates if os.path.isfile(p)]:
            try:
                self.log("[DEBUG] 尝试 Edge 驱动: {}".format(os.path.basename(_cp)))
                _t_start = time.time()
                self.driver = webdriver.Edge(service=EdgeService(_cp), options=opts)
                _t_end = time.time()
                self.log("[OK] 使用 Edge 驱动 ({:.1f}s)".format(_t_end - _t_start))
                self.wait = WebDriverWait(self.driver, 20)
                _cdp_hide_webdriver(self.driver)
                _t_total = time.time()
                self.log("[TOTAL] Edge 启动完成 ({:.1f}s)".format(_t_total - _t0))
                return
            except Exception as _e:
                self.log("[DEBUG] Edge 驱动失败: {}".format(str(_e)[:60]))
                self.driver = None

        # 如果 Edge 都失败，尝试 Chrome
        self.log("[DEBUG] Edge 失败，尝试 Chrome...")
        try:
            self.driver = webdriver.Chrome(options=Options())
            self.wait = WebDriverWait(self.driver, 20)
            _cdp_hide_webdriver(self.driver)
            self.log("[OK] 使用 Chrome 启动")
            return
        except Exception as _e:
            raise RuntimeError(
                "无法启动浏览器！\n\n"
                "请确保已安装 Microsoft Edge 或 Google Chrome\n\n"
                "错误: {}".format(str(_e)[:100])
            )

    def open_login(self):
        self.driver.get(self.LOGIN_URL)

    def goto_publish_page(self):
        """
        从 SHEIN 首页导航到「商品」->「商品发布」页面。
        返回 True 表示成功，False 表示失败。
        """
        driver = self.driver
        HOME_URL = "https://www.geiwohuo.com/#/oversea-home"
        PUBLISH_URL = "https://sso.geiwohuo.com/#/spmc/commodities-category/followsales-pro/list?externalSystem=spmp"

        self.log("导航到首页...")
        driver.get(HOME_URL)
        time.sleep(5)

        def _click_text(text, timeout=10):
            """在页面中查找包含指定文字的元素并点击。"""
            tags = ["span", "a", "li", "div", "button", "p"]
            end = time.time() + timeout
            while time.time() < end:
                for tag in tags:
                    for el in driver.find_elements(By.TAG_NAME, tag):
                        try:
                            t = el.text.strip()
                            if t == text and el.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                                time.sleep(0.3)
                                driver.execute_script("arguments[0].click();", el)
                                self.log(f"已点击「{text}」")
                                return True
                        except Exception:
                            continue
                # 也尝试 XPath 含包匹配
                for xp in [
                    f"//*[normalize-space(text())='{text}']",
                    f"//*[contains(text(),'{text}')]",
                ]:
                    try:
                        els = driver.find_elements(By.XPATH, xp)
                        for el in els:
                            if el.is_displayed():
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                                time.sleep(0.3)
                                driver.execute_script("arguments[0].click();", el)
                                self.log(f"已点击「{text}」 (xpath)")
                                return True
                    except Exception:
                        continue
                time.sleep(1)
            return False

        original_handles = set(driver.window_handles)

        # 策略1：直接导航到商品发布 URL
        self.log("尝试直接导航到商品发布页...")
        try:
            driver.get(PUBLISH_URL)
            time.sleep(3)
            cur = driver.current_url
            if "spmc" in cur or "followsales" in cur or "commodities" in cur:
                self.log("已直接打开商品发布页")
                return True
        except Exception as e:
            self.log(f"直接导航失败: {e}")

        # 策略2：回到首页，点击菜单
        self.log("导航到首页并点击菜单...")
        driver.get(HOME_URL)
        time.sleep(4)

        if not _click_text("商品", timeout=10):
            self.log("未找到「商品」菜单")
            # 最后参考：直接打开 URL
            driver.get(PUBLISH_URL)
            time.sleep(2)
            return True
        time.sleep(2)

        if not _click_text("商品发布", timeout=8):
            self.log("未找到「商品发布」子菜单")
            driver.get(PUBLISH_URL)
            time.sleep(2)
            return True

        # 等待新窗口或页面跳转
        for _ in range(20):
            time.sleep(0.5)
            new_handles = set(driver.window_handles)
            if new_handles - original_handles:
                driver.switch_to.window((new_handles - original_handles).pop())
                self.log("已切换到商品发布页面")
                time.sleep(2)
                return True
        return True

    def is_alive(self):
        """检测浏览器是否还在运行。"""
        try:
            _ = self.driver.current_url
            return True
        except Exception:
            return False

    def upload_image_by_path(self, image_path):
        """
        上传图片到商品发布页面。
        需要用户已在浏览器中打开商品发布页面。
        """
        if not os.path.isfile(image_path):
            self.log("图片文件不存在: {}".format(image_path))
            return False
        try:
            # 查找"识图发品"按钮
            self.log("查找'识图发品'按钮...")
            for el in self.driver.find_elements(By.TAG_NAME, "button"):
                if "识图" in el.text or "发品" in el.text:
                    self.log("找到按钮: {}".format(el.text))
                    el.click()
                    time.sleep(2)
                    break
            # 查找文件上传输入框
            self.log("查找文件上传框...")
            file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            if file_inputs:
                file_inputs[0].send_keys(os.path.abspath(image_path))
                self.log("已上传图片: {}".format(image_path))
                time.sleep(2)
                return True
            else:
                self.log("未找到文件上传框")
                return False
        except Exception as e:
            self.log("上传失败: {}".format(str(e)))
            return False

    def get_product_images(self, asin):
        """获取指定 ASIN 商品的所有图片路径。"""
        # 这里需要根据你的图片存储方式来实现
        # 假设图片存储在 ./images/{asin}/ 目录下
        image_dir = os.path.join(os.path.dirname(__file__), "images", asin)
        if os.path.isdir(image_dir):
            images = [os.path.join(image_dir, f) for f in os.listdir(image_dir) 
                     if f.lower().endswith(('.jpg', '.jpeg', '.png', '.gif'))]
            return sorted(images)
        return []

    def ensure_alive(self):
        """如果浏览器已关闭，自动重新启动。"""
        if self.driver is None or not self.is_alive():
            self.log("浏览器已关闭，正在重新启动...")
            self.start_browser()
            return False  # 表示重新启动了
        return True  # 表示已经在运行

    def is_logged_in(self):
        """检测当前是否已登录。"""
        try:
            url = self.driver.current_url
            # 在登录页 = 未登录
            if "/#/login" in url or url.rstrip("/").endswith("#/login"):
                return False
            # 在 sso.geiwohuo.com 且不是登录页 = 已登录
            if "sso.geiwohuo.com" in url and "login" not in url.lower():
                return True
            return False
        except Exception:
            return False
        except Exception:
            return False

    def wait_for_login(self, timeout=60):
        """检测当前 URL 是否已离开登录页。"""
        end = time.time() + timeout
        while time.time() < end:
            try:
                url = self.driver.current_url
                if "sso.geiwohuo.com" in url and "login" not in url.lower():
                    time.sleep(2)
                    return True
            except Exception:
                pass
            time.sleep(1)
        # 超时后再检查一次
        try:
            url = self.driver.current_url
            if "sso.geiwohuo.com" in url and "login" not in url.lower():
                return True
        except Exception:
            pass
        return False

    def dump_page_elements(self):
        """
        抓取当前页面的所有元素信息，重点抓取推荐类目。
        进入时先关闭公告弹窗，避免公告内容混入抓取结果。
        同时保存完整的页面HTML代码到桌面，便于调试。
        """
        try:
            # 先关闭公告弹窗，确保抓取的是业务页面内容
            self._dismiss_announcements()
            time.sleep(0.5)

            elements_info = []

            # 抓取所有按钮
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            elements_info.append("=== 页面按钮 ===")
            for i, btn in enumerate(buttons):
                try:
                    text = btn.text.strip()
                    if text:
                        elements_info.append(f"按钮 {i}: {text}")
                except Exception:
                    pass
            
            # 抓取所有包含"推荐"的元素及其子元素
            elements_info.append("\n=== 推荐类目详细信息 ===")
            for el in self.driver.find_elements(By.XPATH, "//*[contains(text(), '推荐')]"):
                try:
                    text = el.text.strip()
                    tag = el.tag_name
                    elements_info.append(f"{tag}: {text}")
                    # 获取父元素的所有文本
                    parent = el.find_element(By.XPATH, "..")
                    parent_text = parent.text.strip()
                    if parent_text and parent_text != text:
                        elements_info.append(f"  └─ 父元素: {parent_text[:200]}")
                except Exception:
                    pass
            
            # 抓取所有 span 元素（可能包含类目名称）
            elements_info.append("\n=== 所有 SPAN 元素 ===")
            spans = self.driver.find_elements(By.TAG_NAME, "span")
            for i, span in enumerate(spans):
                try:
                    text = span.text.strip()
                    if text and len(text) < 100:
                        elements_info.append(f"span {i}: {text}")
                except Exception:
                    pass
            
            # 抓取所有 p 元素
            elements_info.append("\n=== 所有 P 元素 ===")
            ps = self.driver.find_elements(By.TAG_NAME, "p")
            for i, p in enumerate(ps):
                try:
                    text = p.text.strip()
                    if text:
                        elements_info.append(f"p {i}: {text}")
                except Exception:
                    pass
            
            # 抓取所有 a 元素（可能是可点击的类目）
            elements_info.append("\n=== 所有 A 元素 ===")
            links = self.driver.find_elements(By.TAG_NAME, "a")
            for i, link in enumerate(links):
                try:
                    text = link.text.strip()
                    if text and len(text) < 100:
                        elements_info.append(f"a {i}: {text}")
                except Exception:
                    pass
            
            # 抓取所有 div 元素（重点抓取包含数字或中文的）
            elements_info.append("\n=== 所有 DIV 元素（包含中文或数字） ===")
            divs = self.driver.find_elements(By.TAG_NAME, "div")
            for i, div in enumerate(divs):
                try:
                    text = div.text.strip()
                    # 只显示包含中文或数字的短文本
                    if text and 5 < len(text) < 150 and any('\u4e00' <= c <= '\u9fff' or c.isdigit() for c in text):
                        elements_info.append(f"div {i}: {text}")
                except Exception:
                    pass
            
            info_text = "\n".join(elements_info)
            self.log(info_text)
            
            # ===== 新增：保存完整的页面HTML代码到桌面 =====
            try:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                os.makedirs(desktop, exist_ok=True)
                
                # 获取完整的页面HTML
                page_html = self.driver.page_source
                
                # 保存HTML文件
                html_file = os.path.join(desktop, "shein_page_debug.html")
                with open(html_file, "w", encoding="utf-8") as f:
                    f.write(page_html)
                self.log("[OK] 页面HTML已保存到: {}".format(html_file))
                
                # 同时保存一个简化版本，只包含关键部分（细节图、点击上传等）
                simplified_html = []
                simplified_html.append("<html><head><meta charset='utf-8'></head><body>")
                simplified_html.append("<h2>关键元素搜索结果</h2>")
                
                # 查找所有包含"细节图"的元素
                simplified_html.append("<h3>包含'细节图'的元素：</h3><pre>")
                for el in self.driver.find_elements(By.XPATH, "//*[contains(text(), '细节图')]"):
                    try:
                        tag = el.tag_name
                        text = el.text.strip()[:100]
                        cls = el.get_attribute("class") or ""
                        simplified_html.append(f"&lt;{tag} class='{cls}'&gt;{text}&lt;/{tag}&gt;\n")
                    except Exception:
                        pass
                simplified_html.append("</pre>")
                
                # 查找所有包含"点击上传"的元素
                simplified_html.append("<h3>包含'点击上传'的元素：</h3><pre>")
                for el in self.driver.find_elements(By.XPATH, "//*[contains(text(), '点击上传')]"):
                    try:
                        tag = el.tag_name
                        text = el.text.strip()[:100]
                        cls = el.get_attribute("class") or ""
                        simplified_html.append(f"&lt;{tag} class='{cls}'&gt;{text}&lt;/{tag}&gt;\n")
                    except Exception:
                        pass
                simplified_html.append("</pre>")
                
                # 查找所有 file input
                simplified_html.append("<h3>所有 file input 元素：</h3><pre>")
                for inp in self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']"):
                    try:
                        cls = inp.get_attribute("class") or ""
                        name = inp.get_attribute("name") or ""
                        simplified_html.append(f"&lt;input type='file' name='{name}' class='{cls}' /&gt;\n")
                    except Exception:
                        pass
                simplified_html.append("</pre>")
                
                simplified_html.append("</body></html>")
                
                # 保存简化版HTML
                simplified_file = os.path.join(desktop, "shein_page_debug_simplified.html")
                with open(simplified_file, "w", encoding="utf-8") as f:
                    f.write("\n".join(simplified_html))
                self.log("[OK] 简化版HTML已保存到: {}".format(simplified_file))
            except Exception as e:
                self.log("[DEBUG] 保存HTML失败: {}".format(str(e)[:60]))
            
            return info_text
        except Exception as e:
            self.log("抓取页面信息失败: {}".format(str(e)))
            return ""

    def click_identify_image_button(self):
        """点击'识图发品'按钮。"""
        try:
            self.log("[DEBUG] 查找'识图发品'按钮...")
            time.sleep(2)  # 等待页面加载
            
            # 方法1：查找包含"识图"的 div 或 button
            for el in self.driver.find_elements(By.XPATH, "//*[contains(text(), '识图')]"):
                try:
                    text = el.text.strip()
                    if "识图" in text:
                        self.log("[DEBUG] 找到识图元素: {}".format(text))
                        # 尝试点击这个元素
                        try:
                            el.click()
                            self.log("[OK] 已点击'识图发品'按钮")
                            time.sleep(2)
                            return True
                        except Exception:
                            # 尝试点击父元素
                            try:
                                parent = el.find_element(By.XPATH, "..")
                                parent.click()
                                self.log("[OK] 已点击'识图发品'按钮（父元素）")
                                time.sleep(2)
                                return True
                            except Exception:
                                continue
                except Exception as e:
                    self.log("[DEBUG] 处理识图元素失败: {}".format(str(e)[:40]))
                    continue
            
            # 方法2：查找所有 span 元素，找包含"识图"的
            for span in self.driver.find_elements(By.TAG_NAME, "span"):
                try:
                    text = span.text.strip()
                    if "识图" in text:
                        self.log("[DEBUG] 找到识图 span: {}".format(text))
                        span.click()
                        self.log("[OK] 已点击'识图发品'按钮")
                        time.sleep(2)
                        return True
                except Exception:
                    continue
            
            # 方法3：查找所有 div 元素，找包含"识图"的
            for div in self.driver.find_elements(By.TAG_NAME, "div"):
                try:
                    text = div.text.strip()
                    if text == "识图发品":
                        self.log("[DEBUG] 找到识图发品 div")
                        div.click()
                        self.log("[OK] 已点击'识图发品'按钮")
                        time.sleep(2)
                        return True
                except Exception:
                    continue
            
            self.log("[ERROR] 未找到'识图发品'按钮")
            return False
        except Exception as e:
            self.log("[ERROR] 点击按钮失败: {}".format(str(e)))
            return False


    def _handle_crop_dialog(self):
        """
        处理"图片裁剪"弹框（基于真实页面HTML）:
          弹框标题: 图片裁剪 (class: so-card-header so-modal-title)
          1:1 radio label: so-checkinput-radio-container > span.so-checkinput-desc 文字为"1:1"
          确认裁剪按钒: class 含 cropBtn, span 文字为"确认裁剪"
        返回 True 成功处理，False 未出现弹框或处理失败。
        """
        driver = self.driver

        def _is_crop_dialog_visible():
            try:
                for el in driver.find_elements(
                        By.XPATH,
                        "//div[contains(@class,'so-modal-title') and normalize-space(text())='图片裁剪']"):
                    if el.is_displayed():
                        return True
                for el in driver.find_elements(
                        By.XPATH, "//div[contains(@class,'so-modal-show')]"):
                    if el.is_displayed():
                        return True
            except Exception:
                pass
            return False

        def _select_ratio_1_1():
            # 方法1: JS直接操作
            js = """
            var labels = document.querySelectorAll('label.so-checkinput-radio-container');
            for (var i = 0; i < labels.length; i++) {
                var desc = labels[i].querySelector('.so-checkinput-desc');
                if (desc && desc.textContent.trim() === '1:1') {
                    var radio = labels[i].querySelector('input[type="radio"]');
                    if (radio && !radio.checked) {
                        labels[i].click();
                        radio.checked = true;
                        radio.dispatchEvent(new Event('change', {bubbles: true}));
                        radio.dispatchEvent(new MouseEvent('click', {bubbles: true}));
                    }
                    return true;
                }
            }
            return false;
            """
            try:
                if driver.execute_script(js):
                    return True
            except Exception:
                pass
            # 方法2: Selenium XPath
            xpaths = [
                "//label[contains(@class,'so-checkinput-radio-container') and .//span[contains(@class,'so-checkinput-desc') and normalize-space(text())='1:1']]",
                "//span[contains(@class,'so-checkinput-desc') and normalize-space(text())='1:1']/ancestor::label[1]",
                "//label[.//span[normalize-space(text())='1:1']]",
            ]
            for xp in xpaths:
                for label in driver.find_elements(By.XPATH, xp):
                    try:
                        if not label.is_displayed():
                            continue
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", label)
                        time.sleep(0.1)
                        driver.execute_script("arguments[0].click();", label)
                        try:
                            radio = label.find_element(By.XPATH, ".//input[@type='radio']")
                            driver.execute_script(
                                "arguments[0].checked=true;"
                                "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));"
                                "arguments[0].dispatchEvent(new MouseEvent('click',{bubbles:true}));",
                                radio)
                        except Exception:
                            pass
                        return True
                    except Exception:
                        continue
            return False

        def _click_confirm():
            # 方法1: JS匹配 cropBtn class
            js = """
            var btns = document.querySelectorAll('button');
            for (var i = 0; i < btns.length; i++) {
                var c = btns[i].className || '';
                var t = btns[i].textContent.trim();
                if ((c.indexOf('cropBtn') !== -1 || t === '确认裁剪') && !btns[i].disabled) {
                    btns[i].click();
                    return true;
                }
            }
            return false;
            """
            try:
                if driver.execute_script(js):
                    return True
            except Exception:
                pass
            # 方法2: Selenium XPath
            xpaths = [
                "//button[contains(@class,'cropBtn') and not(@disabled)]",
                "//div[contains(@class,'so-modal-show')]//button[contains(@class,'so-button-primary') and .//span[normalize-space(text())='确认裁剪'] and not(@disabled)]",
                "//button[.//span[normalize-space(text())='确认裁剪'] and not(@disabled)]",
                "//div[contains(@class,'so-modal-show')]//button[contains(@class,'so-button-primary') and not(@disabled)]",
            ]
            for xp in xpaths:
                for btn in driver.find_elements(By.XPATH, xp):
                    try:
                        if not btn.is_displayed():
                            continue
                        driver.execute_script(
                            "arguments[0].scrollIntoView({block:'center'});", btn)
                        time.sleep(0.1)
                        driver.execute_script("arguments[0].click();", btn)
                        return True
                    except Exception:
                        continue
            return False

        try:
            # Step0: 等待弹框出现（8秒）
            self.log("[DEBUG] 等待图片裁剪弹框...")
            deadline = time.time() + 8
            while time.time() < deadline:
                if _is_crop_dialog_visible():
                    self.log("[OK] 检测到图片裁剪弹框")
                    break
                time.sleep(0.4)
            else:
                self.log("[DEBUG] 未检测到裁剪弹框，跳过")
                return False

            time.sleep(0.3)

            # Step1: 选择 1:1 裁剪比例
            if _select_ratio_1_1():
                self.log("[OK] 已选择 1:1 裁剪比例")
                time.sleep(0.5)
            else:
                self.log("[WARN] 未找到 1:1 比例选项，继续点击确认...")

            # Step2: 点击确认裁剪
            if _click_confirm():
                self.log("[OK] 已点击确认裁剪")
                time.sleep(2)
            else:
                self.log("[ERROR] 未能点击确认裁剪按钒")
                return False

            # Step3: 等待弹框关闭
            self.log("[DEBUG] 等待裁剪弹框关闭...")
            deadline2 = time.time() + 10
            while time.time() < deadline2:
                if not _is_crop_dialog_visible():
                    self.log("[OK] 裁剪弹框已关闭")
                    break
                time.sleep(0.4)

            return True

        except Exception as e:
            self.log("[ERROR] 处理裁剪弹框失败: {}".format(str(e)[:80]))
            return False

    def upload_product_image(self, image_path):
        """上传商品图片到'识图发品'页面。"""
        if not os.path.isfile(image_path):
            self.log("[ERROR] 图片文件不存在: {}".format(image_path))
            return False
        
        try:
            self.log("[DEBUG] 查找文件上传框...")
            file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            
            if not file_inputs:
                self.log("[ERROR] 未找到文件上传框")
                return False
            
            # 使用第一个文件上传框
            file_input = file_inputs[0]
            abs_path = os.path.abspath(image_path)
            
            self.log("[DEBUG] 上传图片: {}".format(os.path.basename(image_path)))
            file_input.send_keys(abs_path)
            
            # 上传后处理裁剪弹框
            self.log("[DEBUG] 检测是否有裁剪弹框...")
            self._handle_crop_dialog()

            # 等待上传完成
            time.sleep(2)
            self.log("[OK] 图片已上传: {}".format(os.path.basename(image_path)))
            return True
        except Exception as e:
            self.log("[ERROR] 上传失败: {}".format(str(e)[:60]))
            return False

    def select_first_category(self):
        """选择第一个推荐类目。"""
        try:
            self.log("[DEBUG] 查找推荐类目...")
            
            # 方法1：查找所有包含"/"的 span（推荐类目格式）
            category_spans = self.driver.find_elements(By.XPATH, "//span[contains(text(), '/')]")
            
            if category_spans:
                for span in category_spans:
                    try:
                        text = span.text.strip()
                        # 确保是推荐类目格式（包含多个"/"）
                        if text.count('/') >= 3:
                            self.log("[DEBUG] 找到第一个推荐类目: {}".format(text))
                            span.click()
                            self.log("[OK] 已选择第一个推荐类目")
                            time.sleep(1)
                            return True
                    except Exception as e:
                        self.log("[DEBUG] 点击 span 失败: {}".format(str(e)[:40]))
                        continue
            
            # 方法2：查找所有包含"/"的 div（推荐类目格式）
            category_divs = self.driver.find_elements(By.XPATH, "//div[contains(text(), '/')]")
            
            if category_divs:
                for div in category_divs:
                    try:
                        text = div.text.strip()
                        # 确保是推荐类目格式（包含多个"/"）
                        if text.count('/') >= 3:
                            self.log("[DEBUG] 找到第一个推荐类目: {}".format(text))
                            div.click()
                            self.log("[OK] 已选择第一个推荐类目")
                            time.sleep(1)
                            return True
                    except Exception as e:
                        self.log("[DEBUG] 点击 div 失败: {}".format(str(e)[:40]))
                        continue
            
            self.log("[ERROR] 未找到推荐类目（span 和 div 都没找到）")
            return False
        except Exception as e:
            self.log("[ERROR] 选择类目失败: {}".format(str(e)[:60]))
            return False

    def click_confirm_button(self):
        """点击'确认，下一步'按钮。"""
        try:
            self.log("[DEBUG] 查找'确认，下一步'按钮...")
            buttons = self.driver.find_elements(By.TAG_NAME, "button")
            
            for btn in buttons:
                try:
                    text = btn.text.strip()
                    if "确认" in text and "下一步" in text:
                        self.log("[DEBUG] 找到'确认，下一步'按钮")
                        btn.click()
                        self.log("[OK] 已点击'确认，下一步'按钮")
                        time.sleep(2)
                        return True
                except Exception:
                    continue
            
            self.log("[ERROR] 未找到'确认，下一步'按钮")
            return False
        except Exception as e:
            self.log("[ERROR] 点击按钮失败: {}".format(str(e)[:60]))
            return False

    def fill_product_info(self, product_info):
        """填写商品基础信息到 SHEIN 发布页面。"""
        try:
            self.log("[DEBUG] 开始填写商品基础信息...")
            
            # 1. 填写商品标题(英语)
            self.log("[DEBUG] 填写商品标题(英语)...")
            title = product_info.get("title", "")
            if title:
                # 查找"商品标题(英语)"对应的输入框
                # 方法1：查找所有 input，找到在"商品标题(英语)" span 之后的
                try:
                    # 先找到"商品标题(英语)"的 span
                    title_spans = self.driver.find_elements(By.XPATH, "//span[contains(text(), '商品标题')]")
                    if title_spans:
                        # 找到最近的 input 元素
                        for span in title_spans:
                            try:
                                # 向上查找到 form 或 div，然后找 input
                                parent = span.find_element(By.XPATH, "./ancestor::div[contains(@class, 'form') or contains(@class, 'field')]")
                                inp = parent.find_element(By.TAG_NAME, "input")
                                inp.clear()
                                inp.send_keys(title)
                                self.log("[OK] 商品标题已填写: {}".format(title[:50]))
                                time.sleep(0.5)
                                break
                            except Exception:
                                continue
                except Exception as e:
                    self.log("[DEBUG] 方法1失败: {}".format(str(e)[:40]))
                
                # 方法2：查找所有 input，按顺序尝试
                if not title:  # 如果还没填写
                    try:
                        all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                        for inp in all_inputs:
                            try:
                                # 跳过已有值的输入框
                                if inp.get_attribute("value"):
                                    continue
                                # 尝试填写
                                inp.clear()
                                inp.send_keys(title)
                                self.log("[OK] 商品标题已填写: {}".format(title[:50]))
                                time.sleep(0.5)
                                break
                            except Exception:
                                continue
                    except Exception as e:
                        self.log("[DEBUG] 方法2失败: {}".format(str(e)[:40]))
            
            # 2. 填写商品描述
            self.log("[DEBUG] 填写商品描述...")
            description = product_info.get("description", "")
            if description:
                # 查找商品描述输入框（textarea）
                textareas = self.driver.find_elements(By.TAG_NAME, "textarea")
                if textareas:
                    try:
                        textareas[0].clear()
                        textareas[0].send_keys(description)
                        self.log("[OK] 商品描述已填写: {}".format(description[:50]))
                        time.sleep(0.5)
                    except Exception as e:
                        self.log("[DEBUG] 填写描述失败: {}".format(str(e)[:40]))
            
            # 3. 填写商品品牌
            self.log("[DEBUG] 填写商品品牌...")
            brand = product_info.get("brand", "").replace("访问 ", "").strip()
            if brand:
                # 查找品牌输入框
                try:
                    all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    for inp in all_inputs:
                        try:
                            placeholder = inp.get_attribute("placeholder")
                            if placeholder and "品牌" in placeholder:
                                inp.clear()
                                inp.send_keys(brand)
                                self.log("[OK] 商品品牌已填写: {}".format(brand))
                                time.sleep(0.5)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    self.log("[DEBUG] 填写品牌失败: {}".format(str(e)[:40]))
            
            # 4. 填写参考产品链接（ASIN链接）
            self.log("[DEBUG] 填写参考产品链接...")
            asin_url = product_info.get("url", "")
            if asin_url:
                # 查找产品链接输入框（在"参考产品链接"部分）
                try:
                    all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                    for inp in all_inputs:
                        try:
                            placeholder = inp.get_attribute("placeholder")
                            if placeholder and "链接" in placeholder:
                                inp.clear()
                                inp.send_keys(asin_url)
                                self.log("[OK] 参考产品链接已填写: {}".format(asin_url[:50]))
                                time.sleep(0.5)
                                break
                        except Exception:
                            continue
                except Exception as e:
                    self.log("[DEBUG] 填写链接失败: {}".format(str(e)[:40]))
            
            # 5. 填写货号（XYZ-{ASIN}）
            self.log("[DEBUG] 填写货号...")
            asin = product_info.get("asin", "")
            if asin:
                model_number = "XYZ-{}".format(asin)
                filled = False
                try:
                    # 方法1：查找"货号" span 的同级或相邻 input
                    for span in self.driver.find_elements(By.TAG_NAME, "span"):
                        try:
                            if span.text.strip() == "货号":
                                # 找到父元素，再找 input
                                parent = span.find_element(By.XPATH, "./..")
                                for _ in range(5):  # 最多向上5层
                                    try:
                                        inp = parent.find_element(By.TAG_NAME, "input")
                                        inp.clear()
                                        inp.send_keys(model_number)
                                        self.log("[OK] 货号已填写: {}".format(model_number))
                                        time.sleep(0.5)
                                        filled = True
                                        break
                                    except Exception:
                                        parent = parent.find_element(By.XPATH, "./..")
                                if filled:
                                    break
                        except Exception:
                            continue
                except Exception as e:
                    self.log("[DEBUG] 方法1填写货号失败: {}".format(str(e)[:40]))
                
                # 方法2：用 placeholder 查找
                if not filled:
                    try:
                        all_inputs = self.driver.find_elements(By.TAG_NAME, "input")
                        for inp in all_inputs:
                            try:
                                placeholder = inp.get_attribute("placeholder")
                                if placeholder and ("货号" in placeholder or "型号" in placeholder):
                                    inp.clear()
                                    inp.send_keys(model_number)
                                    self.log("[OK] 货号已填写(方法2): {}".format(model_number))
                                    time.sleep(0.5)
                                    filled = True
                                    break
                            except Exception:
                                continue
                    except Exception as e:
                        self.log("[DEBUG] 方法2填写货号失败: {}".format(str(e)[:40]))
                
                if not filled:
                    self.log("[ERROR] 未能填写货号")

            # 5.5 展开【商品描述】并填写产品特点
            self.log("[DEBUG] 填写商品描述(英文)...")
            features = product_info.get("features", [])
            desc_text = "\n".join(features) if features else product_info.get("description", "")
            if desc_text:
                try:
                    # 点击"展开添加【商品描述】"折叠按钮
                    collapse_xpaths = [
                        "//div[contains(@class,'soui-collapseItem-title') and contains(text(),'商品描述')]",
                        "//*[contains(@class,'soui-collapseItem-header') and .//*[contains(text(),'商品描述')] ]",
                        "//*[contains(text(),'展开添加') and contains(text(),'商品描述')]",
                        "//div[contains(@class,'cbg5ad') or contains(@class,'soui-collapseItem-header')]",
                    ]
                    expanded = False
                    for xp in collapse_xpaths:
                        try:
                            els = self.driver.find_elements(By.XPATH, xp)
                            for el in els:
                                if el.is_displayed():
                                    self.driver.execute_script(
                                        "arguments[0].scrollIntoView({block:'center'});", el)
                                    time.sleep(0.3)
                                    self.driver.execute_script("arguments[0].click();", el)
                                    self.log("[OK] 已展开商品描述区域")
                                    time.sleep(0.8)
                                    expanded = True
                                    break
                        except Exception:
                            pass
                        if expanded:
                            break
                    if not expanded:
                        self.log("[DEBUG] 未找到商品描述折叠按钮，尝试直接查找textarea")
                    # 找到展开后的textarea（class包含main_desc或multi_desc下的textarea）
                    desc_filled = False
                    desc_xpaths = [
                        "//div[contains(@class,'main_desc') or contains(@class,'multi_desc')]//textarea",
                        "//div[contains(@class,'soui-collapseItem-expanded')]//textarea",
                        "//div[contains(@class,'soui-collapseItem-content') and not(contains(@style,'display: none'))]//textarea",
                        "//textarea[contains(@placeholder,'5000')]",
                    ]
                    for xp in desc_xpaths:
                        try:
                            ta = WebDriverWait(self.driver, 5).until(
                                EC.presence_of_element_located((By.XPATH, xp)))
                            if ta.is_displayed():
                                self.driver.execute_script(
                                    "arguments[0].scrollIntoView({block:'center'});", ta)
                                ta.clear()
                                ta.send_keys(desc_text)
                                self.log("[OK] 商品描述(英文)已填写")
                                desc_filled = True
                                time.sleep(0.5)
                                break
                        except Exception:
                            pass
                    if not desc_filled:
                        self.log("[DEBUG] 未找到商品描述textarea，跳过")
                except Exception as e:
                    self.log("[DEBUG] 填写商品描述失败: {}".format(str(e)[:60]))

            # 6. 上传主规格图和细节图（非阻塞：失败不影响后续“规格及供应信息”流程）
            self.log("[DEBUG] 上传商品图片...")
            try:
                self._upload_product_images(product_info)
            except Exception as e:
                self.log("[DEBUG] 上传商品图片步骤异常，继续后续流程: {}".format(str(e)[:60]))
            
            self.log("[OK] 商品基础信息填写完成")
            return True
        except Exception as e:
            self.log("[ERROR] 填写基础信息失败: {}".format(str(e)[:60]))
            return False

    def fill_spec_and_supply_info(self, product_info):
        """填写'规格及供应信息'板块（价格、SKU、库存等）。"""
        try:
            self.log("[DEBUG] 开始填写规格及供应信息...")
            driver = self.driver

            # 等待规格板块出现（查找包含'规格'或'供应'的标题）
            spec_visible = False
            for _ in range(10):
                try:
                    els = driver.find_elements(By.XPATH,
                        "//*[contains(text(),'规格及供应') or contains(text(),'规格信息') or contains(text(),'供应信息')]")
                    if els:
                        spec_visible = True
                        self.log("[OK] 找到规格及供应信息板块")
                        break
                except Exception:
                    pass
                time.sleep(1)

            if not spec_visible:
                self.log("[DEBUG] 未检测到规格板块标题，继续尝试填写...")

            # 提取商品信息
            price_raw = product_info.get("price", "")
            asin = product_info.get("asin", "")
            main_images = product_info.get("main_images", [])

            # ── 解析价格（转为数字字符串，去掉货币符号）
            price_num = ""
            if price_raw and price_raw != "N/A":
                m = re.search(r"[\d]+\.?[\d]*", price_raw.replace(",", ""))
                if m:
                    price_num = m.group()

            # 步骤1: 向供应信息表格的「价格(USD)」列填写价格
            if price_num:
                self.log("[DEBUG] 填写价格(USD): {}".format(price_num))
                price_filled = False
                try:
                    # 主定位: HTML中确认的 supplier_priceClass_0
                    inp = driver.find_element(By.CSS_SELECTOR, ".supplier_priceClass_0 input")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
                    self._js_input(inp, price_num)
                    self.log("[OK] 价格(USD)已填写: {}".format(price_num))
                    price_filled = True
                    time.sleep(0.5)
                except Exception as e1:
                    self.log("[DEBUG] 主定位失败: {}".format(str(e1)[:50]))
                    try:
                        # 备用: 通过表头 .cost 定位
                        inp = driver.find_element(By.XPATH,
                            "//*[contains(@class,'cost')]//following::input[@type='text'][1]")
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
                        self._js_input(inp, price_num)
                        self.log("[OK] 价格(USD)已填写(备用): {}".format(price_num))
                        price_filled = True
                        time.sleep(0.5)
                    except Exception as e2:
                        self.log("[WARN] 价格(USD)未能填写: {}".format(str(e2)[:50]))
            # 步骤2.5: 填写含包装重量(g)
            try:
                self.log("[DEBUG] 填写含包装重量...")
                w_inp = driver.find_element(By.CSS_SELECTOR, ".weightClass_0 input")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", w_inp)
                driver.execute_script(
                    "(function(el,val){"
                    "var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                    "s.call(el,val);"
                    "el.dispatchEvent(new Event('input',{bubbles:true}));"
                    "el.dispatchEvent(new Event('change',{bubbles:true}));"
                    "el.dispatchEvent(new Event('blur',{bubbles:true}));"
                    "})(arguments[0],arguments[1]);",
                    w_inp, "100")
                self.log("[OK] 含包装重量已填写100g")
                time.sleep(0.3)
            except Exception as _we:
                self.log("[DEBUG] 含包装重量填写失败: {}".format(str(_we)[:60]))

            # 步骤2: 点击“编辑库存”，在表格行的「请输入」库存 input 中填200，确定
            try:
                self.log("[DEBUG] 处理库存...")
                edit_stock_btn = None
                for btn in driver.find_elements(By.XPATH,
                        "//button[.//span[contains(text(),'编辑库存')] or contains(text(),'编辑库存')]"):
                    try:
                        if btn.is_displayed():
                            edit_stock_btn = btn
                            break
                    except Exception:
                        continue
                if edit_stock_btn is None:
                    self.log("[WARN] 未找到「编辑库存」按鈕")
                else:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", edit_stock_btn)
                    driver.execute_script("arguments[0].click();", edit_stock_btn)
                    self.log("[DEBUG] 已点击「编辑库存」")
                    time.sleep(2)
                    # 等待库存维护对话框
                    try:
                        from selenium.webdriver.support.ui import WebDriverWait as _WDW
                        from selenium.webdriver.support import expected_conditions as _EC
                        _WDW(driver, 8).until(_EC.presence_of_element_located(
                            (By.XPATH, "//*[contains(@class,'so-modal-title') and contains(.,'库存维护')]"))
                        )
                        self.log("[DEBUG] 库存维护对话框已出现")
                    except Exception:
                        self.log("[DEBUG] 库存维护对话框等待超时")
                    time.sleep(0.5)
                    stock_filled = False
                    try:
                        # 精确定位: class 含 stockInfo_ 的库存 input
                        row_inps = driver.find_elements(By.XPATH,
                            "//*[contains(@class,'stockInfo_')]//input[@type='text']")
                        if not row_inps:
                            row_inps = driver.find_elements(By.XPATH,
                                "//*[contains(@class,'warehouseListBox')]//input[@type='text']")
                        self.log("[DEBUG] 找到库存行 input 数量: {}".format(len(row_inps)))
                        for row_inp in row_inps:
                            try:
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row_inp)
                                driver.execute_script("arguments[0].focus();", row_inp)
                                time.sleep(0.2)
                                # 使用 React 原生 setter 设定并触发事件
                                driver.execute_script("""
                                    var inp = arguments[0];
                                    var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                    setter.call(inp, '200');
                                    inp.dispatchEvent(new Event('input', {bubbles:true}));
                                    inp.dispatchEvent(new Event('change', {bubbles:true}));
                                    inp.dispatchEvent(new Event('blur', {bubbles:true}));
                                """, row_inp)
                                time.sleep(0.8)
                                # 验证小: 读回属性确认填入成功
                                val = driver.execute_script("return arguments[0].value;", row_inp)
                                self.log("[DEBUG] 库存 input 当前値: {}".format(val))
                                stock_filled = True
                            except Exception as e:
                                self.log("[DEBUG] 行 input 填写失败: {}".format(str(e)[:40]))
                    except Exception as e:
                        self.log("[DEBUG] 库存 input 定位失败: {}".format(str(e)[:50]))
                    if not stock_filled:
                        self.log("[WARN] 库存 input 未找到")
                    time.sleep(0.5)
                    # 点击确定按鈕关闭对话框
                    try:
                        confirm_btn = driver.find_element(By.XPATH,
                            "//div[contains(@class,'so-modal-footer') or contains(@class,'so-card-footer')]"
                            "//button[contains(@class,'so-button-primary')]")
                        driver.execute_script("arguments[0].click();", confirm_btn)
                        self.log("[OK] 库存已确认")
                        time.sleep(1)
                    except Exception as e:
                        self.log("[WARN] 确定按鈕失败: {}".format(str(e)[:50]))
            except Exception as e:
                self.log("[WARN] 库存处理失败: {}".format(str(e)[:60]))

            # [DISABLED] # ── 4. 上传主规格图到细节图/方形图区域（跳过色块图）
            # [DISABLED] if main_images:
            # [DISABLED] self.log("[DEBUG] 上传主规格图...")
            # [DISABLED] try:
            # [DISABLED] main_img_url = main_images[0]
            # [DISABLED] img_path = self._save_img_temp(main_img_url)
            # [DISABLED] if img_path:
            # [DISABLED] # 定位细节图或方形图区域的 file input，明确排除色块图
            # [DISABLED] fi = None
            # [DISABLED] # 方法1：通过祖先标题文字定位
            # [DISABLED] try:
            # [DISABLED] els = driver.find_elements(By.XPATH,
            # [DISABLED] "//td[not(contains(@class,'detail_img'))]//input[@type='file'][1]")
            # [DISABLED] if els:
            # [DISABLED] fi = els[0]
            # [DISABLED] self.log("[DEBUG] 通过区域标题定位到规格图 input")
            # [DISABLED] except Exception:
            # [DISABLED] pass
            # [DISABLED] # 方法2：遍历所有 file input，跳过色块图区域内的
            # [DISABLED] if fi is None:
            # [DISABLED] all_fi = driver.find_elements(By.XPATH, "//input[@type='file']")
            # [DISABLED] for candidate in all_fi:
            # [DISABLED] try:
            # [DISABLED] is_swatch = False
            # [DISABLED] node = candidate
            # [DISABLED] for _ in range(8):
            # [DISABLED] try:
            # [DISABLED] node = node.find_element(By.XPATH, "..")
            # [DISABLED] node_text = node.get_attribute("innerText") or ""
            # [DISABLED] if "色块图" in node_text:
            # [DISABLED] is_swatch = True
            # [DISABLED] break
            # [DISABLED] except Exception:
            # [DISABLED] break
            # [DISABLED] if not is_swatch:
            # [DISABLED] fi = candidate
            # [DISABLED] self.log("[DEBUG] 通过排除色块图定位到规格图 input")
            # [DISABLED] break
            # [DISABLED] except Exception:
            # [DISABLED] continue
            # [DISABLED] if fi:
            # [DISABLED] driver.execute_script(
            # [DISABLED] "arguments[0].style.cssText='display:block!important;visibility:visible!important;opacity:1!important;';", fi)
            # [DISABLED] fi.send_keys(img_path)
            # [DISABLED] self._handle_crop_dialog()
            # [DISABLED] self.log("[OK] 主规格图已上传")
            # [DISABLED] time.sleep(2)
            # [DISABLED] else:
            # [DISABLED] self.log("[DEBUG] 未找到合适的规格图 file input，跳过")
            # [DISABLED] try:
            # [DISABLED] os.remove(img_path)
            # [DISABLED] except Exception:
            # [DISABLED] pass
            # [DISABLED] else:
            # [DISABLED] self.log("[DEBUG] 主规格图下载失败，跳过")
            # [DISABLED] except Exception as e:
            # [DISABLED] self.log("[DEBUG] 主规格图上传异常: {}".format(str(e)[:60]))

            self.log("[OK] 规格及供应信息填写完成")
            return True
        except Exception as e:
            self.log("[ERROR] 填写规格及供应信息失败: {}".format(str(e)[:80]))
            return False

    def _get_detail_img_input(self):
        """精确定位细节图列的 file input。
        先滚动页面使容器渲染，再等待它出现，最多重试境欿10次。"""
        import time as _time
        driver = self.driver
        # 先滚动到细节图容器位置并等待其渲染
        try:
            driver.execute_script(
                "var el=document.querySelector('div.detail_img_container,#userguide_commodities_info_skc_title_table');"
                "if(el){el.scrollIntoView({block:'center',behavior:'smooth'});}"
                "else{window.scrollTo(0,document.body.scrollHeight*0.6);}"
            )
            _time.sleep(1.5)
        except Exception:
            pass
        # 重试最多10次，每次0.8秒
        for attempt in range(10):
            # 方法1：通过 detail_img_container 容器
            try:
                containers = driver.find_elements(By.CSS_SELECTOR,
                    "div.detail_img_container, #userguide_commodities_info_skc_title_table")
                if containers:
                    inputs = containers[0].find_elements(By.CSS_SELECTOR,
                        "input[type='file'][multiple]")
                    if inputs:
                        self.log("[DEBUG] 细节图 input 找到 (multiple, attempt {})".format(attempt+1))
                        return inputs[0]
                    inputs = containers[0].find_elements(By.CSS_SELECTOR, "input[type='file']")
                    if inputs:
                        self.log("[DEBUG] 细节图 input 找到 (attempt {})".format(attempt+1))
                        return inputs[0]
            except Exception as e:
                self.log("[DEBUG] 容器定位失败: {}".format(str(e)[:40]))
            # 方法2： JS 通过祖先查找
            try:
                all_fi = driver.find_elements(By.XPATH, "//input[@type='file']")
                js = ("var el=arguments[0];for(var i=0;i<15;i++){el=el.parentElement;"
                      "if(!el)return false;var c=el.className||'';var d=el.id||'';"
                      "if(c.indexOf('detail_img_container')!==-1)return true;"
                      "if(d==='userguide_commodities_info_skc_title_table')return true;}return false;")
                for fi in all_fi:
                    try:
                        if driver.execute_script(js, fi):
                            self.log("[DEBUG] JS祖先找到细节图 input (attempt {})".format(attempt+1))
                            return fi
                    except Exception:
                        continue
            except Exception as e:
                self.log("[DEBUG] JS定位失败: {}".format(str(e)[:40]))
            if attempt < 9:
                self.log("[DEBUG] 细节图 input 未找到，等待0.8s后重试 (attempt {})".format(attempt+1))
                # 每次重试时再滚动一次
                try:
                    driver.execute_script(
                        "var el=document.querySelector('div.detail_img_container,#userguide_commodities_info_skc_title_table');"
                        "if(el){el.scrollIntoView({block:'center'});}"
                        "else{window.scrollTo(0,document.body.scrollHeight*0.6);}"
                    )
                except Exception:
                    pass
                _time.sleep(0.8)
        self.log("[ERROR] 细节图 input 经10次重试仍未找到")
        return None

    def _upload_product_images(self, product_info):
        "连续上传5张图片到细节图列，每张裁剪后重复。"
        try:
            main_images = product_info.get("main_images", [])
            if not main_images and product_info.get("image_url"):
                main_images = [product_info["image_url"]]
            if not main_images:
                self.log("[ERROR] 没有主页图可以上传")
                return
            images_to_upload = main_images
            self.log("开始上传细节图...")
            self.log("[DEBUG] 准备上传 {} 张图片到细节图".format(len(images_to_upload)))
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
            time.sleep(1.5)
            self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
            time.sleep(1.5)
            for idx, img_url in enumerate(images_to_upload):
                try:
                    self.log("[DEBUG] 上传细节图第 {} 张...".format(idx + 1))
                    img_path = self._save_img_temp(img_url)
                    if not img_path:
                        self.log("[ERROR] 第 {} 张下载失败".format(idx + 1))
                        continue
                    fi = self._get_detail_img_input()
                    if fi is None:
                        self.log("[ERROR] 第 {} 张：未找到细节图 input".format(idx + 1))
                        try:
                            import os as _os; _os.remove(img_path)
                        except Exception:
                            pass
                        continue
                    try:
                        self.driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';", fi)
                        fi.send_keys(img_path)
                        self.log("[OK] 第 {} 张细节图已送入上传".format(idx + 1))
                        self._handle_crop_dialog()
                        time.sleep(1.5)
                    except Exception as e:
                        self.log("[ERROR] 第 {} 张 send_keys 失败: {}".format(idx + 1, str(e)[:60]))
                    try:
                        import os as _os; _os.remove(img_path)
                    except Exception:
                        pass
                except Exception as e:
                    self.log("[ERROR] 第 {} 张上传失败: {}".format(idx + 1, str(e)[:60]))
                    continue
            self.log("[OK] 细节图上传完成")
        except Exception as e:
            self.log("[ERROR] 上传细节图异常: {}".format(str(e)[:60]))

    def click_identify_image_button_OLD(self):
        """点击'识图发品'按钮。"""
        try:
            self.log("[DEBUG] 查找'识图发品'按钮...")
            # 方法1：查找包含"识图"的 div 或 button
            for el in self.driver.find_elements(By.XPATH, "//*[contains(text(), '识图')]"):
                try:
                    # 尝试点击这个元素或其父元素
                    el.click()
                    self.log("[OK] 已点击'识图发品'按钮")
                    time.sleep(2)
                    return True
                except Exception:
                    # 尝试点击父元素
                    try:
                        parent = el.find_element(By.XPATH, "..")
                        parent.click()
                        self.log("[OK] 已点击'识图发品'按钮（父元素）")
                        time.sleep(2)
                        return True
                    except Exception:
                        continue
            
            self.log("[ERROR] 未找到'识图发品'按钮")
            return False
        except Exception as e:
            self.log("[ERROR] 点击按钮失败: {}".format(str(e)))
            return False

    def upload_product_image(self, image_path):
        """上传商品图片到'识图发品'页面。"""
        if not os.path.isfile(image_path):
            self.log("[ERROR] 图片文件不存在: {}".format(image_path))
            return False
        
        try:
            self.log("[DEBUG] 查找文件上传框...")
            file_inputs = self.driver.find_elements(By.CSS_SELECTOR, "input[type='file']")
            
            if not file_inputs:
                self.log("[ERROR] 未找到文件上传框")
                return False
            
            # 使用第一个文件上传框
            file_input = file_inputs[0]
            abs_path = os.path.abspath(image_path)
            
            self.log("[DEBUG] 上传图片: {}".format(os.path.basename(image_path)))
            file_input.send_keys(abs_path)
            
            # 等待上传完成
            time.sleep(3)
            self.log("[OK] 图片已上传: {}".format(os.path.basename(image_path)))
            return True
        except Exception as e:
            self.log("[ERROR] 上传失败: {}".format(str(e)[:60]))
            return False

    def quit(self):
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass

    # ── 工具方法
    def _wait_click(self, by, sel, timeout=15):
        el = WebDriverWait(self.driver, timeout).until(
            EC.element_to_be_clickable((by, sel)))
        self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
        time.sleep(0.4)
        try:
            el.click()
        except Exception:
            self.driver.execute_script("arguments[0].click();", el)
        return el

    def _try_click(self, selectors, timeout=8):
        """尝试多个选择器，返回是否成功。"""
        for by, sel in selectors:
            try:
                self._wait_click(by, sel, timeout)
                return True
            except Exception:
                continue
        return False

    def _try_input(self, selectors, text, timeout=8):
        for by, sel in selectors:
            try:
                el = WebDriverWait(self.driver, timeout).until(
                    EC.presence_of_element_located((by, sel)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                el.clear()
                el.send_keys(text)
                return True
            except Exception:
                continue
        return False

    def _js_input(self, el, text):
        """用 JS 直接赋值（应对 React/Vue 受控组件）。"""
        self.driver.execute_script(
            "arguments[0].value = arguments[1];"
            "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));"
            "arguments[0].dispatchEvent(new Event('change',{bubbles:true}));",
            el, text)

    def _save_img_temp(self, url):
        """将图片下载到临时文件，返回路径。"""
        try:
            hdrs = random.choice(HEADERS_POOL).copy()
            r = requests.get(url, headers=hdrs, timeout=15)
            if r.status_code == 200:
                ext = ".jpg"
                if "png" in r.headers.get("Content-Type",""): ext = ".png"
                fd, path = tempfile.mkstemp(suffix=ext)
                with os.fdopen(fd, "wb") as f:
                    f.write(r.content)
                return path
        except Exception:
            pass
        return None

    # ── 识图选类目
    def select_category_by_image(self, img_url_or_path, timeout=60):
        """识图自动选类目。返回 True/False。"""
        driver = self.driver
        CATEGORY_URL = ("https://sso.geiwohuo.com/#/spmc/commodities-category"
                        "/followsales-pro/list?externalSystem=spmp")
        self.log("[识图] 导航到分类选择页...")
        try:
            driver.get(CATEGORY_URL)
            time.sleep(4)
        except Exception as e:
            self.log("[识图] 导航失败: {}".format(e)); return False
        tmp_path = None
        if img_url_or_path.startswith("http"):
            tmp_path = self._save_img_temp(img_url_or_path)
            if not tmp_path: self.log("[识图] 图片下载失败"); return False
            img_path = tmp_path
        else:
            img_path = img_url_or_path
        entry_xpaths = [
            "//*[contains(text(),'识图发品')]",
            "//*[contains(text(),'图片上传')]",
            "//*[contains(text(),'上传图片')]",
            "//label[contains(@class,'upload')]",
            "//div[contains(@class,'upload')]",
        ]
        try:
            # Step1: 触发 file input
            for xp in entry_xpaths:
                try:
                    for el in driver.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            driver.execute_script("arguments[0].click();", el)
                            self.log("[识图] 点击入口: {}".format(el.text.strip()[:30]))
                            time.sleep(1.5); break
                except Exception: pass
            # Step2: 上传图片
            uploaded = False
            for attempt in range(3):
                for inp in driver.find_elements(By.XPATH, "//input[@type='file']"):
                    try:
                        driver.execute_script(
                            "arguments[0].style.cssText='display:block!important;visibility:visible!important;opacity:1!important;';", inp)
                        inp.send_keys(img_path)
                        self.log("[识图] 图片已上传"); uploaded = True; break
                    except Exception as e:
                        self.log("[识图] file input 失败: {}".format(e))
                if uploaded: break
                for xp in entry_xpaths:
                    try:
                        for el in driver.find_elements(By.XPATH, xp):
                            if el.is_displayed():
                                driver.execute_script("arguments[0].click();", el)
                                time.sleep(1.5); break
                    except Exception: pass
            if not uploaded:
                self.log("[识图] 无法上传图片"); return False
            # Step3: 等待推荐类目
            # 用 JS 扫描所有元素，找到包含「推荐类目」文字的元素后找相邻可点击元素
            self.log("[识图] 等待推荐类目（最多 {}s）...".format(timeout))
            recommend_el = None
            deadline = time.time() + timeout
            while time.time() < deadline:
                try:
                    # JS：在所有 DOM 元素中搜索 spmc_selected 字样的元素
                    found = driver.execute_script("""
                        var spans = document.querySelectorAll('span[class*=spmc_selected]');
                        for (var i=0; i<spans.length; i++) {
                            var t = spans[i].innerText || spans[i].textContent;
                            if (t && t.trim().length > 0) return spans[i];
                        }
                        return null;
                    """)
                    if found:
                        txt = driver.execute_script("return arguments[0].innerText || arguments[0].textContent;", found) or ""
                        self.log("[识图] 推荐类目: {}".format(txt.strip()[:60]))
                        recommend_el = found
                except Exception as _e:
                    self.log("[识图] JS搜索异常: {}".format(_e))
                if recommend_el: break
                # 保存调试截图（首次等待2s后拍一张）
                elapsed = timeout - (deadline - time.time())
                if 1.5 < elapsed < 3.5:
                    try:
                        import os as _os
                        driver.save_screenshot(_os.path.join(_os.path.expanduser("~"), "Desktop", "shein_after_upload.png"))
                        # 保存此时 HTML 中所有 span 的信息
                        info_txt = driver.execute_script("""
                            var result = [];
                            var spans = document.querySelectorAll('span');
                            for (var i=0; i<Math.min(spans.length,200); i++) {
                                var t = (spans[i].innerText||spans[i].textContent||''). trim();
                                var c = spans[i].className || '';
                                if (t) result.push('class='+c+': '+t);
                            }
                            return result.join('\n');
                        """)
                        dbg_path = _os.path.join(_os.path.expanduser("~"), "Desktop", "shein_after_upload_spans.txt")
                        with open(dbg_path, "w", encoding="utf-8") as _f:
                            _f.write("URL: {}\n".format(driver.current_url))
                            _f.write(info_txt or "(no spans)")
                        self.log("[识图] 调试信息已保存到桌面")
                    except Exception: pass
                time.sleep(1.5)
            if not recommend_el:
                self.log("[识图] 超时，推荐类目未出现")
                return False
            # Step4: 点击推荐类目的 cursor-pointer 父容器或直接点 span
            time.sleep(0.5)
            try:
                parent = driver.execute_script(
                    "return arguments[0].closest('.cursor-pointer') || arguments[0].parentElement;",
                    recommend_el)
                click_target = parent if parent else recommend_el
            except Exception:
                click_target = recommend_el
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", click_target)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", click_target)
            txt = driver.execute_script("return arguments[0].innerText;", recommend_el) or ""
            self.log("[识图] 已点击推荐类目: {}".format(txt.strip()[:60]))
            time.sleep(1.5)
            # Step5: 点击「确认，下一步」 (class=soui-button-primary)
            confirmed = False
            for by, sel in [
                (By.XPATH, "//button[contains(@class,'soui-button-primary')]"),
                (By.XPATH, "//button[contains(text(),'确认，下一步')]"),
                (By.XPATH, "//button[contains(text(),'确认')]"),
            ]:
                try:
                    for btn in driver.find_elements(by, sel):
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            self.log("[识图] 已点击确认按钒: {}".format(btn.text.strip()[:20]))
                            confirmed = True; time.sleep(3); break
                except Exception: pass
                if confirmed: break
            if not confirmed: self.log("[识图] 未找到确认按钒")
            return confirmed
        finally:
            if tmp_path and os.path.exists(tmp_path):
                try: os.remove(tmp_path)
                except Exception: pass

    # ── 识图选类目
    def select_category_by_image(self, img_url_or_path, timeout=60):
        """
        使用 SHEIN「识图发品」功能自动选择类目。
        流程：
          1. 导航到分类选择页
          2. 点击「图片上传」按钮（如果存在）
          3. 上传商品图片到 file input
          4. 等待系统推荐类目出现
          5. 点击第一个推荐类目
          6. 点击「确认，下一步」
        返回 True 表示成功，False 表示失败。
        """
        driver = self.driver
        CATEGORY_URL = ("https://sso.geiwohuo.com/#/spmc/commodities-category"
                        "/followsales-pro/list?externalSystem=spmp")

        self.log("[识图选类目] 导航到分类选择页...")
        try:
            original_handles = set(driver.window_handles)
            driver.get(CATEGORY_URL)
            time.sleep(3)
            new_handles = set(driver.window_handles) - original_handles
            if new_handles:
                driver.switch_to.window(new_handles.pop())
                time.sleep(2)
        except Exception as e:
            self.log("[识图选类目] 导航失败: {}".format(e))
            return False

        # 准备图片路径（URL 先下载到临时文件）
        tmp_path = None
        if img_url_or_path.startswith("http"):
            self.log("[识图选类目] 下载图片...")
            tmp_path = self._save_img_temp(img_url_or_path)
            if not tmp_path:
                self.log("[识图选类目] 图片下载失败")
                return False
            img_path = tmp_path
        else:
            img_path = img_url_or_path

        try:
            # Step1: 点击「识图发品」/「图片上传」入口
            self.log("[识图选类目] 查找图片上传入口...")
            entry_xpaths = [
                "//*[contains(text(),'识图发品')]",
                "//*[contains(text(),'图片上传')]",
                "//*[contains(text(),'上传图片')]",
                "//*[contains(@class,'imageUpload') or contains(@class,'image-upload')"
                " or contains(@class,'img-upload') or contains(@class,'uploadImg')]",
            ]
            for xp in entry_xpaths:
                try:
                    els = driver.find_elements(By.XPATH, xp)
                    for el in els:
                        if el.is_displayed():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", el)
                            self.log("[识图选类目] 已点击入口: {}".format(
                                el.text.strip()[:30]))
                            time.sleep(1.5)
                            break
                except Exception:
                    pass

            # Step2: 找 file input 并发送图片路径
            self.log("[识图选类目] 上传图片: {}".format(img_path))
            uploaded = False
            for attempt in range(2):
                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")  
                self.log("[识图选类目] 找到 {} 个 file input (第{}轮)".format(
                    len(file_inputs), attempt + 1))
                for inp in file_inputs:
                    try:
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';", inp)
                        inp.send_keys(img_path)
                        self.log("[识图选类目] 图片已上传")
                        uploaded = True
                        break
                    except Exception as e:
                        self.log("[识图选类目] file input 尝试失败: {}".format(e))
                if uploaded:
                    break
                if attempt == 0:
                    for xp in entry_xpaths:
                        try:
                            els = driver.find_elements(By.XPATH, xp)
                            for el in els:
                                if el.is_displayed():
                                    driver.execute_script("arguments[0].click();", el)
                                    time.sleep(1.5)
                                    break
                        except Exception:
                            pass

            if not uploaded:
                self.log("[识图选类目] 无法上传图片，终止识图流程")
                return False

            # Step3: 等待推荐类目出现
            self.log("[识图选类目] 等待推荐类目（最多 {}s）...".format(timeout))
            recommend_el = None
            deadline = time.time() + timeout
            rec_xpaths = [
                "//*[contains(text(),'推荐类目') or contains(text(),'推荐分类')]"
                "/following::span[contains(@class,'spmc_itemContent')][1]",
                "//*[contains(@class,'recommend') or contains(@class,'Recommend')]"
                "//span[contains(@class,'spmc_itemContent')]",
                "//span[contains(@class,'spmc_itemContent')]",
            ]
            while time.time() < deadline:
                for xp in rec_xpaths:
                    try:
                        els = driver.find_elements(By.XPATH, xp)
                        visible = [e for e in els if e.is_displayed() and e.text.strip()]
                        if visible:
                            recommend_el = visible[0]
                            self.log("[识图选类目] 推荐类目出现: {}".format(
                                recommend_el.text.strip()[:40]))
                            break
                    except Exception:
                        pass
                if recommend_el:
                    break
                time.sleep(1)

            if not recommend_el:
                self.log("[识图选类目] 超时仍未出现推荐类目")
                try:
                    import os as _os
                    desktop = _os.path.join(_os.path.expanduser("~"), "Desktop")
                    driver.save_screenshot(
                        _os.path.join(desktop, "shein_imgcat_timeout.png"))
                    self.log("[识图选类目] 截图已保存到桌面")
                except Exception:
                    pass
                return False

            # Step4: 点击推荐类目
            time.sleep(0.5)
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", recommend_el)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", recommend_el)
            self.log("[识图选类目] 已点击推荐类目: {}".format(
                recommend_el.text.strip()[:40]))
            time.sleep(1.5)

            # Step5: 点击「确认，下一步」
            self.log("[识图选类目] 点击确认按钮...")
            confirmed = False
            confirm_xpaths = [
                "//button[contains(text(),'确认，下一步')]",
                "//button[contains(text(),'确认')]",
                "//span[contains(text(),'确认，下一步')]",
                "//span[contains(text(),'确认')]",
            ]
            for xp in confirm_xpaths:
                try:
                    for btn in driver.find_elements(By.XPATH, xp):
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            self.log("[识图选类目] 已点击: {}".format(
                                btn.text.strip()[:20]))
                            confirmed = True
                            time.sleep(3)
                            break
                except Exception:
                    pass
                if confirmed:
                    break

            if not confirmed:
                self.log("[识图选类目] 未找到确认按钮，类目可能已自动确认")
            return confirmed

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # ── 识图选类目
    def select_category_by_image(self, img_url_or_path, timeout=60):
        """
        使用 SHEIN「识图发品」功能自动选择类目。
        流程：
          1. 导航到分类选择页
          2. 点击「图片上传」按钮（如果存在）
          3. 上传商品图片到 file input
          4. 等待系统推荐类目出现
          5. 点击第一个推荐类目
          6. 点击「确认，下一步」
        返回 True 表示成功，False 表示失败。
        """
        driver = self.driver
        CATEGORY_URL = ("https://sso.geiwohuo.com/#/spmc/commodities-category"
                        "/followsales-pro/list?externalSystem=spmp")

        self.log("[识图选类目] 导航到分类选择页...")
        try:
            original_handles = set(driver.window_handles)
            driver.get(CATEGORY_URL)
            time.sleep(3)
            new_handles = set(driver.window_handles) - original_handles
            if new_handles:
                driver.switch_to.window(new_handles.pop())
                time.sleep(2)
        except Exception as e:
            self.log("[识图选类目] 导航失败: {}".format(e))
            return False

        # 准备图片路径（URL 先下载到临时文件）
        tmp_path = None
        if img_url_or_path.startswith("http"):
            self.log("[识图选类目] 下载图片...")
            tmp_path = self._save_img_temp(img_url_or_path)
            if not tmp_path:
                self.log("[识图选类目] 图片下载失败")
                return False
            img_path = tmp_path
        else:
            img_path = img_url_or_path

        try:
            # Step1: 点击「识图发品」/「图片上传」入口
            self.log("[识图选类目] 查找图片上传入口...")
            entry_xpaths = [
                "//*[contains(text(),'识图发品')]",
                "//*[contains(text(),'图片上传')]",
                "//*[contains(text(),'上传图片')]",
                "//*[contains(@class,'imageUpload') or contains(@class,'image-upload')"
                " or contains(@class,'img-upload') or contains(@class,'uploadImg')]",
            ]
            for xp in entry_xpaths:
                try:
                    els = driver.find_elements(By.XPATH, xp)
                    for el in els:
                        if el.is_displayed():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", el)
                            self.log("[识图选类目] 已点击入口: {}".format(
                                el.text.strip()[:30]))
                            time.sleep(1.5)
                            break
                except Exception:
                    pass

            # Step2: 找 file input 并发送图片路径
            self.log("[识图选类目] 上传图片: {}".format(img_path))
            uploaded = False
            for attempt in range(2):
                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")  
                self.log("[识图选类目] 找到 {} 个 file input (第{}轮)".format(
                    len(file_inputs), attempt + 1))
                for inp in file_inputs:
                    try:
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';", inp)
                        inp.send_keys(img_path)
                        self.log("[识图选类目] 图片已上传")
                        uploaded = True
                        break
                    except Exception as e:
                        self.log("[识图选类目] file input 尝试失败: {}".format(e))
                if uploaded:
                    break
                if attempt == 0:
                    for xp in entry_xpaths:
                        try:
                            els = driver.find_elements(By.XPATH, xp)
                            for el in els:
                                if el.is_displayed():
                                    driver.execute_script("arguments[0].click();", el)
                                    time.sleep(1.5)
                                    break
                        except Exception:
                            pass

            if not uploaded:
                self.log("[识图选类目] 无法上传图片，终止识图流程")
                return False

            # Step3: 等待推荐类目出现
            self.log("[识图选类目] 等待推荐类目（最多 {}s）...".format(timeout))
            recommend_el = None
            deadline = time.time() + timeout
            rec_xpaths = [
                "//*[contains(text(),'推荐类目') or contains(text(),'推荐分类')]"
                "/following::span[contains(@class,'spmc_itemContent')][1]",
                "//*[contains(@class,'recommend') or contains(@class,'Recommend')]"
                "//span[contains(@class,'spmc_itemContent')]",
                "//span[contains(@class,'spmc_itemContent')]",
            ]
            while time.time() < deadline:
                for xp in rec_xpaths:
                    try:
                        els = driver.find_elements(By.XPATH, xp)
                        visible = [e for e in els if e.is_displayed() and e.text.strip()]
                        if visible:
                            recommend_el = visible[0]
                            self.log("[识图选类目] 推荐类目出现: {}".format(
                                recommend_el.text.strip()[:40]))
                            break
                    except Exception:
                        pass
                if recommend_el:
                    break
                time.sleep(1)

            if not recommend_el:
                self.log("[识图选类目] 超时仍未出现推荐类目")
                try:
                    import os as _os
                    desktop = _os.path.join(_os.path.expanduser("~"), "Desktop")
                    driver.save_screenshot(
                        _os.path.join(desktop, "shein_imgcat_timeout.png"))
                    self.log("[识图选类目] 截图已保存到桌面")
                except Exception:
                    pass
                return False

            # Step4: 点击推荐类目
            time.sleep(0.5)
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", recommend_el)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", recommend_el)
            self.log("[识图选类目] 已点击推荐类目: {}".format(
                recommend_el.text.strip()[:40]))
            time.sleep(1.5)

            # Step5: 点击「确认，下一步」
            self.log("[识图选类目] 点击确认按钮...")
            confirmed = False
            confirm_xpaths = [
                "//button[contains(text(),'确认，下一步')]",
                "//button[contains(text(),'确认')]",
                "//span[contains(text(),'确认，下一步')]",
                "//span[contains(text(),'确认')]",
            ]
            for xp in confirm_xpaths:
                try:
                    for btn in driver.find_elements(By.XPATH, xp):
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            self.log("[识图选类目] 已点击: {}".format(
                                btn.text.strip()[:20]))
                            confirmed = True
                            time.sleep(3)
                            break
                except Exception:
                    pass
                if confirmed:
                    break

            if not confirmed:
                self.log("[识图选类目] 未找到确认按钮，类目可能已自动确认")
            return confirmed

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # ── 识图选类目
    def select_category_by_image(self, img_url_or_path, timeout=60):
        """
        使用 SHEIN「识图发品」功能自动选择类目。
        流程：
          1. 导航到分类选择页
          2. 点击「图片上传」按钮（如果存在）
          3. 上传商品图片到 file input
          4. 等待系统推荐类目出现
          5. 点击第一个推荐类目
          6. 点击「确认，下一步」
        返回 True 表示成功，False 表示失败。
        """
        driver = self.driver
        CATEGORY_URL = ("https://sso.geiwohuo.com/#/spmc/commodities-category"
                        "/followsales-pro/list?externalSystem=spmp")

        self.log("[识图选类目] 导航到分类选择页...")
        try:
            original_handles = set(driver.window_handles)
            driver.get(CATEGORY_URL)
            time.sleep(3)
            new_handles = set(driver.window_handles) - original_handles
            if new_handles:
                driver.switch_to.window(new_handles.pop())
                time.sleep(2)
        except Exception as e:
            self.log("[识图选类目] 导航失败: {}".format(e))
            return False

        # 准备图片路径（URL 先下载到临时文件）
        tmp_path = None
        if img_url_or_path.startswith("http"):
            self.log("[识图选类目] 下载图片...")
            tmp_path = self._save_img_temp(img_url_or_path)
            if not tmp_path:
                self.log("[识图选类目] 图片下载失败")
                return False
            img_path = tmp_path
        else:
            img_path = img_url_or_path

        try:
            # Step1: 点击「识图发品」/「图片上传」入口
            self.log("[识图选类目] 查找图片上传入口...")
            entry_xpaths = [
                "//*[contains(text(),'识图发品')]",
                "//*[contains(text(),'图片上传')]",
                "//*[contains(text(),'上传图片')]",
                "//*[contains(@class,'imageUpload') or contains(@class,'image-upload')"
                " or contains(@class,'img-upload') or contains(@class,'uploadImg')]",
            ]
            for xp in entry_xpaths:
                try:
                    els = driver.find_elements(By.XPATH, xp)
                    for el in els:
                        if el.is_displayed():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", el)
                            self.log("[识图选类目] 已点击入口: {}".format(
                                el.text.strip()[:30]))
                            time.sleep(1.5)
                            break
                except Exception:
                    pass

            # Step2: 找 file input 并发送图片路径
            self.log("[识图选类目] 上传图片: {}".format(img_path))
            uploaded = False
            for attempt in range(2):
                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")  
                self.log("[识图选类目] 找到 {} 个 file input (第{}轮)".format(
                    len(file_inputs), attempt + 1))
                for inp in file_inputs:
                    try:
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';", inp)
                        inp.send_keys(img_path)
                        self.log("[识图选类目] 图片已上传")
                        uploaded = True
                        break
                    except Exception as e:
                        self.log("[识图选类目] file input 尝试失败: {}".format(e))
                if uploaded:
                    break
                if attempt == 0:
                    for xp in entry_xpaths:
                        try:
                            els = driver.find_elements(By.XPATH, xp)
                            for el in els:
                                if el.is_displayed():
                                    driver.execute_script("arguments[0].click();", el)
                                    time.sleep(1.5)
                                    break
                        except Exception:
                            pass

            if not uploaded:
                self.log("[识图选类目] 无法上传图片，终止识图流程")
                return False

            # Step3: 等待推荐类目出现
            self.log("[识图选类目] 等待推荐类目（最多 {}s）...".format(timeout))
            recommend_el = None
            deadline = time.time() + timeout
            rec_xpaths = [
                "//*[contains(text(),'推荐类目') or contains(text(),'推荐分类')]"
                "/following::span[contains(@class,'spmc_itemContent')][1]",
                "//*[contains(@class,'recommend') or contains(@class,'Recommend')]"
                "//span[contains(@class,'spmc_itemContent')]",
                "//span[contains(@class,'spmc_itemContent')]",
            ]
            while time.time() < deadline:
                for xp in rec_xpaths:
                    try:
                        els = driver.find_elements(By.XPATH, xp)
                        visible = [e for e in els if e.is_displayed() and e.text.strip()]
                        if visible:
                            recommend_el = visible[0]
                            self.log("[识图选类目] 推荐类目出现: {}".format(
                                recommend_el.text.strip()[:40]))
                            break
                    except Exception:
                        pass
                if recommend_el:
                    break
                time.sleep(1)

            if not recommend_el:
                self.log("[识图选类目] 超时仍未出现推荐类目")
                try:
                    import os as _os
                    desktop = _os.path.join(_os.path.expanduser("~"), "Desktop")
                    driver.save_screenshot(
                        _os.path.join(desktop, "shein_imgcat_timeout.png"))
                    self.log("[识图选类目] 截图已保存到桌面")
                except Exception:
                    pass
                return False

            # Step4: 点击推荐类目
            time.sleep(0.5)
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", recommend_el)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", recommend_el)
            self.log("[识图选类目] 已点击推荐类目: {}".format(
                recommend_el.text.strip()[:40]))
            time.sleep(1.5)

            # Step5: 点击「确认，下一步」
            self.log("[识图选类目] 点击确认按钮...")
            confirmed = False
            confirm_xpaths = [
                "//button[contains(text(),'确认，下一步')]",
                "//button[contains(text(),'确认')]",
                "//span[contains(text(),'确认，下一步')]",
                "//span[contains(text(),'确认')]",
            ]
            for xp in confirm_xpaths:
                try:
                    for btn in driver.find_elements(By.XPATH, xp):
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            self.log("[识图选类目] 已点击: {}".format(
                                btn.text.strip()[:20]))
                            confirmed = True
                            time.sleep(3)
                            break
                except Exception:
                    pass
                if confirmed:
                    break

            if not confirmed:
                self.log("[识图选类目] 未找到确认按钮，类目可能已自动确认")
            return confirmed

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # ── 识图选类目
    def select_category_by_image(self, img_url_or_path, timeout=60):
        """
        使用 SHEIN「识图发品」功能自动选择类目。
        流程：
          1. 导航到分类选择页
          2. 点击「图片上传」按钮（如果存在）
          3. 上传商品图片到 file input
          4. 等待系统推荐类目出现
          5. 点击第一个推荐类目
          6. 点击「确认，下一步」
        返回 True 表示成功，False 表示失败。
        """
        driver = self.driver
        CATEGORY_URL = ("https://sso.geiwohuo.com/#/spmc/commodities-category"
                        "/followsales-pro/list?externalSystem=spmp")

        self.log("[识图选类目] 导航到分类选择页...")
        try:
            original_handles = set(driver.window_handles)
            driver.get(CATEGORY_URL)
            time.sleep(3)
            new_handles = set(driver.window_handles) - original_handles
            if new_handles:
                driver.switch_to.window(new_handles.pop())
                time.sleep(2)
        except Exception as e:
            self.log("[识图选类目] 导航失败: {}".format(e))
            return False

        # 准备图片路径（URL 先下载到临时文件）
        tmp_path = None
        if img_url_or_path.startswith("http"):
            self.log("[识图选类目] 下载图片...")
            tmp_path = self._save_img_temp(img_url_or_path)
            if not tmp_path:
                self.log("[识图选类目] 图片下载失败")
                return False
            img_path = tmp_path
        else:
            img_path = img_url_or_path

        try:
            # Step1: 点击「识图发品」/「图片上传」入口
            self.log("[识图选类目] 查找图片上传入口...")
            entry_xpaths = [
                "//*[contains(text(),'识图发品')]",
                "//*[contains(text(),'图片上传')]",
                "//*[contains(text(),'上传图片')]",
                "//*[contains(@class,'imageUpload') or contains(@class,'image-upload')"
                " or contains(@class,'img-upload') or contains(@class,'uploadImg')]",
            ]
            for xp in entry_xpaths:
                try:
                    els = driver.find_elements(By.XPATH, xp)
                    for el in els:
                        if el.is_displayed():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", el)
                            self.log("[识图选类目] 已点击入口: {}".format(
                                el.text.strip()[:30]))
                            time.sleep(1.5)
                            break
                except Exception:
                    pass

            # Step2: 找 file input 并发送图片路径
            self.log("[识图选类目] 上传图片: {}".format(img_path))
            uploaded = False
            for attempt in range(2):
                file_inputs = driver.find_elements(By.XPATH, "//input[@type='file']")  
                self.log("[识图选类目] 找到 {} 个 file input (第{}轮)".format(
                    len(file_inputs), attempt + 1))
                for inp in file_inputs:
                    try:
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';", inp)
                        inp.send_keys(img_path)
                        self.log("[识图选类目] 图片已上传")
                        uploaded = True
                        break
                    except Exception as e:
                        self.log("[识图选类目] file input 尝试失败: {}".format(e))
                if uploaded:
                    break
                if attempt == 0:
                    for xp in entry_xpaths:
                        try:
                            els = driver.find_elements(By.XPATH, xp)
                            for el in els:
                                if el.is_displayed():
                                    driver.execute_script("arguments[0].click();", el)
                                    time.sleep(1.5)
                                    break
                        except Exception:
                            pass

            if not uploaded:
                self.log("[识图选类目] 无法上传图片，终止识图流程")
                return False

            # Step3: 等待推荐类目出现
            self.log("[识图选类目] 等待推荐类目（最多 {}s）...".format(timeout))
            recommend_el = None
            deadline = time.time() + timeout
            rec_xpaths = [
                "//*[contains(text(),'推荐类目') or contains(text(),'推荐分类')]"
                "/following::span[contains(@class,'spmc_itemContent')][1]",
                "//*[contains(@class,'recommend') or contains(@class,'Recommend')]"
                "//span[contains(@class,'spmc_itemContent')]",
                "//span[contains(@class,'spmc_itemContent')]",
            ]
            while time.time() < deadline:
                for xp in rec_xpaths:
                    try:
                        els = driver.find_elements(By.XPATH, xp)
                        visible = [e for e in els if e.is_displayed() and e.text.strip()]
                        if visible:
                            recommend_el = visible[0]
                            self.log("[识图选类目] 推荐类目出现: {}".format(
                                recommend_el.text.strip()[:40]))
                            break
                    except Exception:
                        pass
                if recommend_el:
                    break
                time.sleep(1)

            if not recommend_el:
                self.log("[识图选类目] 超时仍未出现推荐类目")
                try:
                    import os as _os
                    desktop = _os.path.join(_os.path.expanduser("~"), "Desktop")
                    driver.save_screenshot(
                        _os.path.join(desktop, "shein_imgcat_timeout.png"))
                    self.log("[识图选类目] 截图已保存到桌面")
                except Exception:
                    pass
                return False

            # Step4: 点击推荐类目
            time.sleep(0.5)
            driver.execute_script(
                "arguments[0].scrollIntoView({block:'center'});", recommend_el)
            time.sleep(0.3)
            driver.execute_script("arguments[0].click();", recommend_el)
            self.log("[识图选类目] 已点击推荐类目: {}".format(
                recommend_el.text.strip()[:40]))
            time.sleep(1.5)

            # Step5: 点击「确认，下一步」
            self.log("[识图选类目] 点击确认按钮...")
            confirmed = False
            confirm_xpaths = [
                "//button[contains(text(),'确认，下一步')]",
                "//button[contains(text(),'确认')]",
                "//span[contains(text(),'确认，下一步')]",
                "//span[contains(text(),'确认')]",
            ]
            for xp in confirm_xpaths:
                try:
                    for btn in driver.find_elements(By.XPATH, xp):
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            self.log("[识图选类目] 已点击: {}".format(
                                btn.text.strip()[:20]))
                            confirmed = True
                            time.sleep(3)
                            break
                except Exception:
                    pass
                if confirmed:
                    break

            if not confirmed:
                self.log("[识图选类目] 未找到确认按钮，类目可能已自动确认")
            return confirmed

        finally:
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except Exception:
                    pass

    # ── 主流程
    def _dismiss_announcements(self):
        """检测并关闭商品发布页面的公告弹窗（支持多条公告）。
        仅点击公告专用按钮（如「我已确认本公告，下一条」），避免误点「确认，下一步」等业务按钮。
        每条公告关闭后等待下一条渲染完成，循环直到无公告或达到上限。
        """
        max_attempts = 20  # 最多处理20条公告
        for attempt in range(max_attempts):
            try:
                def _has_announcement():
                    """检测当前是否有可见的公告弹窗。"""
                    for el in self.driver.find_elements(By.XPATH, "//*[contains(text(), '公告')]"):
                        try:
                            if el.is_displayed():
                                return True
                        except Exception:
                            continue
                    return False

                has_announcement = _has_announcement()

                # 若无公告：若刚处理过，再等一会确认（避免过渡期漏检下一条）
                if not has_announcement:
                    if attempt > 0:
                        time.sleep(1.0)
                        has_announcement = _has_announcement()
                    if not has_announcement:
                        if attempt > 0:
                            self.log("[OK] 所有公告已关闭 (共 {} 条)".format(attempt))
                        return

                self.log("[DEBUG] 检测到公告弹窗，尝试关闭 ({}/{})...".format(attempt + 1, max_attempts))

                # 仅点击公告专用按钮，避免误点「确认，下一步」（类目选择按钮）
                # 单条公告按钮：「我已确认本公告内容」；多条公告按钮：「我已确认本公告，下一条」
                clicked = False
                announcement_keywords = [
                    "我已确认本公告内容",       # 单条公告时的确认按钮
                    "我已确认本公告，下一条",  # 多条公告时的翻页按钮
                    "下一条",                   # 公告翻页
                    "下一个", "下一页", "Next",
                    "知道了", "我知道了",
                    "关闭", "Close",
                ]
                for kw in announcement_keywords:
                    btns = self.driver.find_elements(By.XPATH,
                        "//*[contains(text(), '{}')]".format(kw))
                    for btn in btns:
                        try:
                            txt = (btn.text or "").strip()
                            if "确认" in txt and "下一步" in txt and "下一条" not in txt:
                                continue
                            if btn.is_displayed():
                                self.driver.execute_script("arguments[0].click();", btn)
                                self.log("[DEBUG] 点击公告按钮: {} (第 {} 条)".format(kw, attempt + 1))
                                # 等待当前公告关闭 + 下一条公告渲染完成
                                time.sleep(2.0)
                                clicked = True
                                break
                        except Exception:
                            continue
                    if clicked:
                        break

                if not clicked:
                    self.log("[DEBUG] 未找到公告关闭按钮，跳过")
                    return

            except Exception as e:
                self.log("[DEBUG] 处理公告失败: {}".format(str(e)[:40]))
                return
        self.log("[DEBUG] 已处理最大公告数量 ({})".format(max_attempts))

    def publish_product(self, info, category):
        """
        category: list of category names from root to leaf, e.g. ["女装", "连衣裙", "迷你裙"]
                  or a plain string for backward compatibility.
        """
        # 兼容旧的字符串格式
        if isinstance(category, str):
            category = [category]
        driver = self.driver
        title  = (info.get("title") or "")[:60]
        asin   = info.get("asin", "")
        brand  = re.sub(r"(Brand:|Visit the|Store)", "",
                        info.get("brand", ""), flags=re.I).strip()
        price_raw = info.get("price", "")
        price_num = re.search(r"[\d.]+", price_raw)
        price_str = price_num.group() if price_num else ""
        desc_lines = []
        if info.get("features"): desc_lines += info["features"]
        if info.get("description"): desc_lines.append(info["description"])
        desc_text = "\n".join(desc_lines)[:800]

        # Step1: 导航到商品发布页
        self.log("导航到商品发布页面...")

        def _save_debug_screenshot(tag):
            """保存调试截图和页面源码到桌面。"""
            try:
                desktop = os.path.join(os.path.expanduser("~"), "Desktop")
                # 保存截图
                path = os.path.join(desktop, "shein_debug_{}.png".format(tag))
                driver.save_screenshot(path)
                # 保存页面 URL 和简化 HTML 结构
                info_path = os.path.join(desktop, "shein_debug_{}.txt".format(tag))
                with open(info_path, "w", encoding="utf-8") as f:
                    f.write("URL: {}\n\n".format(driver.current_url))
                    # 提取菜单文本
                    try:
                        menus = driver.find_elements(By.XPATH,
                            "//*[contains(@class,'menu') or contains(@class,'nav') or contains(@class,'sidebar')]//*[string-length(normalize-space(text()))>0 and string-length(normalize-space(text()))<20]")
                        f.write("=== 菜单元素 ===\n")
                        seen = set()
                        for m in menus[:50]:
                            try:
                                txt = m.text.strip()
                                tag_name = m.tag_name
                                cls = m.get_attribute("class") or ""
                                if txt and txt not in seen:
                                    seen.add(txt)
                                    f.write("  <{}> class='{}': {}\n".format(tag_name, cls[:50], txt))
                            except Exception:
                                pass
                    except Exception as e:
                        f.write("菜单提取失败: {}\n".format(e))
                    # 提取所有可点击文本
                    try:
                        clickable = driver.find_elements(By.XPATH,
                            "//a | //button | //li | //span[contains(@class,'menu') or contains(@class,'item')]")
                        f.write("\n=== 可点击元素(前50) ===\n")
                        seen2 = set()
                        for el in clickable[:80]:
                            try:
                                txt = el.text.strip()
                                if txt and len(txt) < 15 and txt not in seen2:
                                    seen2.add(txt)
                                    tag_name = el.tag_name
                                    cls = el.get_attribute("class") or ""
                                    href = el.get_attribute("href") or ""
                                    f.write("  <{}> class='{}' href='{}': {}\n".format(
                                        tag_name, cls[:40], href[:40], txt))
                            except Exception:
                                pass
                    except Exception as e:
                        f.write("可点击元素提取失败: {}\n".format(e))
                self.log("调试信息已保存: {}".format(info_path))
            except Exception as ex:
                self.log("保存调试信息失败: {}".format(ex))

        def _page_has_publish_elements():
            """检测当前页面是否包含商品发布的特征元素。"""
            indicators = [
                "//*[contains(@class,'category') or contains(@class,'cate')]",
                "//span[contains(text(),'选择类目') or contains(text(),'请选择') or contains(text(),'商品类目')]",
                "//div[contains(text(),'选择类目') or contains(text(),'请选择类目')]",
                "//*[contains(@placeholder,'搜索类目') or contains(@placeholder,'搜索分类') or contains(@placeholder,'类目')]",
                "//button[contains(text(),'下一步') or contains(text(),'确认')]",
            ]
            for xp in indicators:
                try:
                    els = driver.find_elements(By.XPATH, xp)
                    if els:
                        return True
                except Exception:
                    pass
            return False

        def _goto_publish():
            # 确保先到达首页
            self.log("导航到首页...")
            driver.get("https://www.geiwohuo.com/#/oversea-home")
            time.sleep(4)
            original_handles = set(driver.window_handles)

            # 点击「商品」span（精确匹配文本）
            self.log("查找「商品」菜单...")
            clicked_shp = False
            for el in driver.find_elements(By.TAG_NAME, "span"):
                try:
                    if el.text.strip() == "商品" and el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        self.log("已点击「商品」")
                        time.sleep(2)
                        clicked_shp = True
                        break
                except Exception:
                    continue

            if not clicked_shp:
                self.log("未找到「商品」菜单，终止")
                return False

            # 点击「商品发布」span（精确匹配文本）
            self.log("查找「商品发布」子菜单...")
            for el in driver.find_elements(By.TAG_NAME, "span"):
                try:
                    if el.text.strip() == "商品发布" and el.is_displayed():
                        driver.execute_script("arguments[0].click();", el)
                        self.log("已点击「商品发布」，等待新窗口...")
                        # 等待新窗口出现（最多10秒）
                        for _ in range(20):
                            time.sleep(0.5)
                            new_handles = set(driver.window_handles)
                            if new_handles - original_handles:
                                # 切换到新窗口
                                new_handle = (new_handles - original_handles).pop()
                                driver.switch_to.window(new_handle)
                                self.log("已切换到新窗口，URL: {}".format(driver.current_url))
                                time.sleep(3)
                                return True
                        # 没有新窗口，可能在同一窗口跳转
                        cur = driver.current_url
                        self.log("无新窗口，当前URL: {}".format(cur))
                        return True
                except Exception:
                    continue

            self.log("未找到「商品发布」子菜单")
            return False

        if not _goto_publish():
            raise Exception(
                "无法导航到商品发布页面。\n"
                "可能原因：\n"
                "  1. 账号没有商品发布权限\n"
                "  2. 网站页面结构已更新\n"
                "  3. 需要先完成店铺资质认证\n"
                "请在浏览器中手动检查。")

        time.sleep(2)

        # 关闭可能弹出的公告弹窗，避免影响类目选择等后续操作
        self._dismiss_announcements()
        time.sleep(1)

        # Step2: 选择类目（优先识图，其次关键词树，最后列表模式）
        img_url = info.get("image_url", "")
        cat_selected = False

        # 方法A：识图自动分类（最准确，优先使用）
        if img_url:
            self.log("[Step2] 尝试识图自动选类目...")
            try:
                cat_selected = self.select_category_by_image(img_url, timeout=60)
                if cat_selected:
                    self.log("[Step2] 识图选类目成功")
                else:
                    self.log("[Step2] 识图未成功，回退到关键词分类树...")
            except Exception as _img_e:
                self.log("[Step2] 识图异常: {}，回退到关键词分类树...".format(_img_e))
        else:
            self.log("[Step2] 无商品图片，跳过识图，使用关键词分类树...")

        # 方法B：关键词分类树逐级点击
        if not cat_selected:
            self.log("[Step2] 关键词分类树，路径: {}".format(" > ".join(category)))

        def _click_span_by_text(text, timeout=8):
            """在页面中点击 spmc_itemContent span，精确匹配文本。"""
            end = time.time() + timeout
            while time.time() < end:
                for el in driver.find_elements(By.XPATH,
                        "//span[contains(@class,'spmc_itemContent')]"):
                    try:
                        if el.text.strip() == text and el.is_displayed():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", el)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", el)
                            self.log("已点击分类：{}".format(text))
                            return True
                    except Exception:
                        pass
                time.sleep(0.5)
            return False

        def _fuzzy_click_span(text, timeout=8):
            """模糊匹配：在 spmc_itemContent span 中找最接近的文本并点击。"""
            end = time.time() + timeout
            while time.time() < end:
                candidates = []
                for el in driver.find_elements(By.XPATH,
                        "//span[contains(@class,'spmc_itemContent')]"):
                    try:
                        t = el.text.strip()
                        if t and el.is_displayed():
                            # 检查是否包含目标文本的关键字
                            if any(kw in t for kw in text.split()) or text in t or t in text:
                                candidates.append((el, t))
                    except Exception:
                        pass
                if candidates:
                    el, matched = candidates[0]
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", el)
                    time.sleep(0.3)
                    driver.execute_script("arguments[0].click();", el)
                    self.log("模糊匹配点击分类：{} (目标: {})".format(matched, text))
                    return True
                time.sleep(0.5)
            return False

        def _select_category_by_path(path):
            """
            逐级点击分类路径。
            path: list，如 ["女装", "连衣裙", "迷你裙"]
            成功后点击「确认，下一步」返回 True。
            """
            time.sleep(3)
            _save_debug_screenshot("category_page")

            for level, cat_name in enumerate(path):
                self.log("点击第{}级分类：{}".format(level + 1, cat_name))
                # 先精确匹配，再模糊匹配
                if not _click_span_by_text(cat_name, timeout=6):
                    self.log("精确匹配失败，尝试模糊匹配：{}".format(cat_name))
                    if not _fuzzy_click_span(cat_name, timeout=6):
                        self.log("第{}级分类未找到：{}".format(level + 1, cat_name))
                        # 如果不是第一级就继续，否则回退到列表模式
                        if level == 0:
                            return False
                        break
                time.sleep(1.5)

            # 点击「确认，下一步」按钮
            self.log("点击「确认，下一步」...")
            confirm_xpaths = [
                "//button[contains(text(),'确认，下一步')]",
                "//button[contains(text(),'确认')]",
                "//span[contains(text(),'确认，下一步')]",
                "//span[contains(text(),'确认')]",
                "//*[contains(@class,'confirm') or contains(@class,'next')][contains(text(),'确认') or contains(text(),'下一步')]",
            ]
            for xp in confirm_xpaths:
                try:
                    btns = driver.find_elements(By.XPATH, xp)
                    for btn in btns:
                        if btn.is_displayed() and btn.is_enabled():
                            driver.execute_script(
                                "arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.3)
                            driver.execute_script("arguments[0].click();", btn)
                            self.log("已点击确认按钮")
                            time.sleep(3)
                            return True
                except Exception:
                    pass

            # 如果没找到确认按钮，也继续（部分页面直接进入填写页）
            self.log("未找到确认按钮，继续后续步骤")
            return True

        def _select_category_from_list():
            """
            回退方案：在分类列表页找到匹配的行，点击「发布商品」按钮。
            """
            time.sleep(3)
            _save_debug_screenshot("category_list")
            cat_keywords = category  # category 是 list
            try:
                publish_btns = driver.find_elements(By.XPATH,
                    "//*[contains(text(),'发布商品') or contains(text(),'去发布')]"
                    "[not(contains(@class,'disabled'))]")
                self.log("列表页找到 {} 个发布按钮".format(len(publish_btns)))
                if publish_btns:
                    best_btn = None
                    best_score = 0
                    for btn in publish_btns:
                        try:
                            row = btn.find_element(By.XPATH,
                                "./ancestor::tr | ./ancestor::*[contains(@class,'row')] | ./ancestor::li")
                            row_text = row.text
                            score = sum(1 for k in cat_keywords if k in row_text)
                            if score > best_score:
                                best_score = score
                                best_btn = btn
                        except Exception:
                            continue
                    target = best_btn if best_btn else publish_btns[0]
                    driver.execute_script(
                        "arguments[0].scrollIntoView({block:'center'});", target)
                    time.sleep(0.5)
                    driver.execute_script("arguments[0].click();", target)
                    time.sleep(3)
                    return True
            except Exception as e:
                self.log("列表模式失败: {}".format(e))
            return False

        # B/C only if image selection failed
        if not cat_selected:
            cat_selected = _select_category_by_path(category)
        if not cat_selected:
            self.log("[Step2] trying list mode...")
            cat_selected = _select_category_from_list()
        if not cat_selected:
            self.log("[Step2] warning: category not selected")
        time.sleep(2)


        # Step3: 填写基础信息
        self.log("填写基础信息...")
        # 商品标题
        title_sels = [
            (By.XPATH, "//input[contains(@placeholder,'标题') or contains(@placeholder,'商品名称')]"),
            (By.XPATH, "//*[contains(text(),'商品标题')]/following::input[1]"),
            (By.XPATH, "//*[contains(text(),'标题')]/following::input[1]"),
            (By.CSS_SELECTOR, "input[name='title'], input[name='productName']"),
        ]
        for by, sel in title_sels:
            try:
                el = WebDriverWait(driver, 6).until(EC.presence_of_element_located((by, sel)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                self._js_input(el, title)
                break
            except Exception:
                continue

        # 货号（ASIN）
        self._try_input([
            (By.XPATH, "//input[contains(@placeholder,'货号') or contains(@placeholder,'SKU') or contains(@placeholder,'编号') or contains(@placeholder,'货品编号')]"),
            (By.XPATH, "//*[contains(text(),'货号')]/following::input[1]"),
        ], asin)

        # 产地
        self._try_input([
            (By.XPATH, "//input[contains(@placeholder,'产地') or contains(@placeholder,'生产地')]"),
            (By.XPATH, "//*[contains(text(),'产地')]/following::input[1]"),
        ], "中国")

        # 品牌
        if brand:
            self._try_input([
                (By.XPATH, "//input[contains(@placeholder,'品牌')]"),
                (By.XPATH, "//*[contains(text(),'品牌')]/following::input[1]"),
            ], brand)

        time.sleep(1)

        # Step4: 填写描述
        self.log("填写商品描述...")
        desc_sels = [
            (By.XPATH, "//textarea[contains(@placeholder,'描述') or contains(@placeholder,'详情')]"),
            (By.XPATH, "//*[contains(text(),'描述')]/following::textarea[1]"),
            (By.CSS_SELECTOR, ".product-desc textarea, .description textarea"),
        ]
        for by, sel in desc_sels:
            try:
                el = WebDriverWait(driver, 6).until(EC.presence_of_element_located((by, sel)))
                self.driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                self._js_input(el, desc_text)
                break
            except Exception:
                continue

        # 富文本编辑器
        try:
            editor = WebDriverWait(driver, 5).until(
                EC.presence_of_element_located((By.CSS_SELECTOR,
                    ".ql-editor, .ProseMirror, [contenteditable='true']")))
            self.driver.execute_script(
                "arguments[0].innerHTML = arguments[1];"
                "arguments[0].dispatchEvent(new Event('input',{bubbles:true}));",
                editor, desc_text.replace("\n", "<br>"))
        except Exception:
            pass

        # Step5: 填写价格
        if price_str:
            self.log("填写价格...")
            self._try_input([
                (By.XPATH, "//input[contains(@placeholder,'价格') or contains(@placeholder,'售价')]"),
                (By.XPATH, "//*[contains(text(),'价格')]/following::input[1]"),
                (By.CSS_SELECTOR, "input[name='price'], input[name='salePrice']"),
            ], price_str)

        # [DISABLED] # Step6: 上传图片
        # [DISABLED] img_url = info.get("image_url", "")
        # [DISABLED] if img_url:
        # [DISABLED] self.log("上传商品图片...")
        # [DISABLED] img_path = self._save_img_temp(img_url)
        # [DISABLED] if img_path:
        # [DISABLED] try:
        # [DISABLED] # 找到文件上传 input
        # [DISABLED] upload_inputs = driver.find_elements(
        # [DISABLED] By.XPATH, "//input[@type='file']"
        # [DISABLED] )
        # [DISABLED] for inp in upload_inputs:
        # [DISABLED] try:
        # [DISABLED] driver.execute_script("arguments[0].style.display='block';", inp)
        # [DISABLED] inp.send_keys(img_path)
        # [DISABLED] time.sleep(3)
        # [DISABLED] break
        # [DISABLED] except Exception:
        # [DISABLED] continue
        # [DISABLED] except Exception as e:
        # [DISABLED] self.log("图片上传失败: {}".format(e))
        # [DISABLED] finally:
        # [DISABLED] try: os.remove(img_path)
        # [DISABLED] except: pass

        # [DISABLED] time.sleep(2)

        # [DISABLED] # Step6.5: 自动上传主页图到"细节图"（最多5张）
        # [DISABLED] main_images = info.get("main_images", [])
        # [DISABLED] if main_images:
        # [DISABLED] self.log("自动上传 {} 张主页图到细节图...".format(len(main_images)))
        # [DISABLED] self._upload_detail_images(main_images)

        # Step7: 提交发布
        self.log("点击发布商品...")
        submitted = self._try_click([
            (By.XPATH, "//button[contains(text(),'发布商品')]"),
            (By.XPATH, "//button[contains(text(),'提交')]"),
            (By.XPATH, "//span[contains(text(),'发布商品')]"),
            (By.CSS_SELECTOR, ".submit-btn, .publish-btn"),
        ], timeout=10)
        if not submitted:
            raise Exception("未找到发布按钮，请手动完成发布")
        time.sleep(3)
        self.log("商品已提交发布")
        return True

    def _upload_detail_images(self, image_urls):
        """
        上传细节图到SHEIN商品发布页面。
        流程：
          1. 找到细节图区域的 file input（不依赖"点击上传"按钮文字）
          2. 逐张下载图片并通过 send_keys 上传
          3. 处理每次上传后可能弹出的"图片处理"裁剪弹框
        """
        if not image_urls:
            return
        driver = self.driver
        try:
            for idx, img_url in enumerate(image_urls):
                try:
                    self.log("上传细节图第 {} 张: {}".format(idx + 1, img_url[:60]))
                    img_path = self._save_img_temp(img_url)
                    if not img_path:
                        self.log("第 {} 张图片下载失败，跳过".format(idx + 1))
                        continue

                    # 找到所有 file input，优先找细节图区域的
                    file_inputs = driver.find_elements(
                        By.XPATH,
                        "//input[@type='file']"
                    )
                    if not file_inputs:
                        self.log("第 {} 张：未找到 file input，跳过".format(idx + 1))
                        try:
                            import os as _os
                            _os.remove(img_path)
                        except Exception:
                            pass
                        continue

                    # 使用最后一个可用的 file input（页面后半段的细节图区域）
                    uploaded = False
                    for file_input in reversed(file_inputs):
                        try:
                            driver.execute_script(
                                "arguments[0].style.display='block';"
                                "arguments[0].style.visibility='visible';"
                                "arguments[0].style.opacity='1';",
                                file_input
                            )
                            file_input.send_keys(img_path)
                            self.log("第 {} 张细节图已送入上传".format(idx + 1))
                            uploaded = True
                            break
                        except Exception:
                            continue

                    if not uploaded:
                        self.log("第 {} 张：send_keys 均失败，跳过".format(idx + 1))
                    else:
                        # 处理可能弹出的"图片处理"裁剪弹框
                        self._handle_crop_dialog()
                        time.sleep(1.5)

                    try:
                        import os as _os
                        _os.remove(img_path)
                    except Exception:
                        pass

                except Exception as e:
                    self.log("第 {} 张细节图上传失败: {}".format(idx + 1, str(e)[:80]))
                    continue

            self.log("细节图上传完成")
        except Exception as e:
            self.log("细节图上传过程出错: {}".format(str(e)[:80]))

if __name__ == "__main__":
    app=SheinApp()
    app.mainloop()
