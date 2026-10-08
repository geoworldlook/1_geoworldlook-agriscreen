"""Experiment B (FAO-56 soil water balance) - shared loaders, v1.0 definitions and statistics.

Read-only use of the AgriWatch repo:
  - step_04.clim_anomaly / rootzone / dekad_end / spi  (anomaly definitions of v1.0),
  - step_07.insitu_daily_depth / _block_bootstrap_ci   (ISMN reading + QC, block bootstrap).
Definitions copied from step_07.validate_anomalies (v1.0 validation harness):
  - reference = mean of ISMN Condom 20 cm and 30 cm daily means (QC as pipeline), days with both depths,
  - anomalies = step_04.clim_anomaly over the COMMON period 2016-2024, +-15 d, min_n=20, for BOTH series,
  - R with 95 % block bootstrap (30-day calendar blocks, 1000 resamples, seed 42),
  - dekadal events: product = dekadal mean of the product's daily z (operational: ref 1991-2020),
    reference = dekadal mean of ISMN z (ref 2016-2024); event = z <= -1; POD/FAR.
"""
import logging
import os
import sys

import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
DATA = os.path.join(SCR, "drive_data")
OUT = os.path.join(SCR, "exp_wb")
sys.path.insert(0, REPO)
logging.disable(logging.CRITICAL)
import step_04_metrics_alert as s4  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402

COMMON = ("2016-01-01", "2024-12-31")       # ISMN period used by validate_anomalies
CLIM_REF = ("1991-01-01", "2020-12-31")     # operational ERA5 reference (MONITOR_CONFIG)
HW = 15                                     # CLIM_HALF_WINDOW_DAYS
THR = -1.0                                  # THR_SMA
VCFG = {"BOOTSTRAP_N": 1000, "BOOTSTRAP_BLOCK_DAYS": 30, "RANDOM_SEED": 42, "MIN_N_METRICS": 10}
LAT_DEG = 43.9744                           # Condom station (vineyard is 136 m away, same ERA5 cell)

_cache = {}


def era5() -> pd.DataFrame:
    if "era5" not in _cache:
        e = pd.read_csv(os.path.join(DATA, "era5_land_daily.csv"), parse_dates=["time"])
        e = e.set_index(e["time"].dt.floor("D")).sort_index()
        e = e[~e.index.duplicated(keep="last")].drop(columns="time")
        assert e.index.to_series().diff().dropna().eq(pd.Timedelta(days=1)).all(), "ERA5 daily series has gaps"
        assert not e.isna().any().any()
        _cache["era5"] = e
    return _cache["era5"]


def insitu_depth(depth_m: float) -> pd.Series:
    key = f"ismn_{depth_m}"
    if key not in _cache:
        _cache[key] = s7.insitu_daily_depth(depth_m, {"PROJECT_DIR": REPO})["sm"]
    return _cache[key]


def insitu_rz() -> pd.Series:
    """v1.0 reference: mean of 20 and 30 cm (days with both)."""
    return pd.concat([insitu_depth(0.20), insitu_depth(0.30)], axis=1).dropna().mean(axis=1)


def anom_common(s: pd.Series) -> pd.Series:
    """Validation anomaly (validate_anomalies): DOY climatology over 2016-2024, +-15 d, min_n=20."""
    s = s.loc[COMMON[0]:COMMON[1]]
    return s4.clim_anomaly(s, COMMON, HW, min_n=20)["z"]


def anom_oper(s: pd.Series) -> pd.Series:
    """Operational anomaly (era5_anomalies): DOY climatology over 1991-2020, +-15 d, min_n=30."""
    return s4.clim_anomaly(s, CLIM_REF, HW)["z"]


def ins_z(kind: str = "rz") -> pd.Series:
    key = f"insz_{kind}"
    if key not in _cache:
        s = insitu_rz() if kind == "rz" else insitu_depth(float(kind) / 100.0)
        _cache[key] = anom_common(s)
    return _cache[key]


# ----------------------------------------------------------------------------- statistics
def pair(x: pd.Series, y: pd.Series) -> pd.DataFrame:
    p = pd.concat([x.rename("x"), y.rename("y")], axis=1, join="inner")
    p = p.replace([np.inf, -np.inf], np.nan).dropna()
    return p


def r_ci(x: pd.Series, y: pd.Series) -> dict:
    """Pearson R + 95% CI from the repo's 30-day block bootstrap (step_07._block_bootstrap_ci)."""
    p = pair(x, y)
    if len(p) < VCFG["MIN_N_METRICS"]:
        return dict(r=np.nan, lo=np.nan, hi=np.nan, n=len(p))
    r = float(np.corrcoef(p["x"], p["y"])[0, 1])
    lo, hi = s7._block_bootstrap_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(),
                                    lambda a, b: np.corrcoef(a, b)[0, 1], VCFG)
    return dict(r=r, lo=lo, hi=hi, n=len(p))


