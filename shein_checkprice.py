# -*- coding: utf-8 -*-
"""SHEIN 议价入口自动化：打开商品列表并抓取「待确认」议价数据。"""

import re
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


def _trim_text(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


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
            if (driver.execute_script("return document.readyState") or "") == "complete":
                return True
        except Exception:
            pass
        time.sleep(0.3)
    return False


def _js_click(driver, element):
    try:
        driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
        time.sleep(0.15)
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


def _click_pending_filter_button(driver, log, timeout=8):
    """点击“待确认”筛选按钮（该按钮用于切换显示数据，不是表格列）。"""
    if By is None:
        return False

    xpaths = [
        # soui tabs（你给的页面结构）
        "//*[contains(@class,'soui-tabs-tab') and contains(normalize-space(.), '待确认')]",
        "//*[contains(@class,'ant-tabs-tab') and contains(normalize-space(.), '待确认')]",
        "//*[@role='tab' and contains(normalize-space(.), '待确认')]",
        "//button[contains(normalize-space(.), '待确认')]",
        "//*[contains(@class,'cursor-pointer') and contains(normalize-space(.), '待确认')]",
    ]

    end = time.time() + timeout
    while time.time() < end:
        for xp in xpaths:
            try:
                els = driver.find_elements(By.XPATH, xp)
            except Exception:
                els = []
            for el in els:
                try:
                    if not el.is_displayed():
                        continue
                except Exception:
                    continue
                if _js_click(driver, el):
                    log("议价流程：已点击“待确认”筛选按钮")
                    time.sleep(0.6)
                    return True
        time.sleep(0.4)

    # JS兜底：只点“待确认”tab，避免点到提示文案“价格调整待确认”
    try:
        ok = driver.execute_script(
            r"""
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
const cands = Array.from(document.querySelectorAll('.soui-tabs-tab,[role="tab"],button,div'))
  .filter(visible)
  .filter(el => {
    const t = clean(el.innerText || '');
    return /^待确认(\s+\d+)?$/.test(t) || t.startsWith('待确认 ');
  });
for (const el of cands) {
  const ctx = (el.closest('.soui-tabs,.ant-tabs,section,div') || el);
  const allText = clean((ctx.innerText || '').slice(0, 3000));
  if (!allText.includes('全部') || !allText.includes('待确认')) continue;
  el.click();
  return true;
}
return false;
"""
        )
        if ok:
            log("议价流程：已通过JS兜底点击“待确认”筛选按钮")
            time.sleep(0.6)
            return True
    except Exception:
        pass

    return False


def _dismiss_user_guide_next_buttons(driver, log, timeout=10, interval=1):
    if By is None:
        return 0

    start = time.time()
    clicked_total = 0

    while time.time() - start < timeout:
        clicked_in_poll = 0

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

            def _first_clickable(xpaths):
                for xp in xpaths:
                    try:
                        found = driver.find_elements(By.XPATH, xp)
                    except Exception:
                        found = []
                    for btn in found:
                        try:
                            if btn.is_displayed() and btn.is_enabled():
                                return btn
                        except Exception:
                            continue
                return None

            target = _first_clickable(next_xpaths)
            label = "下一步"
            if target is None:
                target = _first_clickable(exit_xpaths)
                label = "退出引导"
            if target is None:
                break

            if _js_click(driver, target):
                clicked_total += 1
                clicked_in_poll += 1
                log("议价流程：已点击引导弹窗「{}」".format(label))
                time.sleep(0.2)
            else:
                break

        if clicked_in_poll == 0:
            time.sleep(interval)

    if clicked_total > 0:
        log("议价流程：共关闭 {} 个引导步骤".format(clicked_total))
    return clicked_total


def dismiss_shein_user_guides(driver, log_cb=None, timeout=10, interval=1):
    log = log_cb or _noop_log
    return _dismiss_user_guide_next_buttons(driver, log, timeout=timeout, interval=interval)


def _extract_candidate_rows(driver):
    """从当前可见区域提取候选行（兼容 modal/drawer/table/list）。"""
    script = """
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  if (el.offsetParent !== null) return true;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  return !!st && st.display !== 'none' && st.visibility !== 'hidden' && st.opacity !== '0';
};

const roots = [];
const push = (el) => { if (el && visible(el) && !roots.includes(el)) roots.push(el); };
Array.from(document.querySelectorAll('.ant-modal-wrap,.ant-modal,.ant-drawer-content-wrapper,.ant-drawer,.ant-popover')).forEach(push);
if (!roots.length) push(document.body || document.documentElement);

const rows = [];
const add = (obj) => {
  if (!obj) return;
  const t = clean(obj._rowText || '');
  if (!t) return;
  rows.push(obj);
};

for (const root of roots) {
  const tables = Array.from(root.querySelectorAll('.ant-table, table'));
  for (const tb of tables) {
    const headers = Array.from(tb.querySelectorAll('thead th')).map(th => clean(th.innerText));
    const trs = Array.from(tb.querySelectorAll('tbody tr, .ant-table-tbody > tr, tr.ant-table-row'));
    for (const tr of trs) {
      const tds = Array.from(tr.querySelectorAll('td'));
      const obj = {};
      if (tds.length) {
        const cells = tds.map(td => clean(td.innerText));
        cells.forEach((v, i) => { obj[headers[i] || ('col_' + i)] = v; });
      }
      obj._rowText = clean(tr.innerText || '');
      add(obj);
    }
  }

  const items = Array.from(root.querySelectorAll('.ant-list-item, .ant-descriptions-row, .ant-row, li, [class*="row"], [class*="item"]'));
  for (const el of items) {
    if (!visible(el)) continue;
    const text = clean(el.innerText || '');
    if (!text || text.length < 6) continue;
    const obj = {_rowText: text};
    const lines = text.split(/\n+/).map(clean).filter(Boolean);
    lines.forEach((line, idx) => {
      const m = line.match(/^([^:：]{1,18})[:：]\s*(.+)$/);
      if (m) obj[m[1]] = clean(m[2]);
      else obj['line_' + idx] = line;
    });
    add(obj);
  }
}

const seen = new Set();
const uniq = [];
for (const r of rows) {
  const k = clean(r._rowText || '');
  if (!k || seen.has(k)) continue;
  seen.add(k);
  uniq.push(r);
}
return uniq;
"""
    try:
        return driver.execute_script(script) or []
    except Exception:
        return []


def _extract_rows_from_todo_drawer_table(driver):
    """
    仅从「待办任务」抽屉中提取表格行，避免全页面误抓。
    返回结构：
    [
      {
        "_row_text": "...",
        "基础信息": "...",
        "建议改价原因": "...",
        "剩余议价次数": "...",
        "SKU信息": "...",
        "平台建议价": "...",
        "状态": "...",
      },
      ...
    ]
    """
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

const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]'))
  .filter(visible);

