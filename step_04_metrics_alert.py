"""
================================================================================
AgriWatch - KROK 4: INDEKSY, ANOMALIE I STATUS SUSZY DLA WINNICY
================================================================================
Wzorzec: Combined Drought Indicator (CDI) Europejskiego Obserwatorium Suszy (EDO, JRC):
  susza rozwija się kaskadowo: deficyt opadu (Watch) -> anomalia wilgotności gleby (Warning)
  -> anomalia roślinności (Alert). Progi EDO: SPI-1 <= -2 lub SPI-3 <= -1; SMA <= -1; anomalia
  roślinności <= -1 (odchylenia standardowe). Factsheet CDI v4 i SMA (drought.emergency.copernicus.eu).

Różnica względem EDO (i wartość dodana projektu):
  - opad i wilgotność gleby: ERA5-Land w oczku winnicy (EDO: LISFLOOD 5 km, fAPAR 1 km),
  - roślinność: Sentinel-2 w granicach JEDNEJ winnicy (10 m oraz SEN2SR 2,5 m),
  - błąd anomalii zwalidowany na profilu glebowym ISMN Condom (krok 7).

Dlaczego anomalie, a nie wartości bezwzględne: anomalia względem własnej historii obiektu znosi
stałe błędy (gleba, głębokość korzeni, kalibracja), a jej jakość da się sprawdzić korelacją anomalii
z pomiarem (Gruber i in. 2020; QA4SM). Status mówi „sprawdź działkę”, nie „winorośl jest w stresie”.
================================================================================
"""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("AgriWatch_Metrics")

S2_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
RASTER_CLOUD_BAND = 10          # indeks pasma 'cloudmask' w plikach z step_01 (1 = chmura/cień)
INDICES = ("ndvi", "ndmi", "ndre", "crswir")
# CRSWIR: środki pasm [nm] jak w FORDEAD (INRAE); waga kontinuum dla B11 między B8A a B12
CRSWIR_W = (1610.0 - 865.0) / (2190.0 - 865.0)

CDI_CLASSES = {0: "normal", 1: "watch", 2: "warning", 3: "alert"}
ACTION = {"normal": "normal", "recovery": "normal", "watch": "watch", "warning": "watch", "alert": "inspect"}


# ==============================================================================
# I. INDEKSY I STATYSTYKI OBIEKTÓW Z RASTRÓW SENTINEL-2
# ==============================================================================

def compute_indices(arr: np.ndarray) -> Dict[str, np.ndarray]:
    """
    NDVI = (B08-B04)/(B08+B04)        — wigor / pokrycie roślinnością,
    NDMI = (B8A-B11)/(B8A+B11)        — woda w liściach (SWIR; Laroche-Pinel i in. 2021: B8A, B12 istotne),
    NDRE = (B8A-B05)/(B8A+B05)        — red-edge (chlorofil),
    CRSWIR = B11 / (B8A + (B12-B8A)·w) — głębokość absorpcji wody przy 1610 nm względem kontinuum B8A–B12
                                         (FORDEAD, INRAE); wyższa wartość = mniej wody. Przegląd: F3, sekcja 7.
    """
    b = {name: arr[i] for i, name in enumerate(S2_BANDS)}
    with np.errstate(all="ignore"):
        return {
            "ndvi": (b["B08"] - b["B04"]) / (b["B08"] + b["B04"]),
            "ndmi": (b["B8A"] - b["B11"]) / (b["B8A"] + b["B11"]),
            "ndre": (b["B8A"] - b["B05"]) / (b["B8A"] + b["B05"]),
            "crswir": b["B11"] / (b["B8A"] + (b["B12"] - b["B8A"]) * CRSWIR_W),
        }


def scene_time(path: str) -> pd.Timestamp:
    """Czas akwizycji z nazwy pliku step_01: S2_L2A_YYYYMMDD_HHMMSS.tif."""
    m = re.search(r"S2_L2A_(\d{8})_(\d{6})", os.path.basename(path))
    if not m:
        raise ValueError(f"Nierozpoznana nazwa sceny: {path}")
    return pd.to_datetime(m.group(1) + m.group(2), format="%Y%m%d%H%M%S")