def _blocks(index: pd.DatetimeIndex, how: str) -> np.ndarray:
    if how == "30d":
        return ((index - index.min()) / pd.Timedelta(days=30)).astype(int).to_numpy()
    if how == "year":
        return index.year.to_numpy()
    raise ValueError(how)


def paired_delta_r(xa: pd.Series, xb: pd.Series, y: pd.Series, how: str = "30d", n_boot: int = 2000,
                   seed: int = 42) -> dict:
    """R(xa,y) - R(xb,y) on the SAME days, 95% CI by resampling the same calendar blocks for both."""
    p = pd.concat([xa.rename("a"), xb.rename("b"), y.rename("y")], axis=1, join="inner")
    p = p.replace([np.inf, -np.inf], np.nan).dropna()
    a, b, yy = p["a"].to_numpy(), p["b"].to_numpy(), p["y"].to_numpy()
    blk = _blocks(p.index, how)
    ub = np.unique(blk)
    idx_by = {k: np.flatnonzero(blk == k) for k in ub}
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n_boot):
        idx = np.concatenate([idx_by[k] for k in rng.choice(ub, len(ub), replace=True)])
        d.append(np.corrcoef(a[idx], yy[idx])[0, 1] - np.corrcoef(b[idx], yy[idx])[0, 1])
    d = np.asarray(d)
    ra, rb = np.corrcoef(a, yy)[0, 1], np.corrcoef(b, yy)[0, 1]
    return dict(r_a=ra, r_b=rb, delta=ra - rb, lo=float(np.percentile(d, 2.5)), hi=float(np.percentile(d, 97.5)),
                n=len(p), p_le0=float(np.mean(d <= 0)))


def r_by_year(x: pd.Series, y: pd.Series) -> pd.Series:
    p = pair(x, y)
    return p.groupby(p.index.year).apply(lambda g: np.corrcoef(g["x"], g["y"])[0, 1] if len(g) > 30 else np.nan)


def dekad_mean(z: pd.Series) -> pd.Series:
    z = z.dropna()
    dk = s4.dekad_end(pd.Series(z.index)).to_numpy()
    return pd.Series(z.to_numpy(), index=dk).groupby(level=0).mean()


def pod_far(prod_dk: pd.Series, ref_dk: pd.Series, thr: float = THR) -> dict:
    j = pd.concat([prod_dk.rename("p"), ref_dk.rename("o")], axis=1, join="inner").dropna()
    obs, prd = j["o"] <= thr, j["p"] <= thr
    h, m, f = int((obs & prd).sum()), int((obs & ~prd).sum()), int((~obs & prd).sum())
    return dict(pod=h / (h + m) if h + m else np.nan, far=f / (h + f) if h + f else np.nan,
                hits=h, misses=m, false_alarms=f, n=len(j))


def pod_far_ci(prod_dk: pd.Series, ref_dk: pd.Series, thr: float = THR, n_boot: int = 2000, seed: int = 42) -> dict:
    """POD/FAR with 95% CI from a by-year block bootstrap of dekads."""
    j = pd.concat([prod_dk.rename("p"), ref_dk.rename("o")], axis=1, join="inner").dropna()
    base = pod_far(j["p"], j["o"], thr)
    yrs = j.index.year.to_numpy()
    uy = np.unique(yrs)
    idx_by = {k: np.flatnonzero(yrs == k) for k in uy}
    rng = np.random.default_rng(seed)
    pods, fars = [], []
    for _ in range(n_boot):
        idx = np.concatenate([idx_by[k] for k in rng.choice(uy, len(uy), replace=True)])
        q = _pf(j["p"].to_numpy()[idx], j["o"].to_numpy()[idx], thr)
        pods.append(q[0])
        fars.append(q[1])
    base.update(pod_lo=np.nanpercentile(pods, 2.5), pod_hi=np.nanpercentile(pods, 97.5),
                far_lo=np.nanpercentile(fars, 2.5), far_hi=np.nanpercentile(fars, 97.5))
    return base


def _pf(p: np.ndarray, o: np.ndarray, thr: float):
    obs, prd = o <= thr, p <= thr
    h, m, f = np.sum(obs & prd), np.sum(obs & ~prd), np.sum(~obs & prd)
    return (h / (h + m) if h + m else np.nan, f / (h + f) if h + f else np.nan)