let root = null;
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) {
  // 兜底：找包含“价格调整待确认，请及时处理”的可见区域
  const all = Array.from(document.querySelectorAll('body *')).filter(visible);
  for (const el of all) {
    const t = clean(el.innerText || '');
    if (t.includes('价格调整待确认，请及时处理')) {
      root = el.closest('.soui-modal-panel,.soui-modal,.merchant-ui-drawer,[class*="drawer"]') || el.closest('section,div') || el;
      break;
    }
  }
}
if (!root) return [];

const headers = Array.from(root.querySelectorAll('thead th')).map(th => clean(th.innerText || ''));
if (!headers.length) return [];

const idx = (name) => headers.findIndex(h => h.includes(name));
const iBase = idx('基础信息');
const iReason = idx('建议改价原因');
const iTimes = idx('剩余议价次数');
const iSku = idx('SKU信息');
const iPrice = headers.findIndex(h => h.includes('平台建议价') || h.includes('建议价'));
const iStatus = idx('状态');

const rows = [];
const trs = Array.from(root.querySelectorAll('tbody tr')).filter(visible);
for (const tr of trs) {
  const tds = Array.from(tr.querySelectorAll('td'));
  if (!tds.length) continue;
  const one = {};
  one['_row_text'] = clean(tr.innerText || '');
  if (iBase >= 0 && tds[iBase]) one['基础信息'] = clean(tds[iBase].innerText || '');
  if (iReason >= 0 && tds[iReason]) one['建议改价原因'] = clean(tds[iReason].innerText || '');
  if (iTimes >= 0 && tds[iTimes]) one['剩余议价次数'] = clean(tds[iTimes].innerText || '');
  if (iSku >= 0 && tds[iSku]) one['SKU信息'] = clean(tds[iSku].innerText || '');
  if (iPrice >= 0 && tds[iPrice]) one['平台建议价'] = clean(tds[iPrice].innerText || '');
  if (iStatus >= 0 && tds[iStatus]) one['状态'] = clean(tds[iStatus].innerText || '');
  rows.push(one);
}
return rows;
"""
    try:
        return driver.execute_script(script) or []
    except Exception:
        return []


def extract_todo_drawer_html(driver):
    """提取当前页面中『待办任务』抽屉HTML，若找不到则返回body HTML。"""
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
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]'))
  .filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) return d.outerHTML || '';
}
return (document.body && document.body.outerHTML) ? document.body.outerHTML : '';
"""
    try:
        return driver.execute_script(script) or ""
    except Exception:
        return ""


