# -*- coding: utf-8 -*-
"""
SHEIN 授权管理网页
- 新增/更新 shein_id 有效期
- 查询全部记录（分页）
- 按 shein_id 精确查询

运行:
    python User_manager/manager.py
访问:
    http://127.0.0.1:8010
"""

import os
import hmac
from typing import Any

import requests
import uvicorn
from fastapi import Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from pydantic import BaseModel, field_validator


# 与 Sever/auth_api.py 保持一致
ADMIN_KEY = os.getenv("SHEIN_ADMIN_KEY", "ChangeThis_AdminKey_2026")
AUTH_API_BASE = os.getenv("SHEIN_AUTH_API_BASE", "http://127.0.0.1:8000")
REQUEST_TIMEOUT = 12
MANAGER_HOST = os.getenv("SHEIN_MANAGER_HOST", "0.0.0.0")
MANAGER_PORT = int(os.getenv("SHEIN_MANAGER_PORT", "8010"))
# 管理网页账号白名单（可直接在此添加更多账号）
# 格式: "用户名": "密码"
MANAGER_ACCOUNTS = {
    "Darren": "Adq430483",
}
ALLOWED_HOSTS = [h.strip() for h in os.getenv("SHEIN_MANAGER_ALLOWED_HOSTS", "*").split(",") if h.strip()]
ALLOWED_ORIGINS = [o.strip() for o in os.getenv("SHEIN_MANAGER_ALLOWED_ORIGINS", "*").split(",") if o.strip()]

app = FastAPI(title="SHEIN User Manager", docs_url=None, redoc_url=None)
security = HTTPBasic(auto_error=False)

