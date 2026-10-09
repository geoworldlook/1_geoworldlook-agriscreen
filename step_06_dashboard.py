"""
================================================================================
AgriWatch - KROK 6: DASHBOARD WINNICY (wzór: panel Wago, projekt ESA WineEO)
================================================================================
Jeden samodzielny plik HTML dla jednej winnicy, wyświetlany w Colab i zapisywany obok biuletynu:

  ┌ Działka ────────┬ Mapa NDVI 2,5 m na zdjęciu satelitarnym ┬ Status (komunikat) ┬ Ryzyko suszy (wskaźnik) ┐
  │ nazwa, ha,      │ wybór daty sceny, obrys działki          ├ Pogoda: ostatnie 10 dni (ERA5-Land) + prognoza 7 dni ┤
  │ źródła, pewność │                                          ├ Przyczyny: SPI-1, SPI-3, gleba, roślinność, pewność  ┤
  └─────────────────┴─ Wykres: ostatnie 12 miesięcy ─────────────┴─ Wiarygodność: walidacja na ISMN Condom ───────────┘

Różnica wobec Wago: zamiast zalecenia nawadniania („podlej 35 mm”) mówimy o anomalii wilgotności
(„sprawdź winnicę”). Dane wyłącznie z wyników zadań step_05 (status_dekads.csv, veg_anomalies.csv,
validation_anomalies.csv, ERA5-Land) i z wycinków NDVI działki zapisywanych w task_scene_stats.
Prognoza pogody: Open-Meteo (bez klucza); brak sieci = panel prognozy pominięty, reszta działa.
================================================================================
"""

from __future__ import annotations

import base64
import glob
import html
import io
import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("AgriWatch_Dashboard")

STATUS_PL = {
    "normal": ("Norma", "Opad i wilgotność gleby w normie dla tej pory roku.", "#3a9d4f"),
    "recovery": ("Powrót do normy", "Po okresie suszy; anomalie jeszcze ujemne.", "#4f8fd6"),
    "watch": ("Obserwuj", "Mniej opadu niż zwykle; gleba jeszcze w normie.", "#e0b400"),
    "warning": ("Sucho", "Gleba wyraźnie suchsza niż zwykle o tej porze roku.", "#f08a24"),
    "alert": ("Sprawdź winnicę", "Gleba sucha i roślinność tej winnicy słabsza niż w innych latach.", "#d63a2f"),
}
GAUGE_LEVEL = {"normal": 0.1, "recovery": 0.3, "watch": 0.45, "warning": 0.7, "alert": 0.92}
SITE_CLIP_DIR = "site_ndvi"          # podkatalog SR_DIR z wycinkami NDVI działki
SITE_CLIP_MARGIN_M = 30.0


# ==============================================================================
# I. WYCINKI NDVI DZIAŁKI (zapisywane w task_scene_stats, czytane przez dashboard)
# ==============================================================================

def save_site_ndvi(ndvi: np.ndarray, profile: Dict[str, Any], geom, out_path: str,
                   margin_m: float = SITE_CLIP_MARGIN_M) -> Optional[str]:
    """Wycina NDVI w prostokącie działki (+ margines) i zapisuje GeoTIFF int16 (skala 10 000)."""
    import rasterio
    from rasterio.windows import from_bounds

    x0, y0, x1, y1 = geom.bounds
    t = profile["transform"]
    win = from_bounds(x0 - margin_m, y0 - margin_m, x1 + margin_m, y1 + margin_m, t).round_offsets().round_lengths()
    r0, c0 = max(int(win.row_off), 0), max(int(win.col_off), 0)
    r1, c1 = min(r0 + int(win.height), ndvi.shape[0]), min(c0 + int(win.width), ndvi.shape[1])
    if r1 <= r0 or c1 <= c0:
        return None
    sub = ndvi[r0:r1, c0:c1]
    data = np.where(np.isfinite(sub), np.round(sub * 10000), -32768).astype("int16")
    prof = {"driver": "GTiff", "dtype": "int16", "count": 1, "height": data.shape[0], "width": data.shape[1],
            "crs": profile["crs"], "transform": rasterio.windows.transform(
                rasterio.windows.Window(c0, r0, c1 - c0, r1 - r0), t),
            "nodata": -32768, "compress": "deflate"}
    os.makedirs(os.path.dirname(out_path) or ".", exist_ok=True)
    with rasterio.open(out_path, "w", **prof) as dst:
        dst.write(data, 1)
    return out_path


