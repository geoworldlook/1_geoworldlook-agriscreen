"""Shared loaders and statistics for Experiment A (vegetation signal vs ISMN Condom).

Read-only use of the repo modules (step_04 anomaly logic, step_07 ISMN reading/QC/bootstrap).
Definitions follow v1.0:
  - vegetation anomaly = step_04.scene_anomaly (clear_frac >= 0.9, other years, +-15 d, >= 5 ref scenes),
    months IV-X (step_05._veg_anomalies);
  - reference = mean of ISMN 20 and 30 cm daily (step_07.insitu_daily_depth, QC as in pipeline),
    standardised with step_04.clim_anomaly over 2016-2024, +-15 d, min_n=20 (step_07.validate_anomalies);
  - R with 95% block bootstrap (30-day calendar blocks, 1000 resamples, seed 42) = step_07._r_with_ci.
"""
import os
import sys
import functools

import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
DATA = os.path.join(SCR, "drive_data")
OUT = os.path.join(SCR, "exp_veg")
sys.path.insert(0, REPO)
import step_04_metrics_alert as s4  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402

VEG_CFG = {"VEG_MIN_CLEAR_FRAC": 0.9, "VEG_HALF_WINDOW_DAYS": 15, "VEG_MIN_REF": 5}
COMMON = ("2016-01-01", "2024-12-31")
VCFG = {"BOOTSTRAP_N": 1000, "BOOTSTRAP_BLOCK_DAYS": 30, "RANDOM_SEED": 42, "MIN_N_METRICS": 10}
INDICES = ("ndvi", "ndmi", "ndre", "crswir")


@functools.lru_cache(maxsize=None)
def obs_wide(months=(4, 10)) -> pd.DataFrame:
    """S-2 parcel statistics in wide format (one row per site x product x scene)."""
    o = pd.read_csv(os.path.join(DATA, "gwl_observations.csv"))
    o = o[o["product"].isin(["S2_10m", "S2SR_2.5m"])]
    w = o.pivot_table(index=["site_id", "product", "time_utc"], columns="variable", values="value").reset_index()
    w["time"] = pd.to_datetime(w["time_utc"]).dt.tz_localize(None)
    if months is not None:
        w = w[w["time"].dt.month.between(*months)]
    return w.sort_values("time").reset_index(drop=True)


def group(site: str, prod: str, months=(4, 10)) -> pd.DataFrame:
    w = obs_wide(months)
    return w[(w["site_id"] == site) & (w["product"] == prod)].copy()


@functools.lru_cache(maxsize=None)
def era5() -> pd.DataFrame:
    e = pd.read_csv(os.path.join(DATA, "era5_land_daily.csv"), parse_dates=["time"])
    e = e.set_index(e["time"].dt.floor("D")).sort_index()
    return e[~e.index.duplicated(keep="last")]


@functools.lru_cache(maxsize=None)
def insitu_depth(depth: float) -> pd.Series:
    return s7.insitu_daily_depth(depth, {"PROJECT_DIR": REPO})["sm"]


@functools.lru_cache(maxsize=None)
def insitu_rz() -> pd.Series:
    rz = pd.concat([insitu_depth(0.20), insitu_depth(0.30)], axis=1).dropna().mean(axis=1)
    return rz


@functools.lru_cache(maxsize=None)
def ins_z(kind: str = "rz") -> pd.Series:
    """Climatological z of ISMN: 'rz' = 20-30 cm (v1.0 reference), '10' = 10 cm."""
    s = insitu_rz() if kind == "rz" else insitu_depth(float(kind) / 100.0)
    return s4.clim_anomaly(s, COMMON, 15, min_n=20)["z"]


@functools.lru_cache(maxsize=None)
def era5_rz_z() -> pd.Series:
    e = era5().loc[COMMON[0]:COMMON[1]]
    return s4.clim_anomaly(s4.rootzone(e), COMMON, 15, min_n=20)["z"]


def daily(z: pd.Series) -> pd.Series:
    """Collapse a time-indexed series to daily means (as validate_anomalies)."""
    z = z.dropna()
    return z.groupby(z.index.floor("D")).mean()


def pair(x: pd.Series, y: pd.Series) -> pd.DataFrame:
    return daily(x).to_frame("x").join(y.rename("y"), how="inner").dropna()


