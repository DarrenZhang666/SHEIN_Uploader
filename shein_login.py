# -*- coding: utf-8 -*-
"""
SHEIN 登录模块
处理浏览器启动、登录检测等功能
"""
import os
import time
import threading
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service

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


class SheinLoginManager:
    """SHEIN 登录管理器"""
    
    HOME_URL    = "https://sso.geiwohuo.com/#/home"
    LOGIN_URL   = "https://sso.geiwohuo.com/#/login"
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

    def start_browser(self):
        """启动浏览器。先尝试连接已有实例，失败则自动起动新实例。"""
        import threading as _th
        import shutil as _shutil
        _t0 = time.time()

        # 策略0: 先尝试连接已有 Edge 调试端口（3s超时）
        _conn_result = [None]
        def _try_connect_edge():
            try:
                _o = EdgeOptions()
                _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(self.DEBUG_PORT))
                _d = webdriver.Edge(options=_o)
                _d.current_url  # 验证连接有效
                _conn_result[0] = _d
            except Exception:
                pass
        _t = _th.Thread(target=_try_connect_edge, daemon=True)
        _t.start(); _t.join(timeout=3)
        if _conn_result[0] is not None:
            self.driver = _conn_result[0]
            self.wait = WebDriverWait(self.driver, 20)
            self.log("[OK] 已连接到现有 Edge ({:.1f}s)".format(time.time() - _t0))
            return

        # 策略1: 先尝试连接已有 Chrome 调试端口（3s超时）
        _conn_result2 = [None]
        def _try_connect_chrome():
            try:
                _o = Options()
                _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(self.DEBUG_PORT))
                _d = webdriver.Chrome(options=_o)
                _d.current_url
                _conn_result2[0] = _d
            except Exception:
                pass
        _t2 = _th.Thread(target=_try_connect_chrome, daemon=True)
        _t2.start(); _t2.join(timeout=3)
        if _conn_result2[0] is not None:
            self.driver = _conn_result2[0]
            self.wait = WebDriverWait(self.driver, 20)
            self.log("[OK] 已连接到现有 Chrome ({:.1f}s)".format(time.time() - _t0))
            return

        # 先检测调试端口是否被占用，若占用说明有浏览器在运行但连接失败，再重试
        import socket as _socket
        _port_in_use = False
        try:
            _sock = _socket.create_connection(("127.0.0.1", self.DEBUG_PORT), timeout=0.5)
            _sock.close()
            _port_in_use = True
        except Exception:
            pass
        if _port_in_use:
            self.log("[WARN] 调试端口{}已被占用，再次尝试连接现有浏览器...".format(self.DEBUG_PORT))
            _conn_retry = [None]
            def _retry_edge():
                try:
                    _o = EdgeOptions()
                    _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(self.DEBUG_PORT))
                    _d = webdriver.Edge(options=_o)
                    _d.current_url
                    _conn_retry[0] = _d
                except Exception:
                    pass
            _tr = _th.Thread(target=_retry_edge, daemon=True)
            _tr.start(); _tr.join(timeout=5)
            if _conn_retry[0] is not None:
                self.driver = _conn_retry[0]
                self.wait = WebDriverWait(self.driver, 20)
                self.log("[OK] 重试连接现有 Edge 成功 ({:.1f}s)".format(time.time() - _t0))
                return

        # 策略2: 启动新 Edge（由 Selenium 自动管理驱动）
        self.log("[DEBUG] 启动新 Edge 浏览器...")
        _profile = os.path.join(os.path.expanduser("~"), ".shein_browser_profile")
        os.makedirs(_profile, exist_ok=True)

        def _make_opts(opt_class):
            o = opt_class()
            o.add_argument("--disable-blink-features=AutomationControlled")
            o.add_argument("--no-sandbox")
            o.add_argument("--disable-dev-shm-usage")
            o.add_argument("--disable-gpu")
            o.add_argument("--disable-infobars")
            o.add_argument("--remote-debugging-port={}".format(self.DEBUG_PORT))
            o.add_argument("--user-data-dir={}".format(_profile))
            o.add_argument("--profile-directory=Default")
            o.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            o.add_experimental_option("useAutomationExtension", False)
            return o

        def _hide_webdriver(drv):
            try:
                drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"})
            except Exception:
                pass

        # 尝试 Edge（Selenium 自动匹配驱动）
        try:
            edge_opts = _make_opts(EdgeOptions)
            self.driver = webdriver.Edge(options=edge_opts)
            self.wait = WebDriverWait(self.driver, 20)
            _hide_webdriver(self.driver)
            self.log("[OK] Edge 启动成功 ({:.1f}s)".format(time.time() - _t0))
            return
        except Exception as _e:
            self.log("[DEBUG] Edge 失败: {}".format(str(_e)[:80]))

        # 尝试 Chrome（Selenium 自动匹配驱动）
        try:
            chrome_opts = _make_opts(Options)
            self.driver = webdriver.Chrome(options=chrome_opts)
            self.wait = WebDriverWait(self.driver, 20)
            _hide_webdriver(self.driver)
            self.log("[OK] Chrome 启动成功 ({:.1f}s)".format(time.time() - _t0))
            return
        except Exception as _e:
            self.log("[DEBUG] Chrome 失败: {}".format(str(_e)[:80]))

        raise RuntimeError(
            "无法启动浏览器！\n\n"
            "请确保已安装 Microsoft Edge 或 Google Chrome\n"
            "Selenium 会自动下载匹配的驱动程序，请确保网络可用")

    def open_login(self):
        """打开登录页面"""
        self.driver.get(self.LOGIN_URL)

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

    def quit(self):
        """关闭浏览器"""
        try:
            if self.driver:
                self.driver.quit()
        except Exception:
            pass