def _site_clips(cfg: Dict[str, Any], site_id: str) -> List[Dict[str, Any]]:
    """
    Wycinki NDVI działki [{date, path, product}], najnowsze na końcu. Produkt detekcji (VEG_PRODUCT) ma
    pierwszeństwo; daty bez niego uzupełnia drugi produkt (np. sceny jeszcze bez SR).
    """
    found = []
    for p in sorted(glob.glob(os.path.join(cfg["SR_DIR"], SITE_CLIP_DIR, site_id, "*_NDVI_*.tif"))):
        m = re.search(r"(\d{8})_NDVI_(2\.5m|10m)\.tif$", os.path.basename(p))
        if m:
            found.append({"date": pd.Timestamp(m.group(1)), "path": p,
                          "product": "S2SR_2.5m" if m.group(2) == "2.5m" else "S2_10m"})
    by_date: Dict[pd.Timestamp, Dict[str, Any]] = {}
    for r in found:
        if r["date"] not in by_date or r["product"] == cfg.get("VEG_PRODUCT"):
            by_date[r["date"]] = r
    return [by_date[k] for k in sorted(by_date)]


def _clips_from_s2(cfg: Dict[str, Any], geom_utm, site_id: str, n: int = 8) -> List[Dict[str, Any]]:
    """Zapasowo (brak wycinków SR): NDVI 10 m z ostatnich bezchmurnych scen S-2 nad działką."""
    import step_01_ingest as s1
    import step_04_metrics_alert as s4
    from rasterio.features import geometry_mask

    out = []
    for path in sorted(glob.glob(os.path.join(cfg["S2_DIR"], "S2_L2A_*.tif")))[::-1]:
        if len(out) >= n:
            break
        data, prof = s1.read_geotiff_to_numpy(path)
        mask = geometry_mask([geom_utm], out_shape=data.shape[1:], transform=prof["transform"], invert=True)
        cloud = np.nan_to_num(data[s4.RASTER_CLOUD_BAND], nan=1.0)
        if mask.sum() == 0 or (cloud[mask] == 0).mean() < 0.9:
            continue
        ndvi = s4.compute_indices(data[:10])["ndvi"]
        ndvi = np.where(cloud == 0, ndvi, np.nan)
        t = s4.scene_time(path)
        p = os.path.join(cfg["SR_DIR"], SITE_CLIP_DIR, site_id, f"{t:%Y%m%d}_NDVI_10m.tif")
        if save_site_ndvi(ndvi, prof, geom_utm, p):
            out.append({"date": t.normalize(), "path": p, "product": "S2_10m"})
    return sorted(out, key=lambda r: r["date"])


# ==============================================================================
# II. ELEMENTY GRAFICZNE
# ==============================================================================

def _png_b64(fig) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=110, bbox_inches="tight", transparent=True)
    import matplotlib.pyplot as plt
    plt.close(fig)
    return base64.b64encode(buf.getvalue()).decode()


