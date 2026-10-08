"""Builders of the pre-registered vegetation-signal variants (VINEYARD_06 unless noted).

Every builder returns a pd.Series of z-like values indexed by day (one value per S-2 scene day).
Nothing here uses ISMN: parameters are either fixed a priori or fitted on S-2 data of OTHER years (LOYO).
"""
import numpy as np
import pandas as pd

from common import group, scene_z
from smooth import smooth_all, clim_stats, realtime_smooth_at

LAM = {"VINEYARD_06": 1000.0, "SMOSMANIA_Condom_poly": 300.0, "SMOSMANIA_Condom": 300.0}  # a1_lambda_cv
SIGN = {"ndvi": 1, "ndmi": 1, "ndre": 1, "crswir": -1}   # +: higher = wetter / greener


def daily(z: pd.Series) -> pd.Series:
    z = z.dropna()
    return z.groupby(z.index.floor("D")).mean()


def b0(site="VINEYARD_06", prod="S2SR_2.5m", idx="ndvi") -> pd.Series:
    return daily(SIGN[idx] * scene_z(group(site, prod), idx))


def whit(site="VINEYARD_06", prod="S2SR_2.5m", idx="ndvi", realtime=False, dates=None) -> pd.Series:
    """Whittaker-smoothed index -> z vs other years' smoothed curves (+-15 d); sampled on scene days."""
    g = group(site, prod)
    lam = LAM[site]
    s = smooth_all(g, idx, lam)
    cs = clim_stats(s, 15)
    if dates is None:
        dates = b0(site, prod, "ndvi").index
    if realtime:
        v = realtime_smooth_at(g, idx, lam, dates)
    else:
        v = s.reindex(pd.DatetimeIndex(dates))
    v = v.dropna()
    c = cs.reindex(v.index)
    return SIGN[idx] * ((v - c["mu"]) / c["sd"]).dropna()


def trailing_mean(z: pd.Series, days=30) -> pd.Series:
    """Causal mean of scene anomalies in (t - days, t] (F3 proposal Z3)."""
    z = daily(z)
    out = {t: z[(z.index > t - pd.Timedelta(days=days)) & (z.index <= t)].mean() for t in z.index}
    return pd.Series(out)


def mean_z(series: list) -> pd.Series:
    """Equal-weight mean of sign-aligned z-scores (only days where all are available)."""
    df = pd.concat(series, axis=1).dropna()
    return df.mean(axis=1)


def pc1_loyo(series: dict) -> pd.Series:
    """First principal component of sign-aligned z (NDVI, NDMI, NDRE, -CRSWIR), loadings fitted on other years."""
    df = pd.concat(series, axis=1).dropna()
    out = []
    for y in np.unique(df.index.year):
        tr, te = df[df.index.year != y], df[df.index.year == y]
        mu, sd = tr.mean(), tr.std(ddof=1)
        X = ((tr - mu) / sd).to_numpy()
        _, _, vt = np.linalg.svd(X, full_matrices=False)
        w = vt[0] * np.sign(vt[0][0])          # sign: positive NDVI loading
        sc_tr = X @ w
        sc = (((te - mu) / sd).to_numpy() @ w) / sc_tr.std(ddof=1)
        out.append(pd.Series(sc, index=te.index))
    return pd.concat(out).sort_index()


def contrast(site_a="VINEYARD_06", site_b="SMOSMANIA_Condom_poly", prod="S2SR_2.5m", idx="ndvi") -> pd.Series:
    """Vine minus grass-plot anomaly on the same scene (removes common-mode scene effects and grass drying)."""
    a, b = b0(site_a, prod, idx), b0(site_b, prod, idx)
    j = pd.concat([a.rename("a"), b.rename("b")], axis=1).dropna()
    return j["a"] - j["b"]


def harmonic_loyo(site="VINEYARD_06", prod="S2SR_2.5m", idx="ndvi", K=3, sd_window=30) -> pd.Series:
    """Phenology-relative anomaly: residual from a K-harmonic seasonal curve fitted on OTHER years,
    divided by the residual SD of other years within +-sd_window days of year (pooled, more stable
    than the +-15 d / >=5 scenes boxcar of v1.0)."""
    g = group(site, prod)
    d = g[(g["clear_frac"] >= 0.9) & g[idx].notna()].copy()
    doy = d["time"].dt.dayofyear.to_numpy(float)
    X = np.column_stack([np.ones(len(d))] + [f(2 * np.pi * k * doy / 365.25) for k in range(1, K + 1)
                                             for f in (np.cos, np.sin)])
    v, yr = d[idx].to_numpy(float), d["time"].dt.year.to_numpy()
    z = np.full(len(d), np.nan)
    for y in np.unique(yr):
        tr = yr != y
        beta = np.linalg.lstsq(X[tr], v[tr], rcond=None)[0]
        res_tr = v[tr] - X[tr] @ beta
        for i in np.flatnonzero(~tr):
            dd = np.abs(doy[tr] - doy[i])
            pool = res_tr[dd <= sd_window]
            if len(pool) >= 10:
                z[i] = (v[i] - X[i] @ beta) / pool.std(ddof=1)
    return SIGN[idx] * daily(pd.Series(z, index=pd.DatetimeIndex(d["time"])))


def decline(site="VINEYARD_06", prod="S2SR_2.5m", idx="ndvi", start="06-01") -> pd.Series:
    """Within-season decline: smoothed value minus the running maximum since 1 June of the same year,
    standardised vs other years (+-15 d). Removes year-specific vigour offsets (pruning, inter-row cover)."""
    g = group(site, prod)
    s = smooth_all(g, idx, LAM[site]) * SIGN[idx]
    parts = []
    for y in np.unique(s.index.year):
        q = s[(s.index.year == y) & (s.index >= pd.Timestamp(f"{y}-{start}"))]
        parts.append(q - q.cummax())
    dec = pd.concat(parts)
    cs = clim_stats(dec, 15)
    zz = ((dec - cs["mu"]) / cs["sd"])
    days = b0(site, prod, "ndvi").index
    return zz.reindex(days).dropna()