def r_ci(x: pd.Series, y: pd.Series, blocks: str = "30d"):
    """Pearson R and 95% block-bootstrap CI. blocks='30d' (v1.0) or 'year'."""
    p = pair(x, y)
    n = len(p)
    if n < VCFG["MIN_N_METRICS"]:
        return dict(r=np.nan, lo=np.nan, hi=np.nan, n=n)
    r = float(np.corrcoef(p["x"], p["y"])[0, 1])
    if blocks == "30d":
        lo, hi = s7._block_bootstrap_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(),
                                        lambda a, b: np.corrcoef(a, b)[0, 1], VCFG)
    else:
        lo, hi = year_boot(p, lambda q: np.corrcoef(q["x"], q["y"])[0, 1])
    return dict(r=r, lo=lo, hi=hi, n=n)


def year_boot(p: pd.DataFrame, func, n_boot=1000, seed=42):
    rng = np.random.default_rng(seed)
    yrs = p.index.year.to_numpy()
    uy = np.unique(yrs)
    idx_by = {k: np.flatnonzero(yrs == k) for k in uy}
    st = []
    for _ in range(n_boot):
        pick = rng.choice(uy, len(uy), replace=True)
        idx = np.concatenate([idx_by[k] for k in pick])
        with np.errstate(all="ignore"):
            st.append(func(p.iloc[idx]))
    st = np.asarray(st, float)
    st = st[np.isfinite(st)]
    return float(np.percentile(st, 2.5)), float(np.percentile(st, 97.5))


def paired_diff_ci(xa: pd.Series, xb: pd.Series, y: pd.Series, n_boot=1000, seed=42, block_days=30):
    """R(xa,y) - R(xb,y) on the common days, with 30-day block bootstrap CI (same resample for both)."""
    p = daily(xa).to_frame("a").join(daily(xb).rename("b"), how="inner").join(y.rename("y"), how="inner").dropna()
    if len(p) < 10:
        return dict(d=np.nan, lo=np.nan, hi=np.nan, n=len(p), ra=np.nan, rb=np.nan)
    ra = np.corrcoef(p["a"], p["y"])[0, 1]
    rb = np.corrcoef(p["b"], p["y"])[0, 1]
    t = pd.Series(p.index)
    blk = ((t - t.min()) / pd.Timedelta(days=block_days)).astype(int).to_numpy()
    ub = np.unique(blk)
    by = {b: np.flatnonzero(blk == b) for b in ub}
    rng = np.random.default_rng(seed)
    A, B, Y = p["a"].to_numpy(), p["b"].to_numpy(), p["y"].to_numpy()
    ds = []
    for _ in range(n_boot):
        idx = np.concatenate([by[b] for b in rng.choice(ub, len(ub), replace=True)])
        ds.append(np.corrcoef(A[idx], Y[idx])[0, 1] - np.corrcoef(B[idx], Y[idx])[0, 1])
    ds = np.asarray(ds)
    ds = ds[np.isfinite(ds)]
    return dict(d=float(ra - rb), lo=float(np.percentile(ds, 2.5)), hi=float(np.percentile(ds, 97.5)),
                n=len(p), ra=float(ra), rb=float(rb))


def per_year_r(x: pd.Series, y: pd.Series) -> pd.Series:
    p = pair(x, y)
    return p.groupby(p.index.year).apply(lambda q: np.corrcoef(q["x"], q["y"])[0, 1] if len(q) >= 6 else np.nan)


def scene_z(df: pd.DataFrame, col: str, cfg=None) -> pd.Series:
    """v1.0 vegetation anomaly (step_04.scene_anomaly) returned as a time-indexed z series."""
    a = s4.scene_anomaly(df, col, cfg or VEG_CFG)
    return pd.Series(a["z"].to_numpy(float), index=pd.DatetimeIndex(a["time"]))


def events(x: pd.Series, y: pd.Series, thr=-1.0):
    """Event skill: x <= thr predicts y <= thr (on paired days). POD, FAR, CSI, HSS, n_obs_events."""
    p = pair(x, y)
    o, f = p["y"] <= thr, p["x"] <= thr
    h, m, fa, cn = int((o & f).sum()), int((o & ~f).sum()), int((~o & f).sum()), int((~o & ~f).sum())
    n = h + m + fa + cn
    pod = h / (h + m) if h + m else np.nan
    far = fa / (h + fa) if h + fa else np.nan
    csi = h / (h + m + fa) if h + m + fa else np.nan
    exp = ((h + m) * (h + fa) + (cn + m) * (cn + fa)) / n if n else np.nan
    hss = (h + cn - exp) / (n - exp) if n and n != exp else np.nan
    return dict(pod=pod, far=far, csi=csi, hss=hss, hits=h, misses=m, fa=fa, cn=cn, n=n)