def _pick_value(row_obj, keys):
    # 1) 精确 key
    for k in keys:
        v = row_obj.get(k)
        if v:
            return _trim_text(v)

    # 2) 包含 key 的列名
    for rk, rv in row_obj.items():
        rks = _trim_text(rk)
        if not rks:
            continue
        for k in keys:
            if k in rks:
                vv = _trim_text(rv)
                if vv:
                    return vv

    # 3) 整行按“字段: 值”提取
    row_text = _trim_text(row_obj.get("_rowText", ""))
    if row_text:
        for k in keys:
            m = re.search(r"{}\s*[:：]\s*([^，。,;；\n]+)".format(re.escape(k)), row_text)
            if m:
                return _trim_text(m.group(1))

    return ""


def _normalize_bargain_row(row_obj):
    supplier_no = _pick_value(row_obj, ["供方货号", "供方货号/颜色", "商家货号", "货号"])
    if not supplier_no:
        basic_info = _pick_value(row_obj, ["基础信息"])
        if basic_info:
            m = re.search(r"供方货号\s*[:：]\s*([^\s\n，。,;；]+)", basic_info)
            if m:
                supplier_no = _trim_text(m.group(1))
    if not supplier_no:
        row_text = _trim_text(row_obj.get("_row_text", ""))
        m = re.search(r"供方货号\s*[:：]\s*([^\s\n，。,;；]+)", row_text)
        if m:
            supplier_no = _trim_text(m.group(1))
    supplier_no = re.sub(r"^(供方货号|货号)\s*[:：]\s*", "", supplier_no)
    supplier_no = re.sub(r"^XYZ-", "", supplier_no, flags=re.I)

    reason = _pick_value(row_obj, ["建议改价原因", "改价原因", "建议原因"])
    remaining_times = _pick_value(row_obj, ["剩余议价次数", "可议价次数", "剩余次数"])
    raw_sku_info = _pick_value(row_obj, ["SKU信息", "SKU", "规格", "颜色/尺码", "颜色尺码"])
    if not raw_sku_info:
        row_text_for_sku = _trim_text(row_obj.get("_row_text", ""))
        m = re.search(r"SKU\s*[:：]\s*([^\s\n，。,;；]+)", row_text_for_sku, flags=re.I)
        if m:
            raw_sku_info = _trim_text(m.group(1))

    # 解析次规格（优先从 SKU 信息单元格提取）
    sub_spec = ""
    for src in (raw_sku_info, _trim_text(row_obj.get("_row_text", ""))):
        if not src:
            continue
        m_sub = re.search(r"次规格\s*[:：]\s*([^\n，。,;；]+)", src)
        if m_sub:
            sub_spec = _trim_text(m_sub.group(1))
            break

    # SKU信息只保留SKU值，不带“次规格”
    sku_info = raw_sku_info or ""
    if sku_info:
        m_sku = re.search(r"SKU\s*[:：]\s*([^\s\n，。,;；]+)", sku_info, flags=re.I)
        if m_sku:
            sku_info = _trim_text(m_sku.group(1))
        else:
            sku_info = re.sub(r"^SKU\s*[:：]\s*", "", sku_info, flags=re.I)
            sku_info = re.sub(r"\s*次规格\s*[:：].*$", "", sku_info)
            sku_info = _trim_text(sku_info)

    platform_price = _pick_value(row_obj, ["平台建议价", "建议价", "建议售价", "建议价格"])
    status = _pick_value(row_obj, ["状态"])
    row_text = _trim_text(row_obj.get("_rowText", ""))

    if not status:
        if "待确认" in row_text:
            status = "待确认"
        elif "已确认" in row_text:
            status = "已确认"

    return {
        "supplier_no": supplier_no,
        "reason": reason,
        "remaining_times": remaining_times,
        "sku_info": sku_info,
        "sub_spec": sub_spec,
        "platform_price": platform_price,
        "status": status,
        "_row_text": row_text,
    }


