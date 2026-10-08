"""Experiment DA - loaders, v1.0 anomaly/bootstrap definitions (imported read-only from the repo), statistics.

Repo functions used (read-only, via sys.path):
  step_04_metrics_alert.clim_anomaly / rootzone / dekad_end
  step_07_station_pipeline.insitu_daily_depth / _r_with_ci / _block_bootstrap_ci
step_07 loaders resolve 'data/7_isismn_data/SMOSMANIA/Condom' relative to the CWD -> we chdir to the repo
only while loading ISMN, and restore the CWD afterwards.
"""
from __future__ import annotations

import logging
import os
import sys

import numpy as np
import pandas as pd

import config as C

sys.dont_write_bytecode = True
REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
DRIVE = os.path.join(SCR, "drive_data")
HERE = os.path.join(SCR, "exp_da")
OUT = os.path.join(HERE, "out")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, REPO)
logging.disable(logging.CRITICAL)
import step_04_metrics_alert as s4  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402

_cache: dict = {}


# ============================================================================ data
def era5() -> pd.DataFrame:
    if "era5" not in _cache:
        e = pd.read_csv(os.path.join(DRIVE, "era5_land_daily.csv"), parse_dates=["time"])
        e = e.set_index(e["time"].dt.floor("D")).sort_index()
        e = e[~e.index.duplicated(keep="last")].drop(columns="time")
        assert e.index.to_series().diff().dropna().eq(pd.Timedelta(days=1)).all(), "ERA5 daily series has gaps"
        assert not e.isna().any().any()
        assert (e["precip_mm"] > -1e-3).all()
        assert (e["t2m_c"] >= e["t2m_min_c"]).all()
        _cache["era5"] = e
    return _cache["era5"]


def insitu_depth(depth_m: float) -> pd.Series:
    key = f"ismn_{depth_m}"
    if key not in _cache:
        cwd = os.getcwd()
        os.chdir(REPO)                      # step_07 uses relative ISMN paths
        try:
            _cache[key] = s7.insitu_daily_depth(depth_m, {})["sm"]
        finally:
            os.chdir(cwd)
    return _cache[key]


def ismn_ref() -> pd.Series:
    """v1.0 reference: mean of 20 and 30 cm daily means, days with both depths."""
    return pd.concat([insitu_depth(0.20), insitu_depth(0.30)], axis=1).dropna().mean(axis=1)


def s1_raw() -> pd.DataFrame:
    """S-1 change-detection SSM (S1_CD_A sm_s1) at SMOSMANIA_Condom, QC'd. Columns: t, value, qc, orbit."""
    o = pd.read_csv(os.path.join(DRIVE, "gwl_observations.csv"))
    o = o[(o.site_id == C.S1["site"]) & (o["product"] == C.S1["product"]) & (o.variable == C.S1["variable"])]
    d = pd.DataFrame({"t": pd.to_datetime(o["time_utc"]).dt.tz_localize(None).to_numpy(),
                      "value": o["value"].to_numpy(float), "qc": o["qc_flags"].fillna("").to_numpy(),
                      "orbit": o["orbit"].to_numpy()})
    assert d["value"].between(0, 0.5).all()
    bad = d["qc"].apply(lambda s: any(f in s.split(";") for f in C.S1["drop_flags"]))
    d = d[~bad].sort_values("t").reset_index(drop=True)
    return d


def s1_daily(d: pd.DataFrame) -> pd.Series:
    """Assign each acquisition to a model analysis time (end of a model day) and average same-time obs.
    06 UTC passes go to the end of the previous day (6 h away instead of 18 h)."""
    day = d["t"].dt.floor("D")
    if C.S1["morning_to_previous_day"]:
        day = day.where(d["t"].dt.hour >= 12, day - pd.Timedelta(days=1))
    return d.groupby(day.to_numpy())["value"].mean().sort_index()


