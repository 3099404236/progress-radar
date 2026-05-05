# -*- coding: utf-8 -*-
"""统一日志：写到 data/app.log，pythonw 下捕获 stdout/stderr 与未捕获异常"""
import logging
import os
import sys
import traceback
from logging.handlers import RotatingFileHandler

import config


_configured = False


class _StreamToLogger:
    def __init__(self, level):
        self.level = level
        self._buf = ""

    def write(self, msg):
        if not msg:
            return
        self._buf += msg
        while "\n" in self._buf:
            line, self._buf = self._buf.split("\n", 1)
            line = line.rstrip()
            if line:
                logging.log(self.level, line)

    def flush(self):
        if self._buf.strip():
            logging.log(self.level, self._buf.strip())
        self._buf = ""

    def isatty(self):
        return False


def _excepthook(exc_type, exc, tb):
    logging.error("UNCAUGHT EXCEPTION", exc_info=(exc_type, exc, tb))


def setup():
    global _configured
    if _configured:
        return logging.getLogger("progressradar")

    os.makedirs(config.DATA_DIR, exist_ok=True)
    log_path = os.path.join(config.DATA_DIR, "app.log")

    fmt = logging.Formatter(
        "%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    fh = RotatingFileHandler(log_path, maxBytes=512 * 1024, backupCount=3, encoding="utf-8")
    fh.setFormatter(fmt)
    fh.setLevel(logging.INFO)

    root = logging.getLogger()
    root.setLevel(logging.INFO)
    for h in list(root.handlers):
        root.removeHandler(h)
    root.addHandler(fh)

    if sys.stdout and hasattr(sys.stdout, "isatty") and sys.stdout.isatty():
        ch = logging.StreamHandler(sys.stdout)
        ch.setFormatter(fmt)
        ch.setLevel(logging.INFO)
        root.addHandler(ch)

    # pythonw: stdout/stderr 是 None 或丢弃 → 重定向到日志
    if sys.stdout is None or not hasattr(sys.stdout, "isatty") or not sys.stdout.isatty():
        sys.stdout = _StreamToLogger(logging.INFO)
        sys.stderr = _StreamToLogger(logging.WARNING)

    sys.excepthook = _excepthook

    # 压低噪音库
    for name in ("webview", "pywebview", "bottle", "urllib3", "openai",
                 "httpx", "httpcore", "PIL", "comtypes"):
        logging.getLogger(name).setLevel(logging.WARNING)

    _configured = True
    log = logging.getLogger("progressradar")
    log.info("=" * 60)
    log.info("logger ready, file=%s, py=%s, exe=%s", log_path, sys.version.split()[0], sys.executable)
    return log


def get_log_path():
    return os.path.join(config.DATA_DIR, "app.log")
