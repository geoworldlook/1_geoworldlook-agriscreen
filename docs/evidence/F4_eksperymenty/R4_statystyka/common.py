"""Shared loaders for the validation-design analysis (read-only use of the repo code)."""
import os
import sys

import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
DD = os.path.join(SCR, "drive_data")
sys.path.insert(0, REPO)

import step_04_metrics_alert as s4  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402

COMMON = ("2016-01-01", "2024-12-31")
HW = 15


def era5():
    e = pd.read_csv(os.path.join(DD, "era5_land_daily.csv"), parse_dates=["time"])
    e = e.set_index(e["time"].dt.floor("D")).sort_index()
    return e[~e.index.duplicated(keep="last")]


def insitu(station="Condom", depth=0.20):
    ov = {"PROJECT_DIR": REPO, "STATION": station}
    return s7.insitu_daily_depth(depth, ov)


def insitu_rz(station="Condom"):
    d20 = insitu(station, 0.20)["sm"]
    d30 = insitu(station, 0.30)["sm"]
    return pd.concat([d20, d30], axis=1).dropna().mean(axis=1)


def zclim(s, ref=COMMON, min_n=20):
    return s4.clim_anomaly(s, ref, HW, min_n=min_n)["z"]


def veg_obs():
    o = pd.read_csv(os.path.join(DD, "gwl_observations.csv"))
    o = o[o["product"].isin(["S2_10m", "S2SR_2.5m"])]
    w = o.pivot_table(index=["site_id", "product", "time_utc"], columns="variable", values="value").reset_index()
    w["time"] = pd.to_datetime(w["time_utc"]).dt.tz_localize(None)
    return w


def acf1(x):
    x = np.asarray(x, float)
    x = x[np.isfinite(x)]
    x = x - x.mean()
    return float(np.sum(x[1:] * x[:-1]) / np.sum(x * x))


def acf(series: pd.Series, lags):
    s = series.asfreq("D")
    return {k: s.autocorr(k) for k in lags}


def neff_bretherton(x: pd.Series, y: pd.Series, maxlag=200):
    """N_eff = N / (1 + 2 sum rho_x(k) rho_y(k)) (Bretherton et al. 1999, eq. 31) on a daily grid."""
    p = pd.concat([x.rename("x"), y.rename("y")], axis=1).dropna()
    n = len(p)
    xs = x.asfreq("D")
    ys = y.asfreq("D")
    s = 0.0
    for k in range(1, maxlag + 1):
        rx, ry = xs.autocorr(k), ys.autocorr(k)
        if not (np.isfinite(rx) and np.isfinite(ry)):
            break
        if rx * ry < 0.0:   # truncate at first non-positive product
            break
        s += rx * ry
    return n, n / (1 + 2 * s)


def fisher_ci(r, n_eff, alpha=0.05):
    from scipy import stats
    z = np.arctanh(r)
    se = 1 / np.sqrt(max(n_eff - 3, 1))
    q = stats.norm.ppf(1 - alpha / 2)
    return float(np.tanh(z - q * se)), float(np.tanh(z + q * se))
