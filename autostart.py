# -*- coding: utf-8 -*-
"""注册/取消 Windows 开机自启（startup 文件夹 .bat 方案）"""
import os
import sys


def _startup_dir():
    return os.path.join(
        os.environ["APPDATA"], "Microsoft", "Windows", "Start Menu", "Programs", "Startup"
    )


def _bat_path():
    return os.path.join(_startup_dir(), "ProgressRadar.bat")


def register():
    startup = _startup_dir()
    os.makedirs(startup, exist_ok=True)
    bat = _bat_path()
    pyw = sys.executable.replace("python.exe", "pythonw.exe")
    if not os.path.exists(pyw):
        pyw = sys.executable
    main_py = os.path.abspath(os.path.join(os.path.dirname(__file__), "main.py"))
    workdir = os.path.dirname(main_py)
    content = (
        '@echo off\r\n'
        f'cd /d "{workdir}"\r\n'
        f'start "" /B "{pyw}" "{main_py}"\r\n'
    )
    with open(bat, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"[ok] 开机自启已注册：{bat}")
    print(f"     使用解释器：{pyw}")


def unregister():
    bat = _bat_path()
    if os.path.exists(bat):
        os.remove(bat)
        print(f"[ok] 开机自启已移除：{bat}")
    else:
        print("[skip] 没有发现已注册的自启项")


def status():
    bat = _bat_path()
    if os.path.exists(bat):
        print(f"[on]  {bat}")
        with open(bat, "r", encoding="utf-8") as f:
            print(f.read())
    else:
        print("[off] 未注册")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "register"
    if cmd == "register":
        register()
    elif cmd == "unregister":
        unregister()
    elif cmd == "status":
        status()
    else:
        print("用法: python autostart.py [register|unregister|status]")
