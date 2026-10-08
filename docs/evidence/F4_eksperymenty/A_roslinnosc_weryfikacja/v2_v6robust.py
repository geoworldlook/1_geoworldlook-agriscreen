"""V6 robustness: K harmonics, SD window, year-block paired dR; mean vs SD component."""
import os, sys, warnings, logging
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v0_base import load_obs, scene_z, R, VD, circ
y = pd.read_csv(os.path.join(VD, "ismn_rz.csv"), index_col=0, parse_dates=True)["ismn_rz_z"]
w = load_obs()

def harm(g, idx="ndvi", K=3, sdw=30, mode="full"):
    d = g[(g.clear_frac >= 0.9) & g[idx].notna()].sort_values("time")
    doy = d.time.dt.dayofyear.to_numpy(float); yr = d.time.dt.year.to_numpy(); v = d[idx].to_numpy(float)
    X = np.column_stack([np.ones(len(d))] + [f(2*np.pi*k*doy/365.25) for k in range(1, K+1) for f in (np.cos, np.sin)])
    z = np.full(len(d), np.nan)
    for yv in np.unique(yr):
        tr = yr != yv
        beta = np.linalg.lstsq(X[tr], v[tr], rcond=None)[0]; rt = v[tr] - X[tr] @ beta
        for i in np.flatnonzero(~tr):
            near = np.abs(doy[tr] - doy[i]) <= sdw
            if near.sum() < 10: continue
            if mode == "full":   # harmonic mean, pooled residual SD
                z[i] = (v[i] - X[i] @ beta) / rt[near].std(ddof=1)
            elif mode == "mean_only":  # harmonic mean, boxcar SD (+-15 d raw values)
                n15 = (circ(doy[tr], doy[i]) <= 15)
                if n15.sum() < 5: continue
                z[i] = (v[i] - X[i] @ beta) / v[tr][n15].std(ddof=1)
            elif mode == "sd_only":  # boxcar mean (+-15d), pooled harmonic residual SD
                n15 = (circ(doy[tr], doy[i]) <= 15)
                if n15.sum() < 5: continue
                z[i] = (v[i] - v[tr][n15].mean()) / rt[near].std(ddof=1)
            elif mode == "const_sd":  # harmonic mean, global residual SD
                z[i] = (v[i] - X[i] @ beta) / rt.std(ddof=1)
    s = pd.Series(z, index=d.time.dt.floor("D").to_numpy()).dropna()
    return s.groupby(level=0).mean()

def paired(xa, xb, yy, kind="year", n=2000, seed=42):
    p = xa.to_frame("a").join(xb.rename("b")).join(yy.rename("y")).dropna()
    rng = np.random.default_rng(seed)
    if kind == "year":
        lab = p.index.year.to_numpy()
    else:
        t = pd.Series(p.index); lab = ((t - t.min()) / pd.Timedelta(days=30)).astype(int).to_numpy()
    u = np.unique(lab); by = {k: np.flatnonzero(lab == k) for k in u}; ds = []
    A, B, Y = p.a.to_numpy(), p.b.to_numpy(), p.y.to_numpy()
    for _ in range(n):
        i = np.concatenate([by[k] for k in rng.choice(u, len(u))])
        ds.append(R(A[i], Y[i]) - R(B[i], Y[i]))
    ds = np.asarray(ds)
    return R(A, Y) - R(B, Y), np.percentile(ds, 2.5), np.percentile(ds, 97.5), len(p)

rows = []
for site, prod in (("VINEYARD_06", "S2SR_2.5m"), ("VINEYARD_06", "S2_10m"), ("SMOSMANIA_Condom_poly", "S2SR_2.5m")):
    g = w[(w.site_id == site) & (w["product"] == prod)]
    b0 = scene_z(g, "ndvi")
    days = b0.to_frame("x").join(y.rename("y")).dropna().index
    b0 = b0[b0.index.isin(days)]
    for K in (1, 2, 3, 4, 6):
        for sdw in (15, 30, 45):
            v = harm(g, "ndvi", K, sdw); v = v[v.index.isin(days)]
            d, lo, hi, n = paired(v, b0, y, "year")
            d30, lo30, hi30, _ = paired(v, b0, y, "30d", n=1000)
            rows.append(dict(site=site, prod=prod, K=K, sdw=sdw, mode="full", n=n, dR=d, yr_lo=lo, yr_hi=hi, b30_lo=lo30, b30_hi=hi30))
    for mode in ("mean_only", "sd_only", "const_sd"):
        v = harm(g, "ndvi", 3, 30, mode); v = v[v.index.isin(days)]
        d, lo, hi, n = paired(v, b0, y, "year")
        rows.append(dict(site=site, prod=prod, K=3, sdw=30, mode=mode, n=n, dR=d, yr_lo=lo, yr_hi=hi))
out = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(out.round(3).to_string(index=False))
out.to_csv(os.path.join(VD, "v2_v6robust.csv"), index=False)