def load_sites(cfg: Dict[str, Any], crs: Any, station_lonlat: Tuple[float, float]):
    """
    Obiekty monitoringu w układzie rastra:
      - winnice z pliku działek (fid -> site_id), statystyki bez pasa brzegowego (1 piksel),
      - poligon stacji Condom (210 m²) — miejsce czujnika,
      - bufor 50 m wokół stacji (ten sam obszar co walidacja S-1 w kroku 7).
    """
    import geopandas as gpd
    from shapely.geometry import Point

    parcels = gpd.read_file(cfg["PARCELS_PATH"]).to_crs(crs)
    rows = []
    for sid, fid in cfg["VINEYARDS"].items():
        geom = parcels.loc[parcels["fid"] == fid, "geometry"]
        if geom.empty:
            raise ValueError(f"Brak działki fid={fid} w {cfg['PARCELS_PATH']}")
        rows.append({"site_id": sid, "site_type": "vineyard", "name": f"Vineyard fid {fid}",
                     "inner_buffer": True, "geometry": geom.iloc[0]})
    st = parcels.loc[parcels["fid"] == cfg["STATION_POLY_FID"], "geometry"]
    if not st.empty:
        rows.append({"site_id": f"{cfg['NETWORK']}_{cfg['STATION']}_poly", "site_type": "station",
                     "name": f"{cfg['STATION']} station plot", "inner_buffer": False, "geometry": st.iloc[0]})
    pt = gpd.GeoSeries([Point(*station_lonlat)], crs=4326).to_crs(crs).iloc[0]
    rows.append({"site_id": f"{cfg['NETWORK']}_{cfg['STATION']}", "site_type": "station",
                 "name": f"{cfg['STATION']} station buffer {cfg['STATION_BUFFER_M']} m", "inner_buffer": False,
                 "geometry": pt.buffer(cfg["STATION_BUFFER_M"])})
    return gpd.GeoDataFrame(rows, crs=crs)


def site_stats(arr: np.ndarray, cloud: np.ndarray, profile: Dict[str, Any], sites, product: str,
               t: pd.Timestamp) -> List[Dict[str, Any]]:
    """
    Średnie indeksów w obiektach (tylko piksele bezchmurne) + udział pikseli czystych i ich liczba.
    Winnice: bez pasa brzegowego o szerokości 1 piksela tej rozdzielczości (Sozzi i in. 2020:
    usunięcie pikseli brzegowych poprawia zgodność z UAV; dla działek < 0,5 ha bywa odwrotnie).
    """
    from rasterio.features import geometry_mask

    res = abs(profile["transform"].a)
    shape = arr.shape[1:]
    idx = compute_indices(arr)
    clear = (cloud == 0) & np.isfinite(arr).all(axis=0)
    out = []
    for s in sites.itertuples():
        geom = s.geometry.buffer(-res) if s.inner_buffer else s.geometry
        if geom.is_empty:
            continue
        mask = geometry_mask([geom], out_shape=shape, transform=profile["transform"], invert=True)
        method = "centre"
        if mask.sum() == 0:
            mask = geometry_mask([geom], out_shape=shape, transform=profile["transform"], invert=True, all_touched=True)
            method = "all_touched"
        n = int(mask.sum())
        if n == 0:
            continue
        ok = mask & clear
        rec = {"site_id": s.site_id, "product": product, "time": t, "n_pixels": n,
               "clear_frac": float(ok.sum() / n), "px_method": method}
        for k, v in idx.items():
            rec[k] = float(np.nanmean(v[ok])) if ok.any() else np.nan
        out.append(rec)
    return out


# ==============================================================================
# II. ANOMALIE KLIMATOLOGICZNE (z-score, percentyl) I SPI
# ==============================================================================

def _circ_doy_dist(a: np.ndarray, b: int) -> np.ndarray:
    d = np.abs(a - b)
    return np.minimum(d, 366 - d)


def clim_anomaly(s: pd.Series, ref: Tuple[str, str], half_window: int = 15, min_n: int = 30) -> pd.DataFrame:
    """
    Anomalia standaryzowana względem klimatologii dnia roku (okno ±half_window dni, lata referencyjne),
    jak SMA w EDO (odchylenie od średniej wieloletniej / odchylenie standardowe dla tej pory roku).
    Zwraca: value, clim_mean, clim_std, z, percentile (empiryczny, 0-100), n_ref.
    """
    s = s.dropna().sort_index()
    r = s.loc[ref[0]:ref[1]]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    doy = s.index.dayofyear.to_numpy()
    out = pd.DataFrame(index=s.index, data={"value": s.to_numpy(float)})
    for c in ("clim_mean", "clim_std", "percentile", "n_ref"):
        out[c] = np.nan
    for d in np.unique(doy):
        pool = np.sort(rv[_circ_doy_dist(rd, d) <= half_window])
        if len(pool) < min_n:
            continue
        sel = doy == d
        v = out["value"].to_numpy()[sel]
        out.loc[sel, "clim_mean"] = pool.mean()
        out.loc[sel, "clim_std"] = pool.std(ddof=1)
        out.loc[sel, "percentile"] = 100.0 * np.searchsorted(pool, v, side="right") / len(pool)
        out.loc[sel, "n_ref"] = len(pool)
    out["z"] = (out["value"] - out["clim_mean"]) / out["clim_std"]
    return out


