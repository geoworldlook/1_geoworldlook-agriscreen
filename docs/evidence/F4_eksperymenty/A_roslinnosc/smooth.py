"""Weighted robust Whittaker smoother (Eilers 2003; Atzberger & Eilers 2011) on a daily seasonal grid,
and anomalies of the smoothed series against other years (same definition as step_04.scene_anomaly)."""
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import spsolve

SEASON = ("04-01", "10-31")


def _D(n, d=2):
    return sparse.diags([1.0, -2.0, 1.0], [0, 1, 2], shape=(n - 2, n)) if d == 2 else None


_DD = {}


def whittaker(y: np.ndarray, w: np.ndarray, lam: float, robust_iter: int = 2) -> np.ndarray:
    """y with NaN where no obs; w >= 0 weights (0 where NaN). Tukey-bisquare robust reweighting."""
    n = len(y)
    if n not in _DD:
        D = _D(n)
        _DD[n] = (D.T @ D).tocsc()
    DD = _DD[n]
    yy = np.where(np.isfinite(y), y, 0.0)
    w0 = np.where(np.isfinite(y), w, 0.0)
    wr = w0.copy()
    z = None
    for it in range(robust_iter + 1):
        W = sparse.diags(wr)
        z = spsolve((W + lam * DD).tocsc(), wr * yy)
        if it == robust_iter:
            break
        m = w0 > 0
        r = (yy - z)[m]
        s = 1.4826 * np.median(np.abs(r - np.median(r)))
        if not np.isfinite(s) or s <= 0:
            break
        u = (yy - z) / (4.685 * s)
        bis = np.where(np.abs(u) < 1, (1 - u ** 2) ** 2, 0.0)
        wr = w0 * bis
    return z


def season_grid(year: int) -> pd.DatetimeIndex:
    return pd.date_range(f"{year}-{SEASON[0]}", f"{year}-{SEASON[1]}", freq="D")


def obs_on_grid(g: pd.DataFrame, col: str, year: int, min_clear: float = 0.5, until=None):
    """Daily vector of observations (mean if 2 scenes/day) and weights = clear_frac."""
    grid = season_grid(year)
    d = g[(g["time"].dt.year == year) & g[col].notna() & (g["clear_frac"] >= min_clear)].copy()
    if until is not None:
        d = d[d["time"] <= until]
    d["day"] = d["time"].dt.floor("D")
    a = d.groupby("day").agg(v=(col, "mean"), w=("clear_frac", "mean"))
    y = a["v"].reindex(grid).to_numpy(float)
    w = a["w"].reindex(grid).fillna(0).to_numpy(float)
    return grid, y, w


def smooth_all(g: pd.DataFrame, col: str, lam: float, min_clear: float = 0.5) -> pd.Series:
    """Smoothed daily series for all seasons with >= 5 observations."""
    parts = []
    for yr in sorted(g["time"].dt.year.unique()):
        grid, y, w = obs_on_grid(g, col, yr, min_clear)
        if (w > 0).sum() < 5:
            continue
        parts.append(pd.Series(whittaker(y, w, lam), index=grid))
    return pd.concat(parts)


def loo_cv_lambda(g: pd.DataFrame, col: str, lams, min_clear: float = 0.5, seed: int = 0) -> pd.DataFrame:
    """Leave-one-observation-out CV (clear scenes >= 0.9 as targets) — uses only S-2 data, not ISMN."""
    rows = []
    for lam in lams:
        err = []
        for yr in sorted(g["time"].dt.year.unique()):
            grid, y, w = obs_on_grid(g, col, yr, min_clear)
            if (w > 0).sum() < 6:
                continue
            idx = np.flatnonzero((w >= 0.9) & np.isfinite(y))
            for i in idx:
                y2, w2 = y.copy(), w.copy()
                y2[i], w2[i] = np.nan, 0.0
                z = whittaker(y2, w2, lam)
                err.append(y[i] - z[i])
        err = np.asarray(err)
        rows.append({"lam": lam, "rmse": float(np.sqrt(np.mean(err ** 2))),
                     "mae": float(np.mean(np.abs(err))), "n": len(err)})
    return pd.DataFrame(rows)


def smooth_anomaly(s: pd.Series, hw: int = 15) -> pd.Series:
    """z of a daily smoothed series vs other years within +-hw days of year (as scene_anomaly, but daily)."""
    doy, yr, v = s.index.dayofyear.to_numpy(), s.index.year.to_numpy(), s.to_numpy(float)
    z = np.full(len(s), np.nan)
    # Precompute per (doy) pools by year to keep it fast
    for d in np.unique(doy):
        near = np.abs(doy - d) <= hw
        for y in np.unique(yr):
            m = near & (yr != y)
            pool = v[m]
            if len(pool) < 30:
                continue
            sel = (doy == d) & (yr == y)
            z[sel] = (v[sel] - pool.mean()) / pool.std(ddof=1)
    return pd.Series(z, index=s.index)


def realtime_smooth_at(g: pd.DataFrame, col: str, lam: float, dates, min_clear: float = 0.5) -> pd.Series:
    """Causal value: for each date t, smoother fitted only on obs of that season up to t; value at t."""
    out = {}
    for t in dates:
        t = pd.Timestamp(t)
        grid, y, w = obs_on_grid(g, col, t.year, min_clear, until=t + pd.Timedelta(hours=23))
        if (w > 0).sum() < 3:
            continue
        k = grid.get_loc(t.floor("D"))
        z = whittaker(y[:k + 1], w[:k + 1], lam) if k + 1 >= 3 else None
        if z is not None:
            out[t.floor("D")] = z[-1]
    return pd.Series(out)


def clim_stats(s: pd.Series, hw: int = 15, min_n: int = 30) -> pd.DataFrame:
    """For each (year, day) of a daily smoothed series: mean/std of other years within +-hw days of year."""
    doy, yr, v = s.index.dayofyear.to_numpy(), s.index.year.to_numpy(), s.to_numpy(float)
    mu, sd = np.full(len(s), np.nan), np.full(len(s), np.nan)
    for d in np.unique(doy):
        near = np.abs(doy - d) <= hw
        for y in np.unique(yr):
            pool = v[near & (yr != y)]
            pool = pool[np.isfinite(pool)]
            if len(pool) < min_n:
                continue
            sel = (doy == d) & (yr == y)
            mu[sel], sd[sel] = pool.mean(), pool.std(ddof=1)
    return pd.DataFrame({"mu": mu, "sd": sd}, index=s.index)
