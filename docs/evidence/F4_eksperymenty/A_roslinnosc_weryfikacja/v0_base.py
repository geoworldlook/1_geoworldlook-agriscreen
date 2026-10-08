"""Independent re-implementation of the v1.0 vegetation validation (no exp_veg helpers).
Uses repo only for ISMN QC (step_07.insitu_daily_depth)."""
import os, sys, logging, warnings
import numpy as np, pandas as pd
logging.basicConfig(level=logging.WARNING); warnings.filterwarnings("ignore")
REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
VD = os.path.join(SCR, "exp_veg_verify")
sys.path.insert(0, REPO)
import step_07_station_pipeline as s7

def circ(a, b):
    d = np.abs(a - b); return np.minimum(d, 366 - d)

def load_obs():
    o = pd.read_csv(os.path.join(SCR, "drive_data/gwl_observations.csv"))
    o = o[o["product"].isin(["S2_10m", "S2SR_2.5m"])]
    w = o.pivot_table(index=["site_id", "product", "time_utc"], columns="variable", values="value").reset_index()
    w["time"] = pd.to_datetime(w["time_utc"]).dt.tz_localize(None)
    w = w[w["time"].dt.month.between(4, 10)]
    return w

def scene_z(g, col, past_only=False, min_ref=5, hw=15, min_past_years=1):
    d = g[(g["clear_frac"] >= 0.9) & g[col].notna()].sort_values("time")
    doy, yr, v = d["time"].dt.dayofyear.to_numpy(), d["time"].dt.year.to_numpy(), d[col].to_numpy(float)
    z = np.full(len(d), np.nan)
    for i in range(len(d)):
        m = (yr < yr[i]) if past_only else (yr != yr[i])
        m = m & (circ(doy, doy[i]) <= hw)
        pool = v[m]
        if past_only and len(np.unique(yr[m])) < min_past_years:
            continue
        if len(pool) >= min_ref:
            z[i] = (v[i] - pool.mean()) / pool.std(ddof=1)
    s = pd.Series(z, index=d["time"].dt.floor("D").to_numpy()).dropna()
    return s.groupby(level=0).mean()

def clim_z(s, ref=("2016-01-01", "2024-12-31"), hw=15, min_n=20):
    s = s.dropna().sort_index(); r = s.loc[ref[0]:ref[1]]
    rd, rv = r.index.dayofyear.to_numpy(), r.to_numpy(float)
    doy = s.index.dayofyear.to_numpy(); z = np.full(len(s), np.nan)
    for d in np.unique(doy):
        pool = rv[circ(rd, d) <= hw]
        if len(pool) < min_n: continue
        z[doy == d] = (s.to_numpy()[doy == d] - pool.mean()) / pool.std(ddof=1)
    return pd.Series(z, index=s.index)

def ismn(depth):
    return s7.insitu_daily_depth(depth, {"PROJECT_DIR": REPO})["sm"]

def block_ci(t, x, y, func, block=30, n=1000, seed=42):
    rng = np.random.default_rng(seed)
    t = pd.Series(pd.DatetimeIndex(t))
    b = ((t - t.min()) / pd.Timedelta(days=block)).astype(int).to_numpy()
    u = np.unique(b); by = {k: np.flatnonzero(b == k) for k in u}; st = []
    for _ in range(n):
        idx = np.concatenate([by[k] for k in rng.choice(u, len(u))])
        st.append(func(x[idx], y[idx]))
    st = np.asarray(st); st = st[np.isfinite(st)]
    return np.percentile(st, 2.5), np.percentile(st, 97.5)

def year_ci(t, x, y, func, n=2000, seed=42):
    rng = np.random.default_rng(seed); yr = pd.DatetimeIndex(t).year.to_numpy(); u = np.unique(yr)
    by = {k: np.flatnonzero(yr == k) for k in u}; st = []
    for _ in range(n):
        idx = np.concatenate([by[k] for k in rng.choice(u, len(u))])
        with np.errstate(all="ignore"): st.append(func(x[idx], y[idx]))
    st = np.asarray(st); st = st[np.isfinite(st)]
    return np.percentile(st, 2.5), np.percentile(st, 97.5)

R = lambda a, b: np.corrcoef(a, b)[0, 1]

if __name__ == "__main__":
    w = load_obs()
    rz = pd.concat([ismn(0.20), ismn(0.30)], axis=1).dropna().mean(axis=1)
    y = clim_z(rz)
    y.to_frame("ismn_rz_z").join(rz.rename("ismn_rz")).to_csv(os.path.join(VD, "ismn_rz.csv"))
    rows = []
    for prod in ("S2SR_2.5m", "S2_10m"):
        g = w[(w.site_id == "VINEYARD_06") & (w["product"] == prod)]
        for idx in ("ndvi", "ndmi", "ndre", "crswir"):
            if idx not in g or g[idx].isna().all(): continue
            z = scene_z(g, idx)
            p = z.to_frame("x").join(y.rename("y")).dropna()
            lo, hi = block_ci(p.index, p.x.to_numpy(), p.y.to_numpy(), R)
            ylo, yhi = year_ci(p.index, p.x.to_numpy(), p.y.to_numpy(), R)
            rows.append(dict(prod=prod, idx=idx, r=R(p.x, p.y), lo=lo, hi=hi, ylo=ylo, yhi=yhi, n=len(p)))
            if prod == "S2SR_2.5m":
                z.to_csv(os.path.join(VD, f"b0_{idx}_sr.csv"))
    print(pd.DataFrame(rows).round(3).to_string(index=False))
