"""
================================================================================
AgriWatch - KROK 8: ZAGROŻENIA POGODOWE I ICH WALIDACJA NA STACJACH MÉTÉO-FRANCE
================================================================================
Co raportujemy (z ERA5-Land w punkcie winnicy):
  - przymrozki wiosenne: dni z Tmin ≤ próg w oknie po pąkowaniu (FROST_SEASON),
  - upały: dni z Tmax ≥ próg latem (HEAT_SEASON),
  - niedobór opadu: SPI-1 / SPI-3 (liczone w step_04, tu tylko walidowane).

Czym walidujemy: dane dobowe Météo-France (meteo.data.gouv.fr, licencja Etalab 2.0, bezpłatne także komercyjnie),
plik „RR-T-Vent” na departament: opad RR, Tmin TN, Tmax TX z kodami jakości. Bierzemy kilka najbliższych stacji
z dobrym pokryciem i porównujemy z ERA5-Land pobranym DOKŁADNIE w punkcie każdej stacji (błąd produktu, nie
różnica między miejscami). Próg ERA5 dla przymrozków/upałów kalibrujemy na latach < WX_CAL_SPLIT_YEAR i
oceniamy na latach późniejszych (wynik na danych, których kalibracja nie widziała).

Zastrzeżenia: TN/TX Météo-France to temperatura w klatce 2 m (okno 18–18 UTC dla TN, 06–06 UTC dla TX),
ERA5-Land DAILY_AGGR — doba 00–24 UTC. Przy przymrozku radiacyjnym pąki bywają 1–2 °C zimniejsze niż klatka.
================================================================================
"""

from __future__ import annotations

import glob
import gzip
import logging
import os
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("AgriWatch_Weather")

MF_DATASET_API = "https://www.data.gouv.fr/api/1/datasets/donnees-climatologiques-de-base-quotidiennes/"
MF_BASE_URL = "https://object.files.data.gouv.fr/meteofrance/data/synchro_ftp/BASE/QUOT/"
MF_BAD_QUALITY = {2}        # kody jakości MF: 0 chroniona, 1 zwalidowana, 9 filtrowana bez walidacji, 2 wątpliwa


# ==============================================================================
# I. DANE MÉTÉO-FRANCE
# ==============================================================================

def mf_resource_urls(dept: str, timeout: int = 30) -> List[str]:
    """Adresy plików dobowych RR-T-Vent departamentu (API data.gouv.fr; zapasowo — wzorzec nazw na serwerze)."""
    import requests
    tag = f"Q_{int(dept):02d}_"
    try:
        r = requests.get(MF_DATASET_API, timeout=timeout)
        r.raise_for_status()
        urls = [x["url"] for x in r.json().get("resources", [])
                if tag in x.get("url", "") and "RR-T-Vent" in x.get("url", "")]
        if urls:
            return sorted(set(urls))
    except Exception as e:
        logger.warning(f"API data.gouv.fr niedostępne ({e}); próbuję nazw plików wprost")
    y = pd.Timestamp.now().year
    cands = [f"{MF_BASE_URL}{tag}previous-1950-{a}_RR-T-Vent.csv.gz" for a in range(y - 1, y - 4, -1)]
    cands += [f"{MF_BASE_URL}{tag}latest-{a}-{a + 1}_RR-T-Vent.csv.gz" for a in range(y, y - 3, -1)]
    found, have_prev, have_latest = [], False, False
    for u in cands:
        kind = "previous" if "previous" in u else "latest"
        if (kind == "previous" and have_prev) or (kind == "latest" and have_latest):
            continue
        try:
            if requests.head(u, timeout=timeout).status_code == 200:
                found.append(u)
                have_prev |= kind == "previous"
                have_latest |= kind == "latest"
        except Exception:
            pass
    return found