# ============================================================================ hargreaves
def et0_hargreaves(tmean_c: pd.Series, tmin_c: pd.Series, lat_deg: float) -> pd.Series:
    """Hargreaves & Samani (1985), FAO-56 eq. 52; Ra from FAO-56 eqs. 21-25 (mm/day equivalent).
    Tmax approximated as 2*Tmean - Tmin (no Tmax in the ERA5-Land file)."""
    doy = tmean_c.index.dayofyear.to_numpy()
    phi = np.deg2rad(lat_deg)
    dr = 1 + 0.033 * np.cos(2 * np.pi * doy / 365)
    dec = 0.409 * np.sin(2 * np.pi * doy / 365 - 1.39)
    ws = np.arccos(-np.tan(phi) * np.tan(dec))
    ra_mj = 24 * 60 / np.pi * 0.0820 * dr * (ws * np.sin(phi) * np.sin(dec) + np.cos(phi) * np.cos(dec) * np.sin(ws))
    ra_mm = 0.408 * ra_mj
    dtr = (2 * tmean_c - tmin_c) - tmin_c
    assert (dtr >= 0).all()
    et0 = 0.0023 * ra_mm * (tmean_c + 17.8) * np.sqrt(dtr)
    return et0.clip(lower=0.0)


def forcing() -> pd.DataFrame:
    e = era5()
    f = pd.DataFrame({"precip_mm": e["precip_mm"].clip(lower=0.0),     # tiny negative ERA5 accumulations -> 0
                      "et0_mm": et0_hargreaves(e["t2m_c"], e["t2m_min_c"], C.SITE["lat_deg"])}, index=e.index)
    return f.loc[C.SPINUP_DET_START:C.END]


# ============================================================================ anomalies (v1.0 definitions)
def z_common(s: pd.Series) -> pd.Series:
    """Validation anomaly (validate_anomalies): DOY climatology over 2016-2024, +-15 d, min_n=20."""
    s = s.loc[C.COMMON[0]:C.COMMON[1]]
    return s4.clim_anomaly(s, C.COMMON, C.HW, min_n=20)["z"]


def z_oper(s: pd.Series) -> pd.Series:
    """Operational anomaly (era5_anomalies): DOY climatology over 1991-2020, +-15 d, min_n=30."""
    return s4.clim_anomaly(s, C.CLIM_REF_OPER, C.HW)["z"]


def _circ(a, d):
    x = np.abs(a - d)
    return np.minimum(x, 366 - x)


def pooled_member_clim(X: np.ndarray, index: pd.DatetimeIndex, ref: tuple) -> tuple[np.ndarray, np.ndarray]:
    """DOY climatology (mean, sd) pooling all ensemble members and days within +-HW of each DOY in `ref`.
    X: (n_days, n_members). Returns per-day arrays (mean, sd) aligned with `index`."""
    assert X.shape[0] == len(index)
    inref = (index >= ref[0]) & (index <= ref[1])
    m1 = X[inref].mean(axis=1)
    m2 = (X[inref] ** 2).mean(axis=1)
    rd = index[inref].dayofyear.to_numpy()
    doy = index.dayofyear.to_numpy()
    mu = np.full(len(index), np.nan)
    sd = np.full(len(index), np.nan)
    n_mem = X.shape[1]
    for d in np.unique(doy):
        sel = _circ(rd, d) <= C.HW
        n = sel.sum() * n_mem
        mean = m1[sel].mean()
        var = (m2[sel].mean() - mean ** 2) * n / (n - 1)
        mu[doy == d], sd[doy == d] = mean, np.sqrt(var)
    return mu, sd


# ============================================================================ statistics
def pair(*series, names=None) -> pd.DataFrame:
    names = names or [f"v{i}" for i in range(len(series))]
    p = pd.concat([s.rename(n) for s, n in zip(series, names)], axis=1, join="inner")
    return p.replace([np.inf, -np.inf], np.nan).dropna()


def r_ci(x: pd.Series, y: pd.Series) -> dict:
    """Pearson R + 95 % CI with the repo's 30-day block bootstrap (step_07._r_with_ci, 1000 draws, seed 42)."""
    p = pair(x, y, names=["x", "y"])
    r, lo, hi = s7._r_with_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(), C.BOOT)
    return dict(r=r, lo=lo, hi=hi, n=len(p))


