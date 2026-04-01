# -*- coding: utf-8 -*-
"""SHEIN 上品自动化模块。"""
import os
import re
import time
import random
import tempfile
import requests
from shein_login import SheinLoginManager
from shein_asin import HEADERS_POOL
try:
    from selenium.webdriver.common.by import By
    from selenium.webdriver.common.keys import Keys
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except ImportError:
    By = None
    Keys = None
    WebDriverWait = None
    EC = None

class SheinPublisher:
    HOME_URL    = "https://sso.geiwohuo.com/#/home"
    LOGIN_URL   = "https://sso.geiwohuo.com/#/login"
    PUBLISH_URL = "https://sso.geiwohuo.com/#/spmc/commodities-category/followsales-pro/list?externalSystem=spmp"
    DEBUG_PORT  = 9222  # Chrome 远程调试端口

    def __init__(self, log_cb=None):
        self.driver = None
        self.wait   = None
        self.log    = log_cb or print
        self.login_manager = SheinLoginManager(log_cb=self.log)
        self._stop_publish = False
        # 记录主规格实际成功写入顺序，供后续按行上传图片对齐
        self._last_main_spec_filled_values = []

    def _ensure_not_stopped(self):
        if self._stop_publish:
            raise RuntimeError("用户已停止上品")

    def _connect_chrome_only(self):
        self.login_manager.driver = self.driver
        self.login_manager.wait = self.wait
        result = self.login_manager._connect_chrome_only()
        self.driver = self.login_manager.driver
        self.wait = self.login_manager.wait
        return result

    def start_chrome_browser(self):
        self.login_manager.driver = self.driver
        self.login_manager.wait = self.wait
        self.login_manager.start_chrome_browser()
        self.driver = self.login_manager.driver
        self.wait = self.login_manager.wait

    def try_connect_existing(self):
        self.login_manager.driver = self.driver
        self.login_manager.wait = self.wait
        ok = self.login_manager.try_connect_existing()
        self.driver = self.login_manager.driver
        self.wait = self.login_manager.wait
        return ok

    def start_browser(self):
        self.login_manager.driver = self.driver
        self.login_manager.wait = self.wait
        self.login_manager.start_browser()
        self.driver = self.login_manager.driver
        self.wait = self.login_manager.wait

    def open_login(self):
        self.login_manager.driver = self.driver
        self.login_manager.wait = self.wait
        self.login_manager.open_login()
        self.driver = self.login_manager.driver
        self.wait = self.login_manager.wait

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
        self.login_manager.driver = self.driver
        return self.login_manager.is_alive()

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
        self.login_manager.driver = self.driver
        self.login_manager.wait = self.wait
        ok = self.login_manager.ensure_alive()
        self.driver = self.login_manager.driver
        self.wait = self.login_manager.wait
        return ok

    def is_logged_in(self):
        self.login_manager.driver = self.driver
        return self.login_manager.is_logged_in()

    def wait_for_login(self, timeout=60):
        self.login_manager.driver = self.driver
        ok = self.login_manager.wait_for_login(timeout=timeout)
        self.driver = self.login_manager.driver
        self.wait = self.login_manager.wait
        return ok
    def click_identify_image_button(self):
        """点击'识图发品'按钮。"""
        try:
            self._ensure_not_stopped()
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
            self._ensure_not_stopped()
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
            # 识图发品阶段不做裁剪，等待系统识别类目
            wait_secs = 4
            self.log("[DEBUG] 图片已上传，等待系统识别类目 {} 秒...".format(wait_secs))
            time.sleep(wait_secs)
            # 等待上传完成
            self.log("[OK] 图片已上传: {}".format(os.path.basename(image_path)))
            return True
        except Exception as e:
            self.log("[ERROR] 上传失败: {}".format(str(e)[:60]))
            return False

    def select_first_category(self):
        """选择第一个推荐类目。"""
        try:
            self._ensure_not_stopped()
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
            self._ensure_not_stopped()
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
            self._ensure_not_stopped()
            self.log("[DEBUG] 开始填写商品基础信息...")
            # 1. 填写商品标题(英语)
            self.log("[DEBUG] 填写商品标题(英语)...")
            time.sleep(3)  # 等待页面完全加载
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
            time.sleep(3)  # 等待页面完全加载
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
            # 5.6 填写类目属性（商品属性）
            self.log("[DEBUG] 填写类目属性...")
            try:
                self._fill_category_attributes(asin)
            except Exception as e:
                self.log("[DEBUG] 填写类目属性失败: {}".format(str(e)[:60]))
            # 6. 处理主规格（需在上传细节图前完成）
            self.log("[DEBUG] 处理主规格...")
            try:
                self._handle_main_spec_if_needed(product_info)
            except Exception as e:
                self.log("[DEBUG] 主规格处理步骤异常，继续后续流程: {}".format(str(e)[:60]))
            # 6.5 处理其他规格（如 size）
            self.log("[DEBUG] 处理其他规格...")
            try:
                self._handle_other_specs(product_info)
            except Exception as e:
                self.log("[DEBUG] 其他规格处理步骤异常，继续后续流程: {}".format(str(e)[:60]))
            # 7. 上传主规格图和细节图（非阻塞：失败不影响后续“规格及供应信息”流程）
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

    def _fill_category_attributes(self, asin):
        """填写类目属性中的必填项：产品型号=ASIN，其余必填空项选首个选项。"""
        driver = self.driver
        try:
            attr_title = WebDriverWait(driver, 8).until(
                EC.presence_of_element_located((By.XPATH,
                    "//div[contains(@class,'so-form-label')]//span[normalize-space(text())='商品属性']")))
            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", attr_title)
            time.sleep(0.5)
        except Exception:
            self.log("[DEBUG] 未明确定位到商品属性标题，继续尝试填写")
        if asin:
            model_filled = False
            model_xpaths = [
                "//span[contains(@class,'spmp_style__productAttrLabel') and contains(normalize-space(.),'产品型号')]/ancestor::div[contains(@class,'so-form-item')]//input",
                "//span[contains(@class,'spmp_style__productAttrLabel') and contains(normalize-space(.),'Product Model')]/ancestor::div[contains(@class,'so-form-item')]//input",
                "//div[contains(@class,'so-form-item') and .//span[contains(normalize-space(.),'产品型号')]]//input",
            ]
            for xp in model_xpaths:
                try:
                    inp = WebDriverWait(driver, 3).until(
                        EC.presence_of_element_located((By.XPATH, xp)))
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inp)
                    self._js_input(inp, asin)
                    self.log("[OK] 产品型号已填写: {}".format(asin))
                    model_filled = True
                    time.sleep(0.3)
                    break
                except Exception:
                    pass
            if not model_filled:
                self.log("[DEBUG] 未找到产品型号输入框")
        # 展开全部属性（让折叠区的必填项也参与自动填写）
        try:
            expand_xpaths = [
                "//*[contains(@class,'spmp_style__collapsed') and contains(normalize-space(.),'展开所有属性')]",
                "//*[contains(normalize-space(.),'展开所有属性')]",
            ]
            expanded = False
            for xp in expand_xpaths:
                for el in driver.find_elements(By.XPATH, xp):
                    try:
                        if not el.is_displayed():
                            continue
                        text = (el.text or "").strip()
                        if "收起" in text:
                            expanded = True
                            break
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", el)
                        time.sleep(0.2)
                        try:
                            el.click()
                        except Exception:
                            driver.execute_script("arguments[0].click();", el)
                        self.log("[OK] 已展开所有属性")
                        expanded = True
                        time.sleep(0.6)
                        break
                    except Exception:
                        pass
                if expanded:
                    break
        except Exception:
            pass
        # 展开后做一次滚动触发懒加载，再回到属性区域
        try:
            for _ in range(4):
                driver.execute_script("window.scrollBy(0, 700);")
                time.sleep(0.25)
            driver.execute_script("window.scrollBy(0, -2800);")
            time.sleep(0.35)
            for _ in range(2):
                driver.execute_script("window.scrollBy(0, 700);")
                time.sleep(0.2)
        except Exception:
            pass
        required_items = driver.find_elements(By.XPATH,
            "//div[contains(@class,'so-form-item') and contains(@class,'so-form-required') and contains(@class,'spmp_style__productAttrItem')]")
        if not required_items:
            self.log("[DEBUG] 未找到必填商品属性项")
            return
        auto_filled_count = 0
        for item in required_items:
            try:
                if not item.is_displayed():
                    continue
                label = ""
                try:
                    label = item.find_element(By.XPATH,
                        ".//span[contains(@class,'spmp_style__productAttrLabel')]"
                    ).text.strip()
                except Exception:
                    pass
                if "产品型号" in label or "Product Model" in label:
                    continue
                has_value = False
                try:
                    inputs = item.find_elements(By.XPATH, ".//input[@type='text' or not(@type)]")
                    for inp in inputs:
                        val = (inp.get_attribute("value") or "").strip()
                        if val:
                            has_value = True
                            break
                except Exception:
                    pass
                if not has_value:
                    try:
                        selected_tags = item.find_elements(By.XPATH,
                            ".//*[contains(@class,'so-select-item') and not(contains(@class,'compressed'))]")
                        selected_text = "".join([(t.text or "").strip() for t in selected_tags]).strip()
                        if selected_text:
                            has_value = True
                    except Exception:
                        pass
                if has_value:
                    continue
                select_inner = None
                for sx in [
                    ".//div[contains(@class,'so-select-inner')]",
                    ".//div[contains(@class,'so-select-result')]",
                    ".//a[contains(@class,'so-select-caret')]",
                ]:
                    try:
                        cand = item.find_element(By.XPATH, sx)
                        if cand.is_displayed():
                            select_inner = cand
                            break
                    except Exception:
                        pass
                if not select_inner:
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", select_inner)
                time.sleep(0.2)
                try:
                    select_inner.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", select_inner)
                time.sleep(0.4)
                preferred_option = None
                if "电源" in label or "Power Supply" in label:
                    preferred_xpaths = [
                        "//*[contains(@class,'so-select-option') and normalize-space(.)='No']",
                        "//*[contains(@class,'so-option') and normalize-space(.)='No']",
                        "//li[normalize-space(.)='No']",
                    ]
                    for px in preferred_xpaths:
                        try:
                            cand = WebDriverWait(driver, 2).until(
                                EC.presence_of_element_located((By.XPATH, px)))
                            if cand.is_displayed():
                                preferred_option = cand
                                break
                        except Exception:
                            pass
                first_option = None
                option_xpaths = [
                    "(//*[contains(@class,'so-select-option') and not(contains(@class,'disabled')) and normalize-space(.)!=''])[1]",
                    "(//*[contains(@class,'so-option') and not(contains(@class,'disabled')) and normalize-space(.)!=''])[1]",
                    "(//li[not(contains(@class,'disabled')) and normalize-space(.)!=''])[1]",
                ]
                for ox in option_xpaths:
                    try:
                        opt = WebDriverWait(driver, 2).until(
                            EC.presence_of_element_located((By.XPATH, ox)))
                        if opt.is_displayed():
                            first_option = opt
                            break
                    except Exception:
                        pass
                target_option = preferred_option if preferred_option else first_option
                if target_option:
                    try:
                        target_option.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", target_option)
                    auto_filled_count += 1
                    if preferred_option:
                        self.log("[OK] 必填属性已选择 No: {}".format(label or "(未识别标签)"))
                    else:
                        self.log("[OK] 必填属性已默认选择首项: {}".format(label or "(未识别标签)"))
                    time.sleep(0.25)
                else:
                    try:
                        driver.execute_script("document.body.click();")
                    except Exception:
                        pass
            except Exception:
                continue
        self.log("[OK] 类目属性处理完成，自动补全 {} 项".format(auto_filled_count))

    def fill_spec_and_supply_info(self, product_info):
        """填写'规格及供应信息'板块（价格、SKU、库存等）。"""
        try:
            self._ensure_not_stopped()
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
            # 步骤1.5: 向“批量填写”区域的「价格」输入框填写价格，并点击「批量填写」按鈕
            if price_num:
                try:
                    _bp_inp = driver.find_element(By.CSS_SELECTOR, ".supplierPriceSupplyFillClass_0 input")
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", _bp_inp)
                    self._js_input(_bp_inp, price_num)
                    self.log("[OK] 批量填写价格已输入: {}".format(price_num))
                    time.sleep(0.3)
                    # 点击「件数类型」下拉并选择「单品」
                    try:
                        _qty_type_sel = driver.find_element(
                            By.XPATH,
                            "//div[contains(@class,'supplierPriceSupplyFillClass_0')]"
                            "/following-sibling::div[contains(@class,'spmp_style__flexColumnCell')]"
                            "//div[contains(@class,'so-select-inner')]"
                        )
                        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", _qty_type_sel)
                        time.sleep(0.2)
                        driver.execute_script("arguments[0].click();", _qty_type_sel)
                        self.log("[DEBUG] 已点开件数类型下拉")
                        time.sleep(0.5)
                        # 在下拉列表中找「单品」选项
                        _found = False
                        for _opt in driver.find_elements(By.XPATH,
                                "//*[contains(@class,'so-select-option') or contains(@class,'so-option')]"
                                "[normalize-space(text())='单品']"):
                            if _opt.is_displayed():
                                driver.execute_script("arguments[0].click();", _opt)
                                self.log("[OK] 已选择件数类型:单品")
                                _found = True
                                time.sleep(0.3)
                                break
                        if not _found:
                            # 备用：找包含「单品」文字的任意可见元素
                            for _li in driver.find_elements(By.XPATH,
                                    "//*[normalize-space(text())='单品']"):
                                if _li.is_displayed():
                                    driver.execute_script("arguments[0].click();", _li)
                                    self.log("[OK] 已选择件数类型:单品(备用)")
                                    time.sleep(0.3)
                                    break
                    except Exception as _qt_e:
                        self.log("[WARN] 件数类型选择失败: {}".format(str(_qt_e)[:60]))
                    # 点击「批量填写」按鈕
                    _batch_btns = driver.find_elements(By.XPATH,
                        "//button[.//span[normalize-space(text())='批量填写']]")
                    for _bbtn in _batch_btns:
                        try:
                            if _bbtn.is_displayed() and _bbtn.is_enabled():
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", _bbtn)
                                time.sleep(0.2)
                                driver.execute_script("arguments[0].click();", _bbtn)
                                self.log("[OK] 已点击批量填写按鈕")
                                time.sleep(0.5)
                                break
                        except Exception:
                            continue
                except Exception as _bp_e:
                    self.log("[WARN] 批量填写价格失败: {}".format(str(_bp_e)[:60]))
            # 步骤2.5: 通过批量填写区域填写含包装重量(g)
            try:
                self.log("[DEBUG] 批量填写含包装重量...")
                batch_w_inp = None
                for sel in [
                    ".weightSupplyFillClass_0 input",
                    ".packageCheckBatchFillError .weightSupplyFillClass_0 input",
                    ".packageCheckBatchFillError input[placeholder*='\u91cd\u91cf']",
                ]:
                    try:
                        el = driver.find_element(By.CSS_SELECTOR, sel)
                        if el.is_displayed():
                            batch_w_inp = el
                            break
                    except Exception:
                        continue
                if batch_w_inp is None:
                    raise RuntimeError("batch weight input not found")
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", batch_w_inp)
                time.sleep(0.3)
                driver.execute_script(
                    "(function(el,val){"
                    "var s=Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype,'value').set;"
                    "s.call(el,val);"
                    "el.dispatchEvent(new Event('input',{bubbles:true}));"
                    "el.dispatchEvent(new Event('change',{bubbles:true}));"
                    "el.dispatchEvent(new Event('blur',{bubbles:true}));"
                    "})(arguments[0],arguments[1]);",
                    batch_w_inp, "100")
                self.log("[OK] 批量填写重量输入框已写入100")
                time.sleep(0.3)
                batch_fill_btn = None
                try:
                    container = batch_w_inp.find_element(By.XPATH,
                        "ancestor::div[contains(@class,'packageCheckBatchFillError')]")
                    for btn in container.find_elements(By.CSS_SELECTOR,
                            "button.so-button-primary"):
                        try:
                            txt = (btn.text or "").strip()
                            if "\u6279\u91cf\u586b\u5199" in txt:
                                batch_fill_btn = btn
                                break
                        except Exception:
                            continue
                except Exception:
                    pass
                if batch_fill_btn is None:
                    for btn in driver.find_elements(By.XPATH,
                            "//div[contains(@class,'packageCheckBatchFillError')]"
                            "//button[.//span[contains(text(),'\u6279\u91cf\u586b\u5199')]]"):
                        try:
                            if btn.is_displayed():
                                batch_fill_btn = btn
                                break
                        except Exception:
                            continue
                if batch_fill_btn is not None:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", batch_fill_btn)
                    time.sleep(0.2)
                    try:
                        batch_fill_btn.click()
                    except Exception:
                        driver.execute_script("arguments[0].click();", batch_fill_btn)
                    self.log("[OK] \u5df2\u70b9\u51fb\u5305\u88c5\u4fe1\u606f\u300c\u6279\u91cf\u586b\u5199\u300d\u6309\u94ae\uff0c\u6240\u6709SKU\u542b\u5305\u88c5\u91cd\u91cf\u5df2\u8bbe\u4e3a100g")
                    time.sleep(0.5)
                else:
                    self.log("[WARN] \u672a\u627e\u5230\u5305\u88c5\u4fe1\u606f\u300c\u6279\u91cf\u586b\u5199\u300d\u6309\u94ae\uff0c\u56de\u9000\u5355\u884c\u586b\u5199")
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
                    self.log("[OK] \u542b\u5305\u88c5\u91cd\u91cf\u5df2\u586b\u5199100g\uff08\u5355\u884c\uff09")
                    time.sleep(0.3)
            except Exception as _we:
                self.log("[DEBUG] \u542b\u5305\u88c5\u91cd\u91cf\u586b\u5199\u5931\u8d25: {}".format(str(_we)[:60]))
            # 步骤2: 点击"编辑库存"，批量填写库存200，确认
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
                    # 在批量填写区域的库存输入框填入200
                    batch_filled = False
                    # 在批量填写区域的库存输入框填入200
                    batch_filled = False
                    try:
                        # 优先找弈窗顶部的批量操作行（通常在表格上方）
                        batch_inps = driver.find_elements(By.XPATH,
                            "//div[contains(@class,'so-modal')]//div[contains(@class,'batch') or contains(@class,'Batch') or contains(@class,'bulkFill') or contains(@class,'batchFill') or contains(@class,'header')]//input[@type='text']")
                        if not batch_inps:
                            # 备用：找弈窗内所有 input，但排除表格数据行（通常在 tr 内）
                            batch_inps = driver.find_elements(By.XPATH,
                                "//div[contains(@class,'so-modal')]//input[@type='text'][not(ancestor::tr)]")
                        self.log("[DEBUG] 批量填写 input 数量: {}".format(len(batch_inps)))
                        if batch_inps:
                            batch_inp = batch_inps[0]
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", batch_inp)
                            time.sleep(0.2)
                            # 先清空再填入
                            driver.execute_script("""
                                var inp = arguments[0];
                                var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                setter.call(inp, '');
                                inp.dispatchEvent(new Event('input', {bubbles:true}));
                                inp.dispatchEvent(new Event('change', {bubbles:true}));
                            """, batch_inp)
                            time.sleep(0.2)
                            # 再填入 200
                            driver.execute_script("""
                                var inp = arguments[0];
                                var setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                                setter.call(inp, '200');
                                inp.dispatchEvent(new Event('input', {bubbles:true}));
                                inp.dispatchEvent(new Event('change', {bubbles:true}));
                            """, batch_inp)
                            time.sleep(0.3)
                            val = driver.execute_script("return arguments[0].value;", batch_inp)
                            self.log("[DEBUG] 批量填写 input 当前値: {}".format(val))
                            batch_filled = True
                    except Exception as e:
                        self.log("[DEBUG] 批量填写 input 定位失败: {}".format(str(e)[:60]))
                    # 点击「批量填写」按鈕
                    if batch_filled:
                        try:
                            batch_btn = None
                            # 精确定位：弈窗内含「批量填写」文本的按鈕
                            for _b in driver.find_elements(By.XPATH,
                                    "//div[contains(@class,'so-modal')]//button"):
                                _text = (_b.text or '').strip()
                                if '批量填写' in _text or _text == '批量填写':
                                    if _b.is_displayed():
                                        batch_btn = _b
                                        break
                            if batch_btn:
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", batch_btn)
                                time.sleep(0.2)
                                driver.execute_script("arguments[0].click();", batch_btn)
                                self.log("[OK] 已点击「批量填写」")
                                time.sleep(1)
                            else:
                                self.log("[WARN] 未找到「批量填写」按鈕，尝试备用 XPath")
                                # 备用 XPath
                                try:
                                    batch_btn2 = driver.find_element(By.XPATH,
                                        "//div[contains(@class,'so-modal')]//button[contains(., '批量填写')]")
                                    driver.execute_script("arguments[0].click();", batch_btn2)
                                    self.log("[OK] 已点击「批量填写」(备用)")
                                    time.sleep(1)
                                except Exception:
                                    self.log("[WARN] 备用 XPath 也未找到「批量填写」按鈕")
                        except Exception as e:
                            self.log("[WARN] 点击批量填写失败: {}".format(str(e)[:60]))
                    else:
                        self.log("[WARN] 批量填写 input 未找到，跳过批量填写")
                    time.sleep(0.5)
                    # 点击确认按鈕关闭对话框
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

    def _handle_main_spec_if_needed(self, product_info=None):
        """
        处理主规格：
        1) 若检测到“无主规格”则切换到“有主规格”；
        2) 第一个下拉框优先按 ASIN 爬取的「分类依据」匹配选项（仅1个选项时直接选）；
        3) 第二个下拉框选择第一个有效选项。
        """
        driver = self.driver
        try:
            self.log("[DEBUG] 检查主规格是否需要填写...")
            # 1) 先处理“有无主规格”开关（必须在上传细节图前完成）
            # 说明：这里不依赖 main_spec_box，避免因为未定位到主规格区而提前 return
            try:
                switch_item = None
                for item in driver.find_elements(By.XPATH, "//div[contains(@class,'so-form-item')]"):
                    try:
                        if not item.is_displayed():
                            continue
                        label_el = item.find_element(By.XPATH, ".//div[contains(@class,'so-form-label')]")
                        if "有无主规格" in (label_el.text or ""):
                            switch_item = item
                            break
                    except Exception:
                        continue
                if switch_item is None:
                    self.log("[WARN] 未找到'有无主规格'开关区域，继续后续流程")
                else:
                    switch_label = None
                    try:
                        switch_label = switch_item.find_element(
                            By.XPATH, ".//label[contains(@class,'so-checkinput-switch')]"
                        )
                    except Exception:
                        pass
                    # 读取当前状态：优先看 children 文案
                    state_text = ""
                    try:
                        state_text = (switch_item.find_element(
                            By.XPATH, ".//span[contains(@class,'so-checkinput-switch-children')]"
                        ).text or "").strip()
                    except Exception:
                        try:
                            state_text = (switch_label.text or "").strip() if switch_label is not None else ""
                        except Exception:
                            state_text = ""
                    if "无主规格" in state_text:
                        self.log("[INFO] 检测到'有无主规格'当前为'无主规格'，准备点击切换")
                        try:
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", switch_item)
                            time.sleep(0.3)
                        except Exception:
                            pass
                        def _click_main_spec_switch_once():
                            targets = []
                            # 优先点击你给出的 LTR 滑动指示器
                            for xp in [
                                ".//span[contains(@class,'so-checkinput-switch-indicator-ltr')]",
                                ".//span[contains(@class,'so-checkinput-switch-indicator')]",
                                ".//i[contains(@class,'so-checkinput-indicator') and contains(@class,'so-checkinput-switch')]",
                                ".//label[contains(@class,'so-checkinput-switch')]",
                            ]:
                                try:
                                    el = switch_item.find_element(By.XPATH, xp)
                                    targets.append(el)
                                except Exception:
                                    pass
                            clicked = False
                            for t in targets:
                                try:
                                    t.click()
                                    clicked = True
                                    break
                                except Exception:
                                    try:
                                        driver.execute_script("arguments[0].click();", t)
                                        clicked = True
                                        break
                                    except Exception:
                                        pass
                            return clicked
                        def _confirm_switch_modal_if_needed():
                            # 最多等待 5 秒，期间如果出现确认弹窗则点击“确认”
                            for _ in range(10):
                                try:
                                    confirm_btns = driver.find_elements(
                                        By.XPATH,
                                        "//div[contains(@class,'so-modal-confirm')]"
                                        "//button[contains(@class,'so-button-primary')]"
                                        "[.//span[normalize-space(text())='确认']]"
                                    )
                                    if not confirm_btns:
                                        confirm_btns = driver.find_elements(
                                            By.XPATH,
                                            "//button[contains(@class,'so-button-primary')]"
                                            "[.//span[normalize-space(text())='确认']]"
                                        )
                                    for btn in confirm_btns:
                                        if btn.is_displayed():
                                            try:
                                                btn.click()
                                            except Exception:
                                                driver.execute_script("arguments[0].click();", btn)
                                            self.log("[OK] 已点击切换确认弹窗的'确认'按钮")
                                            time.sleep(0.5)
                                            return
                                except Exception:
                                    pass
                                time.sleep(0.5)
                        def _is_switched_to_main_spec():
                            try:
                                txt = (switch_item.find_element(
                                    By.XPATH, ".//span[contains(@class,'so-checkinput-switch-children')]"
                                ).text or "").strip()
                                if "有主规格" in txt:
                                    return True
                                if "无主规格" in txt:
                                    return False
                            except Exception:
                                pass
                            try:
                                cb = switch_item.find_element(By.XPATH, ".//input[@type='checkbox']")
                                return bool(cb.is_selected())
                            except Exception:
                                return False
                        # 尝试最多 2 次：点击 -> 处理弹窗 -> 校验状态
                        switched_ok = False
                        for idx in range(2):
                            clicked = _click_main_spec_switch_once()
                            if not clicked:
                                self.log("[WARN] 第{}次点击'有无主规格'开关失败".format(idx + 1))
                                continue
                            self.log("[INFO] 已点击'有无主规格'开关，检查确认弹窗...")
                            _confirm_switch_modal_if_needed()
                            time.sleep(0.6)
                            if _is_switched_to_main_spec():
                                switched_ok = True
                                break
                        if switched_ok:
                            self.log("[OK] '有无主规格'已切换为'有主规格'")
                        else:
                            self.log("[WARN] '有无主规格'切换未确认成功，继续后续流程")
                    else:
                        self.log("[DEBUG] '有无主规格'当前非'无主规格'，无需切换")
            except Exception as e:
                self.log("[WARN] 处理'有无主规格'开关异常: {}".format(str(e)[:80]))
            # 2) 再定位主规格区域
            main_spec_box = None
            for xp in [
                "//div[contains(@class,'so-form-item') and contains(@class,'main_spec') and .//span[normalize-space(text())='主规格']]",
                "//div[contains(@class,'main_spec') and .//*[contains(normalize-space(.),'主规格')]]",
            ]:
                try:
                    for box in driver.find_elements(By.XPATH, xp):
                        if box.is_displayed():
                            main_spec_box = box
                            break
                except Exception:
                    pass
                if main_spec_box is not None:
                    break
            if main_spec_box is None:
                self.log("[WARN] 未定位到主规格区域(main_spec)，跳过主规格下拉填写")
                return
            self.log("[DEBUG] 开始填写主规格")
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", main_spec_box)
                time.sleep(0.25)
            except Exception:
                pass
            # 3) 锁定提示文字下方内容区域
            spec_content = None
            try:
                for c in main_spec_box.find_elements(By.XPATH,
                    ".//div[contains(@class,'specContent') or contains(@class,'spmp_style__specContent')]"):
                    if c.is_displayed():
                        spec_content = c
                        break
            except Exception:
                pass
            if spec_content is None:
                spec_content = main_spec_box
            def _open_dropdown(inner):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inner)
                except Exception:
                    pass
                time.sleep(0.2)
                clicked = False
                for _ in range(2):
                    try:
                        inner.click()
                        clicked = True
                        break
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", inner)
                            clicked = True
                            break
                        except Exception:
                            pass
                if not clicked:
                    try:
                        caret = inner.find_element(By.XPATH, ".//a[contains(@class,'so-select-caret')]")
                        driver.execute_script("arguments[0].click();", caret)
                    except Exception:
                        pass
                time.sleep(0.3)
            def _collect_options(data_id):
                """获取当前下拉浮层中的可点击项，优先 label.so-select-option。"""
                if not data_id:
                    return []
                try:
                    # 仅拿当前 data-id 对应浮层（优先已显示）
                    boxes = driver.find_elements(By.XPATH,
                        "//div[contains(@class,'so-list') and @data-id='{0}' and "
                        "(contains(@class,'so-hidable-show') or not(contains(@style,'display: none')))]".format(data_id)
                    )
                    if not boxes:
                        boxes = driver.find_elements(By.XPATH,
                            "//div[contains(@class,'so-list') and @data-id='{0}']".format(data_id)
                        )
                    candidates = []
                    for box in boxes:
                        try:
                            cur = box.find_elements(By.XPATH,
                                ".//label[contains(@class,'so-select-option') or contains(@class,'so-checkinput')]"
                            )
                            if not cur:
                                cur = box.find_elements(By.XPATH,
                                    ".//*[contains(@class,'so-select-option') or contains(@class,'so-option')]"
                                )
                            candidates.extend(cur)
                        except Exception:
                            continue
                    opts = []
                    for el in candidates:
                        try:
                            if not el.is_displayed():
                                continue
                            txt = (el.text or "").strip().replace("\n", " ")
                            if not txt or txt in ("有主规格", "无主规格", "请选择", "请选择或自定义", "无数据") or len(txt) > 50:
                                continue
                            opts.append(el)
                        except Exception:
                            continue
                    return opts
                except Exception:
                    return []
            def _click_option(option_el):
                # 先点 option 本体，再兜底点内部 radio/input
                try:
                    driver.execute_script("arguments[0].click();", option_el)
                    return True
                except Exception:
                    pass
                try:
                    option_el.click()
                    return True
                except Exception:
                    pass
                try:
                    radio = option_el.find_element(By.XPATH, ".//input[@type='radio' or @type='checkbox']")
                    driver.execute_script("arguments[0].click();", radio)
                    return True
                except Exception:
                    return False
            def _normalize_key(txt):
                t = (txt or "").strip().lower()
                t = t.replace(" ", "")
                t = t.replace("colour", "color")
                t = t.replace("颜色", "color")
                t = t.replace("色彩", "color")
                t = t.replace("款式", "style")
                t = t.replace("型号", "model")
                t = t.replace("尺寸", "size")
                return t
            def _extract_target_spec_value(selected_attr_text):
                """从 ASIN 首个 SKU 提取用于主规格值输入的文本（如 brown）。"""
                if not isinstance(product_info, dict):
                    return ""
                sku_list = product_info.get("sku_list", []) or []
                if not sku_list:
                    return ""
                first_sku = sku_list[0] or {}
                selected_norm = _normalize_key(selected_attr_text)
                try:
                    raw_key = str(((first_sku.get("debug_variation") or {}).get("raw_dimension_key") or "")).strip()
                    if raw_key:
                        for part in re.split(r"[;,|]", raw_key):
                            seg = str(part or "").strip()
                            if not seg:
                                continue
                            key = ""
                            val = ""
                            if "=" in seg:
                                key, val = seg.split("=", 1)
                            elif ":" in seg:
                                key, val = seg.split(":", 1)
                            if key and val and _normalize_key(key) == selected_norm:
                                vv = str(val).strip()
                                if vv:
                                    return vv
                except Exception:
                    pass
                sku_attrs = str(first_sku.get("sku_attributes") or "").strip()
                if sku_attrs and sku_attrs != "默认规格":
                    first_part = sku_attrs.split("/")[0].strip()
                    if first_part:
                        return first_part
                return ""
            def _pick_first(inner, label):
                data_id = (inner.get_attribute("data-id") or "").strip()
                self.log("[DEBUG] 点击{}下拉框 data-id={}".format(label, data_id or "N/A"))
                options = []
                for i in range(5):
                    _open_dropdown(inner)
                    options = _collect_options(data_id)
                    if options:
                        if i > 0:
                            self.log("[DEBUG] {} 第{}次重试后拿到选项".format(label, i + 1))
                        break
                    time.sleep(0.35)
                if not options:
                    self.log("[WARN] {} 下拉未获取到可选项".format(label))
                    return None
                sample = []
                for o in options[:12]:
                    t = (o.text or "").strip().replace("\n", " ")
                    if t:
                        sample.append(t)
                self.log("[DEBUG] {} 可选项: {}".format(label, " | ".join(sample) if sample else "(空)"))
                target = options[0]
                picked = (target.text or "").strip().replace("\n", " ")
                if label == "主规格属性":
                    preferred_basis = []
                    if isinstance(product_info, dict):
                        for sku in product_info.get("sku_list", []) or []:
                            for b in sku.get("dimension_basis", []) or []:
                                bb = str(b or "").strip()
                                if bb and bb not in preferred_basis:
                                    preferred_basis.append(bb)
                    if preferred_basis:
                        norm_basis_set = set(_normalize_key(x) for x in preferred_basis if _normalize_key(x))
                        if len(options) == 1:
                            self.log("[DEBUG] 主规格属性仅 1 个选项，直接选择")
                        else:
                            matched = None
                            for opt in options:
                                opt_text = (opt.text or "").strip().replace("\n", " ")
                                if _normalize_key(opt_text) in norm_basis_set:
                                    matched = opt
                                    break
                            if matched is not None:
                                target = matched
                                picked = (matched.text or "").strip().replace("\n", " ")
                                self.log("[OK] 主规格属性已按分类依据匹配: {} (依据: {})".format(
                                    picked, " / ".join(preferred_basis)))
                            else:
                                self.log("[WARN] 主规格属性未匹配到分类依据({})，回退首项".format(
                                    " / ".join(preferred_basis)))
                    else:
                        self.log("[DEBUG] 未获取到 ASIN 分类依据，主规格属性回退首项")
                ok = _click_option(target)
                if not ok:
                    self.log("[WARN] {} 首项点击失败".format(label))
                    return None
                time.sleep(0.35)
                self.log("[OK] {} 已选择首项: {}".format(label, picked or "(空文本)"))
                return picked
            def _type_and_pick_first(inner, label, typed_text):
                seed_text = (typed_text or "").strip()
                if not seed_text:
                    self.log("[WARN] {} 未拿到ASIN规格关键字，无法执行输入匹配".format(label))
                    return None
                data_id = (inner.get_attribute("data-id") or "").strip()
                def _build_keywords(seed):
                    kws = []
                    def _add(x):
                        t = (x or "").strip()
                        if t and t not in kws:
                            kws.append(t)
                    _add(seed)
                    txt = seed.replace("/", " ").replace("_", " ").replace("-", " ")
                    parts = [p.strip() for p in txt.split() if p.strip()]
                    # ?????????????? Double Brown -> Brown?
                    for p in reversed(parts):
                        if len(p) >= 2:
                            _add(p)
                    # ???????
                    for p in parts:
                        if len(p) >= 2:
                            _add(p)
                    return kws
                keywords = _build_keywords(seed_text)
                self.log("[DEBUG] {} 候选输入词: {}".format(label, " | ".join(keywords)))
                def _dismiss_error_modal_if_any(wait_rounds=6):
                    for _ in range(wait_rounds):
                        try:
                            modal = driver.find_elements(By.XPATH,
                                "//div[contains(@class,'soui-modal-panel') and .//*[contains(normalize-space(.),'错误信息')]]"
                            )
                            know_btn = driver.find_elements(By.XPATH,
                                "//div[contains(@class,'soui-modal-panel')]//button[.//span[normalize-space(text())='我知道了'] or normalize-space(text())='我知道了']"
                            )
                            if modal and know_btn:
                                clicked = False
                                for b in know_btn:
                                    try:
                                        if b.is_displayed():
                                            try:
                                                b.click()
                                            except Exception:
                                                driver.execute_script("arguments[0].click();", b)
                                            clicked = True
                                            break
                                    except Exception:
                                        continue
                                if clicked:
                                    time.sleep(0.5)
                                    self.log("[WARN] {} 触发错误弹窗，已点击'我知道了'".format(label))
                                    return True
                        except Exception:
                            pass
                        time.sleep(0.25)
                    return False
                def _attempt_once(one_kw, skip_open=False):
                    self.log("[DEBUG] {} 尝试输入: {}".format(label, one_kw))
                    if not skip_open:
                        _open_dropdown(inner)
                    else:
                        # 错误弹窗后不重新点击，确保下拉框已开着
                        time.sleep(0.1)
                    time.sleep(0.25)
                    input_el = None
                    candidates = []
                    try:
                        candidates.extend(inner.find_elements(By.XPATH, ".//input[not(@type='hidden') and not(@disabled)]"))
                    except Exception:
                        pass
                    try:
                        if data_id:
                            candidates.extend(driver.find_elements(By.XPATH,
                                "//div[contains(@class,'so-list') and @data-id='{}']//input[not(@type='hidden') and not(@disabled)]".format(data_id)
                            ))
                    except Exception:
                        pass
                    try:
                        candidates.extend(driver.find_elements(By.XPATH,
                            "//input[not(@type='hidden') and not(@disabled) and "
                            "(contains(@class,'so-select') or contains(@class,'search') or @type='search' or @role='combobox')]"
                        ))
                    except Exception:
                        pass
                    for ip in candidates:
                        try:
                            if ip.is_displayed() and ip.is_enabled():
                                input_el = ip
                                break
                        except Exception:
                            continue
                    typed_ok = False
                    if input_el is not None:
                        try:
                            driver.execute_script(
                                "var el=arguments[0],v=arguments[1];"
                                "el.focus();"
                                "el.value='';"
                                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                                "el.value=v;"
                                "el.dispatchEvent(new Event('input',{bubbles:true}));"
                                "el.dispatchEvent(new Event('change',{bubbles:true}));",
                                input_el, one_kw
                            )
                            typed_ok = True
                        except Exception:
                            pass
                        if not typed_ok:
                            try:
                                input_el.click()
                            except Exception:
                                pass
                            try:
                                input_el.clear()
                            except Exception:
                                pass
                            try:
                                input_el.send_keys(one_kw)
                                typed_ok = True
                            except Exception:
                                pass
                    if not typed_ok:
                        try:
                            ae = driver.switch_to.active_element
                            if ae is not None:
                                ae.send_keys(one_kw)
                                typed_ok = True
                        except Exception:
                            pass
                    if not typed_ok:
                        try:
                            inner.click()
                        except Exception:
                            pass
                        try:
                            inner.send_keys(one_kw)
                            typed_ok = True
                        except Exception:
                            pass
                    if not typed_ok:
                        self.log("[WARN] {} 输入失败: {}".format(label, one_kw))
                        return None, False
                    # [PATCHED] wait loop below
                    options = []
                    for _wr in range(6):
                        time.sleep(0.5)
                        options = _collect_options(data_id)
                        if options:
                            self.log("[DEBUG] {} found {} opts round {}".format(label, len(options), _wr+1))
                            break
                    if not options:
                        try:
                            options = [el for el in driver.find_elements(By.XPATH,
                                "//label[contains(@class,'so-select-option') or contains(@class,'so-checkinput')]"
                                " | //*[contains(@class,'so-select-option') or contains(@class,'so-option')]"
                            ) if el.is_displayed() and (el.text or '').strip() not in ('', '无数据', '请选择')]
                        except Exception:
                            options = []
                    target = None
                    low = one_kw.lower().strip()
                    if options and low:
                        for op in options:
                            try:
                                txt = (op.text or "").strip().lower()
                                if low == txt:
                                    target = op
                                    break
                            except Exception:
                                continue
                    if target is None and options and low:
                        # Pass 2a: extract English-only part from option, exact match
                        # e.g. "white" matches "白色White" (en="White") but NOT
                        #      "黑白色Black and White" (en="Black and White")
                        def _extract_en(s):
                            return re.sub(r'[^\x00-\x7f]', '', s).strip().lower()
                        for op in options:
                            try:
                                txt = (op.text or "").strip()
                                en = _extract_en(txt)
                                if en and re.sub(r'[\s\-_]+', '', en) == re.sub(r'[\s\-_]+', '', low):
                                    target = op
                                    break
                            except Exception:
                                continue
                    if target is None and options and low:
                        # Pass 2b: word-boundary match
                        _word_pat = re.compile(r'(?<![a-z])' + re.escape(low) + r'(?![a-z])', re.IGNORECASE)
                        for op in options:
                            try:
                                txt = (op.text or "").strip()
                                if _word_pat.search(txt):
                                    target = op
                                    break
                            except Exception:
                                continue
                    if target is None and options and low:
                        # Pass 2c: fallback substring containment
                        for op in options:
                            try:
                                txt = (op.text or "").strip().lower()
                                if low in txt or txt in low:
                                    target = op
                                    break
                            except Exception:
                                continue
                    if target is None and options:
                        # 已取消默认首项回退，避免顺序错位
                        # 已取消默认首项回退，避免顺序错位
                        target = None
                    if target is None:
                        # 无数据时：点击屏幕任意位置确认，然后检测"提示"弹窗
                        # 先尝试自定义值确认（按 Enter），避免无下拉选项时丢 SKU
                        custom_ok = False
                        try:
                            from selenium.webdriver.common.keys import Keys as _Keys
                            if input_el is not None and input_el.is_enabled():
                                try:
                                    input_el.send_keys(_Keys.RETURN)
                                    custom_ok = True
                                except Exception:
                                    pass
                            if not custom_ok:
                                try:
                                    ae = driver.switch_to.active_element
                                    if ae is not None:
                                        ae.send_keys(_Keys.RETURN)
                                        custom_ok = True
                                except Exception:
                                    pass
                            if custom_ok:
                                try:
                                    clicked_blank = driver.execute_script(
                                        "var c=document.getElementById('spec_info');"
                                        "if(c){var h=c.querySelector('[class*=card_header]');"
                                        "if(h){h.click();return true;}c.click();return true;}return false;"
                                    )
                                    if not clicked_blank:
                                        driver.execute_script("document.body.click();")
                                except Exception:
                                    pass
                                time.sleep(0.8)
                                selected_txt = ""
                                try:
                                    selected_txt = (inner.find_element(By.XPATH,
                                        ".//span[contains(@class,'so-select-input') or contains(@class,'renderItemEllipsis')]")
                                        .text or "").strip()
                                except Exception:
                                    pass
                                if selected_txt and (low in selected_txt.lower() or selected_txt.lower() in low):
                                    self.log("[OK] {} 自定义值已确认: {}".format(label, selected_txt))
                                    return selected_txt, False
                        except Exception:
                            pass
                        self.log("[DEBUG] {} 输入'{}' 后无数据，点击空白处等待提示弹窗".format(label, one_kw))
                        try:
                            # 通过 id=spec_info 容器头部点击触发失焦
                            clicked_blank = False
                            try:
                                # DEBUG: 先打印 spec_info 是否存在
                                _dbg_exists = driver.execute_script("return !!document.getElementById('spec_info');")
                                self.log("[DEBUG] {} spec_info元素存在={}".format(label, _dbg_exists))
                                if _dbg_exists:
                                    _dbg_hdr = driver.execute_script(
                                        "var c=document.getElementById('spec_info');"
                                        "var h=c.querySelector('[class*=card_header]');"
                                        "return h ? h.className : 'NO_HEADER';"
                                    )
                                    self.log("[DEBUG] {} card_header class={}".format(label, _dbg_hdr))
                                clicked_blank = driver.execute_script(
                                    "var c = document.getElementById('spec_info');"
                                    "if (c) {"
                                    "  var h = c.querySelector('[class*=card_header]');"
                                    "  if (h) { h.click(); return true; }"
                                    "  c.click(); return true;"
                                    "} return false;"
                                )
                                self.log("[DEBUG] {} JS点击spec_info结果={}".format(label, clicked_blank))
                            except Exception as _e:
                                self.log("[DEBUG] {} JS点击spec_info异常: {}".format(label, _e))
                            if not clicked_blank:
                                # 兑底: 点击页面坐标(10,10)
                                try:
                                    from selenium.webdriver.common.action_chains import ActionChains as _AC
                                    _AC(driver).move_by_offset(10, 10).click().perform()
                                    self.log("[DEBUG] {} 兜底点击坐标(10,10)".format(label))
                                except Exception as _e2:
                                    self.log("[DEBUG] {} 兜底点击异常: {}".format(label, _e2))
                            time.sleep(0.8)
                            # DEBUG: 点击后检查下拉框是否还开着
                            try:
                                _dbg_open = driver.execute_script(
                                    "var el=document.querySelector('.so-select-box-list');"
                                    "return el ? el.style.display : 'NOT_FOUND';"
                                )
                                self.log("[DEBUG] {} 0.8s后下拉display={}".format(label, _dbg_open))
                            except Exception:
                                pass
                        except Exception as _ex:
                            self.log("[DEBUG] {} 外层异常: {}".format(label, _ex))
                        hint_target = None
                        try:
                            hint_modal_xpaths = [
                                "//div[contains(@class,'soui-modal-panel')]",
                                "//div[contains(@class,'so-modal-panel')]",
                                "//div[contains(@class,'soui-modal') and not(contains(@class,'soui-modal-panel'))]",
                            ]
                            modal_found = False
                            for xp in hint_modal_xpaths:
                                for m in driver.find_elements(By.XPATH, xp):
                                    if m.is_displayed():
                                        modal_found = True
                                        self.log("[DEBUG] {} 检测到'提示'弹窗，重新收集选项".format(label))
                                        break
                                if modal_found:
                                    break
                            if modal_found:
                                # 检测到"提示"弹窗：说明 SHEIN 已通过弹窗处理当前词
                                # 不在当前框再填任何选项，等待弹窗消失后返回特殊标记
                                # 让外层等待3秒再寻找下一个新输入框继续后续 SKU
                                self.log("[INFO] {} '{}' 触发提示弹窗，等待弹窗消失，不覆盖当前框".format(label, one_kw))
                                for _wait_modal in range(12):
                                    time.sleep(0.5)
                                    still_open = False
                                    try:
                                        for xp2 in hint_modal_xpaths:
                                            for m2 in driver.find_elements(By.XPATH, xp2):
                                                if m2.is_displayed():
                                                    still_open = True
                                                    break
                                            if still_open:
                                                break
                                    except Exception:
                                        pass
                                    if not still_open:
                                        break
                                return None, 'hint_modal'
                            else:
                                self.log("[WARN] {} 输入'{}' 后无可选项".format(label, one_kw))
                                return None, False
                        except Exception as e:
                            self.log("[WARN] {} 空白处点击处理异常: {}".format(label, str(e)[:60]))
                            return None, False
                        # 不应执行到此处（hint_modal 已提前返回），保留 target 赋值作为防御
                        target = hint_target
                        if target is None:
                            return None, False
                    picked = (target.text or "").strip().replace("\n", " ")
                    ok = _click_option(target)
                    if not ok:
                        self.log("[WARN] {} 输入'{}' 后选项点击失败".format(label, one_kw))
                        return None, False
                    time.sleep(0.45)
                    has_err = _dismiss_error_modal_if_any(wait_rounds=6)
                    if has_err:
                        return None, True
                    self.log("[OK] {} 输入'{}' 后已选择: {}".format(label, one_kw, picked or "(空文本)"))
                    return picked, False
                _skip_open = False
                for kw in keywords:
                    picked, got_error_modal = _attempt_once(kw, skip_open=_skip_open)
                    if picked:
                        _skip_open = False
                        return picked
                    if got_error_modal == 'hint_modal':
                        # 触发了"提示"弹窗：当前框已由 SHEIN 弹窗处理，等南3s渲染下一输入框
                        # 直接返回原始词视为已填写，不再尝试其他关键词，不调用 _pick_first
                        self.log("[INFO] {} '{}' 提示弹窗已处理，等南3s后继续下一个SKU".format(label, seed_text))
                        time.sleep(3.0)
                        return seed_text
                    if got_error_modal:
                        # SHEIN 不支持该颜色词（错误弹窗），直接跳过尝试下一个关键词
                        self.log("[DEBUG] {} SHEIN不支持'{}', 跳过".format(label, kw))
                        _skip_open = True
                        continue
                self.log("[WARN] {} 所有关键词尝试后仍未成功".format(label))
                return None
            # 4) ????????????
            attr_inner = None
            for xp in [
                ".//div[contains(@class,'specAttrSelect') or contains(@class,'spmp_style__specAttrSelect')]//div[contains(@class,'so-select-inner') and @data-id]",
                ".//div[contains(@class,'so-select-inner') and @data-id][1]",
            ]:
                try:
                    for el in spec_content.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            attr_inner = el
                            break
                except Exception:
                    pass
                if attr_inner is not None:
                    break
            if attr_inner is None:
                self.log("[WARN] 未找到第1个下拉框(主规格属性)")
                return
            picked_attr = _pick_first(attr_inner, "主规格属性")
            if not picked_attr:
                self.log("[WARN] 第1个下拉框未成功选择")
                return
            # 5) 第二个框：主规格值下拉
            # 5) 第二个框：主规格値—循环填写所有 SKU 规格値
            def _collect_all_spec_values(attr_text):
                """从 sku_list 提取所有唯一规格値（基于已选的属性维度）。"""
                if not isinstance(product_info, dict):
                    return []
                sku_list = product_info.get("sku_list", []) or []
                if not sku_list:
                    return []
                norm_attr = _normalize_key(attr_text)
                values = []
                seen = set()
                for sku in sku_list:
                    try:
                        raw_key = str(((sku.get("debug_variation") or {}).get("raw_dimension_key") or "")).strip()
                        if raw_key:
                            for part in re.split(r"[;,|]", raw_key):
                                seg = str(part or "").strip()
                                if not seg:
                                    continue
                                key = ""
                                val = ""
                                if "=" in seg:
                                    key, val = seg.split("=", 1)
                                elif ":" in seg:
                                    key, val = seg.split(":", 1)
                                if key and val and _normalize_key(key) == norm_attr:
                                    vv = str(val).strip()
                                    if vv and vv.lower() not in seen:
                                        seen.add(vv.lower())
                                        values.append(vv)
                    except Exception:
                        pass
                if not values:
                    for sku in sku_list:
                        attrs = str(sku.get("sku_attributes") or "").strip()
                        if attrs and attrs != "默认规格":
                            first_part = attrs.split("/")[0].strip()
                            # Strip leading "Key: " prefix (e.g. "Color: black" -> "black")
                            if ":" in first_part:
                                first_part = first_part.split(":", 1)[1].strip()
                            if first_part and first_part.lower() not in seen:
                                seen.add(first_part.lower())
                                values.append(first_part)
                return values
            all_spec_values = _collect_all_spec_values(picked_attr)
            if not all_spec_values:
                first_val = _extract_target_spec_value(picked_attr)
                if first_val:
                    all_spec_values = [first_val]
            self.log("[DEBUG] 需填入的主规格値共 {} 个: {}".format(
                len(all_spec_values), " | ".join(all_spec_values)))
            if not all_spec_values:
                self.log("[WARN] 未提取到任何主规格値，跳过")
                return
            filled_vals = []
            used_data_ids = set()  # track already-processed input boxes by data-id
            # Build a mapping: spec_val order -> sku_list index, so image upload stays aligned
            # all_spec_values is already in sku_list order (same as GUI display)
            for val_idx, spec_val in enumerate(all_spec_values):
                self.log("[DEBUG] 填写第 {} 个规格値: {}".format(val_idx + 1, spec_val))
                # Find the next NEW empty 'please select or customize' input box
                # Key: use data-id to skip boxes we've already filled
                value_inner = None
                # 主规格值每填一个，SHEIN 渲染下一行较慢，重试次数提高
                for _retry in range(20):
                    candidates = []
                    for xp in [
                        ".//div[contains(@class,'specValues') or contains(@class,'spmp_style__specValues')]//div[contains(@class,'so-select-inner') and @data-id]",
                        ".//div[contains(@class,'so-select-inner') and @data-id]",
                    ]:
                        try:
                            els = spec_content.find_elements(By.XPATH, xp)
                            for el in els:
                                if el.is_displayed():
                                    candidates.append(el)
                        except Exception:
                            pass
                        if candidates:
                            break
                    # Pick first candidate whose data-id is NOT in used_data_ids
                    for c in candidates:
                        try:
                            did = (c.get_attribute('data-id') or '').strip()
                            if did and did not in used_data_ids:
                                value_inner = c
                                break
                        except Exception:
                            continue
                    if value_inner is not None:
                        break
                    # Not found yet - SHEIN may not have rendered new box yet
                    self.log("[DEBUG] 第 {} 个规格値：第{}次尝试寻找新输入框...".format(val_idx + 1, _retry + 1))
                    time.sleep(0.5)
                if value_inner is None:
                    self.log("[WARN] 第 {} 个规格値：未找到新的输入框，停止填写".format(val_idx + 1))
                    break
                # Record this box's data-id before filling
                try:
                    current_did = (value_inner.get_attribute('data-id') or '').strip()
                    if current_did:
                        used_data_ids.add(current_did)
                except Exception:
                    pass
                picked_val = _type_and_pick_first(value_inner, "主规格値", spec_val)
                if picked_val:
                    filled_vals.append(picked_val)
                    self.log("[OK] 第 {} 个规格値已填写: {}".format(val_idx + 1, picked_val))
                    time.sleep(1.6)  # wait for SHEIN to append next input box
                else:
                    # _type_and_pick_first 返回 None 说明输入匹配彻底失败
                    # 不能调用 _pick_first 去覆盖当前框（可能 hint_modal 已处理过）
                    self.log("[WARN] 第 {} 个规格値 '{}' 输入匹配失败，跳过（不覆盖已有数据）".format(val_idx + 1, spec_val))
            if filled_vals:
                self._last_main_spec_filled_values = list(filled_vals)
                self.log("[OK] 主规格填写完成: 属性={}，値=[{}]".format(
                    picked_attr, " | ".join(filled_vals)))
            else:
                self._last_main_spec_filled_values = []
                self.log("[WARN] 主规格値全部填写失败")
        except Exception as e:
            self.log("[WARN] 主规格处理失败: {}".format(str(e)[:100]))

    def _handle_other_specs(self, product_info=None):
        """处理其他规格：选规格类型，依次填入规格值。"""
        driver = self.driver
        try:
            if not isinstance(product_info, dict):
                return
            other_specs = product_info.get("other_specs") or {}
            if not other_specs:
                self.log("[DEBUG] 其他规格：无数据，跳过")
                return
            self.log("[DEBUG] 其他规格数据: {}".format(other_specs))
            other_spec_box = None
            for xp in [
                "//div[contains(@class,'so-form-item') and contains(@class,'other_spec')]",
                "//div[contains(@class,'other_spec')]",
            ]:
                try:
                    for box in driver.find_elements(By.XPATH, xp):
                        if box.is_displayed():
                            other_spec_box = box
                            break
                except Exception:
                    pass
                if other_spec_box:
                    break
            if other_spec_box is None:
                self.log("[WARN] 其他规格：未找到区域，跳过")
                return
            try:
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", other_spec_box)
                time.sleep(0.3)
            except Exception:
                pass
            spec_content = None
            try:
                for c in other_spec_box.find_elements(By.XPATH,
                        ".//div[contains(@class,'specContent') or contains(@class,'spmp_style__specContent')]"):
                    if c.is_displayed():
                        spec_content = c
                        break
            except Exception:
                pass
            if spec_content is None:
                spec_content = other_spec_box
            def _osp_open(inner):
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", inner)
                except Exception:
                    pass
                time.sleep(0.2)
                for _ in range(2):
                    try:
                        inner.click()
                        break
                    except Exception:
                        try:
                            driver.execute_script("arguments[0].click();", inner)
                            break
                        except Exception:
                            pass
                time.sleep(0.3)
            def _osp_opts(data_id):
                if not data_id:
                    return []
                try:
                    boxes = driver.find_elements(By.XPATH,
                        "//div[contains(@class,'so-list') and @data-id='{0}' and "
                        "(contains(@class,'so-hidable-show') or not(contains(@style,'display: none')))]".format(data_id))
                    if not boxes:
                        boxes = driver.find_elements(By.XPATH,
                            "//div[contains(@class,'so-list') and @data-id='{0}']".format(data_id))
                    cands = []
                    for b in boxes:
                        try:
                            els = b.find_elements(By.XPATH,
                                ".//label[contains(@class,'so-select-option') or contains(@class,'so-checkinput')]")
                            if not els:
                                els = b.find_elements(By.XPATH,
                                    ".//*[contains(@class,'so-select-option') or contains(@class,'so-option')]")
                            cands.extend(els)
                        except Exception:
                            continue
                    opts = []
                    for el in cands:
                        try:
                            if not el.is_displayed():
                                continue
                            txt = (el.text or "").strip().replace("\n", " ")
                            if not txt or txt in ("请选择", "请选择或自定义", "无数据") or len(txt) > 80:
                                continue
                            opts.append(el)
                        except Exception:
                            continue
                    return opts
                except Exception:
                    return []
            def _osp_click(opt):
                try:
                    driver.execute_script("arguments[0].click();", opt)
                    return True
                except Exception:
                    pass
                try:
                    opt.click()
                    return True
                except Exception:
                    pass
                try:
                    r = opt.find_element(By.XPATH, ".//input[@type='radio' or @type='checkbox']")
                    driver.execute_script("arguments[0].click();", r)
                    return True
                except Exception:
                    return False
            def _osp_norm(txt):
                t = (txt or "").strip().lower().replace(" ", "")
                t = t.replace("colour", "color").replace("颜色", "color").replace("色彩", "color")
                t = t.replace("尺寸", "size").replace("大小", "size")
                return t
            # Step1: 选规格类型
            spec_type_key = list(other_specs.keys())[0]
            spec_values   = list(other_specs.values())[0]
            self.log("[DEBUG] 其他规格类型={} 值={}".format(spec_type_key, spec_values))
            attr_inner = None
            for xp in [
                ".//div[contains(@class,'specAttrSelect') or contains(@class,'spmp_style__specAttrSelect')]//div[contains(@class,'so-select-inner') and @data-id]",
                ".//div[contains(@class,'so-select-inner') and @data-id][1]",
            ]:
                try:
                    for el in spec_content.find_elements(By.XPATH, xp):
                        if el.is_displayed():
                            attr_inner = el
                            break
                except Exception:
                    pass
                if attr_inner:
                    break
            if attr_inner is None:
                self.log("[WARN] 其他规格：未找到类型下拉")
                return
            already = ""
            try:
                sp = attr_inner.find_element(By.XPATH,
                    ".//span[contains(@class,'so-select-input') or contains(@class,'renderItemEllipsis')]")
                already = (sp.text or "").strip()
            except Exception:
                pass
            if already and _osp_norm(already) == _osp_norm(spec_type_key):
                self.log("[OK] 其他规格类型已预选: {}".format(already))
            else:
                did = (attr_inner.get_attribute("data-id") or "").strip()
                opts = []
                for _ in range(5):
                    _osp_open(attr_inner)
                    opts = _osp_opts(did)
                    if opts:
                        break
                    time.sleep(0.35)
                if not opts:
                    self.log("[WARN] 其他规格：类型下拉无选项")
                    return
                tgt = None
                for o in opts:
                    txt = (o.text or "").strip().replace("\n", " ")
                    if _osp_norm(txt) == _osp_norm(spec_type_key) or _osp_norm(spec_type_key) in _osp_norm(txt):
                        tgt = o
                        break
                if tgt is None:
                    tgt = opts[0]
                picked = (tgt.text or "").strip().replace("\n", " ")
                if _osp_click(tgt):
                    self.log("[OK] 其他规格类型已选: {}".format(picked))
                    time.sleep(0.5)
                else:
                    self.log("[WARN] 其他规格：类型点击失败")
                    return
            # Step2: 依次填入规格值
            used_dids = set()
            for val_idx, spec_val in enumerate(spec_values):
                spec_val = str(spec_val).strip()
                if not spec_val:
                    continue
                self.log("[DEBUG] 其他规格值[{}]: {}".format(val_idx + 1, spec_val))
                val_inner = None
                for _retry in range(8):
                    cands = []
                    for xp in [
                        ".//div[contains(@class,'specValues') or contains(@class,'spmp_style__specValues')]//div[contains(@class,'so-select-inner') and @data-id]",
                        ".//div[contains(@class,'so-select-inner') and @data-id]",
                    ]:
                        try:
                            for el in spec_content.find_elements(By.XPATH, xp):
                                if el.is_displayed():
                                    cands.append(el)
                        except Exception:
                            pass
                        if cands:
                            break
                    for c in cands:
                        try:
                            d = (c.get_attribute("data-id") or "").strip()
                            if d and d not in used_dids:
                                val_inner = c
                                break
                        except Exception:
                            continue
                    if val_inner:
                        break
                    time.sleep(0.5)
                if val_inner is None:
                    self.log("[WARN] 其他规格：值[{}]未找到输入框，停止".format(val_idx + 1))
                    break
                try:
                    d = (val_inner.get_attribute("data-id") or "").strip()
                    if d:
                        used_dids.add(d)
                except Exception:
                    pass
                did_val = (val_inner.get_attribute("data-id") or "").strip()
                _osp_open(val_inner)
                time.sleep(0.25)
                inp_el = None
                try:
                    for ip in val_inner.find_elements(By.XPATH,
                            ".//input[not(@type='hidden') and not(@disabled)]"):
                        if ip.is_displayed() and ip.is_enabled():
                            inp_el = ip
                            break
                except Exception:
                    pass
                if inp_el is None and did_val:
                    try:
                        for ip in driver.find_elements(By.XPATH,
                                "//div[contains(@class,'so-list') and @data-id='{0}']//input[not(@type='hidden')]".format(did_val)):
                            if ip.is_displayed() and ip.is_enabled():
                                inp_el = ip
                                break
                    except Exception:
                        pass
                typed = False
                if inp_el:
                    try:
                        driver.execute_script(
                            "var e=arguments[0],v=arguments[1];e.focus();e.value='';"
                            "e.dispatchEvent(new Event('input',{bubbles:true}));e.value=v;"
                            "e.dispatchEvent(new Event('input',{bubbles:true}));"
                            "e.dispatchEvent(new Event('change',{bubbles:true}));",
                            inp_el, spec_val)
                        typed = True
                    except Exception:
                        pass
                    if not typed:
                        try:
                            inp_el.clear()
                            inp_el.send_keys(spec_val)
                            typed = True
                        except Exception:
                            pass
                if not typed:
                    try:
                        ae = driver.switch_to.active_element
                        if ae:
                            ae.send_keys(spec_val)
                            typed = True
                    except Exception:
                        pass
                if not typed:
                    self.log("[WARN] 其他规格值[{}] '{}' 输入失败".format(val_idx + 1, spec_val))
                    continue
                vopts = []
                for _wr in range(6):
                    time.sleep(0.5)
                    vopts = _osp_opts(did_val)
                    if vopts:
                        break
                if not vopts:
                    try:
                        from selenium.webdriver.common.keys import Keys as _Keys
                        if inp_el:
                            inp_el.send_keys(_Keys.RETURN)
                        self.log("[OK] other_spec val[{}] '{}' custom confirmed".format(val_idx+1, spec_val))
                        # click blank to confirm custom input
                        try:
                            clicked_blank = driver.execute_script(
                                "var c=document.getElementById('spec_info');"+
                                "if(c){var h=c.querySelector('[class*=card_header]');"+
                                "if(h){h.click();return true;}c.click();return true;}return false;")
                            if not clicked_blank:
                                try:
                                    from selenium.webdriver.common.action_chains import ActionChains as _AC
                                    _AC(driver).move_by_offset(10,10).click().perform()
                                except Exception:
                                    pass
                        except Exception:
                            pass
                        time.sleep(1.0)
                        continue
                    except Exception:
                        pass
                    self.log("[WARN] 其他规格值[{}] '{}' 无选项".format(val_idx + 1, spec_val))
                    continue
                tgt_v = None
                low = spec_val.lower().strip()
                for op in vopts:
                    try:
                        txt = (op.text or "").strip().lower()
                        if low in txt or txt in low:
                            tgt_v = op
                            break
                    except Exception:
                        continue
                if tgt_v is None:
                    tgt_v = vopts[0]
                pv = (tgt_v.text or "").strip().replace("\n", " ")
                if _osp_click(tgt_v):
                    self.log("[OK] 其他规格值[{}] 已选: {}".format(val_idx + 1, pv))
                    # click blank to confirm input
                    try:
                        clicked_blank = driver.execute_script(
                            "var c=document.getElementById('spec_info');"+
                            "if(c){var h=c.querySelector('[class*=card_header]');"+
                            "if(h){h.click();return true;}c.click();return true;}return false;")
                        if not clicked_blank:
                            try:
                                from selenium.webdriver.common.action_chains import ActionChains as _AC
                                _AC(driver).move_by_offset(10,10).click().perform()
                            except Exception:
                                pass
                    except Exception:
                        pass
                    time.sleep(1.0)
                else:
                    self.log("[WARN] other_spec value click failed idx={}".format(val_idx+1))
            self.log("[OK] other_spec fill complete")
        except Exception as e:
            self.log("[WARN] other_spec failed: {}".format(str(e)[:100]))


    def _get_detail_img_input(self):
        """精确定位细节图列的 file input。
        先滚动页面使容器渲染，再等待它出现，最多重试境欿10次。"""
        self._ensure_not_stopped()
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
            try:
                self._ensure_not_stopped()
            except Exception:
                return None
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
        """按 SKU 行逐行为各 SKU 的细节图列上传对应图片，每个 SKU 最多5张。"""
        try:
            self._ensure_not_stopped()
            driver = self.driver
            sku_list = product_info.get("sku_list", []) or []
            main_images = product_info.get("main_images", [])
            if not main_images and product_info.get("image_url"):
                main_images = [product_info["image_url"]]
            fallback_images = main_images[:5]
            if not sku_list:
                # No SKU list: fallback to old single-input upload
                if not fallback_images:
                    self.log("[ERROR] 没有图片可上传")
                    return
                self.log("[DEBUG] 无 SKU 列表，回退单框模式，上传 {} 张".format(len(fallback_images)))
                self._upload_images_to_single_input(fallback_images)
                return
            # Scroll to detail image table
            self.log("开始上传细节图...")
            try:
                driver.execute_script(
                    "var el=document.querySelector('div.detail_img_container,#userguide_commodities_info_skc_title_table');"
                    "if(el){el.scrollIntoView({block:'center',behavior:'smooth'});}"
                    "else{window.scrollTo(0,document.body.scrollHeight*0.6);}"
                )
                time.sleep(1.5)
            except Exception:
                pass
            # Find all <tr> rows in the detail image table body
            try:
                rows = driver.find_elements(By.CSS_SELECTOR,
                    "#userguide_commodities_info_skc_title_table tbody tr,"
                    "div.detail_img_container tbody tr")
            except Exception:
                rows = []
            if not rows:
                self.log("[WARN] 未找到细节图表格行，回退单框模式")
                self._upload_images_to_single_input(fallback_images)
                return
            self.log("[DEBUG] 找到 {} 行 SKU 细节图行".format(len(rows)))

            # -- 动态检测各列索引（细节图、方形图、色块图）--
            _col_detail = 2
            _col_square = -1
            _col_color_block = -1
            try:
                _header_rows = driver.find_elements(By.CSS_SELECTOR,
                    "#userguide_commodities_info_skc_title_table thead tr,"
                    "div.detail_img_container thead tr")
                for _hr in _header_rows:
                    _ths = _hr.find_elements(By.TAG_NAME, "th")
                    if not _ths:
                        _ths = _hr.find_elements(By.TAG_NAME, "td")
                    _header_texts = []
                    for _th_idx, _th in enumerate(_ths):
                        _th_text = (_th.text or "").strip()
                        _header_texts.append(_th_text)
                        if "细节" in _th_text:
                            _col_detail = _th_idx
                        elif "方形" in _th_text:
                            _col_square = _th_idx
                        elif "色块" in _th_text:
                            _col_color_block = _th_idx
                    if _header_texts:
                        self.log("[DEBUG] 表头列: {}".format(_header_texts))
                        break
            except Exception:
                pass
            if _col_color_block < 0:
                _col_color_block = _col_detail + 2 if _col_detail >= 0 else 4
            self.log("[DEBUG] 列索引: 细节图={}, 方形图={}, 色块图={}".format(
                _col_detail, _col_square, _col_color_block))

            # -- 读取页面每行第1列颜色文本，反查 sku_list 找对应 SKU --
            _CN_EN = {
                "黑色": "black", "白色": "white", "灰色": "grey",
                "红色": "red", "蓝色": "blue", "绿色": "green",
                "黄色": "yellow", "粉色": "pink", "粉红色": "pink",
                "紫色": "purple", "棕色": "brown", "褐色": "brown",
                "橙色": "orange", "金色": "gold", "银色": "silver",
                "米色": "beige", "米白色": "beige",
                "酒红色": "wine", "卡其色": "khaki",
                "深灰色": "darkgrey", "浅灰色": "lightgrey",
                "深蓝色": "darkblue", "天蓝色": "skyblue",
                "藏青色": "navy", "咖啡色": "coffee",
                "墨绿色": "darkgreen", "浅绿色": "lightgreen",
                "浅蓝色": "lightblue", "深红色": "darkred",
                "橘色": "orange", "灰白色": "greywhite",
                "奶白色": "creamwhite", "米黄色": "cream",
                "原木色": "natural", "驼色": "camel",
                "透明": "clear", "黑白色": "blackandwhite",
                "花色": "floral", "多色": "multicolor",
                "杏色": "apricot",
            }

            def _norm_color(s):
                return re.sub(r"[\s\-_&/]+", "", (s or "")).lower()

            def _sku_color_val(sku):
                attrs = str(sku.get("sku_attributes") or "")
                cv = attrs.split("/")[0].strip() if attrs else ""
                if ":" in cv:
                    cv = cv.split(":", 1)[1].strip()
                return cv

            def _read_row_color(row_el):
                try:
                    tds = row_el.find_elements(By.TAG_NAME, "td")
                    if tds:
                        raw = tds[0].text or ""
                        lns = [l.strip() for l in raw.strip().splitlines() if l.strip()]
                        if lns:
                            return lns[0]
                except Exception:
                    pass
                return ""

            def _split_cn_en(text):
                """Split '白色White' into ('白色', 'White')."""
                t = (text or "").strip()
                cn_part = ""
                en_part = ""
                for ch in t:
                    if '\u4e00' <= ch <= '\u9fff':
                        cn_part += ch
                    elif ch.isascii() and ch.isalpha():
                        en_part += ch
                    elif ch == ' ' and en_part:
                        en_part += ch
                return cn_part.strip(), en_part.strip()

            def _match_sku_by_color(page_color, _sku_list, used_indices):
                nc = _norm_color(page_color)
                if not nc:
                    return None, -1
                # Layer 1: direct normalized match
                for i, sku in enumerate(_sku_list):
                    if i in used_indices:
                        continue
                    if _norm_color(_sku_color_val(sku)) == nc:
                        return sku, i
                # Layer 2: extract Chinese/English parts and match via CN_EN dict
                cn_part, en_part = _split_cn_en(page_color)
                # 2a: look up Chinese part in CN_EN
                for cn_key in [page_color.strip(), cn_part]:
                    cn_en_hit = _CN_EN.get(cn_key)
                    if cn_en_hit:
                        nc_en = _norm_color(cn_en_hit)
                        for i, sku in enumerate(_sku_list):
                            if i in used_indices:
                                continue
                            if _norm_color(_sku_color_val(sku)) == nc_en:
                                return sku, i
                # 2b: use English part directly (e.g. page="白色White" -> en_part="White")
                if en_part:
                    nc_en = _norm_color(en_part)
                    for i, sku in enumerate(_sku_list):
                        if i in used_indices:
                            continue
                        nc_attr = _norm_color(_sku_color_val(sku))
                        if nc_attr == nc_en:
                            return sku, i
                # Layer 3: match via filled_values prefix
                filled_vals = getattr(self, "_last_main_spec_filled_values", []) or []
                filled_idxs = getattr(self, "_main_spec_filled_sku_indices", []) or []
                for fi, fv in enumerate(filled_vals):
                    nfv = _norm_color(fv)
                    if nc and nfv and (nfv.startswith(nc) or nc.startswith(nfv) or nc == nfv):
                        if fi < len(filled_idxs):
                            si = filled_idxs[fi]
                            if si not in used_indices and 0 <= si < len(_sku_list):
                                return _sku_list[si], si
                # Layer 4: substring containment (fuzzy)
                for i, sku in enumerate(_sku_list):
                    if i in used_indices:
                        continue
                    nc_attr = _norm_color(_sku_color_val(sku))
                    if nc_attr and (nc_attr in nc or nc in nc_attr):
                        return sku, i
                return None, -1

            row_sku_map = []
            used_sku_indices = set()
            for ri, r in enumerate(rows):
                page_color = _read_row_color(r)
                matched_sku, matched_idx = _match_sku_by_color(
                    page_color, sku_list, used_sku_indices)
                if matched_sku is not None:
                    used_sku_indices.add(matched_idx)
                    row_sku_map.append((page_color, matched_sku))
                    self.log("[MAP] 行{:02d} 页面='{}' -> SKU='{}' | imgs={}".format(
                        ri + 1, page_color,
                        matched_sku.get("sku_attributes", ""),
                        len((matched_sku.get("images") or [])[:5])))
                else:
                    row_sku_map.append((page_color, None))
                    self.log("[MAP] 行{:02d} 页面='{}' -> 未匹配".format(
                        ri + 1, page_color))

            for row_idx in range(len(row_sku_map)):
                self._ensure_not_stopped()
                # Re-find rows each iteration to avoid stale DOM references
                # (swatch upload / crop dialog may trigger table re-render)
                try:
                    rows = driver.find_elements(By.CSS_SELECTOR,
                        "#userguide_commodities_info_skc_title_table tbody tr,"
                        "div.detail_img_container tbody tr")
                except Exception:
                    pass
                if row_idx >= len(rows):
                    self.log("[WARN] 行 {} 超出当前表格行数 {}，跳过".format(row_idx + 1, len(rows)))
                    break
                row = rows[row_idx]
                page_color, matched_sku = row_sku_map[row_idx]
                if matched_sku is not None:
                    sku_imgs = (matched_sku.get("images") or [])[:5]
                    sku_attr = matched_sku.get("sku_attributes", "")
                else:
                    sku_imgs = fallback_images
                    sku_attr = page_color or "(未匹配)"
                if not sku_imgs:
                    sku_imgs = fallback_images
                self.log("[DEBUG] SKU行 {} (页面:{} -> SKU:{}): 准备上传 {} 张图片".format(
                    row_idx + 1, page_color, sku_attr, len(sku_imgs)))
                # Scroll row into view
                try:
                    driver.execute_script("arguments[0].scrollIntoView({block:'center'});", row)
                    time.sleep(0.5)
                except Exception:
                    pass
                # Find the detail image file input in the 3rd <td> of this row
                # The 3rd td (index 2) has class uploadSimpleDragBox with file input
                fi = None
                try:
                    # Target specifically the detail img column (3rd td, index 2)
                    tds = row.find_elements(By.TAG_NAME, "td")
                    detail_td = None
                    if len(tds) >= 3:
                        detail_td = tds[2]  # 3rd column = 细节图
                    elif tds:
                        detail_td = tds[-1]
                    if detail_td:
                        # Find file input with multiple attribute (detail img accepts multiple)
                        inputs = detail_td.find_elements(By.CSS_SELECTOR, "input[type='file'][multiple]")
                        if not inputs:
                            inputs = detail_td.find_elements(By.CSS_SELECTOR, "input[type='file']")
                        if inputs:
                            fi = inputs[0]
                except Exception as e:
                    self.log("[WARN] 行 {} 定位细节图 input 失败: {}".format(row_idx+1, str(e)[:60]))
                if fi is None:
                    self.log("[WARN] SKU行 {} 未找到 file input, 跳过".format(row_idx + 1))
                    continue
                # Upload all images for this SKU row at once via send_keys
                # Collect all temp paths first
                img_paths = []
                for img_url in sku_imgs:
                    try:
                        p = self._save_img_temp(img_url)
                        if p:
                            img_paths.append(p)
                    except Exception as e:
                        self.log("[WARN] 图片下载失败: {}".format(str(e)[:60]))
                if not img_paths:
                    self.log("[WARN] SKU行 {} 所有图片下载失败, 跳过".format(row_idx + 1))
                    continue
                # Upload images one by one for this SKU row, handling crop dialog per image
                upload_ok_count = 0
                for img_idx, img_path in enumerate(img_paths):
                    try:
                        self._dismiss_switch_confirm_modal()
                        # Re-find the file input for this row each time (DOM may refresh)
                        fi_cur = fi
                        try:
                            tds_cur = row.find_elements(By.TAG_NAME, "td")
                            detail_td_cur = tds_cur[2] if len(tds_cur) >= 3 else (tds_cur[-1] if tds_cur else None)
                            if detail_td_cur:
                                inputs_cur = detail_td_cur.find_elements(By.CSS_SELECTOR, "input[type='file'][multiple]")
                                if not inputs_cur:
                                    inputs_cur = detail_td_cur.find_elements(By.CSS_SELECTOR, "input[type='file']")
                                if inputs_cur:
                                    fi_cur = inputs_cur[0]
                        except Exception:
                            pass
                        driver.execute_script(
                            "arguments[0].style.display='block';"
                            "arguments[0].style.visibility='visible';"
                            "arguments[0].style.opacity='1';", fi_cur)
                        fi_cur.send_keys(img_path)
                        self.log("[DEBUG] SKU行 {} 图{}已提交".format(row_idx + 1, img_idx + 1))
                        self._dismiss_switch_confirm_modal()
                        self._handle_crop_dialog()
                        time.sleep(1.5)
                        upload_ok_count += 1
                    except Exception as e:
                        self.log("[ERROR] SKU行 {} 图{} 上传失败: {}".format(row_idx+1, img_idx+1, str(e)[:60]))
                self.log("[OK] SKU行 {} 已成功上传 {}/{} 张细节图".format(
                    row_idx + 1, upload_ok_count, len(img_paths)))

                # -- 上传后颜色校验：重读当前行颜色，与预期 SKU 比对 --
                try:
                    rows = driver.find_elements(By.CSS_SELECTOR,
                        "#userguide_commodities_info_skc_title_table tbody tr,"
                        "div.detail_img_container tbody tr")
                    if row_idx < len(rows):
                        row = rows[row_idx]
                    verify_color = _read_row_color(row)
                    if matched_sku is not None:
                        expected_attr = _sku_color_val(matched_sku)
                        vc_norm = _norm_color(verify_color)
                        ea_norm = _norm_color(expected_attr)
                        cn_part_v, en_part_v = _split_cn_en(verify_color)
                        cn_part_e, en_part_e = _split_cn_en(expected_attr)
                        color_ok = (
                            vc_norm == ea_norm
                            or (en_part_v and en_part_e and _norm_color(en_part_v) == _norm_color(en_part_e))
                            or (cn_part_v and _CN_EN.get(cn_part_v, "") and _norm_color(_CN_EN[cn_part_v]) == ea_norm)
                            or (ea_norm and ea_norm in vc_norm)
                            or (vc_norm and vc_norm in ea_norm)
                        )
                        if color_ok:
                            self.log("[CHECK] SKU行 {} 颜色校验通过: 页面='{}' SKU='{}'".format(
                                row_idx + 1, verify_color, expected_attr))
                        else:
                            self.log("[WARN] SKU行 {} 颜色校验不一致! 页面='{}' 预期SKU='{}' — 图片可能传错".format(
                                row_idx + 1, verify_color, expected_attr))
                except Exception as _vc_e:
                    self.log("[DEBUG] SKU行 {} 颜色校验异常: {}".format(row_idx + 1, str(_vc_e)[:60]))

                # -- 方形图检查：动态定位方形图列，检查是否需要补传第1张细节图 --
                square_uploaded = False
                try:
                    try:
                        rows_sq = driver.find_elements(By.CSS_SELECTOR,
                            "#userguide_commodities_info_skc_title_table tbody tr,"
                            "div.detail_img_container tbody tr")
                        if row_idx < len(rows_sq):
                            row = rows_sq[row_idx]
                    except Exception:
                        pass
                    tds_sq = row.find_elements(By.TAG_NAME, "td")

                    square_td = None
                    square_td_idx = -1

                    # 方法1：通过表头文字匹配"方形"定位列索引
                    try:
                        header_rows = driver.find_elements(By.CSS_SELECTOR,
                            "#userguide_commodities_info_skc_title_table thead tr,"
                            "div.detail_img_container thead tr")
                        for hr in header_rows:
                            ths = hr.find_elements(By.TAG_NAME, "th")
                            if not ths:
                                ths = hr.find_elements(By.TAG_NAME, "td")
                            for th_idx, th in enumerate(ths):
                                th_text = (th.text or "").strip()
                                if "方形" in th_text:
                                    square_td_idx = th_idx
                                    if th_idx < len(tds_sq):
                                        square_td = tds_sq[th_idx]
                                    self.log("[DEBUG] 通过表头定位方形图列: 索引 {}".format(th_idx))
                                    break
                            if square_td is not None:
                                break
                    except Exception:
                        pass

                    # 方法2：扫描 td 的 innerHTML，方形图为单文件上传框（无 multiple 属性）
                    if square_td is None:
                        for chk_idx in [1, 3]:
                            if chk_idx >= len(tds_sq) or chk_idx == 2:
                                continue
                            try:
                                chk_html = driver.execute_script(
                                    "return arguments[0].innerHTML;", tds_sq[chk_idx])
                                has_file = ("type=\"file\"" in chk_html or "type='file'" in chk_html)
                                is_single = "multiple" not in chk_html
                                if has_file and is_single:
                                    square_td = tds_sq[chk_idx]
                                    square_td_idx = chk_idx
                                    self.log("[DEBUG] 通过HTML特征定位方形图列: 索引 {}".format(chk_idx))
                                    break
                            except Exception:
                                pass

                    # 方法3：兜底，优先索引 1（方形图在细节图前）再试 3
                    if square_td is None:
                        for fb_idx in [1, 3]:
                            if fb_idx < len(tds_sq):
                                square_td = tds_sq[fb_idx]
                                square_td_idx = fb_idx
                                self.log("[DEBUG] 方形图列兜底定位: 索引 {}".format(fb_idx))
                                break

                    if square_td is not None:
                        sq_inner_html = ""
                        try:
                            sq_inner_html = driver.execute_script(
                                "return arguments[0].innerHTML;", square_td)
                        except Exception:
                            pass

                        sq_has_upload_btn = False
                        if "点击上传" in sq_inner_html or "上传图片" in sq_inner_html:
                            sq_has_upload_btn = True
                        if not sq_has_upload_btn:
                            for cls_kw in ['uploadPlus', 'uploadText', 'uploadHandle', 'upload-text']:
                                if cls_kw in sq_inner_html:
                                    sq_has_upload_btn = True
                                    break
                        if not sq_has_upload_btn:
                            try:
                                sq_upload_els = square_td.find_elements(By.XPATH,
                                    ".//*[contains(@class,'uploadPlus') or contains(@class,'uploadText') "
                                    "or contains(@class,'uploadHandle') or contains(@class,'upload-text')]")
                                if not sq_upload_els:
                                    sq_upload_els = square_td.find_elements(By.XPATH,
                                        ".//*[contains(text(),'点击上传') or contains(text(),'上传图片')]")
                                sq_has_upload_btn = len(sq_upload_els) > 0
                            except Exception:
                                pass

                        sq_has_img = False
                        try:
                            sq_imgs = square_td.find_elements(By.CSS_SELECTOR, "img")
                            sq_has_img = any(
                                im.is_displayed() and (im.get_attribute("src") or "").startswith("http")
                                for im in sq_imgs
                            )
                        except Exception:
                            pass

                        self.log("[DEBUG] SKU行 {} 方形图检查(列{}): 有上传按钮={}, 已有图片={}, HTML: {}".format(
                            row_idx + 1, square_td_idx, sq_has_upload_btn, sq_has_img,
                            sq_inner_html[:200] if sq_inner_html else "(empty)"))

                        if (sq_has_upload_btn or not sq_has_img) and img_paths:
                            sq_input = None
                            try:
                                sq_inputs = square_td.find_elements(By.CSS_SELECTOR, "input[type='file']")
                                if sq_inputs:
                                    sq_input = sq_inputs[0]
                            except Exception:
                                pass
                            if sq_input is not None:
                                try:
                                    self._dismiss_switch_confirm_modal()
                                    driver.execute_script(
                                        "arguments[0].style.display='block';"
                                        "arguments[0].style.visibility='visible';"
                                        "arguments[0].style.opacity='1';", sq_input)
                                    sq_input.send_keys(img_paths[0])
                                    self.log("[OK] SKU行 {} 方形图未自动加载，已补传第1张细节图".format(row_idx + 1))
                                    self._dismiss_switch_confirm_modal()
                                    self._handle_crop_dialog()
                                    time.sleep(1.2)
                                    square_uploaded = True
                                except Exception as e:
                                    self.log("[WARN] SKU行 {} 方形图补传失败: {}".format(row_idx + 1, str(e)[:60]))
                            else:
                                self.log("[DEBUG] SKU行 {} 方形图列未找到 file input, HTML: {}".format(
                                    row_idx + 1, sq_inner_html[:300]))
                        else:
                            self.log("[DEBUG] SKU行 {} 方形图已有图片，跳过补传".format(row_idx + 1))
                    else:
                        try:
                            row_html = driver.execute_script("return arguments[0].innerHTML;", row)
                            self.log("[DEBUG] SKU行 {} 未找到方形图列(共{}列), 行HTML: {}".format(
                                row_idx + 1, len(tds_sq), row_html[:500]))
                        except Exception:
                            self.log("[DEBUG] SKU行 {} 未找到方形图列(共{}列)".format(row_idx + 1, len(tds_sq)))
                except Exception as e:
                    self.log("[DEBUG] SKU行 {} 方形图检查异常: {}".format(row_idx + 1, str(e)[:60]))

                # -- 色块图：必须上传，缺失会导致发布失败 --
                try:
                    color_img_path = img_paths[0] if img_paths else None
                    if not color_img_path:
                        self.log("[WARN] SKU行 {} 无可用图片，跳过色块图".format(row_idx + 1))
                    else:
                        piece_uploaded = False
                        for _cb_attempt in range(5):
                            if piece_uploaded:
                                break
                            try:
                                # 每次重试都重新获取行引用
                                try:
                                    _rows_cb = driver.find_elements(By.CSS_SELECTOR,
                                        "#userguide_commodities_info_skc_title_table tbody tr,"
                                        "div.detail_img_container tbody tr")
                                    if row_idx < len(_rows_cb):
                                        row = _rows_cb[row_idx]
                                except Exception:
                                    pass
                                if _cb_attempt > 0:
                                    self._dismiss_switch_confirm_modal()

                                tds_piece = row.find_elements(By.TAG_NAME, "td")
                                piece_input = None

                                # 方法1：使用表头检测到的色块图列索引
                                if piece_input is None and 0 <= _col_color_block < len(tds_piece):
                                    _pi = tds_piece[_col_color_block].find_elements(
                                        By.CSS_SELECTOR, "input[type='file']")
                                    if _pi:
                                        piece_input = _pi[0]
                                        self.log("[DEBUG] 色块图 input 定位: 表头列索引 {}".format(
                                            _col_color_block)) if _cb_attempt == 0 else None

                                # 方法2：旧逻辑兼容，第5列
                                if piece_input is None and len(tds_piece) >= 5:
                                    _pi = tds_piece[4].find_elements(
                                        By.CSS_SELECTOR, "input[type='file']")
                                    if _pi:
                                        piece_input = _pi[0]

                                # 方法3：圆角上传容器
                                if piece_input is None:
                                    _ri = row.find_elements(By.CSS_SELECTOR,
                                        "div[style*='border-radius: 50'] input[type='file'],"
                                        "div[style*='border-radius:50'] input[type='file']")
                                    if _ri:
                                        piece_input = _ri[0]

                                # 方法4：最后一列
                                if piece_input is None and tds_piece:
                                    _pi = tds_piece[-1].find_elements(
                                        By.CSS_SELECTOR, "input[type='file']")
                                    if _pi:
                                        piece_input = _pi[0]

                                # 方法5：行内所有非 multiple 的 file input（排除细节图列）
                                if piece_input is None:
                                    _all_fi = row.find_elements(
                                        By.CSS_SELECTOR, "input[type='file']")
                                    for _fi in _all_fi:
                                        if not _fi.get_attribute("multiple"):
                                            _fi_parent_td = None
                                            try:
                                                _fi_parent_td = driver.execute_script(
                                                    "return arguments[0].closest('td');", _fi)
                                            except Exception:
                                                pass
                                            td_idx = -1
                                            if _fi_parent_td:
                                                for _ti, _td in enumerate(tds_piece):
                                                    try:
                                                        if _td == _fi_parent_td:
                                                            td_idx = _ti
                                                            break
                                                    except Exception:
                                                        pass
                                            if td_idx != _col_detail:
                                                piece_input = _fi
                                                self.log("[DEBUG] 色块图 input 定位: 行内非multiple input (td={})".format(td_idx))
                                                break

                                if piece_input is None:
                                    self.log("[DEBUG] SKU行 {} 色块图第{}次尝试未找到 input (共{}列)".format(
                                        row_idx + 1, _cb_attempt + 1, len(tds_piece)))
                                    if _cb_attempt < 4:
                                        time.sleep(1.5)
                                    continue

                                self._dismiss_switch_confirm_modal()
                                driver.execute_script(
                                    "var el=arguments[0];"
                                    "el.style.display='block';"
                                    "el.style.visibility='visible';"
                                    "el.style.opacity='1';"
                                    "el.style.height='10px';"
                                    "el.style.width='10px';"
                                    "el.style.position='relative';"
                                    "el.style.zIndex='9999';", piece_input)
                                piece_input.send_keys(color_img_path)
                                self.log("[OK] SKU行 {} 色块图已提交（第{}次, 取细节图第1张）".format(
                                    row_idx + 1, _cb_attempt + 1))
                                self._dismiss_switch_confirm_modal()
                                self._handle_crop_dialog()
                                time.sleep(1.2)
                                piece_uploaded = True
                            except Exception as e:
                                self.log("[WARN] SKU行 {} 色块图第{}次尝试异常: {}".format(
                                    row_idx + 1, _cb_attempt + 1, str(e)[:60]))
                                if _cb_attempt < 4:
                                    time.sleep(1.5)

                        if not piece_uploaded:
                            self.log("[ERROR] SKU行 {} 色块图经5次重试仍未上传!".format(row_idx + 1))
                except Exception as e:
                    self.log("[ERROR] SKU行 {} 色块图流程异常: {}".format(row_idx + 1, str(e)[:60]))

                # Cleanup temp files
                for p in img_paths:
                    try:
                        os.remove(p)
                    except Exception:
                        pass
            self.log("[OK] 细节图上传完成")
        except Exception as e:
            self.log("[ERROR] 上传细节图异常: {}".format(str(e)[:80]))

    def _upload_images_to_single_input(self, images):
        """原单框模式：将图片列表逐个上传到第一个找到的细节图 input。"""
        images_to_upload = images[:5]
        self.log("[DEBUG] 单框模式：准备上传 {} 张图片".format(len(images_to_upload)))
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        time.sleep(1.5)
        self.driver.execute_script("window.scrollTo(0, document.body.scrollHeight * 0.5);")
        time.sleep(1.5)
        for idx, img_url in enumerate(images_to_upload):
            try:
                self._ensure_not_stopped()
                self.log("[DEBUG] 上传细节图第 {} 张...".format(idx + 1))
                img_path = self._save_img_temp(img_url)
                if not img_path:
                    self.log("[ERROR] 第 {} 张下载失败".format(idx + 1))
                    continue
                self._dismiss_switch_confirm_modal()
                fi = self._get_detail_img_input()
                if fi is None:
                    self.log("[ERROR] 第 {} 张：未找到细节图 input".format(idx + 1))
                    try:
                        os.remove(img_path)
                    except Exception:
                        pass
                    continue
                try:
                    self.driver.execute_script(
                        "arguments[0].style.display='block';"
                        "arguments[0].style.visibility='visible';"
                        "arguments[0].style.opacity='1';", fi)
                    fi.send_keys(img_path)
                    self.log("[OK] 第 {} 张细节图已提交上传".format(idx + 1))
                    self._dismiss_switch_confirm_modal()
                    self._handle_crop_dialog()
                    time.sleep(1.5)
                except Exception as e:
                    self.log("[ERROR] 第 {} 张 send_keys 失败: {}".format(idx + 1, str(e)[:60]))
                try:
                    os.remove(img_path)
                except Exception:
                    pass
            except Exception as e:
                self.log("[ERROR] 第 {} 张上传失败: {}".format(idx + 1, str(e)[:60]))

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

    def upload_product_image_OLD(self, image_path):
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
                        before_val = (inp.get_attribute("value") or "").strip()
                        inp.send_keys(os.path.abspath(img_path))
                        time.sleep(0.4)
                        after_val = (inp.get_attribute("value") or "").strip()
                        if not after_val or after_val == before_val:
                            self.log("[识图选类目] 此 input 未接收文件，尝试下一个")
                            continue
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

    def cleanup_after_stop(self):
        """停止后清理页面临时弹窗，避免影响回到主页后的停留稳定性。"""
        try:
            if self.driver is None:
                return
            # 1) 先关闭公告弹窗
            try:
                self._dismiss_announcements()
            except Exception:
                pass
            # 2) 关闭常见 modal / dialog 的关闭按钮
            close_xpaths = [
                "//button[contains(@class,'close')]",
                "//i[contains(@class,'close')]",
                "//*[contains(@class,'so-modal') or contains(@class,'dialog')]//*[contains(text(),'关闭') or contains(text(),'取消') or contains(text(),'我知道了') or contains(text(),'知道了')]",
                "//*[contains(@class,'so-modal') or contains(@class,'dialog')]//button[.//span[contains(text(),'关闭') or contains(text(),'取消') or contains(text(),'我知道了') or contains(text(),'知道了')]]",
            ]
            for xp in close_xpaths:
                try:
                    for el in self.driver.find_elements(By.XPATH, xp):
                        try:
                            if el.is_displayed() and el.is_enabled():
                                self.driver.execute_script("arguments[0].click();", el)
                                time.sleep(0.15)
                        except Exception:
                            continue
                except Exception:
                    continue
            # 3) 发送 ESC，兜底关闭遮罩层
            try:
                from selenium.webdriver.common.action_chains import ActionChains
                from selenium.webdriver.common.keys import Keys
                ActionChains(self.driver).send_keys(Keys.ESCAPE).perform()
            except Exception:
                pass
            self.log("[STOP] 停止后弹窗清理完成")
        except Exception as e:
            self.log("[STOP] 停止后弹窗清理异常: {}".format(str(e)[:80]))

    def _dismiss_switch_confirm_modal(self):
        """
        检测页面上是否弹出"切换后，将清空已填写SKC、SKU信息，是否确认切换？"弹窗，
        若存在则点击"取消"按钮，避免误清空已填写数据。
        返回 True 表示检测到并已点击取消，False 表示未检测到弹窗。
        """
        driver = self.driver
        try:
            # 通过弹窗特征文字定位
            modal_xpaths = [
                "//div[contains(@class,'so-modal-confirm') and .//*[contains(text(),'清空已填写')]]//button[contains(@class,'so-button-default')]",
                "//div[contains(@class,'so-modal-confirm') and .//*[contains(text(),'SKC')]]//button[contains(@class,'so-button-default')]",
                "//div[contains(@class,'so-modal-confirm')]//button[@id[contains(.,'cancel')]]",
                "//div[contains(@class,'so-modal-confirm') and .//*[contains(text(),'切换后')]]//button[.//span[normalize-space(text())='取消']]",
                "//div[contains(@class,'so-card') and .//*[contains(text(),'清空已填写')]]//button[.//span[normalize-space(text())='取消']]",
            ]
            for xp in modal_xpaths:
                try:
                    btns = driver.find_elements(By.XPATH, xp)
                    for btn in btns:
                        if btn.is_displayed():
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", btn)
                            time.sleep(0.1)
                            try:
                                btn.click()
                            except Exception:
                                driver.execute_script("arguments[0].click();", btn)
                            self.log("[OK] 检测到'切换清空'确认弹窗，已点击取消")
                            time.sleep(0.5)
                            return True
                except Exception:
                    continue
        except Exception as e:
            self.log("[DEBUG] _dismiss_switch_confirm_modal 异常: {}".format(str(e)[:60]))
        return False

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
            """
            导航到商品发布页面。
            优先检查是否已在发布页面，避免重复导航。
            """
            current_url = driver.current_url
            # 检查是否已在发布页面
            if "spmc" in current_url and "followsales" in current_url and "commodities" in current_url:
                self.log("已在商品发布页面，跳过导航")
                return True
            
            # 直接导航到发布页面
            self.log("直接导航到商品发布页面...")
            try:
                driver.get(self.PUBLISH_URL)
                time.sleep(3)
                cur = driver.current_url
                if "spmc" in cur and "followsales" in cur:
                    self.log("已直接打开商品发布页")
                    return True
            except Exception as e:
                self.log("直接导航失败: {}".format(e))
            
            # 备用方案：从首页导航
            self.log("尝试从首页导航...")
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
        # Step7: 点击发布商品按鈕
        self.log("点击发布商品...")
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
            try:
                for _btn in driver.find_elements(By.XPATH, _xp):
                    try:
                        if _btn.is_displayed() and _btn.is_enabled():
                            driver.execute_script("arguments[0].scrollIntoView({block:'center'});", _btn)
                            time.sleep(0.5)
                            driver.execute_script("arguments[0].click();", _btn)
                            self.log("[OK] 已点击发布商品按鈕")
                            submitted = True
                            break
                    except Exception:
                        continue
            except Exception:
                continue
            if submitted:
                break
        if not submitted:
            raise Exception("未找到发布按鈕，请手动完成发布")
        # Step8: 等待确认弹窗，点击"一件翻译并发布"
        self.log("等待确认弹窗（一件翻译并发布）...")
        _confirm_clicked = False
        _deadline = time.time() + 15
        while time.time() < _deadline:
            try:
                _dlg_xpaths = [
                    "//button[.//span[contains(text(),'一件翻译并发布')]]",
                    "//button[contains(text(),'一件翻译并发布')]",
                    "//span[contains(text(),'一件翻译并发布')]/parent::button",
                    "//*[contains(@class,'so-modal') or contains(@class,'dialog')]//button[.//span[contains(text(),'翻译')]]",
                ]
                for _xp in _dlg_xpaths:
                    try:
                        for _btn in driver.find_elements(By.XPATH, _xp):
                            if _btn.is_displayed() and _btn.is_enabled():
                                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", _btn)
                                time.sleep(0.3)
                                driver.execute_script("arguments[0].click();", _btn)
                                self.log("[OK] 已点击一件翻译并发布")
                                _confirm_clicked = True
                                break
                    except Exception:
                        continue
                    if _confirm_clicked:
                        break
            except Exception:
                pass
            if _confirm_clicked:
                break
            time.sleep(0.5)
        if not _confirm_clicked:
            self.log("[WARN] 未找到'一件翻译并发布'按鈕，弹窗可能未出现或已自动关闭")
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
                        _os.remove(img_path)
                    except Exception:
                        pass
                except Exception as e:
                    self.log("第 {} 张细节图上传失败: {}".format(idx + 1, str(e)[:80]))
                    continue
            self.log("细节图上传完成")
        except Exception as e:
            self.log("细节图上传过程出错: {}".format(str(e)[:80]))
