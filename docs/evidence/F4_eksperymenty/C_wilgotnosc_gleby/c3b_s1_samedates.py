"""C3b - single S-1 retrievals vs ERA5-Land on identical days (S-1 acquisition days only)."""
import pandas as pd
from common import COMMON, OUT, era5_full, era5_layers, insitu, ismn_ref, pair, r_ci, s1_obs, zclim, anom35, diff_r_ci
s1 = s1_obs("sm_s1"); s1d = s1.groupby(s1.index.floor("D")).mean()
e = era5_full().loc[COMMON[0]:COMMON[1]]; lay = era5_layers(e); rz = ismn_ref(); d05 = insitu(0.05)["sm"]
rows = []
# clim z vs 20-30 cm on S-1 days
zs, zr, zl2, zi = zclim(s1d), zclim(lay["RZ_0_100"]), zclim(lay["L2_7_28"]), zclim(rz)
p = pair(zs, zr, zl2, zi, names=["s1", "rz", "l2", "y"])
for c in ("s1", "rz", "l2"):
    rows.append({"x": c, "target": "ISMN 20-30 clim z", "days": "S-1 days", **dict(zip(["R", "lo", "hi", "n"], r_ci(p[c], p["y"])))})
d = diff_r_ci(p["s1"], p["rz"], p["y"]); print("dR S1 clim z - ERA5 RZ (S1 days):", [round(v, 3) for v in d])
# 35-day anomalies vs 5 cm on S-1 days (S-1 anomaly from the irregular series as in step_07)
a = pair(anom35(s1d), anom35(lay["L1_0_7"]), anom35(d05), names=["s1", "l1", "y"])
for c in ("s1", "l1"):
    rows.append({"x": c, "target": "ISMN 5 cm anom35", "days": "S-1 days w/ anomaly", **dict(zip(["R", "lo", "hi", "n"], r_ci(a[c], a["y"])))})
df = pd.DataFrame(rows); print(df.round(3).to_string(index=False)); df.to_csv(f"{OUT}/c3b_s1_samedates.csv", index=False)