app.add_middleware(TrustedHostMiddleware, allowed_hosts=ALLOWED_HOSTS or ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=ALLOWED_ORIGINS or ["*"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


class UpsertPayload(BaseModel):
    shein_id: str
    start_time: str
    end_time: str

    @field_validator("shein_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("shein_id 无效")
        return v

    @field_validator("start_time", "end_time")
    @classmethod
    def _validate_date(cls, v: str) -> str:
        v = v.strip()
        # 简单格式校验：YYYY-MM-DD
        parts = v.split("-")
        if len(parts) != 3 or any(not p.isdigit() for p in parts):
            raise ValueError("日期格式必须为 YYYY-MM-DD")
        y, m, d = map(int, parts)
        if y < 2000 or y > 2100 or m < 1 or m > 12 or d < 1 or d > 31:
            raise ValueError("日期值不合法")
        return v


class DeletePayload(BaseModel):
    shein_id: str
    delete_password: str

    @field_validator("shein_id")
    @classmethod
    def _validate_id(cls, v: str) -> str:
        v = v.strip()
        if not v or len(v) > 120:
            raise ValueError("shein_id 无效")
        return v

    @field_validator("delete_password")
    @classmethod
    def _validate_password(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("请输入删除密码")
        return v


def _admin_headers() -> dict[str, str]:
    return {"x-admin-key": ADMIN_KEY}


def _require_manager_login(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    """
    管理网页基础认证（账号密码白名单在 MANAGER_ACCOUNTS 中维护）。
    """
    if credentials is None:
        raise HTTPException(
            status_code=401,
            detail="需要登录",
            headers={"WWW-Authenticate": "Basic"},
        )

    input_user = (credentials.username or "").strip()
    input_pass = credentials.password or ""

    account_ok = False
    for user, passwd in MANAGER_ACCOUNTS.items():
        user_ok = hmac.compare_digest(input_user, user)
        pass_ok = hmac.compare_digest(input_pass, passwd)
        if user_ok and pass_ok:
            account_ok = True
            return user

    if not account_ok:
        raise HTTPException(
            status_code=401,
            detail="账号或密码错误",
            headers={"WWW-Authenticate": "Basic"},
        )
    return ""


def _proxy_get(path: str, params: dict[str, Any]) -> dict[str, Any]:
    url = "{}{}".format(AUTH_API_BASE.rstrip("/"), path)
    try:
        resp = requests.get(
            url,
            params=params,
            headers=_admin_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail="连接 auth_api 失败: {}".format(str(e)[:120]))
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


def _proxy_post(path: str, payload: dict[str, Any]) -> dict[str, Any]:
    url = "{}{}".format(AUTH_API_BASE.rstrip("/"), path)
    try:
        resp = requests.post(
            url,
            json=payload,
            headers=_admin_headers(),
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail="连接 auth_api 失败: {}".format(str(e)[:120]))
    if resp.status_code != 200:
        try:
            detail = resp.json().get("detail", resp.text[:200])
        except Exception:
            detail = resp.text[:200]
        raise HTTPException(status_code=resp.status_code, detail=detail)
    return resp.json()


@app.get("/", response_class=HTMLResponse)
def index(_: None = Depends(_require_manager_login)) -> str:
    return """
<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="UTF-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1.0" />
  <title>SHEIN 授权管理</title>
  <style>
    body { font-family: Arial, sans-serif; background:#f6f7fb; margin:0; padding:24px; }
    .wrap { max-width: 1100px; margin:0 auto; }
    .card { background:#fff; border-radius:10px; padding:18px; box-shadow:0 2px 8px rgba(0,0,0,.07); margin-bottom:16px; }
    h2 { margin:0 0 12px 0; }
    .row { display:flex; gap:10px; flex-wrap:wrap; align-items:center; }
    input { height:34px; padding:0 10px; border:1px solid #d7dbe3; border-radius:6px; min-width:200px; }
    button { height:36px; border:0; border-radius:6px; padding:0 14px; cursor:pointer; color:#fff; background:#2563eb; }
    button.gray { background:#6b7280; }
    button.green { background:#059669; }
    .msg { margin-top:10px; min-height:20px; color:#111827; }
    .err { color:#dc2626; }
    table { width:100%; border-collapse:collapse; background:#fff; }
    th, td { border-bottom:1px solid #e5e7eb; padding:10px; text-align:left; font-size:14px; }
    th { background:#f3f4f6; }
    .toolbar { display:flex; justify-content:space-between; align-items:center; margin:10px 0; flex-wrap:wrap; gap:10px; }
    .small { color:#6b7280; font-size:13px; }
  </style>
</head>
<body>
  <div class="wrap">
    <div class="card">
      <h2>SHEIN 授权管理</h2>
      <div class="row">
        <input id="shein_id" placeholder="添加 shein_id" />
        <input id="start_time" type="date" placeholder="开始时间" />
        <input id="end_time" type="date" placeholder="结束时间" />
        <button class="green" onclick="saveRecord()">确认</button>
      </div>
      <div id="saveMsg" class="msg"></div>
    </div>

    <div class="card">
      <div class="toolbar">
        <div class="row">
          <input id="search_id" placeholder="输入 shein_id 查询" />
          <button onclick="searchOne()">查询</button>
          <button class="gray" onclick="loadAll()">一键查询全部</button>
          <input id="delete_id" placeholder="输入 shein_id 删除权限" />
          <input id="delete_password" type="password" placeholder="删除密码" />
          <button style="background:#dc2626;" onclick="deleteRecord()">删除</button>
        </div>
        <div class="row">
          <span class="small">每页条数:</span>
          <input id="limit" value="100" style="min-width:90px;width:90px;" />
          <span class="small">偏移:</span>
          <input id="offset" value="0" style="min-width:90px;width:90px;" />
          <button class="gray" onclick="loadPage()">分页查询</button>
        </div>
      </div>
      <div id="listMsg" class="msg"></div>
      <table>
        <thead>
          <tr>
            <th>shein_id</th>
            <th>start_time</th>
            <th>end_time</th>
          </tr>
        </thead>
        <tbody id="tbody"></tbody>
      </table>
    </div>
  </div>

<script>
async function apiGet(url) {
  const res = await fetch(url);
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '请求失败');
  return data;
}
async function apiPost(url, payload) {
  const res = await fetch(url, {
    method: 'POST',
    headers: {'Content-Type': 'application/json'},
    body: JSON.stringify(payload),
  });
  const data = await res.json();
  if (!res.ok) throw new Error(data.detail || '请求失败');
  return data;
}
function setMsg(id, text, isErr=false) {
  const el = document.getElementById(id);
  el.className = 'msg' + (isErr ? ' err' : '');
  el.textContent = text || '';
}
function renderRows(items) {
  const tbody = document.getElementById('tbody');
  tbody.innerHTML = '';
  for (const it of items || []) {
    const tr = document.createElement('tr');
    tr.innerHTML = `<td>${it.shein_id || ''}</td><td>${it.start_time || ''}</td><td>${it.end_time || ''}</td>`;
    tbody.appendChild(tr);
  }
}
async function saveRecord() {
  setMsg('saveMsg', '');
  try {
    const payload = {
      shein_id: document.getElementById('shein_id').value.trim(),
      start_time: document.getElementById('start_time').value.trim(),
      end_time: document.getElementById('end_time').value.trim(),
    };
    const data = await apiPost('/api/upsert', payload);
    setMsg('saveMsg', `保存成功: ${data.action} / ${data.record.shein_id}`);
    await loadPage();
  } catch (e) {
    setMsg('saveMsg', e.message, true);
  }
}
async function deleteRecord() {
  setMsg('listMsg', '');
  try {
    const sheinId = document.getElementById('delete_id').value.trim();
    const deletePassword = document.getElementById('delete_password').value.trim();
    if (!sheinId) {
      throw new Error('请先输入要删除的 shein_id');
    }
    if (!deletePassword) {
      throw new Error('请先输入删除密码');
    }
    const ok = confirm(`确认删除 shein_id: ${sheinId} ?`);
    if (!ok) return;
    const data = await apiPost('/api/delete', {
      shein_id: sheinId,
      delete_password: deletePassword,
    });
    if ((data.deleted || 0) > 0) {
      setMsg('listMsg', `删除成功: ${sheinId}（删除 ${data.deleted} 条）`);
    } else {
      setMsg('listMsg', `未找到 shein_id: ${sheinId}（0 条）`, true);
    }
    await loadPage();
  } catch (e) {
    setMsg('listMsg', e.message, true);
  }
}
async function searchOne() {
  const sid = document.getElementById('search_id').value.trim();
  document.getElementById('offset').value = '0';
  await loadPage(sid);
}
async function loadAll() {
  document.getElementById('search_id').value = '';
  document.getElementById('offset').value = '0';
  await loadPage('');
}
async function loadPage(sidOverride=null) {
  setMsg('listMsg', '');
  try {
    const sheinId = sidOverride === null
      ? document.getElementById('search_id').value.trim()
      : sidOverride;
    const limit = parseInt(document.getElementById('limit').value || '100', 10);
    const offset = parseInt(document.getElementById('offset').value || '0', 10);
    const q = new URLSearchParams({
      shein_id: sheinId,
      limit: String(limit > 0 ? limit : 100),
      offset: String(offset >= 0 ? offset : 0),
    });
    const data = await apiGet('/api/list?' + q.toString());
    renderRows(data.items || []);
    setMsg('listMsg', `查询成功: total=${data.total}, 当前返回=${(data.items || []).length}`);
  } catch (e) {
    setMsg('listMsg', e.message, true);
  }
}
loadPage('');
</script>
</body>
</html>
"""


@app.post("/api/upsert")
def api_upsert(
    payload: UpsertPayload,
    operator: str = Depends(_require_manager_login),
) -> dict[str, Any]:
    body = payload.model_dump()
    body["operator"] = operator
    return _proxy_post("/admin/upsert_record", body)


@app.post("/api/delete")
def api_delete(
    payload: DeletePayload,
    operator: str = Depends(_require_manager_login),
) -> dict[str, Any]:
    body = payload.model_dump()
    body["operator"] = operator
    return _proxy_post("/admin/delete_record", body)


@app.get("/api/list")
def api_list(
    shein_id: str = Query(default=""),
    limit: int = Query(default=100, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _: None = Depends(_require_manager_login),
) -> dict[str, Any]:
    return _proxy_get(
        "/admin/list_records",
        {"shein_id": shein_id.strip(), "limit": limit, "offset": offset},
    )


@app.get("/health")
def health() -> dict[str, Any]:
    return {"ok": True, "service": "shein-user-manager"}


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=MANAGER_HOST,
        port=MANAGER_PORT,
        reload=False,
        proxy_headers=True,
        forwarded_allow_ips="*",
    )