def _ndvi_overlay(path: str, geom_wgs84) -> Optional[Dict[str, Any]]:
    """Wycinek NDVI -> EPSG:4326, kolory jak w Wago (czerwony = słaba roślinność, zielony = silna), poza działką przezroczysty."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    import rasterio
    from rasterio.features import geometry_mask
    from rasterio.warp import calculate_default_transform, reproject, Resampling

    with rasterio.open(path) as src:
        a = src.read(1).astype("float32")
        a[a == src.nodata] = np.nan
        a /= 10000.0
        dst_t, w, h = calculate_default_transform(src.crs, "EPSG:4326", src.width, src.height, *src.bounds)
        dst = np.full((h, w), np.nan, "float32")
        reproject(a, dst, src_transform=src.transform, src_crs=src.crs, dst_transform=dst_t, dst_crs="EPSG:4326",
                  resampling=Resampling.nearest, src_nodata=np.nan, dst_nodata=np.nan)
    inside = geometry_mask([geom_wgs84], out_shape=dst.shape, transform=dst_t, invert=True)
    vals = dst[inside & np.isfinite(dst)]
    if vals.size == 0:
        return None
    rgba = plt.get_cmap("RdYlGn")(np.clip((dst - 0.15) / (0.75 - 0.15), 0, 1))
    rgba[..., 3] = np.where(inside & np.isfinite(dst), 0.85, 0.0)
    fig = plt.figure(figsize=(w / 100, h / 100), dpi=100)
    ax = fig.add_axes([0, 0, 1, 1])
    ax.imshow(rgba, interpolation="nearest")
    ax.axis("off")
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, transparent=True)
    plt.close(fig)
    west, north = dst_t.c, dst_t.f
    east, south = west + dst_t.a * w, north + dst_t.e * h
    return {"png": base64.b64encode(buf.getvalue()).decode(), "bounds": [[south, west], [north, east]],
            "mean": float(np.nanmean(vals)), "p10": float(np.nanpercentile(vals, 10)),
            "p90": float(np.nanpercentile(vals, 90))}


def _gauge_svg(level: float, color: str) -> str:
    """Półokrągły wskaźnik ryzyka (jak „Water stress risk” w Wago): 4 strefy, wskazówka na poziomie 0–1."""
    import math
    cx, cy, r = 110, 100, 80
    arcs = []
    for i, c in enumerate(("#3a9d4f", "#e0b400", "#f08a24", "#d63a2f")):
        a0, a1 = math.pi * (1 - i / 4), math.pi * (1 - (i + 1) / 4)
        x0, y0 = cx + r * math.cos(a0), cy - r * math.sin(a0)
        x1, y1 = cx + r * math.cos(a1), cy - r * math.sin(a1)
        arcs.append(f'<path d="M{x0:.1f},{y0:.1f} A{r},{r} 0 0 1 {x1:.1f},{y1:.1f}" stroke="{c}" '
                    f'stroke-width="18" fill="none"/>')
    ang = math.pi * (1 - level)
    nx, ny = cx + (r - 18) * math.cos(ang), cy - (r - 18) * math.sin(ang)
    return (f'<svg viewBox="0 0 220 120" width="100%">{"".join(arcs)}'
            f'<line x1="{cx}" y1="{cy}" x2="{nx:.1f}" y2="{ny:.1f}" stroke="#333" stroke-width="4" stroke-linecap="round"/>'
            f'<circle cx="{cx}" cy="{cy}" r="6" fill="#333"/></svg>')


def fetch_forecast(lat: float, lon: float, days: int = 7, timeout: int = 15) -> Optional[pd.DataFrame]:
    """Prognoza dzienna Open-Meteo (opad, Tmin, Tmax, ET0 FAO). Brak sieci lub błąd = None."""
    try:
        import requests
        r = requests.get("https://api.open-meteo.com/v1/forecast", timeout=timeout, params={
            "latitude": lat, "longitude": lon, "forecast_days": days, "timezone": "Europe/Paris",
            "daily": "precipitation_sum,temperature_2m_max,temperature_2m_min,et0_fao_evapotranspiration"})
        r.raise_for_status()
        d = r.json()["daily"]
        return pd.DataFrame({"date": pd.to_datetime(d["time"]), "precip_mm": d["precipitation_sum"],
                             "tmax": d["temperature_2m_max"], "tmin": d["temperature_2m_min"],
                             "et0_mm": d["et0_fao_evapotranspiration"]})
    except Exception as e:
        logger.warning(f"Prognoza Open-Meteo niedostępna: {e}")
        return None


def _fmt(x, nd=1, suffix=""):
    try:
        return "—" if x is None or not np.isfinite(float(x)) else f"{float(x):.{nd}f}{suffix}".replace(".", ",")
    except (TypeError, ValueError):
        return "—"


# ==============================================================================
# III. DASHBOARD
# ==============================================================================

def build_dashboard(rt: Dict[str, Any], cfg: Dict[str, Any], forecast: bool = True, max_dates: int = 12) -> str:
    """Buduje dashboard.html w OUTPUT_DIR i zwraca jego ścieżkę."""
    import geopandas as gpd
    from shapely.geometry import mapping

    from step_05_colab_run import sr_coverage

    out_dir = cfg["OUTPUT_DIR"]
    sid = cfg["MAIN_SITE"]
    status = pd.read_csv(os.path.join(out_dir, "status_dekads.csv"))
    st = status[status["site_id"] == sid].sort_values("date")
    if st.empty:
        raise RuntimeError(f"Brak statusu dla {sid}: uruchom task_anomalies.")
    cur = st.iloc[-1]
    vpath = os.path.join(out_dir, "validation_anomalies.csv")
    val = pd.read_csv(vpath) if os.path.exists(vpath) else pd.DataFrame()
    era5 = pd.read_csv(os.path.join(cfg["ERA5_DIR"], "era5_land_daily.csv"), parse_dates=["time"])

    parcels = gpd.read_file(cfg["PARCELS_PATH"])
    pg = parcels.loc[parcels["fid"] == cfg["VINEYARDS"][sid]]
    geom_utm = pg.to_crs(cfg["EPSG"]).geometry.iloc[0]
    geom_ll = pg.to_crs(4326).geometry.iloc[0]
    c = geom_ll.centroid
    area_ha = geom_utm.area / 1e4

    # --- Mapa: wycinki NDVI (SR 2,5 m, a gdy ich brak — 10 m z ostatnich scen) ---
    clips = _site_clips(cfg, sid)
    if not clips:
        clips = _clips_from_s2(cfg, geom_utm, sid)
    m0, m1 = cfg["S2_MONTHS"]
    season = [r for r in clips if m0 <= r["date"].month <= m1] or clips
    layers = []
    for r in season[-max_dates:]:
        ov = _ndvi_overlay(r["path"], geom_ll)
        if ov:
            ov.update(date=r["date"].strftime("%Y-%m-%d"), product=r["product"])
            layers.append(ov)
    layers = layers[::-1]                                  # najnowsza pierwsza na liście

    # --- Anomalia NDVI dla dat z mapy ---
    veg_path = os.path.join(out_dir, "veg_anomalies.csv")
    veg = pd.read_csv(veg_path, parse_dates=["time"]) if os.path.exists(veg_path) else pd.DataFrame()
    if len(veg):
        vv = veg[(veg["site_id"] == sid) & (veg["index"] == "ndvi")].copy()
        vv["d"] = vv["time"].dt.strftime("%Y-%m-%d")
        for ly in layers:
            m = vv[(vv["d"] == ly["date"]) & (vv["product"] == ly["product"])]
            ly["z"] = float(m["z"].iloc[0]) if len(m) else None

    # --- Pogoda: ostatnie 10 dni ERA5-Land i prognoza ---
    e = era5.sort_values("time").tail(10)
    fc = fetch_forecast(c.y, c.x) if forecast else None

    # --- Wykres 12 miesięcy (z biuletynu) ---
    chart = ""
    p = os.path.join(out_dir, "last_12_months.png")
    if os.path.exists(p):
        chart = base64.b64encode(open(p, "rb").read()).decode()

    # --- Wiarygodność ---
    trust = []
    if len(val):
        def pick(prod, seg, sub=None):
            q = val[(val["product"] == prod) & (val["segment"] == seg)]
            if sub:
                q = q[q["subset"].astype(str).str.contains(sub)]
            return q.iloc[0] if len(q) else None
        r = pick("ERA5L_SM_RZ", "anomaly_clim")
        if r is not None:
            trust.append(f"Anomalia gleby (ERA5-Land) vs czujniki 20–30 cm: R = {_fmt(r['value'], 2)} "
                         f"[{_fmt(r['ci_low'], 2)}; {_fmt(r['ci_high'], 2)}], n = {int(r['n'])} dni")
        q = val[(val["segment"] == "events_dekad")]
        if len(q[q["metric"] == "pod"]) and len(q[q["metric"] == "far"]):
            pod = q[q["metric"] == "pod"]["value"].iloc[0]
            far = q[q["metric"] == "far"]["value"].iloc[0]
            n_dk = int(q["n"].iloc[0]) if "n" in q and pd.notna(q["n"].iloc[0]) else None
            trust.append(f"Suche dekady (warstwa gleby ERA5-Land{'' if n_dk is None else f', n = {n_dk} dekad'}): "
                         f"wykryte {_fmt(100 * pod, 0)}%, fałszywe sygnały {_fmt(100 * far, 0)}% — granica wynikająca "
                         f"z korelacji ERA5 z czujnikiem, dlatego status podaje też prawdopodobieństwo")
        r = pick(cfg["VEG_PRODUCT"] + "_NDVI", "anomaly_clim", "vineyard")
        if r is not None:
            trust.append(f"Anomalia NDVI winnicy ({cfg['VEG_PRODUCT']}, klimatologia z lat wcześniejszych) vs czujniki: "
                         f"R = {_fmt(r['value'], 2)} [{_fmt(r['ci_low'], 2)}; {_fmt(r['ci_high'], 2)}], n = {int(r['n'])} "
                         f"— pośrednio (stacja 136 m od winnicy, pod trawą)")
    trust.append("Alarm (gleba + roślinność) nie jest jeszcze zwalidowany na stanie wodnym winorośli")

    cov = sr_coverage(rt, cfg)
    label, meaning, color = STATUS_PL.get(cur["cdi_class"], (cur["cdi_class"], "", "#888"))
    run_start = cur["date"]                                # początek bieżącego ciągu dekad w tej samej klasie
    for d, cls in zip(st["date"][::-1], st["cdi_class"][::-1]):
        if cls != cur["cdi_class"]:
            break
        run_start = d
    n_dk = int((st["date"] >= run_start).sum())

    payload = {
        "site": {"id": sid, "name": f"Winnica {sid.split('_')[-1]} (Condom, Gers)", "area_ha": round(area_ha, 2),
                 "lat": round(c.y, 5), "lon": round(c.x, 5), "geometry": mapping(geom_ll)},
        "status": {"code": cur["cdi_class"], "label": label, "meaning": meaning, "color": color,
                   "date": cur["date"], "since": run_start, "n_dekads": n_dk,
                   "confidence": cur.get("confidence", ""), "gauge": GAUGE_LEVEL.get(cur["cdi_class"], 0.1),
                   "p_soil": cur.get("p_soil_drought")},
        "drivers": {"spi1": cur.get("spi1"), "spi3": cur.get("spi3"), "sma": cur.get("sma_rz"),
                    "veg_z": cur.get("veg_z"), "veg_source": cur.get("veg_source"), "veg_age": cur.get("veg_age_days")},
        "layers": layers,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    page = _render(payload, e, fc, chart, trust, cov, cfg)
    path = os.path.join(out_dir, "dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    logger.info(f"Dashboard: {path} ({len(layers)} dat mapy, prognoza: {'tak' if fc is not None else 'nie'})")
    return path


def _render(p: Dict[str, Any], era: pd.DataFrame, fc: Optional[pd.DataFrame], chart: str, trust: List[str],
            cov: Dict[str, int], cfg: Dict[str, Any]) -> str:
    s, d = p["status"], p["drivers"]
    esc = html.escape

    def drv(name, val, note=""):
        v = _fmt(val, 1)
        bad = val is not None and np.isfinite(float(val)) and float(val) <= -1 if v != "—" else False
        return (f'<div class="drv"><span>{name}</span><b style="color:{"#d63a2f" if bad else "#222"}">{v}</b>'
                f'<small>{note}</small></div>')

    era_rows = "".join(f"<tr><td>{r.time:%d.%m}</td><td>{_fmt(r.precip_mm, 1)}</td><td>{_fmt(r.t2m_c, 1)}</td></tr>"
                       for r in era.itertuples())
    fc_html = ""
    if fc is not None and len(fc):
        cells = "".join(f'<div class="fc"><b>{r.date:%a %d.%m}</b><span>{_fmt(r.tmax, 0)}° / {_fmt(r.tmin, 0)}°</span>'
                        f'<span>💧 {_fmt(r.precip_mm, 1)} mm</span><small>ET0 {_fmt(r.et0_mm, 1)}</small></div>'
                        for r in fc.itertuples())
        fc_html = f'<div class="fcrow">{cells}</div><small class="src">Prognoza: Open-Meteo</small>'
    else:
        fc_html = '<small class="src">Prognoza niedostępna (brak połączenia z Open-Meteo).</small>'

    opts = "".join(f'<option value="{i}">{esc(ly["date"])} · {"2,5 m SR" if ly["product"] == "S2SR_2.5m" else "10 m"}</option>'
                   for i, ly in enumerate(p["layers"]))
    ps = s.get("p_soil")
    p_soil_html = (f'<div class="src">Prawdopodobieństwo suszy w glebie (czujnik 20–30 cm, z ≤ −1): '
                   f'<b>{100 * float(ps):.0f}%</b> — z anomalii ERA5-Land i jej zgodności z ISMN Condom</div>'
                   if ps is not None and np.isfinite(float(ps)) else "")
    trust_html = "".join(f"<li>{esc(t)}</li>" for t in trust) or "<li>Brak wyników walidacji (uruchom task_validate).</li>"
    veg_note = (f"{d['veg_source']}, scena sprzed {int(d['veg_age'])} dni"
                if d.get("veg_source") and d.get("veg_age") is not None and np.isfinite(float(d["veg_age"]))
                else "brak sceny w sezonie")
    cov_txt = (f"SR 2,5 m: {cov['sr_ok']} z {cov['scenes']} scen sezonu przyjętych, {cov['remaining']} w kolejce"
               if cov.get("scenes") else "SR 2,5 m: brak scen")
    data_json = json.dumps({"layers": p["layers"], "geometry": p["site"]["geometry"],
                            "center": [p["site"]["lat"], p["site"]["lon"]]})
    return f"""<!doctype html><html lang="pl"><head><meta charset="utf-8">