def download_mf(depts: List[str], cache_dir: str, refresh_days: int = 3) -> List[str]:
    """
    Pobiera pliki do cache. Plik „previous” (archiwum) pobierany raz; „latest” (bieżące lata) odświeżany,
    gdy starszy niż refresh_days. Brak sieci = używa tego, co jest w cache.
    """
    import requests
    os.makedirs(cache_dir, exist_ok=True)
    paths = []
    for dept in depts:
        try:
            urls = mf_resource_urls(dept)
        except Exception as e:
            logger.warning(f"Météo-France {dept}: {e}")
            urls = []
        for u in urls:
            p = os.path.join(cache_dir, os.path.basename(u.split("?")[0]))
            fresh = os.path.exists(p) and ("previous" in p or
                                           (pd.Timestamp.now().timestamp() - os.path.getmtime(p)) < refresh_days * 86400)
            if not fresh:
                try:
                    r = requests.get(u, timeout=300)
                    r.raise_for_status()
                    with open(p + ".tmp", "wb") as f:
                        f.write(r.content)
                    os.replace(p + ".tmp", p)
                    logger.info(f"Météo-France: pobrano {os.path.basename(p)} ({len(r.content) / 1e6:.1f} MB)")
                except Exception as e:
                    logger.warning(f"Météo-France: nie pobrano {u}: {e}")
            if os.path.exists(p):
                paths.append(p)
        # starsze wersje „latest”/„previous” tego departamentu (zmiana roku w nazwie) są zbędne
        for kind in ("latest", "previous"):
            mine = sorted(glob.glob(os.path.join(cache_dir, f"Q_{int(dept):02d}_{kind}-*_RR-T-Vent.csv.gz")))
            for old in mine[:-1]:
                if old not in paths:
                    os.remove(old)
    if not paths:
        paths = sorted(glob.glob(os.path.join(cache_dir, "Q_*_RR-T-Vent.csv.gz")))
    return paths


def read_mf(paths: List[str], start: str = "1991-01-01") -> pd.DataFrame:
    """Pliki RR-T-Vent -> num_poste, name, lat, lon, alti, time, rr, tn, tx (wartości wątpliwe = NaN)."""
    cols = ["NUM_POSTE", "NOM_USUEL", "LAT", "LON", "ALTI", "AAAAMMJJ", "RR", "QRR", "TN", "QTN", "TX", "QTX"]
    frames = []
    for p in paths:
        with gzip.open(p, "rt", encoding="utf-8", errors="replace") if p.endswith(".gz") else open(p) as f:
            df = pd.read_csv(f, sep=";", usecols=lambda c: c in cols, dtype={"NUM_POSTE": str}, low_memory=False)
        df = df[df["AAAAMMJJ"] >= int(start.replace("-", ""))]
        frames.append(df)
    if not frames:
        return pd.DataFrame(columns=["num_poste", "name", "lat", "lon", "alti", "time", "rr", "tn", "tx"])
    d = pd.concat(frames, ignore_index=True)
    out = pd.DataFrame({"num_poste": d["NUM_POSTE"].str.strip(), "name": d["NOM_USUEL"].astype(str).str.strip(),
                        "lat": d["LAT"].astype(float), "lon": d["LON"].astype(float), "alti": d["ALTI"],
                        "time": pd.to_datetime(d["AAAAMMJJ"].astype(str), format="%Y%m%d")})
    for v, q in (("rr", "QRR"), ("tn", "QTN"), ("tx", "QTX")):
        x = pd.to_numeric(d[v.upper()], errors="coerce")
        if q in d:
            x = x.where(~pd.to_numeric(d[q], errors="coerce").isin(MF_BAD_QUALITY))
        out[v] = x.to_numpy()
    return out.drop_duplicates(["num_poste", "time"], keep="last").sort_values(["num_poste", "time"])


def haversine_km(lat1, lon1, lat2, lon2):
    p1, p2 = np.radians(lat1), np.radians(lat2)
    a = np.sin((p2 - p1) / 2) ** 2 + np.cos(p1) * np.cos(p2) * np.sin(np.radians(lon2 - lon1) / 2) ** 2
    return 2 * 6371.0 * np.arcsin(np.sqrt(a))


