"""Shared helpers for Experiment C (soil-moisture layer and event skill).

Repo is used read-only: anomaly / QC / bootstrap logic is imported from step_04 and step_07 so that every
number is computed with the same definitions as v1.0 (clim_anomaly, rootzone, dekad_end, insitu_daily_depth,
_block_bootstrap_ci, _moving_anomaly).
"""
from __future__ import annotations

import os
import sys
import warnings

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
sys.dont_write_bytecode = True

REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
DRIVE = os.path.join(SCR, "drive_data")
OUT = os.path.join(SCR, "exp_sm", "out")
os.makedirs(OUT, exist_ok=True)
sys.path.insert(0, REPO)

import step_07_station_pipeline as s7  # noqa: E402
from step_04_metrics_alert import clim_anomaly, dekad_end, rootzone  # noqa: E402

OVR = {"PROJECT_DIR": REPO, "BOOTSTRAP_N": 1000}
CFG = s7.build_config(OVR)              # BOOTSTRAP_BLOCK_DAYS=30, seed 42 (as in v1.0 validation)
COMMON = ("2016-01-01", "2024-12-31")   # validation period (ISMN files end 2024-12-31)
CLIM_REF = ("1991-01-01", "2020-12-31")  # operational ERA5 climatology
HW = 15
THR = -1.0
YEARS = list(range(2016, 2025))


# ---------------------------------------------------------------- data
def era5_full() -> pd.DataFrame:
    e = pd.read_csv(os.path.join(DRIVE, "era5_land_daily.csv"), parse_dates=["time"])
    e = e.set_index(e["time"].dt.floor("D")).sort_index()
    return e[~e.index.duplicated(keep="last")]


def era5_layers(e: pd.DataFrame) -> dict:
    """ERA5-Land layer combinations (layer bounds 0-7, 7-28, 28-100 cm)."""
    return {
        "RZ_0_100": rootzone(e),                                         # v1.0 operational
        "L1_0_7": e["sm_l1"],
        "L2_7_28": e["sm_l2"],
        "W_0_28": (7 * e["sm_l1"] + 21 * e["sm_l2"]) / 28.0,             # thickness-weighted 0-28 cm
        "M_20_30": (8 * e["sm_l2"] + 2 * e["sm_l3"]) / 10.0,             # overlap of 20-30 cm with layers 2/3
        "L3_28_100": e["sm_l3"],
    }


_INSITU_CACHE: dict = {}


def insitu(depth: float, station: str = "Condom") -> pd.DataFrame:
    key = (depth, station)
    if key not in _INSITU_CACHE:
        ov = dict(OVR, STATION=station)
        if station != "Condom":
            ov["EXCLUDE_PERIODS"] = []
        _INSITU_CACHE[key] = s7.insitu_daily_depth(depth, ov)
    return _INSITU_CACHE[key]


def ismn_ref(station: str = "Condom") -> pd.Series:
    """v1.0 reference: mean of 20 and 30 cm daily means (days with both)."""
    d20 = insitu(0.20, station)["sm"]
    d30 = insitu(0.30, station)["sm"]
    return pd.concat([d20, d30], axis=1).dropna().mean(axis=1)


def s1_obs(var: str = "sm_s1") -> pd.Series:
    o = pd.read_csv(os.path.join(DRIVE, "gwl_observations.csv"))
    o = o[(o.site_id == "SMOSMANIA_Condom") & (o["product"] == "S1_CD_A") & (o.variable == var)]
    t = pd.to_datetime(o["time_utc"]).dt.tz_localize(None)
    return pd.Series(o["value"].to_numpy(float), index=t).sort_index()


# ---------------------------------------------------------------- anomalies
def zclim(s: pd.Series, ref=COMMON, hw: int = HW, min_n: int = 20) -> pd.Series:
    """DOY climatology z-score (step_04.clim_anomaly). min_n=20 as in validate_anomalies."""
    return clim_anomaly(s.dropna(), ref, hw, min_n=min_n)["z"]


def zclim_years(s: pd.Series, years, hw: int = HW, min_n: int = 20) -> pd.Series:
    """DOY-climatology z with the reference pool restricted to `years` (used inside LOYO folds)."""
    s = s.dropna().sort_index()
    r = s[s.index.year.isin(list(years))]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    doy = s.index.dayofyear.to_numpy()
    z = np.full(len(s), np.nan)
    v = s.to_numpy(float)
    for d in np.unique(doy):
        dd = np.abs(rd - d)
        pool = rv[np.minimum(dd, 366 - dd) <= hw]
        if len(pool) < min_n:
            continue
        sel = doy == d
        z[sel] = (v[sel] - pool.mean()) / pool.std(ddof=1)
    return pd.Series(z, index=s.index)


def anom35(s: pd.Series) -> pd.Series:
    return s7._moving_anomaly(s, 35, 15)


def swi(s: pd.Series, T: float) -> pd.Series:
    """Recursive exponential filter (Albergel et al. 2008, eq. 3-4; Wagner et al. 1999) on irregular obs.
    Returns the daily SWI = filter state after the last observation of each day, carried forward max 6 days
    (S-1 revisit here is 1-3 days; longer gaps are left as NaN)."""
    s = s.dropna().sort_index()
    t = ((s.index - s.index[0]) / pd.Timedelta(days=1)).to_numpy(float)
    v = s.to_numpy(float)
    out = np.empty(len(v))
    K, sw = 1.0, v[0]
    out[0] = sw
    for i in range(1, len(v)):
        K = K / (K + np.exp(-(t[i] - t[i - 1]) / T))
        sw = sw + K * (v[i] - sw)
        out[i] = sw
    d = pd.Series(out, index=s.index).groupby(s.index.floor("D")).last()
    return d.asfreq("D").ffill(limit=6)


