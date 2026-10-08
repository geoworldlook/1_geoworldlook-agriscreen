import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from common import insitu, ismn_rz, zclim, s7, era5, COMMON, r_ci, rootzone, clim_anomaly
e = era5(); e_c = e.loc[COMMON[0]:COMMON[1]]
rz = ismn_rz(); z_ins = zclim(rz)
a = lambda s: s7._moving_anomaly(s, 35, 15)
era_rz = rootzone(e_c); e028 = (7*e_c.sm_l1 + 21*e_c.sm_l2)/28
for lab, x in (("RZ", era_rz), ("0-28", e028)):
    print(lab, "clim15", np.round(r_ci(zclim(x), z_ins), 3), " 35d", np.round(r_ci(a(x), a(rz)), 3),
          " clim hw30", np.round(r_ci(zclim(x, hw=30), zclim(rz, hw=30)), 3),
          " clim hw7", np.round(r_ci(zclim(x, hw=7), zclim(rz, hw=7)), 3))
    # slow component: clim anomaly minus 35d anomaly (i.e. 35-d smoothed clim anomaly)
    ca_x = clim_anomaly(x, COMMON, 15, 20); ca_y = clim_anomaly(rz, COMMON, 15, 20)
    slow_x = (ca_x.value - ca_x.clim_mean).rolling("35D", center=True, min_periods=15).mean()
    slow_y = (ca_y.value - ca_y.clim_mean).rolling("35D", center=True, min_periods=15).mean()
    print("   slow (35-d mean of clim anomaly) R", np.round(r_ci(slow_x, slow_y), 3))
    # variance share of the slow part in the clim anomaly
    raw = (ca_x.value - ca_x.clim_mean)
    print("   var share slow/total ERA5:", round(slow_x.var() / raw.var(), 2), " ISMN:", round(slow_y.var() / (ca_y.value - ca_y.clim_mean).var(), 2))

# Operational clim 1991-2020: share of days z<=-1 in 2016-2024 and by month
z_op = zclim(rootzone(e), ref=("1991-01-01", "2020-12-31"))
zz = z_op.loc["2016":"2024"]
print("share z<=-1 (1991-2020 clim) 2016-2024:", round((zz <= -1).mean(), 3), "expected ~0.16 if normal")
print("share by year:", (zz <= -1).groupby(zz.index.year).mean().round(2).to_dict())
# trend in RZ annual means 1991-2025
ann = rootzone(e).groupby(rootzone(e).index.year).mean().loc[1991:2025]
sl = np.polyfit(ann.index, ann.values, 1)[0]
print("RZ trend m3/m3 per decade:", round(sl*10, 4), " clim std of annual means", round(ann.std(), 4))
# percentile vs z: skewness by month of RZ
full = clim_anomaly(rootzone(e), ("1991-01-01", "2020-12-31"), 15, 30)
for m in (1, 4, 7, 8, 9, 10):
    s = full[full.index.month == m]
    p = s.loc[s.z <= -1, "percentile"]
    print(f"month {m}: skew {round(s.value.loc['1991':'2020'].skew(),2)}  z=-1 ~ percentile median {round(np.nanmax(p) if len(p) else np.nan,1)}  share(z<=-1 in 1991-2020) {round((s.z.loc['1991':'2020']<=-1).mean(),3)}")

# neighbours: 20-30 cm clim anomaly correlation with Condom
coords = {"Condom": (43.9744, 0.3361), "CreondArmagnac": (43.9936, -0.0469), "PeyrusseGrande": (43.6664, 0.2217),
          "Savenes": (43.825, 1.1767), "Lahas": (43.5472, 0.8878), "Urgons": (43.6397, -0.435), "SaintFelixdeLauragais": (43.4417, 1.88),
          "Montaut": (43.1922, 1.6436), "Sabres": (44.1475, -0.8456)}
def dist(a, b):
    from math import radians, sin, cos, asin, sqrt
    la1, lo1, la2, lo2 = map(radians, (*a, *b))
    h = sin((la2-la1)/2)**2 + cos(la1)*cos(la2)*sin((lo2-lo1)/2)**2
    return 2*6371*asin(sqrt(h))
for st, c in coords.items():
    if st == "Condom": continue
    try:
        r2 = ismn_rz(st)
        zr = zclim(r2)
        print(f"{st:22s} {dist(coords['Condom'], c):5.0f} km  R(clim z, Condom 20-30)={np.round(r_ci(zr, z_ins)[:2],3)} n={r_ci(zr, z_ins)[3]}  R(ERA5 Condom-cell 0-28)={round(r_ci(zclim(e028), zr)[0],3)}  R(ERA5 RZ)={round(r_ci(zclim(era_rz), zr)[0],3)}")
    except Exception as ex:
        print(st, "ERR", ex)
