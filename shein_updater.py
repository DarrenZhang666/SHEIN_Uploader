"""SHEIN 自动更新模块（阿里云 OSS 版本）."""

import hashlib
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import zipfile
from dataclasses import dataclass
from urllib.parse import urlsplit

import requests


# 本地版本文件（随程序一起发版）
LOCAL_VERSION_FILE = ".version.json"

# 远程版本文件（OSS）
# 示例: https://<bucket>.<region>.aliyuncs.com/version.json
DEFAULT_REMOTE_VERSION_URL = ""

# 下载超时（秒）
HTTP_TIMEOUT = 12


def _normalize_version(v):
    """把版本号转成可比较元组，如 v1.2.3 -> (1,2,3)."""
    raw = str(v or "").strip().lower()
    if raw.startswith("v"):
        raw = raw[1:]
    parts = []
    for p in raw.split("."):
        digits = "".join(ch for ch in p if ch.isdigit())
        parts.append(int(digits) if digits else 0)
    while len(parts) < 3:
        parts.append(0)
    return tuple(parts[:4])


def _is_newer(remote_ver, local_ver):
    return _normalize_version(remote_ver) > _normalize_version(local_ver)


def _safe_json_load(path):
    if not os.path.exists(path):
        return {}
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def _safe_json_save(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def _sha256_of_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest().lower()


@dataclass
class UpdateInfo:
    has_update: bool
    current_version: str
    remote_version: str
    download_url: str
    force: bool
    release_notes: str
    error: str = ""


class OSSAutoUpdater:
    """
    OSS 自动更新器。

    远程 version.json 推荐格式:
    {
      "version": "1.2.6",
      "download_url": "https://xxx.oss-cn-hangzhou.aliyuncs.com/releases/SHEIN_Uploader_1.2.6.zip",
      "sha256": "可选",
      "force": false,
      "release_notes": "修复xxx"
    }
    """

    def __init__(self, remote_version_url="", app_name="SHEIN_Uploader", log_cb=None):
        self.remote_version_url = (remote_version_url or DEFAULT_REMOTE_VERSION_URL).strip()
        self.app_name = app_name
        self.log = log_cb or print

        self.base_dir = self._get_base_dir()
        self.local_version_path = os.path.join(self.base_dir, LOCAL_VERSION_FILE)
        self.latest_remote = {}

    def _get_base_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def get_local_version(self):
        data = _safe_json_load(self.local_version_path)
        return str(data.get("version") or "0.0.0")

    def fetch_remote_version(self):
        if not self.remote_version_url:
            raise ValueError("remote_version_url 未配置")
        url = self.remote_version_url
        sep = "&" if "?" in url else "?"
        # 防缓存，确保每次都拿到 OSS 最新 version.json
        url = f"{url}{sep}t={int(time.time())}"
        resp = requests.get(url, timeout=HTTP_TIMEOUT)
        resp.raise_for_status()
        data = resp.json()
        if not data.get("version"):
            raise ValueError("远程 version.json 缺少 version")
        if not data.get("download_url"):
            raise ValueError("远程 version.json 缺少 download_url")
        self.latest_remote = data
        return data

    def check_update(self):
        current_ver = self.get_local_version()
        try:
            remote = self.fetch_remote_version()
            remote_ver = str(remote.get("version"))
            return UpdateInfo(
                has_update=_is_newer(remote_ver, current_ver),
                current_version=current_ver,
                remote_version=remote_ver,
                download_url=str(remote.get("download_url") or ""),
                force=bool(remote.get("force", False)),
                release_notes=str(remote.get("release_notes") or ""),
                error="",
            )
        except Exception as e:
            return UpdateInfo(
                has_update=False,
                current_version=current_ver,
                remote_version=current_ver,
                download_url="",
                force=False,
                release_notes="",
                error=str(e),
            )

    def auto_update_if_needed(self):
        """
        自动检查并更新。
        返回 (updated: bool, message: str)
        """
        info = self.check_update()
        if info.error:
            return False, f"检查更新失败: {info.error}"
        if not info.has_update:
            return False, f"当前已是最新版本 {info.current_version}"

        self.log(f"[UPDATER] 检测到新版本: {info.remote_version} (当前 {info.current_version})")
        try:
            self._download_and_apply(self.latest_remote)
            return True, f"已更新到 {info.remote_version}"
        except Exception as e:
            return False, f"更新失败: {e}"

    def _download_and_apply(self, remote):
        download_url = str(remote.get("download_url") or "").strip()
        expected_sha256 = str(remote.get("sha256") or "").strip().lower()
        new_version = str(remote.get("version") or "").strip()

        if not download_url:
            raise ValueError("download_url 为空")

        tmp_dir = os.path.join(tempfile.gettempdir(), f"{self.app_name}_updater")
        os.makedirs(tmp_dir, exist_ok=True)

        filename = os.path.basename(urlsplit(download_url).path) or "update_package.zip"
        package_path = os.path.join(tmp_dir, filename)
        extract_dir = os.path.join(tmp_dir, "extract")
        bat_path = os.path.join(tmp_dir, "apply_update.bat")

        self.log("[UPDATER] 开始下载更新包...")
        self._download_file(download_url, package_path)
        self.log(f"[UPDATER] 下载完成: {package_path}")

        if expected_sha256:
            got = _sha256_of_file(package_path)
            if got != expected_sha256:
                raise ValueError(f"SHA256 校验失败，期望 {expected_sha256}，实际 {got}")

        ext = os.path.splitext(package_path)[1].lower()
        if ext != ".zip":
            # 非zip: 直接下载到本地并交给你自己安装逻辑（例如exe安装器）
            raise ValueError("当前仅支持 ZIP 更新包，请将 download_url 指向 zip")

        if os.path.exists(extract_dir):
            shutil.rmtree(extract_dir, ignore_errors=True)
        os.makedirs(extract_dir, exist_ok=True)
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(extract_dir)

        self._write_update_bat(
            bat_path=bat_path,
            extracted_dir=extract_dir,
            target_dir=self.base_dir,
            exe_path=sys.executable,
            temp_package_path=package_path,
        )

        self.log("[UPDATER] 启动更新脚本并退出当前程序...")
        subprocess.Popen(f'cmd /c "{bat_path}"', shell=True)

        # 提前写入本地版本（脚本成功替换后即对应新版本）
        local = _safe_json_load(self.local_version_path)
        local["version"] = new_version
        _safe_json_save(self.local_version_path, local)

        if threading.current_thread() is threading.main_thread():
            sys.exit(0)
        os._exit(0)

    def _download_file(self, url, save_path):
        with requests.get(url, timeout=HTTP_TIMEOUT, stream=True) as resp:
            resp.raise_for_status()
            with open(save_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1024 * 256):
                    if chunk:
                        f.write(chunk)

    def _write_update_bat(self, bat_path, extracted_dir, target_dir, exe_path, temp_package_path):
        backup_dir = f"{target_dir}_old"
        extracted_dir = extracted_dir.replace("/", "\\")
        target_dir = target_dir.replace("/", "\\")
        backup_dir = backup_dir.replace("/", "\\")
        exe_path = exe_path.replace("/", "\\")
        temp_package_path = temp_package_path.replace("/", "\\")

        # 兼容 zip 里“直接是文件”或“有一层目录”两种结构
        content = f"""@echo off
chcp 65001 > nul
title SHEIN 自动更新中...

echo [1/6] 等待旧进程退出...
timeout /t 2 /nobreak > nul

echo [2/6] 备份旧目录...
if exist "{backup_dir}" rmdir /s /q "{backup_dir}"
if exist "{target_dir}" ren "{target_dir}" "{os.path.basename(backup_dir)}"

echo [3/6] 创建新目录...
mkdir "{target_dir}"

echo [4/6] 复制新版本文件...
xcopy "{extracted_dir}\\*" "{target_dir}\\" /E /I /H /Y > nul
if %errorlevel% neq 0 (
  for /d %%D in ("{extracted_dir}\\*") do (
    xcopy "%%D\\*" "{target_dir}\\" /E /I /H /Y > nul
    goto copied
  )
)
:copied

echo [5/6] 启动新版本...
start "" "{exe_path}"

echo [6/6] 清理临时文件...
timeout /t 3 /nobreak > nul
if exist "{extracted_dir}" rmdir /s /q "{extracted_dir}"
if exist "{temp_package_path}" del /f /q "{temp_package_path}"
if exist "{backup_dir}" rmdir /s /q "{backup_dir}"
del "%~f0"
exit
"""
        with open(bat_path, "w", encoding="gbk") as f:
            f.write(content)


def ensure_local_version_file(base_dir=None, version_value="0.0.0"):
    """确保本地 .version.json 存在。"""
    base = base_dir or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, LOCAL_VERSION_FILE)
    if not os.path.exists(path):
        _safe_json_save(path, {"version": str(version_value), "channel": "stable"})
    return path