<title>AgriWatch — {esc(p['site']['name'])}</title>
<link rel="stylesheet" href="https://unpkg.com/leaflet@1.9.4/dist/leaflet.css"/>
<script src="https://unpkg.com/leaflet@1.9.4/dist/leaflet.js"></script>
<style>
body{{font-family:Segoe UI,Roboto,Arial,sans-serif;margin:0;background:#f3f5f2;color:#222}}
.top{{background:#6f9b3a;color:#fff;padding:10px 18px;font-size:18px;font-weight:600;display:flex;justify-content:space-between}}
.top small{{font-weight:400;opacity:.9}}
.grid{{display:grid;grid-template-columns:230px 1fr 360px;gap:12px;padding:12px}}
.card{{background:#fff;border-radius:6px;box-shadow:0 1px 3px rgba(0,0,0,.12);padding:12px}}
.card h3{{margin:0 0 8px;font-size:14px;color:#555;text-transform:uppercase;letter-spacing:.04em}}
#map{{height:430px;border-radius:4px}}
.status{{border:2px solid {s['color']};text-align:center}}
.status .lbl{{font-size:24px;font-weight:700;color:{s['color']}}}
.drv{{display:flex;justify-content:space-between;align-items:baseline;border-bottom:1px solid #eee;padding:4px 0;font-size:13px}}
.drv b{{font-size:16px;margin-left:10px}} .drv small{{color:#888;margin-left:6px;flex:1;text-align:right}}
.fcrow{{display:flex;gap:6px;overflow-x:auto}} .fc{{min-width:70px;background:#eef5e6;border-radius:4px;padding:6px;font-size:12px;display:flex;flex-direction:column;gap:2px}}
table{{font-size:12px;border-collapse:collapse;width:100%}} td,th{{padding:2px 4px;text-align:right}} th{{color:#666}}
.src{{color:#888;font-size:11px}} .legend{{display:flex;align-items:center;gap:6px;font-size:12px;margin-top:6px}}
.bar{{height:10px;flex:1;background:linear-gradient(90deg,#a50026,#f46d43,#fee08b,#a6d96a,#1a9850);border-radius:3px}}
ul{{padding-left:18px;font-size:12px;margin:4px 0}} .full{{grid-column:1/4}}
</style></head><body>
<div class="top">AgriWatch · monitoring anomalii wilgotności <small>{esc(p['generated'])}</small></div>
<div class="grid">
 <div class="card"><h3>Działka</h3>
  <div style="font-size:16px;font-weight:600">{esc(p['site']['name'])}</div>
  <div class="drv"><span>Uprawa</span><b>winorośl</b></div>
  <div class="drv"><span>Powierzchnia</span><b>{_fmt(p['site']['area_ha'], 2)} ha</b></div>
  <div class="drv"><span>Nawadnianie</span><b>nie</b></div>
  <div class="drv"><span>Stacja ISMN</span><b>136 m</b></div>
  <h3 style="margin-top:14px">Dane</h3>
  <ul><li>Opad, gleba: ERA5-Land (~9 km)</li><li>Roślinność: Sentinel-2, {"SEN2SR 2,5 m" if cfg['VEG_PRODUCT'] == 'S2SR_2.5m' else "10 m"}</li>
  <li>{esc(cov_txt)}</li><li>Norma: 1991–2020 (gleba), inne lata (roślinność)</li></ul>
 </div>
 <div class="card"><h3>Roślinność (NDVI) <select id="sel" style="float:right">{opts}</select></h3>
  <div id="map"></div>
  <div class="legend"><span>słaba</span><div class="bar"></div><span>silna</span></div>
  <div id="info" class="src"></div>
 </div>
 <div style="display:flex;flex-direction:column;gap:12px">
  <div class="card status"><h3>Stan na {esc(str(s['date']))}</h3>
   <div class="lbl">{esc(s['label'])}</div><div style="font-size:13px;margin:6px 0">{esc(s['meaning'])}</div>
   <div class="src">od {esc(str(s['since']))} ({s['n_dekads']} dekad) · pewność: {esc(str(s['confidence']))}</div></div>
  <div class="card"><h3>Ryzyko suszy</h3>{_gauge_svg(s['gauge'], s['color'])}{p_soil_html}</div>
  <div class="card"><h3>Przyczyny (z-score, ≤ −1 = anomalia)</h3>
   {drv("Opad 30 dni (SPI-1)", d['spi1'], "próg −2")}{drv("Opad 90 dni (SPI-3)", d['spi3'], "próg −1")}
   {drv("Wilgotność gleby 0–100 cm", d['sma'], "próg −1")}{drv("Roślinność winnicy (NDVI)", d['veg_z'], veg_note)}</div>
 </div>
 <div class="card"><h3>Pogoda: ostatnie dni (ERA5-Land)</h3>
  <table><tr><th>dzień</th><th>opad mm</th><th>T °C</th></tr>{era_rows}</table></div>
 <div class="card"><h3>Prognoza 7 dni</h3>{fc_html}</div>
 <div class="card"><h3>Wiarygodność (ISMN Condom)</h3><ul>{trust_html}</ul>
  <div class="src">Status oznacza „sprawdź winnicę”, nie diagnozę stresu wodnego winorośli. Umiarkowany niedobór wody bywa pożądany dla jakości.</div></div>
 <div class="card full"><h3>Ostatnie 12 miesięcy</h3>{f'<img src="data:image/png;base64,{chart}" style="width:100%">' if chart else '<div class="src">Wykres powstaje w task_bulletin.</div>'}</div>
</div>
<script>
const D = {data_json};
const hasL = (typeof L !== 'undefined');
let map = null, ov = null;
function info(ly) {{
  const z = (ly.z === null || ly.z === undefined) ? '—' : ly.z.toFixed(1).replace('.', ',');
  document.getElementById('info').textContent = 'NDVI działki: średnio ' + ly.mean.toFixed(2).replace('.', ',') +
    ' (10–90%: ' + ly.p10.toFixed(2).replace('.', ',') + '–' + ly.p90.toFixed(2).replace('.', ',') + '), anomalia z = ' + z +
    (hasL ? '' : ' · mapa podkładowa niedostępna (brak sieci), pokazany sam obraz działki');
}}
if (!hasL) {{
  window.show = function(i) {{
    const ly = D.layers[i]; if (!ly) return;
    document.getElementById('map').innerHTML = '<img src="data:image/png;base64,' + ly.png +
      '" style="height:100%;width:100%;object-fit:contain;background:#d9d9d9;image-rendering:pixelated">';
    info(ly);
  }};
}} else {{
map = L.map('map').setView(D.center, 17);
L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{{z}}/{{y}}/{{x}}',
  {{maxZoom: 20, attribution: 'Esri World Imagery'}}).addTo(map);
const outline = L.geoJSON(D.geometry, {{style: {{color: '#ffffff', weight: 2, fill: false}}}}).addTo(map);
map.fitBounds(outline.getBounds(), {{padding: [20, 20]}});
window.show = function(i) {{
  const ly = D.layers[i]; if (!ly) {{ document.getElementById('info').textContent = 'Brak scen do pokazania.'; return; }}
  if (ov) map.removeLayer(ov);
  ov = L.imageOverlay('data:image/png;base64,' + ly.png, ly.bounds, {{opacity: 0.85}}).addTo(map);
  info(ly);
}};
}}
document.getElementById('sel').addEventListener('change', e => show(+e.target.value));
show(0);
</script></body></html>"""


def show_dashboard(path: str, height: int = 1250):
    """Wyświetla dashboard w komórce Colab / Jupyter."""
    from IPython.display import HTML, display
    display(HTML(f'<iframe srcdoc="{html.escape(open(path, encoding="utf-8").read())}" '
                 f'style="width:100%;height:{height}px;border:0"></iframe>'))
