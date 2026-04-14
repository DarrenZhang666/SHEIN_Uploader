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


def _should_stop(should_stop):
    if should_stop is None:
        return False
    try:
        return bool(should_stop())
    except Exception:
        return False


def _trim_text(v):
    return re.sub(r"\s+", " ", str(v or "")).strip()


def _is_driver_alive(driver):
    try:
        _ = driver.current_url
        return True
    except Exception:
        return False


def _wait_ready(driver, timeout=15, should_stop=None):
    end = time.time() + timeout
    while time.time() < end:
        if _should_stop(should_stop):
            return False
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


def _click_pending_filter_button(driver, log, timeout=8, should_stop=None):
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
        if _should_stop(should_stop):
            return False
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
                    time.sleep(0.2)
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
            time.sleep(0.2)
            return True
    except Exception:
        pass

    return False


def _dismiss_user_guide_next_buttons(driver, log, timeout=10, interval=1):
    if By is None:
        return 0

    start = time.time()
    clicked_total = 0
    no_click_polls = 0

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
            no_click_polls += 1
            # 无引导时尽快退出，避免白等满 timeout
            if no_click_polls >= 2:
                break
            time.sleep(min(interval, 0.4))
        else:
            no_click_polls = 0

    if clicked_total > 0:
        log("议价流程：共关闭 {} 个引导步骤".format(clicked_total))
    return clicked_total


def dismiss_shein_user_guides(driver, log_cb=None, timeout=10, interval=1):
    log = log_cb or _noop_log
    return _dismiss_user_guide_next_buttons(driver, log, timeout=timeout, interval=interval)


def _wait_todo_drawer_visible(driver, timeout=2.5, should_stop=None):
    end = time.time() + timeout
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
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) return true;
}
return false;
"""
    while time.time() < end:
        if _should_stop(should_stop):
            return False
        try:
            if bool(driver.execute_script(script)):
                return True
        except Exception:
            pass
        time.sleep(0.2)
    return False


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
        "SKU信息": "...",
        "平台建议价": "...",
        "状态": "...",
        "操作": "...",
        "_action_labels": "...",
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
const iSku = idx('SKU信息');
const iPrice = headers.findIndex(h => h.includes('平台建议价') || h.includes('建议价'));
const iStatus = idx('状态');
const iAction = idx('操作');

const rows = [];
const trs = Array.from(root.querySelectorAll('tbody tr')).filter(visible);
for (const tr of trs) {
  const tds = Array.from(tr.querySelectorAll('td'));
  if (!tds.length) continue;
  const one = {};
  one['_row_text'] = clean(tr.innerText || '');
  if (iBase >= 0 && tds[iBase]) one['基础信息'] = clean(tds[iBase].innerText || '');
  if (iReason >= 0 && tds[iReason]) one['建议改价原因'] = clean(tds[iReason].innerText || '');
  if (iSku >= 0 && tds[iSku]) one['SKU信息'] = clean(tds[iSku].innerText || '');
  if (iPrice >= 0 && tds[iPrice]) one['平台建议价'] = clean(tds[iPrice].innerText || '');
  if (iStatus >= 0 && tds[iStatus]) one['状态'] = clean(tds[iStatus].innerText || '');
  if (iAction >= 0 && tds[iAction]) {
    const td = tds[iAction];
    one['操作'] = clean(td.innerText || '');
    const labels = Array.from(td.querySelectorAll('button,button span,[role="button"]'))
      .map(n => clean(n.innerText || ''))
      .filter(Boolean);
    const uniq = [];
    const seen = new Set();
    for (const lb of labels) {
      if (seen.has(lb)) continue;
      seen.add(lb);
      uniq.push(lb);
    }
    one['_action_labels'] = uniq.join('|');
  }
  rows.push(one);
}
return rows;
"""
    try:
        return driver.execute_script(script) or []
    except Exception:
        return []


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
    row_text = _trim_text(row_obj.get("_rowText", "") or row_obj.get("_row_text", ""))
    if row_text:
        for k in keys:
            m = re.search(r"{}\s*[:：]\s*([^，。,;；\n]+)".format(re.escape(k)), row_text)
            if m:
                return _trim_text(m.group(1))

    return ""


