"""C1 - ERA5-Land layer / depth matching (variant family 1) and anomaly definition (variant family 2).

Physical reasoning
  * Reference sensors sit at 20 and 30 cm. ERA5-Land 0-100 cm is dominated (72 %) by layer 3 (28-100 cm), which
    is slower and smoother than the 20-30 cm soil. Layers that physically contain 20-30 cm (layer 2, 7-28 cm,
    and the top of layer 3) should track the sensors better: L2 alone, thickness-weighted 0-28 cm, and an
    overlap-weighted 20-30 cm column (0.8*L2 + 0.2*L3). No parameter is fitted.
  * Anomaly definition: (i) DOY climatology on the common 2016-2024 period (v1.0 validation),
    (ii) DOY climatology 1991-2020 (what the operational status actually uses), (iii) 35-day moving anomaly
    (QA4SM short-term anomaly; removes the seasonal *and* the slow drought signal).
Outputs: out/c1_layers.csv, out/c1_depth_matrix.csv, out/c1_years.csv
"""
import numpy as np
import pandas as pd

from common import (CLIM_REF, COMMON, OUT, anom35, diff_r_ci, era5_full, era5_layers, insitu, ismn_ref, r_by_year,
                    r_ci, zclim)

e = era5_full()
lay_full = era5_layers(e)
lay = {k: v.loc[COMMON[0]:COMMON[1]] for k, v in lay_full.items()}
rz_ins = ismn_ref()
z_ins = zclim(rz_ins)
a35_ins = anom35(rz_ins)
season = lambda s: s[s.index.month.isin(range(4, 11))]  # noqa: E731

z_val = {k: zclim(v) for k, v in lay.items()}                                             # 2016-2024 base
z_op = {k: zclim(v, ref=CLIM_REF, min_n=30).loc[COMMON[0]:COMMON[1]] for k, v in lay_full.items()}  # 1991-2020
a35 = {k: anom35(v) for k, v in lay.items()}

rows = []
base = z_val["RZ_0_100"]
for k in lay:
    for kind, x, y, b in (("clim_2016_2024", z_val[k], z_ins, base),
                          ("clim_1991_2020", z_op[k], z_ins, base),
                          ("anom35_vs_anom35", a35[k], a35_ins, a35["RZ_0_100"]),
                          ("anom35_vs_climz", a35[k], z_ins, base)):
        r, lo, hi, n = r_ci(x, y)
        d, dlo, dhi, nd, pgt = diff_r_ci(x, b, y)
        rs, slo, shi, ns = r_ci(season(x), season(y))
        rho = pd.concat([x, y], axis=1).dropna().corr("spearman").iloc[0, 1]
        rows.append({"layer": k, "anomaly": kind, "R": r, "ci_lo": lo, "ci_hi": hi, "n": n, "spearman": rho,
                     "dR_vs_base": d, "dR_lo": dlo, "dR_hi": dhi, "P(dR>0)": pgt,
                     "R_IV_X": rs, "R_IV_X_lo": slo, "R_IV_X_hi": shi, "n_IV_X": ns})
res = pd.DataFrame(rows)
res.to_csv(f"{OUT}/c1_layers.csv", index=False)
pd.set_option("display.width", 220)
print(res.round(3).to_string(index=False))

# per-year R for the clim (2016-2024) anomalies: consistency of any gain across years
yr = pd.DataFrame({k: r_by_year(z_val[k], z_ins) for k in lay})
yr["n_days"] = pd.concat([base, z_ins], axis=1).dropna().groupby(lambda t: t.year).size()
yr.to_csv(f"{OUT}/c1_years.csv")
print("\nR per year (clim anomaly 2016-2024 base):\n", yr.round(3).to_string())
for k in lay:
    if k != "RZ_0_100":
        print(f"  {k}: better than RZ in {(yr[k] > yr['RZ_0_100']).sum()}/{yr[k].notna().sum()} years")

# context: ERA5 layer x ISMN depth matrix (clim anomaly 2016-2024)
dep = {f"ismn_{int(d*100)}cm": insitu(d)["sm"] for d in (0.05, 0.10, 0.20, 0.30)}
dep["ismn_20_30cm"] = rz_ins
prof = pd.concat([dep["ismn_5cm"], dep["ismn_10cm"], dep["ismn_20cm"], dep["ismn_30cm"]], axis=1).dropna()
dep["ismn_0_30_weighted"] = (prof.to_numpy() @ np.array([7.5, 7.5, 10, 5]) / 30.0)
dep["ismn_0_30_weighted"] = pd.Series(dep["ismn_0_30_weighted"], index=prof.index)
mat = []
for dn, ds in dep.items():
    zd = zclim(ds)
    for k in lay:
        r, lo, hi, n = r_ci(z_val[k], zd)
        mat.append({"ismn": dn, "layer": k, "R": r, "ci_lo": lo, "ci_hi": hi, "n": n})
mat = pd.DataFrame(mat)
mat.to_csv(f"{OUT}/c1_depth_matrix.csv", index=False)
print("\nDepth matrix R (clim anomaly 2016-2024):\n", mat.pivot(index="ismn", columns="layer", values="R").round(3))
