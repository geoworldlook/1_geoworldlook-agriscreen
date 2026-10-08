import os, sys, warnings, logging
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v0_base import load_obs, scene_z, R, VD, circ
from v2_v6robust import paired
y = pd.read_csv(os.path.join(VD, "ismn_rz.csv"), index_col=0, parse_dates=True)
yz, yraw = y["ismn_rz_z"], y["ismn_rz"]
w = load_obs()
g = w[(w.site_id == "VINEYARD_06") & (w["product"] == "S2SR_2.5m")]
b0 = scene_z(g, "ndvi")
days = b0.to_frame("x").join(yz.rename("y")).dropna().index
b0 = b0[b0.index.isin(days)]

def scene_z2(g, col, hw_mu=15, hw_sd=15, min_ref=5):
    d = g[(g.clear_frac >= 0.9) & g[col].notna()].sort_values("time")
    doy, yr, v = d.time.dt.dayofyear.to_numpy(), d.time.dt.year.to_numpy(), d[col].to_numpy(float)
    z = np.full(len(d), np.nan)
    for i in range(len(d)):
        o = yr != yr[i]
        pm, ps = v[o & (circ(doy, doy[i]) <= hw_mu)], v[o & (circ(doy, doy[i]) <= hw_sd)]
        if len(pm) >= min_ref and len(ps) >= min_ref:
            z[i] = (v[i] - pm.mean()) / ps.std(ddof=1)
    s = pd.Series(z, index=d.time.dt.floor("D").to_numpy()).dropna()
    return s.groupby(level=0).mean()

print("Simple boxcar window variants vs B0 (year-block paired dR):")
for hm, hs in ((15, 30), (15, 45), (30, 30), (20, 20), (10, 10), (10, 30)):
    v = scene_z2(g, "ndvi", hm, hs); v = v[v.index.isin(days)]
    d, lo, hi, n = paired(v, b0, yz, "year")
    print(f"  mean +-{hm} d, SD +-{hs} d: dR={d:+.3f} [{lo:+.3f},{hi:+.3f}] n={n}")

# V1b dropped dates
ser = pd.read_csv(os.path.join(VD, "..", "exp_veg", "a2_variant_series.csv"), index_col=0, parse_dates=True)
v1b = ser["V1b_ndvi_whittaker_RT"].dropna()
dropped = days.difference(v1b.index)
print("V1b dropped dates:", [str(d.date()) for d in dropped])
keep = days.difference(dropped)
print("B0 R on all 245: %.3f; on the 230 kept: %.3f; on dropped 15: %.3f" % (
    R(b0, yz.reindex(days)), R(b0.reindex(keep), yz.reindex(keep)), R(b0.reindex(dropped), yz.reindex(dropped))))
p = b0.to_frame("x").join(yz.rename("y"))
print(p.loc[dropped].round(2).T.to_string())
# R of B0 excluding April
na = p[p.index.month != 4]
print("B0 excluding April: R=%.3f n=%d; excluding Apr+May: R=%.3f n=%d; Apr only R=%.3f n=%d" % (
    R(na.x, na.y), len(na), R(p[p.index.month >= 6].x, p[p.index.month >= 6].y), (p.index.month >= 6).sum(),
    R(p[p.index.month == 4].x, p[p.index.month == 4].y), (p.index.month == 4).sum()))
print("B0 R by month:", {m: (round(R(q.x, q.y), 2), len(q)) for m, q in p.groupby(p.index.month)})

# Floor effect check
a = yraw[(yraw.index.month == 8)]
print("ISMN 20-30 cm raw, August: mean %.3f sd(all days) %.3f; min per year:" % (a.mean(), a.std()), a.groupby(a.index.year).min().round(3).to_dict())
print("August mean per year:", a.groupby(a.index.year).mean().round(3).to_dict())
z22 = yz["2022-06-01":"2022-09-30"]
print("2022 ISMN z by month VI-IX:", z22.groupby(z22.index.month).agg(['mean', 'min']).round(2).to_dict())
for yv in range(2016, 2025):
    zz = yz[f"{yv}-07-01":f"{yv}-09-15"]
    print(yv, "Jul-midSep ISMN z min %.2f mean %.2f raw min %.3f" % (zz.min(), zz.mean(), yraw[f"{yv}-07-01":f"{yv}-09-15"].min()))
