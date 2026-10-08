"""Shared loaders for the vegetation-anomaly experiments (read-only use of repo modules)."""
import os
import sys

import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
DATA = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/drive_data"
sys.path.insert(0, REPO)
import step_04_metrics_alert as s4  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402

CFG_VEG = {"VEG_MIN_CLEAR_FRAC": 0.9, "VEG_HALF_WINDOW_DAYS": 15, "VEG_MIN_REF": 5}
COMMON = ("2016-01-01", "2024-12-31")
VCFG = {"BOOTSTRAP_N": 1000, "BOOTSTRAP_BLOCK_DAYS": 30, "RANDOM_SEED": 42, "MIN_N_METRICS": 10}


def obs_wide():
    o = pd.read_csv(os.path.join(DATA, "gwl_observations.csv"))
    o = o[o["product"].isin(["S2_10m", "S2SR_2.5m"])]
    w = o.pivot_table(index=["site_id", "product", "time_utc"], columns="variable", values="value").reset_index()
    w["time"] = pd.to_datetime(w["time_utc"]).dt.tz_localize(None)
    w = w[w["time"].dt.month.between(4, 10)]
    return w


def era5():
    e = pd.read_csv(os.path.join(DATA, "era5_land_daily.csv"), parse_dates=["time"])
    e = e.set_index(e["time"].dt.floor("D")).sort_index()
    e = e[~e.index.duplicated(keep="last")]
    return e


def insitu_rz():
    ov = {"PROJECT_DIR": REPO}
    d20 = s7.insitu_daily_depth(0.20, ov)["sm"]
    d30 = s7.insitu_daily_depth(0.30, ov)["sm"]
    rz = pd.concat([d20, d30], axis=1).dropna().mean(axis=1)
    return rz


def insitu_z():
    rz = insitu_rz()
    return s4.clim_anomaly(rz, COMMON, 15, min_n=20)["z"]


def era5_rz_z():
    e = era5().loc[COMMON[0]:COMMON[1]]
    return s4.clim_anomaly(s4.rootzone(e), COMMON, 15, min_n=20)["z"]


def r_ci(x: pd.Series, y: pd.Series):
    p = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    if len(p) < 10:
        return np.nan, np.nan, np.nan, len(p)
    r = float(np.corrcoef(p["x"], p["y"])[0, 1])
    lo, hi = s7._block_bootstrap_ci(pd.Series(p.index), p["x"].to_numpy(), p["y"].to_numpy(),
                                    lambda a, b: np.corrcoef(a, b)[0, 1], VCFG)
    return r, lo, hi, len(p)


def partial_r(x, y, z):
    """Partial correlation of x and y controlling for z (linear)."""
    p = pd.concat([x.rename("x"), y.rename("y"), z.rename("z")], axis=1).dropna()
    def res(a, b):
        A = np.c_[np.ones(len(b)), b]
        beta = np.linalg.lstsq(A, a, rcond=None)[0]
        return a - A @ beta
    rx, ry = res(p["x"].to_numpy(), p["z"].to_numpy()), res(p["y"].to_numpy(), p["z"].to_numpy())
    return float(np.corrcoef(rx, ry)[0, 1]), len(p)


def partial_r_ci(x, y, z):
    p = pd.concat([x.rename("x"), y.rename("y"), z.rename("z")], axis=1).dropna()
    def f_idx(idx):
        q = p.iloc[idx]
        A = np.c_[np.ones(len(q)), q["z"].to_numpy()]
        rx = q["x"].to_numpy() - A @ np.linalg.lstsq(A, q["x"].to_numpy(), rcond=None)[0]
        ry = q["y"].to_numpy() - A @ np.linalg.lstsq(A, q["y"].to_numpy(), rcond=None)[0]
        return np.corrcoef(rx, ry)[0, 1]
    r = f_idx(np.arange(len(p)))
    ii = np.arange(len(p)).astype(float)
    lo, hi = s7._block_bootstrap_ci(pd.Series(p.index), ii, ii, lambda a, b: f_idx(a.astype(int)), VCFG)
    return float(r), lo, hi, len(p)


def daily_series(df, col):
    g = df.dropna(subset=[col]).copy()
    g["day"] = g["time"].dt.floor("D")
    return g.set_index("day")[col].groupby(level=0).mean()
