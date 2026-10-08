"""C0 - reproduce the v1.0 soil-moisture validation numbers with the repo definitions.

(a) validate_anomalies section 2: R(ERA5 0-100 cm z, ISMN 20-30 cm z), both DOY climatologies over the common
    period 2016-2024 (hw 15, min_n 20); expected R=0.583 [0.50,0.665], n=2976.
(b) section 4: dekads with status sma_rz <= -1 (ERA5 0-100 cm z vs 1991-2020 climatology, dekadal mean) vs dekads
    with mean ISMN 20-30 cm z <= -1; expected POD 0.574, FAR 0.571, n=312.
    Done twice: with gwl_status.csv from the Drive registry and with sma_rz recomputed from era5_land_daily.csv.
"""
import json

import numpy as np
import pandas as pd

from common import (CLIM_REF, COMMON, DRIVE, OUT, contingency, contingency_ci, era5_full, ismn_ref, r_ci,
                    rootzone, to_dekad, zclim, anom35)

e = era5_full()
ec = e.loc[COMMON[0]:COMMON[1]]
rz_ins = ismn_ref()
z_ins = zclim(rz_ins)                       # reference anomaly (2016-2024 base)
z_era_val = zclim(rootzone(ec))             # validation definition (2016-2024 base)
r, lo, hi, n = r_ci(z_era_val, z_ins)
print(f"(a) R clim anomaly ERA5 RZ vs ISMN 20-30: {r:.3f} [{lo:.3f},{hi:.3f}] n={n}")
r35 = r_ci(anom35(rootzone(ec)), anom35(rz_ins))
print(f"    R 35-day anomaly: {r35[0]:.3f} [{r35[1]:.3f},{r35[2]:.3f}] n={r35[3]}")

# (b) events from the registry status table (first site per date, as validate_anomalies does)
st = pd.read_csv(f"{DRIVE}/gwl_status.csv")
print("status run_ids:", st.run_id.unique().tolist())
st = st.drop_duplicates("date").copy()
st["date"] = pd.to_datetime(st["date"])
ins_dk = to_dekad(z_ins)
j = st.set_index("date").join(ins_dk.rename("ins_z"), how="inner").dropna(subset=["ins_z", "sma_rz"])
c_reg = contingency((j["ins_z"] <= -1).to_numpy(), (j["sma_rz"] <= -1).to_numpy())
print("(b) registry status:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in c_reg.items()})

# (b') recomputed sma_rz: daily z vs 1991-2020 clim (min_n 30, as era5_anomalies), dekadal mean from 2016-01-01
z_op = zclim(rootzone(e), ref=CLIM_REF, min_n=30)
sma_dk = to_dekad(z_op.loc["2016-01-01":])
jj = pd.concat([sma_dk.rename("sma"), ins_dk.rename("ins")], axis=1).dropna()
c_rec = contingency((jj["ins"] <= -1).to_numpy(), (jj["sma"] <= -1).to_numpy())
print("(b') recomputed:", {k: (round(v, 3) if isinstance(v, float) else v) for k, v in c_rec.items()})
cmp = st.set_index("date")["sma_rz"].to_frame().join(sma_dk.rename("re")).dropna()
print("    max |registry sma_rz - recomputed| =", float((cmp["sma_rz"] - cmp["re"]).abs().max()))
ci = contingency_ci(jj["ins"] <= -1, jj["sma"] <= -1, by="year")
ci90 = contingency_ci(jj["ins"] <= -1, jj["sma"] <= -1, by="90d")
print("    CI by year:", ci, "\n    CI 90-day blocks:", ci90)

# share of z<=-1 days, 2016-2024, operational vs validation base -> base-period effect
fr = {"era5_1991_2020_base": float((z_op.loc[COMMON[0]:COMMON[1]] <= -1).mean()),
      "era5_2016_2024_base": float((z_era_val <= -1).mean()),
      "ismn_2016_2024_base": float((z_ins <= -1).mean()),
      "era5_mean_z_2016_2024_vs_1991_2020": float(z_op.loc[COMMON[0]:COMMON[1]].mean())}
print("share of days z<=-1:", fr)
json.dump({"R_clim": [r, lo, hi, n], "R_35d": list(r35), "events_registry": c_reg, "events_recomputed": c_rec,
           "events_ci_year": ci, "events_ci_90d": ci90, "freq": fr},
          open(f"{OUT}/c0_baseline.json", "w"), indent=1, default=float)
