import warnings; warnings.filterwarnings("ignore")
import os
import pandas as pd, numpy as np
from common import DRIVE, insitu, ismn_rz, zclim, s7, era5, COMMON, r_ci, swi_regular, rootzone, paired_diff_ci

o = pd.read_csv(os.path.join(DRIVE, "gwl_observations.csv"))
o = o[(o.site_id == "SMOSMANIA_Condom") & o["product"].isin(["S1_CD_A", "S1_GRD", "S2_L2A"])]
o["time"] = pd.to_datetime(o["time_utc"]).dt.tz_localize(None)
s1 = o[o["product"].isin(["S1_CD_A", "S1_GRD"])].pivot_table(index=["time", "orbit"], columns="variable", values="value").reset_index()
print(s1.groupby("orbit").agg(n=("vv_db", "size"), ang=("angle", "mean"), vv=("vv_db", "mean"), vvsd=("vv_db", "std")).round(2))
s1["hour"] = s1["time"].dt.hour
print(s1.groupby("orbit")["hour"].agg(lambda x: x.mode().iat[0]))

e = era5()
e_c = e.loc[COMMON[0]:COMMON[1]]
d05 = insitu(0.05)["sm"]
rz = ismn_rz()
z_rz = zclim(rz)
z_05 = zclim(d05)
a35_05 = s7._moving_anomaly(d05, 35, 15)
a35_rz = s7._moving_anomaly(rz, 35, 15)

res = []
def add(name, x, y, lab):
    r, lo, hi, n = r_ci(x, y)
    res.append((name, lab, round(r, 3), round(lo, 3), round(hi, 3), n))

# daily S1 (mean of obs same day)
sm = s1.set_index("time")["sm_s1"].sort_index()
smd = sm.groupby(sm.index.floor("D")).mean()
add("S1 CD raw daily", zclim(smd, min_n=10), z_05, "ISMN5 clim")
add("S1 CD raw daily", s7._moving_anomaly(smd, 35, 3), a35_05, "ISMN5 35d")
add("ERA5 L1", s7._moving_anomaly(e_c["sm_l1"], 35, 15).reindex(smd.index), a35_05, "ISMN5 35d (S1 days)")
add("S1 CD raw daily", zclim(smd, min_n=10), z_rz, "ISMN20-30 clim")
# per-orbit
for orb, g in s1.groupby("orbit"):
    x = g.set_index("time")["sm_s1"]; x.index = x.index.floor("D")
    x = x[~x.index.duplicated()]
    add(f"S1 orbit {orb}", s7._moving_anomaly(x, 35, 3), a35_05, "ISMN5 35d")
# per-orbit standardised VV (z of vv within orbit, monthly-clim-free) -> combine
s1["vv_z"] = s1.groupby("orbit")["vv_db"].transform(lambda v: (v - v.mean()) / v.std())
vz = s1.set_index("time")["vv_z"]; vzd = vz.groupby(vz.index.floor("D")).mean()
add("S1 VV z per orbit daily", s7._moving_anomaly(vzd, 35, 3), a35_05, "ISMN5 35d")
# 3-obs running mean (temporal speckle reduction)
add("S1 CD 3-obs mean", s7._moving_anomaly(smd.rolling(3, center=True, min_periods=2).mean(), 35, 3), a35_05, "ISMN5 35d")

# SWI from S1 irregular obs (all orbits), daily value
for T in (5, 10, 20, 30, 40):
    sw = swi_regular(sm, T)
    swd = sw.groupby(sw.index.floor("D")).last().asfreq("D").ffill(limit=6)
    add(f"SWI(S1) T={T}", zclim(swd, min_n=20), z_rz, "ISMN20-30 clim")
for T in (5, 10, 20):
    sw = swi_regular(sm, T)
    swd = sw.groupby(sw.index.floor("D")).last().asfreq("D").ffill(limit=6)
    add(f"SWI(S1) T={T}", s7._moving_anomaly(swd, 35, 15), a35_rz, "ISMN20-30 35d")

# Seasonal split for S1 35d vs 5 cm (vegetation): Apr-Sep vs Oct-Mar
x = s7._moving_anomaly(smd, 35, 3)
for lab, months in (("Oct-Mar", [10, 11, 12, 1, 2, 3]), ("Apr-Sep", [4, 5, 6, 7, 8, 9])):
    xs = x[x.index.month.isin(months)]
    add(f"S1 CD {lab}", xs, a35_05, "ISMN5 35d")
    es = s7._moving_anomaly(e_c["sm_l1"], 35, 15).reindex(xs.index)
    add(f"ERA5 L1 {lab}", es, a35_05, "ISMN5 35d (S1 days)")

df = pd.DataFrame(res, columns=["series", "ref", "R", "lo", "hi", "n"])
print(df.to_string(index=False))