def select_stations(mf: pd.DataFrame, lat: float, lon: float, cfg: Dict[str, Any]) -> pd.DataFrame:
    """Najbliższe stacje (≤ MF_MAX_KM) z pokryciem TN, TX i RR ≥ MF_MIN_COVERAGE w okresie walidacji."""
    t0 = pd.Timestamp(cfg["WX_VAL_START"])
    end = mf["time"].max()
    n_days = (end - t0).days + 1
    rows = []
    for num, g in mf[mf["time"] >= t0].groupby("num_poste"):
        r = g.iloc[-1]
        cov = {v: g[v].notna().sum() / n_days for v in ("rr", "tn", "tx")}
        rows.append({"num_poste": num, "name": r["name"], "lat": r["lat"], "lon": r["lon"], "alti": r["alti"],
                     "dist_km": float(haversine_km(lat, lon, r["lat"], r["lon"])),
                     "cov_rr": cov["rr"], "cov_t": min(cov["tn"], cov["tx"])})
    st = pd.DataFrame(rows)
    if st.empty:
        return st
    ok = (st["dist_km"] <= cfg["MF_MAX_KM"]) & (st["cov_t"] >= cfg["MF_MIN_COVERAGE"])
    return st[ok].sort_values("dist_km").head(cfg["MF_MAX_STATIONS"]).reset_index(drop=True)


# ==============================================================================
# II. METRYKI
# ==============================================================================

def contingency(obs: np.ndarray, prd: np.ndarray) -> Dict[str, float]:
    """Tabela zdarzeń: POD (wykryte), FAR (fałszywe sygnały), CSI, liczba zdarzeń obserwowanych."""
    obs, prd = np.asarray(obs, bool), np.asarray(prd, bool)
    h, m, f = int((obs & prd).sum()), int((obs & ~prd).sum()), int((~obs & prd).sum())
    return {"pod": h / (h + m) if h + m else np.nan, "far": f / (h + f) if h + f else np.nan,
            "csi": h / (h + m + f) if h + m + f else np.nan, "n_events": h + m, "n_days": int(len(obs))}


def in_season(t: pd.DatetimeIndex, season: Tuple[str, str]) -> np.ndarray:
    md = t.strftime("%m-%d")
    return (md >= season[0]) & (md <= season[1])


def calibrate_threshold(x: np.ndarray, obs: np.ndarray, grid: np.ndarray, below: bool) -> Tuple[float, float]:
    """Próg na ERA5 maksymalizujący CSI względem zdarzeń stacyjnych (zwraca próg, CSI)."""
    best = (np.nan, -1.0)
    for g in grid:
        c = contingency(obs, x <= g if below else x >= g)["csi"]
        if np.isfinite(c) and c > best[1]:
            best = (float(g), float(c))
    return best


