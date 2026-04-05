# -*- coding: utf-8 -*-
"""
SHEIN 登录模块
处理浏览器启动、登录检测等功能
"""
import os
import time
import threading
import shutil
try:
    import winreg
except Exception:
    winreg = None
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

    def _disable_ie_esc_notice(self):
        """禁用 IE 增强安全提示，避免登录后弹窗阻塞。"""
        if winreg is None:
            return
        try:
            esc_keys = [
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A7-37EF-4b3f-8CFC-4F3A74704073}"),
                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Microsoft\Active Setup\Installed Components\{A509B1A8-37EF-4b3f-8CFC-4F3A74704073}"),
            ]
            for hive, subkey in esc_keys:
                try:
                    k = winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE)
                    winreg.SetValueEx(k, "IsInstalled", 0, winreg.REG_DWORD, 0)
                    winreg.CloseKey(k)
                except Exception:
                    pass

            try:
                sogou_key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    r"SOFTWARE\Microsoft\Windows\CurrentVersion\Internet Settings\ZoneMap\Domains\sogou.com\config\pinyin",
                )
                winreg.SetValueEx(sogou_key, "http", 0, winreg.REG_DWORD, 2)
                winreg.CloseKey(sogou_key)
            except Exception:
                pass
        except Exception:
            pass

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

    def _get_debug_port(self, account=""):
        """根据账号生成独立的调试端口号，避免多账号冲突。"""
        if not account:
            return self.DEBUG_PORT
        h = 0
        for ch in account:
            h = (h * 31 + ord(ch)) & 0xFFFF
        return 9300 + (h % 200)

    def _safe_profile_name(self, account=""):
        import re as _re
        return _re.sub(r'[^\w\-.]', '_', account) if account else "default"

    def _clone_profile_best_effort(self, src_profile, dst_profile):
        """
        尽力复制浏览器 profile（跳过锁文件/临时文件），用于并发线程快速复用登录态。
        返回 (copied_count, skipped_count)。
        """
        copied = 0
        skipped = 0
        if not os.path.isdir(src_profile):
            return copied, skipped

        skip_names = {
            "LOCK", "lockfile", "SingletonLock", "SingletonCookie",
            "SingletonSocket", "DevToolsActivePort"
        }

        for root, dirs, files in os.walk(src_profile):
            rel = os.path.relpath(root, src_profile)
            dst_root = dst_profile if rel == "." else os.path.join(dst_profile, rel)
            try:
                os.makedirs(dst_root, exist_ok=True)
            except Exception:
                skipped += len(files)
                continue

            for fn in files:
                try:
                    if fn in skip_names or fn.lower().endswith(".lock"):
                        skipped += 1
                        continue
                    src_f = os.path.join(root, fn)
                    dst_f = os.path.join(dst_root, fn)
                    shutil.copy2(src_f, dst_f)
                    copied += 1
                except Exception:
                    skipped += 1
                    continue
        return copied, skipped

    def start_browser(self, account="", clone_from_account="", headless=False, force_new=False):
        """启动浏览器。同一账号复用实例，不同账号用独立 profile 和端口。"""
        import socket as _socket
        _t0 = time.time()
        self._disable_ie_esc_notice()

        # 同一个 LoginManager 已有可用 driver 时，默认直接复用，避免重复拉起 driver 进程
        try:
            if self.driver is not None and (not force_new):
                _ = self.driver.current_url
                self.wait = WebDriverWait(self.driver, 20)
                self.log("[OK] 复用当前浏览器会话 ({:.1f}s)".format(time.time() - _t0))
                return
        except Exception:
            try:
                if self.driver:
                    self.driver.quit()
            except Exception:
                pass
            self.driver = None
            self.wait = None

        _port = self._get_debug_port(account)
        self.log("[DEBUG] 账号='{}' 调试端口={}".format(account or "(默认)", _port))

        # 先快速检测端口是否有浏览器在监听（<0.3s）
        _port_open = False
        try:
            _sock = _socket.create_connection(("127.0.0.1", _port), timeout=0.3)
            _sock.close()
            _port_open = True
        except Exception:
            pass

        if _port_open and (not force_new):
            # 端口有响应 → 串行尝试连接，避免同一次调用额外拉起多个 driver 进程
            try:
                _o = EdgeOptions()
                _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(_port))
                _d = webdriver.Edge(options=_o)
                _d.current_url
                self.driver = _d
                self.wait = WebDriverWait(self.driver, 20)
                self.log("[OK] 已连接到现有 Edge ({:.1f}s)".format(time.time() - _t0))
                return
            except Exception:
                pass
            try:
                _o = Options()
                _o.add_experimental_option("debuggerAddress", "127.0.0.1:{}".format(_port))
                _d = webdriver.Chrome(options=_o)
                _d.current_url
                self.driver = _d
                self.wait = WebDriverWait(self.driver, 20)
                self.log("[OK] 已连接到现有 Chrome ({:.1f}s)".format(time.time() - _t0))
                return
            except Exception:
                pass
            self.log("[DEBUG] 端口{}有响应但连接失败，启动新浏览器".format(_port))

        # 启动新浏览器 — 每个账号独立的 profile 目录
        _safe_name = self._safe_profile_name(account)
        _profile = os.path.join(
            os.path.expanduser("~"), ".shein_profiles", _safe_name)
        _profile_exists = os.path.isdir(_profile)
        _profile_empty = (not _profile_exists) or (len(os.listdir(_profile)) == 0 if _profile_exists else True)

        if clone_from_account and clone_from_account != account and _profile_empty:
            _clone_name = self._safe_profile_name(clone_from_account)
            _src_profile = os.path.join(os.path.expanduser("~"), ".shein_profiles", _clone_name)
            if os.path.isdir(_src_profile):
                try:
                    os.makedirs(_profile, exist_ok=True)
                    copied, skipped = self._clone_profile_best_effort(_src_profile, _profile)
                    self.log("[DEBUG] 已克隆登录 profile: {} -> {} (复制{} 跳过{})".format(
                        _clone_name, _safe_name, copied, skipped))
                except Exception as _ce:
                    self.log("[DEBUG] 克隆 profile 失败: {}".format(str(_ce)[:80]))
            else:
                os.makedirs(_profile, exist_ok=True)
        else:
            os.makedirs(_profile, exist_ok=True)
        self.log("[DEBUG] 启动新浏览器, profile={}".format(_profile))

        def _make_opts(opt_class):
            o = opt_class()
            o.add_argument("--disable-blink-features=AutomationControlled")
            o.add_argument("--no-sandbox")
            o.add_argument("--disable-dev-shm-usage")
            o.add_argument("--disable-gpu")
            o.add_argument("--disable-infobars")
            o.add_argument("--disable-extensions")
            o.add_argument("--host-rules=MAP config.pinyin.sogou.com 127.0.0.1")
            o.add_argument("--remote-debugging-port={}".format(_port))
            o.add_argument("--user-data-dir={}".format(_profile))
            o.add_argument("--profile-directory=Default")
            if headless:
                o.add_argument("--headless=new")
                o.add_argument("--window-size=1366,900")
            o.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
            o.add_experimental_option("useAutomationExtension", False)
            return o

        def _hide_webdriver(drv):
            try:
                drv.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument",
                    {"source": "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"})
            except Exception:
                pass

        try:
            edge_opts = _make_opts(EdgeOptions)
            self.driver = webdriver.Edge(options=edge_opts)
            self.wait = WebDriverWait(self.driver, 20)
            _hide_webdriver(self.driver)
            self.log("[OK] Edge 启动成功 ({:.1f}s)".format(time.time() - _t0))
            return
        except Exception as _e:
            self.log("[DEBUG] Edge 失败: {}".format(str(_e)[:80]))

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
                _drv = self.driver
                try:
                    _drv.quit()
                except Exception:
                    pass
                # 兜底：终止残留的 webdriver service 进程（若存在）
                try:
                    _svc = getattr(_drv, "service", None)
                    _proc = getattr(_svc, "process", None) if _svc is not None else None
                    if _proc is not None and _proc.poll() is None:
                        _proc.terminate()
                except Exception:
                    pass
        except Exception:
            pass
        finally:
            self.driver = None
            self.wait = None
