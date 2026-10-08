"""A2: vegetation anomaly construction choices vs ISMN 20-30 cm anomaly (VINEYARD_06)."""
import numpy as np
import pandas as pd
from scipy import sparse
from scipy.sparse.linalg import spsolve
from common import COMMON, era5, insitu_rz, zclim, s4, veg_obs, neff_bretherton, fisher_ci

CFG = {"VEG_HALF_WINDOW_DAYS": 15, "VEG_MIN_REF": 5, "VEG_MIN_CLEAR_FRAC": 0.9}
w = veg_obs()
w = w[w["time"].dt.month.between(4, 10)]
rz_ins = insitu_rz("Condom")
y_full = zclim(rz_ins)            # same as validate_anomalies (2016-2024 clim)
e = era5()
x_era = zclim(s4.rootzone(e.loc[COMMON[0]:COMMON[1]]))


def r_with(z: pd.Series, ref=y_full, label="", extra=""):
    p = z.to_frame("x").join(ref.rename("y")).dropna()
    if len(p) < 10:
        print(label, "n<10"); return np.nan
    r = p.corr().iloc[0, 1]
    rs = p.corr(method="spearman").iloc[0, 1]
    # year-block bootstrap
    rng = np.random.default_rng(0)
    yrs = p.index.year.to_numpy(); uy = np.unique(yrs); bs = []
    for _ in range(1000):
        pick = rng.choice(uy, len(uy), replace=True)
        idx = np.concatenate([np.flatnonzero(yrs == k) for k in pick])
        bs.append(np.corrcoef(p["x"].to_numpy()[idx], p["y"].to_numpy()[idx])[0, 1])
    lo, hi = np.nanpercentile(bs, [2.5, 97.5])
    print(f"{label:55s} R={r:.3f} rho={rs:.3f} n={len(p):4d} yearCI=[{lo:.2f},{hi:.2f}] {extra}")
    return r


def scene_z(g, col, robust=False, all_years=False, axis="doy", hw=15, gdd=None):
    d = g[(g["clear_frac"] >= 0.9) & g[col].notna()].sort_values("time").copy()
    if axis == "doy":
        t = d["time"].dt.dayofyear.to_numpy().astype(float)
    else:
        t = gdd.reindex(d["time"].dt.floor("D")).to_numpy()
    yr = d["time"].dt.year.to_numpy(); v = d[col].to_numpy(float)
    z = np.full(len(d), np.nan)
    for i in range(len(d)):
        dist = np.abs(t - t[i]) if axis != "doy" else s4._circ_doy_dist(t, t[i])
        m = (dist <= hw) & ((yr != yr[i]) | all_years)
        pool = v[m]
        if len(pool) < 5:
            continue
        if robust:
            med = np.median(pool); mad = 1.4826 * np.median(np.abs(pool - med))
            z[i] = (v[i] - med) / mad if mad > 0 else np.nan
        else:
            z[i] = (v[i] - pool.mean()) / pool.std(ddof=1)
    return pd.Series(z, index=d["time"].dt.floor("D").to_numpy()).groupby(level=0).mean()


def pct_rank(g, col, hw=15):
    d = g[(g["clear_frac"] >= 0.9) & g[col].notna()].sort_values("time").copy()
    t = d["time"].dt.dayofyear.to_numpy(); yr = d["time"].dt.year.to_numpy(); v = d[col].to_numpy(float)
    out = np.full(len(d), np.nan)
    from scipy import stats
    for i in range(len(d)):
        m = (s4._circ_doy_dist(t, t[i]) <= hw) & (yr != yr[i])
        pool = v[m]
        if len(pool) < 5: continue
        # Weibull plotting position -> normal score (standardized percentile, like SPI)
        k = np.sum(pool < v[i]) + 0.5 * np.sum(pool == v[i])
        out[i] = stats.norm.ppf((k + 1) / (len(pool) + 2))
    return pd.Series(out, index=d["time"].dt.floor("D").to_numpy()).groupby(level=0).mean()


def whittaker(y, wts, lam):
    n = len(y)
    D = sparse.diags([1, -2, 1], [0, 1, 2], shape=(n - 2, n))
    W = sparse.diags(wts)
    A = (W + lam * D.T @ D).tocsc()
    return spsolve(A, wts * y)


def smoothed_daily(g, col, lam=50, causal=False):
    """Weighted Whittaker on a daily grid per season (weights = clear_frac, 0 where missing)."""
    d = g[g[col].notna() & (g["clear_frac"] >= 0.5)].copy()
    d["day"] = d["time"].dt.floor("D")
    s = d.groupby("day").agg(v=(col, "mean"), w=("clear_frac", "mean"))
    out = []
    for yy, gy in s.groupby(s.index.year):
        idx = pd.date_range(f"{yy}-04-01", f"{yy}-10-31", freq="D")
        gy = gy.reindex(idx)
        v = gy["v"].fillna(0).to_numpy(); wt = np.where(gy["v"].notna(), gy["w"].fillna(0) ** 2, 0.0)
        if wt.sum() < 3: continue
        if not causal:
            out.append(pd.Series(whittaker(v, wt, lam), index=idx))
        else:
            # near-real-time: value at day t uses only data up to t (end-point estimate)
            vals = np.full(len(idx), np.nan)
            obs_days = np.flatnonzero(wt > 0)
            for k in obs_days:
                if (wt[:k + 1] > 0).sum() < 3: continue
                sm = whittaker(v[:k + 1], wt[:k + 1], lam)
                vals[k] = sm[-1]
            out.append(pd.Series(vals, index=idx))
    return pd.concat(out)