def spi(precip: pd.Series, days: int, ref: Tuple[str, str], half_window: int = 15) -> pd.DataFrame:
    """
    SPI (McKee i in. 1993) z sum kroczących `days` dni: rozkład gamma dopasowany dla pory roku
    (okno ±half_window dni w latach referencyjnych), z uwzględnieniem prawdopodobieństwa zera.
    """
    from scipy import stats

    p = precip.sort_index().asfreq("D")
    acc = p.rolling(days, min_periods=int(0.9 * days)).sum().dropna()
    r = acc.loc[ref[0]:ref[1]]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    doy = acc.index.dayofyear.to_numpy()
    z = np.full(len(acc), np.nan)
    for d in np.unique(doy):
        pool = rv[_circ_doy_dist(rd, d) <= half_window]
        if len(pool) < 30:
            continue
        q0 = np.mean(pool <= 0.01)
        pos = pool[pool > 0.01]
        if len(pos) < 20:
            continue
        a, loc, scale = stats.gamma.fit(pos, floc=0)
        sel = doy == d
        x = acc.to_numpy()[sel]
        prob = q0 + (1 - q0) * stats.gamma.cdf(np.maximum(x, 0), a, loc=0, scale=scale)
        prob = np.where(x <= 0.01, q0 / 2 if q0 > 0 else 1e-6, prob)
        z[sel] = stats.norm.ppf(np.clip(prob, 1e-6, 1 - 1e-6))
    return pd.DataFrame({"value": acc.to_numpy(), "z": z}, index=acc.index)


def rootzone(era5: pd.DataFrame) -> pd.Series:
    """Wilgotność 0-100 cm: średnia ważona grubością warstw ERA5-Land (7, 21, 72 cm)."""
    return (7 * era5["sm_l1"] + 21 * era5["sm_l2"] + 72 * era5["sm_l3"]) / 100.0


def era5_anomalies(era5: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str, pd.DataFrame]:
    """Dzienne anomalie z ERA5-Land: wilgotność 0-7 cm i 0-100 cm, SPI-1 i SPI-3."""
    e = era5.set_index(pd.to_datetime(era5["time"]).dt.floor("D")).sort_index()
    e = e[~e.index.duplicated(keep="last")]
    ref, hw = cfg["CLIM_REF"], cfg["CLIM_HALF_WINDOW_DAYS"]
    out = {
        "ERA5L_SM_L1": clim_anomaly(e["sm_l1"], ref, hw),
        "ERA5L_SM_RZ": clim_anomaly(rootzone(e), ref, hw),
    }
    for days, name in zip(cfg["SPI_DAYS"], ("ERA5L_SPI1", "ERA5L_SPI3")):
        out[name] = spi(e["precip_mm"], days, ref, hw)
    return out


def track_ids(t: pd.Series, min_sep_min: float = 5.0) -> np.ndarray:
    """Tor orbity S-2 z godziny akwizycji: nad stałym punktem sąsiednie orbity względne przelatują o różnej porze
    (nad Condom ~10:59 i ~11:09 UTC, z rozrzutem kilku minut w archiwum). Podział na dwie grupy progiem Otsu
    na minutach doby; gdy średnie grup różnią się o mniej niż min_sep_min minut — jeden tor."""
    mins = (t.dt.hour * 60 + t.dt.minute + t.dt.second / 60).to_numpy(float)
    u = np.sort(np.unique(mins))
    if len(u) < 2:
        return np.zeros(len(mins), int)
    best, thr = -1.0, None
    for cut in (u[:-1] + u[1:]) / 2:
        a, b = mins[mins <= cut], mins[mins > cut]
        score = len(a) * len(b) * (a.mean() - b.mean()) ** 2
        if score > best:
            best, thr = score, cut
    lo, hi = mins[mins <= thr], mins[mins > thr]
    if hi.mean() - lo.mean() < min_sep_min:
        return np.zeros(len(mins), int)
    return (mins > thr).astype(int)


