"""SHEIN 自动更新模块（阿里云 OSS 版本）."""

import hashlib
import json
import os
import re
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
# 更新包下载分块（适当增大可减少磁盘写入与 Python 循环开销）
DOWNLOAD_CHUNK_SIZE = 1024 * 1024


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

    def __init__(self, remote_version_url="", app_name="SHEIN_Uploader", log_cb=None, progress_cb=None):
        self.remote_version_url = (remote_version_url or DEFAULT_REMOTE_VERSION_URL).strip()
        self.app_name = app_name
        self.log = log_cb or print
        self.progress_cb = progress_cb

        self.base_dir = self._get_base_dir()
        self.local_version_path = os.path.join(self.base_dir, LOCAL_VERSION_FILE)
        self.latest_remote = {}

    def _emit_progress(self, percent=None, stage=""):
        cb = self.progress_cb
        if cb is None:
            return
        try:
            cb(percent=percent, stage=str(stage or ""))
        except Exception:
            pass

    def _get_base_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def _get_local_version_candidates(self):
        """本地版本文件候选路径：exe目录优先，其次脚本目录、工作目录。"""
        cands = []
        try:
            cands.append(os.path.join(self._get_base_dir(), LOCAL_VERSION_FILE))
        except Exception:
            pass
        try:
            cands.append(os.path.join(os.path.dirname(os.path.abspath(__file__)), LOCAL_VERSION_FILE))
        except Exception:
            pass
        try:
            cands.append(os.path.join(os.getcwd(), LOCAL_VERSION_FILE))
        except Exception:
            pass
        uniq = []
        seen = set()
        for p in cands:
            np = os.path.normpath(p)
            if np in seen:
                continue
            seen.add(np)
            uniq.append(p)
        return uniq

    def get_local_version(self):
        for vp in self._get_local_version_candidates():
            data = _safe_json_load(vp)
            v = str((data or {}).get("version") or "").strip()
            if v:
                return v
        return "0.0.0"

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
        self._emit_progress(percent=5, stage="开始下载更新包")
        self._download_file(download_url, package_path)
        self.log(f"[UPDATER] 下载完成: {package_path}")
        self._emit_progress(percent=72, stage="下载完成")

        if expected_sha256:
            self._emit_progress(percent=78, stage="正在校验文件完整性")
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
        self._emit_progress(percent=84, stage="正在解压更新包")
        with zipfile.ZipFile(package_path, "r") as zf:
            zf.extractall(extract_dir)

        current_dir = self.base_dir
        old_version = self.get_local_version()
        target_dir = self._derive_target_dir_for_version(current_dir, new_version)
        cleanup_dirs = self._build_legacy_cleanup_dirs(
            current_dir=current_dir,
            target_dir=target_dir,
            old_version=old_version,
            new_version=new_version,
        )
        exe_name = os.path.basename(sys.executable)
        self.log(f"[UPDATER] 更新目录: {current_dir} -> {target_dir}")
        if cleanup_dirs:
            self.log("[UPDATER] 升级后将清理旧目录: {}".format(" | ".join(cleanup_dirs)))
        pre_deployed = False
        if os.path.normcase(os.path.normpath(target_dir)) != os.path.normcase(os.path.normpath(current_dir)):
            self._emit_progress(percent=90, stage="正在预部署新版本文件")
            self._predeploy_target_dir(extract_dir, target_dir, exe_name)
            pre_deployed = True
            self._emit_progress(percent=96, stage="预部署完成，准备切换到新版本")
        self._emit_progress(percent=98, stage="正在准备切换脚本")
        self._write_update_bat(
            bat_path=bat_path,
            extracted_dir=extract_dir,
            current_dir=current_dir,
            target_dir=target_dir,
            exe_name=exe_name,
            temp_package_path=package_path,
            cleanup_dirs=cleanup_dirs,
            pre_deployed=pre_deployed,
        )

        self.log("[UPDATER] 启动更新脚本并退出当前程序...")
        self._emit_progress(percent=100, stage="更新包准备完成，正在启动新版本...")
        subprocess.Popen(f'cmd /c "{bat_path}"', shell=True)

        if threading.current_thread() is threading.main_thread():
            sys.exit(0)
        os._exit(0)

    def _download_file(self, url, save_path):
        with requests.Session() as sess:
            with sess.get(url, timeout=(8, HTTP_TIMEOUT), stream=True) as resp:
                resp.raise_for_status()
                total = 0
                try:
                    total = int(resp.headers.get("Content-Length") or 0)
                except Exception:
                    total = 0
                done = 0
                last_emit_ts = 0.0
                with open(save_path, "wb") as f:
                    for chunk in resp.iter_content(chunk_size=DOWNLOAD_CHUNK_SIZE):
                        if not chunk:
                            continue
                        f.write(chunk)
                        done += len(chunk)
                        if total > 0:
                            now_ts = time.time()
                            if (now_ts - last_emit_ts) >= 0.18 or done >= total:
                                ratio = max(0.0, min(1.0, float(done) / float(total)))
                                pct = 5.0 + ratio * 65.0
                                mb_done = done / (1024 * 1024)
                                mb_total = total / (1024 * 1024)
                                self._emit_progress(
                                    percent=round(pct, 1),
                                    stage="下载中 {:.1f}/{:.1f} MB".format(mb_done, mb_total),
                                )
                                last_emit_ts = now_ts

    def _resolve_extract_source_dir(self, extracted_dir, exe_name):
        base = os.path.normpath(extracted_dir)
        exe_base = os.path.join(base, exe_name)
        if os.path.isfile(exe_base):
            return base
        try:
            for name in os.listdir(base):
                full = os.path.join(base, name)
                if os.path.isdir(full) and os.path.isfile(os.path.join(full, exe_name)):
                    return os.path.normpath(full)
        except Exception:
            pass
        return base

    def _predeploy_target_dir(self, extracted_dir, target_dir, exe_name):
        src_dir = self._resolve_extract_source_dir(extracted_dir, exe_name)
        tar_dir = os.path.normpath(target_dir)
        try:
            if os.path.exists(tar_dir):
                shutil.rmtree(tar_dir, ignore_errors=True)
        except Exception:
            pass
        moved_ok = False
        try:
            src_drive = os.path.splitdrive(os.path.normpath(src_dir))[0].lower()
            tar_drive = os.path.splitdrive(tar_dir)[0].lower()
            if src_drive and (src_drive == tar_drive):
                # 同盘优先 move，通常秒级完成，避免 robocopy 弹窗和长耗时
                shutil.move(src_dir, tar_dir)
                moved_ok = os.path.isdir(tar_dir)
        except Exception:
            moved_ok = False

        if not moved_ok:
            copied_ok = False
            try:
                shutil.copytree(src_dir, tar_dir, dirs_exist_ok=True)
                copied_ok = True
            except Exception:
                copied_ok = False
            if (not copied_ok) and shutil.which("robocopy"):
                create_no_window = int(getattr(subprocess, "CREATE_NO_WINDOW", 0))
                cp = subprocess.run(
                    [
                        "robocopy",
                        src_dir,
                        tar_dir,
                        "/E",
                        "/COPY:DAT",
                        "/DCOPY:DAT",
                        "/R:0",
                        "/W:0",
                        "/MT:32",
                        "/NFL",
                        "/NDL",
                        "/NJH",
                        "/NJS",
                        "/NP",
                    ],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    shell=False,
                    creationflags=create_no_window,
                )
                if cp.returncode >= 8:
                    raise RuntimeError("预部署 robocopy 失败，返回码 {}".format(cp.returncode))
        exe_path = os.path.join(tar_dir, exe_name)
        if not os.path.isfile(exe_path):
            raise FileNotFoundError("预部署失败：未找到 {}".format(exe_path))

    def _derive_target_dir_for_version(self, current_dir, new_version):
        """若目录名含版本号则替换；无版本号时按 app_name_版本 生成新目录。"""
        if not new_version:
            return current_dir
        normalized_new_ver = str(new_version).strip().lstrip("vV")
        if not normalized_new_ver:
            return current_dir
        base_name = os.path.basename(os.path.normpath(current_dir))
        parent_dir = os.path.dirname(os.path.normpath(current_dir))
        parent_name = os.path.basename(os.path.normpath(parent_dir))
        app_low = str(self.app_name or "").strip().lower()
        base_low = base_name.lower()
        parent_low = parent_name.lower()
        install_root = parent_dir
        # 处理双层目录：...\SHEIN_Uploader(2)\SHEIN_Uploader(2)
        if app_low and base_low.startswith(app_low) and parent_low.startswith(app_low):
            install_root = os.path.dirname(parent_dir)
        matches = list(re.finditer(r"\d+(?:\.\d+){1,3}", base_name))
        if matches:
            last = matches[-1]
            new_name = "{}{}{}".format(
                base_name[:last.start()],
                normalized_new_ver,
                base_name[last.end():],
            )
            if new_name and new_name != base_name:
                return os.path.join(install_root, new_name)
            return current_dir
        if app_low and (base_low == app_low or base_low.startswith(app_low)):
            base_stem = self.app_name if app_low == base_low else base_name
            return os.path.join(install_root, "{}_{}".format(base_stem, normalized_new_ver))
        return current_dir

    def _build_legacy_cleanup_dirs(self, current_dir, target_dir, old_version="", new_version=""):
        """构建升级后可安全删除的旧版本目录候选。"""
        app = str(self.app_name or "").strip()
        if not app:
            return []
        cur = os.path.normpath(current_dir)
        tar = os.path.normpath(target_dir)
        parent = os.path.dirname(cur)
        grand = os.path.dirname(parent)
        old_ver = str(old_version or "").strip().lstrip("vV")
        new_ver = str(new_version or "").strip().lstrip("vV")
        candidates = []

        def _add(p):
            if not p:
                return
            np = os.path.normpath(p)
            if np in (cur, tar):
                return
            try:
                if tar.startswith(np + os.sep):
                    return
            except Exception:
                pass
            if np not in candidates:
                candidates.append(np)

        for base in (parent, grand):
            if not base:
                continue
            _add(os.path.join(base, app))
            if old_ver:
                _add(os.path.join(base, "{}_{}".format(app, old_ver)))
            if new_ver:
                _add(os.path.join(base, "{}_v{}".format(app, new_ver)))

            # 激进清理：同级目录中所有 SHEIN_Uploader* 旧目录（保留当前目标目录）
            try:
                for name in os.listdir(base):
                    full = os.path.join(base, name)
                    if not os.path.isdir(full):
                        continue
                    low = str(name or "").strip().lower()
                    app_low = app.lower()
                    if not low.startswith(app_low):
                        continue
                    # 仅清理常见版本目录后缀，避免误删完全无关目录
                    suffix = low[len(app_low):]
                    if suffix and (suffix[0] not in ("_", "-", " ", "(", "v")):
                        continue
                    _add(full)
            except Exception:
                pass
        try:
            app_low = app.lower()
            cur_name = os.path.basename(cur).lower()
            parent_name = os.path.basename(parent).lower()
            if cur_name.startswith(app_low) and parent_name.startswith(app_low):
                _add(parent)
        except Exception:
            pass
        return candidates

    def _write_update_bat(self, bat_path, extracted_dir, current_dir, target_dir, exe_name, temp_package_path, cleanup_dirs=None, pre_deployed=False):
        backup_dir = f"{current_dir}_old"
        cleanup_bat_path = os.path.join(os.path.dirname(bat_path), "cleanup_after_update.bat")
        extracted_dir = extracted_dir.replace("/", "\\")
        current_dir = current_dir.replace("/", "\\")
        target_dir = target_dir.replace("/", "\\").rstrip("\\")
        backup_dir = backup_dir.replace("/", "\\")
        cleanup_bat_path = cleanup_bat_path.replace("/", "\\")
        exe_name = os.path.basename(exe_name.replace("/", "\\"))
        temp_package_path = temp_package_path.replace("/", "\\")
        cleanup_dirs = list(cleanup_dirs or [])
        cleanup_cmds = []
        for d in cleanup_dirs:
            d2 = str(d).replace("/", "\\")
            if not d2:
                continue
            cleanup_cmds.append(
                'if /I not "{d}"=="{target}" if exist "{d}" rmdir /s /q "{d}"'.format(
                    d=d2, target=target_dir
                )
            )
        cleanup_block = "\n".join(cleanup_cmds) if cleanup_cmds else "rem no extra cleanup dirs"

        # 兼容 zip 里“直接是文件”或“有一层目录”两种结构
        content = f"""@echo off
chcp 65001 > nul
title SHEIN 自动更新中...
cd /d "%TEMP%"

echo [1/7] 等待旧进程退出...
timeout /t 1 /nobreak > nul

echo [2/7] 清理历史备份...
if exist "{backup_dir}" rmdir /s /q "{backup_dir}"

echo [3/7] 迁移旧版本目录...
if /I not "{current_dir}"=="{target_dir}" (
  if "{1 if pre_deployed else 0}"=="1" (
    rem 已预部署，保留目标目录
  ) else (
    if exist "{target_dir}" rmdir /s /q "{target_dir}"
  )
)
if exist "{current_dir}" ren "{current_dir}" "{os.path.basename(backup_dir)}"

echo [4/7] 创建新版本目录...
mkdir "{target_dir}"

echo [5/7] 识别更新包根目录...
set "SRC_DIR={extracted_dir}"
if not exist "{extracted_dir}\\{exe_name}" (
  for /d %%D in ("{extracted_dir}\\*") do (
    if exist "%%~fD\\{exe_name}" (
      set "SRC_DIR=%%~fD"
      goto found_src
    )
  )
)
:found_src

echo [5/7] 复制新版本文件...
if "{1 if pre_deployed else 0}"=="1" (
  echo [UPDATER] 已预部署，跳过复制
) else (
  xcopy "%SRC_DIR%\\*" "{target_dir}\\" /E /I /H /Y > nul
  if %errorlevel% neq 0 (
    echo [UPDATER] 复制失败，源目录: %SRC_DIR%
  )
)

echo [6/7] 启动新版本...
set "TARGET_DIR={target_dir}"
set "TARGET_EXE=%TARGET_DIR%\\{exe_name}"
if not exist "%TARGET_EXE%" (
  for /r "%TARGET_DIR%" %%F in ("{exe_name}") do (
    set "TARGET_EXE=%%~fF"
    goto found_exe
  )
)
:found_exe
if exist "%TARGET_EXE%" (
  start "" "%TARGET_EXE%"
) else (
  echo [UPDATER] 启动失败，未找到新版本可执行文件: %TARGET_EXE%
)

echo [7/7] 清理临时文件...
if exist "{cleanup_bat_path}" start "" /min "{cleanup_bat_path}"
del "%~f0"
exit
"""
        cleanup_content = f"""@echo off
chcp 65001 > nul
cd /d "%TEMP%"
timeout /t 2 /nobreak > nul
if exist "{extracted_dir}" rmdir /s /q "{extracted_dir}"
if exist "{temp_package_path}" del /f /q "{temp_package_path}"
for /l %%I in (1,1,6) do (
  if exist "{backup_dir}" rmdir /s /q "{backup_dir}"
  if not exist "{backup_dir}" goto backup_deleted
  timeout /t 1 /nobreak > nul
)
:backup_deleted
if /I not "{current_dir}"=="{target_dir}" (
  for /l %%I in (1,1,6) do (
    if exist "{current_dir}" rmdir /s /q "{current_dir}"
    if not exist "{current_dir}" goto current_deleted
    timeout /t 1 /nobreak > nul
  )
)
:current_deleted
{cleanup_block}
echo [8/8] 刷新桌面图标...
if exist "%SystemRoot%\System32\ie4uinit.exe" "%SystemRoot%\System32\ie4uinit.exe" -ClearIconCache > nul 2>nul
if exist "%SystemRoot%\System32\ie4uinit.exe" "%SystemRoot%\System32\ie4uinit.exe" -show > nul 2>nul
if exist "%SystemRoot%\Sysnative\ie4uinit.exe" "%SystemRoot%\Sysnative\ie4uinit.exe" -show > nul 2>nul
rundll32.exe user32.dll,UpdatePerUserSystemParameters 1, True > nul 2>nul
del "%~f0"
exit
"""
        with open(bat_path, "w", encoding="gbk") as f:
            f.write(content)
        with open(cleanup_bat_path, "w", encoding="gbk") as f:
            f.write(cleanup_content)