def hazard_validation(era: pd.DataFrame, stn: pd.DataFrame, cfg: Dict[str, Any]) -> List[Dict[str, Any]]:
    """
    Przymrozki i upały: ERA5-Land w punkcie stacji vs stacja.
    Wiersze: bias/MAE/R temperatury (cały rok, dni sezonu), próg skalibrowany na latach < split,
    POD/FAR/CSI na latach ≥ split dla progu nominalnego i skalibrowanego.
    """
    split = cfg["WX_CAL_SPLIT_YEAR"]
    j = era.set_index("time")[["t2m_min_c", "t2m_max_c"]].join(stn.set_index("time")[["tn", "tx"]], how="inner")
    rows = []
    for var, e_col, s_col, season, thr, below in (
            ("TMIN", "t2m_min_c", "tn", cfg["FROST_SEASON"], cfg["FROST_TMIN"], True),
            ("TMAX", "t2m_max_c", "tx", cfg["HEAT_SEASON"], cfg["HEAT_TMAX"], False)):
        d = j[[e_col, s_col]].dropna()
        if len(d) < 100:
            continue
        diff = d[e_col] - d[s_col]
        rows += [(var, "daily", "all", "bias", diff.mean(), len(d)), (var, "daily", "all", "mae", diff.abs().mean(), len(d)),
                 (var, "daily", "all", "pearson_r", d[e_col].corr(d[s_col]), len(d))]
        s = d[in_season(d.index, season)]
        if len(s) < 30:
            continue
        sd = s[e_col] - s[s_col]
        rows += [(var, "daily", "season", "bias", sd.mean(), len(s)), (var, "daily", "season", "mae", sd.abs().mean(), len(s))]
        obs = (s[s_col] <= thr) if below else (s[s_col] >= thr)
        tr, te = s.index.year < split, s.index.year >= split
        grid = np.arange(thr - 3.0, thr + 3.01, 0.25)
        cal, csi_tr = calibrate_threshold(s.loc[tr, e_col].to_numpy(), obs[tr].to_numpy(), grid, below) \
            if obs[tr].sum() >= 5 else (np.nan, np.nan)
        ev = "frost" if below else "heat"
        rows.append((var, f"{ev}_events", f"train<{split}", "threshold_cal", cal, int(obs[tr].sum())))
        for name, t in (("nominal", thr), ("calibrated", cal)):
            if not np.isfinite(t):
                continue
            prd = (s[e_col] <= t) if below else (s[e_col] >= t)
            c = contingency(obs[te].to_numpy(), prd[te].to_numpy())
            for m in ("pod", "far", "csi"):
                rows.append((var, f"{ev}_events", f"test>={split} {name} thr={t:+.2f}", m, c[m], c["n_events"]))
        # roczne liczby dni (cały okres): czy ERA5 dobrze liczy sezon
        yr = pd.DataFrame({"o": obs, "p": (s[e_col] <= (cal if np.isfinite(cal) else thr)) if below
                           else (s[e_col] >= (cal if np.isfinite(cal) else thr))}).groupby(s.index.year).sum()
        rows.append((var, f"{ev}_days_per_year", "calibrated", "mae_days", float((yr["p"] - yr["o"]).abs().mean()),
                     int(len(yr))))
    return rows


def precip_validation(era: pd.DataFrame, stn: pd.DataFrame, cfg: Dict[str, Any]) -> List[Tuple]:
    """Opad: R sum 30 dni; SPI-1/SPI-3 ERA5 vs SPI ze stacji (ta sama metoda, ten sam okres odniesienia)."""
    from step_04_metrics_alert import dekad_end, spi
    e = era.set_index("time")["precip_mm"].asfreq("D")
    s = stn.set_index("time")["rr"].asfreq("D")
    rows = []
    t0 = pd.Timestamp(cfg["WX_VAL_START"])
    a30 = pd.concat([e.rolling(30, min_periods=27).sum(), s.rolling(30, min_periods=27).sum()], axis=1,
                    keys=["e", "s"]).loc[t0:].dropna()
    if len(a30) > 100:
        rows.append(("PRECIP", "sum_30d", "all", "pearson_r", a30["e"].corr(a30["s"]), len(a30)))
        rows.append(("PRECIP", "sum_30d", "all", "bias_pct", 100 * (a30["e"].mean() / a30["s"].mean() - 1), len(a30)))
    ref = cfg["CLIM_REF"]
    ref_cov = s.loc[ref[0]:ref[1]].notna().mean() if len(s.loc[ref[0]:ref[1]]) else 0.0
    if ref_cov < 0.8:
        ref = (cfg["WX_VAL_START"], str(s.index.max().date()))   # krótka stacja: wspólny okres jako odniesienie
    for days, name, thr in ((cfg["SPI_DAYS"][0], "SPI1", cfg["THR_SPI1"]), (cfg["SPI_DAYS"][1], "SPI3", cfg["THR_SPI3"])):
        z = pd.concat([spi(e.dropna(), days, ref)["z"], spi(s.dropna(), days, ref)["z"]], axis=1,
                      keys=["e", "s"]).loc[t0:].dropna()
        if len(z) < 100:
            continue
        rows.append(("PRECIP", name, f"ref {ref[0][:4]}-{ref[1][:4]}", "pearson_r", z["e"].corr(z["s"]), len(z)))
        dk = z.groupby(dekad_end(pd.Series(z.index)).to_numpy()).last()
        c = contingency((dk["s"] <= thr).to_numpy(), (dk["e"] <= thr).to_numpy())
        for m in ("pod", "far"):
            rows.append(("PRECIP", f"{name}<={thr:g}_dekad", f"ref {ref[0][:4]}-{ref[1][:4]}", m, c[m], c["n_events"]))
    return rows


