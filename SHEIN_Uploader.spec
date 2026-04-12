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
OBF_DIR = PROJECT_DIR / "dist_obf"


def _resolve_entry_script():
    """强制使用加密后的入口脚本，缺失即终止打包。"""
    obf_entry = OBF_DIR / "shein_main.py"
    if obf_entry.is_file():
        print("[SPEC] using obfuscated entry: {}".format(obf_entry))
        return obf_entry
    raise FileNotFoundError(
        "[SPEC] 缺少加密入口: {}。请先执行 PyArmor 生成 dist_obf。".format(obf_entry)
    )


def _assert_obfuscated_artifacts_ready():
    """校验加密产物完整性，避免误打包源码。"""
    required_modules = [
        "shein_main.py",
        "shein_gui.py",
        "shein_uploader.py",
        "shein_checkprice.py",
        "shein_login.py",
        "shein_asin.py",
        "shein_mysql.py",
        "shein_sensitive_clean.py",
        "shein_developer_mode.py",
        "shein_updater.py",
    ]
    missing = []
    if not OBF_DIR.exists():
        missing.append(str(OBF_DIR))
    else:
        for name in required_modules:
            p = OBF_DIR / name
            if not p.is_file():
                missing.append(str(p))
        runtime_dirs = [p for p in OBF_DIR.glob("pyarmor_runtime_*") if p.is_dir()]
        if not runtime_dirs:
            missing.append(str(OBF_DIR / "pyarmor_runtime_*"))
    if missing:
        raise FileNotFoundError(
            "[SPEC] 加密产物不完整，终止打包:\n  - " + "\n  - ".join(missing)
        )
    print("[SPEC] obfuscated artifacts check passed")


def _collect_pyarmor_runtime_datas():
    """自动收集 dist_obf 下的 pyarmor runtime 包目录。"""
    datas = []
    if not OBF_DIR.exists():
        print("[SPEC] dist_obf not found, skip pyarmor runtime datas")
        return datas
    runtime_dirs = [p for p in OBF_DIR.glob("pyarmor_runtime_*") if p.is_dir()]
    if not runtime_dirs:
        print("[SPEC] no pyarmor runtime package found in dist_obf")
        return datas
    for runtime_dir in runtime_dirs:
        for f in runtime_dir.rglob("*"):
            if not f.is_file():
                continue
            rel = f.relative_to(OBF_DIR).as_posix()
            dst = str(Path(rel).parent).replace("\\", "/")
            datas.append((str(f), dst if dst != "." else "."))
    print("[SPEC] bundled pyarmor runtime dirs:")
    for d in runtime_dirs:
        print("  - {}".format(d))
    return datas


def _collect_obfuscated_hiddenimports():
    """自动收集 dist_obf 顶层模块名，避免每次新增加密文件都手工维护。"""
    mods = []
    if not OBF_DIR.exists():
        print("[SPEC] dist_obf not found, skip obfuscated hiddenimports")
        return mods
    for f in OBF_DIR.glob("*.py"):
        if not f.is_file():
            continue
        name = f.stem
        if name.startswith("_") or name == "__init__":
            continue
        mods.append(name)
    mods = sorted(set(mods))
    if mods:
        print("[SPEC] bundled obfuscated modules:")
        for m in mods:
            print("  - {}".format(m))
    else:
        print("[SPEC] no obfuscated python modules found in dist_obf")
    return mods


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
    + collect_submodules("tkinter")
    + collect_submodules("bs4")
    + collect_submodules("PIL")
    + _collect_obfuscated_hiddenimports()
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
        'tkinter',
        'tkinter.ttk',
        'tkinter.messagebox',
        'tkinter.filedialog',
        'tkinter.font',
        '_tkinter',
        'bs4',
        'PIL',
        'PIL.Image',
        'PIL.ImageTk',
    ]
))

EXTRA_DATAS = collect_data_files("webdriver_manager", include_py_files=False)
_assert_obfuscated_artifacts_ready()
PYARMOR_RUNTIME_DATAS = _collect_pyarmor_runtime_datas()
VERSION_FILE = PROJECT_DIR / ".version.json"
if VERSION_FILE.is_file():
    EXTRA_DATAS.append((str(VERSION_FILE), "."))
    print("[SPEC] bundled version file: {}".format(VERSION_FILE))
else:
    print("[SPEC] version file not found, skip: {}".format(VERSION_FILE))


a = Analysis(
    [str(_resolve_entry_script())],
    pathex=[str(OBF_DIR), str(PROJECT_DIR)],
    binaries=RUNTIME_BINARIES,
    datas=DRIVER_DATAS + EXTRA_DATAS + PYARMOR_RUNTIME_DATAS,
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
