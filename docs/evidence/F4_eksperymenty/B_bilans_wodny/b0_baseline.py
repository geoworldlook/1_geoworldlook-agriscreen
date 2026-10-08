"""B0: reproduce the v1.0 baseline numbers with the repo definitions.

Targets (CONTEXT): ERA5-Land root-zone anomaly vs ISMN 20-30 cm R=0.583 [0.50,0.665], n=2976;
dekadal events POD=0.574, FAR=0.571, n=312.
"""
import json

import numpy as np
import pandas as pd

import common as C

e = C.era5()
rz = C.s4.rootzone(e)

# 1) daily anomaly R (validate_anomalies, part 2: anomaly_clim over the common period)
era_z = C.anom_common(rz)
res = {"R_era5_rz_vs_ismn2030": C.r_ci(era_z, C.ins_z("rz"))}
res["R_era5_rz_vs_ismn10"] = C.r_ci(era_z, C.ins_z("10"))

# 2) dekadal events, (a) from the registry status table (as in validate_anomalies part 4)
st = pd.read_csv(f"{C.DATA}/gwl_status.csv").drop_duplicates("date").copy()
st["date"] = pd.to_datetime(st["date"])
ins_dk = C.dekad_mean(C.ins_z("rz"))
res["events_registry_status"] = C.pod_far_ci(st.set_index("date")["sma_rz"], ins_dk)

# (b) recomputed from ERA5 with the operational definition (ref 1991-2020, dekad mean of daily z)
era_oper_z = C.anom_oper(rz)
res["events_recomputed_oper"] = C.pod_far_ci(C.dekad_mean(era_oper_z.loc["2016":]), ins_dk)
# (c) both anomalies over the common period (consistency variant, not the v1.0 definition)
res["events_common_ref"] = C.pod_far_ci(C.dekad_mean(era_z), ins_dk)

# agreement registry sma_rz vs recomputed
j = pd.concat([st.set_index("date")["sma_rz"], C.dekad_mean(era_oper_z.loc["2016":])], axis=1, join="inner").dropna()
res["registry_vs_recomputed_sma_rz_maxabsdiff"] = float((j.iloc[:, 0] - j.iloc[:, 1]).abs().max())
res["n_status_sites"] = int(pd.read_csv(f"{C.DATA}/gwl_status.csv")["site_id"].nunique())

print(json.dumps(res, indent=1, default=float))
with open(f"{C.OUT}/b0_baseline.json", "w") as f:
    json.dump(res, f, indent=1, default=float)
