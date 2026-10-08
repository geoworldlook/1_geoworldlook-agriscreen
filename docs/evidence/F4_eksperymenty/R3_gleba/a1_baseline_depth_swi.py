"""A1: baseline reproduction, depth-matched ERA5 layers, exponential filter on ERA5 L1 and ISMN 5 cm."""
import warnings

import numpy as np
import pandas as pd

from common import COMMON, era5, insitu, ismn_rz, r_ci, zclim, swi_regular, paired_diff_ci, rootzone

warnings.filterwarnings("ignore")
e = era5().loc[COMMON[0]:COMMON[1]]
e_full = era5()
rz_ins = ismn_rz()
z_ins = zclim(rz_ins)

res = []
def add(name, x, y=z_ins):
    r, lo, hi, n = r_ci(x, y)
    res.append((name, round(r, 3), round(lo, 3), round(hi, 3), n))

# Baseline: ERA5 RZ clim anomaly (common period) vs ISMN 20-30
era_rz = rootzone(e)
add("ERA5 RZ 0-100 (baseline)", zclim(era_rz))
# operational clim 1991-2020
z_op = zclim(rootzone(e_full), ref=("1991-01-01", "2020-12-31")).loc[COMMON[0]:COMMON[1]]
add("ERA5 RZ 0-100, clim 1991-2020", z_op)
add("ERA5 L1 0-7", zclim(e["sm_l1"]))
add("ERA5 L2 7-28", zclim(e["sm_l2"]))
add("ERA5 L3 28-100", zclim(e["sm_l3"]))
l12 = (7 * e["sm_l1"] + 21 * e["sm_l2"]) / 28
add("ERA5 0-28 (L1+L2)", zclim(l12))
l030 = (7 * e["sm_l1"] + 21 * e["sm_l2"] + 2 * e["sm_l3"]) / 30
add("ERA5 0-30", zclim(l030))
l1540 = (13 * e["sm_l2"] + 12 * e["sm_l3"]) / 25   # 15-40 cm centred on 20-30
add("ERA5 15-40 (L2/L3)", zclim(l1540))

# in-situ profile 0-30 weighted (5,10,20,30 cm ~ layers 0-7.5, 7.5-15, 15-25, 25-30)
d05 = insitu(0.05)["sm"]; d10 = insitu(0.10)["sm"]; d20 = insitu(0.20)["sm"]; d30 = insitu(0.30)["sm"]
prof = pd.concat([d05, d10, d20, d30], axis=1).dropna()
prof030 = (7.5 * prof.iloc[:, 0] + 7.5 * prof.iloc[:, 1] + 10 * prof.iloc[:, 2] + 5 * prof.iloc[:, 3]) / 30
z_prof = zclim(prof030)
r, lo, hi, n = r_ci(zclim(l030), z_prof); res.append(("ERA5 0-30 vs ISMN profile 0-30", round(r,3), round(lo,3), round(hi,3), n))
r, lo, hi, n = r_ci(zclim(era_rz), z_prof); res.append(("ERA5 RZ vs ISMN profile 0-30", round(r,3), round(lo,3), round(hi,3), n))

# Spearman for baseline
p = pd.concat([zclim(era_rz), z_ins], axis=1).dropna()
print("Spearman baseline", round(p.corr("spearman").iloc[0, 1], 3))

# Exponential filter on ERA5 L1 (full series, then clip)
for T in (2, 5, 10, 15, 20, 30, 40, 60):
    sw = swi_regular(e_full["sm_l1"], T).loc[COMMON[0]:COMMON[1]]
    add(f"SWI(ERA5 L1) T={T}", zclim(sw))
# Exponential filter on ISMN 5 cm (perfect surface input)
for T in (5, 10, 15, 20, 30, 40):
    sw = swi_regular(d05, T)
    add(f"SWI(ISMN 5cm) T={T}", zclim(sw))
add("ISMN 5cm raw", zclim(d05))
add("ISMN 10cm raw", zclim(d10))

df = pd.DataFrame(res, columns=["series", "R", "lo", "hi", "n"])
print(df.to_string(index=False))

# lag analysis baseline
zx = zclim(era_rz)
for lag in (-10, -5, -3, 0, 3, 5, 10):
    pp = pd.concat([zx.shift(lag, freq="D"), z_ins], axis=1).dropna()
    print("lag", lag, round(pp.corr().iloc[0, 1], 3))

print("paired diff ERA5 0-30 - RZ:", [round(v, 3) if isinstance(v, float) else v for v in paired_diff_ci(zclim(l030), zclim(era_rz), z_ins)])
print("paired diff ERA5 L2 - RZ:", [round(v, 3) if isinstance(v, float) else v for v in paired_diff_ci(zclim(e['sm_l2']), zclim(era_rz), z_ins)])