def validate_weather(stations: pd.DataFrame, mf: pd.DataFrame, era_by_station: Dict[str, pd.DataFrame],
                     cfg: Dict[str, Any]) -> pd.DataFrame:
    """Wiersze w formacie gwl_validation_metrics (product = ERA5L_<zmienna>, reference = MF_<nr stacji>)."""
    out = []
    for st in stations.itertuples():
        era = era_by_station.get(st.num_poste)
        if era is None or era.empty:
            continue
        stn = mf[mf["num_poste"] == st.num_poste]
        era = era.assign(time=pd.to_datetime(era["time"]).dt.floor("D"))
        rows = [r for r in hazard_validation(era, stn, cfg)] + precip_validation(era, stn, cfg)
        sub = f"{st.name} ({st.dist_km:.0f} km, {st.alti} m)"
        for var, seg, period, metric, value, n in rows:
            out.append({"site_id": f"MF_{st.num_poste}", "product": f"ERA5L_{var}", "reference": f"MF_{st.num_poste}",
                        "segment": seg, "period": period, "subset": sub, "metric": metric,
                        "value": float(value) if value is not None and np.isfinite(value) else np.nan,
                        "ci_low": np.nan, "ci_high": np.nan, "n": n,
                        "date_from": cfg["WX_VAL_START"], "date_to": str(stn["time"].max().date())})
    return pd.DataFrame(out)


def calibrated_thresholds(val: pd.DataFrame, cfg: Dict[str, Any]) -> Dict[str, float]:
    """Progi ERA5 dla zagrożeń: mediana progów skalibrowanych na stacjach; brak = progi nominalne."""
    thr = {"frost": cfg["FROST_TMIN"], "heat": cfg["HEAT_TMAX"]}
    if val is None or val.empty:
        return thr
    for ev, prod in (("frost", "ERA5L_TMIN"), ("heat", "ERA5L_TMAX")):
        q = val[(val["product"] == prod) & (val["metric"] == "threshold_cal")]["value"].dropna()
        if len(q):
            thr[ev] = float(q.median())
    return thr


# ==============================================================================
# III. ZAGROŻENIA DLA WINNICY (ERA5-Land w punkcie winnicy)
# ==============================================================================

def weather_hazards(era5: pd.DataFrame, cfg: Dict[str, Any], thr: Dict[str, float]) -> pd.DataFrame:
    """Dzienne flagi: frost (Tmin ≤ próg w FROST_SEASON), heat (Tmax ≥ próg w HEAT_SEASON)."""
    e = era5.assign(time=pd.to_datetime(era5["time"]).dt.floor("D")).drop_duplicates("time").set_index("time")
    idx = e.index
    out = pd.DataFrame(index=idx)
    out["tmin"] = e["t2m_min_c"]
    out["tmax"] = e["t2m_max_c"] if "t2m_max_c" in e else np.nan
    out["frost"] = in_season(idx, cfg["FROST_SEASON"]) & (out["tmin"] <= thr["frost"]).to_numpy()
    out["heat"] = in_season(idx, cfg["HEAT_SEASON"]) & (out["tmax"] >= thr["heat"]).to_numpy()
    return out


def hazard_summary(hz: pd.DataFrame, cfg: Dict[str, Any], years: int = 5) -> pd.DataFrame:
    """Liczba dni przymrozku i upału w każdym z ostatnich `years` lat + data ostatniego zdarzenia."""
    last = hz.index.max().year
    g = hz[hz.index.year > last - years]
    rows = []
    for y, d in g.groupby(g.index.year):
        rows.append({"year": int(y), "frost_days": int(d["frost"].sum()), "heat_days": int(d["heat"].sum()),
                     "last_frost": d.index[d["frost"]].max().strftime("%d.%m") if d["frost"].any() else "",
                     "min_tmin_spring": float(d.loc[in_season(d.index, cfg["FROST_SEASON"]), "tmin"].min()),
                     "max_tmax": float(d["tmax"].max())})
    return pd.DataFrame(rows)


