# -*- coding: utf-8 -*-
"""ProgressRadar v2 桌面客户端入口"""
import os
import sys
import threading

import logging_setup
log = logging_setup.setup()

try:
    import webview
    import config
    from api import API
    import tray
except Exception:
    log.exception("启动期 import 失败")
    raise


def _ui_path(name):
    return os.path.join(os.path.dirname(os.path.abspath(__file__)), "ui", name)


def _on_close(window, name):
    log.info("窗口[%s] 收到关闭事件 → hide", name)
    try:
        window.hide()
    except Exception:
        log.exception("hide 失败")
    return False


def _register_hotkey(paste_window):
    try:
        import keyboard
    except Exception:
        log.exception("keyboard 库不可用，跳过全局热键")
        return

    def show():
        log.info("热键触发 → 显示快速粘贴窗口")
        try:
            paste_window.show()
        except Exception:
            log.exception("paste_window.show 失败")

    try:
        keyboard.add_hotkey("ctrl+shift+p", show)
        log.info("全局热键 Ctrl+Shift+P 已注册")
    except Exception:
        log.exception("注册全局热键失败")


def main():
    log.info("启动参数: %s", sys.argv)
    os.makedirs(config.DATA_DIR, exist_ok=True)
    os.makedirs(config.WEEKLY_DIR, exist_ok=True)

    api = API()

    start_hidden = "--silent" in sys.argv
    try:
        main_window = webview.create_window(
            "ProgressRadar",
            _ui_path("dashboard.html"),
            js_api=api,
            width=1100,
            height=720,
            min_size=(720, 480),
            hidden=start_hidden,
        )
        paste_window = webview.create_window(
            "快速粘贴",
            _ui_path("input.html"),
            js_api=api,
            width=560,
            height=420,
            min_size=(420, 320),
            hidden=True,
            on_top=True,
        )
    except Exception:
        log.exception("create_window 失败")
        raise

    api.set_windows(main_window, paste_window)

    main_window.events.closing += lambda: _on_close(main_window, "dashboard")
    paste_window.events.closing += lambda: _on_close(paste_window, "paste")

    def on_quit():
        log.info("用户从托盘点击退出")
        try:
            main_window.destroy()
        except Exception:
            log.exception("destroy main 失败")
        try:
            paste_window.destroy()
        except Exception:
            log.exception("destroy paste 失败")

    def _tray_thread():
        try:
            tray.create_tray(main_window, paste_window, on_quit)
        except Exception:
            log.exception("托盘线程崩溃")

    threading.Thread(target=_tray_thread, daemon=True).start()
    threading.Thread(target=_register_hotkey, args=(paste_window,), daemon=True).start()

    log.info("ProgressRadar 已启动 — 托盘左键=Dashboard，Ctrl+Shift+P=快速粘贴 (--silent 可静默启动)")
    try:
        webview.start(debug=("--debug" in sys.argv))
    except Exception:
        log.exception("webview.start 崩溃")
        raise
    log.info("webview.start 返回，进程退出")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        log.exception("main 崩溃")
        raise
