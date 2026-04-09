# -*- coding: utf-8 -*-
"""GUI layer for SHEIN app."""

from shein_main import *
from concurrent.futures import ThreadPoolExecutor, as_completed, TimeoutError as FutureTimeoutError
import tkinter.font as tkfont
import subprocess
from shein_developer_mode import DevModeToggle, is_dev_mode
from shein_mysql import verify_shein_account_detail
from shein_checkprice import (
    fetch_shein_pending_bargain_rows,
    dismiss_shein_user_guides,
    trigger_shein_pending_bargain_action,
)
from datetime import datetime
try:
    from shein_asin import _canonicalize_shein_color, _split_color_candidates, _normalize_color_token
except Exception:
    _canonicalize_shein_color = None
    _split_color_candidates = None
    _normalize_color_token = None

class SheinApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self._ui_thread_id = threading.get_ident()
        self.title("SHEIN 商品采集 & 发布工具V1.25")
        self.geometry("1280x800"); self.minsize(1000,680)
        self.configure(bg=BG_DARK)
        self.asin_list=[]; self.asin_vars={}; self.asin_dots={}; self.asin_status={}
        self.asin_row_widgets={}
        self.asin_progress={}
        self.product_cache={}; self.current_asin=None
        self.select_all_var=tk.BooleanVar(value=False)
        self.price_multiplier=tk.StringVar(value="5")
        self.fetch_workers=tk.StringVar(value="3")
        self.amazon_region=tk.StringVar(value="美国")
        self.shein_account=tk.StringVar(value="")
        self.current_view_mode = "collect_publis1h"  # collect_publish / bargain
        self._fetch_thread=None; self._photo_ref=None
        self._launching_browser = False  # 防止重复点击登录按钮
        self._shein_publisher=None   # 持久化浏览器实例
        self._shein_publisher_account = ""  # 当前浏览器实例对应的账号
        self._stop_publish=False      # 停止上品标志
        self._driver_ready=False      # 驱动预热完成标志
        self._publish_running=False   # 当前是否正在执行上品流程
        self._publish_session_id = 0  # 上品会话ID（用于中断旧线程）
        self._worker_publishers = {}  # 多线程worker浏览器实例 {worker_idx: publisher}
        self._worker_active_asins = {}  # 多线程worker当前处理ASIN {worker_idx: asin}
        self._worker_publishers_lock = threading.Lock()
        self._stop_cleanup_running = False  # 避免重复触发停止清理线程
        self._login_cookies = []      # 登录会话快照：cookies
        self._login_storage = {}      # 登录会话快照：localStorage
        self._login_session_storage = {}  # 登录会话快照：sessionStorage
        self._login_session_account = ""  # 最近一次登录会话所属账号
        # 详情主图缓存（URL -> PhotoImage），减少切换商品时重复下载
        self._preview_photo_cache = {}
        self._preview_cache_order = []
        self._preview_cache_max = 80
        self._preview_cache_lock = threading.Lock()
        self._current_preview_url = ""
        self._preview_inflight = set()
        self._sku_render_after_id = None
        self._detail_switch_after_id = None
        self._asin_wheel_after_id = None
        self._asin_wheel_accum = 0
        self._asin_virtual_after_id = None
        self._asin_row_height = 34
        self._asin_row_buffer = 10
        self._asin_visible_range = (-1, -1)
        self._asin_index_map = {}
        self._active_publish_asin = None
        self._verified_accounts: set[str] = set()
        self._account_auth_periods = {}  # account -> (start_raw, end_raw)
        self._auth_check_interval_ms = 60 * 60 * 1000  # 每小时复检一次账号授权
        self._auth_check_after_id = None
        self._auth_watch_account = ""
        self._license_locked = False
        self._license_locked_reason = ""
        self._app_closing = False
        self._bargain_rows = []
        self._bargain_progress_percent = 0.0
        self._bargain_fetch_thread = None
        self._bargain_fetch_running = False
        self._stop_bargain_fetch = False
        self._bargain_runtime_publisher = None
        self._bargain_runtime_is_temp = False
        self._bargain_action_running = False
        self._bargain_batch_running = False
        self._bargain_action_lock = threading.Lock()
        self._bargain_row_uid_seq = 1
        self._bargain_rowid_to_index = {}
        self._bargain_sort_column = ""
        self._bargain_sort_desc = True
        self._bargain_filter_platform_var = tk.StringVar(value="")
        self._bargain_filter_amazon_var = tk.StringVar(value="")
        self._bargain_filter_profit_var = tk.StringVar(value="")
        # 开关：是否在议价界面补充“亚马逊价格/利润率”
        self._enable_bargain_amazon_metrics = True
        self._load_bargain_table_prefs()
        
        # 初始化日志文件
        self._init_log_file()
        
        self._build_ui(); self._apply_styles()
        self.protocol("WM_DELETE_WINDOW", self._on_app_close)
        # 兜底：任何路径导致根窗口销毁时，都确保进程退出
        self.bind("<Destroy>", self._on_root_destroy, add="+")

    def _init_log_file(self):
        """初始化日志目录（所有模式均可落盘）。"""
        desktop = os.path.join(os.path.expanduser("~"), "Desktop")
        os.makedirs(desktop, exist_ok=True)
        self._log_dir = os.path.join(desktop, "SHEIN_Logs")
        self.log_file = None

    def _ensure_log_file(self):
        """懒创建日志文件。"""
        if self.log_file:
            return
        os.makedirs(self._log_dir, exist_ok=True)
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        self.log_file = os.path.join(self._log_dir, "log_{}.txt".format(timestamp))
        try:
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("[{}] === SHEIN 商品采集工具日志 ===\n".format(time.strftime("%H:%M:%S")))
                f.write("[{}] 启动时间: {}\n".format(
                    time.strftime("%H:%M:%S"), time.strftime("%Y-%m-%d %H:%M:%S")))
                f.write("[{}] \n".format(time.strftime("%H:%M:%S")))
        except Exception:
            pass

    def _write_log(self, msg):
        """写入日志文件。"""
        try:
            self._ensure_log_file()
            with open(self.log_file, 'a', encoding='utf-8') as f:
                f.write("[{}] {}\n".format(time.strftime("%H:%M:%S"), msg))
        except Exception:
            pass

    @staticmethod
    def _is_simple_publish_msg(msg):
        """非开发者模式下，仅允许显示简化上品进度日志。"""
        if not msg:
            return False
        if not re.search(r"\bB[A-Z0-9]{9}\b", msg):
            return False
        return any(k in msg for k in ("开始上品", "上品中", "上品成功", "上品失败"))

    def _log_publish_progress(self, asin, stage):
        """统一输出简化上品进度日志。"""
        if not asin:
            return
        # 直接按 ASIN 更新，避免多线程日志路由时序导致串行/错位。
        try:
            s = str(stage or "")
            if s == "开始上品":
                self._set_asin_progress(asin, 10, "开始上品", state="running")
            elif s == "上品中":
                self._set_asin_progress(asin, 15, "上品中", state="running")
            elif s == "上品成功":
                self._set_asin_progress(asin, 100, "上品成功", state="success")
            elif s == "上品失败":
                self._set_asin_progress(asin, 100, "上品失败", state="fail")
        except Exception:
            pass
        self._pub_log("{} {}".format(asin, stage))

    def _set_publish_status(self, asin, detailed_msg, stage_for_non_dev=None):
        """
        发布流程状态栏输出：
        - 开发者模式：显示 detailed_msg
        - 非开发者模式：仅显示「ASIN + 开始/上品中/上品成功/上品失败」
        """
        if not hasattr(self, "status_lbl"):
            return
        if is_dev_mode():
            self.after(0, lambda m=str(detailed_msg)[:100]: self.status_lbl.config(text=m))
            return
        if asin and stage_for_non_dev:
            self.after(0, lambda a=asin, s=stage_for_non_dev: self.status_lbl.config(text="{} {}".format(a, s)))

    @staticmethod
    def _is_publish_page_ready(driver):
        """判定是否已进入 SHEIN 商品发布页（URL+DOM 双通道）。"""
        if driver is None:
            return False
        try:
            cur = str(driver.current_url or "").lower()
        except Exception:
            cur = ""
        if ("followsales-pro/list" in cur) and ("commoditiescategory" in cur or "commodities-category" in cur):
            return True
        try:
            return bool(driver.execute_script(r"""
                const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
                const body = document && document.body ? clean(document.body.innerText || '') : '';
                if (body.includes('识图发品') || body.includes('上传图片') || body.includes('商品发布')) return true;
                if (document.querySelector("input[type='file']")) return true;
                const nodes = Array.from(document.querySelectorAll('button,span,div,a'));
                for (const n of nodes) {
                    const t = clean(n.innerText || n.textContent || '');
                    if (!t) continue;
                    if (t.includes('识图发品') || t.includes('上传图片') || t.includes('确认，下一步')) return true;
                }
                return false;
            """))
        except Exception:
            return False

    def _is_chinese_page(self, driver):
        """检测当前页面是否为中文界面。"""
        try:
            txt = driver.execute_script(
                "return document && document.body ? (document.body.innerText || '') : '';"
            ) or ""
            if not txt:
                return False
            # 关键文案命中优先判定
            keywords = ("中文", "卖家中心", "发布商品", "识图发品", "确认，下一步")
            if any(k in txt for k in keywords):
                return True
            # 兜底：统计中文字符数量
            zh_count = len(re.findall(r"[\u4e00-\u9fff]", txt))
            return zh_count >= 20
        except Exception:
            return False

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
        self._main_body = body
        self._left_panel_min_width = 280
        self._left_panel_max_width = 720
        self._left_panel_default_width = 320
        self._left_resize_hotzone = 12
        body.columnconfigure(0,weight=0,minsize=self._left_panel_min_width)
        body.columnconfigure(1,weight=1)
        body.rowconfigure(0,weight=1)
        self._build_left(body); self._build_right(body)


        self._build_bargain_panel(body)
        self._toggle_main_panels_for_mode()
        self._dev_toggle = DevModeToggle(self, bg=BG_DARK)
        self._dev_toggle.place(relx=0.0, rely=1.0, anchor="sw", x=16, y=-6)
        self._license_lbl = tk.Label(
            self,
            text="软件有效期：未验证",
            font=("Segoe UI", 10, "bold"),
            fg=RED,
            bg=BG_DARK,
        )
        self._license_lbl.place(relx=1.0, rely=1.0, anchor="se", x=-16, y=-6)

    def _build_topbar(self):
        bar=tk.Frame(self,bg=BG_PANEL,height=60)
        bar.pack(fill="x"); bar.pack_propagate(False)
        lg=tk.Frame(bar,bg=BG_PANEL); lg.pack(side="left",padx=20)
        tk.Label(lg,text="SHEIN",font=("Segoe UI",18,"bold"),fg=ACCENT,bg=BG_PANEL).pack(side="left")
        mode_wrap = tk.Frame(lg, bg=BG_PANEL)
        mode_wrap.pack(side="left", padx=(12,0))
        self._mode_collect_btn = tk.Button(
            mode_wrap,
            text="商品采集&发布",
            bg=ACCENT,
            fg="white",
            font=("Segoe UI",10,"bold"),
            relief="flat",
            bd=0,
            width=10,
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self._switch_view_mode("collect_publish")
        )
        self._mode_collect_btn.pack(side="left", padx=(0,6))
        self._mode_bargain_btn = tk.Button(
            mode_wrap,
            text="议价",
            bg=BG_CARD,
            fg=TEXT_MAIN,
            font=("Segoe UI",10,"bold"),
            relief="flat",
            bd=0,
            width=5,
            padx=10,
            pady=5,
            cursor="hand2",
            command=lambda: self._switch_view_mode("bargain")
        )
        self._mode_bargain_btn.pack(side="left")
        bf=tk.Frame(bar,bg=BG_PANEL); bf.pack(side="right",padx=20,pady=10)
        # 售价倍数输入框（在最后添加，寄弹出效果为最左侧）
        pm_frame=tk.Frame(bf,bg=BG_PANEL)
        pm_frame.pack(side="left",padx=(0,10))
        tk.Label(pm_frame,text="售价倍数:",font=("Segoe UI",10),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        tk.Entry(pm_frame,textvariable=self.price_multiplier,width=4,font=("Segoe UI",10),bg=BG_CARD,fg=TEXT_MAIN,insertbackground=TEXT_MAIN,relief="flat",bd=2).pack(side="left",padx=(4,0))
        fw_frame=tk.Frame(bf,bg=BG_PANEL)
        fw_frame.pack(side="left",padx=(0,10))
        tk.Label(fw_frame,text="运行线程:",font=("Segoe UI",10),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        tk.Entry(fw_frame,textvariable=self.fetch_workers,width=4,font=("Segoe UI",10),bg=BG_CARD,fg=TEXT_MAIN,insertbackground=TEXT_MAIN,relief="flat",bd=2).pack(side="left",padx=(4,0))
        self._import_btn = self._btn(bf,"导入 ASIN 文本",ACCENT,self._import_txt)
        self._import_btn.pack(side="left",padx=5)
        self._fetch_btn = self._btn(bf,"抓取选中商品","#2563eb",self._fetch_sel)
        self._fetch_btn.pack(side="left",padx=5)
        self._publish_btn = self._btn(bf,"开始上品","#7c3aed",self._open_publish_page)
        self._publish_btn.pack(side="left",padx=5)
        self._suggest_price_btn = self._btn(bf,"抓取SHEIN建议价格","#0ea5a4",self._fetch_shein_suggest_price)
        
        self._stop_btn = self._btn(bf,"停止","#dc2626",self._stop_publish_action)
        self._stop_btn.pack(side="left",padx=5)
        self._shein_login_btn = self._btn(bf,"登录 SHEIN","#059669",self._open_shein)
        self._shein_login_btn.pack(side="left",padx=5)
        acct_frame=tk.Frame(bf,bg=BG_PANEL)
        acct_frame.pack(side="left",padx=(5,0))
        tk.Label(acct_frame,text="SHEIN账号:",font=("Segoe UI",10),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        self._acct_combo = ttk.Combobox(acct_frame, textvariable=self.shein_account,
            width=18, font=("Segoe UI",10), values=self._load_account_history())
        self._acct_combo.pack(side="left",padx=(4,0))
        self._apply_view_mode()
        self._toggle_main_panels_for_mode()

    def _switch_view_mode(self, mode):
        if mode not in ("collect_publish", "bargain"):
            return
        if self.current_view_mode == mode:
            return
        self.current_view_mode = mode
        self._apply_view_mode()
        self._toggle_main_panels_for_mode()

    def _apply_view_mode(self):
        if not hasattr(self, "_mode_collect_btn"):
            return

        if self.current_view_mode == "bargain":
            self._mode_collect_btn.config(bg=BG_CARD, fg=TEXT_MAIN)
            self._mode_bargain_btn.config(bg=ACCENT, fg="white")

            if hasattr(self, "_import_btn"):
                self._import_btn.pack_forget()
            if hasattr(self, "_fetch_btn"):
                self._fetch_btn.pack_forget()
            if hasattr(self, "_publish_btn"):
                self._publish_btn.pack_forget()

            if hasattr(self, "_suggest_price_btn"):
                self._suggest_price_btn.pack(side="left", padx=5, before=self._shein_login_btn)

            if hasattr(self, "status_lbl"):
                self.status_lbl.config(text="当前为【议价】界面")
        else:
            self._mode_collect_btn.config(bg=ACCENT, fg="white")
            self._mode_bargain_btn.config(bg=BG_CARD, fg=TEXT_MAIN)

            if hasattr(self, "_suggest_price_btn"):
                self._suggest_price_btn.pack_forget()

            if hasattr(self, "_import_btn"):
                self._import_btn.pack(side="left", padx=5, before=self._shein_login_btn)
            if hasattr(self, "_fetch_btn"):
                self._fetch_btn.pack(side="left", padx=5, before=self._shein_login_btn)
            if hasattr(self, "_publish_btn"):
                self._publish_btn.pack(side="left", padx=5, before=self._shein_login_btn)

            if hasattr(self, "status_lbl"):
                self.status_lbl.config(text="请先导入 ASIN 文件")

    def _fetch_shein_suggest_price(self):
        if self._license_locked:
            self._show_auth_lock_popup()
            return
        if getattr(self, "_bargain_fetch_running", False):
            messagebox.showinfo("议价", "正在抓取中，请先等待当前任务完成或点击“停止”")
            return
        account = self.shein_account.get().strip()
        if not account:
            messagebox.showwarning('提示', '请先在「SHEIN账号」输入框中填写账号')
            return
        if not self._verify_account(account):
            return

        dev_mode = bool(is_dev_mode())
        fetch_publisher = self._shein_publisher if dev_mode else None
        headless_mode = (not dev_mode)
        force_new_browser = (not dev_mode)

        self._stop_bargain_fetch = False
        self._bargain_fetch_running = True
        self._bargain_runtime_publisher = None
        self._bargain_runtime_is_temp = (not dev_mode)
        self.status_lbl.config(text='议价功能：正在抓取“待确认”数据...')
        self._set_bargain_progress("进入议价界面", state="running", percent=25)

        def _run():
            temp_pub = None
            keep_runtime_after_fetch = False
            try:
                import re
                progress_state = {"total_pages": 1}

                def _progress_log(msg):
                    self._pub_log(msg)
                    t = str(msg or "")
                    if "打开商品列表页面" in t:
                        self.after(
                            0,
                            lambda: self._set_bargain_progress("进入议价界面（加载页面）", state="running", percent=30),
                        )
                        return
                    if ("已点击“价格调整待确认，请及时处理”" in t) or ("重试后已点击“价格调整待确认，请及时处理”" in t):
                        self.after(
                            0,
                            lambda: self._set_bargain_progress("进入议价界面（打开待办任务）", state="running", percent=38),
                        )
                        return
                    if ("已点击“待确认”筛选按钮" in t) or ("已通过JS兜底点击“待确认”筛选按钮" in t):
                        self.after(
                            0,
                            lambda: self._set_bargain_progress("抓取第1页数据", state="running", percent=45),
                        )
                        return
                    # 读取总页数：议价流程：分页信息 页码 1/4，总条数 37
                    m_total = re.search(r"页码\s*(\d+)\s*/\s*(\d+)", t)
                    if m_total:
                        total_pages = max(1, int(m_total.group(2)))
                        progress_state["total_pages"] = total_pages
                        self.after(
                            0,
                            lambda: self._set_bargain_progress("抓取第1页数据", state="running", percent=45),
                        )
                        return
                    # 抓取第N页
                    m_page = re.search(r"开始抓取第\s*(\d+)\s*页", t)
                    if m_page:
                        page = max(1, int(m_page.group(1)))
                        total_pages = max(1, int(progress_state.get("total_pages", 1) or 1))
                        # 线性区间：25%（进入页面）~90%（抓完最后一页）
                        percent = 25 + (float(page) / float(total_pages)) * 65.0
                        self.after(
                            0,
                            lambda p=page, pct=percent: self._set_bargain_progress(
                                "抓取第{}页数据".format(p), state="running", percent=pct
                            ),
                        )
                        return

                run_pub = fetch_publisher
                if not dev_mode:
                    run_pub = SheinPublisher(log_cb=_progress_log)
                    self._bargain_runtime_publisher = run_pub

                ok, msg, pub, rows = fetch_shein_pending_bargain_rows(
                    publisher=run_pub,
                    account=account,
                    log_cb=_progress_log,
                    headless=headless_mode,
                    should_stop=lambda: bool(self._stop_bargain_fetch or self._app_closing),
                    force_new_browser=force_new_browser,
                )
                self._bargain_runtime_publisher = pub
                temp_pub = pub
                if dev_mode:
                    self._shein_publisher = pub
                    self._shein_publisher_account = account
                self._bargain_rows = rows or []
                self.after(0, self._render_bargain_rows)
                amazon_done = True
                if self._enable_bargain_amazon_metrics and ok:
                    amazon_done = self._enrich_bargain_rows_with_amazon_progressive()
                if ok:
                    if self._stop_bargain_fetch or (not amazon_done):
                        self.after(0, lambda: self._set_bargain_progress("已停止", state="fail"))
                        self.after(0, lambda: self.status_lbl.config(text="议价流程已停止"))
                    else:
                        keep_runtime_after_fetch = (not dev_mode) and (temp_pub is not None)
                        self.after(0, lambda: self._set_bargain_progress("完毕", state="success", percent=100))
                        self.after(0, lambda: self.status_lbl.config(text=msg))
                        self.after(0, lambda: messagebox.showinfo('议价', msg))
                else:
                    if "用户已停止议价抓取" in str(msg):
                        self.after(0, lambda: self._set_bargain_progress("已停止", state="fail"))
                        self.after(0, lambda: self.status_lbl.config(text="议价流程已停止"))
                    else:
                        self.after(0, lambda: self._set_bargain_progress("抓取失败", state="fail"))
                        self.after(0, lambda: self.status_lbl.config(text=msg))
                        self.after(0, lambda: messagebox.showwarning('议价', msg))
            except Exception as e:
                err = str(e)[:120]
                self.after(0, lambda: self._set_bargain_progress("抓取失败", state="fail"))
                self.after(0, lambda: self.status_lbl.config(text='议价流程失败: ' + err))
                self.after(0, lambda: messagebox.showerror('议价', '议价流程失败：' + err))
            finally:
                keep_runtime = bool(keep_runtime_after_fetch)
                close_runtime = bool((not dev_mode) and temp_pub is not None and self._stop_bargain_fetch)
                if close_runtime:
                    self._close_publisher_instance(temp_pub, reason="用户停止议价抓取")
                    self._bargain_runtime_publisher = None
                    self._bargain_runtime_is_temp = False
                elif keep_runtime:
                    # 非开发者模式：抓取完成后保留后台浏览器，用于“操作”列按钮回传网页点击。
                    self._bargain_runtime_publisher = temp_pub
                    self._bargain_runtime_is_temp = True
                    self._pub_log("议价流程：已保留后台浏览器实例，等待执行“操作”按钮")
                else:
                    self._bargain_runtime_publisher = None
                    self._bargain_runtime_is_temp = False
                self._bargain_fetch_running = False
                self._stop_bargain_fetch = False
                self._bargain_fetch_thread = None

        self._bargain_fetch_thread = threading.Thread(target=_run, daemon=True)
        self._bargain_fetch_thread.start()

    def _build_bargain_panel(self,parent):
        self.bargain_panel=tk.Frame(parent,bg=BG_PANEL)
        self.bargain_panel.grid(row=0,column=0,columnspan=2,sticky="nsew",pady=4)
        self.bargain_panel.grid_remove()

        top = tk.Frame(self.bargain_panel, bg=BG_PANEL)
        # 顶部信息行留出上方空位，给 debug 进度日志显示
        top.pack(fill="x", padx=18, pady=(20,4))
        self._bargain_select_all_var = tk.BooleanVar(value=False)
        self._bargain_select_all_chk = tk.Checkbutton(
            top,
            variable=self._bargain_select_all_var,
            command=self._toggle_bargain_select_all,
            bg=BG_PANEL,
            activebackground=BG_PANEL,
            selectcolor=BG_CARD,
            bd=0,
            highlightthickness=0,
            relief="flat",
            cursor="hand2",
        )
        self._bargain_select_all_chk.pack(side="left", padx=(0, 6))
        tk.Label(
            top,
            text="议价待确认数据",
            font=("Segoe UI", 12, "bold"),
            fg=TEXT_MAIN,
            bg=BG_PANEL,
        ).pack(side="left")
        self._bargain_count_lbl = tk.Label(
            top,
            text="0 条",
            font=("Segoe UI", 10),
            fg=TEXT_SUB,
            bg=BG_PANEL,
        )
        self._bargain_count_lbl.pack(side="left", padx=(8,0))
        # 筛选工具单独放到下一行，避免挤占顶部进度/调试展示区域
        filter_row = tk.Frame(self.bargain_panel, bg=BG_PANEL)
        filter_row.pack(fill="x", padx=18, pady=(0, 8))
        filter_wrap = tk.Frame(filter_row, bg=BG_PANEL)
        # 与“全选”复选框左边缘对齐
        filter_wrap.pack(side="left", padx=(0, 0))
        tk.Label(
            filter_wrap, text="筛选:", font=("Segoe UI", 9, "bold"),
            fg=TEXT_SUB, bg=BG_PANEL
        ).pack(side="left", padx=(0, 4))
        tk.Label(
            filter_wrap, text="平台建议价", font=("Segoe UI", 9),
            fg=TEXT_SUB, bg=BG_PANEL
        ).pack(side="left")
        self._bargain_filter_platform_entry = tk.Entry(
            filter_wrap, textvariable=self._bargain_filter_platform_var,
            width=8, font=("Segoe UI", 9), relief="flat", bd=0
        )
        self._bargain_filter_platform_entry.pack(side="left", padx=(4, 8), ipady=2)
        tk.Label(
            filter_wrap, text="亚马逊价格", font=("Segoe UI", 9),
            fg=TEXT_SUB, bg=BG_PANEL
        ).pack(side="left")
        self._bargain_filter_amazon_entry = tk.Entry(
            filter_wrap, textvariable=self._bargain_filter_amazon_var,
            width=8, font=("Segoe UI", 9), relief="flat", bd=0
        )
        self._bargain_filter_amazon_entry.pack(side="left", padx=(4, 8), ipady=2)
        tk.Label(
            filter_wrap, text="利润率", font=("Segoe UI", 9),
            fg=TEXT_SUB, bg=BG_PANEL
        ).pack(side="left")
        self._bargain_filter_profit_entry = tk.Entry(
            filter_wrap, textvariable=self._bargain_filter_profit_var,
            width=8, font=("Segoe UI", 9), relief="flat", bd=0
        )
        self._bargain_filter_profit_entry.pack(side="left", padx=(4, 6), ipady=2)
        tk.Button(
            filter_wrap, text="应用", font=("Segoe UI", 9), relief="flat", bd=0,
            bg="#334155", fg="white", padx=8, pady=2, cursor="hand2",
            command=self._apply_bargain_filters
        ).pack(side="left", padx=(0, 4))
        tk.Button(
            filter_wrap, text="清空", font=("Segoe UI", 9), relief="flat", bd=0,
            bg="#475569", fg="white", padx=8, pady=2, cursor="hand2",
            command=self._clear_bargain_filters
        ).pack(side="left")
        tk.Label(
            top,
            text="Ctrl+点击亚马逊链接打开",
            font=("Segoe UI", 10, "bold"),
            fg=ACCENT2,
            bg=BG_PANEL,
        ).pack(side="left", padx=(28, 0))
        action_wrap = tk.Frame(top, bg=BG_PANEL)
        action_wrap.pack(side="left", padx=(18, 0))
        self._bargain_bulk_agree_btn = tk.Button(
            action_wrap,
            text="同意平台建议价",
            bg="#16a34a",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self._trigger_bargain_batch_action("同意平台建议价"),
        )
        self._bargain_bulk_agree_btn.pack(side="left", padx=(0, 6))
        self._bargain_bulk_requote_btn = tk.Button(
            action_wrap,
            text="重新报价",
            bg="#2563eb",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self._trigger_bargain_batch_action("重新报价"),
        )
        self._bargain_bulk_requote_btn.pack(side="left", padx=(0, 6))
        self._bargain_bulk_reject_btn = tk.Button(
            action_wrap,
            text="拒绝，放弃上新",
            bg="#dc2626",
            fg="white",
            font=("Segoe UI", 9, "bold"),
            relief="flat",
            bd=0,
            padx=10,
            pady=4,
            cursor="hand2",
            command=lambda: self._trigger_bargain_batch_action("拒绝，放弃上新"),
        )
        self._bargain_bulk_reject_btn.pack(side="left")
        prog_wrap = tk.Frame(top, bg=BG_PANEL)
        prog_wrap.pack(side="right", padx=(12, 0))
        self._bargain_progress_lbl = tk.Label(
            prog_wrap,
            text="待开始",
            font=("Segoe UI", 9),
            fg=TEXT_SUB,
            bg=BG_PANEL,
        )
        self._bargain_progress_lbl.pack(anchor="e")
        self._bargain_progress_canvas = tk.Canvas(
            prog_wrap,
            width=260,
            height=16,
            bg=BG_PANEL,
            highlightthickness=0,
            bd=0,
        )
        self._bargain_progress_canvas.pack(anchor="e", pady=(3, 0))
        self._set_bargain_progress("待开始", state="running", percent=0)

        wrap = tk.Frame(self.bargain_panel, bg=BG_CARD)
        wrap.pack(fill="both", expand=True, padx=18, pady=(0,14))

        table_wrap = tk.Frame(wrap, bg=BG_CARD)
        table_wrap.pack(fill="both", expand=True)

        base_cols = (
            "pick",
            "supplier_no",
            "sku_info",
            "amazon_url",
            "platform_price",
        )
        if self._enable_bargain_amazon_metrics:
            cols = base_cols + ("amazon_price", "profit_rate", "operation")
        else:
            cols = base_cols + ("operation",)
        self._bargain_table_columns = cols
        self._bargain_table = ttk.Treeview(
            table_wrap,
            columns=cols,
            show="headings",
            style="Bargain.Treeview",
            selectmode="browse",
        )
        self._bargain_table.heading("pick", text="勾选", anchor="center")
        self._bargain_table.heading("supplier_no", text="供方货号", anchor="w")
        self._bargain_table.heading("sku_info", text="SKU信息", anchor="w")
        self._bargain_table.heading("platform_price", text="平台建议价", anchor="w", command=lambda: self._on_bargain_sort_click("platform_price"))
        self._bargain_table.heading("operation", text="操作", anchor="w")
        if "amazon_url" in cols:
            self._bargain_table.heading("amazon_url", text="亚马逊链接", anchor="w")
        if "amazon_price" in cols:
            self._bargain_table.heading("amazon_price", text="亚马逊价格", anchor="w", command=lambda: self._on_bargain_sort_click("amazon_price"))
        if "profit_rate" in cols:
            self._bargain_table.heading("profit_rate", text="利润率", anchor="w", command=lambda: self._on_bargain_sort_click("profit_rate"))

        self._bargain_table.column("pick", width=54, minwidth=50, anchor="center")
        self._bargain_table.column("supplier_no", width=140, minwidth=120, anchor="w")
        self._bargain_table.column("sku_info", width=150, minwidth=130, anchor="w")
        self._bargain_table.column("platform_price", width=100, minwidth=90, anchor="w")
        self._bargain_table.column("operation", width=430, minwidth=380, anchor="w")
        if "amazon_url" in cols:
            self._bargain_table.column("amazon_url", width=220, minwidth=170, anchor="w")
        if "amazon_price" in cols:
            self._bargain_table.column("amazon_price", width=120, minwidth=100, anchor="w")
        if "profit_rate" in cols:
            self._bargain_table.column("profit_rate", width=120, minwidth=100, anchor="w")
        # 统一使用「商品详情」区域同款底色，不做奇偶分色
        self._bargain_table.tag_configure("odd", background=BG_CARD)
        self._bargain_table.tag_configure("even", background=BG_CARD)

        ysb = ttk.Scrollbar(table_wrap, orient="vertical", command=self._bargain_table.yview)
        xsb = ttk.Scrollbar(table_wrap, orient="horizontal", command=self._bargain_table.xview)
        self._bargain_table.configure(yscrollcommand=ysb.set, xscrollcommand=xsb.set)

        ysb.pack(side="right", fill="y")
        xsb.pack(side="bottom", fill="x")
        self._bargain_table.pack(side="left", fill="both", expand=True)
        self._bargain_table.bind("<ButtonRelease-1>", self._on_bargain_table_click)
        for _e in (
            self._bargain_filter_platform_entry,
            self._bargain_filter_amazon_entry,
            self._bargain_filter_profit_entry,
        ):
            _e.bind("<Return>", lambda _evt: self._apply_bargain_filters())
        self._refresh_bargain_sort_headings()

        empty_row = [""] * len(cols)
        if empty_row:
            empty_row[0] = "暂无数据，请点击顶部【抓取SHEIN建议价格】"
        self._bargain_table.insert("", "end", values=tuple(empty_row), tags=("odd",))

    def _render_bargain_rows(self):
        rows = list(getattr(self, "_bargain_rows", []) or [])
        self._ensure_bargain_row_uids(rows)
        display_rows = self._get_bargain_display_rows(rows)
        table = getattr(self, "_bargain_table", None)
        if table is None:
            return

        self._bargain_rowid_to_index = {}
        for iid in table.get_children():
            table.delete(iid)

        if not display_rows:
            cols = tuple(getattr(self, "_bargain_table_columns", ()) or ())
            empty_row = [""] * len(cols)
            if empty_row:
                empty_row[0] = "暂无“待确认”数据"
            table.insert("", "end", values=tuple(empty_row), tags=("odd",))
            if hasattr(self, "_bargain_count_lbl"):
                if rows:
                    self._bargain_count_lbl.config(text="0 / {} 条".format(len(rows)))
                else:
                    self._bargain_count_lbl.config(text="0 条")
            return

        cols = tuple(getattr(self, "_bargain_table_columns", ()) or ())

        def _op_display(r):
            actions = list(r.get("actions", []) or [])
            if not actions:
                actions = ["同意平台建议价", "重新报价", "拒绝，放弃上新"]
            chunks, gap = self._build_bargain_operation_segments(actions)
            # Treeview 不支持单元格内原生 Button，这里用“按钮样式文案+平铺”展示，并按文字宽度命中。
            return gap.join(chunks)

        value_getter = {
            "pick": lambda r: "☑" if bool(r.get("_selected", False)) else "☐",
            "supplier_no": lambda r: r.get("supplier_no", ""),
            "reason": lambda r: r.get("reason", ""),
            "sku_info": lambda r: r.get("sku_info", ""),
            "platform_price": lambda r: r.get("platform_price", ""),
            "operation": _op_display,
            "amazon_url": lambda r: r.get("amazon_url", ""),
            "amazon_price": lambda r: r.get("amazon_price", ""),
            "profit_rate": lambda r: r.get("profit_rate", ""),
        }
        source_index_map = {int(r.get("_row_uid", -1)): idx for idx, r in enumerate(rows)}
        for i, r in enumerate(display_rows):
            tag = "odd" if (i % 2 == 0) else "even"
            values = tuple(value_getter.get(c, lambda _x: "")(r) for c in cols)
            row_uid = int(r.get("_row_uid", -1))
            iid = "br_{}".format(row_uid if row_uid >= 0 else i)
            table.insert(
                "",
                "end",
                iid=iid,
                values=values,
                tags=(tag,),
            )
            self._bargain_rowid_to_index[iid] = source_index_map.get(row_uid, i)
        if hasattr(self, "_bargain_count_lbl"):
            if len(display_rows) == len(rows):
                self._bargain_count_lbl.config(text="{} 条".format(len(rows)))
            else:
                self._bargain_count_lbl.config(text="{} / {} 条".format(len(display_rows), len(rows)))
        self._sync_bargain_select_all_checkbox(display_rows)

    _BARGAIN_TABLE_PREF_FILE = os.path.join(
        os.path.expanduser("~"), ".shein_profiles", "bargain_table_pref.json"
    )

    def _load_bargain_table_prefs(self):
        try:
            if not os.path.isfile(self._BARGAIN_TABLE_PREF_FILE):
                return
            with open(self._BARGAIN_TABLE_PREF_FILE, "r", encoding="utf-8") as f:
                obj = json.load(f) or {}
            flt = obj.get("filters", {}) if isinstance(obj, dict) else {}
            self._bargain_filter_platform_var.set(str(flt.get("platform_price", "") or ""))
            self._bargain_filter_amazon_var.set(str(flt.get("amazon_price", "") or ""))
            self._bargain_filter_profit_var.set(str(flt.get("profit_rate", "") or ""))
            srt = obj.get("sort", {}) if isinstance(obj, dict) else {}
            col = str(srt.get("column", "") or "").strip()
            if col in ("platform_price", "amazon_price", "profit_rate"):
                self._bargain_sort_column = col
                self._bargain_sort_desc = bool(srt.get("desc", True))
        except Exception:
            pass

    def _save_bargain_table_prefs(self):
        try:
            os.makedirs(os.path.dirname(self._BARGAIN_TABLE_PREF_FILE), exist_ok=True)
            obj = {
                "filters": {
                    "platform_price": str(self._bargain_filter_platform_var.get() or "").strip(),
                    "amazon_price": str(self._bargain_filter_amazon_var.get() or "").strip(),
                    "profit_rate": str(self._bargain_filter_profit_var.get() or "").strip(),
                },
                "sort": {
                    "column": str(self._bargain_sort_column or ""),
                    "desc": bool(self._bargain_sort_desc),
                },
            }
            with open(self._BARGAIN_TABLE_PREF_FILE, "w", encoding="utf-8") as f:
                json.dump(obj, f, ensure_ascii=False, indent=2)
        except Exception:
            pass

    def _ensure_bargain_row_uids(self, rows):
        if not rows:
            return
        for r in rows:
            try:
                uid = int(r.get("_row_uid", 0))
            except Exception:
                uid = 0
            if uid > 0:
                continue
            r["_row_uid"] = int(self._bargain_row_uid_seq)
            self._bargain_row_uid_seq += 1

    @staticmethod
    def _parse_percent_number(raw):
        txt = str(raw or "").strip().replace("%", "")
        if not txt:
            return None
        m = re.search(r"(-?\d+(?:\.\d+)?)", txt)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    @staticmethod
    def _parse_numeric_filter(expr):
        text = str(expr or "").strip()
        if not text:
            return None
        text = text.replace(" ", "").replace("％", "%")
        if text.endswith("%"):
            text = text[:-1]
        m = re.match(r"^(>=|<=|>|<|==|=)?(-?\d+(?:\.\d+)?)$", text)
        if not m:
            return None
        op = m.group(1) or ">="
        if op == "=":
            op = "=="
        try:
            val = float(m.group(2))
        except Exception:
            return None
        return op, val

    @staticmethod
    def _compare_with_operator(actual, rule):
        if rule is None:
            return True
        if actual is None:
            return False
        op, val = rule
        if op == ">":
            return actual > val
        if op == ">=":
            return actual >= val
        if op == "<":
            return actual < val
        if op == "<=":
            return actual <= val
        return abs(actual - val) < 1e-9

    def _on_bargain_sort_click(self, column):
        if column not in ("platform_price", "amazon_price", "profit_rate"):
            return
        if self._bargain_sort_column == column:
            self._bargain_sort_desc = not bool(self._bargain_sort_desc)
        else:
            # 首次点击按需求默认倒序
            self._bargain_sort_column = column
            self._bargain_sort_desc = True
        self._save_bargain_table_prefs()
        self._refresh_bargain_sort_headings()
        self._render_bargain_rows()

    def _refresh_bargain_sort_headings(self):
        table = getattr(self, "_bargain_table", None)
        if table is None:
            return
        defs = {
            "platform_price": "平台建议价",
            "amazon_price": "亚马逊价格",
            "profit_rate": "利润率",
        }
        for col, title in defs.items():
            if col not in getattr(self, "_bargain_table_columns", ()):
                continue
            suffix = ""
            if self._bargain_sort_column == col:
                suffix = " ▼" if self._bargain_sort_desc else " ▲"
            table.heading(col, text=title + suffix, anchor="w", command=lambda c=col: self._on_bargain_sort_click(c))

    def _apply_bargain_filters(self):
        self._save_bargain_table_prefs()
        self._render_bargain_rows()

    def _clear_bargain_filters(self):
        self._bargain_filter_platform_var.set("")
        self._bargain_filter_amazon_var.set("")
        self._bargain_filter_profit_var.set("")
        self._save_bargain_table_prefs()
        self._render_bargain_rows()

    def _get_bargain_display_rows(self, rows):
        rows = list(rows or [])
        if not rows:
            return []
        f_platform = self._parse_numeric_filter(self._bargain_filter_platform_var.get())
        f_amazon = self._parse_numeric_filter(self._bargain_filter_amazon_var.get())
        f_profit = self._parse_numeric_filter(self._bargain_filter_profit_var.get())

        filtered = []
        for r in rows:
            p1 = self._parse_money_number(r.get("platform_price", ""))
            p2 = self._parse_money_number(r.get("amazon_price", ""))
            p3 = self._parse_percent_number(r.get("profit_rate", ""))
            if not self._compare_with_operator(p1, f_platform):
                continue
            if not self._compare_with_operator(p2, f_amazon):
                continue
            if not self._compare_with_operator(p3, f_profit):
                continue
            filtered.append(r)

        sort_col = str(self._bargain_sort_column or "").strip()
        if sort_col in ("platform_price", "amazon_price", "profit_rate"):
            def _key(item):
                if sort_col == "profit_rate":
                    v = self._parse_percent_number(item.get(sort_col, ""))
                else:
                    v = self._parse_money_number(item.get(sort_col, ""))
                return (v is None, v if v is not None else float("-inf"))
            filtered.sort(key=_key, reverse=bool(self._bargain_sort_desc))
        return filtered

    def _sync_bargain_select_all_checkbox(self, rows=None):
        if rows is None:
            rows = self._get_bargain_display_rows(list(getattr(self, "_bargain_rows", []) or []))
        if not hasattr(self, "_bargain_select_all_var"):
            return
        if not rows:
            self._bargain_select_all_var.set(False)
            return
        all_selected = all(bool(r.get("_selected", False)) for r in rows)
        self._bargain_select_all_var.set(bool(all_selected))

    def _toggle_bargain_select_all(self):
        rows = list(getattr(self, "_bargain_rows", []) or [])
        if not rows:
            self._bargain_select_all_var.set(False)
            return
        display_rows = self._get_bargain_display_rows(rows)
        if not display_rows:
            self._bargain_select_all_var.set(False)
            return
        display_uids = {int(r.get("_row_uid", -1)) for r in display_rows}
        checked = bool(self._bargain_select_all_var.get())
        for r in rows:
            if int(r.get("_row_uid", -1)) in display_uids:
                r["_selected"] = checked
        self._bargain_rows = rows
        self._render_bargain_rows()

    def _on_bargain_table_click(self, _event=None):
        table = getattr(self, "_bargain_table", None)
        if table is None:
            return
        try:
            x = getattr(_event, "x", 0)
            y = getattr(_event, "y", 0)
            row_id = table.identify_row(y)
            if not row_id:
                return
            table.selection_set(row_id)
            table.focus(row_id)
            col = table.identify_column(x)
            if not col:
                return
            try:
                col_idx = int(str(col).lstrip("#")) - 1
            except Exception:
                col_idx = -1
            cols = list(getattr(self, "_bargain_table_columns", ()) or ())
            col_name = cols[col_idx] if 0 <= col_idx < len(cols) else ""
            ctrl_pressed = bool(getattr(_event, "state", 0) & 0x0004)
            if col_name == "pick":
                row_idx = int(getattr(self, "_bargain_rowid_to_index", {}).get(row_id, -1))
                rows = list(getattr(self, "_bargain_rows", []) or [])
                if 0 <= row_idx < len(rows):
                    rows[row_idx]["_selected"] = not bool(rows[row_idx].get("_selected", False))
                    self._bargain_rows = rows
                    self._render_bargain_rows()
                return
            if ctrl_pressed and col_name == "amazon_url":
                vals = table.item(row_id, "values") or ()
                url = str(vals[col_idx]).strip() if 0 <= col_idx < len(vals) else ""
                if url.startswith("http://") or url.startswith("https://"):
                    webbrowser.open(url)
                return
            if col_name == "operation":
                bbox = table.bbox(row_id, col)
                if not bbox:
                    return
                rel_x = float(x - bbox[0])
                row_idx = int(getattr(self, "_bargain_rowid_to_index", {}).get(row_id, -1))
                actions = self._get_bargain_row_actions(row_idx)
                if not actions:
                    return
                chunks, gap = self._build_bargain_operation_segments(actions)
                try:
                    style_font = ttk.Style(self).lookup("Bargain.Treeview", "font") or ("Segoe UI", 10)
                    fnt = tkfont.Font(font=style_font)
                except Exception:
                    try:
                        fnt = tkfont.nametofont("TkDefaultFont")
                    except Exception:
                        fnt = None
                if fnt is None:
                    seg_idx = min(2, max(0, int(rel_x // max(1.0, float(bbox[2])) * 3)))
                else:
                    # Treeview 单元格内部通常有少量左边距，预留 8px 可提升点击命中精度
                    cur_x = max(0.0, rel_x - 8.0)
                    seg_idx = len(chunks) - 1
                    for i, ch in enumerate(chunks):
                        w = float(fnt.measure(ch))
                        if cur_x <= w:
                            seg_idx = i
                            break
                        cur_x -= w
                        if i < len(chunks) - 1:
                            gw = float(fnt.measure(gap))
                            if cur_x <= gw:
                                # 点击在间隔区域时，按就近按钮归属
                                seg_idx = i if cur_x < (gw / 2.0) else (i + 1)
                                break
                            cur_x -= gw
                action_label = actions[min(seg_idx, len(actions) - 1)]
                self._trigger_bargain_row_action(row_idx, action_label)
        except Exception:
            pass

    @staticmethod
    def _build_bargain_operation_segments(actions):
        a1 = actions[0] if len(actions) > 0 else "同意平台建议价"
        a2 = actions[1] if len(actions) > 1 else "重新报价"
        a3 = actions[2] if len(actions) > 2 else "拒绝，放弃上新"
        chunks = ["[ {} ]".format(a1), "[ {} ]".format(a2), "[ {} ]".format(a3)]
        gap = "   "
        return chunks, gap

    def _get_bargain_row_actions(self, row_idx):
        rows = list(getattr(self, "_bargain_rows", []) or [])
        if row_idx < 0 or row_idx >= len(rows):
            return []
        actions = list(rows[row_idx].get("actions", []) or [])
        if not actions:
            actions = ["同意平台建议价", "重新报价", "拒绝，放弃上新"]
        # 只保留前3个，保证点击分段稳定
        return actions[:3]

    def _trigger_bargain_row_action(self, row_idx, action_label):
        if not action_label:
            return
        rows = list(getattr(self, "_bargain_rows", []) or [])
        if row_idx < 0 or row_idx >= len(rows):
            return
        with self._bargain_action_lock:
            if self._bargain_action_running:
                self.status_lbl.config(text="议价功能：已有操作正在执行，请稍候")
                return
            self._bargain_action_running = True
        row = dict(rows[row_idx] or {})
        pub = getattr(self, "_bargain_runtime_publisher", None) or getattr(self, "_shein_publisher", None)
        if pub is None:
            self._bargain_action_running = False
            messagebox.showwarning("议价", "未找到可用浏览器实例，请先抓取“待确认”数据。")
            return

        self.status_lbl.config(text='议价功能：正在执行「{}」...'.format(action_label))
        self._pub_log("议价操作：准备执行 [{}]，议价单号={}，供方货号={}".format(
            action_label,
            row.get("bargain_no", ""),
            row.get("supplier_no", ""),
        ))

        def _run_action():
            try:
                ok, msg = self._execute_bargain_action(row, action_label)
                if ok:
                    self.after(0, lambda r=row: self._remove_bargain_row_after_action(r))
                    self.after(0, lambda: self.status_lbl.config(text="议价功能：{}".format(msg)))
                    self.after(0, lambda: messagebox.showinfo("议价", msg))
                else:
                    self.after(0, lambda: self.status_lbl.config(text="议价功能：{}".format(msg)))
                    self.after(0, lambda: messagebox.showwarning("议价", msg))
            except Exception as e:
                err = str(e)[:120]
                self.after(0, lambda: self.status_lbl.config(text="议价功能：操作失败 - " + err))
                self.after(0, lambda: messagebox.showerror("议价", "执行操作失败：{}".format(err)))
            finally:
                with self._bargain_action_lock:
                    self._bargain_action_running = False

        threading.Thread(target=_run_action, daemon=True).start()

    def _execute_bargain_action(self, row, action_label):
        pub = getattr(self, "_bargain_runtime_publisher", None) or getattr(self, "_shein_publisher", None)
        if pub is None:
            return False, "未找到可用浏览器实例，请先抓取“待确认”数据。"
        return trigger_shein_pending_bargain_action(
            publisher=pub,
            row=row,
            action_label=action_label,
            log_cb=self._pub_log,
            should_stop=lambda: bool(self._app_closing),
        )

    def _trigger_bargain_batch_action(self, action_label):
        rows = list(getattr(self, "_bargain_rows", []) or [])
        selected = [dict(r) for r in rows if bool(r.get("_selected", False))]
        if not selected:
            messagebox.showinfo("议价", "请先勾选要处理的商品。")
            return
        with self._bargain_action_lock:
            if self._bargain_action_running or self._bargain_batch_running:
                self.status_lbl.config(text="议价功能：已有操作正在执行，请稍候")
                return
            self._bargain_action_running = True
            self._bargain_batch_running = True

        self.status_lbl.config(text="议价功能：批量执行「{}」准备中...".format(action_label))
        self._pub_log("议价批量：开始执行 [{}]，共 {} 条".format(action_label, len(selected)))

        def _run_batch():
            total = len(selected)
            ok_count = 0
            fail_count = 0
            try:
                for i, row in enumerate(selected, start=1):
                    if self._app_closing:
                        break
                    self.after(0, lambda idx=i, t=total: self.status_lbl.config(
                        text="议价功能：批量执行「{}」 {}/{}".format(action_label, idx, t)
                    ))
                    ok, msg = self._execute_bargain_action(row, action_label)
                    if ok:
                        ok_count += 1
                        self.after(0, lambda r=row: self._remove_bargain_row_after_action(r))
                    else:
                        fail_count += 1
                        self._pub_log("议价批量：第 {} 条失败 - {}".format(i, msg))
                    # 按需求：执行完成一个后，等待1秒再执行下一个
                    if i < total:
                        time.sleep(1.0)
            finally:
                with self._bargain_action_lock:
                    self._bargain_batch_running = False
                    self._bargain_action_running = False
                self.after(0, lambda: self.status_lbl.config(
                    text="议价功能：批量完成，成功 {} 条，失败 {} 条".format(ok_count, fail_count)
                ))
                self.after(0, lambda: messagebox.showinfo(
                    "议价",
                    "批量操作完成\n动作：{}\n成功：{}\n失败：{}".format(action_label, ok_count, fail_count),
                ))

        threading.Thread(target=_run_batch, daemon=True).start()

    def _remove_bargain_row_after_action(self, row_snapshot):
        """网页操作成功后，从GUI中移除对应行。"""
        rows = list(getattr(self, "_bargain_rows", []) or [])
        if not rows:
            return

        bargain_no = str((row_snapshot or {}).get("bargain_no", "") or "").strip()
        supplier_no = str((row_snapshot or {}).get("supplier_no", "") or "").strip()
        sku_info = str((row_snapshot or {}).get("sku_info", "") or "").strip()
        platform_price = str((row_snapshot or {}).get("platform_price", "") or "").strip()

        hit_idx = -1
        if bargain_no:
            for i, r in enumerate(rows):
                if str(r.get("bargain_no", "") or "").strip() == bargain_no:
                    hit_idx = i
                    break
        if hit_idx < 0:
            # 兜底：用供方货号 + SKU + 价格定位
            for i, r in enumerate(rows):
                if (
                    str(r.get("supplier_no", "") or "").strip() == supplier_no
                    and str(r.get("sku_info", "") or "").strip() == sku_info
                    and str(r.get("platform_price", "") or "").strip() == platform_price
                ):
                    hit_idx = i
                    break
        if hit_idx < 0:
            # 最后兜底：同供方货号的第一条
            for i, r in enumerate(rows):
                if str(r.get("supplier_no", "") or "").strip() == supplier_no and supplier_no:
                    hit_idx = i
                    break
        if hit_idx < 0:
            return

        rows.pop(hit_idx)
        self._bargain_rows = rows
        self._render_bargain_rows()

    @staticmethod
    def _parse_money_number(raw):
        txt = str(raw or "").strip()
        if not txt:
            return None
        txt = txt.replace(",", "")
        m = re.search(r"(\d+(?:\.\d+)?)", txt)
        if not m:
            return None
        try:
            return float(m.group(1))
        except Exception:
            return None

    def _enrich_bargain_rows_with_amazon_progressive(self):
        data = list(getattr(self, "_bargain_rows", []) or [])
        if not data:
            return True

        asin_to_row_indices = {}
        for idx, r in enumerate(data):
            asin = str(r.get("supplier_no", "") or "").strip().upper()
            if re.match(r"^B[A-Z0-9]{9}$", asin):
                asin_to_row_indices.setdefault(asin, []).append(idx)
            else:
                r["amazon_url"] = "N/A"
                r["amazon_price"] = "N/A"
                r["profit_rate"] = "N/A"

        if not asin_to_row_indices:
            self._bargain_rows = data
            self.after(0, self._render_bargain_rows)
            return True

        valid_row_indices = [i for rows in asin_to_row_indices.values() for i in rows]
        for idx in valid_row_indices:
            data[idx]["amazon_url"] = "获取中"
            data[idx]["amazon_price"] = "获取中"
            data[idx]["profit_rate"] = ""
        self._bargain_rows = data
        self.after(0, self._render_bargain_rows)

        unique_asins = list(asin_to_row_indices.keys())
        self._pub_log("议价流程：开始补充亚马逊价格（{}行，{}个ASIN）".format(len(valid_row_indices), len(unique_asins)))
        self.after(0, lambda: self._set_bargain_progress("补充亚马逊价格", state="running", percent=92))
        region = self.amazon_region.get() if hasattr(self, "amazon_region") else "美国"
        try:
            max_workers = int(self.fetch_workers.get())
        except Exception:
            max_workers = 5
        # 与“抓取选中商品(ASIN)”保持同一线程策略
        max_workers = max(1, min(6, max_workers))
        self.fetch_workers.set(str(max_workers))
        self._pub_log("议价流程：亚马逊价格补充使用 {} 线程".format(max_workers))

        def _fetch_one(asin):
            if self._stop_bargain_fetch:
                return asin, None, ""
            amazon_price_val = None
            amazon_url = ""
            cached = self.product_cache.get(asin) if isinstance(self.product_cache, dict) else None
            if isinstance(cached, dict) and self._is_cache_region_match(cached, region):
                pv = self._parse_money_number(cached.get("price", ""))
                if pv and pv > 0:
                    amazon_price_val = pv
                cached_url = str(cached.get("url", "") or "").strip()
                if cached_url.startswith("http://") or cached_url.startswith("https://"):
                    amazon_url = cached_url
            if amazon_price_val is None:
                try:
                    info = fetch_amazon_product(asin, region=region)
                    if isinstance(info, dict):
                        info["_fetch_region"] = region
                    amazon_url = str((info or {}).get("url", "") or "").strip()
                    p = self._parse_money_number((info or {}).get("price", ""))
                    if p and p > 0:
                        amazon_price_val = p
                        try:
                            if isinstance(self.product_cache, dict):
                                old = self.product_cache.get(asin, {}) or {}
                                old["price"] = "${:.2f}".format(p)
                                if amazon_url:
                                    old["url"] = amazon_url
                                self.product_cache[asin] = old
                        except Exception:
                            pass
                except Exception:
                    pass
            if not amazon_url:
                try:
                    amazon_url = AMAZON_PRODUCT_URL.format(asin=asin)
                except Exception:
                    amazon_url = ""
            return asin, amazon_price_val, amazon_url

        finished = 0
        total_tasks = len(unique_asins)
        executor = ThreadPoolExecutor(max_workers=max_workers)
        try:
            futures = {executor.submit(_fetch_one, asin): asin for asin in unique_asins}
            for fut in as_completed(futures):
                if self._stop_bargain_fetch:
                    for pending in futures:
                        pending.cancel()
                    break
                asin = futures[fut]
                finished += 1
                try:
                    _asin, amazon_price_val, amazon_url = fut.result()
                except Exception:
                    _asin, amazon_price_val, amazon_url = asin, None, ""
                for idx in asin_to_row_indices.get(_asin, []):
                    row = data[idx]
                    row["amazon_url"] = amazon_url if (amazon_url.startswith("http://") or amazon_url.startswith("https://")) else "N/A"
                    if amazon_price_val is not None and amazon_price_val > 0:
                        row["amazon_price"] = "${:.2f}".format(amazon_price_val)
                        platform_price_val = self._parse_money_number(row.get("platform_price", ""))
                        if platform_price_val is not None and amazon_price_val > 0:
                            ratio = (platform_price_val - amazon_price_val + 2.99) / amazon_price_val
                            row["profit_rate"] = "{:.2f}%".format(ratio * 100.0)
                        else:
                            row["profit_rate"] = "N/A"
                    else:
                        row["amazon_price"] = "N/A"
                        row["profit_rate"] = "N/A"
                self._bargain_rows = data
                self.after(0, self._render_bargain_rows)
                self.after(0, lambda f=finished, t=total_tasks: self.status_lbl.config(
                    text="议价功能：补充亚马逊价格 {}/{}".format(f, t)
                ))
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except Exception:
                pass

        if self._stop_bargain_fetch:
            for idx in valid_row_indices:
                if data[idx].get("amazon_url") == "获取中":
                    data[idx]["amazon_url"] = "N/A"
                if data[idx].get("amazon_price") == "获取中":
                    data[idx]["amazon_price"] = "N/A"
                    data[idx]["profit_rate"] = "N/A"
            self._bargain_rows = data
            self.after(0, self._render_bargain_rows)
            return False
        return True

    def _draw_bargain_progress_bar(self, percent, color):
        cv = getattr(self, "_bargain_progress_canvas", None)
        if cv is None:
            return
        try:
            cv.delete("all")
            w = int(cv.cget("width"))
            h = int(cv.cget("height"))
            y = h // 2
            pad = 6
            x1 = pad
            x2 = w - pad
            # 底槽（圆弧）
            cv.create_line(x1, y, x2, y, width=12, capstyle=tk.ROUND, fill="#2b3545")
            # 进度（圆弧）
            p = max(0.0, min(100.0, float(percent)))
            fx = x1 + (x2 - x1) * (p / 100.0)
            if fx > x1 + 0.3:
                cv.create_line(x1, y, fx, y, width=12, capstyle=tk.ROUND, fill=color)
        except Exception:
            pass

    def _set_bargain_progress(self, text, state="running", percent=None):
        lbl = getattr(self, "_bargain_progress_lbl", None)
        cv = getattr(self, "_bargain_progress_canvas", None)
        if lbl is None or cv is None:
            return
        color_map = {
            "running": "#3b82f6",
            "success": "#22c55e",
            "fail": "#ef4444",
        }
        if percent is not None:
            self._bargain_progress_percent = max(0.0, min(100.0, float(percent)))
        elif state == "success":
            self._bargain_progress_percent = 100.0
        self._draw_bargain_progress_bar(self._bargain_progress_percent, color_map.get(state, "#3b82f6"))
        lbl.config(text=str(text or ""))

    def _close_publisher_instance(self, pub, reason=""):
        """安全关闭单个浏览器实例。"""
        if pub is None:
            return
        try:
            if hasattr(pub, "request_stop"):
                pub.request_stop(force_quit=True)
            elif hasattr(pub, "quit"):
                pub.quit()
            else:
                driver = getattr(pub, "driver", None)
                if driver is not None:
                    driver.quit()
        except Exception as e:
            self._pub_log("[WARN] 关闭浏览器实例失败: {}".format(str(e)[:80]))
        finally:
            if reason:
                self._pub_log("[BARGAIN] 已关闭议价浏览器实例: {}".format(reason))

    def _toggle_main_panels_for_mode(self):
        if self.current_view_mode == "bargain":
            if hasattr(self, "left_panel"):
                self.left_panel.grid_remove()
            if hasattr(self, "right_panel"):
                self.right_panel.grid_remove()
            if hasattr(self, "bargain_panel"):
                self.bargain_panel.grid()
        else:
            if hasattr(self, "bargain_panel"):
                self.bargain_panel.grid_remove()
            if hasattr(self, "left_panel"):
                self.left_panel.grid()
            if hasattr(self, "right_panel"):
                self.right_panel.grid()

    def _build_left(self,parent):
        left_w = int(getattr(self, "_left_panel_default_width", 320))
        self.left_panel=tk.Frame(parent,bg=BG_PANEL,width=left_w)
        self.left_panel.grid(row=0,column=0,sticky="nsew",padx=(0,8),pady=4)
        self.left_panel.pack_propagate(False)
        self.left_panel.bind("<Motion>", self._on_left_panel_motion)
        self.left_panel.bind("<Leave>", self._on_left_panel_leave)
        self.left_panel.bind("<Button-1>", self._on_left_panel_press)
        self.left_panel.bind("<B1-Motion>", self._drag_left_panel_resize)
        self.left_panel.bind("<ButtonRelease-1>", self._end_left_panel_resize)
        self._left_content = tk.Frame(self.left_panel,bg=BG_PANEL)
        self._left_content.pack(side="left",fill="both",expand=True)
        self._left_content.bind("<Motion>", self._on_left_panel_motion)
        self._left_content.bind("<Leave>", self._on_left_panel_leave)
        self._left_content.bind("<Button-1>", self._on_left_panel_press)
        self._left_content.bind("<B1-Motion>", self._drag_left_panel_resize)
        self._left_content.bind("<ButtonRelease-1>", self._end_left_panel_resize)
        self._left_resize_handle = tk.Frame(
            self.left_panel,
            bg=BG_PANEL,
            width=8,
            cursor="sb_h_double_arrow",
        )
        self._left_resize_handle.pack(side="right",fill="y")
        self._left_resize_handle.pack_propagate(False)
        self._left_resize_indicator = tk.Frame(
            self._left_resize_handle,
            bg="#94a3b8",
            width=1,
        )
        self._left_resize_indicator.pack(side="left", fill="y", padx=3, pady=6)
        self._left_resize_indicator.bind("<Button-1>", self._start_left_panel_resize)
        self._left_resize_indicator.bind("<B1-Motion>", self._drag_left_panel_resize)
        self._left_resize_indicator.bind("<ButtonRelease-1>", self._end_left_panel_resize)
        self._left_resize_handle.bind("<Button-1>", self._start_left_panel_resize)
        self._left_resize_handle.bind("<B1-Motion>", self._drag_left_panel_resize)
        self._left_resize_handle.bind("<ButtonRelease-1>", self._end_left_panel_resize)
        f=self._left_content
        h=tk.Frame(f,bg=BG_PANEL); h.pack(fill="x",padx=12,pady=(12,4))
        tk.Label(h,text="ASIN 列表",font=("Segoe UI",11,"bold"),fg=TEXT_MAIN,bg=BG_PANEL).pack(side="left")
        self.cnt_lbl=tk.Label(h,text="(0)",font=("Segoe UI",10),fg=TEXT_SUB,bg=BG_PANEL)
        self.cnt_lbl.pack(side="left",padx=4)

        sr=tk.Frame(f,bg=BG_PANEL); sr.pack(fill="x",padx=12,pady=(0,6))
        tk.Checkbutton(sr,text="全选",variable=self.select_all_var,command=self._sel_all,
            bg=BG_PANEL,fg=TEXT_MAIN,selectcolor=BG_CARD,activebackground=BG_PANEL,
            activeforeground=ACCENT2,font=("Segoe UI",10),cursor="hand2").pack(side="left")
        self.asin_search_var = tk.StringVar(value="")
        locate_wrap = tk.Frame(sr, bg=BG_PANEL)
        locate_wrap.pack(side="right", padx=(6,0))
        asin_search_entry = tk.Entry(
            locate_wrap,
            textvariable=self.asin_search_var,
            width=10,
            font=("Consolas", 9),
            bg=BG_CARD,
            fg=TEXT_MAIN,
            insertbackground=TEXT_MAIN,
            relief="flat",
            bd=2
        )
        asin_search_entry.pack(side="left")
        tk.Button(
            locate_wrap,
            text="定位",
            bg="#334155",
            fg=TEXT_MAIN,
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._locate_asin_from_query
        ).pack(side="left", padx=(4,0))
        tk.Button(
            locate_wrap,
            text="抓取",
            bg="#2563eb",
            fg=TEXT_MAIN,
            font=("Segoe UI", 8, "bold"),
            relief="flat",
            bd=0,
            padx=8,
            pady=2,
            cursor="hand2",
            command=self._fetch_asin_from_query
        ).pack(side="left", padx=(4,0))
        asin_search_entry.bind("<Return>", lambda _e: self._locate_asin_from_query())
        # 亚马逊地区选择（仅支持美国）
        rg=tk.Frame(f,bg=BG_PANEL); rg.pack(fill="x",padx=12,pady=(2,4))
        tk.Label(rg,text="抓取地区:",font=("Segoe UI",9),fg=TEXT_SUB,bg=BG_PANEL).pack(side="left")
        region_cb=ttk.Combobox(rg,textvariable=self.amazon_region,
            values=["美国","其他国家暂不支持"],
            state="readonly",width=12,font=("Segoe UI",9))
        region_cb.pack(side="left",padx=(4,0))
        self.sel_lbl=tk.Label(rg,text="已选: 0",font=("Segoe UI",9),fg=TEXT_SUB,bg=BG_PANEL)
        self.sel_lbl.pack(side="left",padx=(10,0))
        tk.Frame(f,bg=BORDER,height=1).pack(fill="x",padx=8,pady=(0,4))
        c=tk.Frame(f,bg=BG_PANEL); c.pack(fill="both",expand=True,padx=4,pady=4)
        cv=tk.Canvas(c,bg=BG_PANEL,highlightthickness=0,bd=0)
        sb=ttk.Scrollbar(c,orient="vertical",command=self._on_asin_scrollbar)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right",fill="y"); cv.pack(side="left",fill="both",expand=True)
        self.lf=tk.Frame(cv,bg=BG_PANEL)
        self._lw=cv.create_window((0,0),window=self.lf,anchor="nw")
        self.lf.bind("<Configure>", self._on_asin_list_inner_configure)
        cv.bind("<Configure>", self._on_asin_list_canvas_configure)
        cv.bind_all("<MouseWheel>", self._on_global_mousewheel, add="+")
        self.acv=cv
        self.after(0, self._sync_left_resize_handle_height)

    def _start_left_panel_resize(self, event):
        self._left_resize_active = True
        self._left_resize_anchor_x = int(event.x_root)
        self._left_resize_origin_width = int(self.left_panel.winfo_width())

    def _drag_left_panel_resize(self, event):
        if not getattr(self, "_left_resize_active", False):
            return
        delta = int(event.x_root) - int(getattr(self, "_left_resize_anchor_x", event.x_root))
        target_w = int(getattr(self, "_left_resize_origin_width", self.left_panel.winfo_width())) + delta
        min_w = int(getattr(self, "_left_panel_min_width", 280))
        max_w = int(getattr(self, "_left_panel_max_width", 720))
        target_w = max(min_w, min(max_w, target_w))
        self.left_panel.config(width=target_w)
        if hasattr(self, "_main_body"):
            self._main_body.columnconfigure(0, minsize=target_w)

    def _end_left_panel_resize(self, _event):
        self._left_resize_active = False

    def _on_left_panel_motion(self, event):
        if getattr(self, "_left_resize_active", False):
            self.left_panel.configure(cursor="sb_h_double_arrow")
            return
        if self._is_near_left_panel_right_edge(event):
            self.left_panel.configure(cursor="sb_h_double_arrow")
        else:
            self.left_panel.configure(cursor="")

    def _on_left_panel_leave(self, _event):
        if not getattr(self, "_left_resize_active", False):
            self.left_panel.configure(cursor="")

    def _on_left_panel_press(self, event):
        if self._is_near_left_panel_right_edge(event):
            self._start_left_panel_resize(event)

    def _is_near_left_panel_right_edge(self, event):
        try:
            x = int(event.x)
            panel_w = int(self.left_panel.winfo_width())
            hotzone = int(getattr(self, "_left_resize_hotzone", 10))
            return x >= max(0, panel_w - hotzone)
        except Exception:
            return False

    def _sync_left_resize_handle_height(self):
        try:
            self._left_resize_handle.lift()
        except Exception:
            pass

    def _build_right(self,parent):
        self.right_panel=tk.Frame(parent,bg=BG_PANEL)
        f=self.right_panel
        self.right_panel.grid(row=0,column=1,sticky="nsew",pady=4)
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
        st.configure(
            "Bargain.Treeview",
            background=BG_CARD,
            fieldbackground=BG_CARD,
            foreground=TEXT_MAIN,
            rowheight=34,
            borderwidth=0,
            relief="flat",
            font=("Segoe UI", 10),
        )
        st.configure(
            "Bargain.Treeview.Heading",
            background=BG_CARD,
            foreground=TEXT_MAIN,
            font=("Segoe UI", 10, "bold"),
            relief="flat",
        )
        st.map(
            "Bargain.Treeview.Heading",
            background=[("active", "#365f5a"), ("pressed", "#365f5a")],
            foreground=[("active", "#f4fffc"), ("pressed", "#f4fffc")],
        )
        st.map(
            "Bargain.Treeview",
            background=[("selected", "#365f5a")],
            foreground=[("selected", "#f4fffc")],
        )

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

    def _set_asin_status(self, asin, status):
        """更新ASIN状态并同步圆点颜色。"""
        self.asin_status[asin] = status
        dot = self.asin_dots.get(asin)
        color_map = {
            "imported": "#ffffff",
            "fetching": YELLOW,
            # 抓取成功使用与界面主蓝区分的亮蓝色
            "fetch_success": "#38bdf8",
            "fetch_fail": RED,
            "no_price": RED,
            "no_suitable_sku": RED,
            "sku_too_many": RED,
            "stock_low": RED,
            "publishing": YELLOW,
            "success": GREEN,
            "fail": RED,
            "pending": "#ffffff",
        }
        if dot:
            dot.config(fg=color_map.get(status, "#ffffff"))
        hint = getattr(self, "asin_hints", {}).get(asin)
        if hint:
            # 警告文案统一显示在进度文案区域，避免与 hint 文案叠加。
            hint.config(text="", fg=dot.cget("bg") if dot else hint.cget("bg"))
        if status in ("imported", "pending", "fetch_success"):
            self._set_asin_progress(asin, 0, "未上品", state="idle")
        elif status == "publishing":
            self._set_asin_progress(asin, 10, "上品中", state="running")
        elif status == "success":
            self._set_asin_progress(asin, 100, "上品成功", state="success")
        elif status == "sku_too_many":
            self._set_asin_progress(asin, 100, "SKU过多，不做爬取", state="fail")
        elif status == "stock_low":
            self._set_asin_progress(asin, 100, "亚马逊库存告急", state="fail")
        elif status == "no_suitable_sku":
            self._set_asin_progress(asin, 100, "无合适SKU", state="fail")
        elif status == "fail":
            self._set_asin_progress(asin, 100, "上品失败", state="fail")
        elif status == "fetch_fail":
            self._set_asin_progress(asin, 100, "抓取失败", state="fail")
        elif status == "no_price":
            self._set_asin_progress(asin, 100, "No price， stop", state="fail")

    def _set_asin_progress(self, asin, pct=None, text=None, state="running"):
        """更新 ASIN 行内简化进度条与文字。"""
        # Tkinter 只能在主线程更新控件；多线程上品时统一切回主线程刷新进度
        try:
            if threading.get_ident() != getattr(self, "_ui_thread_id", threading.get_ident()):
                self.after(0, lambda a=asin, p=pct, t=text, s=state: self._set_asin_progress(a, p, t, s))
                return
        except Exception:
            pass
        ws = self.asin_row_widgets.get(asin) or {}
        bar = ws.get("prog_canvas")
        fill_id = ws.get("prog_fill")
        txt_lbl = ws.get("prog_text")
        cur = self.asin_progress.get(asin, {"pct": 0, "text": "未上品", "state": "idle"})
        if pct is None:
            pct = cur.get("pct", 0)
        if text is None:
            text = cur.get("text", "未上品")
        pct = max(0, min(100, int(pct)))
        # 运行中阶段不允许回退，避免并发日志时序导致进度条倒退。
        if state == "running" and cur.get("state") == "running":
            pct = max(int(cur.get("pct", 0)), pct)
        # 进度未变化时不触发控件重绘，降低高频日志带来的 UI 抖动/卡顿。
        unchanged = (
            int(cur.get("pct", 0)) == int(pct)
            and str(cur.get("text", "")) == str(text)
            and str(cur.get("state", "")) == str(state)
        )
        render_key = (int(pct), str(text), str(state))
        self.asin_progress[asin] = {"pct": pct, "text": text, "state": state}
        if not bar or not fill_id or not txt_lbl:
            return
        # 仅当当前行已经按同一内容渲染过，才跳过重绘。
        # 这样可避免虚拟列表中新建行因“值未变化”而不刷新颜色/文案。
        if unchanged and ws.get("prog_drawn") == render_key:
            return
        color_map = {
            "idle": "#64748b",
            "running": "#3b82f6",
            "success": "#22c55e",
            "fail": "#ef4444",
            "stopped": "#94a3b8",
        }
        fill_color = color_map.get(state, "#3b82f6")
        width = 110
        bar.coords(fill_id, 0, 0, int(width * pct / 100.0), 6)
        bar.itemconfig(fill_id, fill=fill_color, outline=fill_color)
        txt_font = ("Segoe UI", 7) if state == "fail" else ("Segoe UI", 8)
        txt_lbl.config(
            text=text,
            fg=fill_color if state in ("success", "fail") else TEXT_SUB,
            font=txt_font
        )
        ws["prog_drawn"] = render_key

    def _on_global_mousewheel(self, event):
        """仅在鼠标位于 ASIN 列表区域时滚动，并合并滚轮事件降低卡顿。"""
        cv = getattr(self, "acv", None)
        if cv is None:
            return
        try:
            x, y = int(event.x_root), int(event.y_root)
            left = cv.winfo_rootx()
            top = cv.winfo_rooty()
            right = left + cv.winfo_width()
            bottom = top + cv.winfo_height()
            if not (left <= x <= right and top <= y <= bottom):
                return
        except Exception:
            return
        delta = int(getattr(event, "delta", 0) or 0)
        if delta == 0:
            return
        self._asin_wheel_accum += delta
        if self._asin_wheel_after_id:
            return
        self._asin_wheel_after_id = self.after(12, self._flush_asin_mousewheel)

    def _flush_asin_mousewheel(self):
        self._asin_wheel_after_id = None
        cv = getattr(self, "acv", None)
        if cv is None:
            self._asin_wheel_accum = 0
            return
        accum = int(getattr(self, "_asin_wheel_accum", 0))
        if accum == 0:
            return
        steps = int(-accum / 120)
        if steps == 0:
            steps = -1 if accum > 0 else 1
        try:
            cv.yview_scroll(steps, "units")
        except Exception:
            pass
        self._asin_wheel_accum = 0
        self._schedule_refresh_visible_asin_rows()

    def _on_asin_list_inner_configure(self, _event):
        cv = getattr(self, "acv", None)
        if cv is None:
            return
        try:
            bbox = cv.bbox("all")
            if bbox:
                cv.configure(scrollregion=bbox)
        except Exception:
            pass

    def _on_asin_list_canvas_configure(self, event):
        cv = getattr(self, "acv", None)
        if cv is None:
            return
        try:
            cv.itemconfig(self._lw, width=event.width)
        except Exception:
            pass
        self._schedule_refresh_visible_asin_rows()

    def _on_asin_scrollbar(self, *args):
        cv = getattr(self, "acv", None)
        if cv is None:
            return
        try:
            cv.yview(*args)
        except Exception:
            return
        self._schedule_refresh_visible_asin_rows()

    def _schedule_refresh_visible_asin_rows(self):
        if self._asin_virtual_after_id:
            return
        self._asin_virtual_after_id = self.after(12, self._flush_refresh_visible_asin_rows)

    def _flush_refresh_visible_asin_rows(self):
        self._asin_virtual_after_id = None
        self._refresh_visible_asin_rows(force=False)

    def _update_publish_progress_by_msg(self, asin, msg):
        m = str(msg or "")
        # 按“后期阶段优先”匹配，避免宽泛关键词把进度卡在早期。
        if "商品已提交发布" in m or "提交成功，等待审核中" in m:
            # 仅日志命中不直接判定成功，最终成功以业务结果回写为准（避免串日志导致误绿）
            self._set_asin_progress(asin, 95, "发布结果确认中", state="running"); return
        if "发布失败" in m or "上品失败" in m:
            self._set_asin_progress(asin, 100, "发布失败", state="fail"); return
        if ("点击发布商品" in m or "等待确认弹窗" in m or "确认弹窗" in m
                or "结果文案" in m or "一键翻译并发布" in m):
            # 业务期望：确认其他信息阶段约在半程，避免从基础信息阶段跃迁过大
            self._set_asin_progress(asin, 50, "确认其他信息中", state="running"); return
        if "上传商品图片" in m:
            # 上传阶段开始时先推进到 48%，避免长时间显示“填写基础信息”。
            self._set_asin_progress(asin, 48, "上传商品图片中", state="running"); return
        if "细节图上传完成" in m:
            self._set_asin_progress(asin, 75, "细节图上传完成", state="running"); return
        if ("SKU行" in m and "图" in m and "已提交" in m) or "开始上传细节图" in m or "上传细节图" in m:
            # 需求：细节图阶段从 50% 开始，逐步到 75%
            self._set_asin_progress(asin, 50, "上传细节图中", state="running"); return
        if "规格及供应信息填写完成" in m or "规格已确定" in m:
            self._set_asin_progress(asin, 68, "规格已确定", state="running"); return
        if "开始填写规格及供应信息" in m or "填写规格" in m:
            self._set_asin_progress(asin, 55, "填写规格信息", state="running"); return
        if "商品基础信息填写完成" in m or "基础信息填写完成" in m:
            self._set_asin_progress(asin, 45, "基础信息已完成", state="running"); return
        if "开始填写商品基础信息" in m or "填写商品基础信息" in m or "填写基础信息" in m:
            self._set_asin_progress(asin, 40, "填写基础信息", state="running"); return
        if ("确认，下一步" in m or "推荐类目" in m or "确认类目" in m
                or "选择第一个推荐类目" in m or "点击确认类目" in m):
            self._set_asin_progress(asin, 35, "确认类目", state="running"); return
        if ("识图发品" in m or "识图" in m or "上传图片" in m or "推荐类目" in m):
            self._set_asin_progress(asin, 25, "识图发品中", state="running"); return

    def _route_asin_progress_from_log(self, msg):
        """从上传日志中提取更细阶段（例如第X张细节图）。"""
        m = str(msg or "")
        # 优先使用日志内显式 ASIN，避免多线程串扰。
        asin_from_msg = None
        try:
            _m_asin = re.search(r"\bB[A-Z0-9]{9}\b", m)
            if _m_asin:
                asin_from_msg = _m_asin.group(0)
        except Exception:
            asin_from_msg = None
        # 多线程日志通常带 [Wn] 前缀，先按 worker->ASIN 映射到对应进度条
        _wm = re.match(r"^\[W(\d+)\]\s*(.*)$", m)
        if _wm:
            try:
                worker_idx = int(_wm.group(1))
            except Exception:
                worker_idx = None
            worker_msg = _wm.group(2) or ""
            target_asin = None
            if worker_idx is not None:
                try:
                    with self._worker_publishers_lock:
                        target_asin = self._worker_active_asins.get(worker_idx)
                except Exception:
                    target_asin = None
            if not target_asin and asin_from_msg:
                target_asin = asin_from_msg
            if target_asin:
                # 与单线程一致：根据阶段文案更新进度条文字
                self._update_publish_progress_by_msg(target_asin, worker_msg)
                try:
                    mm = re.search(r"(?:全局图|图)(\d+)已提交", worker_msg)
                    if mm and ("SKU行" in worker_msg):
                        img_idx = int(mm.group(1))
                        # 细节图上传阶段：从 50% 逐步推进到 75%
                        pct = min(74, 50 + img_idx * 4)
                        self._set_asin_progress(
                            target_asin, pct, "上传第{}张细节图中".format(img_idx), state="running")
                        return
                    if "细节图上传完成" in worker_msg:
                        # 需求：细节图上传完成时，到 3/4
                        self._set_asin_progress(target_asin, 75, "细节图上传完成", state="running")
                        return
                except Exception:
                    pass
            return

        # 不再回退到 current_asin，避免用户切换选中项时把日志错路由到当前详情商品
        asin = asin_from_msg or self._active_publish_asin
        if not asin:
            return
        try:
            mm = re.search(r"(?:全局图|图)(\d+)已提交", m)
            if mm and ("SKU行" in m):
                img_idx = int(mm.group(1))
                pct = min(74, 50 + img_idx * 4)
                self._set_asin_progress(asin, pct, "上传第{}张细节图中".format(img_idx), state="running")
                return
            if "细节图上传完成" in m:
                self._set_asin_progress(asin, 75, "细节图上传完成", state="running")
        except Exception:
            pass

    def _reset_publishing_asins_to_unpublished(self):
        """停止上品时，将仍处于上品中的黄色状态恢复为未发布蓝色。"""
        try:
            for asin, st in list(self.asin_status.items()):
                if st == "publishing":
                    info = self.product_cache.get(asin) or {}
                    fetch_st = self._infer_fetch_status(info)
                    self._set_asin_status(asin, fetch_st)
                    if fetch_st == "fetch_success":
                        self._set_asin_progress(asin, 0, "未上品", state="idle")
        except Exception:
            pass

    @staticmethod
    def _has_publishable_price(product_info):
        """价格可用于上品：非 NA/N/A 且包含数字。"""
        if not isinstance(product_info, dict):
            return False
        raw = str(product_info.get("price", "") or "").strip()
        if not raw:
            return False
        norm = raw.replace(" ", "").upper()
        if norm in ("NA", "N/A", "NONE", "NULL", "-", "--"):
            return False
        return bool(re.search(r"\d", raw))

    @staticmethod
    def _is_failed_fetch_info(product_info):
        """根据抓取结果内容判断是否属于抓取失败数据。"""
        if not isinstance(product_info, dict):
            return True
        title = str(product_info.get("title", "") or "").strip()
        if not title:
            return True
        fail_prefixes = ("获取失败", "HTTP ", "错误:", "被亚马逊反爬", "Error")
        return any(title.startswith(p) for p in fail_prefixes)

    def _infer_fetch_status(self, product_info):
        """从商品信息推断抓取状态，避免仅靠 UI 状态误判。"""
        if not isinstance(product_info, dict) or not product_info:
            return "fetch_fail"
        if bool(product_info.get("stock_low")):
            return "stock_low"
        if bool(product_info.get("sku_too_many")):
            return "sku_too_many"
        if bool(product_info.get("no_suitable_sku")):
            return "no_suitable_sku"
        if self._is_failed_fetch_info(product_info):
            return "fetch_fail"
        if not self._has_publishable_price(product_info):
            return "no_price"
        return "fetch_success"

    @staticmethod
    def _is_cache_region_match(product_info, region):
        """缓存是否与当前抓取地区一致。"""
        if not isinstance(product_info, dict):
            return False
        cached_region = str(product_info.get("_fetch_region", "") or "").strip()
        target_region = str(region or "").strip()
        return bool(cached_region) and (cached_region == target_region)

    def _is_asin_fetch_ready(self, asin):
        """上品前校验：必须抓取成功。"""
        info = self.product_cache.get(asin) or {}
        inferred = self._infer_fetch_status(info)
        if inferred != "fetch_success":
            reason_map = {
                "stock_low": "亚马逊库存告急",
                "sku_too_many": "SKU过多",
                "no_suitable_sku": "无合适SKU",
                "fetch_fail": "抓取失败",
                "no_price": "No price， stop",
            }
            return False, reason_map.get(inferred, "未抓取成功")
        if bool(info.get("nonstandard_color_only")):
            return False, "颜色非标准"
        if not info.get("image_url"):
            return False, "缺少图片信息"
        return True, ""

    def _mark_asin_not_fetch_ready(self, asin, reason=""):
        """标记 ASIN 未抓取成功，禁止开始上品。"""
        if not asin:
            return
        status = str(self.asin_status.get(asin, "") or "")
        if status not in ("stock_low", "sku_too_many", "fetch_fail", "no_suitable_sku", "no_price"):
            self._set_asin_status(asin, "fetch_fail")
        text = "请先抓取成功"
        if "库存" in reason:
            text = "亚马逊库存告急"
        elif "无合适SKU" in reason:
            text = "无合适SKU"
        elif "SKU" in reason.upper():
            text = "SKU过多，不做爬取"
        elif "抓取失败" in reason:
            text = "抓取失败，请重新抓取"
        elif "No price" in reason:
            text = "No price， stop"
        elif "颜色非标准" in reason:
            text = "颜色非标准，已过滤"
        elif "图片" in reason:
            text = "缺少图片，请重新抓取"
        self._set_asin_progress(asin, 100, text, state="fail")
        self._pub_log("[SKIP] {} 未抓取成功（{}），已跳过上品".format(asin, reason or "未知原因"))

    def _mark_asin_no_price(self, asin):
        """标记 ASIN 因无价格无法上品（红色进度）。"""
        if not asin:
            return
        self._set_asin_status(asin, "no_price")
        self._set_asin_progress(asin, 100, "No price， stop", state="fail")
        self._pub_log("[SKIP] {} 无价格，无法上品".format(asin))

    def _save_manual_price(self, asin, raw_price):
        """保存手动价格到缓存，后续上品直接使用该值。"""
        asin = str(asin or "").strip()
        if not asin:
            return
        info = self.product_cache.get(asin)
        if not isinstance(info, dict):
            info = {"asin": asin}
            self.product_cache[asin] = info
        price_text = str(raw_price or "").strip()
        if not price_text:
            price_text = "N/A"
        info["price"] = price_text

        inferred = self._infer_fetch_status(info)
        status_map = {
            "fetch_success": "fetch_success",
            "stock_low": "stock_low",
            "sku_too_many": "sku_too_many",
            "no_suitable_sku": "no_suitable_sku",
            "fetch_fail": "fetch_fail",
            "no_price": "no_price",
        }
        cur_status = str(self.asin_status.get(asin, "") or "")
        if cur_status in ("", "imported", "pending", "fetching", "fetch_success", "fetch_fail", "no_price", "fail"):
            self._set_asin_status(asin, status_map.get(inferred, "fetch_fail"))
        elif cur_status in ("stock_low", "sku_too_many", "no_suitable_sku"):
            # 保持更高优先级失败态，不因手工改价覆盖库存/SKU类错误。
            pass

        if self.current_asin == asin:
            if inferred == "no_price":
                self.status_lbl.config(text="No price， stop")
            else:
                # 恢复为与正常抓取一致的状态文案，清除 no price 提示
                self.status_lbl.config(text="抓取完成，共缓存 {} 个商品".format(len(self.product_cache)))

    @staticmethod
    def _parse_manual_features(raw_text):
        """将多行商品特点文本规范化为列表。"""
        lines = []
        for line in str(raw_text or "").splitlines():
            item = str(line or "").strip()
            if not item:
                continue
            item = re.sub(r"^[>\-\u2022\u00b7\*\s]+", "", item).strip()
            if item:
                lines.append(item[:500])
        return lines[:6]

    def _save_manual_title_features(self, asin, raw_title=None, raw_features_text=None):
        """保存详情页手动编辑的标题与商品特点，发布时优先使用。"""
        asin = str(asin or "").strip()
        if not asin:
            return
        info = self.product_cache.get(asin)
        if not isinstance(info, dict):
            info = {"asin": asin}
            self.product_cache[asin] = info

        if raw_title is not None:
            title = str(raw_title or "").strip()
            if title:
                info["title"] = title[:300]
            else:
                info["title"] = ""

        if raw_features_text is not None:
            features = self._parse_manual_features(raw_features_text)
            info["features"] = features
            # 与上品填写逻辑保持一致：有特点时优先拼接为商品描述
            if features:
                info["description"] = "\n".join(features)

    def _import_txt(self):
        if self._license_locked:
            self._show_auth_lock_popup()
            return
        path=filedialog.askopenfilename(title="选择 ASIN 文本文件",
            filetypes=[("文本文件","*.txt"),("所有文件","*.*")])
        if not path: return
        try:
            with open(path,"r",encoding="utf-8") as f:
                lines=[l.strip() for l in f]
            asins=[l for l in lines if re.match(r"^B[A-Z0-9]{9}$",l)]
            if not asins:
                messagebox.showwarning("提示","未找到有效 ASIN 码"); return
            self.asin_list=asins; self.asin_vars={}; self.asin_dots={}; self.asin_status={}; self.asin_row_widgets={}
            self._render_list()
            self.status_lbl.config(text="已载入 {} 个 ASIN".format(len(asins)))
            self._welcome()
        except Exception as e:
            messagebox.showerror("读取失败",str(e))

    def _render_list(self):
        for w in self.lf.winfo_children(): w.destroy()
        self.asin_hints = {}
        self.asin_row_widgets = {}
        self._asin_visible_range = (-1, -1)
        self._asin_index_map = {asin: idx for idx, asin in enumerate(self.asin_list)}
        for asin in self.asin_list:
            var=tk.BooleanVar(value=False)
            self.asin_vars[asin]=var
            self.asin_status[asin]="imported"
            self._set_asin_progress(asin, 0, "未上品", state="idle")
        total_h = max(1, len(self.asin_list) * self._asin_row_height)
        self.lf.configure(height=total_h)
        self.lf.pack_propagate(False)
        self.acv.configure(scrollregion=(0, 0, max(1, self.acv.winfo_width()), total_h))
        self._refresh_visible_asin_rows(force=True)
        self.cnt_lbl.config(text="({})".format(len(self.asin_list)))
        self._upd_cnt(); self.select_all_var.set(False)
        self._update_asin_row_styles()

    def _create_asin_row_widget(self, asin, idx):
        bg=BG_CARD if idx%2==0 else BG_PANEL
        row=tk.Frame(self.lf,bg=bg,cursor="hand2")
        row.place(x=0, y=idx * self._asin_row_height, relwidth=1.0, height=self._asin_row_height - 2)
        var = self.asin_vars.get(asin)
        cb=tk.Checkbutton(row,variable=var,bg=bg,fg="#ffffff",selectcolor=BG_DARK,
            activebackground=bg,activeforeground="#ffffff",command=self._upd_cnt)
        cb.pack(side="left",padx=(8,2))
        dot=tk.Label(row,text="\u25cf",font=("Segoe UI",8),fg="#ffffff",bg=bg)
        dot.pack(side="left"); self.asin_dots[asin]=dot
        lbl=tk.Label(row,text=asin,font=("Consolas",10),fg=TEXT_MAIN,bg=bg,anchor="w",cursor="hand2")
        lbl.pack(side="left",padx=4,pady=5)
        hint=tk.Label(row,text="",font=("Segoe UI",8),fg=bg,bg=bg,anchor="w")
        hint.pack(side="left",padx=(0,4))
        prog_wrap = tk.Frame(row, bg=bg)
        prog_wrap.pack(side="right", padx=(4,8), pady=2)
        prog_text = tk.Label(prog_wrap, text="未上品", font=("Segoe UI",8), fg=TEXT_SUB, bg=bg, anchor="e")
        prog_text.pack(fill="x")
        prog_canvas = tk.Canvas(prog_wrap, width=110, height=6, bg=bg, highlightthickness=0, bd=0)
        prog_canvas.pack(fill="x")
        prog_canvas.create_rectangle(0, 0, 110, 6, fill="#334155", outline="#334155")
        prog_fill = prog_canvas.create_rectangle(0, 0, 0, 6, fill="#64748b", outline="#64748b")
        self.asin_hints[asin]=hint
        self.asin_row_widgets[asin] = {
            "idx": idx,
            "row": row,
            "cb": cb,
            "lbl": lbl,
            "dot": dot,
            "hint": hint,
            "prog_wrap": prog_wrap,
            "prog_text": prog_text,
            "prog_canvas": prog_canvas,
            "prog_fill": prog_fill,
        }
        lbl.bind("<Button-1>",lambda e,a=asin:self._click(a))
        row.bind("<Button-1>",lambda e,a=asin:self._click(a))
        lbl.bind("<Double-Button-1>",lambda e,a=asin:self._dbl_select_asin(a))
        row.bind("<Double-Button-1>",lambda e,a=asin:self._dbl_select_asin(a))
        dot.bind("<Double-Button-1>",lambda e,a=asin:self._dbl_select_asin(a))
        self._apply_asin_row_style(asin)
        st = self.asin_status.get(asin, "imported")
        if st:
            self._set_asin_status(asin, st)
        pg = self.asin_progress.get(asin)
        if isinstance(pg, dict):
            self._set_asin_progress(asin, pg.get("pct", 0), pg.get("text", "未上品"), pg.get("state", "idle"))
        else:
            self._set_asin_progress(asin, 0, "未上品", state="idle")

    def _destroy_asin_row_widget(self, asin):
        ws = self.asin_row_widgets.pop(asin, None) or {}
        row = ws.get("row")
        if row:
            try:
                row.destroy()
            except Exception:
                pass
        self.asin_dots.pop(asin, None)
        self.asin_hints.pop(asin, None)

    def _refresh_visible_asin_rows(self, force=False):
        cv = getattr(self, "acv", None)
        if cv is None:
            return
        total = len(self.asin_list)
        if total <= 0:
            for asin in list(self.asin_row_widgets.keys()):
                self._destroy_asin_row_widget(asin)
            self._asin_visible_range = (-1, -1)
            return
        try:
            top = float(cv.canvasy(0))
            height = max(1, int(cv.winfo_height()))
        except Exception:
            top = 0.0
            height = 1
        bottom = top + height
        row_h = max(1, int(self._asin_row_height))
        start = max(0, int(top // row_h) - int(self._asin_row_buffer))
        end = min(total, int(bottom // row_h) + int(self._asin_row_buffer) + 1)
        if (not force) and (start, end) == self._asin_visible_range:
            return
        self._asin_visible_range = (start, end)
        visible_asins = set(self.asin_list[start:end])
        for asin in list(self.asin_row_widgets.keys()):
            if asin not in visible_asins:
                self._destroy_asin_row_widget(asin)
        for idx in range(start, end):
            asin = self.asin_list[idx]
            if asin not in self.asin_row_widgets:
                self._create_asin_row_widget(asin, idx)

    def _apply_asin_row_style(self, asin):
        """仅刷新单个 ASIN 行样式，避免切换时全量遍历。"""
        if not asin:
            return
        ws = self.asin_row_widgets.get(asin)
        if not ws:
            return
        selected_bg = "#243447"
        selected_fg = "#EAF3FF"
        idx = ws.get("idx", 0)
        normal_bg = BG_CARD if idx % 2 == 0 else BG_PANEL
        is_selected = (asin == self.current_asin)
        bg = selected_bg if is_selected else normal_bg
        fg = selected_fg if is_selected else TEXT_MAIN
        try:
            ws["row"].config(bg=bg)
            ws["cb"].config(bg=bg, activebackground=bg)
            ws["lbl"].config(bg=bg, fg=fg)
            ws["dot"].config(bg=bg)
            ws["hint"].config(bg=bg, fg=bg)
            if ws.get("prog_wrap"): ws["prog_wrap"].config(bg=bg)
            if ws.get("prog_text"): ws["prog_text"].config(bg=bg)
            if ws.get("prog_canvas"): ws["prog_canvas"].config(bg=bg)
        except Exception:
            pass

    def _update_asin_row_styles(self, changed_asins=None):
        """高亮当前选中的 ASIN 行，让定位更清晰。"""
        if changed_asins is None:
            for asin in self.asin_row_widgets.keys():
                self._apply_asin_row_style(asin)
            return
        seen = set()
        for asin in changed_asins:
            if asin and asin not in seen:
                seen.add(asin)
                self._apply_asin_row_style(asin)

    def _click(self,asin):
        prev_asin = self.current_asin
        self.current_asin=asin
        self._update_asin_row_styles(changed_asins=[prev_asin, asin])
        self._schedule_show_current_asin()

    def _schedule_show_current_asin(self, delay_ms=16):
        """切换时合并高频点击，避免重复重绘详情面板。"""
        if self._detail_switch_after_id:
            try:
                self.after_cancel(self._detail_switch_after_id)
            except Exception:
                pass
            self._detail_switch_after_id = None
        self._detail_switch_after_id = self.after(delay_ms, self._show_current_asin_now)

    def _show_current_asin_now(self):
        self._detail_switch_after_id = None
        asin = self.current_asin
        if not asin:
            return
        if asin in self.product_cache:
            self._show(self.product_cache[asin])
        else:
            self._placeholder(asin)

    def _dbl_select_asin(self, asin):
        """双击 ASIN 行时直接勾选该 ASIN。"""
        var = self.asin_vars.get(asin)
        if var is not None and not var.get():
            var.set(True)
            self._upd_cnt()
        self._click(asin)

    def _scroll_to_asin(self, asin):
        if not hasattr(self, "acv"):
            return
        try:
            self.update_idletasks()
            idx = self._asin_index_map.get(asin, -1)
            if idx < 0:
                return
            row_y = idx * self._asin_row_height
            list_h = max(1, len(self.asin_list) * self._asin_row_height)
            canvas_h = max(1, self.acv.winfo_height())
            target_top = max(0, row_y - canvas_h // 2)
            frac = min(1.0, max(0.0, float(target_top) / float(list_h)))
            self.acv.yview_moveto(frac)
            self._refresh_visible_asin_rows(force=True)
        except Exception:
            pass

    def _locate_asin_from_query(self):
        """按输入关键词定位 ASIN 行（不做筛选，仅定位并展示详情）。"""
        if not self.asin_list:
            self.status_lbl.config(text="请先导入 ASIN 文件")
            return
        q = (self.asin_search_var.get() or "").strip().upper()
        if not q:
            self.status_lbl.config(text="请输入 ASIN 或其片段")
            return
        # 先精确匹配，再按片段匹配
        matched = None
        for asin in self.asin_list:
            if asin.upper() == q:
                matched = asin
                break
        if matched is None:
            for asin in self.asin_list:
                if q in asin.upper():
                    matched = asin
                    break
        if not matched:
            self.status_lbl.config(text="未找到匹配 ASIN: {}".format(q))
            return
        self._click(matched)
        self._scroll_to_asin(matched)
        self.status_lbl.config(text="已定位 ASIN: {}".format(matched))

    def _fetch_asin_from_query(self):
        """从输入框直接抓取单个 ASIN，并刷新商品详情。"""
        if self._fetch_thread and self._fetch_thread.is_alive():
            messagebox.showinfo("提示", "正在抓取中，请稍候...")
            return
        q = (self.asin_search_var.get() or "").strip().upper()
        if not q:
            self.status_lbl.config(text="请输入 ASIN 码")
            return
        if not re.match(r"^B[A-Z0-9]{9}$", q):
            self.status_lbl.config(text="ASIN 格式不正确: {}".format(q))
            return

        self._stop_publish = False
        self._last_fetch_no_price_asins = []

        if q in self.asin_list:
            self._click(q)
            self._scroll_to_asin(q)
        else:
            self.current_asin = q
            self._schedule_show_current_asin(delay_ms=1)

        # 直抓模式：强制重新抓取该 ASIN，避免命中旧缓存
        try:
            if q in self.product_cache:
                del self.product_cache[q]
        except Exception:
            pass

        self.progress.start(12)
        self.status_lbl.config(text="正在抓取 ASIN: {} ...".format(q))
        self._fetch_thread = threading.Thread(
            target=self._worker,
            args=([q], 1, []),
            daemon=True
        )
        self._fetch_thread.start()

    def _placeholder(self,asin):
        self._cancel_pending_sku_render()
        for w in self.df.winfo_children(): w.destroy()
        tk.Label(self.df,text="ASIN: {}\n\n尚未抓取。\n请勾选后点击【抓取选中商品】。".format(asin),
            font=("Segoe UI",12),fg=TEXT_SUB,bg=BG_PANEL,justify="center").pack(pady=60)

    def _sel_all(self):
        v=self.select_all_var.get()
        for var in self.asin_vars.values(): var.set(v)
        self._upd_cnt()

    def _upd_cnt(self):
        cnt=sum(1 for v in self.asin_vars.values() if v.get())
        self.sel_lbl.config(text="已选: {}".format(cnt))
        if len(self.asin_vars)>0:
            self.select_all_var.set(cnt==len(self.asin_vars))

    _ACCT_HISTORY_FILE = os.path.join(
        os.path.expanduser("~"), ".shein_profiles", "account_history.txt")

    def _load_account_history(self):
        """从本地文件加载历史账号列表。"""
        try:
            if os.path.isfile(self._ACCT_HISTORY_FILE):
                with open(self._ACCT_HISTORY_FILE, "r", encoding="utf-8") as f:
                    return [l.strip() for l in f if l.strip()]
        except Exception:
            pass
        return []

    def _save_account_to_history(self, account):
        """将登录成功的账号保存到历史记录（去重，最新在前）。"""
        if not account:
            return
        try:
            history = self._load_account_history()
            if account in history:
                history.remove(account)
            history.insert(0, account)
            history = history[:20]
            os.makedirs(os.path.dirname(self._ACCT_HISTORY_FILE), exist_ok=True)
            with open(self._ACCT_HISTORY_FILE, "w", encoding="utf-8") as f:
                f.write("\n".join(history))
            self._acct_combo['values'] = history
        except Exception:
            pass

    def _capture_login_session_from_driver(self, driver, account=""):
        """从浏览器提取并缓存登录会话（cookies/localStorage/sessionStorage）。"""
        if driver is None:
            return False
        cookies = []
        local_storage = {}
        session_storage = {}
        try:
            cookies = driver.get_cookies() or []
        except Exception:
            cookies = []
        try:
            local_storage = driver.execute_script(
                "var r={}; for(var i=0;i<localStorage.length;i++){var k=localStorage.key(i); r[k]=localStorage.getItem(k);} return r;"
            ) or {}
        except Exception:
            local_storage = {}
        try:
            session_storage = driver.execute_script(
                "var r={}; for(var i=0;i<sessionStorage.length;i++){var k=sessionStorage.key(i); r[k]=sessionStorage.getItem(k);} return r;"
            ) or {}
        except Exception:
            session_storage = {}
        if not (cookies or local_storage or session_storage):
            return False
        self._login_cookies = cookies
        self._login_storage = local_storage
        self._login_session_storage = session_storage
        if account:
            self._login_session_account = account
        return True

    def _get_saved_login_session(self):
        """优先从当前浏览器提取，其次返回已缓存会话。"""
        try:
            if self._is_publisher_reusable(self._shein_publisher):
                acct = (self._shein_publisher_account or self.shein_account.get().strip() or "")
                self._capture_login_session_from_driver(self._shein_publisher.driver, acct)
        except Exception:
            pass
        return (
            list(self._login_cookies or []),
            dict(self._login_storage or {}),
            dict(self._login_session_storage or {}),
        )

    def _inject_login_session_to_driver(self, driver, login_cookies, login_storage, login_session_storage):
        """将缓存会话注入到目标浏览器。"""
        if driver is None:
            return
        if login_storage:
            try:
                driver.execute_script(
                    "for (var k in arguments[0]) { try { localStorage.setItem(k, arguments[0][k]); } catch(e) {} }",
                    login_storage,
                )
            except Exception:
                pass
        if login_session_storage:
            try:
                driver.execute_script(
                    "for (var k in arguments[0]) { try { sessionStorage.setItem(k, arguments[0][k]); } catch(e) {} }",
                    login_session_storage,
                )
            except Exception:
                pass
        if login_cookies:
            for ck in login_cookies:
                try:
                    c = dict(ck)
                    if c.get('expiry') is not None:
                        try:
                            c['expiry'] = int(c['expiry'])
                        except Exception:
                            c.pop('expiry', None)
                    driver.add_cookie(c)
                except Exception:
                    continue

    def _verify_account(self, account: str) -> bool:
        """验证 SHEIN 账号是否已授权，通过后缓存结果。"""
        account = (account or "").strip()
        if self._license_locked:
            self._show_auth_lock_popup()
            return False
        if not account:
            return False
        if account in self._verified_accounts:
            start_raw, end_raw = self._account_auth_periods.get(account, ("", ""))
            period_ok, period_msg = self._check_local_period(start_raw, end_raw)
            self._update_license_text(start_raw, end_raw)
            if period_ok:
                self._mark_verified_account(account, start_raw, end_raw)
                return True
            self.status_lbl.config(text='账号验证失败')
            messagebox.showerror('账号验证失败', period_msg)
            return False

        self.status_lbl.config(text='正在验证账号授权...')
        ok, msg, start_raw, end_raw = verify_shein_account_detail(account)
        if ok:
            period_ok, period_msg = self._check_local_period(start_raw, end_raw)
            self._update_license_text(start_raw, end_raw)
            if not period_ok:
                self.status_lbl.config(text='账号验证失败')
                messagebox.showerror('账号验证失败', period_msg)
                return False
            self._mark_verified_account(account, start_raw, end_raw)
            self.status_lbl.config(text='账号验证通过')
            return True
        self.status_lbl.config(text='账号验证失败')
        messagebox.showerror('账号验证失败', msg)
        return False

    def _mark_verified_account(self, account, start_raw, end_raw):
        """记录验证成功账号，并开启每小时复检。"""
        account = str(account or "").strip()
        if not account:
            return
        self._verified_accounts.add(account)
        self._account_auth_periods[account] = (start_raw, end_raw)
        self._auth_watch_account = account
        self._schedule_auth_check()

    def _schedule_auth_check(self, delay_ms=None):
        """计划下一次账号授权复检。"""
        if self._app_closing or self._license_locked:
            return
        if self._auth_check_after_id is not None:
            try:
                self.after_cancel(self._auth_check_after_id)
            except Exception:
                pass
            self._auth_check_after_id = None
        if delay_ms is None:
            delay_ms = self._auth_check_interval_ms
        self._auth_check_after_id = self.after(delay_ms, self._run_periodic_auth_check)

    def _run_periodic_auth_check(self):
        """每小时请求服务端复检账号授权状态。"""
        self._auth_check_after_id = None
        if self._app_closing or self._license_locked:
            return
        account = str(self._auth_watch_account or "").strip()
        if not account:
            return
        self.status_lbl.config(text='正在复检账号授权...')

        def _worker():
            ok, msg, start_raw, end_raw = verify_shein_account_detail(account)
            if ok:
                period_ok, period_msg = self._check_local_period(start_raw, end_raw)
                if not period_ok:
                    ok = False
                    msg = period_msg
            self.after(
                0,
                lambda a=account, s=start_raw, e=end_raw, passed=ok, m=msg:
                self._on_periodic_auth_check_done(a, passed, m, s, e)
            )

        threading.Thread(target=_worker, daemon=True).start()

    def _on_periodic_auth_check_done(self, account, ok, msg, start_raw, end_raw):
        if self._app_closing or self._license_locked:
            return
        if ok:
            self._mark_verified_account(account, start_raw, end_raw)
            self._update_license_text(start_raw, end_raw)
            self.status_lbl.config(text='账号授权复检通过')
            return
        lock_reason = "账号 [{}] 已不在权限范围内。\n{}\n请联系管理员续费/开通后再使用。".format(account, str(msg or "授权校验未通过"))
        self._lock_app_for_auth(lock_reason)

    def _set_auth_control_state(self, enabled):
        state = "normal" if enabled else "disabled"
        for name in (
            "_mode_collect_btn",
            "_mode_bargain_btn",
            "_import_btn",
            "_fetch_btn",
            "_publish_btn",
            "_suggest_price_btn",
            "_shein_login_btn",
        ):
            btn = getattr(self, name, None)
            if btn is None:
                continue
            try:
                btn.config(state=state)
            except Exception:
                pass
        combo = getattr(self, "_acct_combo", None)
        if combo is not None:
            try:
                combo.config(state=("normal" if enabled else "disabled"))
            except Exception:
                pass

    def _lock_app_for_auth(self, reason):
        """权限失效后锁定功能入口并提示用户。"""
        if self._license_locked:
            return
        self._license_locked = True
        self._license_locked_reason = str(reason or "账号权限已失效，请联系管理员")
        if self._auth_check_after_id is not None:
            try:
                self.after_cancel(self._auth_check_after_id)
            except Exception:
                pass
            self._auth_check_after_id = None
        try:
            self._stop_publish = True
            self._stop_bargain_fetch = True
            self._publish_session_id += 1
        except Exception:
            pass
        self._set_auth_control_state(False)
        self.status_lbl.config(text='账号权限失效，软件已锁定')
        self._show_auth_lock_popup()

    def _show_auth_lock_popup(self):
        msg = str(self._license_locked_reason or "账号权限已失效，请联系管理员")
        try:
            self.status_lbl.config(text='账号权限失效，软件已锁定')
        except Exception:
            pass
        try:
            messagebox.showerror('账号权限失效', msg)
        except Exception:
            pass

    @staticmethod
    def _parse_period_datetime(raw_value):
        """解析服务端返回的 start/end 时间，兼容常见格式。"""
        if raw_value is None:
            return None
        txt = str(raw_value).strip()
        if not txt:
            return None
        txt = txt.replace("T", " ").replace("/", "-")
        if txt.endswith("Z"):
            txt = txt[:-1]
        # 去掉毫秒（如 2026-12-21 23:59:59.000）
        if "." in txt:
            txt = txt.split(".", 1)[0]
        fmts = (
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
        )
        for fmt in fmts:
            try:
                return datetime.strptime(txt, fmt)
            except Exception:
                continue
        return None

    def _check_local_period(self, start_raw, end_raw):
        """
        使用本机当前时间校验软件有效期。
        返回 (True/False, message)。
        """
        start_dt = self._parse_period_datetime(start_raw)
        end_dt = self._parse_period_datetime(end_raw)
        if start_dt is None or end_dt is None:
            return False, "账号有效期数据异常（缺少 start_time / end_time），请联系管理员"
        now_dt = datetime.now()
        if now_dt < start_dt or now_dt > end_dt:
            return False, "当前时间不在软件有效期内，禁止使用。\n有效期：{} 至 {}".format(
                start_dt.strftime("%Y-%m-%d"), end_dt.strftime("%Y-%m-%d"))
        return True, ""

    def _update_license_text(self, start_raw, end_raw):
        """更新右下角有效期显示。"""
        if not hasattr(self, "_license_lbl"):
            return
        start_dt = self._parse_period_datetime(start_raw)
        end_dt = self._parse_period_datetime(end_raw)
        if start_dt is None or end_dt is None:
            txt = "软件有效期：未获取"
        else:
            txt = "软件有效期：{} 至 {}".format(
                start_dt.strftime("%Y-%m-%d"),
                end_dt.strftime("%Y-%m-%d"),
            )
        self._license_lbl.config(text=txt)

    def _open_shein(self):
        """打开 SHEIN 登录页面。"""
        if self._license_locked:
            self._show_auth_lock_popup()
            return
        account = self.shein_account.get().strip()
        if not account:
            messagebox.showwarning('提示', '请先在「SHEIN账号」输入框中填写账号')
            return

        if not self._verify_account(account):
            return

        if self._launching_browser:
            self.status_lbl.config(text='浏览器正在启动中，请稍候...')
            return

        # 如果已有实例但不可复用（例如被手动关窗），先清理引用
        if self._shein_publisher is not None and (not self._is_publisher_reusable(self._shein_publisher)):
            self._pub_log('检测到旧浏览器实例已失效，将重新启动')
            self._shein_publisher = None

        # 如果已有浏览器实例且账号相同，直接复用
        if (self._shein_publisher is not None
                and self._shein_publisher_account == account):
            try:
                if self._is_publisher_reusable(self._shein_publisher):
                    self.status_lbl.config(text='复用已有浏览器 (账号: {})'.format(account))
                    self._shein_publisher.driver.get(SHEIN_PUBLISH_URL)
                    threading.Thread(target=self._watch_login,
                                     args=(self._shein_publisher,), daemon=True).start()
                    return
            except Exception:
                pass

        # 账号不同或无实例 → 启动新浏览器
        self._launching_browser = True
        self.status_lbl.config(text='正在启动浏览器 (账号: {})...'.format(account))

        def _launch():
            try:
                pub = SheinPublisher(log_cb=self._pub_log)
                pub.start_browser(account=account)
                self._shein_publisher = pub
                self._shein_publisher_account = account
                self.status_lbl.config(text='浏览器已就绪，打开商品发布页...')
                pub.driver.get(SHEIN_PUBLISH_URL)
                self.status_lbl.config(text='已打开商品发布页，请确认登录状态')
                threading.Thread(target=self._watch_login, args=(pub,), daemon=True).start()
            except Exception as e:
                self.status_lbl.config(text='启动失败: ' + str(e)[:50])
                self.after(0, lambda err=str(e): messagebox.showerror('启动失败', err[:200]))
            finally:
                self._launching_browser = False

        threading.Thread(target=_launch, daemon=True).start()


    def _has_confirmed_shein_session(self, driver):
        """更严格地判断 SHEIN 是否已完成登录，返回 (是否登录, 判定依据)。"""
        try:
            url = (driver.current_url or "").strip().lower()
        except Exception:
            return False, "url_unavailable"

        if not url or url.startswith("about:blank"):
            return False, "blank_url"
        if "geiwohuo.com" not in url:
            return False, "outside_domain"
        if "login" in url:
            return False, "still_login_page"
        if "/auth/" in url or "gmpsso" in url:
            return False, "auth_pending"

        # 已进入发布页通常意味着登录完成
        if "followsales-pro/list" in url and ("commoditiescategory" in url or "commodities-category" in url):
            return True, "publish_url"

        # 优先以 localStorage 中的登录信息作为确认依据（仅 token 容易误判，故不单独使用）
        try:
            session_state = driver.execute_script(
                """
                try {
                    var infoRaw = localStorage.getItem('loginInfo');
                    var info = infoRaw ? JSON.parse(infoRaw) : null;
                    var hasLoginInfo = !!(info && (
                        info.userName || info.supplierUserName || info.phoneTel || info.email
                    ));
                    return {hasLoginInfo: hasLoginInfo};
                } catch (e) {
                    return {hasLoginInfo: false};
                }
                """
            ) or {}
            if isinstance(session_state, dict):
                if bool(session_state.get("hasLoginInfo")):
                    # loginInfo 需配合 home 页面，避免被残留缓存误判
                    if "#/home" in url:
                        return True, "home_with_localStorage.loginInfo"
        except Exception:
            pass

        # 兜底：当 URL 已进入 home，同时带有用户态 cookie 时也认为已登录
        try:
            cookies = driver.get_cookies() or []
            cookie_names = {(ck.get("name") or "").lower() for ck in cookies}
            hints = (
                "userinfo", "user_info", "username", "user_name", "loginname",
                "accesstoken", "access_token", "refreshtoken", "refresh_token",
                "id_token", "jwt"
            )
            has_user_cookie = any(any(h in name for h in hints) for name in cookie_names)
            if has_user_cookie and "#/home" in url:
                return True, "home_with_user_cookie"
        except Exception:
            pass

        return False, "no_confirmed_session"

    def _dismiss_announcements_quick(self, driver):
        """快速关闭公告弹窗：单次点击，不做长等待。"""
        script = r"""
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
const targets = ['我已确认本公告内容', '我已确认本公告，下一条', '下一条', '我知道了'];
const btns = Array.from(document.querySelectorAll('button,span,div,a')).filter(visible);
for (const b of btns) {
  const t = clean(b.innerText || b.textContent || '');
  if (!t) continue;
  for (const kw of targets) {
    if (t.includes(kw)) {
      try { b.click(); return kw; } catch (e) {}
    }
  }
}
return '';
"""
        try:
            clicked = driver.execute_script(script) or ""
            if clicked:
                self._pub_log("[LOGIN] 已快速关闭公告: {}".format(clicked))
                return True
        except Exception:
            pass
        return False

    def _has_publish_entry_text(self, driver):
        """快速检测发布页是否已出现“识图发品”等关键文案。"""
        script = r"""
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
const body = document && document.body ? clean(document.body.innerText || '') : '';
if (body.includes('识图发品')) return true;
const nodes = Array.from(document.querySelectorAll('button,span,div,a')).filter(visible);
for (const n of nodes) {
  const t = clean(n.innerText || n.textContent || '');
  if (!t) continue;
  if (t.includes('识图发品') || t.includes('上传图片')) return true;
}
return false;
"""
        try:
            return bool(driver.execute_script(script))
        except Exception:
            return False


    def _watch_login(self, pub, timeout=180):
        """后台轮询检测SHEIN登录状态，成功后更新按钮显示账号。"""
        import time as _t
        end = _t.time() + timeout
        logged_in = False
        login_reason = ""
        while _t.time() < end:
            # 浏览器已被手动关闭或失效时，不再继续误判
            if not self._is_publisher_reusable(pub):
                return
            try:
                # 先快速处理公告弹窗，避免遮挡导致“识图发品”不可见
                self._dismiss_announcements_quick(pub.driver)

                # 每1秒检测页面是否出现“识图发品”，命中即判定登录成功
                if self._has_publish_entry_text(pub.driver):
                    logged_in = True
                    login_reason = "dom_text_识图发品"
                    break

                # 兜底：保留原有会话判断，避免页面文案变化时失效
                _ok, _reason = self._has_confirmed_shein_session(pub.driver)
                if _ok:
                    logged_in = True
                    login_reason = _reason or "session_confirmed"
                    break
            except Exception:
                pass
            _t.sleep(1.0)

        if not logged_in:
            return
        self._pub_log("[OK] 登录判定成功依据: {}".format(login_reason or "unknown"))
        self.after(0, lambda: self.status_lbl.config(text="检测到登录成功，正在完成初始化..."))

        # 已登录后仅做极短等待，避免“已打开商品发布页”阶段长时间停留
        _t.sleep(0.3)
        # 非开发者模式下：循环检测页面中文状态（每1秒一次，最多3分钟）
        if not is_dev_mode():
            zh_timeout = 180.0
            zh_deadline = _t.time() + zh_timeout
            self._pub_log("[INFO] 已登录，开始检测页面是否中文（每1秒检测，最长180秒）")
            self.after(0, lambda: self.status_lbl.config(text="已登录，等待页面切换为中文..."))
            chinese_ready = False
            last_hint_left = None
            while _t.time() < zh_deadline:
                # 用户手动关闭浏览器时，不再判定失败（视为已手动调试完成）
                if not self._is_publisher_reusable(pub):
                    self._pub_log("[INFO] 登录浏览器已手动关闭，默认视为中文已调试完成")
                    chinese_ready = True
                    break
                try:
                    if self._is_chinese_page(pub.driver):
                        chinese_ready = True
                        self._pub_log("[OK] 中文页面检测通过，登录流程继续")
                        break
                except Exception:
                    pass
                left = int(max(0, zh_deadline - _t.time()))
                # 每10秒刷新一次状态，避免日志与状态栏刷屏
                if left // 10 != last_hint_left:
                    last_hint_left = left // 10
                    self.after(0, lambda s=left: self.status_lbl.config(
                        text="页面非中文，等待手动切换为中文（剩余{}秒）...".format(s)))
                _t.sleep(1.0)
            if not chinese_ready:
                self._pub_log("[ERROR] 页面非中文：180秒内未检测到中文页面，登录失败")
                self.after(0, lambda: self.status_lbl.config(
                    text="页面非中文：3分钟内未切换中文，登录失败"))
                return

        try:
            now_url = (pub.driver.current_url or "").lower()
        except Exception:
            now_url = ""
        already_publish_page = (
            "followsales-pro/list" in now_url
            and ("commoditiescategory" in now_url or "commodities-category" in now_url)
        )
        if not already_publish_page:
            try:
                pub.driver.get(SHEIN_PUBLISH_URL)
            except Exception:
                pass
            _t.sleep(1)
        else:
            self._pub_log("登录后已在商品发布页，跳过重复刷新")
        try:
            dismiss_shein_user_guides(pub.driver, log_cb=self._pub_log, timeout=5, interval=1)
        except Exception as _guide_e:
            self._pub_log("登录后处理引导异常: {}".format(str(_guide_e)[:80]))
        account = ""
        import re as _re
        try:
            from selenium.webdriver.common.by import By as _By

            # 策略1: 从 Cookie 获取邮笱账号
            try:
                cookies = pub.driver.get_cookies()
                for ck in cookies:
                    name = ck.get('name', '').lower()
                    val = ck.get('value', '').strip()
                    if name in ('username', 'email', 'account', 'loginname',
                                'user_email', 'user_name', 'userinfo'):
                        if val and '@' in val and len(val) < 60:
                            account = val
                            break
            except Exception:
                pass

            # 策略2: 从 localStorage.loginInfo 获取 userName
            if not account:
                try:
                    js_result = pub.driver.execute_script('''
                        try {
                            // 直接从 loginInfo 提取 userName
                            var info = JSON.parse(localStorage.getItem('loginInfo') || 'null');
                            if (info && info.userName) return info.userName;
                            if (info && info.supplierUserName) return info.supplierUserName;
                            if (info && info.phoneTel) return info.phoneTel;
                        } catch(e) {}
                        // 备用：遍历所有 localStorage 项
                        for (var i=0; i<localStorage.length; i++) {
                            try {
                                var k = localStorage.key(i);
                                var obj = JSON.parse(localStorage.getItem(k));
                                if (obj && typeof obj === 'object') {
                                    var u = obj.userName || obj.supplierUserName ||
                                            obj.username || obj.account || '';
                                    if (u && u.length > 2 && u.length < 50) return u;
                                    var em = obj.email || obj.userEmail || '';
                                    if (em && em.indexOf('@') !== -1) return em;
                                }
                            } catch(e) {}
                        }
                        return null;
                    '''
                    )
                    if js_result:
                        account = str(js_result).strip()
                except Exception:
                    pass

            # 策略3: JS扫描页面所有邮笱格式文本
            if not account:
                try:
                    all_texts = pub.driver.execute_script('''
                        var texts = [];
                        var all = document.querySelectorAll('*');
                        for (var i=0; i<all.length; i++) {
                            var t = (all[i].childNodes.length === 1 &&
                                     all[i].childNodes[0].nodeType === 3)
                                    ? all[i].innerText.trim() : '';
                            if (t && t.indexOf('@') !== -1 && t.length < 60 && t.indexOf('\n') === -1)
                                texts.push(t);
                        }
                        return texts;
                    '''
                    )
                    if all_texts:
                        for t in all_texts:
                            if _re.match(r'[^@\s]+@[^@\s]+\.[^@\s]+', t):
                                account = t
                                break
                except Exception:
                    pass

            # 策略4: 页面元素笻选手机号
            if not account:
                try:
                    for el in pub.driver.find_elements(_By.XPATH,
                            '//*[string-length(normalize-space(text()))=11]'):
                        txt = el.text.strip()
                        if _re.fullmatch(r'1[3-9]\d{9}', txt):
                            account = txt
                            break
                except Exception:
                    pass

        except Exception:
            pass

        # DEBUG: 记录页面信息帮助分析账号元素位置
        try:
            _url = pub.driver.current_url
            _body = pub.driver.execute_script(
                "return document.body ? document.body.innerText.slice(0,800) : 'no body';")
            _ls = pub.driver.execute_script(
                "var r={}; for(var i=0;i<localStorage.length;i++){"
                "var k=localStorage.key(i); r[k]=localStorage.getItem(k);}"
                "return JSON.stringify(r).slice(0,1000);")
            _cks = [{c['name']: c['value']} for c in pub.driver.get_cookies()]
            self._pub_log("[ACCT-DEBUG] URL: {}".format(_url))
            self._pub_log("[ACCT-DEBUG] body: {}".format(str(_body).replace('\n','|')[:400]))
            self._pub_log("[ACCT-DEBUG] localStorage: {}".format(str(_ls)[:600]))
            self._pub_log("[ACCT-DEBUG] cookies: {}".format(str(_cks)[:400]))
        except Exception as _de:
            self._pub_log("[ACCT-DEBUG] 失败: {}".format(str(_de)[:80]))

        # 记忆登录成功的账号
        _login_acct = getattr(self, '_shein_publisher_account', '') or ''
        if _login_acct:
            self.after(0, lambda a=_login_acct: self._save_account_to_history(a))
        try:
            if self._capture_login_session_from_driver(pub.driver, _login_acct):
                self._pub_log("[OK] 已保存登录会话快照")
        except Exception as _se:
            self._pub_log("[WARN] 保存登录会话失败: {}".format(str(_se)[:80]))

        # 更新按钮
        self.after(0, lambda: self._shein_login_btn.config(
            text="已登录", bg="#0d7a4e", font=("Segoe UI", 9, "bold")))
        self.after(0, lambda: self.status_lbl.config(
            text="SHEIN 登录成功" + ("  账号: " + _login_acct if _login_acct else "")))
        self._pub_log("[OK] SHEIN 登录成功(依据: {})，账号: {}".format(
            login_reason or "unknown", _login_acct or "(未获取到)"))
        # 登录成功后的窗口行为：
        # - 开发者模式：保留窗口便于观察
        # - 非开发者模式：先检查页面是否中文；不是中文则保留窗口并提示切换语言
        if is_dev_mode():
            self._pub_log("[DEV] 开发者模式：保留登录窗口")
        else:
            try:
                pub.driver.quit()
                if self._shein_publisher is pub:
                    self._shein_publisher = None
                self._pub_log("[OK] 登录窗口已关闭（会话已保留）")
            except Exception:
                pass

    def _open_publish_page(self):
        """打开 SHEIN 商品发布页面，自动上传选中商品的图片。"""
        if self._license_locked:
            self._show_auth_lock_popup()
            return
        account = self.shein_account.get().strip()
        if not account:
            messagebox.showwarning('提示', '请先在「SHEIN账号」输入框中填写账号')
            return
        if not self._verify_account(account):
            return

        # 优先使用勾选的 ASIN；未勾选时回退到当前点击项
        selected_asins = [a for a, v in self.asin_vars.items() if v.get()]
        if len(selected_asins) > 1:
            skipped_success = [a for a in selected_asins if self.asin_status.get(a) == "success"]
            publish_asins = [a for a in selected_asins if self.asin_status.get(a) != "success"]
            no_price_asins = []
            not_ready_asins = []
            filtered_asins = []
            for asin in publish_asins:
                info = self.product_cache.get(asin) or {}
                is_ready, reason = self._is_asin_fetch_ready(asin)
                if not is_ready:
                    not_ready_asins.append(asin)
                    self._mark_asin_not_fetch_ready(asin, reason)
                    continue
                if self._has_publishable_price(info):
                    filtered_asins.append(asin)
                else:
                    no_price_asins.append(asin)
            publish_asins = filtered_asins
            for asin in no_price_asins:
                self._mark_asin_no_price(asin)
            if skipped_success:
                self._pub_log("[SKIP] 已过滤 {} 个已上品成功 ASIN".format(len(skipped_success)))
            if no_price_asins:
                self._pub_log("[SKIP] 已过滤 {} 个无价格 ASIN".format(len(no_price_asins)))
            if not_ready_asins:
                self._pub_log("[SKIP] 已过滤 {} 个未抓取成功 ASIN".format(len(not_ready_asins)))
            if not publish_asins:
                if not_ready_asins and no_price_asins:
                    self.status_lbl.config(text="所选商品未抓取成功/无价格，已自动跳过")
                elif no_price_asins:
                    self.status_lbl.config(text="No price， stop")
                elif not_ready_asins:
                    self.status_lbl.config(text="所选商品未抓取成功，已自动跳过")
                else:
                    self.status_lbl.config(text="所选商品均已上品成功，已自动跳过")
                return
            # 并发模式按“全部选中项”执行，缺图项在 worker 内计为失败，
            # 确保结果弹窗以“选中总数”为准，不会因预过滤而提前结束。
            try:
                max_workers = int(self.fetch_workers.get())
            except Exception:
                max_workers = 5
            max_workers = max(1, min(3, max_workers))
            self.fetch_workers.set(str(max_workers))
            self._publish_session_id += 1
            current_session_id = self._publish_session_id
            self._stop_publish = False
            self.progress.start(12)
            valid_count = 0
            for asin in publish_asins:
                info = self.product_cache.get(asin)
                if info and info.get('image_url'):
                    valid_count += 1
            self.status_lbl.config(text='并发上品中：{} 个商品（可发布 {} 个，跳过 {} 个，{}线程）...'.format(
                len(selected_asins), valid_count, len(skipped_success), min(max_workers, len(publish_asins))))
            threading.Thread(target=self._publish_worker, args=(publish_asins, max_workers, current_session_id), daemon=True).start()
            return

        target_asin = selected_asins[0] if selected_asins else self.current_asin
        if target_asin is None:
            messagebox.showwarning('提示', '请先勾选一个商品或点击左侧 ASIN')
            return
        if self.asin_status.get(target_asin) == "success":
            self.status_lbl.config(text="ASIN {} 已上品成功，已自动跳过".format(target_asin))
            self._pub_log("[SKIP] {} 已上品成功，跳过本次上品".format(target_asin))
            return

        # 同步当前 ASIN，后续流程统一使用 current_asin
        self.current_asin = target_asin

        # 必须抓取成功才允许上品
        is_ready, reason = self._is_asin_fetch_ready(target_asin)
        if not is_ready:
            self._mark_asin_not_fetch_ready(target_asin, reason)
            self.status_lbl.config(text="ASIN {} 未抓取成功，已跳过上品".format(target_asin))
            messagebox.showwarning('提示', 'ASIN {} 未抓取成功（{}），请先重新抓取'.format(target_asin, reason))
            return

        # 检查商品是否有图片
        product_info = self.product_cache.get(target_asin)
        if not product_info or not product_info.get('image_url'):
            messagebox.showwarning('提示', 'ASIN {} 没有图片信息，请先抓取商品'.format(target_asin))
            return
        if not self._has_publishable_price(product_info):
            self._mark_asin_no_price(target_asin)
            self.status_lbl.config(text='无价格，无法上品')
            return
        
        # 每次点击“开始上品”创建新的会话ID，并清理停止标志
        self._publish_session_id += 1
        current_session_id = self._publish_session_id
        self._stop_publish = False
        try:
            if self._shein_publisher is not None:
                setattr(self._shein_publisher, '_stop_publish', False)
        except Exception:
            pass

        # 已禁用该主线程分支：避免点击“开始上品”后界面卡死
        if False and self._shein_publisher is not None and self._shein_publisher.is_alive():
            self.status_lbl.config(text='已有 Chrome 实例，打开商品发布页...')
            try:
                self._shein_publisher.driver.get(SHEIN_PUBLISH_URL)
                time.sleep(2)
                self.status_lbl.config(text='正在上传商品图片...')
                threading.Thread(target=self._auto_upload_image, args=(current_session_id,), daemon=True).start()
                return
            except Exception as e:
                self._pub_log('打开页面失败: ' + str(e)[:40])
                self._shein_publisher = None
        
        # 在后台线程中复用已登录浏览器；没有则再创建
        self.status_lbl.config(text='准备打开商品发布页...')

        def _init_selenium():
            def _set_status(text):
                self.after(0, lambda t=text: self.status_lbl.config(text=t))

            try:
                dev_mode = is_dev_mode()
                run_headless = (not dev_mode)
                # 模式切换保护：避免开发者模式误复用之前的无界面实例
                if self._shein_publisher is not None:
                    old_headless = bool(getattr(self._shein_publisher, "_headless_mode", False))
                    if old_headless != run_headless:
                        self._pub_log("检测到浏览器模式切换（headless={} -> {}），重建实例".format(
                            old_headless, run_headless))
                        try:
                            if getattr(self._shein_publisher, "driver", None):
                                self._shein_publisher.driver.quit()
                        except Exception:
                            pass
                        self._shein_publisher = None
                if self._shein_publisher is not None and (not self._is_publisher_reusable(self._shein_publisher)):
                    self._pub_log('检测到浏览器实例不可复用（可能已被手动关闭），将重新连接')
                    self._shein_publisher = None
                # 开发者模式要求可视化全流程，强制重建可见浏览器实例（不复用旧实例）
                if dev_mode and self._is_publisher_reusable(self._shein_publisher):
                    self._pub_log("[DEV] 开始上品：重建可视浏览器以便观察全过程")
                    try:
                        self._shein_publisher.driver.quit()
                    except Exception:
                        pass
                    self._shein_publisher = None

                target_account = (self.shein_account.get().strip()
                                  or self._login_session_account
                                  or self._shein_publisher_account
                                  or 'default')
                # 先拿到旧会话快照，再启动新实例，避免被新空白实例覆盖
                login_cookies, login_storage, login_session_storage = self._get_saved_login_session()
                _set_status('正在启动后台发布实例...' if run_headless else '正在连接或启动浏览器...')
                launch_account = target_account
                launch_clone_from = ""

                def _launch_publisher_instance(preferred_account, preferred_clone):
                    _pub = SheinPublisher(log_cb=self._pub_log)
                    _launch_account = preferred_account
                    _launch_clone_from = preferred_clone
                    try:
                        _pub.start_browser(
                            account=_launch_account,
                            clone_from_account=_launch_clone_from,
                            headless=run_headless,
                            force_new=(not run_headless),
                        )
                    except Exception as first_e:
                        # 兼容场景：先登录(非Dev)后切Dev，原账号profile可能短时残留锁，重试独立Dev profile。
                        if not dev_mode:
                            raise
                        self._pub_log("[DEV] 首次启动失败，重试独立可视实例: {}".format(str(first_e)[:80]))
                        _launch_account = "{}__dev".format(target_account)
                        _launch_clone_from = target_account
                        _pub.start_browser(
                            account=_launch_account,
                            clone_from_account=_launch_clone_from,
                            headless=False,
                            force_new=True,
                        )
                    self._shein_publisher = _pub
                    self._shein_publisher_account = _launch_account
                    # 注入已保存登录会话，确保无需重新登录
                    if login_cookies or login_storage or login_session_storage:
                        try:
                            _pub.driver.get("https://sso.geiwohuo.com/#/login")
                            time.sleep(0.5)
                        except Exception:
                            pass
                        self._inject_login_session_to_driver(
                            _pub.driver, login_cookies, login_storage, login_session_storage
                        )
                        self._pub_log("已注入登录会话(cookies:{} storage:{})".format(
                            len(login_cookies), len(login_storage)))
                    return _pub, _launch_account, _launch_clone_from

                pub, launch_account, launch_clone_from = _launch_publisher_instance(
                    launch_account, launch_clone_from
                )
                _set_status('浏览器已就绪，正在打开商品发布页...')

                open_ok = False
                for open_try in range(1, 4):
                    try:
                        pub.driver.get(SHEIN_PUBLISH_URL)
                    except Exception as nav_e:
                        self._pub_log("[WARN] 打开商品发布页异常(第{}/3次): {}".format(
                            open_try, str(nav_e)[:80]))
                    time.sleep(2)
                    if self._is_publish_page_ready(pub.driver):
                        open_ok = True
                        break
                    self._pub_log("[WARN] 未进入商品发布页（第{}/3次），关闭实例并重开".format(open_try))
                    if open_try >= 3:
                        break
                    try:
                        if getattr(pub, "driver", None):
                            pub.driver.quit()
                    except Exception:
                        pass
                    self._shein_publisher = None
                    pub, launch_account, launch_clone_from = _launch_publisher_instance(
                        target_account, ""
                    )
                if not open_ok:
                    raise RuntimeError("未能进入商品发布页：已自动重开实例3次仍失败")
                _set_status('正在上传商品图片...')
                threading.Thread(target=self._auto_upload_image, args=(current_session_id,), daemon=True).start()
            except Exception as e:
                _set_status('操作失败: ' + str(e)[:40])
                self._pub_log('操作失败: ' + str(e))
                self.after(0, lambda err=str(e): messagebox.showerror('失败', err[:100]))

        threading.Thread(target=_init_selenium, daemon=True).start()

    def _is_publish_stopped(self):
        if self._stop_publish:
            return True
        try:
            return bool(self._shein_publisher is not None and getattr(self._shein_publisher, '_stop_publish', False))
        except Exception:
            return False

    def _check_stop_or_return(self, status='已停止上品', session_id=None):
        # 会话ID变化表示已有新任务启动，旧线程必须立刻退出
        if session_id is not None and session_id != self._publish_session_id:
            self._pub_log('[STOP] 检测到新上品会话，旧线程退出')
            return True
        if self._license_locked:
            self._pub_log('[STOP] 账号授权失效，任务终止')
            self.after(0, lambda: self.status_lbl.config(text="账号权限失效，任务已终止"))
            return True
        if self._is_publish_stopped():
            self._pub_log('[STOP] 用户点击停止，抓取已中断')
            self.after(0, lambda s=status: self.status_lbl.config(text=s))
            return True
        return False

    def _auto_upload_image(self, session_id=None):
        """自动上传商品图片、选择推荐类目、填写基础信息（在后台线程中调用）。"""
        self._publish_running = True
        target_asin = None
        dot = None
        if session_id is None:
            session_id = self._publish_session_id
        try:
            if self.current_asin is None or self._shein_publisher is None:
                return
            target_asin = self.current_asin
            self._active_publish_asin = target_asin

            if self._check_stop_or_return(session_id=session_id):
                return

            product_info = self.product_cache.get(target_asin)
            dot = self.asin_dots.get(target_asin)
            is_ready, reason = self._is_asin_fetch_ready(target_asin)
            if not is_ready:
                self.after(0, lambda a=target_asin, r=reason: self._mark_asin_not_fetch_ready(a, r))
                return
            if not product_info or not product_info.get('image_url'):
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                return

            if self._check_stop_or_return(session_id=session_id):
                return
            self._log_publish_progress(target_asin, "开始上品")
            self._log_publish_progress(target_asin, "上品中")
            if dot:
                self.after(0, lambda a=target_asin: self._set_asin_status(a, "publishing"))
            def _set_status(msg, stage=None):
                self._set_publish_status(target_asin, msg, stage)
                self._update_publish_progress_by_msg(target_asin, msg)

            def _update_publish_fail_reason(reason_text):
                try:
                    reason = str(reason_text or "").strip()
                    if not isinstance(product_info, dict):
                        return
                    if reason:
                        product_info["publish_fail_reason"] = reason[:300]
                    else:
                        product_info.pop("publish_fail_reason", None)
                    if target_asin in self.product_cache and isinstance(self.product_cache.get(target_asin), dict):
                        if reason:
                            self.product_cache[target_asin]["publish_fail_reason"] = reason[:300]
                        else:
                            self.product_cache[target_asin].pop("publish_fail_reason", None)
                    if self.current_asin == target_asin:
                        self.after(0, self._show_current_asin_now)
                except Exception:
                    pass

            try:
                self._shein_publisher._dismiss_announcements()
            except Exception:
                pass

            if self._check_stop_or_return(session_id=session_id):
                return
            image_url = product_info.get('image_url')
            temp_dir = os.path.join(tempfile.gettempdir(), 'shein_images')
            os.makedirs(temp_dir, exist_ok=True)
            temp_image = os.path.join(temp_dir, '{}.jpg'.format(target_asin))

            def _restart_instance_and_open_publish():
                """关闭当前实例并新开实例，直达商品发布页。"""
                try:
                    old_pub = self._shein_publisher
                    run_headless = bool(
                        getattr(old_pub, "_headless_mode", (not is_dev_mode()))
                    )
                    try:
                        if old_pub and getattr(old_pub, "driver", None):
                            old_pub.driver.quit()
                    except Exception:
                        pass
                    self._shein_publisher = None

                    target_account = (self.shein_account.get().strip()
                                      or self._login_session_account
                                      or self._shein_publisher_account
                                      or 'default')
                    login_cookies, login_storage, login_session_storage = self._get_saved_login_session()
                    pub = None
                    for reopen_try in range(1, 4):
                        pub = SheinPublisher(log_cb=self._pub_log)
                        pub.start_browser(
                            account=target_account,
                            headless=run_headless,
                            force_new=(not run_headless),
                        )
                        self._shein_publisher = pub
                        self._shein_publisher_account = target_account

                        if login_cookies or login_storage or login_session_storage:
                            try:
                                pub.driver.get("https://sso.geiwohuo.com/#/login")
                                time.sleep(0.5)
                            except Exception:
                                pass
                            self._inject_login_session_to_driver(
                                pub.driver, login_cookies, login_storage, login_session_storage
                            )
                        try:
                            pub.driver.get(SHEIN_PUBLISH_URL)
                        except Exception:
                            pass
                        time.sleep(2)
                        if self._is_publish_page_ready(pub.driver):
                            try:
                                pub._dismiss_announcements()
                            except Exception:
                                pass
                            return True
                        self._pub_log("[WARN] 重开后未进入商品发布页（第{}/3次），继续重开".format(reopen_try))
                        try:
                            if getattr(pub, "driver", None):
                                pub.driver.quit()
                        except Exception:
                            pass
                        self._shein_publisher = None
                    return False
                except Exception as _re_e:
                    self._pub_log('[ERROR] 重开实例失败: {}'.format(str(_re_e)[:80]))
                    return False

            def _is_https_download_error(_err):
                t = str(_err or "")
                tl = t.lower()
                return (
                    "httpscon" in tl
                    or "httpsconnection" in tl
                    or "max retries exceeded" in tl
                    or "connection aborted" in tl
                    or "ssleoferror" in tl
                    or "sslerror" in tl
                )

            # 识图前置图片下载：命中 HTTPSConnection 类错误时，自动重开实例并重试（最多3次）
            downloaded_ok = False
            for dl_try in range(1, 4):
                if self._check_stop_or_return(session_id=session_id):
                    return
                _set_status('下载商品图片（第{}/3次）...'.format(dl_try), "上品中")
                try:
                    _tmp_dl = None
                    try:
                        if self._shein_publisher:
                            _tmp_dl = self._shein_publisher._download_identify_image_to_temp(image_url)
                    except Exception:
                        _tmp_dl = None
                    if _tmp_dl and os.path.exists(_tmp_dl):
                        with open(_tmp_dl, "rb") as _rf, open(temp_image, "wb") as _wf:
                            _wf.write(_rf.read())
                        try:
                            os.remove(_tmp_dl)
                        except Exception:
                            pass
                    else:
                        # 兜底：保留原 requests 直连下载
                        response = requests.get(image_url, timeout=(5, 20))
                        response.raise_for_status()
                        with open(temp_image, 'wb') as f:
                            f.write(response.content)
                    downloaded_ok = True
                    break
                except Exception as e:
                    err_text = str(e)
                    self._pub_log('[WARN] 下载图片失败（第{}/3次）: {}'.format(dl_try, err_text[:120]))
                    if _is_https_download_error(e):
                        if dl_try < 3:
                            _set_status('下载图片失败（HTTPS连接异常），重开实例重试第{}/3次...'.format(dl_try + 1), "上品中")
                            if not _restart_instance_and_open_publish():
                                _set_status('✗ 重开实例失败，归属上品失败', "上品失败")
                                if dot:
                                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                                return
                            continue
                        _set_status('✗ 下载图片失败（HTTPS连接异常），3次重试后仍失败', "上品失败")
                        if dot:
                            self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                        return
                    # 非 HTTPSConnection 类错误保持原策略：直接失败
                    _set_status('下载图片失败: {}'.format(err_text[:40]), "上品失败")
                    if dot:
                        self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                    return

            if not downloaded_ok:
                _set_status('✗ 下载图片失败，归属上品失败', "上品失败")
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                return

            category_selected = False
            last_step_err = ""
            last_recognition_state = ""
            for attempt in range(1, 4):
                if self._check_stop_or_return(session_id=session_id):
                    return

                _set_status('识图发品流程：第{}/3次尝试...'.format(attempt), "上品中")

                try:
                    self._shein_publisher._dismiss_announcements()
                except Exception:
                    pass

                step_err = None
                if self._check_stop_or_return(session_id=session_id):
                    return
                _set_status('点击"识图发品"按钮（第{}/3次）...'.format(attempt), "上品中")
                if not self._shein_publisher.click_identify_image_button():
                    step_err = '未找到"识图发品"按钮'

                if not step_err:
                    if self._check_stop_or_return(session_id=session_id):
                        return
                    _set_status('上传图片到 SHEIN（第{}/3次）...'.format(attempt), "上品中")
                    if not self._shein_publisher.upload_product_image(temp_image):
                        step_err = "图片上传失败"
                    elif getattr(self._shein_publisher, "_last_recognition_state", "") == "no_category":
                        step_err = "识图发品暂无分类推荐"

                if not step_err:
                    if self._check_stop_or_return(session_id=session_id):
                        return
                    _set_status('选择第一个推荐类目（第{}/3次）...'.format(attempt), "上品中")
                    if not self._shein_publisher.select_first_category():
                        step_err = "未识别到推荐类目"

                if not step_err:
                    category_selected = True
                    self._pub_log('[OK] 商品 {} 识图选类目成功（第{}/3次）'.format(target_asin, attempt))
                    break

                self._pub_log('[WARN] 商品 {} 识图第{}/3次失败: {}'.format(target_asin, attempt, step_err))
                no_cat_hint = False
                try:
                    no_cat_hint = bool(self._shein_publisher.has_no_category_recommend_hint())
                except Exception:
                    no_cat_hint = False
                rec_state = str(getattr(self._shein_publisher, "_last_recognition_state", "") or "").strip()
                step_text = str(step_err or "")
                last_step_err = step_text
                last_recognition_state = rec_state
                no_category_case = (
                    no_cat_hint
                    or rec_state in ("no_category", "timeout")
                    or ("暂无分类推荐" in step_text)
                    or ("未识别到推荐类目" in step_text)
                )

                if no_category_case and attempt < 3:
                    _set_status('✗ 识图后未出现可选类目，第{}/3次：重开实例后重试...'.format(attempt), "上品中")
                    self._pub_log(
                        '[RETRY] 类目未出现（err={} state={} hint={}），开始第{}/3次重试'.format(
                            step_text or "N/A", rec_state or "N/A", no_cat_hint, attempt + 1
                        )
                    )
                    if not _restart_instance_and_open_publish():
                        _set_status('✗ 重开实例失败，归属上品失败', "上品失败")
                        if dot:
                            self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                        return
                    continue
                if no_category_case and attempt >= 3:
                    break
                _set_status('✗ 识图流程失败（{}），归属上品失败'.format(step_err), "上品失败")
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                return

            if not category_selected:
                _set_status('✗ 识图发品失败：3次重试后仍未出现可选类目，归属上品失败', "上品失败")
                self._pub_log(
                    '[ERROR] 商品 {} 识图发品失败：3次重试后仍未出现可选类目（最后错误={}，识别状态={}）'.format(
                        target_asin, last_step_err or "N/A", last_recognition_state or "N/A"
                    )
                )
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                return

            if self._check_stop_or_return(session_id=session_id):
                return
            _set_status('✓ 已选择推荐类目，点击确认...', "上品中")
            time.sleep(1)
            if not self._shein_publisher.click_confirm_button():
                _set_status('✗ 点击确认按钮失败', "上品失败")
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                return

            if self._check_stop_or_return(session_id=session_id):
                return
            _set_status('✓ 商品类目确认成功，等待页面加载...', "上品中")
            time.sleep(1.5)

            if self._check_stop_or_return(session_id=session_id):
                return
            _set_status('填写商品基础信息...', "上品中")
            if not self._shein_publisher.fill_product_info(product_info):
                _set_status('✗ 基础信息填写失败', "上品失败")
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                return

            if self._check_stop_or_return(session_id=session_id):
                return
            _set_status('✓ 商品基础信息填写完成', "上品中")

            _set_status('等待页面加载，准备填写规格信息...', "上品中")
            time.sleep(2)
            if self._check_stop_or_return(session_id=session_id):
                return

            _set_status('填写规格信息...', "上品中")
            try:
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
                        product_info_pub["price"] = str(round(_orig * mult, 2))

                if self._check_stop_or_return(session_id=session_id):
                    return
                _set_status('上传细节图...', "上品中")
                self._shein_publisher.fill_spec_and_supply_info(product_info_pub)
                if self._check_stop_or_return(session_id=session_id):
                    return
                _set_status('✓ 规格已确定', "上品中")
            except Exception as spec_e:
                self._pub_log('[ERROR] 规格及供应信息填写异常: {}'.format(str(spec_e)[:80]))
                _set_status('规格及供应信息填写遇到问题，请手动检查', "上品失败")

            if self._check_stop_or_return(session_id=session_id):
                return
            _set_status('点击发布商品...', "上品中")
            self._pub_log('[DEBUG] 开始点击发布商品按鈕...')
            try:
                from selenium.webdriver.common.by import By as _By
                _driver = self._shein_publisher.driver
                submitted = False
                _pub_xpaths = [
                    "//div[contains(@class,'auditOperate') or contains(@class,'bottomAlert')]//button[@type='submit']",
                    "//button[@type='submit' and .//span[normalize-space(text())='发布商品']]",
                    "//button[.//span[normalize-space(text())='发布商品']]",
                    "//button[contains(text(),'发布商品')]",
                    "//span[normalize-space(text())='发布商品']/parent::button",
                    "//button[contains(text(),'提交')]",
                    "//span[contains(text(),'发布商品')]",
                ]
                for _xp in _pub_xpaths:
                    if self._check_stop_or_return(session_id=session_id):
                        return
                    try:
                        for _btn in _driver.find_elements(_By.XPATH, _xp):
                            if self._check_stop_or_return(session_id=session_id):
                                return
                            try:
                                if _btn.is_displayed() and _btn.is_enabled():
                                    _driver.execute_script("arguments[0].scrollIntoView({block:'center'});", _btn)
                                    time.sleep(0.5)
                                    _driver.execute_script("arguments[0].click();", _btn)
                                    self._pub_log('[OK] 已点击发布商品按鈕')
                                    submitted = True
                                    break
                            except Exception:
                                continue
                    except Exception:
                        continue
                    if submitted:
                        break

                if submitted:
                    _set_status('✓ 已点击发布，等待确认弹窗...', "上品中")
                    _confirm_clicked = False
                    _deadline = time.time() + 15
                    _dlg_xpaths = [
                        "//button[.//span[contains(text(),'一件翻译并发布')]]",
                        "//button[contains(text(),'一件翻译并发布')]",
                        "//span[contains(text(),'一件翻译并发布')]/parent::button",
                        "//*[contains(@class,'so-modal') or contains(@class,'dialog')]//button[.//span[contains(text(),'翻译')]]",
                    ]
                    while time.time() < _deadline:
                        if self._check_stop_or_return(session_id=session_id):
                            return
                        for _xp in _dlg_xpaths:
                            try:
                                for _btn in _driver.find_elements(_By.XPATH, _xp):
                                    if self._check_stop_or_return(session_id=session_id):
                                        return
                                    if _btn.is_displayed() and _btn.is_enabled():
                                        _driver.execute_script("arguments[0].scrollIntoView({block:'center'});", _btn)
                                        time.sleep(0.3)
                                        _driver.execute_script("arguments[0].click();", _btn)
                                        self._pub_log('[OK] 已点击一件翻译并发布')
                                        _confirm_clicked = True
                                        break
                            except Exception:
                                continue
                            if _confirm_clicked:
                                break
                        if _confirm_clicked:
                            break
                        time.sleep(0.5)
                    if _confirm_clicked:
                        _set_status('检查发布结果文案...', "上品中")
                        _submit_ok = False
                        _submit_deadline = time.time() + 20
                        while time.time() < _submit_deadline:
                            if self._check_stop_or_return(session_id=session_id):
                                return
                            try:
                                _ok_els = _driver.find_elements(
                                    _By.XPATH,
                                    "//*[contains(normalize-space(.),'提交成功') and contains(normalize-space(.),'等待审核中')]"
                                )
                                for _ok_el in _ok_els:
                                    try:
                                        if _ok_el.is_displayed():
                                            _submit_ok = True
                                            break
                                    except Exception:
                                        continue
                            except Exception:
                                pass
                            if _submit_ok:
                                break
                            time.sleep(1)

                        if _submit_ok:
                            _update_publish_fail_reason("")
                            _set_status('✓ 商品已提交发布', "上品成功")
                            if dot:
                                self.after(0, lambda a=target_asin: self._set_asin_status(a, "success"))
                            self._pub_log('商品 {} 已提交发布'.format(target_asin))
                        else:
                            fail_reason = ""
                            try:
                                if hasattr(self._shein_publisher, "get_publish_failure_reason"):
                                    fail_reason = self._shein_publisher.get_publish_failure_reason(wait_seconds=1.5)
                            except Exception:
                                fail_reason = ""
                            _update_publish_fail_reason(fail_reason)
                            if fail_reason:
                                _set_status('✗ 发布失败：未检测到“提交成功，等待审核中”；上品失败原因：{}'.format(fail_reason[:80]), "上品失败")
                            else:
                                _set_status('✗ 发布失败：未检测到“提交成功，等待审核中”', "上品失败")
                            if dot:
                                self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                            if fail_reason:
                                self._pub_log('[ERROR] 商品 {} 发布失败：点击一件翻译并发布后未出现“提交成功，等待审核中”；失败原因: {}'.format(target_asin, fail_reason))
                            else:
                                self._pub_log('[ERROR] 商品 {} 发布失败：点击一件翻译并发布后未出现“提交成功，等待审核中”'.format(target_asin))
                    else:
                        _set_status('✗ 发布失败：15秒内未检测到"一键翻译并发布"确认弹窗', "上品失败")
                        if dot:
                            self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                        self._pub_log('[ERROR] 商品 {} 发布失败：点击发布按鈕后15秒内未出现"一键翻译并发布"确认弹窗，请检查页面状态'.format(target_asin))
                else:
                    _set_status('✗ 未找到发布按鈕，请手动点击发布', "上品失败")
                    if dot:
                        self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                    self._pub_log('[ERROR] 未找到发布商品按鈕')
            except Exception as pub_e:
                self._pub_log('[ERROR] 点击发布商品异常: {}'.format(str(pub_e)[:80]))
                _set_status('发布出错: {}'.format(str(pub_e)[:40]), "上品失败")
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))

        except Exception as e:
            if self._is_stop_requested(session_id=session_id) or '用户已停止上品' in str(e):
                self._pub_log('[STOP] 用户已停止上品')
                self._set_publish_status(target_asin, '已停止上品', "上品失败")
                if target_asin:
                    self._set_asin_progress(target_asin, 0, "已停止", state="stopped")
            else:
                self._set_publish_status(target_asin, '上传出错: {}'.format(str(e)[:40]), "上品失败")
                if dot:
                    self.after(0, lambda a=target_asin: self._set_asin_status(a, "fail"))
                self._pub_log('上传出错: ' + str(e))
        finally:
            try:
                if target_asin:
                    _st = self.asin_status.get(target_asin, "")
                    if _st == "success":
                        self._log_publish_progress(target_asin, "上品成功")
                    elif _st == "fail":
                        self._log_publish_progress(target_asin, "上品失败")
            except Exception:
                pass
            # 单商品流程结束后默认清理实例；开发者模式点击停止时保留当前页面。
            try:
                stop_requested = bool(
                    self._stop_publish or
                    (session_id is not None and session_id != self._publish_session_id)
                )
                keep_alive_for_dev_stop = bool(is_dev_mode() and stop_requested)
                if keep_alive_for_dev_stop:
                    self._pub_log('[STOP][DEV] 保留当前浏览器页面，不关闭实例与driver')
                elif self._shein_publisher and getattr(self._shein_publisher, "driver", None):
                    self._shein_publisher.quit()
                    self._pub_log('[CLEANUP] 当前商品结束，已关闭浏览器实例与driver')
            except Exception as _qe:
                self._pub_log('[WARN] 清理浏览器实例失败: {}'.format(str(_qe)[:80]))
            finally:
                if not (is_dev_mode() and bool(self._stop_publish)):
                    self._shein_publisher = None
            self._active_publish_asin = None
            self._publish_running = False
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
        if self._license_locked:
            self._show_auth_lock_popup()
            return
        sel=[a for a,v in self.asin_vars.items() if v.get()]
        if not sel: messagebox.showinfo("提示","请先勾选要抓取的 ASIN"); return
        if self._fetch_thread and self._fetch_thread.is_alive():
            messagebox.showinfo("提示","正在抓取中，请稍候..."); return
        
        # 重置停止标志，允许新的抓取任务开始
        self._stop_publish = False
        self._last_fetch_no_price_asins = []
        
        # 分离已成功缓存 和 需要重新抓取 的 ASIN（缓存按地区隔离）
        need_fetch = []
        already_cached = []
        current_region = self.amazon_region.get() if hasattr(self, "amazon_region") else "美国"
        for asin in sel:
            if asin in self.product_cache:
                cached_info = self.product_cache[asin]
                inferred = self._infer_fetch_status(cached_info)
                region_match = self._is_cache_region_match(cached_info, current_region)
                is_cached_ok = (inferred == "fetch_success" and region_match)
                if is_cached_ok:
                    already_cached.append(asin)
                else:
                    del self.product_cache[asin]
                    need_fetch.append(asin)
            else:
                need_fetch.append(asin)
        
        # 已成功缓存的 ASIN 确保显示绿色圆点
        for asin in already_cached:
            self._set_asin_status(asin, "fetch_success")
        
        # 如果没有需要抓取的商品，直接返回
        if not need_fetch:
            self.status_lbl.config(text="所有选中商品在当前抓取地区都已抓取成功，无需重复抓取")
            return
        
        try:
            max_workers = int(self.fetch_workers.get())
        except Exception:
            max_workers = 5
        max_workers = max(1, min(6, max_workers))
        # 美国站反爬更敏感，自动收缩并发，提升跨电脑稳定性
        if str(self.amazon_region.get() or "").strip() == "美国":
            max_workers = min(max_workers, 3)
        self.fetch_workers.set(str(max_workers))
        self.progress.start(12)
        # 直接开始抓取，自动跳过已缓存的商品
        if already_cached:
            self.status_lbl.config(text="正在抓取 {} 个商品（{}线程，自动跳过 {} 个已缓存）...".format(
                len(need_fetch), max_workers, len(already_cached)))
        else:
            self.status_lbl.config(text="正在抓取 {} 个商品（{}线程）...".format(len(need_fetch), max_workers))
        self._fetch_thread=threading.Thread(target=self._worker,args=(need_fetch,max_workers,already_cached),daemon=True)
        self._fetch_thread.start()

    def _worker(self,asins,max_workers=5,already_cached=None):
        if already_cached is None:
            already_cached = []
        total = len(asins)
        no_price_asins = []
        region = self.amazon_region.get()
        for asin in asins:
            # 抓取进行中：黄色
            try:
                self.after(0, lambda a=asin: self._set_asin_status(a, "fetching"))
            except RuntimeError:
                pass  # 主线程已退出

        def _is_anti_blocked_title(_title):
            t = str(_title or "").strip().lower()
            if not t:
                return False
            return (
                ("被亚马逊反爬" in t)
                or ("captcha" in t)
                or ("robot" in t)
                or ("automated access" in t)
                or ("bot check" in t)
            )

        def _fetch_one(asin):
            try:
                last_info = None
                for _try in range(3):
                    info = fetch_amazon_product(asin, region=region)
                    if isinstance(info, dict):
                        info["_fetch_region"] = region
                    title = str((info or {}).get("title", "") or "")
                    _fp = ("获取失败", "HTTP ", "错误:", "被亚马逊反爬", "Error")
                    is_fail = (not info) or any(title.startswith(p) for p in _fp)
                    anti_blocked = _is_anti_blocked_title(title)
                    last_info = info
                    # 非反爬失败不重试，避免无意义重复请求
                    if (not is_fail) or (not anti_blocked):
                        return asin, info, is_fail, anti_blocked
                    if _try < 2:
                        time.sleep(1.5 + (_try * 1.2) + random.uniform(0.6, 1.8))
                info = last_info if isinstance(last_info, dict) else {"asin": asin, "title": "被亚马逊反爬拦截，请稍后重试"}
                info["_fetch_region"] = region
                return asin, info, True, True
            except Exception as e:
                info = {"asin": asin, "title": "获取失败: {}".format(str(e)[:30]), "_fetch_region": region}
                return asin, info, True, False

        done = 0
        adaptive_workers = max(1, int(max_workers or 1))
        anti_rates_window = []
        clean_batch_streak = 0
        batch_start = 0
        while batch_start < total:
            batch_size = max(1, min(adaptive_workers * 3, 15, total - batch_start))
            batch_asins = asins[batch_start: batch_start + batch_size]
            anti_block_count = 0
            with ThreadPoolExecutor(max_workers=adaptive_workers) as executor:
                futures = [executor.submit(_fetch_one, asin) for asin in batch_asins]
                for fut in as_completed(futures):
                    try:
                        asin, info, is_fail, anti_blocked = fut.result()
                        self.product_cache[asin] = info
                        done += 1
                        if anti_blocked:
                            anti_block_count += 1
                        try:
                            self.after(0, lambda d=done, t=total, a=asin: self.status_lbl.config(text="抓取完成 {}/{}：{}".format(d, t, a)))
                        except RuntimeError:
                            pass
                        if info and info.get("stock_low"):
                            try:
                                self.after(0, lambda a=asin: self._set_asin_status(a, "stock_low"))
                            except RuntimeError:
                                pass
                        elif info and info.get("sku_too_many"):
                            try:
                                self.after(0, lambda a=asin: self._set_asin_status(a, "sku_too_many"))
                            except RuntimeError:
                                pass
                        elif info and info.get("no_suitable_sku"):
                            try:
                                self.after(0, lambda a=asin: self._set_asin_status(a, "no_suitable_sku"))
                            except RuntimeError:
                                pass
                        elif is_fail:
                            try:
                                self.after(0, lambda a=asin: self._set_asin_status(a, "fetch_fail"))
                            except RuntimeError:
                                pass
                        elif not self._has_publishable_price(info):
                            no_price_asins.append(asin)
                            try:
                                self.after(0, lambda a=asin: self._set_asin_status(a, "no_price"))
                                self.after(0, lambda: self.status_lbl.config(text="No price， stop"))
                            except RuntimeError:
                                pass
                        else:
                            try:
                                self.after(0, lambda a=asin: self._set_asin_status(a, "fetch_success"))
                            except RuntimeError:
                                pass
                        if self.current_asin == asin:
                            try:
                                self.after(0, self._show_current_asin_now)
                            except RuntimeError:
                                pass
                    except Exception:
                        pass
            anti_rate = (float(anti_block_count) / float(len(batch_asins))) if batch_asins else 0.0
            anti_rates_window.append(anti_rate)
            if len(anti_rates_window) > 3:
                anti_rates_window = anti_rates_window[-3:]
            avg_anti_rate = (sum(anti_rates_window) / float(len(anti_rates_window))) if anti_rates_window else anti_rate

            prev_workers = adaptive_workers
            if anti_block_count >= 2 or anti_rate >= 0.5 or avg_anti_rate >= 0.4:
                adaptive_workers = max(1, adaptive_workers - 1)
                clean_batch_streak = 0
            else:
                if anti_block_count == 0:
                    clean_batch_streak += 1
                else:
                    clean_batch_streak = 0
                if clean_batch_streak >= 2 and avg_anti_rate <= 0.12 and adaptive_workers < max_workers:
                    adaptive_workers = min(max_workers, adaptive_workers + 1)
                    clean_batch_streak = 0

            if adaptive_workers != prev_workers:
                try:
                    self.after(0, lambda nw=adaptive_workers, pr=prev_workers, ar=anti_rate: self.status_lbl.config(
                        text="检测到反爬波动，抓取线程 {} -> {}（当前命中率 {:.0%}）".format(pr, nw, ar)
                    ))
                except RuntimeError:
                    pass
            # 批次间冷却，降低后半段 ASIN 被连续风控的概率
            remaining = total - (batch_start + len(batch_asins))
            if remaining > 0:
                cool_down = 3.0 if remaining > 18 else 2.0
                if anti_rate >= 0.5:
                    cool_down = max(cool_down, 5.0)
                elif anti_rate >= 0.2:
                    cool_down = max(cool_down, 3.5)
                try:
                    self.after(0, lambda d=done, t=total, s=cool_down: self.status_lbl.config(
                        text="抓取完成 {}/{}，冷却 {:.1f}s 后继续".format(d, t, s)
                    ))
                except RuntimeError:
                    pass
                time.sleep(cool_down)
            batch_start += len(batch_asins)
        try:
            self.after(0, lambda ac=already_cached, np=list(no_price_asins): self._done(ac, np))
        except RuntimeError:
            pass  # 主线程已退出

    def _done(self, already_cached=None, no_price_asins=None):
        if already_cached is None:
            already_cached = []
        if no_price_asins is None:
            no_price_asins = []
        self.progress.stop()
        # 清理线程对象，允许下次抓取
        self._fetch_thread = None
        self._last_fetch_no_price_asins = list(no_price_asins)
        cached_count = len(already_cached)
        total_cached = len(self.product_cache)
        msg = "抓取完成，共缓存 {} 个商品".format(total_cached)
        if cached_count > 0:
            msg += "（其中 {} 个为已缓存）".format(cached_count)
        if no_price_asins:
            msg = "No price， stop"
        self.status_lbl.config(text=msg)
        if self.current_asin and self.current_asin in self.product_cache:
            self._show_current_asin_now()

    def _show(self,info):
        self._cancel_pending_sku_render()
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
        title_bar = tk.Frame(inf, bg=BG_PANEL)
        title_bar.pack(fill="x", padx=4, pady=2)
        title_bar.grid_columnconfigure(0, weight=1)
        title_edit_frame = tk.Frame(title_bar, bg=BG_PANEL)
        title_edit_frame.grid(row=0, column=0, sticky="ew")
        tk.Label(
            title_edit_frame,
            text="商品标题（可编辑）",
            font=("Segoe UI",9),
            fg=TEXT_SUB,
            bg=BG_PANEL,
            anchor="w"
        ).pack(anchor="w")
        title_var = tk.StringVar(value=str(info.get("title", "") or ""))
        title_entry = tk.Entry(
            title_edit_frame,
            textvariable=title_var,
            font=("Segoe UI",11,"bold"),
            fg=TEXT_MAIN,
            bg=BG_CARD,
            insertbackground=TEXT_MAIN,
            relief="flat",
            bd=2
        )
        title_entry.pack(fill="x", pady=(2, 0))
        publish_fail_reason = str(info.get("publish_fail_reason", "") or "").strip()
        if publish_fail_reason:
            tk.Label(
                title_bar,
                text="上品失败原因：{}".format(publish_fail_reason),
                font=("Segoe UI",10,"bold"),
                fg=RED,
                bg=BG_PANEL,
                anchor="w",
                justify="left",
                wraplength=320
            ).grid(row=0, column=1, sticky="w", padx=(8, 0))
        row("ASIN: {}  货号: XYZ-{}".format(info.get("asin",""), info.get("asin","")),10,TEXT_SUB)
        row("品牌: {}".format(info.get("brand","N/A")),10,YELLOW)
        asin = str(info.get("asin", "") or "").strip()
        price_frame = tk.Frame(inf, bg=BG_PANEL)
        price_frame.pack(fill="x", padx=4, pady=2)
        tk.Label(
            price_frame,
            text="价格:",
            font=("Segoe UI", 12, "bold"),
            fg=GREEN,
            bg=BG_PANEL
        ).pack(side="left")
        price_var = tk.StringVar(value=str(info.get("price", "N/A") or "N/A"))
        price_entry = tk.Entry(
            price_frame,
            textvariable=price_var,
            width=18,
            font=("Segoe UI", 12, "bold"),
            fg=GREEN,
            bg=BG_CARD,
            insertbackground=GREEN,
            relief="flat",
            bd=2,
        )
        price_entry.pack(side="left", padx=(6, 8))
        tk.Label(
            price_frame,
            text="可手动修改",
            font=("Segoe UI", 9),
            fg=TEXT_SUB,
            bg=BG_PANEL
        ).pack(side="left")

        def _commit_price(_event=None, _asin=asin, _var=price_var):
            self._save_manual_price(_asin, _var.get())

        price_entry.bind("<FocusOut>", _commit_price)
        price_entry.bind("<Return>", lambda e: (_commit_price(), "break")[1])
        def _commit_title(_event=None, _asin=asin, _var=title_var):
            self._save_manual_title_features(_asin, raw_title=_var.get())
        title_entry.bind("<FocusOut>", _commit_title)
        title_entry.bind("<Return>", lambda e: (_commit_title(), "break")[1])
        row("评分: {}  评论数: {}".format(info.get("rating","N/A"),info.get("reviews","N/A")),10,TEXT_SUB)
        url=info.get("url","")
        if url:
            tk.Button(inf,text="在亚马逊中查看",bg=BG_CARD,fg=ACCENT2,
                font=("Segoe UI",9),relief="flat",bd=0,cursor="hand2",
                command=lambda u=url:webbrowser.open(u)).pack(anchor="w",padx=4,pady=4)
        feats = info.get("features", [])
        feature_lines = []
        if isinstance(feats, (list, tuple)):
            feature_lines = [str(ft or "").strip() for ft in feats if str(ft or "").strip()]
        elif str(feats or "").strip():
            feature_lines = [str(feats).strip()]
        tk.Frame(self.df,bg=BORDER,height=1).pack(fill="x",padx=20,pady=6)
        tk.Label(self.df,text="商品特点（可编辑，每行一条）",font=("Segoe UI",11,"bold"),fg=ACCENT2,bg=BG_PANEL).pack(anchor="w",padx=20)
        feat_editor = tk.Text(
            self.df,
            height=max(4, min(8, len(feature_lines) + 1)),
            font=("Segoe UI",10),
            fg=TEXT_MAIN,
            bg=BG_CARD,
            insertbackground=TEXT_MAIN,
            relief="flat",
            bd=2,
            wrap="word"
        )
        feat_editor.pack(fill="x", padx=20, pady=(4, 2))
        feat_editor.insert("1.0", "\n".join(feature_lines))
        tk.Label(self.df,text="提示：保存后将按这里的内容填写上品“商品描述”",font=("Segoe UI",9),fg=TEXT_SUB,bg=BG_PANEL).pack(anchor="w",padx=20,pady=(0,4))

        def _commit_features(_event=None, _asin=asin, _text=feat_editor):
            try:
                raw_text = _text.get("1.0", "end-1c")
            except Exception:
                raw_text = ""
            self._save_manual_title_features(_asin, raw_features_text=raw_text)

        feat_editor.bind("<FocusOut>", _commit_features)
        feat_editor.bind("<Control-Return>", lambda e: (_commit_features(), "break")[1])

        def _publish_from_detail(_asin=asin):
            _commit_price()
            _commit_title()
            _commit_features()
            info_latest = self.product_cache.get(_asin) or info
            self._publish_direct(info_latest)

        tk.Frame(self.df,bg=BORDER,height=1).pack(fill="x",padx=20,pady=10)
        self._btn(self.df,"发布此商品到 SHEIN",ACCENT,
            _publish_from_detail).pack(anchor="w",padx=20,pady=(0,16))
        preview_url = info.get("image_url") or ""
        self._current_preview_url = preview_url
        if preview_url:
            cached_photo = self._get_cached_preview_photo(preview_url)
            if cached_photo is not None:
                self._set_img(cached_photo, preview_url)
            else:
                threading.Thread(target=self._load_img,args=(preview_url,),daemon=True).start()
            # 预加载相邻商品主图，提升连续切换速度
            self._prefetch_adjacent_previews(info.get("asin"))
        
        # 显示 SKU 维度信息（每个SKU展示5张图）
        sku_list = info.get("sku_list", [])
        tk.Frame(self.df,bg=BORDER,height=1).pack(fill="x",padx=20,pady=10)
        tk.Label(self.df,text="商品详情页 · SKU 信息（每个SKU图片前5张，Ctrl+点击打开）",font=("Segoe UI",11,"bold"),fg=ACCENT2,bg=BG_PANEL).pack(anchor="w",padx=20)
        if info.get("stock_low"):
            tk.Label(
                self.df,
                text="亚马逊库存告急，不做抓取",
                font=("Segoe UI",10,"bold"),
                fg=RED,
                bg=BG_PANEL,
                anchor="w"
            ).pack(anchor="w",padx=24,pady=(2,6))
        if info.get("sku_too_many"):
            sku_count = int(info.get("sku_count") or 0)
            tip = "SKU过多，不做爬取"
            if sku_count > 0:
                tip = "SKU过多，不做爬取（共{}个）".format(sku_count)
            tk.Label(
                self.df,
                text=tip,
                font=("Segoe UI",10,"bold"),
                fg=RED,
                bg=BG_PANEL,
                anchor="w"
            ).pack(anchor="w",padx=24,pady=(2,6))
        other_specs = info.get("other_specs", {})
        if other_specs:
            parts = ["{}：{}".format(k, "，".join(str(v) for v in vals)) for k, vals in other_specs.items()]
            tk.Label(self.df,text="其他规格：" + "  /  ".join(parts),font=("Segoe UI",10),fg=TEXT_SUB,bg=BG_PANEL,anchor="w",wraplength=700,justify="left").pack(anchor="w",padx=24,pady=(0,6))
        if sku_list:
            sku_holder = tk.Frame(self.df, bg=BG_PANEL)
            sku_holder.pack(fill="x")
            self._render_sku_cards_chunked(sku_holder, sku_list, start_idx=0, batch_size=8)
        else:
            tk.Label(self.df,text="暂无 SKU 数据",font=("Segoe UI",10),fg=TEXT_SUB,bg=BG_PANEL).pack(anchor="w",padx=24,pady=4)

    def _cancel_pending_sku_render(self):
        if self._sku_render_after_id:
            try:
                self.after_cancel(self._sku_render_after_id)
            except Exception:
                pass
            self._sku_render_after_id = None

    def _render_sku_cards_chunked(self, container, sku_list, start_idx=0, batch_size=8):
        """分批渲染 SKU 卡片，避免一次性创建大量控件导致切换卡顿。"""
        if container is None:
            return
        try:
            if not int(container.winfo_exists()):
                return
        except Exception:
            return

        end_idx = min(len(sku_list), start_idx + batch_size)
        for idx in range(start_idx, end_idx):
            sku = sku_list[idx] or {}
            sku_asin = sku.get("sku_asin", "")
            sku_attrs = sku.get("sku_attributes", "默认规格")
            sku_images = sku.get("images", [])[:5]
            sku_basis = sku.get("dimension_basis", [])

            card=tk.Frame(container,bg=BG_CARD)
            card.pack(fill="x",padx=20,pady=4)
            tk.Label(card,text="SKU {}: {}".format(idx+1, sku_asin),font=("Consolas",10,"bold"),fg=TEXT_MAIN,bg=BG_CARD,anchor="w").pack(fill="x",padx=10,pady=(8,2))
            spec_row = tk.Frame(card, bg=BG_CARD)
            spec_row.pack(fill="x", padx=10, pady=(0, 2))
            tk.Label(
                spec_row,
                text="规格: {}".format(sku_attrs),
                font=("Segoe UI",9),
                fg=YELLOW,
                bg=BG_CARD,
                anchor="w",
                wraplength=680,
                justify="left"
            ).pack(side="left", anchor="w")
            if self._is_nonstandard_color_spec(sku_attrs):
                tk.Label(
                    spec_row,
                    text="  该颜色不是SHEIN标准颜色",
                    font=("Segoe UI",9,"bold"),
                    fg=RED,
                    bg=BG_CARD,
                    anchor="w"
                ).pack(side="left", anchor="w")
            basis_text = " / ".join(sku_basis) if sku_basis else "未识别"
            tk.Label(card,text="分类依据: {}".format(basis_text),font=("Segoe UI",9),fg=TEXT_SUB,bg=BG_CARD,anchor="w",wraplength=680,justify="left").pack(fill="x",padx=10,pady=(0,6))

            if sku_images:
                for img_idx, img_url in enumerate(sku_images):
                    fr=tk.Frame(card,bg=BG_CARD); fr.pack(fill="x",padx=10,pady=(0,2))
                    tk.Label(fr,text="图{}:".format(img_idx+1),fg=TEXT_SUB,bg=BG_CARD,font=("Segoe UI",9)).pack(side="left")
                    link_lbl=tk.Label(fr,text=img_url[:78]+("..." if len(img_url) > 78 else ""),fg=ACCENT,bg=BG_CARD,font=("Segoe UI",9),
                        wraplength=620,justify="left",anchor="w",cursor="hand2")
                    link_lbl.pack(side="left",padx=6)
                    link_lbl.bind("<Control-Button-1>",lambda e,url=img_url:webbrowser.open(url))
            else:
                tk.Label(card,text="该SKU暂无图片",font=("Segoe UI",9),fg=TEXT_SUB,bg=BG_CARD,anchor="w").pack(fill="x",padx=10,pady=(0,8))

        if end_idx < len(sku_list):
            self._sku_render_after_id = self.after(
                1,
                lambda c=container, s=sku_list, n=end_idx, b=batch_size: self._render_sku_cards_chunked(c, s, n, b)
            )
        else:
            self._sku_render_after_id = None

    def _is_nonstandard_color_spec(self, sku_attrs):
        """仅用于 GUI 展示：判断规格颜色是否不是 SHEIN 标准颜色。"""
        attrs = str(sku_attrs or "").strip()
        if not attrs:
            return False
        if "该颜色不是SHEIN标准颜色" in attrs or "此颜色不是SHEIN标准颜色" in attrs:
            return True
        m = re.search(r"(?:color|colour|颜色)\s*[:：]\s*([^/]+)", attrs, flags=re.IGNORECASE)
        if not m:
            return False
        raw_color = str(m.group(1) or "").strip()
        if not raw_color:
            return False

        # 包装数量文本直接判定为非标准颜色，避免 2|1pack 这类漏标
        packed_raw_letters = re.sub(r"[^a-z]", "", raw_color.lower())
        if any(w in packed_raw_letters for w in ("pack", "pcs", "piece", "set", "count", "unit")):
            return True

        candidates = []
        if callable(_split_color_candidates):
            try:
                candidates = list(_split_color_candidates(raw_color) or [])
            except Exception:
                candidates = []
        if callable(_normalize_color_token):
            try:
                packed = _normalize_color_token(raw_color)
            except Exception:
                packed = re.sub(r"[^a-z0-9]", "", raw_color.lower())
        else:
            packed = re.sub(r"[^a-z0-9]", "", raw_color.lower())
        if packed and packed not in candidates:
            candidates.append(packed)
        if not candidates:
            candidates = [packed] if packed else []

        for c in candidates:
            try:
                if callable(_canonicalize_shein_color) and _canonicalize_shein_color(c):
                    return False
            except Exception:
                continue
        return True

    def _get_cached_preview_photo(self, url):
        with self._preview_cache_lock:
            photo = self._preview_photo_cache.get(url)
            if photo is not None:
                try:
                    self._preview_cache_order.remove(url)
                except Exception:
                    pass
                self._preview_cache_order.append(url)
            return photo

    def _put_cached_preview_photo(self, url, photo):
        with self._preview_cache_lock:
            self._preview_photo_cache[url] = photo
            try:
                self._preview_cache_order.remove(url)
            except Exception:
                pass
            self._preview_cache_order.append(url)
            while len(self._preview_cache_order) > self._preview_cache_max:
                old_url = self._preview_cache_order.pop(0)
                self._preview_photo_cache.pop(old_url, None)

    def _try_mark_preview_inflight(self, url):
        with self._preview_cache_lock:
            if url in self._preview_inflight:
                return False
            self._preview_inflight.add(url)
            return True

    def _clear_preview_inflight(self, url):
        with self._preview_cache_lock:
            self._preview_inflight.discard(url)

    def _prefetch_adjacent_previews(self, asin):
        if not asin or asin not in self.asin_list:
            return
        try:
            idx = self.asin_list.index(asin)
        except Exception:
            return
        neighbors = []
        if idx - 1 >= 0:
            neighbors.append(self.asin_list[idx - 1])
        if idx + 1 < len(self.asin_list):
            neighbors.append(self.asin_list[idx + 1])

        for nb_asin in neighbors:
            info = self.product_cache.get(nb_asin) or {}
            nb_url = info.get("image_url") or ""
            if not nb_url:
                continue
            if self._get_cached_preview_photo(nb_url) is not None:
                continue
            if not self._try_mark_preview_inflight(nb_url):
                continue
            threading.Thread(target=self._prefetch_img_worker, args=(nb_url,), daemon=True).start()

    def _prefetch_img_worker(self, url):
        try:
            img = download_image(url)
            if not img:
                return
            img.thumbnail((220,220), Image.LANCZOS)
            self._safe_ui_after(0, lambda im=img, u=url: self._cache_preview_only(im, u))
        except Exception:
            self._clear_preview_inflight(url)

    def _safe_ui_after(self, delay_ms, callback):
        """线程安全调度 UI 回调；主循环不可用时静默跳过。"""
        try:
            if not int(self.winfo_exists()):
                return False
        except Exception:
            return False
        try:
            self.after(delay_ms, callback)
            return True
        except Exception:
            # 常见于窗口关闭后后台线程仍在回调：RuntimeError/TclError
            return False

    def _cache_preview_only(self, img, url):
        try:
            ph = ImageTk.PhotoImage(img)
            self._put_cached_preview_photo(url, ph)
        finally:
            self._clear_preview_inflight(url)

    def _load_img(self,url):
        # 命中缓存直接显示，避免重复下载
        cached_photo = self._get_cached_preview_photo(url)
        if cached_photo is not None:
            self._safe_ui_after(0, lambda p=cached_photo, u=url: self._set_img(p, u))
            return
        img=download_image(url)
        if img:
            img.thumbnail((220,220),Image.LANCZOS)
            self._safe_ui_after(0, lambda im=img, u=url: self._cache_and_set_img(im, u))

    def _cache_and_set_img(self, img, url):
        try:
            ph=ImageTk.PhotoImage(img)
        except Exception:
            return
        self._put_cached_preview_photo(url, ph)
        self._set_img(ph, url)

    def _set_img(self,photo,url=None):
        # 防止异步加载时串图：仅显示当前选中商品对应图片
        if url and url != self._current_preview_url:
            return
        img_lbl = getattr(self, "img_lbl", None)
        if img_lbl is None:
            return
        try:
            if not int(img_lbl.winfo_exists()):
                return
            self._photo_ref = photo
            img_lbl.config(image=photo, text="")
        except Exception:
            # 详情面板切换时旧 Label 可能已销毁，忽略异步回调即可
            return

    def _pub_log(self, msg):
        """发布日志回调：开发者模式=完整日志，非开发者模式=仅简化上品进度。"""
        m = str(msg)[:100] if msg else ""
        self._route_asin_progress_from_log(m)
        # 本地日志落盘：所有模式都保留完整日志（便于非开发者模式排障）
        self._write_log(msg)
        if not is_dev_mode():
            if not self._is_simple_publish_msg(m):
                return
        # 更新状态栏
        if hasattr(self, "status_lbl"):
            self.after(0, lambda m=m: self.status_lbl.config(text=m))

    def _is_publisher_reusable(self, pub):
        """检查浏览器实例是否可复用（防止用户手动关窗后复用失败）。"""
        try:
            if pub is None:
                return False
            if not pub.is_alive():
                return False
            drv = getattr(pub, 'driver', None)
            if drv is None:
                return False
            _ = drv.window_handles
            _ = drv.current_url
            return True
        except Exception:
            return False

    def _shutdown_all_browsers(self, reason=""):
        """关闭所有由本程序持有的浏览器与 webdriver 引用。"""
        pubs = []
        seen = set()
        try:
            if self._shein_publisher is not None:
                pubs.append(self._shein_publisher)
            with self._worker_publishers_lock:
                for _p in self._worker_publishers.values():
                    if _p is not None:
                        pubs.append(_p)
                self._worker_publishers = {}
        except Exception:
            pass

        for pub in pubs:
            try:
                _id = id(pub)
                if _id in seen:
                    continue
                seen.add(_id)
                if hasattr(pub, "request_stop"):
                    pub.request_stop(force_quit=True)
                elif hasattr(pub, "quit"):
                    pub.quit()
                else:
                    drv = getattr(pub, "driver", None)
                    if drv is not None:
                        drv.quit()
            except Exception:
                pass
        self._shein_publisher = None
        if reason:
            self._pub_log("[STOP] 已关闭全部浏览器/driver: {}".format(reason))
  
    def _kill_edge_processes_on_exit(self):
        """Windows 兜底：强制清理所有 Edge 与 EdgeDriver 进程。"""
        if os.name != "nt":
            return
        targets = ["msedgedriver.exe", "msedge.exe"]
        creation_flags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        for proc_name in targets:
            try:
                cp = subprocess.run(
                    ["taskkill", "/F", "/T", "/IM", proc_name],
                    capture_output=True,
                    text=True,
                    creationflags=creation_flags
                )
                out = (cp.stdout or cp.stderr or "").strip()
                if cp.returncode == 0:
                    try:
                        self._pub_log("[STOP] 已强制结束进程: {}".format(proc_name))
                    except Exception:
                        pass
                else:
                    # 128/1 常见于“未找到进程”，属于可接受结果
                    if out and ("未找到" not in out) and ("not found" not in out.lower()):
                        try:
                            self._pub_log("[WARN] 清理进程 {} 返回码{}: {}".format(
                                proc_name, cp.returncode, out[:160]))
                        except Exception:
                            pass
            except Exception as e:
                try:
                    self._pub_log("[WARN] 清理进程 {} 异常: {}".format(proc_name, str(e)[:120]))
                except Exception:
                    pass


    def _publish_worker(self,asins,max_workers=5,session_id=None):
        success_list = []
        fail_list = []
        total = len(asins)
        def _read_timeout_env(name, default_value, min_sec, max_sec):
            raw = str(os.environ.get(name, "") or "").strip()
            try:
                val = int(float(raw)) if raw else int(default_value)
            except Exception:
                val = int(default_value)
            return max(int(min_sec), min(int(max_sec), val))

        # 双阈值超时策略：
        # 1) 无进度超时：长期没有阶段变化才判定卡死（默认 420s）
        # 2) 硬超时：总耗时兜底，防止极端情况下无限等待（默认 1200s）
        per_asin_stall_timeout_sec = _read_timeout_env(
            "SHEIN_PUBLISH_STALL_TIMEOUT_SEC", 420, 180, 3600
        )
        per_asin_hard_timeout_sec = _read_timeout_env(
            "SHEIN_PUBLISH_HARD_TIMEOUT_SEC",
            max(1200, per_asin_stall_timeout_sec * 2),
            per_asin_stall_timeout_sec + 120,
            10800,
        )
        self._pub_log(
            "[CFG] 单商品超时策略：无进度{}秒，总耗时{}秒".format(
                per_asin_stall_timeout_sec, per_asin_hard_timeout_sec
            )
        )
        done = 0
        result_lock = threading.Lock()
        task_lock = threading.Lock()
        self._stop_publish = False  # 确保开始时标志为 False
        with self._worker_publishers_lock:
            self._worker_publishers = {}
            self._worker_active_asins = {}

        try:
            max_workers = int(max_workers)
        except Exception:
            max_workers = 5
        max_workers = max(1, min(20, max_workers, total if total > 0 else 1))

        # 获取登录会话（优先当前实例，兜底使用缓存），供多线程实例复用
        login_cookies, login_storage, login_session_storage = self._get_saved_login_session()

        base_account = (self.shein_account.get() or '').strip() or 'default'
        try:
            _price_mult = float(self.price_multiplier.get())
        except Exception:
            _price_mult = 3.0
        # 同时启动过多浏览器会触发“授权中/网页无法访问”，限制到3更稳
        max_workers = min(max_workers, 3)
        dev_mode_now = bool(is_dev_mode())
        reusable_main_pub = self._shein_publisher if self._is_publisher_reusable(self._shein_publisher) else None
        # 非开发者模式下，避免复用主实例导致授权态污染扩散到并发 worker
        if (not dev_mode_now):
            reusable_main_pub = None
        # 开发者模式要求可视化：若当前主实例是无界面浏览器，禁止复用并重建可视实例。
        if dev_mode_now and reusable_main_pub is not None:
            old_headless = bool(getattr(reusable_main_pub, "_headless_mode", False))
            if old_headless:
                self._pub_log("[DEV] 检测到主实例为无界面模式，重建可视浏览器")
                try:
                    if getattr(reusable_main_pub, "driver", None):
                        reusable_main_pub.driver.quit()
                except Exception:
                    pass
                if self._shein_publisher is reusable_main_pub:
                    self._shein_publisher = None
                reusable_main_pub = None
        if reusable_main_pub is not None:
            self._pub_log("[POOL] 复用主浏览器作为一个工作线程，减少额外driver进程")
        next_idx = 0

        def _next_asin():
            nonlocal next_idx
            with task_lock:
                if next_idx >= total:
                    return None
                asin = asins[next_idx]
                next_idx += 1
                return asin

        def _record_result(asin, ok, err=''):
            nonlocal done
            # 会话隔离：旧会话线程的晚到结果不允许覆盖当前会话状态
            if session_id is not None and session_id != self._publish_session_id:
                return
            with result_lock:
                done += 1
                if ok:
                    success_list.append(asin)
                else:
                    fail_list.append((asin, err))
                d = done
                s = len(success_list)
                f = len(fail_list)

            dot = self.asin_dots.get(asin)
            if ok:
                try:
                    if asin in self.product_cache and isinstance(self.product_cache.get(asin), dict):
                        self.product_cache[asin].pop("publish_fail_reason", None)
                except Exception:
                    pass
                if dot: self.after(0, lambda a=asin: self._set_asin_status(a, "success"))
                self._log_publish_progress(asin, "上品成功")
                self._pub_log("[OK {}/{}] {} 上品成功".format(s, total, asin))
            else:
                try:
                    if asin in self.product_cache and isinstance(self.product_cache.get(asin), dict):
                        _cached_info = self.product_cache.get(asin) or {}
                        _existing_reason = str(_cached_info.get("publish_fail_reason", "") or "").strip()
                        _err_reason = str(err or "").strip()
                        if (not _existing_reason) and _err_reason:
                            _cached_info["publish_fail_reason"] = _err_reason[:300]
                except Exception:
                    pass
                if dot: self.after(0, lambda a=asin: self._set_asin_status(a, "fail"))
                self._log_publish_progress(asin, "上品失败")
                self._pub_log("[FAIL {}/{}] {} 失败: {}".format(f, total, asin, str(err)[:80]))
                try:
                    if self.current_asin == asin:
                        self.after(0, self._show_current_asin_now)
                except Exception:
                    pass

            self.after(0, lambda dd=d, tt=total, ss=s, ff=f:
                self.status_lbl.config(text="并发上品进度 {}/{}（成功{}，失败{}）".format(dd, tt, ss, ff)))

        def _worker_loop(worker_idx):
            def _worker_log(msg):
                # 会话隔离：旧会话日志不更新当前会话进度
                if session_id is not None and session_id != self._publish_session_id:
                    return
                _msg = str(msg)[:220]
                _asin = None
                try:
                    with self._worker_publishers_lock:
                        _asin = self._worker_active_asins.get(worker_idx)
                except Exception:
                    _asin = None
                # 直接把 worker 日志映射到 worker 当前 ASIN，避免多线程进度混乱。
                if _asin:
                    try:
                        self._update_publish_progress_by_msg(_asin, _msg)
                        _mm = re.search(r"图(\d+)已提交", _msg)
                        if _mm and ("SKU行" in _msg):
                            _img_idx = int(_mm.group(1))
                            _pct = min(74, 50 + _img_idx * 4)
                            self._set_asin_progress(
                                _asin, _pct, "上传第{}张细节图中".format(_img_idx), state="running")
                        elif "细节图上传完成" in _msg:
                            self._set_asin_progress(_asin, 75, "细节图上传完成", state="running")
                    except Exception:
                        pass
                self._pub_log('[W{}] {}'.format(worker_idx, _msg))
            worker_has_failure = False
            auth_fail_streak = 0
            worker_headless = not is_dev_mode()

            def _inject_login_session(driver):
                """将主登录实例的 cookies/localStorage/sessionStorage 注入 worker 浏览器。"""
                self._inject_login_session_to_driver(
                    driver, login_cookies, login_storage, login_session_storage
                )

            def _is_on_publish_page(url):
                u = str(url or "").lower()
                return ("followsales-pro/list" in u
                        and ("commoditiescategory" in u or "commodities-category" in u))

            def _has_publish_dom(driver):
                """URL 不稳定时，用页面关键特征兜底判定是否已在发布页。"""
                try:
                    return bool(driver.execute_script(r"""
                        const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
                        const body = document && document.body ? clean(document.body.innerText || '') : '';
                        if (body.includes('识图发品') || body.includes('上传图片') || body.includes('商品发布')) return true;
                        const fileInput = document.querySelector("input[type='file']");
                        if (fileInput) return true;
                        const nodes = Array.from(document.querySelectorAll('button,span,div,a'));
                        for (const n of nodes) {
                            const t = clean(n.innerText || n.textContent || '');
                            if (!t) continue;
                            if (t.includes('识图发品') || t.includes('上传图片') || t.includes('确认，下一步')) return true;
                        }
                        return false;
                    """))
                except Exception:
                    return False

            def _is_auth_page(url):
                u = str(url or "").lower()
                return ("/auth/" in u) or ("gmpsso" in u) or ("authorize" in u and "sso" in u)

            def _wait_leave_auth_page(driver, wait_sec=18):
                end_ts = time.time() + float(wait_sec)
                while time.time() < end_ts:
                    try:
                        cur = driver.current_url or ""
                    except Exception:
                        cur = ""
                    if (not _is_auth_page(cur)) and cur:
                        return cur
                    if _has_publish_dom(driver):
                        return cur
                    time.sleep(0.8)
                try:
                    return driver.current_url or ""
                except Exception:
                    return ""

            def _ensure_publish_page(driver):
                try:
                    cur = driver.current_url or ""
                except Exception:
                    cur = ""
                if _is_on_publish_page(cur) or _has_publish_dom(driver):
                    return True

                _has_session = bool(login_cookies or login_storage)

                # 优化：先导航到基础域名建立 cookie 上下文，注入会话后再直达发布页
                if _has_session:
                    try:
                        driver.get("https://sso.geiwohuo.com/#/login")
                        time.sleep(0.5)
                    except Exception:
                        pass
                    _inject_login_session(driver)
                    _worker_log("已注入登录会话(cookies:{} storage:{})".format(
                        len(login_cookies), len(login_storage)))

                for _attempt in range(7):
                    try:
                        driver.get(SHEIN_PUBLISH_URL)
                        time.sleep(1.4 if _attempt == 0 else (2.0 + 0.6 * _attempt))
                        cur = driver.current_url or ""
                        if _is_on_publish_page(cur) or _has_publish_dom(driver):
                            return True
                        if _is_auth_page(cur):
                            _worker_log("授权中页面，第{}/7次重试".format(_attempt + 1))
                            # 先等待 SSO 回跳，有些机器会慢几秒
                            cur2 = _wait_leave_auth_page(driver, wait_sec=18 + _attempt * 2)
                            if _is_on_publish_page(cur2) or _has_publish_dom(driver):
                                return True
                            try:
                                driver.get("https://sso.geiwohuo.com/#/home")
                                time.sleep(1.2 + 0.3 * _attempt)
                            except Exception:
                                pass
                            continue
                        # URL 不是授权页但也不是发布页时，强制 replace 一次，避免历史回退/拦截导致的假跳转
                        try:
                            driver.execute_script("window.location.replace(arguments[0]);", SHEIN_PUBLISH_URL)
                            time.sleep(1.2 + 0.3 * _attempt)
                            cur3 = driver.current_url or ""
                            if _is_on_publish_page(cur3) or _has_publish_dom(driver):
                                return True
                        except Exception:
                            pass
                    except Exception:
                        pass

                # 最终重试：再次注入会话 + 导航
                if _has_session:
                    _inject_login_session(driver)
                    try:
                        driver.get("https://sso.geiwohuo.com/#/home")
                        time.sleep(1.2)
                        driver.get(SHEIN_PUBLISH_URL)
                        time.sleep(2.2)
                        cur = driver.current_url or ""
                    except Exception:
                        cur = ""
                    return _is_on_publish_page(cur) or _has_publish_dom(driver)
                return False

            worker_account = '{}__w{}'.format(base_account, worker_idx)
            use_main_pub = (reusable_main_pub is not None and worker_idx == 1)
            pub = reusable_main_pub if use_main_pub else SheinPublisher(log_cb=_worker_log)

            def _rebuild_worker_instance(reason_text="", force_visible=False):
                """当前 worker 连续授权失败时，重建浏览器实例并恢复到发布页。"""
                nonlocal pub, use_main_pub, auth_fail_streak, worker_headless
                try:
                    if force_visible and worker_headless:
                        worker_headless = False
                        _worker_log("授权链路降级：自动切换可视浏览器模式")
                    _worker_log("触发实例重建: {}".format(reason_text or "unknown"))
                    old_pub = pub
                    try:
                        if old_pub and getattr(old_pub, "driver", None):
                            old_pub.driver.quit()
                    except Exception:
                        pass
                    if use_main_pub:
                        # 主实例已失效，避免后续误复用
                        self._shein_publisher = None
                    rebuilt = SheinPublisher(log_cb=_worker_log)
                    rebuilt_account = "{}__w{}_r{}".format(
                        base_account, worker_idx, int(time.time()) % 100000
                    )
                    rebuilt.start_browser(
                        account=rebuilt_account,
                        clone_from_account=base_account,
                        headless=worker_headless,
                        force_new=True,
                    )
                    pub = rebuilt
                    use_main_pub = False
                    with self._worker_publishers_lock:
                        self._worker_publishers[worker_idx] = pub
                    if not _ensure_publish_page(pub.driver):
                        _worker_log("重建后仍未进入发布页")
                        return False
                    auth_fail_streak = 0
                    _worker_log("重建后已恢复商品发布页")
                    return True
                except Exception as _rb_e:
                    _worker_log("重建实例失败: {}".format(str(_rb_e)[:100]))
                    return False
            try:
                if not use_main_pub:
                    # 先克隆已登录账号 profile，再补会话注入，尽量避免每个线程从登录页慢跳转
                    pub.start_browser(
                        account=worker_account,
                        clone_from_account=base_account,
                        headless=worker_headless,
                        force_new=True,
                    )
                else:
                    _worker_log("复用主浏览器实例")
                with self._worker_publishers_lock:
                    self._worker_publishers[worker_idx] = pub
                _startup_ok = _ensure_publish_page(pub.driver)
                if not _startup_ok and worker_headless:
                    if not _rebuild_worker_instance("启动阶段授权中", force_visible=True):
                        self._pub_log('[W{}] 启动阶段授权失败，结束 worker'.format(worker_idx))
                        return
                    _startup_ok = True
                if not _startup_ok:
                    self._pub_log('[W{}] 会话注入后仍未进入发布页'.format(worker_idx))
                else:
                    self._pub_log('[W{}] 已进入商品发布页'.format(worker_idx))

                while True:
                    if self._stop_publish:
                        return
                    if session_id is not None and session_id != self._publish_session_id:
                        return

                    asin = _next_asin()
                    if asin is None:
                        return
                    with self._worker_publishers_lock:
                        self._worker_active_asins[worker_idx] = asin
                    info = self.product_cache.get(asin, {})
                    is_ready, not_ready_reason = self._is_asin_fetch_ready(asin)
                    if not is_ready:
                        self.after(0, lambda a=asin, r=not_ready_reason: self._mark_asin_not_fetch_ready(a, r))
                        worker_has_failure = True
                        _record_result(asin, False, "未抓取成功: {}".format(not_ready_reason))
                        continue
                    if not info or not info.get('image_url'):
                        self.after(0, lambda a=asin: self._mark_asin_not_fetch_ready(a, "缺少图片信息"))
                        worker_has_failure = True
                        _record_result(asin, False, '缺少商品图片')
                        continue

                    try:
                        self._log_publish_progress(asin, "开始上品")
                        self.after(0, lambda a=asin: self._set_asin_status(a, "publishing"))
                        self.after(0, lambda a=asin: self._set_asin_progress(a, 15, "上品中", state="running"))
                        self._log_publish_progress(asin, "上品中")
                        if not getattr(pub, "driver", None):
                            _worker_log("检测到浏览器实例已关闭，准备为当前商品重建实例")
                            if not _rebuild_worker_instance("单商品开始前初始化实例"):
                                worker_has_failure = True
                                _record_result(asin, False, '实例重建失败：无法启动浏览器')
                                return
                        ok_page = _ensure_publish_page(pub.driver)
                        if not ok_page:
                            if _rebuild_worker_instance("ASIN授权中", force_visible=True):
                                ok_page = _ensure_publish_page(pub.driver)
                        if not ok_page:
                            auth_fail_streak += 1
                            worker_has_failure = True
                            _record_result(asin, False, '未能进入商品发布页（授权中）')
                            if auth_fail_streak >= 1:
                                _worker_log("连续{}次进入发布页失败，尝试重建实例".format(auth_fail_streak))
                                if not _rebuild_worker_instance("连续授权失败", force_visible=True):
                                    _worker_log("重建失败，结束当前worker")
                                    return
                            continue
                        auth_fail_streak = 0
                        cat_result = auto_match_category(info)
                        cat_name = cat_result["name"]
                        cat_path = cat_result["path"]
                        with ThreadPoolExecutor(max_workers=1) as _asin_exec:
                            _f = _asin_exec.submit(
                                pub.publish_product,
                                info,
                                cat_path if cat_path else [cat_name],
                                _price_mult
                            )
                            result = False
                            _start_ts = time.time()
                            _last_progress_ts = _start_ts
                            _last_snapshot = None
                            _last_wait_log_ts = 0.0
                            try:
                                while True:
                                    try:
                                        result = _f.result(timeout=8)
                                        break
                                    except FutureTimeoutError:
                                        if _f.done():
                                            continue
                                        now_ts = time.time()
                                        pg = self.asin_progress.get(asin) or {}
                                        pg_pct = int(pg.get("pct", 0) or 0)
                                        pg_text = str(pg.get("text", "") or "").strip()
                                        pg_state = str(pg.get("state", "") or "").strip()
                                        snapshot = (pg_pct, pg_text, pg_state)
                                        if snapshot != _last_snapshot:
                                            _last_snapshot = snapshot
                                            _last_progress_ts = now_ts

                                        elapsed_sec = int(now_ts - _start_ts)
                                        no_progress_sec = int(now_ts - _last_progress_ts)
                                        stage_text = pg_text or "处理中"

                                        if now_ts - _last_wait_log_ts >= 30:
                                            _worker_log(
                                                "ASIN={} 上品进行中 {}秒（当前阶段：{}）".format(
                                                    asin, elapsed_sec, stage_text[:50]
                                                )
                                            )
                                            _last_wait_log_ts = now_ts

                                        hit_stall_timeout = (no_progress_sec >= per_asin_stall_timeout_sec)
                                        hit_hard_timeout = (elapsed_sec >= per_asin_hard_timeout_sec)
                                        if not hit_stall_timeout and not hit_hard_timeout:
                                            continue

                                        try:
                                            if hasattr(pub, "request_stop"):
                                                pub.request_stop(force_quit=True)
                                        except Exception:
                                            pass
                                        worker_has_failure = True
                                        if hit_stall_timeout:
                                            timeout_reason = (
                                                "超时：{}秒内无阶段进展（总耗时{}秒，当前阶段：{}）".format(
                                                    no_progress_sec, elapsed_sec, stage_text[:60]
                                                )
                                            )
                                        else:
                                            timeout_reason = (
                                                "超时：总耗时{}秒仍未完成（当前阶段：{}）".format(
                                                    elapsed_sec, stage_text[:60]
                                                )
                                            )
                                        _record_result(asin, False, timeout_reason)
                                        _worker_log("ASIN={} 上品超时，已中断并准备重建实例".format(asin))
                                        if not _rebuild_worker_instance("单商品上品超时"):
                                            _worker_log("超时后重建失败，结束当前worker")
                                            return
                                        break
                            except FutureTimeoutError:
                                try:
                                    if hasattr(pub, "request_stop"):
                                        pub.request_stop(force_quit=True)
                                except Exception:
                                    pass
                                worker_has_failure = True
                                _record_result(
                                    asin,
                                    False,
                                    "超时：{}秒内未完成".format(per_asin_hard_timeout_sec)
                                )
                                _worker_log("ASIN={} 上品超时，已中断并准备重建实例".format(asin))
                                if not _rebuild_worker_instance("单商品上品超时"):
                                    _worker_log("超时后重建失败，结束当前worker")
                                    return
                                continue
                            if not _f.done():
                                continue
                        if result:
                            _record_result(asin, True)
                        else:
                            worker_has_failure = True
                            _fail_reason = ""
                            try:
                                _fail_reason = str((info or {}).get("publish_fail_reason", "") or "").strip()
                            except Exception:
                                _fail_reason = ""
                            _record_result(asin, False, _fail_reason or '发布流程未能确认成功')
                    except Exception as e:
                        worker_has_failure = True
                        _record_result(asin, False, str(e))
                    finally:
                        # 每个商品结束后默认关闭实例；开发者模式点击停止时保留当前页面。
                        try:
                            stop_requested = bool(
                                self._stop_publish or
                                (session_id is not None and session_id != self._publish_session_id)
                            )
                            keep_alive_for_dev_stop = bool(is_dev_mode() and stop_requested)
                            if keep_alive_for_dev_stop:
                                _worker_log("ASIN={} 开发者模式停止：保留当前浏览器页面".format(asin))
                            elif pub is not None and getattr(pub, "driver", None):
                                pub.quit()
                                _worker_log("ASIN={} 收尾完成：已关闭浏览器实例与驱动".format(asin))
                        except Exception as _close_e:
                            _worker_log("ASIN={} 收尾关闭实例失败: {}".format(asin, str(_close_e)[:80]))
                        try:
                            with self._worker_publishers_lock:
                                if self._worker_active_asins.get(worker_idx) == asin:
                                    self._worker_active_asins.pop(worker_idx, None)
                        except Exception:
                            pass
            finally:
                try:
                    if pub.driver:
                        stop_requested = bool(
                            self._stop_publish or
                            (session_id is not None and session_id != self._publish_session_id)
                        )
                        if stop_requested:
                            if is_dev_mode():
                                self._pub_log('[W{}] [STOP][DEV] 已停止任务，保留当前页面用于继续调试'.format(worker_idx))
                            else:
                                try:
                                    if hasattr(pub, "request_stop"):
                                        pub.request_stop(force_quit=True)
                                    else:
                                        pub.driver.quit()
                                except Exception:
                                    pass
                                self._pub_log('[W{}] [STOP] 已关闭浏览器与driver'.format(worker_idx))
                        elif is_dev_mode() and worker_has_failure:
                            self._pub_log('[W{}] [DEV] 检测到失败，保留当前浏览器页面用于排查'.format(worker_idx))
                        else:
                            if use_main_pub:
                                self._pub_log('[W{}] [POOL] 主浏览器线程完成，保留主实例供后续复用'.format(worker_idx))
                            else:
                                pub.driver.quit()
                except Exception:
                    pass
                finally:
                    with self._worker_publishers_lock:
                        self._worker_active_asins.pop(worker_idx, None)
                        self._worker_publishers.pop(worker_idx, None)

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [executor.submit(_worker_loop, i + 1) for i in range(max_workers)]
            for fut in as_completed(futures):
                try:
                    fut.result()
                except Exception as e:
                    self._pub_log('并发线程异常: {}'.format(str(e)[:80]))

        stopped = bool(self._stop_publish)
        if stopped:
            self._pub_log("上品已停止，共完成 {}/{}".format(done, total))
        show_popup = (not stopped and done >= total)
        self.after(0, lambda s=success_list, f=fail_list, t=total, sp=show_popup:
            self._publish_done(s, f, expected_total=t, show_popup=sp))

    def _publish_done(self, success_list, fail_list, expected_total=None, show_popup=True):
        self.progress.stop()
        total = len(success_list) + len(fail_list)
        if expected_total is not None and total < expected_total:
            self.status_lbl.config(text="上品进行中：已完成 {}/{}，等待其余任务结束...".format(total, expected_total))
            return
        self._stop_publish = False  # 全部线程结束后再重置，避免停止状态被过早清空
        msg = "上品完成！\n\n成功：{} 个\n失败：{} 个\n共计：{} 个".format(
            len(success_list), len(fail_list), total)
        if fail_list:
            msg += "\n\n失败列表：\n"
            msg += "\n".join("  {} - {}".format(a, e[:40]) for a,e in fail_list[:10])
            if len(fail_list) > 10:
                msg += "\n  ...(共 {} 个失败)".format(len(fail_list))
        self.status_lbl.config(text="上品完成 成功:{} 失败:{}".format(
            len(success_list), len(fail_list)))
        if show_popup:
            messagebox.showinfo("上品结果", msg)

    def _signal_stop_to_all_publishers(self):
        """向所有已持有的发布实例发送停止标志，不强制关闭浏览器。"""
        try:
            if self._shein_publisher is not None:
                setattr(self._shein_publisher, "_stop_publish", True)
        except Exception:
            pass
        try:
            with self._worker_publishers_lock:
                for _pub in self._worker_publishers.values():
                    if _pub is not None:
                        try:
                            setattr(_pub, "_stop_publish", True)
                        except Exception:
                            pass
        except Exception:
            pass

    def _stop_publish_action(self):
        """停止上品进程。"""
        dev_mode = bool(is_dev_mode())
        if getattr(self, "_bargain_fetch_running", False):
            self._stop_bargain_fetch = True
            self._set_bargain_progress("正在停止...", state="fail")
            self.status_lbl.config(text="正在停止议价抓取...")
            try:
                pub = self._bargain_runtime_publisher or self._shein_publisher
                if pub is not None:
                    setattr(pub, "_stop_publish", True)
            except Exception:
                pass

            def _stop_bargain_async():
                is_temp_runtime = bool(self._bargain_runtime_is_temp)
                try:
                    pub = self._bargain_runtime_publisher
                    # 非开发者模式：议价抓取使用临时后台浏览器，停止时立即关闭实例与进程
                    if (not dev_mode) and is_temp_runtime and pub is not None:
                        self._close_publisher_instance(pub, reason="用户停止议价抓取")
                finally:
                    if (not dev_mode) and is_temp_runtime:
                        self.after(0, lambda: self.status_lbl.config(text="已停止议价抓取，后台浏览器已关闭"))
                    elif dev_mode:
                        self.after(0, lambda: self.status_lbl.config(text="开发者模式：已暂停议价抓取，保留当前页面"))
                    else:
                        self.after(0, lambda: self.status_lbl.config(text="已停止议价抓取"))

            threading.Thread(target=_stop_bargain_async, daemon=True).start()
            if not self._publish_running:
                return

        if not self._stop_publish:
            self._publish_session_id += 1  # 使当前会话立即失效，强制旧线程退出
            self._stop_publish = True
            self._signal_stop_to_all_publishers()
            self._reset_publishing_asins_to_unpublished()
            self._fetch_thread = None
            self.progress.stop()
            if dev_mode:
                self.status_lbl.config(text="开发者模式：已暂停上品任务，保留当前页面")
                self._pub_log("[STOP][DEV] 已发送停止信号，暂停当前任务并保留浏览器页面")
                return
            # 非开发者模式：继续执行后台清理，确保进程与资源被及时回收。
            self.status_lbl.config(text="正在停止上品：后台清理浏览器与driver...")
            self._pub_log("[STOP] 已发送停止信号，后台开始清理浏览器与driver")

            if not self._stop_cleanup_running:
                self._stop_cleanup_running = True
                def _async_stop_cleanup():
                    try:
                        self._shutdown_all_browsers(reason="用户点击停止")
                        self.after(0, lambda: self.status_lbl.config(text="已停止上品：所有任务已终止"))
                        self._pub_log("[STOP] 停止完成：所有上品线程与浏览器实例已终止")
                    finally:
                        self._stop_cleanup_running = False
                threading.Thread(target=_async_stop_cleanup, daemon=True).start()
        else:
            if self._stop_cleanup_running:
                self.status_lbl.config(text="正在停止中：请稍候，浏览器清理进行中...")
            else:
                self.status_lbl.config(text="已在停止中：任务终止信号已发送")

    def _on_app_close(self):
        """窗口关闭时确保回收全部浏览器与 driver。"""
        if self._app_closing:
            try:
                self.destroy()
            except Exception:
                pass
            try:
                os._exit(0)
            except Exception:
                pass
            return
        self._app_closing = True
        def _hard_exit_after_delay():
            # 兜底：避免线程池/driver 残留导致主进程不退出
            try:
                time.sleep(0.6)
                os._exit(0)
            except Exception:
                pass
        threading.Thread(target=_hard_exit_after_delay, daemon=True).start()
        try:
            if self._auth_check_after_id is not None:
                self.after_cancel(self._auth_check_after_id)
                self._auth_check_after_id = None
        except Exception:
            pass
        try:
            self._stop_publish = True
            self._publish_session_id += 1
            self.progress.stop()
        except Exception:
            pass
        try:
            self._shutdown_all_browsers(reason="软件退出")
        except Exception:
            pass
        try:
            self._kill_edge_processes_on_exit()
        except Exception:
            pass
        try:
            self.destroy()
        except Exception:
            pass
        try:
            os._exit(0)
        except Exception:
            pass

    def _on_root_destroy(self, event):
        """根窗口被销毁时的最终兜底退出。"""
        try:
            if event is None or event.widget is not self:
                return
        except Exception:
            return
        if self._app_closing:
            return
        self._app_closing = True
        try:
            self._shutdown_all_browsers(reason="根窗口销毁")
        except Exception:
            pass
        try:
            self._kill_edge_processes_on_exit()
        except Exception:
            pass
        def _force_exit():
            try:
                time.sleep(0.2)
                os._exit(0)
            except Exception:
                pass
        threading.Thread(target=_force_exit, daemon=True).start()




    def _publish_direct(self, product_info):
        """详情页“发布此商品”与“开始上品”保持完全同流程（单品模式）。"""
        if self._license_locked:
            self._show_auth_lock_popup()
            return
        if product_info is None or not product_info.get('image_url'):
            messagebox.showwarning('提示', '商品信息不完整，请重新抓取')
            return
        target_asin = str(product_info.get('asin') or '').strip()
        if not target_asin:
            messagebox.showwarning('提示', '未获取到 ASIN，无法发布')
            return
        # 强制详情页走单品发布：仅勾选当前 ASIN，再调用统一入口 _open_publish_page
        self.current_asin = target_asin
        try:
            for a, v in self.asin_vars.items():
                if hasattr(v, "set"):
                    v.set(a == target_asin)
            self._update_selection_count()
        except Exception:
            pass
        self._open_publish_page()

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

if __name__ == '__main__':
    app = SheinApp()
    try:
        app.mainloop()
    except KeyboardInterrupt:
        pass
    finally:
        try:
            if hasattr(app, "_on_app_close"):
                app._on_app_close()
            else:
                app.destroy()
        except Exception:
            pass









