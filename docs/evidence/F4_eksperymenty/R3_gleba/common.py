"""Shared loaders for the soil-moisture-layer analysis (read-only use of the repo)."""
import os
import sys

import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
DRIVE = os.path.join(SCR, "drive_data")
sys.dont_write_bytecode = True
sys.path.insert(0, REPO)

import step_07_station_pipeline as s7  # noqa: E402
from step_04_metrics_alert import clim_anomaly, rootzone, dekad_end  # noqa: E402

OVR = {"PROJECT_DIR": REPO}
CFG = s7.build_config(OVR)
COMMON = ("2016-01-01", "2024-12-31")
HW = 15


def era5():
    e = pd.read_csv(os.path.join(DRIVE, "era5_land_daily.csv"), parse_dates=["time"])
    e = e.set_index(e["time"].dt.floor("D")).sort_index()
    e = e[~e.index.duplicated(keep="last")]
    return e


def insitu(depth, station="Condom"):
    ov = dict(OVR, STATION=station)
    if station != "Condom":
        ov["EXCLUDE_PERIODS"] = []
    return s7.insitu_daily_depth(depth, ov)


def ismn_rz(station="Condom"):
    d20 = insitu(0.20, station)["sm"]
    d30 = insitu(0.30, station)["sm"]
    return pd.concat([d20, d30], axis=1).dropna().mean(axis=1)


def zclim(s, ref=COMMON, hw=HW, min_n=20):
    return clim_anomaly(s.dropna(), ref, hw, min_n=min_n)["z"]


def r_ci(x, y, n_boot=1000, block=30, seed=42):
    p = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if len(p) < 10:
        return np.nan, np.nan, np.nan, len(p)
    r, lo, hi = s7._r_with_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(), CFG)
    return r, lo, hi, len(p)


def paired_diff_ci(a, b, y, n_boot=1000, block=30, seed=42):
    """Block-bootstrap CI of R(a,y) - R(b,y) on common days."""
    p = pd.concat([a.rename("a"), b.rename("b"), y.rename("y")], axis=1).dropna()
    t = pd.Series(p.index)
    blk = ((t - t.min()) / pd.Timedelta(days=block)).astype(int).to_numpy()
    u = np.unique(blk)
    ib = {k: np.flatnonzero(blk == k) for k in u}
    rng = np.random.default_rng(seed)
    A, B, Y = p["a"].to_numpy(), p["b"].to_numpy(), p["y"].to_numpy()
    d0 = np.corrcoef(A, Y)[0, 1] - np.corrcoef(B, Y)[0, 1]
    ds = []
    for _ in range(n_boot):
        idx = np.concatenate([ib[k] for k in rng.choice(u, len(u))])
        ds.append(np.corrcoef(A[idx], Y[idx])[0, 1] - np.corrcoef(B[idx], Y[idx])[0, 1])
    return d0, np.percentile(ds, 2.5), np.percentile(ds, 97.5), len(p)


def swi_regular(s, T):
    """Exponential filter (Wagner 1999 / Albergel 2008 recursive form) for a daily series with gaps."""
    s = s.dropna().sort_index()
    out = np.empty(len(s))
    t = (s.index - s.index[0]) / pd.Timedelta(days=1)
    t = t.to_numpy(float)
    v = s.to_numpy(float)
    K, swi = 1.0, v[0]
    out[0] = swi
    for i in range(1, len(v)):
        dt = t[i] - t[i - 1]
        K = K / (K + np.exp(-dt / T))
        swi = swi + K * (v[i] - swi)
        out[i] = swi
    return pd.Series(out, index=s.index)


def swi_daily(s, T):
    """SWI from irregular obs, evaluated as daily series (value of the filter at each day, last-obs carried)."""
    sw = swi_regular(s, T)
    d = sw.groupby(sw.index.floor("D")).last()
    return d
