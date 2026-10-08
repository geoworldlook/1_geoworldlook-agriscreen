"""C1b - leave-one-year-out selection of the ERA5-Land layer (selection among 5 candidates is itself a fit).
For each held-out year: pick the layer with max R on the 8 training years (predictor clim from training years),
score the held-out year. Compared with v1.0 RZ (same LOYO climatology) on identical days."""
import pandas as pd
from common import COMMON, OUT, YEARS, era5_full, era5_layers, ismn_ref, pair, r_ci, diff_r_ci, zclim, zclim_years
e = era5_full().loc[COMMON[0]:COMMON[1]]; lay = era5_layers(e); z_ins = zclim(ismn_ref())
cands = ["RZ_0_100", "L1_0_7", "L2_7_28", "W_0_28", "M_20_30"]
sel, base, picks = [], [], {}
for yv in YEARS:
    tr = [y for y in YEARS if y != yv]
    zs = {k: zclim_years(lay[k], tr) for k in cands}
    sc = {k: (lambda p: p[p.index.year.isin(tr)].corr().iloc[0, 1])(pair(zs[k], z_ins)) for k in cands}
    best = max(sc, key=sc.get); picks[yv] = best
    sel.append(zs[best][zs[best].index.year == yv]); base.append(zs["RZ_0_100"][zs["RZ_0_100"].index.year == yv])
sel, base = pd.concat(sel), pd.concat(base)
print("picked:", picks)
print("LOYO-selected layer R:", [round(v, 3) for v in r_ci(sel, z_ins)])
print("RZ (LOYO clim) R:     ", [round(v, 3) for v in r_ci(base, z_ins)])
d = diff_r_ci(sel, base, z_ins); print("dR:", [round(v, 3) for v in d])
pd.DataFrame({"picked": picks}).to_csv(f"{OUT}/c1b_layer_loyo_picks.csv")
