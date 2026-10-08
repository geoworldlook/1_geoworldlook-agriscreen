"""E4: does acquisition geometry (relative orbit, proxied by UTC time) bias vineyard anomalies? (row-structure BRDF)"""
import numpy as np, pandas as pd
from common import CFG_VEG, obs_wide, s4, insitu_z, r_ci
w = obs_wide()
w["hhmm"] = w["time"].dt.strftime("%H:%M")
w["tgrp"] = np.where(w["time"].dt.hour * 60 + w["time"].dt.minute < 11 * 60 + 4, "early(~10:5x)", "late(~11:0x)")
print(w[w.site_id == "VINEYARD_06"].groupby(["product", "tgrp"]).size())
print(w[(w.site_id == "VINEYARD_06") & (w["product"] == "S2_10m")]["hhmm"].value_counts().head(10))
for site in ("VINEYARD_06", "SMOSMANIA_Condom_poly"):
    g = w[(w.site_id == site) & (w["product"] == "S2_10m")]
    for idx in ("ndvi", "ndmi"):
        a = s4.scene_anomaly(g, idx, CFG_VEG).dropna(subset=["z"])
        a["tgrp"] = np.where(a["time"].dt.hour * 60 + a["time"].dt.minute < 11 * 60 + 4, "early", "late")
        a["dv"] = a[idx] - a["clim_mean"]
        summ = a[a["time"].dt.month.between(6, 9)].groupby("tgrp").agg(n=("z", "size"), z_mean=("z", "mean"), dv_mean=("dv", "mean"))
        print(site, idx, "VI-IX\n", summ.round(3))
# near-simultaneous pairs (<=3 days) from different groups, VI-IX, vineyard minus grass difference
g = w[(w["product"] == "S2_10m") & (w["clear_frac"] >= 0.9)].pivot_table(index="time", columns="site_id", values="ndvi")
g = g.dropna(subset=["VINEYARD_06", "SMOSMANIA_Condom_poly"])
g["early"] = (g.index.hour * 60 + g.index.minute) < 11 * 60 + 4
g = g[g.index.month.isin([6, 7, 8, 9])]
rows = []
tt = g.index
for i in range(len(tt)):
    for j in range(i + 1, len(tt)):
        if (tt[j] - tt[i]).days > 3: break
        if g["early"].iloc[i] != g["early"].iloc[j]:
            e_, l_ = (i, j) if g["early"].iloc[i] else (j, i)
            rows.append({"t": tt[i], "dvine": g["VINEYARD_06"].iloc[e_] - g["VINEYARD_06"].iloc[l_],
                         "dgrass": g["SMOSMANIA_Condom_poly"].iloc[e_] - g["SMOSMANIA_Condom_poly"].iloc[l_]})
p = pd.DataFrame(rows)
print("pairs <=3 d, early minus late NDVI, VI-IX: n=%d" % len(p))
print(p[["dvine", "dgrass"]].describe().round(4))
from scipy import stats
print("vine: t-test mean!=0 p=%.3g; grass p=%.3g" % (stats.ttest_1samp(p.dvine, 0).pvalue, stats.ttest_1samp(p.dgrass, 0).pvalue))