# ==============================================================================
# IV. TEST OFFLINE (syntetyczna stacja w formacie Météo-France)
# ==============================================================================

def _selftest(out_dir: str) -> None:
    rng = np.random.default_rng(0)
    t = pd.date_range("1991-01-01", "2025-12-31", freq="D")
    doy = t.dayofyear.to_numpy()
    tn = 6 - 7 * np.cos(2 * np.pi * (doy - 15) / 365) + rng.normal(0, 3, len(t))
    tx = tn + 10 + rng.normal(0, 2, len(t))
    rr = np.where(rng.random(len(t)) < 0.3, rng.gamma(0.8, 8, len(t)), 0.0)
    os.makedirs(out_dir, exist_ok=True)
    p = os.path.join(out_dir, "Q_32_previous-1950-2023_RR-T-Vent.csv.gz")
    d = pd.DataFrame({"NUM_POSTE": "32107001", "NOM_USUEL": "TEST", "LAT": 43.95, "LON": 0.37, "ALTI": 90,
                      "AAAAMMJJ": t.strftime("%Y%m%d").astype(int), "RR": rr.round(1), "QRR": 1,
                      "TN": tn.round(1), "QTN": 1, "HTN": "", "TX": tx.round(1), "QTX": 1})
    d.loc[5, "QTN"] = 2
    with gzip.open(p, "wt") as f:
        d.to_csv(f, sep=";", index=False)
    mf = read_mf([p])
    assert np.isnan(mf["tn"].iloc[5]) and len(mf) == len(t)
    cfg = {"WX_VAL_START": "2016-01-01", "MF_MAX_KM": 30, "MF_MAX_STATIONS": 3, "MF_MIN_COVERAGE": 0.8,
           "FROST_SEASON": ("03-15", "05-15"), "FROST_TMIN": 0.0, "HEAT_SEASON": ("06-01", "08-31"),
           "HEAT_TMAX": 25.0, "WX_CAL_SPLIT_YEAR": 2021, "CLIM_REF": ("1991-01-01", "2020-12-31"),
           "SPI_DAYS": (30, 90), "THR_SPI1": -2.0, "THR_SPI3": -1.0}
    st = select_stations(mf, 43.94, 0.36, cfg)
    assert len(st) == 1 and st["dist_km"].iat[0] < 3
    # ERA5 = stacja + ciepły błąd Tmin 1,5 °C + szum; opad z szumem multiplikatywnym
    era = pd.DataFrame({"time": t, "t2m_min_c": tn + 1.5 + rng.normal(0, 1, len(t)), "t2m_max_c": tx + rng.normal(0, 1, len(t)),
                        "precip_mm": rr * rng.lognormal(0, 0.3, len(t))})
    val = validate_weather(st, mf, {"32107001": era}, cfg)
    b = val[(val["product"] == "ERA5L_TMIN") & (val["metric"] == "bias") & (val["period"] == "all")]["value"].iat[0]
    assert abs(b - 1.5) < 0.1, b
    thr = calibrated_thresholds(val, cfg)
    assert 0.5 <= thr["frost"] <= 2.5, thr                     # kalibracja przesuwa próg o ciepły błąd ERA5
    r_spi = val[(val["product"] == "ERA5L_PRECIP") & (val["segment"] == "SPI3") & (val["metric"] == "pearson_r")]["value"].iat[0]
    assert r_spi > 0.8, r_spi
    hz = weather_hazards(era, cfg, thr)
    assert hz["frost"].sum() > 0 and not hz.loc[hz.index.month == 1, "frost"].any()
    assert len(hazard_summary(hz, cfg)) == 5
    print(f"step_08 selftest OK: {len(val)} metryk, progi {thr}")


if __name__ == "__main__":
    import tempfile
    logging.basicConfig(level=logging.INFO)
    _selftest(tempfile.mkdtemp())
