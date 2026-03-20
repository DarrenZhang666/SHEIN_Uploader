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
     "Accept-Language": "zh-CN,zh;q=0.9", "Accept": "text/html,*/*;q=0.8"},
    {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64; rv:124.0) Gecko/20100101 Firefox/124.0",
     "Accept-Language": "en-US,en;q=0.5", "Accept": "text/html,*/*;q=0.8"},
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
           "description":"","features":[],"url":url}
    try:
        r = requests.Session().get(url, headers=hdrs, timeout=15)
        if r.status_code != 200:
            res["title"] = "HTTP {}".format(r.status_code); return res
        s = BeautifulSoup(r.text, "html.parser")
        t = s.select_one("#productTitle")
        if t: res["title"] = t.get_text(strip=True)
        for sel in ["#priceblock_ourprice",".a-price .a-offscreen",
                    "#priceblock_dealprice",".apexPriceToPay .a-offscreen"]:
            p = s.select_one(sel)
            if p: res["price"] = p.get_text(strip=True); break
        rt = s.select_one("span[data-hook='rating-out-of-text']")
        if rt:
            m = re.search(r"[\d.]+", rt.get_text())
            if m: res["rating"] = m.group()
        rv = s.select_one("#acrCustomerReviewText")
        if rv: res["reviews"] = rv.get_text(strip=True)
        br = s.select_one("#bylineInfo")
        if br: res["brand"] = br.get_text(strip=True)
        img = s.select_one("#landingImage,#imgBlkFront")
        if img:
            src = img.get("src") or ""
            res["image_url"] = img.get("data-old-hires") or img.get("data-a-hires") or src
        feats = [li.get_text(strip=True)
                 for li in s.select("#feature-bullets li span.a-list-item") if li.get_text(strip=True)]
        res["features"] = feats[:6]
        d = s.select_one("#productDescription p")
        if d: res["description"] = d.get_text(strip=True)[:300]
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
        self._fetch_thread=None; self._photo_ref=None
        self._shein_publisher=None   # 持久化浏览器实例
        self._stop_publish=False      # 停止上品标志
        self._driver_ready=False      # 驱动预热完成标志
        self._build_ui(); self._apply_styles()

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
        self._btn(bf,"导入 ASIN 文本",ACCENT,self._import_txt).pack(side="left",padx=5)
        self._btn(bf,"抓取选中商品","#2563eb",self._fetch_sel).pack(side="left",padx=5)
        self._btn(bf,"开始上品","#7c3aed",self._open_publish_page).pack(side="left",padx=5)
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
        """打开 SHEIN 登录页面（用系统默认浏览器，无需驱动）。"""
        webbrowser.open(SHEIN_LOGIN_URL)
        self.status_lbl.config(text='已在浏览器中打开 SHEIN 登录页，请手动登录')
        messagebox.showinfo('提示', '已在浏览器中打开 SHEIN 登录页\n\n请手动登录，登录完成后点击【开始上品】')

    def _open_publish_page(self):
        """打开 SHEIN 商品发布页面（用系统默认浏览器，无需驱动）。"""
        webbrowser.open(SHEIN_PUBLISH_URL)
        self.status_lbl.config(text='已在浏览器中打开商品发布页')
        messagebox.showinfo('提示', '已在浏览器中打开商品发布页\n\n请确保已登录 SHEIN 后台')

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
        row("ASIN: {}".format(info.get("asin","")),10,TEXT_SUB)
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
        """发布日志回调，可在子线程中安全调用。"""
        m = str(msg)[:100] if msg else ""
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
        """启动 Chrome。优先连接已有实例，其次用本地缓存驱动，最后才联网下载。"""
        import glob as _glob
        import shutil as _shutil
        _t0 = time.time()

        # 策略0：连接已有 Chrome 调试端口（秒级，超时0.5秒跳过）
        self.log("[DEBUG] 尝试连接已有 Chrome (0.5s超时)...")
        import threading as _th
        _conn_result = [None]
        def _try_connect():
            try:
                _o = Options()
                _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(self.DEBUG_PORT))
                _d = webdriver.Chrome(options=_o)
                _d.current_url
                _conn_result[0] = _d
            except Exception as _e:
                self.log("[DEBUG] 连接失败: {}".format(str(_e)[:40]))
        _conn_thread = _th.Thread(target=_try_connect, daemon=True)
        _conn_thread.start()
        _conn_thread.join(timeout=0.5)  # 最多等0.5秒
        if _conn_result[0] is not None:
            self.driver = _conn_result[0]
            self.wait = WebDriverWait(self.driver, 20)
            _t1 = time.time()
            self.log("[OK] 已连接到现有 Chrome ({:.1f}s)".format(_t1 - _t0))
            return
        else:
            self.log("[DEBUG] 连接超时或失败，启动新 Chrome...")

        opts = Options()
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
        opts.add_argument("--disable-component-extensions-with-background-pages")
        opts.add_argument("--disable-default-apps")
        opts.add_argument("--disable-preconnect")
        opts.add_argument("--disable-sync")
        opts.add_argument("--metrics-recording-only")
        opts.add_argument("--mute-audio")
        opts.add_argument("--no-default-browser-check")
        opts.add_argument("--no-pings")
        opts.add_argument("user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
        opts.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging", "enable-features"])
        opts.add_experimental_option("useAutomationExtension", False)
        opts.add_experimental_option("w3c", False)
        opts.add_argument("--remote-debugging-port={}".format(self.DEBUG_PORT))

        import tempfile as _tmp
        _profile = os.path.join(_tmp.gettempdir(), ".shein_chrome")
        os.makedirs(_profile, exist_ok=True)
        opts.add_argument("--user-data-dir={}".format(_profile))

        def _cdp_hide_webdriver(drv):
            try:
                # 隐藏 navigator.webdriver
                drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                    "source": """
                        Object.defineProperty(navigator, 'webdriver', {
                            get: () => undefined
                        });
                        Object.defineProperty(navigator, 'plugins', {
                            get: () => [1, 2, 3, 4, 5]
                        });
                        Object.defineProperty(navigator, 'languages', {
                            get: () => ['zh-CN', 'zh', 'en-US', 'en']
                        });
                        window.chrome = {
                            runtime: {}
                        };
                    """
                })
            except Exception:
                pass

        # 策略1：查找本地已缓存的 chromedriver（无需联网）
        _candidates = []
        self.log("[DEBUG] 查找本地 chromedriver...")
        _t_search = time.time()
        # 先尝试 PATH 里的 chromedriver（最快）
        _path_driver = _shutil.which("chromedriver")
        if _path_driver:
            self.log("[DEBUG] 找到 PATH chromedriver: {}".format(_path_driver))
            _candidates.append(_path_driver)
        # 再查找常见缓存目录
        for _base in [
            os.path.join(os.path.expanduser("~"), ".cache", "selenium"),
            os.path.join(os.path.expanduser("~"), ".wdm", "drivers", "chromedriver"),
        ]:
            if os.path.isdir(_base):
                _found = _glob.glob(os.path.join(_base, "**", "chromedriver.exe"), recursive=True)
                if _found:
                    self.log("[DEBUG] 找到 {} 个缓存 chromedriver".format(len(_found)))
                _candidates += _found
        _candidates += [
            r"C:\chromedriver\chromedriver.exe",
            r"C:\chromedriver-win64\chromedriver.exe",
        ]
        _t_search_end = time.time()
        self.log("[DEBUG] 查找耗时 {:.1f}s, 找到 {} 个候选".format(_t_search_end - _t_search, len(_candidates)))

        for _i, _cp in enumerate(sorted(set([p for p in _candidates if os.path.isfile(p)]), key=os.path.getmtime, reverse=True)):
            try:
                self.log("[DEBUG] 尝试第 {} 个驱动: {}".format(_i+1, os.path.basename(_cp)))
                _t_start = time.time()
                self.driver = webdriver.Chrome(service=Service(_cp), options=opts)
                _t_end = time.time()
                self.log("[OK] 使用本地驱动 ({:.1f}s)".format(_t_end - _t_start))
                self.wait = WebDriverWait(self.driver, 20)
                _cdp_hide_webdriver(self.driver)
                _t_total = time.time()
                self.log("[TOTAL] Chrome 启动完成 ({:.1f}s)".format(_t_total - _t0))
                return
            except Exception as _e:
                self.log("[DEBUG] 驱动失败: {}".format(str(_e)[:60]))
                self.driver = None

        # 策略2：如果本地驱动都失败，提示用户手动下载驱动
        self.log("[ERROR] 未找到匹配的本地 chromedriver")
        raise RuntimeError(
            "无法启动 Chrome！\n\n"
            "原因：找不到与当前 Chrome 版本匹配的 chromedriver\n\n"
            "解决方案：\n"
            "1. 下载与你的 Chrome 版本匹配的 chromedriver\n"
            "   访问: https://googlechromelabs.github.io/chrome-for-testing/\n"
            "2. 将 chromedriver.exe 放在以下任一位置：\n"
            "   - C:\\chromedriver\\\n"
            "   - 项目目录\n"
            "   - 系统 PATH 环境变量中\n"
            "3. 重新运行程序"
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

        # Step6: 上传图片
        img_url = info.get("image_url", "")
        if img_url:
            self.log("上传商品图片...")
            img_path = self._save_img_temp(img_url)
            if img_path:
                try:
                    # 找到文件上传 input
                    upload_inputs = driver.find_elements(
                        By.XPATH, "//input[@type='file']"
                    )
                    for inp in upload_inputs:
                        try:
                            driver.execute_script("arguments[0].style.display='block';", inp)
                            inp.send_keys(img_path)
                            time.sleep(3)
                            break
                        except Exception:
                            continue
                except Exception as e:
                    self.log("图片上传失败: {}".format(e))
                finally:
                    try: os.remove(img_path)
                    except: pass

        time.sleep(2)

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


if __name__ == "__main__":
    app=SheinApp()
    app.mainloop()
