"""E5: orbit-stratified climatology vs pooled (current); also harmonic + orbit offset. Paired dR with block bootstrap."""
import numpy as np, pandas as pd
from common import obs_wide, insitu_z, era5_rz_z, r_ci, partial_r_ci, VCFG, s7
from e3_phenology import z_pool, harm_z, circ

w = obs_wide()
ins = insitu_z(); erz = era5_rz_z()

def harm_orbit_z(t, yr, v, early):
    doy = t.dt.dayofyear.to_numpy(); om = 2*np.pi*doy/365.25
    X = np.c_[np.ones(len(v)), np.cos(om), np.sin(om), np.cos(2*om), np.sin(2*om), early.astype(float)]
    z = np.full(len(v), np.nan)
    for y in np.unique(yr):
        tr, te = yr != y, yr == y
        b = np.linalg.lstsq(X[tr], v[tr], rcond=None)[0]
        res = v[tr] - X[tr] @ b
        z[te] = (v[te] - X[te] @ b) / res.std(ddof=6)
    return z

def build(site, prod, col):
    g = w[(w.site_id == site) & (w["product"] == prod)]
    d = g[(g.clear_frac >= 0.9) & g[col].notna()].sort_values("time").reset_index(drop=True)
    t, yr, v = d.time, d.time.dt.year.to_numpy(), d[col].to_numpy(float)
    doy = t.dt.dayofyear.to_numpy().astype(float)
    early = ((t.dt.hour*60 + t.dt.minute) < 11*60+4).to_numpy()
    out = pd.DataFrame({"time": t, "early": early})
    out["pooled"] = z_pool(doy, yr, v)
    zs = np.full(len(v), np.nan)
    for e_ in (True, False):
        m = early == e_
        zs[m] = z_pool(doy[m], yr[m], v[m], min_ref=4)
    out["orbit_strat"] = zs
    out["harm"] = harm_z(t, yr, v)
    out["harm_orbit"] = harm_orbit_z(t, yr, v, early)
    out["day"] = t.dt.floor("D")
    return out.groupby("day").mean(numeric_only=True)

def dr_ci(a, b, y):
    p = pd.concat([a.rename("a"), b.rename("b"), y.rename("y")], axis=1).dropna()
    ii = np.arange(len(p)).astype(float)
    def f(idx, _):
        q = p.iloc[idx.astype(int)]
        return np.corrcoef(q.a, q.y)[0,1] - np.corrcoef(q.b, q.y)[0,1]
    d = f(ii, None)
    lo, hi = s7._block_bootstrap_ci(pd.Series(p.index), ii, ii, f, VCFG)
    return d, lo, hi, len(p)

if __name__ == "__main__":
    for site, prod, col, sign in (("VINEYARD_06","S2SR_2.5m","ndvi",1), ("VINEYARD_06","S2_10m","ndvi",1),
                                  ("VINEYARD_06","S2SR_2.5m","ndmi",1), ("VINEYARD_06","S2SR_2.5m","crswir",-1)):
        V = build(site, prod, col)
        V[["pooled","orbit_strat","harm","harm_orbit"]] *= sign
        print(f"\n=== {site} {prod} {col} ===")
        print("mean z by orbit group (VI-IX):")
        s = V[V.index.month.isin([6,7,8,9])]
        print(s.groupby("early")[["pooled","orbit_strat","harm_orbit"]].mean().round(3))
        for per, months in (("IV-X", range(4,11)), ("VI-IX", range(6,10))):
            Vs = V[V.index.month.isin(months)]
            for name in ("pooled","orbit_strat","harm","harm_orbit"):
                r, lo, hi, n = r_ci(Vs[name], ins)
                pr = partial_r_ci(Vs[name], ins, erz)
                print(f"{per:6s} {name:12s} r={r:.3f} [{lo:.3f},{hi:.3f}] n={n}  partial|ERA5={pr[0]:.3f} [{pr[1]:.3f},{pr[2]:.3f}]")
            for name in ("orbit_strat","harm","harm_orbit"):
                d, lo, hi, n = dr_ci(Vs[name], Vs["pooled"], ins)
                print(f"{per:6s} dR({name}-pooled) = {d:+.3f} [{lo:+.3f},{hi:+.3f}] n={n}")
        # alerts-like counts: z<=-1 by orbit
        for name in ("pooled","orbit_strat","harm_orbit"):
            c = s[s[name] <= -1].groupby("early").size()
            print(name, "VI-IX scenes with z<=-1 by orbit (early True/False):", c.to_dict())