def paired_delta_r(xa: pd.Series, xb: pd.Series, y: pd.Series, n_boot: int = C.PAIRED_BOOT_N, seed: int = 42) -> dict:
    """R(xa,y) - R(xb,y) on the SAME days; 95 % CI from resampling the same 30-day calendar blocks."""
    p = pair(xa, xb, y, names=["a", "b", "y"])
    a, b, yy = (p[c].to_numpy() for c in "aby")
    blk = ((p.index - p.index.min()) / pd.Timedelta(days=30)).astype(int).to_numpy()
    ub = np.unique(blk)
    idx_by = {k: np.flatnonzero(blk == k) for k in ub}
    rng = np.random.default_rng(seed)
    d = np.empty(n_boot)
    for i in range(n_boot):
        idx = np.concatenate([idx_by[k] for k in rng.choice(ub, len(ub), replace=True)])
        d[i] = np.corrcoef(a[idx], yy[idx])[0, 1] - np.corrcoef(b[idx], yy[idx])[0, 1]
    ra, rb = np.corrcoef(a, yy)[0, 1], np.corrcoef(b, yy)[0, 1]
    return dict(r_a=ra, r_b=rb, delta=ra - rb, lo=float(np.percentile(d, 2.5)), hi=float(np.percentile(d, 97.5)),
                n=len(p), p_le0=float(np.mean(d <= 0)))


def to_dekad(z: pd.Series) -> pd.Series:
    """Dekadal mean of a daily series, indexed by dekad end (build_status / validate_anomalies)."""
    z = z.dropna()
    dk = s4.dekad_end(pd.Series(z.index)).to_numpy()
    return pd.Series(z.to_numpy(), index=pd.DatetimeIndex(dk)).groupby(level=0).mean()


def dekad_frame(X: np.ndarray, index: pd.DatetimeIndex) -> pd.DataFrame:
    """Dekadal mean of every ensemble member (rows = dekad end, columns = members)."""
    dk = s4.dekad_end(pd.Series(index)).to_numpy()
    return pd.DataFrame(X, index=pd.DatetimeIndex(dk)).groupby(level=0).mean()


def pod_far(prd: np.ndarray, obs: np.ndarray) -> dict:
    h, m, f = int((obs & prd).sum()), int((obs & ~prd).sum()), int((~obs & prd).sum())
    return dict(pod=h / (h + m) if h + m else np.nan, far=f / (h + f) if h + f else np.nan,
                hits=h, misses=m, false_alarms=f, n=len(obs))


def brier(p: np.ndarray, o: np.ndarray) -> float:
    return float(np.mean((p - o.astype(float)) ** 2))


def reliability(p: np.ndarray, o: np.ndarray, bins) -> pd.DataFrame:
    b = np.digitize(p, bins) - 1
    rows = []
    for k in range(len(bins) - 1):
        s = b == k
        rows.append(dict(bin=f"[{bins[k]:.1f},{min(bins[k + 1], 1):.1f}{']' if k == len(bins) - 2 else ')'}",
                         n=int(s.sum()), p_mean=float(p[s].mean()) if s.any() else np.nan,
                         obs_freq=float(o[s].mean()) if s.any() else np.nan))
    return pd.DataFrame(rows)


def brier_decomposition(p: np.ndarray, o: np.ndarray, bins) -> dict:
    """Murphy (1973): BS = REL - RES + UNC (binned; exact only if p is constant within bins)."""
    o = o.astype(float)
    ob = o.mean()
    b = np.digitize(p, bins) - 1
    rel = res = 0.0
    for k in np.unique(b):
        s = b == k
        rel += s.sum() * (p[s].mean() - o[s].mean()) ** 2
        res += s.sum() * (o[s].mean() - ob) ** 2
    n = len(o)
    return dict(rel=rel / n, res=res / n, unc=ob * (1 - ob))