def _normalize_bargain_row(row_obj):
    basic_info = _pick_value(row_obj, ["基础信息"])
    supplier_no_raw = _pick_value(row_obj, ["供方货号", "供方货号/颜色", "商家货号", "货号"])
    if not supplier_no_raw:
        if basic_info:
            m = re.search(r"供方货号\s*[:：]\s*([^\s\n，。,;；]+)", basic_info)
            if m:
                supplier_no_raw = _trim_text(m.group(1))
    if not supplier_no_raw:
        row_text = _trim_text(row_obj.get("_row_text", ""))
        m = re.search(r"供方货号\s*[:：]\s*([^\s\n，。,;；]+)", row_text)
        if m:
            supplier_no_raw = _trim_text(m.group(1))
    supplier_no_raw = re.sub(r"^(供方货号|货号)\s*[:：]\s*", "", supplier_no_raw)
    supplier_no = ""
    m_asin = re.search(r"\b(B[A-Z0-9]{9})\b", str(supplier_no_raw or "").upper())
    if m_asin:
        supplier_no = _trim_text(m_asin.group(1))
    if not supplier_no:
        supplier_no = supplier_no_raw
        supplier_no = re.sub(r"^XYZ-", "", supplier_no, flags=re.I)
        supplier_no = _trim_text(supplier_no)

    reason = _pick_value(row_obj, ["建议改价原因", "改价原因", "建议原因"])
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
    operation_text = _pick_value(row_obj, ["操作"]) or _trim_text(row_obj.get("操作", ""))
    action_labels_raw = _trim_text(row_obj.get("_action_labels", ""))
    row_text = _trim_text(row_obj.get("_rowText", ""))
    if not row_text:
        row_text = _trim_text(row_obj.get("_row_text", ""))

    bargain_no = ""
    skc = ""
    spu = ""
    for src in (basic_info, row_text):
        if not src:
            continue
        if not bargain_no:
            m = re.search(r"议价单号\s*[:：]\s*([^\s\n，。,;；]+)", src)
            if m:
                bargain_no = _trim_text(m.group(1))
        if not skc:
            m = re.search(r"SKC\s*[:：]\s*([^\s\n，。,;；]+)", src, flags=re.I)
            if m:
                skc = _trim_text(m.group(1))
        if not spu:
            m = re.search(r"SPU\s*[:：]\s*([^\s\n，。,;；]+)", src, flags=re.I)
            if m:
                spu = _trim_text(m.group(1))

    actions = []
    if action_labels_raw:
        actions = [_trim_text(x) for x in action_labels_raw.split("|") if _trim_text(x)]
    if not actions and operation_text:
        for lb in ("同意平台建议价", "重新报价", "拒绝，放弃上新"):
            if lb in operation_text:
                actions.append(lb)
    if not actions:
        actions = ["同意平台建议价", "重新报价", "拒绝，放弃上新"]

    if not status:
        if "待确认" in row_text:
            status = "待确认"
        elif "已确认" in row_text:
            status = "已确认"

    return {
        "supplier_no_raw": supplier_no_raw,
        "supplier_no": supplier_no,
        "reason": reason,
        "sku_info": sku_info,
        "sub_spec": sub_spec,
        "platform_price": platform_price,
        "status": status,
        "bargain_no": bargain_no,
        "skc": skc,
        "spu": spu,
        "operation_text": operation_text,
        "actions": actions,
        "_row_text": row_text,
    }


def _wait_fetch_pending_bargain_rows(driver, log, timeout=14, interval=0.7, assume_pending=False, xyz_only=True, should_stop=None):
    end = time.time() + timeout
    max_seen = 0

    while time.time() < end:
        if _should_stop(should_stop):
            return []
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

            raw_no = _trim_text(one.get("supplier_no_raw", ""))
            if xyz_only and (not raw_no.upper().startswith("XYZ-")):
                continue

            results.append({
                "supplier_no_raw": one.get("supplier_no_raw", ""),
                "supplier_no": one.get("supplier_no", ""),
                "reason": one.get("reason", ""),
                "sku_info": one.get("sku_info", ""),
                "sub_spec": one.get("sub_spec", ""),
                "platform_price": one.get("platform_price", ""),
                "status": one.get("status", ""),
                "bargain_no": one.get("bargain_no", ""),
                "skc": one.get("skc", ""),
                "spu": one.get("spu", ""),
                "operation_text": one.get("operation_text", ""),
                "actions": one.get("actions", []),
                "_row_text": one.get("_row_text", ""),
            })

        if results:
            return results
        time.sleep(interval)

    return []


def _get_todo_pagination_state(driver):
    """读取待办任务抽屉中的分页状态。"""
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
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return {page: 1, has_prev: false, has_next: false, total_pages: 1, total_items: 0, page_size: 10};

let page = 1;
const activeBtn = root.querySelector('.soui-pagination-buttons .soui-button-primary');
if (activeBtn) {
  const n = parseInt(clean(activeBtn.innerText || ''), 10);
  if (!isNaN(n)) page = n;
}

let totalItems = 0;
const totalEl = root.querySelector('.soui-pagination-section span');
if (totalEl) {
  const m = clean(totalEl.innerText || '').match(/共\s*(\d+)\s*条/);
  if (m) totalItems = parseInt(m[1], 10) || 0;
}

let pageSize = 10;
const sizeEl = root.querySelector('.soui-pagination-size-list .soui-select-ellipsis');
if (sizeEl) {
  const m = clean(sizeEl.innerText || '').match(/(\d+)\s*\/\s*页/);
  if (m) pageSize = parseInt(m[1], 10) || 10;
}
const totalPages = totalItems > 0 ? Math.max(1, Math.ceil(totalItems / pageSize)) : 1;

