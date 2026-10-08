"""C7 - diagnostic: dry-end 'floor' of the 20-30 cm reference in late summer (limits event validation in VIII-IX)."""
import numpy as np, pandas as pd
from common import OUT, ismn_ref, era5_full, era5_layers, COMMON, zclim
rz = ismn_ref(); e = era5_full().loc[COMMON[0]:COMMON[1]]; lay = era5_layers(e)
q02 = rz.quantile(0.02)
mm = rz.groupby([rz.index.year, rz.index.month]).mean().unstack()
tab = pd.DataFrame({"ismn_monthly_mean_interannual_sd": mm.std(), "ismn_monthly_mean_avg": mm.mean(),
    "share_days_within_0.02_of_p2": (rz <= q02 + 0.02).groupby(rz.index.month).mean(),
    "ismn_z_sd": zclim(rz).groupby(rz.index.month).std(),
    "era5_rz_interannual_sd": lay["RZ_0_100"].groupby([e.index.year, e.index.month]).mean().unstack().std(),
    "era5_l2_interannual_sd": lay["L2_7_28"].groupby([e.index.year, e.index.month]).mean().unstack().std()})
print(f"ISMN 20-30 cm p2 = {q02:.3f}"); print(tab.round(3).to_string())
tab.to_csv(f"{OUT}/c7_floor.csv")
print("\n2017 dekadal z (ISMN vs ERA5 RZ/L2, 1991-2020 base):")
from common import to_dekad, CLIM_REF
lf = era5_layers(era5_full())
d = pd.DataFrame({"ismn": to_dekad(zclim(rz)), "rz_op": to_dekad(zclim(lf["RZ_0_100"], CLIM_REF, min_n=30).loc["2016":"2024"]),
                  "l2_op": to_dekad(zclim(lf["L2_7_28"], CLIM_REF, min_n=30).loc["2016":"2024"]),
                  "l3_op": to_dekad(zclim(lf["L3_28_100"], CLIM_REF, min_n=30).loc["2016":"2024"])})
print(d.loc["2017"].round(2).T.to_string())
