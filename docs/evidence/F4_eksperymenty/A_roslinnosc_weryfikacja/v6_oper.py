import os, sys, warnings, logging
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); logging.basicConfig(level=logging.WARNING)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from v0_base import load_obs, scene_z, R, VD
y = pd.read_csv(os.path.join(VD, "ismn_rz.csv"), index_col=0, parse_dates=True)["ismn_rz_z"]
w = load_obs(); g = w[(w.site_id == "VINEYARD_06") & (w["product"] == "S2SR_2.5m")]
b0 = scene_z(g, "ndvi"); bp = scene_z(g, "ndvi", past_only=True, min_past_years=2)
p = bp.to_frame("a").join(b0.rename("b")).join(y.rename("y")).dropna()
rng = np.random.default_rng(42); yr = p.index.year.to_numpy(); u = np.unique(yr); by = {k: np.flatnonzero(yr == k) for k in u}; ds = []
for _ in range(2000):
    i = np.concatenate([by[k] for k in rng.choice(u, len(u))]); ds.append(R(p.a.values[i], p.y.values[i]) - R(p.b.values[i], p.y.values[i]))
print("past-only minus LOYO clim: dR=%.3f year-block CI [%.3f, %.3f] n=%d" % (R(p.a, p.y) - R(p.b, p.y), *np.percentile(ds, [2.5, 97.5]), len(p)))
print("fraction of scenes with z<=-1: LOYO %.2f, past-only %.2f" % ((p.b <= -1).mean(), (p.a <= -1).mean()))
# ISMN z autocorrelation (daily, within season)
yd = y.asfreq("D")
for L in (10, 30, 60, 90, 180):
    print("ISMN z autocorr lag %d d: %.2f" % (L, yd.autocorr(L)))
xs = b0.asfreq("D")
print("NDVI z autocorr (scene pairs) lag 30d via interpolation: %.2f" % xs.interpolate(limit=20).autocorr(30))
