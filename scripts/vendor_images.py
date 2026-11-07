#!/usr/bin/env python3
"""Download all site <img> photos into GitHub Pages assets and rewrite image URLs.

Run from repository root. Source images are kept only in this maintenance script;
the published HTML depends exclusively on local assets/images/*.webp files.
"""
from __future__ import annotations

from html import unescape
from io import BytesIO
from pathlib import Path
import re
import sys
from urllib.parse import quote, urlparse

import requests
from PIL import Image, UnidentifiedImageError, ImageOps

ROOT = Path(__file__).resolve().parents[1]
INDEX = ROOT / "index.html"
ASSETS = ROOT / "assets" / "images"
NAMES = [
    "brand-logo",
    "hero-interior",
    "service-hair",
    "service-nails",
    "service-cosmetology",
    "service-brows-lashes",
    "service-depilation",
    "salon-interior",
    "master-olesya",
    "master-svetlana-usacheva",
    "master-elena-poshibaylova",
    "master-anastasia-titkova",
    "master-melanya-loretsyan",
    "master-irina-gribina",
    "master-inga-papoyan",
    "master-zhanna-prakina",
    "master-anna-baranovskaya",
]
UA = "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
SESSION = requests.Session()
IMAGE_RX = re.compile(r'<img\b[^>]*?\bsrc="(https?[^"]+)"', re.I | re.S)


def candidates(original: str):
    """Try source first; only use image proxy as a build-time fallback."""
    yield original
    encoded = quote(original, safe="")
    yield "https://wsrv.nl/?url=" + encoded
    yield "https://images.weserv.nl/?url=" + encoded


def fetch_image(source: str):
    errors = []
    host = urlparse(source).hostname or ""
    referer = ("https://n768387.yclients.com/" if "yclients.com" in host
               else "https://yandex.ru/" if "yandex.net" in host else "https://www.google.com/")
    for uri in candidates(source):
        try:
            response = SESSION.get(uri, headers={"User-Agent": UA, "Accept": "image/avif,image/webp,image/png,image/jpeg,image/*;q=0.8,*/*;q=0.5", "Referer": referer}, timeout=(15, 35))
            response.raise_for_status()
            if not response.content or len(response.content) < 100:
                raise ValueError("too small or empty")
            img = Image.open(BytesIO(response.content))
            img.load()
            if img.width < 32 or img.height < 32:
                raise ValueError(f"image resolution {img.width}x{img.height} is too small")
            return img, uri
        except Exception as exc:
            errors.append(f"{urlparse(uri).hostname}: {type(exc).__name__}: {exc}")
    raise RuntimeError("Image unavailable; " + " | ".join(errors))


def main():
    source = INDEX.read_text(encoding="utf-8")
    urls = list(dict.fromkeys(IMAGE_RX.findall(source)))
    if len(urls) != len(NAMES):
        raise SystemExit(f"Expected exactly {len(NAMES)} original images; found {len(urls)}. No files modified.")

    # Download every image before updating HTML to prevent half-bundled websites.
    prepared = []
    failures = []
    for idx, (raw, name) in enumerate(zip(urls, NAMES), start=1):
        uri = unescape(raw)
        print(f"[{idx}/{len(urls)}] {name}: {urlparse(uri).hostname}", flush=True)
        try:
            img, source_used = fetch_image(uri)
            img = ImageOps.exif_transpose(img)
            img.thumbnail((1800, 1800), Image.Resampling.LANCZOS)
            if "A" in img.getbands():
                img = img.convert("RGBA")
            else:
                img = img.convert("RGB")
            bio = BytesIO()
            img.save(bio, format="WEBP", quality=85, method=6)
            prepared.append((raw, name, bio.getvalue()))
            print(f"    {img.width}x{img.height} -> {len(bio.getvalue())} bytes (via {urlparse(source_used).hostname})", flush=True)
        except Exception as err:
            failures.append((name, str(err)))
            print(f"FAILED: {name}: {err}", file=sys.stderr, flush=True)
    if failures:
        print("Could not bundle every image. Original HTML will not be changed.", file=sys.stderr)
        for name, err in failures:
            print(f"  {name}: {err}", file=sys.stderr)
        raise SystemExit(1)

    ASSETS.mkdir(parents=True, exist_ok=True)
    rewritten = source
    for original, name, data in prepared:
        target = ASSETS / f"{name}.webp"
        target.write_bytes(data)
        local = f"assets/images/{name}.webp"
        if rewritten.count(original) != 1:
            raise RuntimeError(f"Expected exactly one use of source {name}")
        rewritten = rewritten.replace(original, local, 1)
    leftovers = IMAGE_RX.findall(rewritten)
    if leftovers:
        raise RuntimeError(f"Remote image sources remain: {leftovers}")
    INDEX.write_text(rewritten, encoding="utf-8")
    print(f"Bundled {len(prepared)} pictures; none of the published <img> tags use remote hosts.", flush=True)


if __name__ == "__main__":
    main()
