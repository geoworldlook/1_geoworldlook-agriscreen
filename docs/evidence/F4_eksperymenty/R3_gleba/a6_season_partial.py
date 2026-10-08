import warnings; warnings.filterwarnings("ignore")
import os
import pandas as pd, numpy as np
from common import DRIVE, ismn_rz, zclim, era5, COMMON, r_ci, swi_regular, rootzone, dekad_end
o = pd.read_csv(os.path.join(DRIVE, "gwl_observations.csv"))
o = o[(o.site_id == "SMOSMANIA_Condom") & (o["product"] == "S1_CD_A") & (o.variable == "sm_s1")]
o["time"] = pd.to_datetime(o["time_utc"]).dt.tz_localize(None)
sm = o.set_index("time")["value"].sort_index()
sw = swi_regular(sm, 10); swd = sw.groupby(sw.index.floor("D")).last().asfreq("D").ffill(limit=6)
e = era5(); e_c = e.loc[COMMON[0]:COMMON[1]]
rz = ismn_rz(); y = zclim(rz)
X = {"ERA5 RZ": zclim(rootzone(e_c)), "ERA5 0-28": zclim((7*e_c.sm_l1+21*e_c.sm_l2)/28), "SWI S1 T10": zclim(swd)}
X["mean(0-28,S1)"] = (X["ERA5 0-28"] + X["SWI S1 T10"]) / 2
X["mean(RZ,S1)"] = (X["ERA5 RZ"] + X["SWI S1 T10"]) / 2
for lab, months in (("IV-X", range(4, 11)), ("VI-IX", range(6, 10)), ("XI-III", [11, 12, 1, 2, 3])):
    print(lab, {k: tuple(np.round(r_ci(v[v.index.month.isin(list(months))], y)[:3], 3)) for k, v in X.items()})
# partial correlation S1 | ERA5 0-28
d = pd.concat([X["SWI S1 T10"].rename("s"), X["ERA5 0-28"].rename("e"), y.rename("y")], axis=1).dropna()
def resid(a, b):
    c = np.polyfit(b, a, 1); return a - np.polyval(c, b)
print("partial r(S1,y | ERA5 0-28) =", round(np.corrcoef(resid(d.s, d.e), resid(d.y, d.e))[0, 1], 3))
d2 = pd.concat([X["SWI S1 T10"].rename("s"), X["ERA5 RZ"].rename("e"), y.rename("y")], axis=1).dropna()
print("partial r(S1,y | ERA5 RZ) =", round(np.corrcoef(resid(d2.s, d2.e), resid(d2.y, d2.e))[0, 1], 3))
# operational POD/FAR reproduction (1991-2020 clim for product, 2016-2024 for ISMN)
z_op = zclim(rootzone(e), ref=("1991-01-01", "2020-12-31")).loc[COMMON[0]:COMMON[1]]
z_op028 = zclim((7*e.sm_l1+21*e.sm_l2)/28, ref=("1991-01-01", "2020-12-31")).loc[COMMON[0]:COMMON[1]]
def events(x, thr=-1.0):
    dk = pd.DataFrame({"x": x, "y": y}).dropna()
    dk["dk"] = dekad_end(pd.Series(dk.index)).to_numpy()
    g = dk.groupby("dk").mean()
    ob, pr = g.y <= thr, g.x <= thr
    h, m, f, cn = (ob & pr).sum(), (ob & ~pr).sum(), (~ob & pr).sum(), (~ob & ~pr).sum()
    hss = 2 * (h * cn - f * m) / ((h + m) * (m + cn) + (h + f) * (f + cn))
    return dict(POD=round(h/(h+m), 3), FAR=round(f/(h+f), 3), HSS=round(hss, 3), n=len(g), obs=int(ob.sum()), pred=int(pr.sum()))
print("op RZ 1991-2020:", events(z_op))
print("op 0-28 1991-2020:", events(z_op028))
