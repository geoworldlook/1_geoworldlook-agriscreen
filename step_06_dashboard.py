"""
================================================================================
AgriWatch - KROK 6: DASHBOARD WINNICY (wzór: panel Wago, projekt ESA WineEO)
================================================================================
Jeden samodzielny plik HTML dla jednej winnicy, wyświetlany w Colab i zapisywany obok biuletynu:

  ┌ Działka ────────┬ Mapa NDVI 2,5 m na zdjęciu satelitarnym ┬ Stan (komunikat), Ryzyko suszy (wskaźnik),  ┐
  │ nazwa, ha, dane │ wybór daty sceny, obrys działki          │ Przyczyny: SPI-1, SPI-3, gleba, roślinność   │
  ├─ Kondycja winnicy: NDVI, NDRE, NDMI (z, klasa, 8 dni, R) ──┼ Wiarygodność: ISMN Condom + Météo-France      ┤
  ├─ Sezon na tle lat poprzednich: NDVI (5 lat), gleba 0–100 cm (norma 1991–2020) + zdanie podsumowania ─────┤
  ├─ Matryca sygnałów: opad -> gleba -> roślinność, 36 dekad, pasek statusu ───────────────────────────────────┤
  ├ Pogoda: 10 dni ─┼ Prognoza 7 dni (Open-Meteo) ──────────────┼ Przymrozki i upały (progi ze stacji MF)      ┤
  ├─ Tabela: ostatnie 5 lat (status, przymrozki, upały) ───────────────────────────────────────────────────────┤
  └─ Wykres: ostatnie 5 lat (DASHBOARD_YEARS) ──────────────────────────────────────────────────────────────────┘
Panele v1.2 (Kondycja, Sezon, Matryca) liczy step_09; błąd jednego z nich daje kartę „Element niedostępny”.

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


def _unavailable(e: Exception) -> str:
    """Treść karty, której element nie powstał (jak przy braku prognozy: reszta dashboardu działa).
    Dla właściciela winnicy tylko krótka informacja; typ i treść wyjątku w logu zadania i w dymku (title)."""
    return (f'<div class="src" title="{html.escape(f"{type(e).__name__}: {e}")}">'
            f'Element niedostępny (szczegóły w logu zadania).</div>')


def _png_file_b64(path: str, colors: int = 64) -> str:
    """PNG jako base64 do osadzenia w dashboardzie, zmniejszony do palety `colors` barw (ok. 4× mniej bajtów;
    dashboard trafia do notatnika Colab). Biuletyn zostaje z pełnym PNG. Bez Pillow — plik bez zmian."""
    data = open(path, "rb").read()
    try:
        from PIL import Image
        buf = io.BytesIO()
        Image.open(io.BytesIO(data)).convert("RGB").quantize(colors).save(buf, format="PNG", optimize=True)
        if buf.tell() < len(data):
            data = buf.getvalue()
    except Exception as e:                                  # brak Pillow / nietypowy PNG: osadzamy oryginał
        logger.info(f"PNG bez kwantyzacji ({os.path.basename(path)}): {e}")
    return base64.b64encode(data).decode()


def _spark_svg(vals: List[float], dates: List[str], thr: float = -1.0, w: int = 160, h: int = 44) -> str:
    """Mini-wykres z ostatnich dni ze sceną: oś z obejmuje dane, 0 i próg (co najmniej od −2,5 do 1),
    linia 0 i przerywana linia progu (−1). Kolory punktów = klasy z roślinności (step_09.VEG_Z_COLORS)."""
    import step_09_panels as s9
    fin = [z for z in vals if np.isfinite(z)]
    if not fin:
        return ""
    lo, hi = min(-2.5, min(fin) - 0.2), max(1.0, max(fin) + 0.2)

    def y(z):
        return h - 3 - (min(max(z, lo), hi) - lo) / (hi - lo) * (h - 6)
    xs = [5 + i * (w - 10) / max(len(vals) - 1, 1) for i in range(len(vals))]
    pts = [(x, y(z), z, d) for x, z, d in zip(xs, vals, dates) if np.isfinite(z)]
    line = " ".join(f"{x:.1f},{yy:.1f}" for x, yy, _, _ in pts)
    dots = "".join(f'<circle cx="{x:.1f}" cy="{yy:.1f}" r="2.4" fill="{s9.z_class(z)[2]}">'
                   f'<title>{html.escape(d)}: z = {s9._num(z, 1)}</title></circle>' for x, yy, z, d in pts)
    return (f'<svg viewBox="0 0 {w} {h}" width="{w}" height="{h}" style="display:block">'
            f'<line x1="0" x2="{w}" y1="{y(0):.1f}" y2="{y(0):.1f}" stroke="#ddd"/>'
            f'<line x1="0" x2="{w}" y1="{y(thr):.1f}" y2="{y(thr):.1f}" stroke="{s9.VEG_Z_COLORS["below"]}" '
            f'stroke-dasharray="3,2"/>'
            f'<polyline points="{line}" fill="none" stroke="#666" stroke-width="1.2"/>{dots}</svg>')


def _condition_html(cond: List[Dict[str, Any]], cfg: Dict[str, Any], status_date: Optional[str]) -> str:
    """Kafelki panelu „Kondycja winnicy” (step_09.condition_panel) i stopka z zastrzeżeniami."""
    import step_09_panels as s9
    esc, num = html.escape, s9._num
    tiles = []
    for c in cond:
        if c.get("date") is None:
            scene = ("brak tego wskaźnika w wynikach" if c["cls"] == "not_computed"
                     else "brak sceny z oceną z w sezonie")
        else:
            age = int(c["age_days"])
            old = c["cls"] == "stale" or age > cfg["VEG_MAX_AGE_DAYS"] or \
                c["date"].year != (c["date"] + pd.Timedelta(days=age)).year
            scene = (f"{'ostatnia scena sezonu' if c['cls'] == 'stale' else 'scena'} "
                     f"{c['date']:{'%d.%m.%Y' if old else '%d.%m'}} ({s9.days_ago_pl(age)}), "
                     f"wartość {num(c['value'])} wobec normy {num(c['clim_mean'])}")
        ref = ""
        if c.get("n_ref"):
            ref = f"norma z {c['n_ref']} scen" + (f", {s9.REF_MODE_PL[c['ref_mode']]}"
                                                  if c.get("ref_mode") in s9.REF_MODE_PL else "")
        prod = s9.PRODUCT_PL.get(c["product"], c["product"])
        if c.get("r") is None:
            r_txt = "Zgodność z czujnikiem gleby 20–30 cm: brak walidacji"
        else:
            r_txt = (f"Zgodność z czujnikiem gleby 20–30 cm (ten sam dzień): {s9.r_strength(c['r'])}, "
                     f"R = {num(c['r'])} [{num(c['r_lo'])}; {num(c['r_hi'])}], n = {c.get('r_n') or '—'} dni ze sceną"
                     + (f" ({c['r_from']}–{c['r_to']})" if c.get("r_from") else ""))
        hint = ""
        if c["cls"] in ("below", "well_below") and np.isfinite(c["z"]) and c["z"] <= cfg["THR_VEG"] \
                and c.get("drop_hint"):
            hint = f'<div class="src"><b>Możliwe przyczyny:</b> {esc(c["drop_hint"])}</div>'
        note = f'<div class="src" style="color:#b35c00">{esc(c["note"])}</div>' if c.get("note") else ""
        stat = ""
        ss = c.get("status_scene")
        if ss is not None and (c.get("date") is None or not c["in_status"]
                               or pd.Timestamp(c["date"]).normalize() != pd.Timestamp(ss["date"]).normalize()):
            stat = (f'<div class="src">W statusie (dekada do {ss["dekad"]:%d.%m.%Y}): scena {ss["date"]:%d.%m}, '
                    f'z = {num(ss["z"], 1)} ({esc(s9.PRODUCT_PL.get(ss["product"], ss["product"]))})</div>')
        if c["in_status"]:
            badge = '<span class="badge">używany w statusie</span>'
        elif c.get("status_index"):
            badge = (f'<span class="badge info">{esc(prod)} — status używa '
                     f'{esc(s9.PRODUCT_PL.get(cfg["VEG_PRODUCT"], cfg["VEG_PRODUCT"]))}</span>')
        else:
            badge = '<span class="badge info">informacyjnie</span>'
        n_sp = len(c["spark"])
        sp_when = "w ostatnim dniu ze sceną" if n_sp == 1 else f"w ostatnich {n_sp} dniach ze sceną"
        sp_txt = (f'<div class="src">Odchylenie z {sp_when}'
                  f'{" (" + c["spark_dates"][0][:5] + "–" + c["spark_dates"][-1][:5] + ")" if n_sp > 1 else ""}; '
                  f'przerywana linia: próg {num(cfg["THR_VEG"], 0)}</div>') if n_sp else ""
        tiles.append(
            f'<div class="tile"><div class="tl"><b>{esc(c["label"])}</b>{badge}</div>'
            f'<div class="zbig" style="color:{c["color"]}">{num(c["z"], 1)}</div>'
            f'<div style="color:{c["color"]};font-weight:600;font-size:13px">{esc(c["cls_label"])}</div>'
            f'<div style="font-size:12px">{esc(scene)} · {esc(prod)}</div>'
            f'<div class="src">{esc(c["meaning"])}{"; " + esc(ref) if ref else ""}</div>'
            f'{_spark_svg(c["spark"], c["spark_dates"], cfg["THR_VEG"])}{sp_txt}'
            f'<div class="src">{esc(r_txt)}</div>{stat}{note}{hint}</div>')
    return (f'<div class="cond">{"".join(tiles)}</div>'
            f'<div class="src" style="margin-top:8px">{esc(s9.condition_footer(cond, cfg, status_date))}</div>')


def _weather_info(out_dir: str, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Wyniki task_weather: progi, zdarzenia w winnicy per rok, linie wiarygodności (stacja referencyjna MF)."""
    def rd(name):
        q = os.path.join(out_dir, name)
        return pd.read_csv(q, dtype={"num_poste": str}) if os.path.exists(q) else pd.DataFrame()
    val, per_year, stations = rd("validation_weather.csv"), rd("hazard_summary.csv"), rd("mf_stations.csv")
    q = os.path.join(out_dir, "hazard_thresholds.json")
    thr = json.load(open(q)) if os.path.exists(q) else {}
    trust = []
    if len(val) and len(stations):
        ref = thr.get("reference") or f"MF_{stations.iloc[0]['num_poste']}"
        v = val[val["reference"].astype(str) == ref]
        name = v["subset"].iloc[0] if len(v) else ""
        min_n = cfg.get("WX_MIN_TEST_EVENTS", 10)
        for prod, ev, key, label in (("ERA5L_TMIN", "frost_events", "frost", "Przymrozki wiosenne"),
                                     ("ERA5L_TMAX", "heat_events", "heat", "Upały")):
            if key not in thr:
                continue
            # metryki dla progu, którego naprawdę używamy (nominalny albo skalibrowany)
            e = v[(v["product"] == prod) & (v["segment"] == ev) &
                  v["period"].astype(str).str.endswith(f"thr={thr[key]:+.2f}")]
            pod, far = e[e["metric"] == "pod"], e[e["metric"] == "far"]
            if not (len(pod) and len(far)):
                continue
            n = int(pod["n"].iat[0])
            if n < min_n:
                trust.append(f"{label} (ERA5-Land vs stacja Météo-France {name}): w latach testowych tylko {n} dni "
                             f"ze zdarzeniem — za mało, żeby podać skuteczność")
            else:
                trust.append(f"{label} (ERA5-Land vs stacja Météo-France {name}, lata testowe): wykryte "
                             f"{_fmt(100 * pod['value'].iat[0], 0)}%, fałszywe {_fmt(100 * far['value'].iat[0], 0)}%, "
                             f"n = {n} dni ze zdarzeniem")
        b = v[(v["product"] == "ERA5L_TMIN") & (v["segment"] == "daily") & (v["period"] == "season") & (v["metric"] == "bias")]
        m = v[(v["product"] == "ERA5L_TMIN") & (v["segment"] == "daily") & (v["period"] == "season") & (v["metric"] == "mae")]
        if len(b) and len(m):
            trust.append(f"Tmin wiosną: ERA5-Land vs stacja {name} — przesunięcie {_fmt(b['value'].iat[0], 1)} °C, "
                         f"średni błąd {_fmt(m['value'].iat[0], 1)} °C")
        s3 = v[(v["product"] == "ERA5L_PRECIP") & (v["segment"] == "SPI3") & (v["metric"] == "pearson_r")]
        if len(s3):
            trust.append(f"Niedobór opadu SPI-3 (ERA5-Land vs deszczomierz {name}): R = {_fmt(s3['value'].iat[0], 2)}, "
                         f"n = {int(s3['n'].iat[0])} dni")
    return {"thr": thr, "per_year": per_year, "trust": trust}


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
    yrs = int(cfg.get("DASHBOARD_YEARS", 5))
    wx = _weather_info(out_dir, cfg)
    chart = ""
    p = os.path.join(out_dir, f"last_{yrs}_years.png")
    if not os.path.exists(p):
        p = os.path.join(out_dir, "last_12_months.png")
    if os.path.exists(p):
        chart = base64.b64encode(open(p, "rb").read()).decode()
    # tabela ostatnich lat: dekady w klasach statusu + dni przymrozku i upału
    st_y = st.assign(year=st["date"].str[:4].astype(int))
    st_y = st_y[st_y["year"] > pd.Timestamp(cur["date"]).year - yrs]
    years_tbl = st_y.pivot_table(index="year", columns="cdi_class", values="date", aggfunc="count", fill_value=0)
    if len(wx["per_year"]):
        years_tbl = years_tbl.join(wx["per_year"].set_index("year")[["frost_days", "heat_days"]], how="left")

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
        q = val[(val["product"] == "ERA5L_SM_L1") & (val["segment"] == "anomaly_clim")].dropna(subset=["value"])
        if len(q):
            r = q.sort_values("date_to").iloc[-1]                # bieżący czujnik 5 cm (po wymianie w 2019)
            trust.append(f"Wierzchnia warstwa gleby 0–7 cm (ERA5-Land) vs czujnik 5 cm: R = {_fmt(r['value'], 2)} "
                         f"[{_fmt(r['ci_low'], 2)}; {_fmt(r['ci_high'], 2)}], n = {int(r['n'])} dni")
    trust += wx["trust"]
    trust.append("Alarm (gleba + roślinność) nie jest jeszcze zwalidowany na stanie wodnym winorośli")

    # --- Panele v1.2 (step_09): każdy osobno; błąd jednego (także import step_09) daje kartę „Element
    # niedostępny”, reszta dashboardu powstaje ---
    panels: Dict[str, str] = {"traj_title": "Sezon na tle lat poprzednich"}

    def element(name, fn):
        try:
            panels[name] = fn()
        except Exception as ex:
            logger.warning(f"Dashboard: element {name} niedostępny: {type(ex).__name__}: {ex}")
            panels[name] = _unavailable(ex)

    def condition_html():
        import step_09_panels as s9
        return _condition_html(s9.condition_panel(veg, val, cfg, sid, status_row=cur), cfg, cur["date"])

    def season_html():
        import step_09_panels as s9
        traj = s9.season_trajectory(veg, era5, cfg, sid)
        png = s9.plot_season_trajectory(traj, cfg, os.path.join(out_dir, "season_trajectory.png"))
        panels["traj_title"] = f"Sezon {traj['year']} na tle lat poprzednich"
        return (f'<div style="font-size:14px;font-weight:600;margin-bottom:6px">{html.escape(s9.season_summary(traj))}'
                f'</div><img src="data:image/png;base64,{_png_file_b64(png)}" style="width:100%">'
                f'<div class="src">{html.escape(s9.season_caption(traj, cfg))}</div>')

    def matrix_html():
        import step_09_panels as s9
        return s9.matrix_html(s9.signal_matrix(status, veg, cfg, sid), cfg, {k: v[0] for k, v in STATUS_PL.items()})

    element("condition", condition_html)
    element("season", season_html)
    element("matrix", matrix_html)

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
                    "sma_l1": cur.get("sma_l1"),
                    "veg_z": cur.get("veg_z"), "veg_source": cur.get("veg_source"), "veg_age": cur.get("veg_age_days")},
        "layers": layers,
        "generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    }
    page = _render(payload, e, fc, chart, trust, cov, cfg, wx, years_tbl, panels)
    path = os.path.join(out_dir, "dashboard.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(page)
    logger.info(f"Dashboard: {path} ({len(layers)} dat mapy, prognoza: {'tak' if fc is not None else 'nie'})")
    return path


def _render(p: Dict[str, Any], era: pd.DataFrame, fc: Optional[pd.DataFrame], chart: str, trust: List[str],
            cov: Dict[str, int], cfg: Dict[str, Any], wx: Optional[Dict[str, Any]] = None,
            years_tbl: Optional[pd.DataFrame] = None, panels: Optional[Dict[str, str]] = None) -> str:
    s, d = p["status"], p["drivers"]
    esc = html.escape
    panels = panels or {}
    na = '<div class="src">Element niedostępny: nie policzono.</div>'
    r0, r1 = cfg["CLIM_REF"]
    norm_txt = (f"Norma: {str(r0)[:4]}–{str(r1)[:4]} (gleba, opad), {int(cfg.get('VEG_REF_YEARS') or 5)} poprzednich "
                f"lat, zwykle ten sam tor orbity (roślinność)")

    def drv(name, val, note=""):
        v = _fmt(val, 1)
        bad = val is not None and np.isfinite(float(val)) and float(val) <= -1 if v != "—" else False
        return (f'<div class="drv"><span>{name}</span><b style="color:{"#d63a2f" if bad else "#222"}">{v}</b>'
                f'<small>{note}</small></div>')

    era_rows = "".join(f"<tr><td>{r.time:%d.%m}</td><td>{_fmt(r.precip_mm, 1)}</td>"
                       f"<td>{_fmt(getattr(r, 't2m_min_c', None), 1)}</td><td>{_fmt(getattr(r, 't2m_max_c', None), 1)}</td></tr>"
                       for r in era.itertuples())
    # Przymrozki i upały: sezon bieżący (ERA5-Land, próg skalibrowany) + prognoza (próg nominalny, bez walidacji)
    wx = wx or {"thr": {}, "per_year": pd.DataFrame()}
    thr = {"frost": cfg["FROST_TMIN"], "heat": cfg["HEAT_TMAX"], **(wx.get("thr") or {})}
    hz_html = ""
    py = wx.get("per_year")
    if py is not None and len(py):
        r = py.sort_values("year").iloc[-1]
        hz_html += (f'<div class="drv"><span>Przymrozki wiosenne {int(r["year"])}</span><b>{int(r["frost_days"])} dni</b>'
                    f'<small>{"ostatni " + pd.Timestamp(r["last_frost"]).strftime("%d.%m") if isinstance(r["last_frost"], str) and r["last_frost"] else ""}</small></div>'
                    f'<div class="drv"><span>Upały ≥ {_fmt(cfg["HEAT_TMAX"], 0)} °C {int(r["year"])}</span>'
                    f'<b>{int(r["heat_days"])} dni</b><small>Tmax sezonu {_fmt(r["max_tmax"], 1)} °C</small></div>')
    if fc is not None and len(fc):
        fr = fc[fc["tmin"] <= cfg["FROST_TMIN"]]
        ht = fc[fc["tmax"] >= cfg["HEAT_TMAX"]]
        fc_msg = "; ".join(x for x in (
            ("przymrozek: " + ", ".join(f"{d:%d.%m}" for d in fr["date"])) if len(fr) else "",
            ("upał: " + ", ".join(f"{d:%d.%m}" for d in ht["date"])) if len(ht) else "") if x) or "brak"
        hz_html += f'<div class="drv"><span>Prognoza 7 dni</span><b>{esc(fc_msg)}</b></div>'
    hz_html += (f'<div class="src">Przymrozek: Tmin ERA5-Land ≤ {_fmt(thr["frost"], 2)} °C w dniach '
                f'{cfg["FROST_SEASON"][0]}–{cfg["FROST_SEASON"][1]} (próg {esc(str(thr.get("frost_source", "nominalny")))}; '
                f'temperatura w klatce 2 m, pąki bywają 1–2 °C zimniejsze). Upał: Tmax ≥ {_fmt(thr["heat"], 1)} °C '
                f'(próg {esc(str(thr.get("heat_source", "nominalny")))}). Prognoza: progi nominalne, bez walidacji.</div>')
    yt_html = ""
    if years_tbl is not None and len(years_tbl):
        names = {"alert": "Sprawdź", "warning": "Sucho", "watch": "Obserwuj", "recovery": "Powrót", "normal": "Norma",
                 "frost_days": "Dni przymrozku", "heat_days": "Dni upału"}
        cols = [c for c in ("alert", "warning", "watch", "recovery", "normal", "frost_days", "heat_days") if c in years_tbl]
        head = "".join(f"<th>{names[c]}</th>" for c in cols)
        body = "".join(f"<tr><td>{y}</td>" + "".join(f"<td>{'' if pd.isna(r[c]) else int(r[c])}</td>" for c in cols) + "</tr>"
                       for y, r in years_tbl.sort_index(ascending=False).iterrows())
        yt_html = (f'<table><tr><th>rok</th>{head}</tr>{body}</table>'
                   f'<div class="src">Status: liczba dekad (10 dni) w każdej klasie. Przymrozki i upały: ERA5-Land w punkcie winnicy.</div>')
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
.cond{{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:10px}}
.tile{{border:1px solid #e6e6e6;border-radius:6px;padding:8px 10px;display:flex;flex-direction:column;gap:3px}}
.tile .tl{{display:flex;justify-content:space-between;align-items:center;gap:6px;font-size:13px}}
.zbig{{font-size:32px;font-weight:700;line-height:1.1}}
.badge{{font-size:10px;padding:1px 7px;border-radius:9px;background:#e4f0d8;color:#3d6b1f;white-space:nowrap}}
.badge.info{{background:#f0f0f0;color:#666}}
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
  <li>{esc(cov_txt)}</li><li>{esc(norm_txt)}</li></ul>
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
   {drv("Wilgotność gleby 0–100 cm", d['sma'], "próg −1")}{drv("Wierzchnia warstwa 0–7 cm", d.get('sma_l1'), "informacyjnie")}{drv("Roślinność winnicy (NDVI)", d['veg_z'], veg_note)}</div>
 </div>
 <div class="card" style="grid-column:1/3"><h3>Kondycja winnicy</h3>{panels.get("condition", na)}</div>
 <div class="card"><h3>Wiarygodność (ISMN Condom)</h3><ul>{trust_html}</ul>
  <div class="src">Status oznacza „sprawdź winnicę”, nie diagnozę stresu wodnego winorośli. Umiarkowany niedobór wody bywa pożądany dla jakości.</div></div>
 <div class="card full"><h3>{esc(panels.get("traj_title", "Sezon na tle lat poprzednich"))}</h3>{panels.get("season", na)}</div>
 <div class="card full"><h3>Matryca sygnałów</h3>{panels.get("matrix", na)}</div>
 <div class="card"><h3>Pogoda: ostatnie dni (ERA5-Land)</h3>
  <table><tr><th>dzień</th><th>opad mm</th><th>Tmin °C</th><th>Tmax °C</th></tr>{era_rows}</table></div>
 <div class="card"><h3>Prognoza 7 dni</h3>{fc_html}</div>
 <div class="card"><h3>Przymrozki i upały</h3>{hz_html}</div>
 <div class="card full"><h3>Ostatnie {int(cfg.get("DASHBOARD_YEARS", 5))} lat</h3>{yt_html or '<div class="src">Brak danych.</div>'}</div>
 <div class="card full"><h3>Ostatnie {int(cfg.get("DASHBOARD_YEARS", 5))} lat: opad, gleba, roślinność, status</h3>{f'<img src="data:image/png;base64,{chart}" style="width:100%">' if chart else '<div class="src">Wykres powstaje w task_bulletin.</div>'}</div>
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


def show_dashboard(path: str, height: int = 3400):
    """Wyświetla dashboard w komórce Colab / Jupyter. Ramka dopasowuje wysokość do strony po załadowaniu
    (onload); `height` to wysokość startowa, gdy przeglądarka nie pozwala odczytać treści ramki."""
    from IPython.display import HTML, display
    fit = "try{this.style.height=(this.contentDocument.documentElement.scrollHeight+20)+'px'}catch(e){}"
    display(HTML(f'<iframe srcdoc="{html.escape(open(path, encoding="utf-8").read())}" onload="{fit}" '
                 f'style="width:100%;height:{height}px;border:0"></iframe>'))
