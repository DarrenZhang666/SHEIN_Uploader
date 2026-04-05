# -*- coding: utf-8 -*-
"""SHEIN 议价入口自动化：打开商品列表并点击「价格调整待确认，请及时处理」。"""

import time

from shein_uploader import SheinPublisher

try:
    from selenium.webdriver.common.by import By
except Exception:
    By = None

SHEIN_LIST_URL = "https://sso.geiwohuo.com/#/spmp/commdities/list"
TODO_TEXT = "价格调整待确认，请及时处理"


def _noop_log(_msg):
    pass


def _is_driver_alive(driver):
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def _wait_ready(driver, timeout=15):
    end = time.time() + timeout
    while time.time() < end:
        try:
            state = driver.execute_script("return document.readyState") or ""
            if state == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _js_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.2)
    except Exception:
        pass
    try:
        element.click()
        return True
    except Exception:
        pass
    try:
        driver.execute_script("arguments[0].click();", element)
        return True
    except Exception:
        return False


def _click_todo_entrance(driver):
    if By is None:
        return False

    xpaths = [
        "//*[@data-display-name='spmp-commdities-list-search-todo']//*[contains(normalize-space(.), '价格调整待确认，请及时处理')]",
        "//*[contains(@class,'cursor-pointer') and contains(normalize-space(.), '价格调整待确认，请及时处理')]",
        "//*[contains(normalize-space(.), '价格调整待确认，请及时处理')]",
    ]

    for xp in xpaths:
        try:
            elements = driver.find_elements(By.XPATH, xp)
        except Exception:
            elements = []
        for el in elements:
            try:
                if not el.is_displayed():
                    continue
            except Exception:
                continue
            if _js_click(driver, el):
                return True

            # 尝试点击可点击父级
            node = el
            for _ in range(4):
                try:
                    node = node.find_element(By.XPATH, "..")
                except Exception:
                    break
                try:
                    cls = (node.get_attribute("class") or "").lower()
                    role = (node.get_attribute("role") or "").lower()
                    if "cursor-pointer" in cls or role == "button" or node.tag_name in ("button", "a"):
                        if _js_click(driver, node):
                            return True
                except Exception:
                    continue

    return False


def _dismiss_user_guide_next_buttons(driver, log, timeout=10, interval=1):
    """10 秒内每隔 1 秒检查并连续点击引导弹窗「下一步 / 退出引导」。"""
    if By is None:
        return 0

    start = time.time()
    clicked_total = 0

    while time.time() - start < timeout:
        clicked_in_this_poll = 0

        while True:
            next_xpaths = [
                "//div[contains(@class,'__floater__open')]//button[(.//span[normalize-space(text())='下一步']) or normalize-space(text())='下一步']",
                "//div[contains(@class,'shein-components_userguidepro_tooltip')]//button[(.//span[normalize-space(text())='下一步']) or normalize-space(text())='下一步']",
                "//button[@title='Next' or @aria-label='Next' or @data-action='primary'][(.//span[normalize-space(text())='下一步']) or normalize-space(text())='下一步']",
            ]
            exit_xpaths = [
                "//div[contains(@class,'__floater__open')]//button[(.//span[normalize-space(text())='退出引导']) or normalize-space(text())='退出引导']",
                "//div[contains(@class,'shein-components_userguidepro_tooltip')]//button[(.//span[normalize-space(text())='退出引导']) or normalize-space(text())='退出引导']",
                "//button[(.//span[normalize-space(text())='退出引导']) or normalize-space(text())='退出引导']",
            ]

            def _pick_first_clickable(xpaths):
                candidates = []
                for xp in xpaths:
                    try:
                        found = driver.find_elements(By.XPATH, xp)
                    except Exception:
                        found = []
                    for btn in found:
                        if btn not in candidates:
                            candidates.append(btn)
                for btn in candidates:
                    try:
                        if btn.is_displayed() and btn.is_enabled():
                            return btn
                    except Exception:
                        continue
                return None

            target = _pick_first_clickable(next_xpaths)
            label = "下一步"
            if target is None:
                target = _pick_first_clickable(exit_xpaths)
                label = "退出引导"

            if target is None:
                break

            if _js_click(driver, target):
                clicked_total += 1
                clicked_in_this_poll += 1
                log("议价流程：已点击引导弹窗「{}」".format(label))
                time.sleep(0.25)
            else:
                break

        if clicked_in_this_poll == 0:
            time.sleep(interval)

    if clicked_total > 0:
        log("议价流程：共关闭 {} 个引导步骤".format(clicked_total))
    return clicked_total


def dismiss_shein_user_guides(driver, log_cb=None, timeout=10, interval=1):
    """公共方法：关闭 SHEIN 引导弹窗（支持「下一步」「退出引导」）。"""
    log = log_cb or _noop_log
    return _dismiss_user_guide_next_buttons(driver, log, timeout=timeout, interval=interval)


def open_shein_suggest_price_popup(publisher=None, account="", log_cb=None, headless=False):
    """
    打开 SHEIN 商品列表页并点击「价格调整待确认，请及时处理」。

    Returns:
        (ok, message, publisher)
    """
    log = log_cb or _noop_log

    pub = publisher
    if pub is None or (not pub.is_alive()):
        pub = SheinPublisher(log_cb=log)
        pub.start_browser(account=account or "default", headless=headless, force_new=False)

    driver = getattr(pub, "driver", None)
    if driver is None or not _is_driver_alive(driver):
        return False, "浏览器未就绪，请先登录 SHEIN", pub

    log("议价流程：打开商品列表页面")
    driver.get(SHEIN_LIST_URL)
    _wait_ready(driver, timeout=15)
    time.sleep(1.2)

    current_url = (driver.current_url or "").lower()
    if "login" in current_url:
        return False, "当前未登录 SHEIN，请先点击“登录 SHEIN”", pub

    _dismiss_user_guide_next_buttons(driver, log, timeout=10, interval=1)

    for _ in range(10):
        if _click_todo_entrance(driver):
            log("议价流程：已点击“价格调整待确认，请及时处理”")
            time.sleep(1.0)
            return True, "已打开议价入口，请在页面弹窗中查看建议价格", pub
        time.sleep(0.5)

    log("议价流程：首次点击入口失败，尝试再次清理引导并重试")
    _dismiss_user_guide_next_buttons(driver, log, timeout=6, interval=1)

    for _ in range(8):
        if _click_todo_entrance(driver):
            log("议价流程：重试后已点击“价格调整待确认，请及时处理”")
            time.sleep(1.0)
            return True, "已打开议价入口，请在页面弹窗中查看建议价格", pub
        time.sleep(0.5)

    return False, "未找到“价格调整待确认，请及时处理”入口，请确认页面已加载", pub
