"""E0 baseline reproduction + E1 index comparison + E2 grass/inter-row dominance test."""
import numpy as np
import pandas as pd

from common import CFG_VEG, daily_series, era5_rz_z, insitu_z, obs_wide, partial_r_ci, r_ci, s4

w = obs_wide()
ins = insitu_z()
erz = era5_rz_z()
print("ERA5 RZ vs ISMN:", r_ci(erz, ins))

Z = {}
for (site, prod), g in w.groupby(["site_id", "product"]):
    if "ratio" not in g:
        g = g.assign(ratio=g["ndmi"] / g["ndvi"])
    for idx in ("ndvi", "ndmi", "ndre", "crswir", "ratio"):
        if idx not in g or g[idx].isna().all():
            continue
        a = s4.scene_anomaly(g, idx, CFG_VEG)
        a = a.dropna(subset=["z"])
        Z[(site, prod, idx)] = daily_series(a, "z")

print("\nE0/E1: anomaly z vs ISMN 20-30 cm z (all scenes of product), and partial r | ERA5 RZ")
rows = []
for k, z in Z.items():
    r, lo, hi, n = r_ci(z, ins)
    pr, plo, phi, pn = partial_r_ci(z, ins, erz)
    rows.append({"site": k[0], "prod": k[1], "idx": k[2], "r": r, "lo": lo, "hi": hi, "n": n,
                 "pr|era5": pr, "plo": plo, "phi": phi})
print(pd.DataFrame(rows).round(3).to_string())

# E2 grass dominance: vineyard vs station grass plot anomalies on same days
print("\nE2: VINEYARD_06 NDVI z vs grass plot (SMOSMANIA_Condom_poly) NDVI z on same days, by season")
for prod in ("S2SR_2.5m", "S2_10m"):
    v = Z[("VINEYARD_06", prod, "ndvi")]
    gpl = Z[("SMOSMANIA_Condom_poly", prod, "ndvi")]
    p = pd.concat([v.rename("v"), gpl.rename("g"), ins.rename("i"), erz.rename("e")], axis=1).dropna()
    for name, months in (("IV-V", (4, 5)), ("VI-VII", (6, 7)), ("VIII-X", (8, 10)), ("all", (4, 10))):
        q = p[p.index.month.isin(range(months[0], months[1] + 1))]
        if len(q) < 10:
            continue
        print(prod, name, "n", len(q), "r(vine,grass)=%.2f" % np.corrcoef(q.v, q.g)[0, 1],
              "r(vine,ISMN)=%.2f" % np.corrcoef(q.v, q.i)[0, 1], "r(grass,ISMN)=%.2f" % np.corrcoef(q.g, q.i)[0, 1])
    # partial: vine vs ISMN controlling for grass
    pr = partial_r_ci(v, ins, gpl)
    print(prod, "partial r(vine, ISMN | grass) =", np.round(pr, 3))
    pr2 = partial_r_ci(gpl, ins, v)
    print(prod, "partial r(grass, ISMN | vine) =", np.round(pr2, 3))

# raw seasonal NDVI levels: vineyard vs grass by month
print("\nMonthly median raw NDVI (S2_10m, clear>=0.9):")
c = w[(w["product"] == "S2_10m") & (w["clear_frac"] >= 0.9)]
c = c.assign(m=c["time"].dt.month)
print(c.pivot_table(index="m", columns="site_id", values="ndvi", aggfunc="median").round(3))
print(c.pivot_table(index="m", columns="site_id", values="ndmi", aggfunc="median").round(3))