def scene_anomaly(df: pd.DataFrame, col: str, cfg: Dict[str, Any]) -> pd.DataFrame:
    """
    Anomalia roślinności dla nieregularnych scen S-2 względem scen z ±VEG_HALF_WINDOW_DAYS dni roku.
    Domyślnie (Plan v7, A1–A3):
      - VEG_CAUSAL: tylko lata WCZEŚNIEJSZE (tak, jak system działałby w danym dniu; trend NDVI winnicy
        sprawiał, że klimatologia z „pozostałych lat” zawyżała zgodność z gruntem: R 0,50 → 0,29 na tych samych dniach);
      - VEG_BY_TRACK: odniesienie z tego samego toru orbity (różnica średnich z między torami ~0,4 na winnicy,
        geometria rzędów); gdy scen z toru za mało — wszystkie tory (ref_mode = "all_tracks");
      - VEG_PREDICTIVE_Z: z predykcyjne z rozkładu t-Studenta (krótka historia, n_ref 5–30),
        żeby częstość z <= -1 odpowiadała rozkładowi normalnemu (było 19,6% zamiast 15,9%).
    Tylko sceny z udziałem pikseli czystych >= VEG_MIN_CLEAR_FRAC.
    """
    from scipy import stats

    d = df[(df["clear_frac"] >= cfg["VEG_MIN_CLEAR_FRAC"]) & df[col].notna()].sort_values("time").copy()
    if d.empty:
        return d.assign(clim_mean=np.nan, clim_std=np.nan, z=np.nan, n_ref=0, track=0, ref_mode="")
    causal, by_track = cfg.get("VEG_CAUSAL", True), cfg.get("VEG_BY_TRACK", True)
    doy, yr, v = d["time"].dt.dayofyear.to_numpy(), d["time"].dt.year.to_numpy(), d[col].to_numpy(float)
    trk = track_ids(d["time"])
    mu, sd, n, mode = [], [], [], []
    for i in range(len(d)):
        m = (yr < yr[i]) if causal else (yr != yr[i])
        if causal and cfg.get("VEG_REF_YEARS"):
            m &= yr >= yr[i] - cfg["VEG_REF_YEARS"]
        m &= _circ_doy_dist(doy, doy[i]) <= cfg["VEG_HALF_WINDOW_DAYS"]
        ref = "all_tracks"
        if by_track and (m & (trk == trk[i])).sum() >= cfg["VEG_MIN_REF"]:
            m, ref = m & (trk == trk[i]), "same_track"
        pool = v[m]
        ok = len(pool) >= cfg["VEG_MIN_REF"]
        mu.append(pool.mean() if ok else np.nan)
        sd.append(pool.std(ddof=1) if ok else np.nan)
        n.append(len(pool))
        mode.append(ref if ok else "")
    d["clim_mean"], d["clim_std"], d["n_ref"], d["track"], d["ref_mode"] = mu, sd, n, trk, mode
    if cfg.get("VEG_PREDICTIVE_Z", True):
        nn = d["n_ref"].to_numpy(float)
        t = (d[col] - d["clim_mean"]).to_numpy() / (d["clim_std"].to_numpy() * np.sqrt(1 + 1 / np.maximum(nn, 1)))
        d["z"] = stats.norm.ppf(np.clip(stats.t.cdf(t, df=np.maximum(nn - 1, 1)), 1e-6, 1 - 1e-6))
        d.loc[~np.isfinite(t), "z"] = np.nan
    else:
        d["z"] = (d[col] - d["clim_mean"]) / d["clim_std"]
    return d


def soil_drought_probability(z: np.ndarray, rho: float, c: float = -1.0) -> np.ndarray:
    """
    Prawdopodobieństwo, że wilgotność gleby mierzona w gruncie jest w anomalii z <= c, gdy anomalia ERA5-Land
    wynosi z (model dwuwymiarowy normalny, korelacja produktu z gruntem rho; F5 §5, Plan v7 A7).
    Przy rho = 0,58 (walidacja ISMN Condom): z = -1 -> p ≈ 0,30; p = 0,5 dopiero przy z ≈ -1,7.
    """
    from scipy import stats
    z = np.asarray(z, float)
    return stats.norm.cdf((c - rho * z) / np.sqrt(1 - rho ** 2))