let hasPrev = false;
let hasNext = false;
const btns = Array.from(root.querySelectorAll('.soui-pagination-buttons button'));
if (btns.length >= 2) {
  const prevBtn = btns[0];
  const prevCls = (prevBtn.className || '').toString();
  hasPrev = !prevCls.includes('soui-button-disabled') && !prevBtn.disabled;
  const nextBtn = btns[btns.length - 1];
  const cls = (nextBtn.className || '').toString();
  hasNext = !cls.includes('soui-button-disabled') && !nextBtn.disabled;
}
if (!hasPrev && page > 1) hasPrev = true;
if (!hasNext && page < totalPages) hasNext = true;
return {page, has_prev: hasPrev, has_next: hasNext, total_pages: totalPages, total_items: totalItems, page_size: pageSize};
"""
    try:
        data = driver.execute_script(script) or {}
        return {
            "page": int(data.get("page", 1) or 1),
            "has_prev": bool(data.get("has_prev", False)),
            "has_next": bool(data.get("has_next", False)),
            "total_pages": int(data.get("total_pages", 1) or 1),
            "total_items": int(data.get("total_items", 0) or 0),
            "page_size": int(data.get("page_size", 10) or 10),
        }
    except Exception:
        return {"page": 1, "has_prev": False, "has_next": False, "total_pages": 1, "total_items": 0, "page_size": 10}


def _ensure_todo_page_size(driver, log, target_size=50, timeout=8, should_stop=None, discover_timeout=10, probe_interval=1):
    """将待办任务抽屉分页切换到目标每页条数（默认 50）。"""
    target = int(target_size or 50)
    if target <= 0:
        return False

    before = _get_todo_pagination_state(driver)
    before_size = int(before.get("page_size", 10) or 10)
    before_sig = _get_todo_table_signature(driver)
    if before_size == target:
        log("议价流程：分页已是 {} / 页".format(target))
        return True

    discover_script = r"""
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return {ok: false, reason: 'no_root', text: ''};
const sizeWrap = root.querySelector('.soui-pagination-size-list');
if (!sizeWrap || !visible(sizeWrap)) return {ok: false, reason: 'no_size_wrap', text: ''};
const sizeEl = sizeWrap.querySelector('.soui-select-ellipsis');
const txt = clean((sizeEl && sizeEl.innerText) || (sizeEl && sizeEl.getAttribute('title')) || '');
return {ok: true, reason: 'ready', text: txt};
"""

    debug_snapshot_script = r"""
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return {ok:false, size_text:'', options:[], reason:'no_root'};
const sizeWrap = root.querySelector('.soui-pagination-size-list');
const sizeEl = sizeWrap ? sizeWrap.querySelector('.soui-select-ellipsis') : null;
const sizeText = clean((sizeEl && sizeEl.innerText) || (sizeWrap && sizeWrap.innerText) || '');
const opts = Array.from(document.querySelectorAll('.soui-select-option,[title]'))
  .filter(visible)
  .map(el => clean(el.innerText || el.getAttribute('title') || ''))
  .filter(Boolean)
  .slice(0, 12);
return {ok:true, size_text:sizeText, options:opts, reason:'ok'};
"""

    open_select_script = r"""
const target = parseInt(arguments[0], 10) || 50;
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
const clickEl = (el) => {
  if (!el) return false;
  try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (_) {}
  try { el.click(); return true; } catch (_) {}
  try {
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    return true;
  } catch (_) {}
  try {
    const r = el.getBoundingClientRect();
    const x = Math.floor(r.left + r.width / 2);
    const y = Math.floor(r.top + r.height / 2);
    const topEl = document.elementFromPoint(x, y);
    if (topEl) {
      topEl.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: x, clientY: y }));
      topEl.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: x, clientY: y }));
      topEl.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: x, clientY: y }));
      return true;
    }
  } catch (_) {}
  return false;
};
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return {ok: false, reason: 'no_root'};

const sizeWrap = root.querySelector('.soui-pagination-size-list');
if (!sizeWrap) return {ok: false, reason: 'no_size_wrap'};

const triggers = [
  sizeWrap.querySelector('.soui-select-result-wrapper'),
  sizeWrap.querySelector('.soui-select-wrapper-padding-box'),
  sizeWrap.querySelector('.soui-select-ellipsis'),
  sizeWrap.querySelector('.soui-select-icon-wrapper'),
  sizeWrap.querySelector('.soui-select-arrow-icon'),
  sizeWrap.querySelector('.soui-select'),
  sizeWrap
].filter(Boolean);
for (const t of triggers) {
  if (clickEl(t)) return {ok: true, changed: true, reason: 'opened'};
}
return {ok: false, reason: 'open_failed'};
"""

    click_option_script = r"""
