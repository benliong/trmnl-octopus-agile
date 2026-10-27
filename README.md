# Octopus Agile — next 24 hours, for TRMNL

An e-ink version of the "Coming up" chart from `daily.html`, for an 800×480 TRMNL:

- **Top:** the current half-hour and its price (vs Flexible), the best 2 hours, the 2 hours to avoid.
- **Chart:** always the next 24 hours (48 bars of fixed width), starting at the current half-hour
  (▲ now). Black = the cheapest third of published half-hours, hatched = the 2 hours to avoid,
  dashed line = Flexible. Before ~4pm, hours not yet priced show as an empty "next prices ~4pm" box.
- **Footer:** "Prices to 23:00 today/tomorrow · drawn HH:MM" — the drawn time tells you how fresh the screen is.

TRMNL polls Octopus's public price API directly: nothing runs on your computer, no API key.

## Why the polling URL has `period_from={{ "now" … }}`

TRMNL only regenerates a screen when the polled data changes. With `period_from` set to the
current time, Octopus returns identical data for the whole half-hour and new data at :00 and :30,
so the screen is redrawn exactly when the current half-hour changes. TRMNL can't wake the device
at exact clock times, so the screen can lag by up to the device refresh interval (15 min, or 5 with TRMNL+).

## Files

| File | Paste into |
|---|---|
| `shared.liquid` | Markup → **Shared** tab (`agileRender()`, used by every layout) |
| `full.liquid`, `half_horizontal.liquid`, `half_vertical.liquid`, `quadrant.liquid` | the matching markup tabs |
| `form_fields.yml` | Settings → **Form Fields** (region A–P, Agile product code, Flexible rate) |
| `icon.png` (from `icon.svg`) | Settings → **Icon** (TRMNL keeps PNG uploads; the SVG didn't stick) |

Styling is TRMNL Framework classes only, no custom CSS. The stat boxes are a Framework grid that
stacks in portrait (`portrait:grid--cols-1`), and their text grows on TRMNL X (`lg:`) and in portrait.
The chart is an SVG that fills whatever height is left and takes its font and size from the Framework's
labels (TRMNL's pixel font on OG, Inter on X). The same markup fits a TRMNL OG (800×480),
TRMNL X (1040×780 CSS px, drawn at 1872×1404) and portrait orientation on both.

## When Octopus can't be reached

Published Agile prices never change, so the screen keeps going on the last prices it fetched:
the "Now" box, best/avoid and chart move on with the clock, and the footer says
"Octopus offline since HH:MM" (anything beyond the old data is marked "Octopus unreachable").
When the old data runs out, or a poll returns nothing, the screen says "Unable to reach Octopus servers".
This relies on TRMNL drawing the screen with the last successful poll's data, which its docs don't spell out.
If a failed poll leaves no data, you get the "Unable to reach" message instead.

## Set up from scratch (private plugin)

Private plugins need TRMNL's Developer add-on (or a BYOD licence).

1. **Plugins → Private Plugin → Add new.** Strategy **Polling**, verb **GET**, polling URL:
   ```
   https://api.octopus.energy/v1/products/{{ product }}/electricity-tariffs/E-1R-{{ product }}-{{ region }}/standard-unit-rates/?page_size=100&period_from={{ "now" | date: "%Y-%m-%dT%H:%M:00%z" | url_encode }}
   ```
2. Paste `form_fields.yml` into **Form Fields**, save, then pick your region (and Flexible rate).
3. Paste the five `.liquid` files into their markup tabs (Shared first) and save each.
4. **Check the data:** markup editor → **Your Variables** → `count` should be the number of
   half-hours from now to the last published one (e.g. 60 at 17:00 once tomorrow is out).
5. Device refresh 15 min (5 with TRMNL+); add to playlist; **Force Refresh**. Within one refresh
   after :00/:30 the Now box moves on; after ~4pm the "next prices" box fills in.

## Preview locally

```
python preview.py                                   # all 4 layouts on an OG, now
python preview.py --screen all                      # OG, OG portrait, TRMNL X, X portrait
python preview.py --at 2026-10-19T10:15 --layout full  # a morning (tomorrow not yet published)
python preview.py --at 2026-10-19T15:10 --fetched-at 2026-10-19T12:05  # Octopus offline since 12:05
python preview.py --no-data                         # a poll that returned nothing
```

Run from this folder after `pip install -r requirements.txt && playwright install chromium`.
Writes `screenshots/trmnl-<screen>-<layout>[-HHMM][-polledHHMM][-nodata].png` plus a 1-bit version approximating the panel.

## Limits

- Polling payload is up to ~9 kB (62 half-hours after 4pm). TRMNL documents a 5 kB cap for
  webhooks but none for polling.
- When Octopus launches a new Agile version (AGILE-24-10-01 → newer), change the "Agile product code" setting.

## Licence

MIT — see `LICENSE`. Not affiliated with Octopus Energy or TRMNL. Contact: ben@forgerelay.uk
