# -*- coding: utf-8 -*-
"""固定一个装了依赖的 pythonw，写桌面快捷方式 + 本地启动 .bat（绝对路径）"""
import os
import sys
import subprocess


REQUIRED = ("webview", "pystray", "PIL", "openai", "keyboard")


def _check_python(exe):
    """返回 True 当且仅当该 exe 能 import 全部依赖"""
    if not exe or not os.path.exists(exe):
        return False
    code = ";".join([f"import {m}" for m in REQUIRED])
    try:
        r = subprocess.run([exe, "-c", code], capture_output=True, timeout=15)
        return r.returncode == 0
    except Exception:
        return False


def _to_pythonw(exe):
    if not exe:
        return exe
    cand = exe.replace("python.exe", "pythonw.exe")
    return cand if os.path.exists(cand) else exe


def _find_python():
    """找到一个装了所有依赖的 python.exe（不是 pythonw）"""
    candidates = []
    candidates.append(sys.executable.replace("pythonw.exe", "python.exe"))
    for env in ("CONDA_PREFIX", "VIRTUAL_ENV"):
        p = os.environ.get(env)
        if p:
            candidates.append(os.path.join(p, "python.exe"))
    for c in ("D:\\anaconda\\python.exe", "D:\\Anaconda\\python.exe",
              "C:\\anaconda\\python.exe", "C:\\Anaconda3\\python.exe"):
        candidates.append(c)
    for c in ("D:\\python\\python.exe", "C:\\Python312\\python.exe",
              "C:\\Python313\\python.exe"):
        candidates.append(c)

    seen = set()
    for c in candidates:
        c = os.path.abspath(c) if c else c
        if c in seen:
            continue
        seen.add(c)
        if _check_python(c):
            return c
    return None


def _write_local_bat(here, pyw, main_py):
    bat = os.path.join(here, "启动 ProgressRadar.bat")
    content = (
        '@echo off\r\n'
        'chcp 65001 >nul\r\n'
        f'cd /d "{here}"\r\n'
        f'start "" "{pyw}" "{main_py}"\r\n'
    )
    with open(bat, "w", encoding="utf-8") as f:
        f.write(content)
    return bat


def _write_debug_bat(here, py, main_py):
    bat = os.path.join(here, "调试启动.bat")
    content = (
        '@echo off\r\n'
        'chcp 65001 >nul\r\n'
        f'cd /d "{here}"\r\n'
        'echo === ProgressRadar 调试模式（保留控制台） ===\r\n'
        'echo 日志同时写到 data\\app.log\r\n'
        'echo.\r\n'
        f'"{py}" main.py --debug\r\n'
        'echo.\r\n'
        'echo === 进程已退出，按任意键关闭 ===\r\n'
        'pause >nul\r\n'
    )
    with open(bat, "w", encoding="utf-8") as f:
        f.write(content)
    return bat


def _write_desktop_lnk(pyw, main_py, here):
    desktop = os.path.join(os.environ["USERPROFILE"], "Desktop")
    if not os.path.isdir(desktop):
        desktop = os.path.join(os.environ["USERPROFILE"], "OneDrive", "Desktop")
    lnk = os.path.join(desktop, "ProgressRadar.lnk")
    ps = (
        f'$s = (New-Object -ComObject WScript.Shell).CreateShortcut("{lnk}");'
        f'$s.TargetPath = "{pyw}";'
        f'$s.Arguments = """{main_py}""";'
        f'$s.WorkingDirectory = "{here}";'
        f'$s.IconLocation = "{pyw},0";'
        f'$s.Description = "ProgressRadar — AI 个人进度追踪";'
        f'$s.Save()'
    )
    subprocess.run(["powershell", "-NoProfile", "-Command", ps], check=True)
    return lnk


def main():
    here = os.path.dirname(os.path.abspath(__file__))
    main_py = os.path.join(here, "main.py")

    py = _find_python()
    if py is None:
        print("[error] 找不到装了所有依赖的 Python。")
        print(f"        当前解释器: {sys.executable}")
        print(f"        请先在装好依赖的环境中执行: pip install -r requirements.txt")
        sys.exit(1)
    pyw = _to_pythonw(py)
    print(f"[ok] 锁定解释器: {py}")
    print(f"     无窗口启动: {pyw}")

    bat = _write_local_bat(here, pyw, main_py)
    print(f"[ok] 启动脚本: {bat}")

    dbg = _write_debug_bat(here, py, main_py)
    print(f"[ok] 调试脚本: {dbg}")

    lnk = _write_desktop_lnk(pyw, main_py, here)
    print(f"[ok] 桌面快捷方式: {lnk}")


if __name__ == "__main__":
    main()