const target = parseInt(arguments[0], 10) || 50;
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
const clickEl = (el) => {
  if (!el) return false;
  try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (_) {}
  try { el.click(); return true; } catch (_) {}
  try {
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    return true;
  } catch (_) {}
  try {
    const r = el.getBoundingClientRect();
    const x = Math.floor(r.left + r.width / 2);
    const y = Math.floor(r.top + r.height / 2);
    const topEl = document.elementFromPoint(x, y);
    if (topEl) {
      topEl.dispatchEvent(new MouseEvent('mousedown', { bubbles: true, clientX: x, clientY: y }));
      topEl.dispatchEvent(new MouseEvent('mouseup', { bubbles: true, clientX: x, clientY: y }));
      topEl.dispatchEvent(new MouseEvent('click', { bubbles: true, clientX: x, clientY: y }));
      return true;
    }
  } catch (_) {}
  return false;
};
const containers = Array.from(document.querySelectorAll('.soui-select-picker-wrapper,.soui-select-list,body'));
let candidates = [];
for (const c of containers) {
  const part = Array.from(c.querySelectorAll('li.soui-select-option,.soui-select-option,[title]')).filter(visible);
  candidates = candidates.concat(part);
}
// 去重
candidates = Array.from(new Set(candidates));
let targetOpt = null;
for (const el of candidates) {
  const txt = clean(el.innerText || el.getAttribute('title') || '');
  if (txt.includes(String(target)) && (txt.includes('/ 页') || txt.includes('/页'))) {
    targetOpt = el;
    break;
  }
}
if (!targetOpt) {
  const sample = candidates.slice(0, 8).map(el => clean(el.innerText || el.getAttribute('title') || '')).filter(Boolean);
  return {ok: false, reason: 'option_not_found', sample};
}
if (!clickEl(targetOpt)) return {ok: false, reason: 'option_click_failed'};
return {ok: true, reason: 'option_clicked'};
"""
    max_attempts = 3
    for attempt in range(1, max_attempts + 1):
        if _should_stop(should_stop):
            return False

        # 先最多等待 10 秒，每 1 秒轮询一次，优先等到“10 / 页”再切
        end_discover = time.time() + max(1.0, float(discover_timeout))
        found_text = ""
        saw_ten = False
        while time.time() < end_discover:
            if _should_stop(should_stop):
                return False
            try:
                probe = driver.execute_script(discover_script) or {}
            except Exception:
                probe = {}
            txt = _trim_text(probe.get("text", ""))
            found_text = txt or found_text
            if txt:
                m = re.search(r"(\d+)\s*/\s*页", txt)
                cur_txt_size = int(m.group(1)) if m else 0
                if cur_txt_size == target:
                    # 仅以前端文本不做最终判定，必须以分页状态读取到的 page_size 为准
                    st_now = _get_todo_pagination_state(driver)
                    if int(st_now.get("page_size", 10) or 10) == target:
                        log("议价流程：分页已是 {} / 页".format(target))
                        return True
                if "10 / 页" in txt or "10/页" in txt:
                    saw_ten = True
                    log("议价流程：检测到分页按钮“{}”，开始切换 {} / 页（第{}次）".format(txt, target, attempt))
                    break
            time.sleep(max(0.2, float(probe_interval)))

        if not saw_ten:
            log("议价流程：第{}次未稳定检测到“10 / 页”，执行兜底切换 {} / 页".format(attempt, target))

        try:
            rs = driver.execute_script(open_select_script, target) or {}
        except Exception:
            rs = {}
        if not rs or not bool(rs.get("ok")):
            log("议价流程：第{}次打开分页下拉失败（{}）".format(attempt, rs.get("reason", "js_error")))
            try:
                snap = driver.execute_script(debug_snapshot_script) or {}
            except Exception:
                snap = {}
            if snap:
                log("议价流程：调试快照 size='{}' options={}".format(
                    _trim_text(snap.get("size_text", "")),
                    (snap.get("options", []) or []),
                ))
            time.sleep(1)
            continue

        changed = bool(rs.get("changed", False))
        if changed:
            log("议价流程：已打开分页下拉，尝试点击 {} / 页".format(target))

        clicked_opt = False
        opt_end = time.time() + 2.5
        opt_reason = "option_not_found"
        while time.time() < opt_end:
            if _should_stop(should_stop):
                return False
            try:
                rs_opt = driver.execute_script(click_option_script, target) or {}
            except Exception:
                rs_opt = {}
            if rs_opt and bool(rs_opt.get("ok")):
                clicked_opt = True
                log("议价流程：已点击 {} / 页选项".format(target))
                break
            opt_reason = rs_opt.get("reason", "option_not_found")
            if rs_opt.get("sample"):
                opt_reason = "{} sample={}".format(opt_reason, rs_opt.get("sample"))
            time.sleep(0.25)
        if not clicked_opt:
            log("议价流程：第{}次点击 {} / 页失败（{}）".format(attempt, target, opt_reason))
            try:
                snap = driver.execute_script(debug_snapshot_script) or {}
            except Exception:
                snap = {}
            if snap:
                log("议价流程：调试快照 size='{}' options={}".format(
                    _trim_text(snap.get("size_text", "")),
                    (snap.get("options", []) or []),
                ))
            time.sleep(1)
            continue

        end = time.time() + max(1.0, float(timeout))
        while time.time() < end:
            if _should_stop(should_stop):
                return False
            st = _get_todo_pagination_state(driver)
            now_size = int(st.get("page_size", 10) or 10)
            if now_size == target:
                now_sig = _get_todo_table_signature(driver)
                if changed and before_sig and now_sig == before_sig:
                    time.sleep(0.3)
                    continue
                log("议价流程：分页已切换为 {} / 页".format(target))
                return True
            time.sleep(0.3)
        log("议价流程：第{}次切换后等待超时，当前 {} / 页".format(attempt, _get_todo_pagination_state(driver).get("page_size", 10)))
        try:
            snap = driver.execute_script(debug_snapshot_script) or {}
        except Exception:
            snap = {}
        if snap:
            log("议价流程：调试快照 size='{}' options={}".format(
                _trim_text(snap.get("size_text", "")),
                (snap.get("options", []) or []),
            ))
        time.sleep(1)

    log("议价流程：切换 {} / 页最终失败，进入降级抓取".format(target))
    return False


def _get_todo_table_signature(driver):
    """读取当前待办任务表格签名，用于判断翻页后数据是否已刷新。"""
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
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return '';
const rows = Array.from(root.querySelectorAll('tbody tr')).filter(visible).slice(0, 8);
const texts = rows.map(r => clean(r.innerText || '')).filter(Boolean);
return texts.join('||');
"""
    try:
        return _trim_text(driver.execute_script(script) or "")
    except Exception:
        return ""


