# -*- coding: utf-8 -*-
"""系统托盘：常驻图标、右键菜单、窗口控制"""
import logging
from PIL import Image, ImageDraw
from pystray import Icon, MenuItem, Menu

log = logging.getLogger("progressradar.tray")


def _make_icon_image(size=64):
    """编程绘制蓝色圆点图标，避免依赖外部 png"""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    pad = 8
    d.ellipse((pad, pad, size - pad, size - pad), fill=(55, 138, 221, 255))
    d.ellipse((size//2 - 6, size//2 - 6, size//2 + 6, size//2 + 6), fill=(255, 255, 255, 230))
    return img


def create_tray(main_window, paste_window, on_quit):
    icon_image = _make_icon_image()

    def show_dashboard(icon, item):
        try:
            main_window.show()
        except Exception:
            pass

    def quick_paste(icon, item):
        try:
            paste_window.show()
        except Exception:
            pass

    def quit_app(icon, item):
        on_quit()
        icon.stop()

    menu = Menu(
        MenuItem("打开 Dashboard", show_dashboard, default=True),
        MenuItem("快速粘贴", quick_paste),
        Menu.SEPARATOR,
        MenuItem("退出", quit_app),
    )

    icon = Icon("ProgressRadar", icon_image, "ProgressRadar", menu)
    log.info("托盘图标已创建，开始 run()…")
    try:
        icon.run()
    except Exception:
        log.exception("托盘 run() 崩溃")
    log.info("托盘 run() 返回（图标已退出）")