# ---------------------------------------------------------------- statistics
def pair(*series, names=None) -> pd.DataFrame:
    names = names or [f"v{i}" for i in range(len(series))]
    return pd.concat([s.rename(n) for s, n in zip(series, names)], axis=1).dropna()


def r_ci(x: pd.Series, y: pd.Series):
    """Pearson R with v1.0 block-bootstrap 95% CI (30-day calendar blocks, 1000 draws, seed 42)."""
    p = pair(x, y, names=["x", "y"])
    if len(p) < 10:
        return np.nan, np.nan, np.nan, len(p)
    r, lo, hi = s7._r_with_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(), CFG)
    return r, lo, hi, len(p)


def _blocks(idx: pd.DatetimeIndex, block_days: int = 30):
    t = pd.Series(idx)
    b = ((t - t.min()) / pd.Timedelta(days=block_days)).astype(int).to_numpy()
    u = np.unique(b)
    return u, {k: np.flatnonzero(b == k) for k in u}


def diff_r_ci(a: pd.Series, b: pd.Series, y: pd.Series, n_boot: int = 1000, block_days: int = 30, seed: int = 42):
    """Paired block-bootstrap of R(a,y) - R(b,y) on common days. Returns d, lo, hi, n, share(d>0)."""
    p = pair(a, b, y, names=["a", "b", "y"])
    A, B, Y = (p[c].to_numpy() for c in "aby")
    u, ib = _blocks(p.index, block_days)
    rng = np.random.default_rng(seed)
    d0 = np.corrcoef(A, Y)[0, 1] - np.corrcoef(B, Y)[0, 1]
    ds = []
    for _ in range(n_boot):
        idx = np.concatenate([ib[k] for k in rng.choice(u, len(u))])
        ds.append(np.corrcoef(A[idx], Y[idx])[0, 1] - np.corrcoef(B[idx], Y[idx])[0, 1])
    ds = np.asarray(ds)
    return d0, np.percentile(ds, 2.5), np.percentile(ds, 97.5), len(p), float((ds > 0).mean())


def r_by_year(x: pd.Series, y: pd.Series) -> pd.Series:
    p = pair(x, y, names=["x", "y"])
    return p.groupby(p.index.year).apply(lambda g: g["x"].corr(g["y"]) if len(g) > 30 else np.nan)


# ---------------------------------------------------------------- dekads and events
def to_dekad(z: pd.Series) -> pd.Series:
    """Dekadal mean of a daily series, indexed by dekad end (as build_status / validate_anomalies)."""
    z = z.dropna()
    dk = dekad_end(pd.Series(z.index)).to_numpy()
    return pd.Series(z.to_numpy(), index=pd.DatetimeIndex(dk)).groupby(level=0).mean()


def contingency(obs: np.ndarray, prd: np.ndarray) -> dict:
    h = int((obs & prd).sum()); m = int((obs & ~prd).sum()); f = int((~obs & prd).sum()); c = int((~obs & ~prd).sum())
    n = h + m + f + c
    pod = h / (h + m) if h + m else np.nan
    far = f / (h + f) if h + f else np.nan
    csi = h / (h + m + f) if h + m + f else np.nan
    bias = (h + f) / (h + m) if h + m else np.nan
    hr = (h + m) * (h + f) / n if n else np.nan           # hits expected by chance
    ets = (h - hr) / (h + m + f - hr) if (h + m + f - hr) else np.nan
    pofd = f / (f + c) if f + c else np.nan
    return {"hits": h, "misses": m, "false_alarms": f, "corr_neg": c, "n": n, "pod": pod, "far": far, "csi": csi,
            "freq_bias": bias, "ets": ets, "pss": pod - pofd if np.isfinite(pod) and np.isfinite(pofd) else np.nan}


def contingency_ci(obs: pd.Series, prd: pd.Series, n_boot: int = 2000, seed: int = 42, by: str = "year"):
    """Bootstrap CI of POD/FAR/CSI resampling whole years (by='year') or 90-day blocks (by='90d')."""
    idx = obs.index
    if by == "year":
        b = idx.year.to_numpy()
    else:
        b = ((idx - idx.min()) / pd.Timedelta(days=90)).astype(int).to_numpy()
    u = np.unique(b)
    ib = {k: np.flatnonzero(b == k) for k in u}
    O, P = obs.to_numpy(bool), prd.to_numpy(bool)
    rng = np.random.default_rng(seed)
    st = {k: [] for k in ("pod", "far", "csi")}
    for _ in range(n_boot):
        ii = np.concatenate([ib[k] for k in rng.choice(u, len(u))])
        c = contingency(O[ii], P[ii])
        for k in st:
            st[k].append(c[k])
    return {k: (np.nanpercentile(v, 2.5), np.nanpercentile(v, 97.5)) for k, v in st.items()}


def persist2(flag: pd.Series) -> pd.Series:
    """Event declared at dekad t if the trigger holds at t and t-1 (consecutive dekads)."""
    f = flag.astype(bool)
    return f & f.shift(1, fill_value=False)


def hysteresis(z: pd.Series, on: float = -1.0, off: float = -0.5) -> pd.Series:
    """EDO-style memory: event starts when z <= on and is kept while z <= off (factsheet CDI v4, table 2a)."""
    out, state = [], False
    for v in z.to_numpy():
        state = (v <= on) or (state and v <= off)
        out.append(state)
    return pd.Series(out, index=z.index)


def fmt(x, nd=3):
    return "nan" if x is None or not np.isfinite(x) else f"{x:.{nd}f}"