def _click_next_todo_page(driver, log, timeout=8, should_stop=None):
    """点击分页“>”按钮，返回是否成功翻页。"""
    before = _get_todo_pagination_state(driver)
    before_sig = _get_todo_table_signature(driver)
    if not before.get("has_next"):
        return False

    clicked = False
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
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return false;
const btns = Array.from(root.querySelectorAll('.soui-pagination-buttons button'));
if (btns.length < 2) return false;
const nextBtn = btns[btns.length - 1];
const cls = (nextBtn.className || '').toString();
if (nextBtn.disabled || cls.includes('soui-button-disabled')) return false;
nextBtn.click();
return true;
"""
    try:
        clicked = bool(driver.execute_script(script))
    except Exception:
        clicked = False
    if not clicked:
        return False

    end = time.time() + timeout
    page_changed = False
    while time.time() < end:
        if _should_stop(should_stop):
            return False
        now = _get_todo_pagination_state(driver)
        if int(now.get("page", 1)) != int(before.get("page", 1)):
            page_changed = True
            now_sig = _get_todo_table_signature(driver)
            # 页码变化且表格内容签名变化，认为翻页数据已刷新完成
            if now_sig and now_sig != before_sig:
                log("议价流程：已翻到第 {} 页（数据已刷新）".format(now.get("page", 1)))
                time.sleep(0.2)
                return True
            # 允许继续轮询，等待数据刷新完成
        time.sleep(0.3)
    if page_changed:
        # 页码已变化但签名未及时更新：给一个兜底短等待，尽量避免读到旧数据
        log("议价流程：页码已变化，等待表格刷新超时，采用兜底继续")
        time.sleep(0.8)
        return True
    return False


def _click_prev_todo_page(driver, log, timeout=8, should_stop=None):
    """点击分页“<”按钮，返回是否成功翻页。"""
    before = _get_todo_pagination_state(driver)
    before_sig = _get_todo_table_signature(driver)
    if not before.get("has_prev"):
        return False

    clicked = False
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
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return false;
const btns = Array.from(root.querySelectorAll('.soui-pagination-buttons button'));
if (btns.length < 2) return false;
const prevBtn = btns[0];
const cls = (prevBtn.className || '').toString();
if (prevBtn.disabled || cls.includes('soui-button-disabled')) return false;
prevBtn.click();
return true;
"""
    try:
        clicked = bool(driver.execute_script(script))
    except Exception:
        clicked = False
    if not clicked:
        return False

    end = time.time() + timeout
    page_changed = False
    while time.time() < end:
        if _should_stop(should_stop):
            return False
        now = _get_todo_pagination_state(driver)
        if int(now.get("page", 1)) != int(before.get("page", 1)):
            page_changed = True
            now_sig = _get_todo_table_signature(driver)
            if now_sig and now_sig != before_sig:
                log("议价流程：已翻到第 {} 页（数据已刷新）".format(now.get("page", 1)))
                time.sleep(0.2)
                return True
        time.sleep(0.3)
    if page_changed:
        log("议价流程：页码已变化，等待表格刷新超时，采用兜底继续")
        time.sleep(0.8)
        return True
    return False


def open_shein_suggest_price_popup(
    publisher=None,
    account="",
    clone_from_account="",
    log_cb=None,
    headless=False,
    should_stop=None,
    force_new_browser=False,
):
    """打开 SHEIN 商品列表页并点击「价格调整待确认，请及时处理」。"""
    log = log_cb or _noop_log

    pub = publisher
    if pub is None or (not pub.is_alive()):
        pub = SheinPublisher(log_cb=log)
        pub.start_browser(
            account=account or "default",
            clone_from_account=clone_from_account or "",
            headless=headless,
            force_new=bool(force_new_browser),
        )

    driver = getattr(pub, "driver", None)
    if driver is None or not _is_driver_alive(driver):
        return False, "浏览器未就绪，请先登录 SHEIN", pub

    if _should_stop(should_stop):
        return False, "用户已停止议价抓取", pub

    log("议价流程：打开商品列表页面")
    driver.get(SHEIN_LIST_URL)
    _wait_ready(driver, timeout=15, should_stop=should_stop)
    if _should_stop(should_stop):
        return False, "用户已停止议价抓取", pub
    time.sleep(0.2)

    current_url = (driver.current_url or "").lower()
    if "login" in current_url:
        return False, "当前未登录 SHEIN，请先点击“登录 SHEIN”", pub

    if _should_stop(should_stop):
        return False, "用户已停止议价抓取", pub
    _dismiss_user_guide_next_buttons(driver, log, timeout=5, interval=1)

    for _ in range(10):
        if _should_stop(should_stop):
            return False, "用户已停止议价抓取", pub
        if _click_todo_entrance(driver):
            log("议价流程：已点击“价格调整待确认，请及时处理”")
            _wait_todo_drawer_visible(driver, timeout=2.5, should_stop=should_stop)
            return True, "已打开议价入口，请在页面弹窗中查看建议价格", pub
        time.sleep(0.5)

    log("议价流程：首次点击入口失败，尝试再次清理引导并重试")
    if _should_stop(should_stop):
        return False, "用户已停止议价抓取", pub
    _dismiss_user_guide_next_buttons(driver, log, timeout=6, interval=1)

    for _ in range(8):
        if _should_stop(should_stop):
            return False, "用户已停止议价抓取", pub
        if _click_todo_entrance(driver):
            log("议价流程：重试后已点击“价格调整待确认，请及时处理”")
            _wait_todo_drawer_visible(driver, timeout=2.5, should_stop=should_stop)
            return True, "已打开议价入口，请在页面弹窗中查看建议价格", pub
        time.sleep(0.5)

    return False, "未找到“价格调整待确认，请及时处理”入口，请确认页面已加载", pub