def ensure_local_version_file(base_dir=None, version_value="0.0.0"):
    """确保本地 .version.json 存在。"""
    base = base_dir or os.path.dirname(os.path.abspath(__file__))
    path = os.path.join(base, LOCAL_VERSION_FILE)
    if not os.path.exists(path):
        _safe_json_save(path, {"version": str(version_value), "channel": "stable"})
    return path


def cleanup_legacy_install_dirs(base_dir=None, app_name="SHEIN_Uploader", keep_version="", log_cb=None):
    """
    清理同级旧版本安装目录（保留当前目录与更高/相同版本目录）。
    仅建议在新版本启动后执行，作为 bat 清理失败时的兜底。
    """
    log = log_cb or (lambda *_args, **_kwargs: None)
    try:
        current_dir = os.path.normpath(base_dir or os.path.dirname(sys.executable))
    except Exception:
        current_dir = os.path.normpath(os.path.dirname(os.path.abspath(__file__)))
    parent_dir = os.path.dirname(current_dir)
    current_name = os.path.basename(current_dir)
    app = str(app_name or "").strip()
    if not app or not os.path.isdir(parent_dir):
        return {"deleted": [], "failed": []}

    keep_ver = str(keep_version or "").strip().lstrip("vV")
    keep_norm = _normalize_version(keep_ver) if keep_ver else ()
    app_low = app.lower()
    deleted = []
    failed = []

    def _extract_ver(name):
        ms = list(re.finditer(r"\d+(?:\.\d+){1,3}", str(name or "")))
        if not ms:
            return ""
        return ms[-1].group(0)

    for name in os.listdir(parent_dir):
        full = os.path.normpath(os.path.join(parent_dir, name))
        if full == current_dir or not os.path.isdir(full):
            continue
        low = str(name or "").strip().lower()
        if not low.startswith(app_low):
            continue
        suffix = low[len(app_low):]
        if suffix and (suffix[0] not in ("_", "-", " ", "(", "v")):
            continue

        # 若能识别版本号，仅清理“低于当前版本”的目录；无法识别则按旧目录处理。
        ver = _extract_ver(name)
        if ver and keep_norm:
            try:
                if _normalize_version(ver) >= keep_norm:
                    continue
            except Exception:
                pass
        # 名称与当前目录一致（大小写差异）不处理
        if str(name).strip().lower() == str(current_name).strip().lower():
            continue

        removed = False
        for _ in range(3):
            try:
                shutil.rmtree(full, ignore_errors=False)
                removed = (not os.path.exists(full))
                if removed:
                    break
            except Exception:
                time.sleep(0.4)
        if removed:
            deleted.append(full)
            log("[UPDATER] 启动后清理旧目录成功: {}".format(full))
        else:
            failed.append(full)
            log("[UPDATER] 启动后清理旧目录失败: {}".format(full))

    return {"deleted": deleted, "failed": failed}