# ==============================================================================
# III. STATUS DEKADOWY (LOGIKA CDI, UPROSZCZONA)
# ==============================================================================

def dekad_end(t: pd.Series) -> pd.Series:
    """Koniec dekady (10., 20. lub ostatni dzień miesiąca)."""
    t = pd.to_datetime(t)
    end_month = t + pd.offsets.MonthEnd(0)
    return pd.to_datetime(np.where(t.dt.day <= 10, t.dt.to_period("M").dt.to_timestamp() + pd.Timedelta(days=9),
                          np.where(t.dt.day <= 20, t.dt.to_period("M").dt.to_timestamp() + pd.Timedelta(days=19),
                                   end_month))).normalize()


def build_status(era5_an: Dict[str, pd.DataFrame], veg: pd.DataFrame, site_id: str, cfg: Dict[str, Any],
                 start: str) -> pd.DataFrame:
    """
    Status na koniec każdej dekady od `start`:
      watch   (1): SPI-1 <= THR_SPI1 lub SPI-3 <= THR_SPI3            (deficyt opadu)
      warning (2): SMA strefy korzeni <= THR_SMA                      (anomalia wilgotności gleby)
      alert   (3): warning ORAZ anomalia roślinności winnicy <= THR_VEG (roślinność reaguje)
      recovery   : poprzednia dekada >= warning, bieżąca poniżej progów, ale anomalie nadal ujemne.
    Roślinność: ostatnia scena nie starsza niż VEG_MAX_AGE_DAYS i tylko w miesiącach S2_MONTHS.
    """
    days = pd.date_range(start, era5_an["ERA5L_SM_RZ"].index.max(), freq="D")
    dk = pd.DataFrame({"day": days, "dekad": dekad_end(pd.Series(days))})
    sma = era5_an["ERA5L_SM_RZ"]["z"].reindex(days)
    dk["sma_rz"] = sma.to_numpy()
    for name, col in (("ERA5L_SPI1", "spi1"), ("ERA5L_SPI3", "spi3")):
        dk[col] = era5_an[name]["z"].reindex(days).to_numpy()
    g = dk.groupby("dekad").agg(sma_rz=("sma_rz", "mean"), spi1=("spi1", "last"), spi3=("spi3", "last"),
                                n_days=("day", "size"))
    g = g[g.index <= days.max()]

    v = veg[veg["site_id"] == site_id].dropna(subset=["z"]).sort_values("time") if len(veg) else veg
    m0, m1 = cfg["S2_MONTHS"]
    rows, prev = [], 0
    for dk_end, r in g.iterrows():
        veg_z, veg_src, veg_age = np.nan, "", np.nan
        if len(v) and m0 <= dk_end.month <= m1:
            cand = v[(v["time"] <= dk_end + pd.Timedelta(days=1)) &
                     (v["time"] >= dk_end - pd.Timedelta(days=cfg["VEG_MAX_AGE_DAYS"]))]
            if len(cand):
                last = cand.iloc[-1]
                veg_z, veg_src = float(last["z"]), str(last["product"])
                veg_age = float((dk_end - last["time"].normalize()).days)
        deficit = (r["spi1"] <= cfg["THR_SPI1"]) or (r["spi3"] <= cfg["THR_SPI3"])
        warn = r["sma_rz"] <= cfg["THR_SMA"]
        alert = warn and np.isfinite(veg_z) and veg_z <= cfg["THR_VEG"]
        level = 3 if alert else 2 if warn else 1 if deficit else 0
        cls = CDI_CLASSES[level]
        if level < 2 and prev >= 2 and ((r["sma_rz"] < 0) or (np.isfinite(veg_z) and veg_z < 0)):
            cls = "recovery"
        reasons = [f"SPI1={r['spi1']:.1f}", f"SPI3={r['spi3']:.1f}", f"SMA_RZ={r['sma_rz']:.1f}"]
        if np.isfinite(veg_z):
            reasons.append(f"VEG_Z={veg_z:.1f}({veg_src},{int(veg_age)}d)")
        in_season = m0 <= dk_end.month <= m1
        conf = "high" if np.isfinite(veg_z) and veg_age <= 10 else "medium" if (np.isfinite(veg_z) or not in_season) else "low"
        p_soil = float(soil_drought_probability(r["sma_rz"], cfg.get("PSMA_RHO", 0.58), cfg["THR_SMA"])) \
            if np.isfinite(r["sma_rz"]) else np.nan
        rows.append({"site_id": site_id, "date": dk_end.strftime("%Y-%m-%d"), "cdi_level": level, "cdi_class": cls,
                     "action": ACTION[cls], "spi1": r["spi1"], "spi3": r["spi3"], "sma_rz": r["sma_rz"],
                     "p_soil_drought": p_soil,
                     "veg_z": veg_z, "veg_source": veg_src, "veg_age_days": veg_age, "confidence": conf,
                     "reason_codes": ";".join(reasons)})
        prev = level
    return pd.DataFrame(rows)