def fetch_shein_pending_bargain_rows(
    publisher=None,
    account="",
    clone_from_account="",
    log_cb=None,
    headless=False,
    should_stop=None,
    force_new_browser=False,
    on_page_rows=None,
):
    """打开议价入口并抓取弹窗中“待确认”行。"""
    log = log_cb or _noop_log
    ok, msg, pub = open_shein_suggest_price_popup(
        publisher=publisher,
        account=account,
        clone_from_account=clone_from_account,
        log_cb=log,
        headless=headless,
        should_stop=should_stop,
        force_new_browser=force_new_browser,
    )
    if not ok:
        return False, msg, pub, []

    driver = getattr(pub, "driver", None)
    if driver is None or not _is_driver_alive(driver):
        return False, "议价入口已打开，但浏览器连接中断", pub, []

    if _should_stop(should_stop):
        return False, "用户已停止议价抓取", pub, []
    _dismiss_user_guide_next_buttons(driver, log, timeout=4, interval=0.8)

    clicked_pending = _click_pending_filter_button(driver, log, timeout=8, should_stop=should_stop)
    switched = _ensure_todo_page_size(driver, log, target_size=50, timeout=8, should_stop=should_stop)
    if not switched:
        log("议价流程：切换 50 / 页失败，按当前每页条数继续抓取（降级模式）")
    st_50 = _get_todo_pagination_state(driver)
    if int(st_50.get("page_size", 10) or 10) != 50:
        log("议价流程：当前每页 {} 条（未到50），继续抓取".format(st_50.get("page_size", 10)))
    if _should_stop(should_stop):
        return False, "用户已停止议价抓取", pub, []
    # 用户要求切换 50 / 页后额外等待 3 秒再抓取，确保数据稳定。
    time.sleep(3)
    state = _get_todo_pagination_state(driver)
    total_pages_hint = state.get("total_pages", 1)
    total_items_hint = state.get("total_items", 0)
    log(
        "议价流程：分页信息 页码 {}/{}，总条数 {}，每页 {} 条".format(
            state.get("page", 1), total_pages_hint, total_items_hint, state.get("page_size", 10)
        )
    )

    all_rows = []
    seen = set()
    visited_pages = set()
    max_pages_guard = max(1, total_pages_hint or 1) + 5

    for _ in range(max_pages_guard):
        if _should_stop(should_stop):
            return False, "用户已停止议价抓取", pub, []
        st = _get_todo_pagination_state(driver)
        page_no = int(st.get("page", 1) or 1)
        if page_no in visited_pages:
            break
        visited_pages.add(page_no)
        log("议价流程：开始抓取第 {} 页".format(page_no))

        page_rows = _wait_fetch_pending_bargain_rows(
            driver,
            log,
            timeout=12,
            interval=0.7,
            assume_pending=clicked_pending,
            xyz_only=True,
            should_stop=should_stop,
        )

        added = 0
        for r in page_rows:
            k = (
                _trim_text(r.get("bargain_no", "")),
                _trim_text(r.get("supplier_no_raw", "")),
                _trim_text(r.get("sku_info", "")),
                _trim_text(r.get("sub_spec", "")),
                _trim_text(r.get("reason", "")),
                _trim_text(r.get("platform_price", "")),
            )
            if k in seen:
                continue
            seen.add(k)
            all_rows.append({
                "supplier_no": r.get("supplier_no", ""),
                "reason": r.get("reason", ""),
                "sku_info": r.get("sku_info", ""),
                "sub_spec": r.get("sub_spec", ""),
                "platform_price": r.get("platform_price", ""),
                "bargain_no": r.get("bargain_no", ""),
                "skc": r.get("skc", ""),
                "spu": r.get("spu", ""),
                "status": r.get("status", ""),
                "operation_text": r.get("operation_text", ""),
                "actions": list(r.get("actions", []) or []),
                "_row_text": r.get("_row_text", ""),
                "page_no": page_no,
            })
            added += 1
        log("议价流程：第 {} 页新增 {} 条，累计 {} 条（仅XYZ-）".format(page_no, added, len(all_rows)))
        if callable(on_page_rows):
            try:
                total_pages_now = int(st.get("total_pages", total_pages_hint) or total_pages_hint or 1)
                snapshot = [dict(x) for x in all_rows]
                on_page_rows(page_no, added, snapshot, total_pages_now)
            except Exception:
                pass

        # 若已经是最后一页则结束
        st_after = _get_todo_pagination_state(driver)
        if (not st_after.get("has_next")) or (st_after.get("page", 1) >= st_after.get("total_pages", 1)):
            break

        if not _click_next_todo_page(driver, log, timeout=8, should_stop=should_stop):
            break

    if not all_rows:
        return False, "已进入议价入口，但未抓到“待确认”数据（已按XYZ-筛选）", pub, []

    # 抓取结束后将抽屉分页复位到第1页，避免停留在末页影响后续GUI“操作”体验
    try:
        if not _should_stop(should_stop):
            if _goto_todo_page(driver, 1, log, timeout=8, should_stop=should_stop):
                log("议价流程：抓取完成后已自动回到第 1 页")
    except Exception:
        pass

    return True, "已抓取“待确认”记录 {} 条（仅XYZ-，共{}页）".format(len(all_rows), max(visited_pages) if visited_pages else 1), pub, all_rows


def _click_todo_page_number(driver, page_no):
    """点击抽屉分页中的页码按钮。"""
    script = r"""
const target = parseInt(arguments[0], 10) || 1;
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return false;
const btns = Array.from(root.querySelectorAll('.soui-pagination-buttons button')).filter(visible);
for (const b of btns) {
  const txt = clean(b.innerText || '');
  if (txt === String(target)) {
    b.click();
    return true;
  }
}
return false;
"""
    try:
        return bool(driver.execute_script(script, int(page_no)))
    except Exception:
        return False


