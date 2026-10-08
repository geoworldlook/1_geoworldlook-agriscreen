"""Trend / causality checks on B0 (NDVI SR, VINEYARD_06)."""
import os, sys, warnings, logging
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); logging.basicConfig(level=logging.WARNING)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from v0_base import load_obs, scene_z, block_ci, year_ci, R, VD
y = pd.read_csv(os.path.join(VD, "ismn_rz.csv"), index_col=0, parse_dates=True)
yz, yraw = y["ismn_rz_z"], y["ismn_rz"]
w = load_obs()
g = w[(w.site_id == "VINEYARD_06") & (w["product"] == "S2SR_2.5m")]
gc = g[g.clear_frac >= 0.9]

# 1. raw NDVI per year, by month
t = gc.assign(yr=gc.time.dt.year, mo=gc.time.dt.month)
print("Raw NDVI SR VINEYARD_06 mean by year x month (clear>=0.9):")
print(t.pivot_table(index="yr", columns="mo", values="ndvi", aggfunc="mean").round(2).to_string())
# ISMN yearly mean z (Apr-Oct) and raw
yy = yz[(yz.index.month >= 4) & (yz.index.month <= 10)]
print("ISMN 20-30 z mean IV-X by year:", yy.groupby(yy.index.year).mean().round(2).to_dict())

b0 = scene_z(g, "ndvi")
p = b0.to_frame("x").join(yz.rename("y")).dropna()
print("B0 R", round(R(p.x, p.y), 3), "n", len(p))
m = p.groupby(p.index.year).mean()
print("yearly means x,y:\n", m.round(2).T.to_string())
yrs = m.index.to_numpy(float)
print("corr(year, mean veg z)=%.2f  corr(year, mean ISMN z)=%.2f  corr(means)=%.2f" %
      (R(yrs, m.x), R(yrs, m.y), R(m.x, m.y)))
# partial between-year after linear time trend
def resid(a, b):
    A = np.c_[np.ones(len(b)), b]; return a - A @ np.linalg.lstsq(A, a, rcond=None)[0]
print("between-year corr after removing linear year trend from both: %.2f" % R(resid(m.x.to_numpy(), yrs), resid(m.y.to_numpy(), yrs)))

# 2. detrended scene z: remove linear trend in year from raw NDVI before anomaly (LOYO trend fit)
# Simple: regress B0 z on year (LOYO) and take residual
pp = p.copy(); pp["yr"] = pp.index.year
res = []
for yv in pp.yr.unique():
    tr = pp[pp.yr != yv]; beta = np.polyfit(tr.yr, tr.x, 1)
    res.append(pp[pp.yr == yv].x - np.polyval(beta, yv))
pp["x_dt"] = pd.concat(res)
print("R of LOYO-detrended veg z vs ISMN z: %.3f" % R(pp.x_dt, pp.y), "CI30", np.round(block_ci(pp.index, pp.x_dt.to_numpy(), pp.y.to_numpy(), R), 3),
      "CIyear", np.round(year_ci(pp.index, pp.x_dt.to_numpy(), pp.y.to_numpy(), R), 3))

# 3. operational (past-years-only) climatology
for mpy in (1, 2, 3):
    bp = scene_z(g, "ndvi", past_only=True, min_past_years=mpy)
    q = bp.to_frame("x").join(yz.rename("y")).dropna()
    q2 = q.join(b0.rename("b0")).dropna()
    print(f"past-only clim (>= {mpy} past yrs): R={R(q.x, q.y):.3f} n={len(q)} years={sorted(set(q.index.year))}; "
          f"B0 on same days R={R(q2.b0, q2.y):.3f}; mean past-only z by year:",
          q.groupby(q.index.year).x.mean().round(2).to_dict())

# 4. jackknife leave-one-year-out R for B0
jk = {yv: round(R(p[p.index.year != yv].x, p[p.index.year != yv].y), 3) for yv in sorted(set(p.index.year))}
print("B0 R leaving out one year:", jk)
print("n per year:", p.groupby(p.index.year).size().to_dict())
