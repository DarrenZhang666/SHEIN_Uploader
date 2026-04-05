# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path
import sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files


if "__file__" in globals():
    PROJECT_DIR = Path(__file__).resolve().parent
elif "SPEC" in globals():
    PROJECT_DIR = Path(SPEC).resolve().parent
else:
    PROJECT_DIR = Path.cwd().resolve()


def _collect_browser_driver_datas():
    """
    自动收集可用浏览器驱动并打包到 dist/SHEIN_Uploader/drivers。
    优先匹配项目内常见目录；不存在时不报错。
    """
    patterns = [
        "msedgedriver.exe",
        "chromedriver.exe",
        "drivers/msedgedriver.exe",
        "drivers/chromedriver.exe",
        "工具/**/msedgedriver.exe",
        "工具/**/chromedriver.exe",
    ]
    datas = []
    seen = set()
    for p in patterns:
        for f in PROJECT_DIR.glob(p):
            if f.is_file():
                key = str(f.resolve()).lower()
                if key in seen:
                    continue
                seen.add(key)
                datas.append((str(f), "drivers"))
    return datas


DRIVER_DATAS = _collect_browser_driver_datas()
if DRIVER_DATAS:
    print("[SPEC] bundled browser drivers:")
    for src, dst in DRIVER_DATAS:
        print("  - {} -> {}".format(src, dst))
else:
    print("[SPEC] no local browser drivers found, runtime will auto-download")


def _collect_runtime_binaries():
    """
    显式收集 Python 运行时 DLL，避免客户机出现
    'Failed to load Python DLL ... python311.dll'。
    """
    roots = []
    try:
        roots.append(Path(sys.base_prefix))
    except Exception:
        pass
    try:
        roots.append(Path(sys.executable).resolve().parent)
    except Exception:
        pass
    dll_names = {
        "python311.dll",
        "python3.dll",
        "vcruntime140.dll",
        "vcruntime140_1.dll",
        "msvcp140.dll",
        "msvcp140_1.dll",
        "msvcp140_2.dll",
    }
    binaries = []
    seen = set()
    for root in roots:
        for rel in (".", "DLLs"):
            d = root / rel
            if not d.exists():
                continue
            for name in dll_names:
                p = d / name
                if p.is_file():
                    key = str(p.resolve()).lower()
                    if key in seen:
                        continue
                    seen.add(key)
                    binaries.append((str(p), "."))
    return binaries


RUNTIME_BINARIES = _collect_runtime_binaries()
if RUNTIME_BINARIES:
    print("[SPEC] bundled runtime dlls:")
    for src, dst in RUNTIME_BINARIES:
        print("  - {} -> {}".format(src, dst))
else:
    print("[SPEC] no extra runtime dlls found (using PyInstaller defaults)")


EXTRA_HIDDENIMPORTS = sorted(set(
    collect_submodules("selenium")
    + collect_submodules("webdriver_manager")
    + [
        'shein_login',
        'shein_gui',
        'shein_uploader',
        'shein_asin',
        'shein_sensitive_clean',
        'shein_developer_mode',
        'shein_mysql',
        'webdriver_manager',
        'webdriver_manager.chrome',
        'webdriver_manager.microsoft',
    ]
))

EXTRA_DATAS = collect_data_files("webdriver_manager", include_py_files=False)


a = Analysis(
    [str(PROJECT_DIR / 'shein_main.py')],
    pathex=[str(PROJECT_DIR)],
    binaries=RUNTIME_BINARIES,
    datas=DRIVER_DATAS + EXTRA_DATAS,
    hiddenimports=EXTRA_HIDDENIMPORTS,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='SHEIN_Uploader',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name='SHEIN_Uploader',
)