def _goto_todo_page(driver, target_page, log, timeout=8, should_stop=None):
    """尽量跳转到目标页：优先直达页码，失败时使用上一页/下一页迭代。"""
    target = max(1, int(target_page or 1))
    st = _get_todo_pagination_state(driver)
    cur = int(st.get("page", 1) or 1)
    total = max(1, int(st.get("total_pages", 1) or 1))
    if target > total:
        target = total
    if cur == target:
        return True

    # 先尝试直接点击页码
    if _click_todo_page_number(driver, target):
        end = time.time() + max(1.0, float(timeout))
        while time.time() < end:
            if _should_stop(should_stop):
                return False
            now = _get_todo_pagination_state(driver)
            if int(now.get("page", 1) or 1) == target:
                return True
            time.sleep(0.2)

    cur = int(_get_todo_pagination_state(driver).get("page", 1) or 1)
    # 正向翻页
    guard = abs(target - cur) + 5
    while cur < target and guard > 0:
        guard -= 1
        if _should_stop(should_stop):
            return False
        if not _click_next_todo_page(driver, log, timeout=timeout, should_stop=should_stop):
            break
        now = _get_todo_pagination_state(driver)
        nxt = int(now.get("page", cur) or cur)
        if nxt == cur:
            break
        cur = nxt

    # 反向翻页
    guard = abs(target - cur) + 5
    while cur > target and guard > 0:
        guard -= 1
        if _should_stop(should_stop):
            return False
        if not _click_prev_todo_page(driver, log, timeout=timeout, should_stop=should_stop):
            break
        now = _get_todo_pagination_state(driver)
        prv = int(now.get("page", cur) or cur)
        if prv == cur:
            break
        cur = prv
    return cur == target


def _click_bargain_action_in_current_page(driver, row, action_label):
    """在当前页按行特征点击指定操作按钮。"""
    script = r"""
const row = arguments[0] || {};
const action = (arguments[1] || '').trim();
const clean = (s) => (s || '').replace(/\s+/g, ' ').trim();
const visible = (el) => {
  if (!el) return false;
  const st = window.getComputedStyle ? window.getComputedStyle(el) : null;
  if (!st) return !!el.offsetParent;
  if (st.display === 'none' || st.visibility === 'hidden' || st.opacity === '0') return false;
  const r = el.getBoundingClientRect();
  return r.width > 0 && r.height > 0;
};
const norm = (s) => clean(s).replace(/[，,]/g, '').replace(/\s+/g, '');
const normAction = (s) => {
  const x = norm(s);
  if (!x) return '';
  if (x === '拒绝上新' || x === '拒绝放弃上新' || x === '拒绝，放弃上新') return '拒绝放弃上新';
  if (x === '同意建议价' || x === '同意平台建议价') return '同意平台建议价';
  if (x.includes('重新报价')) return '重新报价';
  return x;
};
const clickEl = (el) => {
  if (!el) return false;
  try { el.scrollIntoView({ block: 'center', inline: 'center' }); } catch (_) {}
  try { el.click(); return true; } catch (_) {}
  try {
    el.dispatchEvent(new MouseEvent('mousedown', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    el.dispatchEvent(new MouseEvent('click', { bubbles: true }));
    return true;
  } catch (_) {}
  return false;
};
let root = null;
const drawers = Array.from(document.querySelectorAll('.soui-modal-panel,.soui-modal-wrapper,.soui-modal,.merchant-ui-drawer,[class*="drawer"]')).filter(visible);
for (const d of drawers) {
  const t = clean(d.innerText || '');
  if (t.includes('待办任务')) { root = d; break; }
}
if (!root) return {ok:false, reason:'no_root'};
const bargainNo = clean(row['bargain_no'] || '');
const supplierRaw = clean(row['supplier_no_raw'] || '');
const supplierNo = clean(row['supplier_no'] || '');
const skuInfo = clean(row['sku_info'] || '');
const platformPrice = clean(row['platform_price'] || '');
const trs = Array.from(root.querySelectorAll('tbody tr')).filter(visible);
if (!trs.length) return {ok:false, reason:'no_rows'};
let best = null;
let bestScore = -1;
for (const tr of trs) {
  const t = clean(tr.innerText || '');
  if (!t) continue;
  let score = 0;
  if (bargainNo && t.includes(bargainNo)) score += 100;
  if (supplierRaw && t.includes(supplierRaw)) score += 35;
  if (supplierNo && t.includes(supplierNo)) score += 25;
  if (skuInfo && t.includes(skuInfo)) score += 15;
  if (platformPrice && t.includes(platformPrice)) score += 3;
  if (score > bestScore) { bestScore = score; best = tr; }
}
if (!best) return {ok:false, reason:'no_match'};
if (bestScore <= 0) {
  return {ok:false, reason:'no_key_match'};
}
const btns = Array.from(best.querySelectorAll('button,[role="button"]')).filter(visible);
if (!btns.length) return {ok:false, reason:'no_buttons'};
const target = normAction(action);
const cands = btns.map(b => ({el: b, txt: clean(b.innerText || ''), key: normAction(b.innerText || '')})).filter(x => !!x.key);
// 先严格精确匹配
for (const c of cands) {
  if (c.key === target) {
    if (clickEl(c.el)) return {ok:true, clicked: c.txt};
    return {ok:false, reason:'click_failed', clicked: c.txt};
  }
}
// 再做有限兜底（只按动作族兜底，不做泛化 includes，避免串到“重新报价”）
if (target === '拒绝放弃上新') {
  const c = cands.find(x => x.key.includes('拒绝'));
  if (c) {
    if (clickEl(c.el)) return {ok:true, clicked: c.txt};
    return {ok:false, reason:'click_failed', clicked: c.txt};
  }
}
if (target === '同意平台建议价') {
  const c = cands.find(x => x.key.includes('同意'));
  if (c) {
    if (clickEl(c.el)) return {ok:true, clicked: c.txt};
    return {ok:false, reason:'click_failed', clicked: c.txt};
  }
}
if (target === '重新报价') {
  const c = cands.find(x => x.key.includes('重新报价'));
  if (c) {
    if (clickEl(c.el)) return {ok:true, clicked: c.txt};
    return {ok:false, reason:'click_failed', clicked: c.txt};
  }
}
return {
  ok:false,
  reason:'action_not_found',
  labels: cands.map(c => c.txt).join('|'),
  score: bestScore,
  bargain_no_hit: !!(bargainNo && clean(best.innerText || '').includes(bargainNo))
};
"""
    try:
        return driver.execute_script(script, row or {}, action_label or "") or {}
    except Exception:
        return {"ok": False, "reason": "js_exception"}


