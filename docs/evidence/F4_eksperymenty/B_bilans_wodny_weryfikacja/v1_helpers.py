"""Helpers copied from v1_baseline_and_depth.py."""
import numpy as np
import pandas as pd


def own_anom(s, ref, hw=15, min_n=20):
    s = s.dropna().sort_index()
    r = s.loc[ref[0]:ref[1]]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    doy = s.index.dayofyear.to_numpy()
    z = np.full(len(s), np.nan)
    for d in np.unique(doy):
        dist = np.abs(rd - d)
        dist = np.minimum(dist, 366 - dist)
        pool = rv[dist <= hw]
        if len(pool) < min_n:
            continue
        sel = doy == d
        z[sel] = (s.to_numpy(float)[sel] - pool.mean()) / pool.std(ddof=1)
    return pd.Series(z, index=s.index)


def boot_r(x, y, block_days, n=1000, seed=7, moving=False, fn=None):
    p = pd.concat([x.rename("x"), y.rename("y")], axis=1, join="inner").dropna()
    t = p.index
    xv, yv = p["x"].to_numpy(), p["y"].to_numpy()
    rng = np.random.default_rng(seed)
    if not moving:
        blk = ((t - t.min()) / pd.Timedelta(days=block_days)).astype(int).to_numpy()
        ub = np.unique(blk)
        by = {b: np.flatnonzero(blk == b) for b in ub}
        st = []
        for _ in range(n):
            idx = np.concatenate([by[b] for b in rng.choice(ub, len(ub))])
            st.append(np.corrcoef(xv[idx], yv[idx])[0, 1])
    else:  # moving block bootstrap on the row index (days with data)
        L = block_days
        N = len(xv)
        k = int(np.ceil(N / L))
        st = []
        for _ in range(n):
            starts = rng.integers(0, N - L + 1, k)
            idx = np.concatenate([np.arange(s0, s0 + L) for s0 in starts])[:N]
            st.append(np.corrcoef(xv[idx], yv[idx])[0, 1])
    return float(np.corrcoef(xv, yv)[0, 1]), float(np.percentile(st, 2.5)), float(np.percentile(st, 97.5)), len(p)


def boot_dr(xa, xb, y, block_days, n=2000, seed=11):
    p = pd.concat([xa.rename("a"), xb.rename("b"), y.rename("y")], axis=1, join="inner").dropna()
    t = p.index
    a, b, yy = p["a"].to_numpy(), p["b"].to_numpy(), p["y"].to_numpy()
    if block_days == "year":
        blk = t.year.to_numpy()
    else:
        blk = ((t - t.min()) / pd.Timedelta(days=block_days)).astype(int).to_numpy()
    ub = np.unique(blk)
    by = {k: np.flatnonzero(blk == k) for k in ub}
    rng = np.random.default_rng(seed)
    d = []
    for _ in range(n):
        idx = np.concatenate([by[k] for k in rng.choice(ub, len(ub))])
        d.append(np.corrcoef(a[idx], yy[idx])[0, 1] - np.corrcoef(b[idx], yy[idx])[0, 1])
    ra, rb = np.corrcoef(a, yy)[0, 1], np.corrcoef(b, yy)[0, 1]
    return dict(ra=round(ra, 4), rb=round(rb, 4), d=round(ra - rb, 4), lo=round(float(np.percentile(d, 2.5)), 4),
                hi=round(float(np.percentile(d, 97.5)), 4), n=len(p))


