"""Render the TRMNL recipe (shared.liquid + each layout) locally with live Agile prices.

Fills the Liquid tags the template uses, wraps it in TRMNL's framework at 800×480,
and saves screenshots/trmnl-agile[-<at>].png plus a 1-bit (pure black/white) version that
approximates the e-ink panel. No API key needed: the price endpoint is public.

    python preview.py [--at 2026-10-19T10:15] [--tariff E-1R-AGILE-24-10-01-J] [--flex 26.88]
    python preview.py --at 2026-10-19T15:10 --fetched-at 2026-10-19T12:05   # Octopus unreachable since 12:05
    python preview.py --no-data                                             # a poll that returned nothing

--at simulates the screen at another London time: the browser clock is frozen there and
only prices that would have been published by then are shown (next day appears ~16:00).
--fetched-at draws at --at using data from an earlier poll, as when later polls have failed.
"""
from __future__ import annotations

import argparse
import base64
import json
from pathlib import Path

import pandas as pd
import requests
from playwright.sync_api import sync_playwright

HERE = Path(__file__).resolve().parent
OUT = HERE / "screenshots"
URL = ("https://api.octopus.energy/v1/products/{product}/electricity-tariffs/{tariff}/standard-unit-rates/"
       "?page_size=100&period_from={period_from}")

WRAP = """<!doctype html><html><head><meta charset="utf-8">
<link rel="stylesheet" href="https://trmnl.com/css/latest/plugins.css">
<script src="https://trmnl.com/js/latest/plugins.js"></script></head>
<body class="environment trmnl" style="margin:0"><div class="screen {screen_cls}">{body}</div></body></html>"""
SCREENS = {  # name -> (width, height, extra .screen classes)
    "og": (800, 480, "screen--og screen--md screen--1bit"),
    "og-portrait": (480, 800, "screen--og screen--md screen--1bit screen--portrait"),
    "x": (1872, 1404, "screen--v2 screen--lg screen--4bit"),  # 1040×780 CSS px, scaled 1.8 by the framework
    "x-portrait": (1404, 1872, "screen--v2 screen--lg screen--4bit screen--portrait"),
}
# layout -> (mashup class or None, number of view slots); our view goes in the first slot.
LAYOUTS = {
    "full": (None, 1),
    "half_horizontal": ("mashup mashup--1Tx1B", 2),
    "half_vertical": ("mashup mashup--1Lx1R", 2),
    "quadrant": ("mashup mashup--2x2", 4),
}

THRESHOLD = """async (png) => {
  const img = new Image(); img.src = 'data:image/png;base64,' + png; await img.decode();
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const x = c.getContext('2d'); x.drawImage(img, 0, 0);
  const d = x.getImageData(0, 0, c.width, c.height);
  for (let i = 0; i < d.data.length; i += 4) {
    const v = (d.data[i] * 0.3 + d.data[i + 1] * 0.59 + d.data[i + 2] * 0.11) < 128 ? 0 : 255;
    d.data[i] = d.data[i + 1] = d.data[i + 2] = v;
  }
  x.putImageData(d, 0, 0); return c.toDataURL('image/png').split(',')[1];
}"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--product", default="AGILE-24-10-01")
    ap.add_argument("--tariff", default="E-1R-AGILE-24-10-01-J")
    ap.add_argument("--flex", default="26.88")
    ap.add_argument("--at", help="London local time to simulate, e.g. 2026-10-19T10:15")
    ap.add_argument("--fetched-at", help="London time of the last successful poll (default: --at)")
    ap.add_argument("--no-data", action="store_true", help="simulate a poll that returned no prices")
    ap.add_argument("--layout", choices=[*LAYOUTS, "all"], default="all")
    ap.add_argument("--screen", choices=[*SCREENS, "all"], default="og")
    a = ap.parse_args()

    at = (pd.Timestamp(a.at).tz_localize("Europe/London") if a.at else pd.Timestamp.now(tz="Europe/London"))
    polled = pd.Timestamp(a.fetched_at).tz_localize("Europe/London") if a.fetched_at else at
    period_from = polled.tz_convert("UTC").strftime("%Y-%m-%dT%H:%M:00Z")  # what TRMNL's Liquid date produces
    resp = requests.get(URL.format(product=a.product, tariff=a.tariff, period_from=period_from), timeout=30)
    resp.raise_for_status()
    results = resp.json()["results"]
    if a.at or a.fetched_at:  # hide prices not yet published when polled (next day lands ~16:00)
        day = polled.normalize()
        cutoff = day + pd.Timedelta(hours=23) + (pd.Timedelta(days=1) if polled.hour >= 16 else pd.Timedelta(0))
        results = [r for r in results if pd.Timestamp(r["valid_to"]) <= cutoff]
    if a.no_data:
        results = []
    print(f"{at:%a %H:%M}: {len(results)} slots, polling payload ≈ {len(json.dumps(results)) / 1024:.1f} kB")

    shared = (HERE / "shared.liquid").read_text()
    shared = shared.replace("{{ results | json }}", json.dumps(results))
    shared = shared.replace("{{ trmnl.plugin_settings.custom_fields_values.flexible_price }}", a.flex)
    assert "{{" not in shared.split("-->", 1)[1], "unfilled Liquid tag"

    OUT.mkdir(exist_ok=True)
    layouts = list(LAYOUTS) if a.layout == "all" else [a.layout]
    screens = list(SCREENS) if a.screen == "all" else [a.screen]
    with sync_playwright() as p:
        b = p.chromium.launch()
        for scr, name in [(x, y) for x in screens for y in layouts]:
            sw, sh, scls = SCREENS[scr]
            mashup, n = LAYOUTS[name]
            view = f'<div class="view view--{name}">{shared}{(HERE / f"{name}.liquid").read_text()}</div>'
            blank = f'<div class="view view--{name}"><div class="layout"></div></div>'
            body = view if mashup is None else f'<div class="{mashup}">{view}{blank * (n - 1)}</div>'
            pg = b.new_page(viewport={"width": sw, "height": sh}, timezone_id="Europe/London")
            pg.clock.set_fixed_time(at.to_pydatetime())
            errors = []
            pg.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
            pg.on("pageerror", lambda e: errors.append(str(e)))
            pg.set_content(WRAP.format(body=body, screen_cls=scls, w=sw, h=sh), wait_until="networkidle")
            stem = (f"trmnl-{scr}-{name}" + (f"-{at:%H%M}" if a.at else "") +
                    (f"-polled{polled:%H%M}" if a.fetched_at else "") + ("-nodata" if a.no_data else ""))
            png = pg.screenshot(path=str(OUT / f"{stem}.png"))
            bw = pg.evaluate(THRESHOLD, base64.b64encode(png).decode())
            (OUT / f"{stem}-1bit.png").write_bytes(base64.b64decode(bw))
            overflow = pg.evaluate("[...document.querySelectorAll('.view')][0].scrollHeight > "
                                   "[...document.querySelectorAll('.view')][0].clientHeight + 1")
            pg.close()
            print(f"{scr:<10} {name:<16} console errors: {errors or 'none'} | overflow: {overflow} | {OUT / (stem + '-1bit.png')}")
        b.close()


if __name__ == "__main__":
    main()
