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
from shein_sensitive_clean import SENSITIVE_WORDS, TITLE_SENSITIVE_WORDS, _filter_sensitive, _filter_title
from shein_login import SheinLoginManager
from shein_asin import HEADERS_POOL, AMAZON_PRODUCT_URL, fetch_amazon_product, download_image


try:
    from selenium import webdriver
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait, Select
    from selenium.webdriver.support import expected_conditions as EC
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from selenium.common.exceptions import TimeoutException, NoSuchElementException
    try:
        from selenium.webdriver.edge.options import Options as EdgeOptions
        from selenium.webdriver.edge.service import Service as EdgeService
    except ImportError:
        EdgeOptions = None
        EdgeService = None
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
SHEIN_PUBLISH_URL = "https://sso.geiwohuo.com/#/spmp/commoditiesCategory/followsales-pro/list"

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
BG_DARK="#1a1d2e"; BG_PANEL="#23263a"; BG_CARD="#2c2f45"
ACCENT="#e84393"; ACCENT2="#ff6bae"; TEXT_MAIN="#f0f0f0"
TEXT_SUB="#a0a3b1"; BORDER="#3a3d55"; GREEN="#4cde96"
YELLOW="#ffc857"; RED="#ff5f57"





from shein_uploader import SheinPublisher

if __name__ == '__main__':
    from shein_gui import SheinApp
    app = SheinApp()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            app.destroy()
        except Exception:
            pass