# ==============================================================================
# IV. BIULETYN: WYKRES, RAPORT, JSON DLA STRONY
# ==============================================================================

_COLORS = {"normal": "#dfeee0", "recovery": "#cfe3f5", "watch": "#ffe08a", "warning": "#ffb15c", "alert": "#e8584f"}


def plot_season(status: pd.DataFrame, veg: pd.DataFrame, site_id: str, start: str, end: str, title: str,
                out_png: str, primary: Optional[str] = None) -> str:
    """Trzy panele (SPI-3, SMA strefy korzeni, anomalia roślinności) + pas statusu.
    primary: produkt roślinności używany w detekcji (opisany w legendzie); pozostałe = odniesienie."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    st = status[(status["site_id"] == site_id)].copy()
    st["date"] = pd.to_datetime(st["date"])
    st = st[(st["date"] >= start) & (st["date"] <= end)]
    vv = veg[(veg["site_id"] == site_id) & (veg["time"] >= start) & (veg["time"] <= end)] if len(veg) else veg
    fig, ax = plt.subplots(4, 1, figsize=(12, 9), sharex=True, gridspec_kw={"height_ratios": [1, 1, 1, 0.35]})
    ax[0].bar(st["date"], st["spi3"], width=8, color="tab:blue"); ax[0].axhline(-1, c="k", ls="--", lw=0.8)
    ax[0].set_ylabel("SPI-3")
    ax[1].plot(st["date"], st["sma_rz"], c="tab:brown"); ax[1].axhline(-1, c="k", ls="--", lw=0.8)
    ax[1].set_ylabel("Soil moisture\nanomaly 0-100 cm (z)")
    for prod, mk in (("S2_10m", "o"), ("S2SR_2.5m", "s")):
        p = vv[vv["product"] == prod] if len(vv) else vv
        if len(p):
            role = "" if primary is None else (" (detection)" if prod == primary else " (reference)")
            kw = {} if primary is None or prod == primary else {"alpha": 0.35}
            ax[2].scatter(p["time"], p["z"], marker=mk, s=18, label=prod + role, **kw)
    ax[2].axhline(-1, c="k", ls="--", lw=0.8); ax[2].set_ylabel("Vegetation\nanomaly NDVI (z)")
    if len(vv):
        ax[2].legend(fontsize=8)
    for _, r in st.iterrows():
        ax[3].axvspan(r["date"] - pd.Timedelta(days=9), r["date"], color=_COLORS[r["cdi_class"]])
    ax[3].set_yticks([]); ax[3].set_ylabel("Status")
    for a in ax[:3]:
        a.axhline(0, c="0.7", lw=0.5)
    fig.suptitle(title)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    fig.savefig(out_png, dpi=120)
    plt.close(fig)
    return out_png


def _veg_method(cfg: Dict[str, Any]) -> str:
    """Opis warstwy roślinności (biuletyn, JSON): produkt detekcji i pokrycie SR."""
    if cfg.get("VEG_PRODUCT") == "S2SR_2.5m":
        txt = ("Sentinel-2 NDVI of the vineyard super-resolved to 2.5 m with SEN2SR (inner pixels), anomaly vs other "
               "years; only scenes that pass the SR quality checks (H-SR0 detail, H-SR1 radiometric consistency of "
               "the 10 m bands) enter detection; 10 m NDVI is kept as a reference")
    else:
        txt = "Sentinel-2 NDVI of the vineyard at 10 m (inner pixels), anomaly vs other years"
    cov = cfg.get("SR_COVERAGE")
    if cov and cov.get("scenes"):
        txt += (f". SR coverage: {cov['sr_ok']} of {cov['scenes']} season scenes accepted, "
                f"{cov['remaining']} not yet processed")
    return txt


def build_bulletin(status: pd.DataFrame, veg: pd.DataFrame, validation: pd.DataFrame, site: Dict[str, Any],
                   cfg: Dict[str, Any], out_dir: str) -> Dict[str, str]:
    """Raport Markdown (EN), wykresy PNG i JSON `agriwatch_latest.json` dla geoworldlook.vercel.app."""
    os.makedirs(out_dir, exist_ok=True)
    sid = site["site_id"]
    st = status[status["site_id"] == sid].sort_values("date")
    cur = st.iloc[-1].to_dict()
    y = cfg["SHOWCASE_SEASON"]
    primary = cfg.get("VEG_PRODUCT")
    png_show = plot_season(status, veg, sid, f"{y}-03-01", f"{y}-10-31",
                           f"AgriWatch — {site['name']} — season {y}", os.path.join(out_dir, f"season_{y}.png"),
                           primary)
    last = pd.to_datetime(st["date"]).max()
    png_now = plot_season(status, veg, sid, (last - pd.Timedelta(days=365)).strftime("%Y-%m-%d"),
                          last.strftime("%Y-%m-%d"), f"AgriWatch — {site['name']} — last 12 months",
                          os.path.join(out_dir, "last_12_months.png"), primary)
    val = validation.copy() if validation is not None else pd.DataFrame()

    def clean(x):
        if isinstance(x, (float, np.floating)):
            return None if not np.isfinite(x) else round(float(x), 3)
        if isinstance(x, (np.integer,)):
            return int(x)
        return x

    payload = {
        "generated_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "site": {k: clean(v) for k, v in site.items() if k != "geometry"},
        "current": {k: clean(v) for k, v in cur.items()},
        "dekads": [{k: clean(v) for k, v in r.items()} for r in st.tail(108).to_dict("records")],
        "showcase_season": y,
        "sr_coverage": cfg.get("SR_COVERAGE"),
        "validation": [{k: clean(v) for k, v in r.items()} for r in val.to_dict("records")],
        "method": {
            "logic": "Simplified EDO Combined Drought Indicator: watch = SPI-1<=-2 or SPI-3<=-1; "
                     "warning = root-zone soil moisture anomaly <=-1; alert = warning and vineyard NDVI anomaly <=-1",
            "soil_moisture": "ERA5-Land layers 0-100 cm, anomaly vs 1991-2020 day-of-year climatology",
            "vegetation": _veg_method(cfg),
            "validation": "Anomaly correlation and drought-event detection against ISMN SMOSMANIA Condom (5-30 cm)",
        },
    }
    js = os.path.join(out_dir, "agriwatch_latest.json")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=1, ensure_ascii=False)

    def fmt(x, nd=2):
        return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"

    vlines = ["| Product | Reference | Type | Footprint | Metric | Value | 95% CI | n |", "|---|---|---|---|---|---|---|---|"]
    for r in val.itertuples() if len(val) else []:
        ci = f"[{fmt(r.ci_low)}, {fmt(r.ci_high)}]" if np.isfinite(r.ci_low) else "—"
        vlines.append(f"| {r.product} | {r.reference} | {r.segment} | {r.subset} | {r.metric} | {fmt(r.value)} | {ci} | {int(r.n)} |")
    md = f"""# AgriWatch bulletin — {site['name']}

Generated {payload['generated_utc']} · status for the dekad ending **{cur['date']}**

| Status | Action | Confidence | Reasons |
|---|---|---|---|
| **{cur['cdi_class']}** | {cur['action']} | {cur['confidence']} | {cur['reason_codes']} |

![last 12 months](last_12_months.png)

## Showcase: season {y}

![season {y}](season_{y}.png)

## How the status is built

{payload['method']['logic']}. Soil moisture: {payload['method']['soil_moisture']}. Vegetation: {payload['method']['vegetation']}.
The status means *check this vineyard*, not a diagnosis of vine water stress.

## Validated error of the anomalies (ISMN SMOSMANIA Condom, 136 m from the vineyard)

{chr(10).join(vlines)}

Limits: the station is in a rainfed field next to the vineyard, not inside it; ERA5-Land (~9 km) gives the same
soil-moisture anomaly for every parcel in the cell; parcel-specific information comes from Sentinel-2 only.
"""
    md_path = os.path.join(out_dir, "bulletin.md")
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md)
    return {"json": js, "markdown": md_path, "png_season": png_show, "png_recent": png_now}
