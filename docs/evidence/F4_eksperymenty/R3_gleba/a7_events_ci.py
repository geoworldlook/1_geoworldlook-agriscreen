import warnings; warnings.filterwarnings("ignore")
import os
import pandas as pd, numpy as np
from common import DRIVE, ismn_rz, zclim, era5, COMMON, swi_regular, rootzone, dekad_end
o = pd.read_csv(os.path.join(DRIVE, "gwl_observations.csv"))
o = o[(o.site_id == "SMOSMANIA_Condom") & (o["product"] == "S1_CD_A") & (o.variable == "sm_s1")]
o["time"] = pd.to_datetime(o["time_utc"]).dt.tz_localize(None)
sm = o.set_index("time")["value"].sort_index()
sw = swi_regular(sm, 10); swd = sw.groupby(sw.index.floor("D")).last().asfreq("D").ffill(limit=6)
e = era5(); e_c = e.loc[COMMON[0]:COMMON[1]]
y = zclim(ismn_rz())
X = {"RZ": zclim(rootzone(e_c)), "0-28": zclim((7*e_c.sm_l1+21*e_c.sm_l2)/28), "S1": zclim(swd)}
X["RZ+S1"] = (X["RZ"] + X["S1"]) / 2; X["0-28+S1"] = (X["0-28"] + X["S1"]) / 2
df = pd.DataFrame(X).join(y.rename("y")).dropna()
df["dk"] = dekad_end(pd.Series(df.index)).to_numpy()
g = df.groupby("dk").mean()
def hss(x, yy, thr=-1):
    ob, pr = yy <= thr, x <= thr
    h, m, f, c = (ob & pr).sum(), (ob & ~pr).sum(), (~ob & pr).sum(), (~ob & ~pr).sum()
    return 2 * (h * c - f * m) / ((h + m) * (m + c) + (h + f) * (f + c)), h/(h+m), f/(h+f)
yrs = g.index.year.to_numpy(); uy = np.unique(yrs); rng = np.random.default_rng(0)
base = {k: hss(g[k], g.y) for k in X}
print({k: tuple(np.round(v, 3)) for k, v in base.items()})
diffs = {k: [] for k in X}
for _ in range(2000):
    pick = rng.choice(uy, len(uy)); gg = pd.concat([g[yrs == u] for u in pick])
    b = hss(gg["RZ"], gg.y)[0]
    for k in X: diffs[k].append(hss(gg[k], gg.y)[0] - b)
for k in X:
    print(k, "HSS - HSS(RZ):", round(base[k][0] - base["RZ"][0], 3), "95% CI (year-block bootstrap)", np.round(np.nanpercentile(diffs[k], [2.5, 97.5]), 3))