def daily_anom_other_years(s: pd.Series, hw=15, at=None):
    """Anomaly of a daily smoothed series vs other years' same DOY window (mean/std)."""
    s = s.dropna()
    doy = s.index.dayofyear.to_numpy(); yr = s.index.year.to_numpy(); v = s.to_numpy()
    idx = s.index if at is None else at.intersection(s.index)
    z = []
    for t in idx:
        m = (s4._circ_doy_dist(doy, t.dayofyear) <= hw) & (yr != t.year)
        pool = v[m]
        z.append((s.loc[t] - pool.mean()) / pool.std(ddof=1) if len(pool) > 20 else np.nan)
    return pd.Series(z, index=idx)


for prod in ("S2SR_2.5m", "S2_10m"):
    g = w[(w.site_id == "VINEYARD_06") & (w["product"] == prod)]
    print(f"===== {prod} VINEYARD_06 =====")
    base = scene_z(g, "ndvi")
    r_with(base, label="NDVI z (current: other years, mean/sd, +-15 d)")
    if prod == "S2SR_2.5m":
        n, ne = neff_bretherton(base.asfreq("D"), y_full)
        print(f"   N={n}, N_eff(Bretherton, daily grid)~{ne:.1f}")
    r_with(scene_z(g, "ndvi", all_years=True), label="NDVI z, all years incl. own (biased)")
    r_with(scene_z(g, "ndvi", robust=True), label="NDVI robust z (median/MAD)")
    r_with(pct_rank(g, "ndvi"), label="NDVI standardized percentile (Weibull->normal)")
    r_with(scene_z(g, "ndvi", hw=30), label="NDVI z, +-30 d window")
    for idx in ("ndmi", "ndre", "crswir"):
        if idx in g:
            r_with(scene_z(g, idx), label=f"{idx.upper()} z (current)")

    # Same-definition reference: ISMN anomaly vs other years (LOYO) at scene days
    ins = rz_ins.loc["2016":"2024"]
    y_loyo = daily_anom_other_years(ins, at=base.index)
    r_with(base, ref=y_loyo, label="NDVI z vs ISMN z (ISMN also LOYO clim)")

    # Lagged/integrated SM: mean ISMN anomaly over previous 30 / 60 days
    for win in (30, 60):
        y_int = y_full.rolling(win, min_periods=int(win * 0.6)).mean()
        r_with(base, ref=y_int, label=f"NDVI z vs ISMN z mean of prev {win} d")
    r_with(base, ref=x_era, label="NDVI z vs ERA5 RZ z (same day)")

    # GDD-aligned climatology (base 10 C, from 1 Jan) — Tmax not needed
    t = e["t2m_c"]
    gdd = (t - 10).clip(lower=0).groupby(t.index.year).cumsum()
    r_with(scene_z(g, "ndvi", axis="gdd", hw=60, gdd=gdd), label="NDVI z, GDD-aligned (+-60 GDD), other years")

    # Monthly stratification
    p = base.to_frame("x").join(y_full.rename("y")).dropna()
    print("   R by month:", {m: (round(gm.corr().iloc[0, 1], 2), len(gm)) for m, gm in p.groupby(p.index.month)})
    # Variance decomposition: between-season means vs within-season deviations
    sm = p.groupby(p.index.year).mean()
    print(f"   between-year R (seasonal means, n={len(sm)}) = {sm.corr().iloc[0,1]:.3f};",
          f"within-year R (deviations) = {(p - p.groupby(p.index.year).transform('mean')).corr().iloc[0,1]:.3f}")
    for m0, m1, lab in ((6, 9, "VI-IX"), (4, 5, "IV-V")):
        q = p[(p.index.month >= m0) & (p.index.month <= m1)]
        print(f"   {lab}: R={q.corr().iloc[0,1]:.3f}, n={len(q)}")
    # Leave-one-year-out sensitivity
    print("   LOYO R:", {yy: round(p[p.index.year != yy].corr().iloc[0, 1], 3) for yy in sorted(set(p.index.year))})

    # Whittaker smoothing (retrospective vs causal NRT)
    for lam in (20, 100):
        sd = smoothed_daily(g, "ndvi", lam=lam)
        z_ret = daily_anom_other_years(sd, at=base.index)
        r_with(z_ret, label=f"Whittaker lam={lam} retrospective, anomaly at scene days")
        z_ret_all = daily_anom_other_years(sd)
        r_with(z_ret_all, label=f"Whittaker lam={lam} retrospective, ALL days (inflated n!)")
    sdc = smoothed_daily(g, "ndvi", lam=50, causal=True)
    # climatology from retrospective smoothing, value from causal estimate
    sdr = smoothed_daily(g, "ndvi", lam=50)
    zc = []
    for tday in base.index:
        if tday not in sdc.index or not np.isfinite(sdc.loc[tday]):
            zc.append(np.nan); continue
        doy = sdr.index.dayofyear.to_numpy(); yr = sdr.index.year.to_numpy()
        m = (s4._circ_doy_dist(doy, tday.dayofyear) <= 15) & (yr != tday.year)
        pool = sdr.to_numpy()[m]
        zc.append((sdc.loc[tday] - np.nanmean(pool)) / np.nanstd(pool, ddof=1))
    r_with(pd.Series(zc, index=base.index), label="Whittaker lam=50 CAUSAL (NRT, as-operated)")
    # 30-day mean of clear scenes (Z3-like) for reference
    d = g[(g.clear_frac >= 0.9)].set_index("time")["ndvi"].sort_index()
    d.index = d.index.floor("D")
    d = d.groupby(level=0).mean()
    roll = d.rolling("30D").mean()
    gg = pd.DataFrame({"time": roll.index, "ndvi30": roll.to_numpy(), "clear_frac": 1.0})
    r_with(scene_z(gg, "ndvi30"), label="Trailing 30-d mean of clear scenes, z vs other years")
