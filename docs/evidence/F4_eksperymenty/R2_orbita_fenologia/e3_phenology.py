"""E3: phenology-aware anomaly baselines vs the current DOY+-15 other-years z-score.

Variants (all leave-one-year-out, i.e. reference = other years only):
  doy15      current: single scene vs other-year scenes within +-15 DOY
  gdd15      same, but time axis = thermal-time-equivalent DOY (GDD base 10 C from 1 Jan, ERA5-Land t2m)
  harm       per-parcel harmonic baseline (2 harmonics) fitted on other years; z = resid / sd(train resid)
  whit       Whittaker-smoothed yearly curve (lambda chosen fixed), anomaly vs other years' smoothed curves at same DOY,
             sampled at scene dates (NON-causal smoothing)
  trail30    trailing 30-day mean of clear-scene values, then z vs other years (causal; = proposal Z3 without C2)
  incr       seasonal increment: value - median(value, 1-30 April same year), then doy15 z (own-trajectory baseline)
Evaluated vs ISMN 20-30 cm clim z (same days, paired across variants), full season and VI-IX, plus partial r | ERA5.
"""
import numpy as np
import pandas as pd

from common import CFG_VEG, era5, era5_rz_z, insitu_z, obs_wide, partial_r_ci, r_ci, s4

w = obs_wide()
ins = insitu_z()
erz = era5_rz_z()
e = era5()

# thermal time
gdd_daily = (e["t2m_c"] - 10).clip(lower=0)
gdd = gdd_daily.groupby(e.index.year).cumsum()
clim = gdd.loc["1991":"2020"]
clim_curve = clim.groupby(clim.index.dayofyear).mean().loc[1:365]


def eq_doy(t):
    g = gdd.reindex([t.normalize()]).iloc[0]
    if np.isnan(g):
        return np.nan
    return float(np.interp(g, clim_curve.to_numpy(), clim_curve.index.to_numpy()))


def circ(a, b):
    d = np.abs(a - b)
    return np.minimum(d, 366 - d)


def z_pool(key, yr, v, hw=15, min_ref=5):
    mu, sd = np.full(len(v), np.nan), np.full(len(v), np.nan)
    for i in range(len(v)):
        m = (yr != yr[i]) & (circ(key, key[i]) <= hw) & np.isfinite(v)
        if m.sum() >= min_ref:
            mu[i], sd[i] = v[m].mean(), v[m].std(ddof=1)
    return (v - mu) / sd


def harm_z(t, yr, v):
    doy = t.dt.dayofyear.to_numpy()
    om = 2 * np.pi * doy / 365.25
    X = np.c_[np.ones(len(v)), np.cos(om), np.sin(om), np.cos(2 * om), np.sin(2 * om)]
    z = np.full(len(v), np.nan)
    for y in np.unique(yr):
        tr, te = yr != y, yr == y
        beta = np.linalg.lstsq(X[tr], v[tr], rcond=None)[0]
        res = v[tr] - X[tr] @ beta
        z[te] = (v[te] - X[te] @ beta) / res.std(ddof=5)
    return z


def whittaker(y, w_, lam):
    n = len(y)
    D = np.diff(np.eye(n), 2, axis=0)
    W = np.diag(w_)
    return np.linalg.solve(W + lam * D.T @ D, w_ * y)


def whit_z(t, yr, v, lam=200.0):
    """Daily Whittaker curve per year on DOY 91..304, anomaly vs other years at same DOY, sampled at scenes."""
    days = np.arange(91, 305)
    curves = {}
    for y in np.unique(yr):
        m = yr == y
        d = t[m].dt.dayofyear.to_numpy()
        yy = np.full(len(days), 0.0)
        ww = np.zeros(len(days))
        for di, vi in zip(d, v[m]):
            k = di - 91
            if 0 <= k < len(days):
                yy[k], ww[k] = vi, 1.0
        if ww.sum() < 8:
            continue
        curves[y] = whittaker(yy, ww, lam)
    z = np.full(len(v), np.nan)
    C = pd.DataFrame(curves, index=days)
    for i in range(len(v)):
        y, d = yr[i], t.iloc[i].dayofyear
        if y not in C or d not in C.index:
            continue
        other = C.loc[d, [c for c in C.columns if c != y]]
        if len(other) >= 4:
            z[i] = (C.loc[d, y] - other.mean()) / other.std(ddof=1)
    return z


def trailing(t, v, days=30):
    s = pd.Series(v, index=t.to_numpy())
    out = np.full(len(v), np.nan)
    for i, ti in enumerate(t):
        m = (s.index > ti - pd.Timedelta(days=days)) & (s.index <= ti)
        out[i] = s[m].mean()
    return out


def variants(g, col):
    d = g[(g["clear_frac"] >= 0.9) & g[col].notna()].sort_values("time").reset_index(drop=True)
    t, yr, v = d["time"], d["time"].dt.year.to_numpy(), d[col].to_numpy(float)
    doy = t.dt.dayofyear.to_numpy().astype(float)
    eq = np.array([eq_doy(x) for x in t])
    out = pd.DataFrame({"time": t})
    out["doy15"] = z_pool(doy, yr, v)
    out["gdd15"] = z_pool(eq, yr, v)
    out["harm"] = harm_z(t, yr, v)
    out["whit"] = whit_z(t, yr, v)
    out["trail30"] = z_pool(doy, yr, trailing(t, v, 30))
    apr = pd.Series(v[t.dt.month.to_numpy() == 4], index=yr[t.dt.month.to_numpy() == 4]).groupby(level=0).median()
    base = pd.Series(yr).map(apr).to_numpy()
    out["incr"] = z_pool(doy, yr, v - base)
    out["day"] = t.dt.floor("D")
    return out.groupby("day").mean(numeric_only=True)


if __name__ == "__main__":
    pd.set_option("display.width", 200)
    for site, prod, col in (("VINEYARD_06", "S2SR_2.5m", "ndvi"), ("VINEYARD_06", "S2_10m", "ndvi"),
                            ("VINEYARD_06", "S2SR_2.5m", "ndmi"), ("VINEYARD_06", "S2SR_2.5m", "crswir"),
                            ("VINEYARD_06", "S2_10m", "ndre"),
                            ("SMOSMANIA_Condom_poly", "S2_10m", "ndvi")):
        g = w[(w["site_id"] == site) & (w["product"] == prod)]
        V = variants(g, col)
        sign = -1 if col == "crswir" else 1
        V = V * sign
        common = V.dropna().index.intersection(ins.dropna().index)
        print(f"\n=== {site} {prod} {col} (sign {sign:+d}); paired n={len(common)} ===")
        rows = []
        for name in V.columns:
            for per, months in (("IV-X", range(4, 11)), ("VI-IX", range(6, 10))):
                idx = [d for d in common if d.month in months]
                x = V.loc[idx, name]
                r, lo, hi, n = r_ci(x, ins)
                pr, plo, phi, _ = partial_r_ci(x, ins, erz)
                rows.append({"variant": name, "season": per, "r": r, "lo": lo, "hi": hi, "n": n,
                             "pr|era5": pr, "plo": plo, "phi": phi})
        print(pd.DataFrame(rows).round(3).to_string(index=False))