def _click_confirm_in_popover(driver, timeout=2.0):
    """若出现确认弹窗，点击“确定”。"""
    if By is None:
        return False
    end = time.time() + max(0.5, float(timeout))
    xpaths = [
        "//div[contains(@class,'soui-popover') and not(contains(@style,'display: none'))]//button[.//span[normalize-space(text())='确定'] or normalize-space(text())='确定']",
        "//button[.//span[normalize-space(text())='确定'] or normalize-space(text())='确定']",
    ]
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
                    return True
        time.sleep(0.15)
    return False


def trigger_shein_pending_bargain_action(
    publisher,
    row,
    action_label,
    log_cb=None,
    should_stop=None,
):
    """在议价待办页面触发指定行的“操作”按钮。"""
    log = log_cb or _noop_log
    if publisher is None:
        return False, "未找到可用浏览器实例（请先抓取议价数据）"
    driver = getattr(publisher, "driver", None)
    if driver is None or not _is_driver_alive(driver):
        return False, "浏览器连接已断开，请重新抓取议价数据"
    if _should_stop(should_stop):
        return False, "操作已停止"
    if not _wait_todo_drawer_visible(driver, timeout=2.5, should_stop=should_stop):
        return False, "未检测到待办任务弹窗，请先抓取并保持页面在议价弹窗"

    def _try_click_with_retry(_retries=3, _sleep=0.18):
        last = {}
        for _ in range(max(1, int(_retries))):
            if _should_stop(should_stop):
                break
            last = _click_bargain_action_in_current_page(driver, row, action_label)
            if bool(last.get("ok")):
                return last
            time.sleep(max(0.05, float(_sleep)))
        return last

    target_page = int(row.get("page_no", 1) or 1)
    st_now = _get_todo_pagination_state(driver)
    cur_page = int(st_now.get("page", 1) or 1)

    # 先在当前页快速重试（很多时候当前页就是目标页，能显著提速）
    ret = _try_click_with_retry(_retries=2, _sleep=0.12)
    if (not bool(ret.get("ok"))) and (target_page > 0) and (target_page != cur_page):
        if not _goto_todo_page(driver, target_page, log, timeout=4, should_stop=should_stop):
            log("议价操作：未找到目标页码按钮，尝试跨页扫描")
        ret = _try_click_with_retry(_retries=3, _sleep=0.15)

    if not bool(ret.get("ok")):
        # 跨页强兜底：从当前页向后扫描，再回到第一页补扫到起始页前
        start_page = int(_get_todo_pagination_state(driver).get("page", 1) or 1)
        visited = set()
        while True:
            if _should_stop(should_stop):
                break
            st_now = _get_todo_pagination_state(driver)
            cur_page = int(st_now.get("page", 1) or 1)
            if cur_page in visited:
                break
            visited.add(cur_page)
            ret = _try_click_with_retry(_retries=2, _sleep=0.1)
            if bool(ret.get("ok")):
                break
            if not st_now.get("has_next"):
                break
            if not _click_next_todo_page(driver, log, timeout=4, should_stop=should_stop):
                break

        if (not bool(ret.get("ok"))) and _goto_todo_page(driver, 1, log, timeout=4, should_stop=should_stop):
            while True:
                if _should_stop(should_stop):
                    break
                st_now = _get_todo_pagination_state(driver)
                cur_page = int(st_now.get("page", 1) or 1)
                if cur_page >= start_page:
                    break
                if cur_page in visited:
                    break
                visited.add(cur_page)
                ret = _try_click_with_retry(_retries=2, _sleep=0.1)
                if bool(ret.get("ok")):
                    break
                if not st_now.get("has_next"):
                    break
                if not _click_next_todo_page(driver, log, timeout=4, should_stop=should_stop):
                    break
    if not bool(ret.get("ok")):
        reason = _trim_text(ret.get("reason", "")) or "未命中行或按钮"
        labels = _trim_text(ret.get("labels", ""))
        extra = "（可见按钮：{}）".format(labels) if labels else ""
        return False, "未能点击“{}”：{}{}".format(action_label, reason, extra)

    # “同意平台建议价”“拒绝，放弃上新”通常会有二次确认
    if action_label in ("同意平台建议价", "拒绝，放弃上新"):
        _click_confirm_in_popover(driver, timeout=2.0)

    clicked = _trim_text(ret.get("clicked", "")) or action_label
    return True, "已触发操作：{}".format(clicked)
