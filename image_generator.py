# -*- coding: utf-8 -*-
"""调 SiliconFlow Z-Image-Turbo 给成就生卡面，存到 data/achievement_images/

每张图 PNG 1024×1024，按 image_id 命名（image_id 形如 dim_<dimid>__<slotid>，全局或洞察类似）。
URL 1 小时过期，必须立即下载。
"""
import base64
import logging
import os
import threading
import urllib.request
import urllib.error

import httpx

import config

log = logging.getLogger("progressradar.image")

_inflight_lock = threading.Lock()
_inflight = set()  # image_id 正在生成中

BASE_STYLE = (
    "digital illustration, achievement card art, centered composition, "
    "single subject, no text, no words, no letters, no captions, "
    "clean background, game achievement style"
)

RARITY_STYLE = {
    "common":    "simple, clean, minimal icon style, flat colors, soft palette",
    "uncommon":  "detailed illustration, soft lighting, subtle glow, refined",
    "rare":      "dramatic lighting, vivid colors, epic atmosphere, ornate",
    "epic":      "dramatic lighting, vivid purple highlights, epic atmosphere, particle effects",
    "legendary": "golden glow, cinematic lighting, majestic, masterpiece quality, divine aura",
}

NEGATIVE = "text, letters, words, captions, watermark, signature, blurry, low quality, jpeg artifacts, duplicate, deformed, ugly"


def build_prompt(visual_concept, rarity="common"):
    rs = RARITY_STYLE.get(rarity, RARITY_STYLE["common"])
    return f"{visual_concept}, {BASE_STYLE}, {rs}"


def image_path(image_id):
    return os.path.join(config.IMAGES_DIR, f"{image_id}.png")


def has_image(image_id):
    return os.path.exists(image_path(image_id))


def _download(url, dst):
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    with open(dst, "wb") as f:
        f.write(data)


def generate(image_id, visual_concept, rarity="common", force=False):
    """同步生成一张图，返回保存的本地路径，失败返回 None"""
    if not visual_concept or not visual_concept.strip():
        log.warning("generate: 空 visual_concept, image_id=%s", image_id)
        return None
    if not config.SILICONFLOW_API_KEY:
        log.warning("缺少 SILICONFLOW_API_KEY，跳过生图")
        return None

    dst = image_path(image_id)
    if not force and os.path.exists(dst):
        return dst

    os.makedirs(config.IMAGES_DIR, exist_ok=True)
    prompt = build_prompt(visual_concept, rarity)

    payload = {
        "model": config.SILICONFLOW_IMAGE_MODEL,
        "prompt": prompt,
        "negative_prompt": NEGATIVE,
        "image_size": config.SILICONFLOW_IMAGE_SIZE,
        "num_inference_steps": config.SILICONFLOW_NUM_STEPS,
    }
    headers = {
        "Authorization": f"Bearer {config.SILICONFLOW_API_KEY}",
        "Content-Type": "application/json",
    }

    try:
        # trust_env=False 避免被系统代理拦
        with httpx.Client(trust_env=False, timeout=120.0) as client:
            r = client.post(
                f"{config.SILICONFLOW_BASE_URL}/images/generations",
                headers=headers,
                json=payload,
            )
        if r.status_code != 200:
            log.error("生图失败 image_id=%s status=%d body=%s",
                      image_id, r.status_code, r.text[:300])
            return None
        data = r.json()
    except Exception:
        log.exception("生图请求异常 image_id=%s", image_id)
        return None

    images = data.get("images") or []
    if not images:
        log.error("生图返回空 images: %s", str(data)[:300])
        return None
    item = images[0]
    url = item.get("url")
    b64 = item.get("b64_json")
    try:
        if url:
            _download(url, dst)
        elif b64:
            with open(dst, "wb") as f:
                f.write(base64.b64decode(b64))
        else:
            log.error("生图响应里没有 url/b64_json: %s", str(item)[:200])
            return None
    except Exception:
        log.exception("下载/解码失败 image_id=%s", image_id)
        return None

    log.info("生图 OK: %s (%d bytes)", image_id, os.path.getsize(dst))
    return dst


def generate_async(image_id, visual_concept, rarity="common", on_done=None):
    """后台线程生成；同一 image_id 并发只跑一次"""
    if not visual_concept:
        return
    with _inflight_lock:
        if image_id in _inflight:
            return
        if has_image(image_id):
            return
        _inflight.add(image_id)

    def _run():
        try:
            path = generate(image_id, visual_concept, rarity)
            if on_done:
                try:
                    on_done(image_id, path)
                except Exception:
                    log.exception("on_done 回调异常")
        finally:
            with _inflight_lock:
                _inflight.discard(image_id)

    threading.Thread(target=_run, daemon=True).start()


def read_as_data_url(image_id):
    p = image_path(image_id)
    if not os.path.exists(p):
        return None
    with open(p, "rb") as f:
        b = f.read()
    return "data:image/png;base64," + base64.b64encode(b).decode("ascii")


def status(image_id):
    """ready / inflight / missing"""
    if has_image(image_id):
        return "ready"
    with _inflight_lock:
        if image_id in _inflight:
            return "inflight"
    return "missing"