def _wait_fetch_pending_bargain_rows(driver, log, timeout=14, interval=0.7, assume_pending=False):
    end = time.time() + timeout
    max_seen = 0

    while time.time() < end:
        raw_rows = _extract_rows_from_todo_drawer_table(driver)
        if not raw_rows:
            # 兜底：旧逻辑
            raw_rows = _extract_candidate_rows(driver)
        if len(raw_rows) > max_seen:
            max_seen = len(raw_rows)
            log("议价流程：检测到候选行 {} 条".format(max_seen))

        results = []
        for r in raw_rows:
            one = _normalize_bargain_row(r)
            s = one.get("status", "")
            rt = one.get("_row_text", "")

            if not assume_pending and s and ("待确认" not in s):
                continue
            if (not assume_pending) and (not s) and ("待确认" not in rt):
                continue

            if not any([one.get("supplier_no"), one.get("reason"), one.get("sku_info"), one.get("platform_price")]):
                continue

            results.append({
                "supplier_no": one.get("supplier_no", ""),
                "reason": one.get("reason", ""),
                "remaining_times": one.get("remaining_times", ""),
                "sku_info": one.get("sku_info", ""),
                "sub_spec": one.get("sub_spec", ""),
                "platform_price": one.get("platform_price", ""),
            })

        if results:
            return results
        time.sleep(interval)

    return []


def open_shein_suggest_price_popup(publisher=None, account="", log_cb=None, headless=False):
    """打开 SHEIN 商品列表页并点击「价格调整待确认，请及时处理」。"""
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

    _dismiss_user_guide_next_buttons(driver, log, timeout=5, interval=1)

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


def fetch_shein_pending_bargain_rows(publisher=None, account="", log_cb=None, headless=False):
    """打开议价入口并抓取弹窗中“待确认”行。"""
    log = log_cb or _noop_log
    ok, msg, pub = open_shein_suggest_price_popup(
        publisher=publisher,
        account=account,
        log_cb=log,
        headless=headless,
    )
    if not ok:
        return False, msg, pub, []

    driver = getattr(pub, "driver", None)
    if driver is None or not _is_driver_alive(driver):
        return False, "议价入口已打开，但浏览器连接中断", pub, []

    _dismiss_user_guide_next_buttons(driver, log, timeout=4, interval=0.8)

    clicked_pending = _click_pending_filter_button(driver, log, timeout=8)
    rows = _wait_fetch_pending_bargain_rows(
        driver,
        log,
        timeout=14,
        interval=0.7,
        assume_pending=clicked_pending,
    )
    if not rows:
        return False, "已进入议价入口，但未抓到“待确认”数据；请确认已切换到“待确认”筛选并且表格中有记录", pub, []

    log("议价流程：抓取到待确认记录 {} 条".format(len(rows)))
    return True, "已抓取“待确认”记录 {} 条".format(len(rows)), pub, rows
