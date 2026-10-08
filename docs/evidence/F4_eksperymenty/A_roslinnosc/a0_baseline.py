"""A0: reproduce v1.0 vegetation-anomaly validation (VINEYARD_06 + station plot) vs ISMN 20-30 cm."""
import logging

import numpy as np
import pandas as pd

from common import OUT, DATA, INDICES, group, ins_z, era5_rz_z, r_ci, scene_z, events, pair

logging.basicConfig(level=logging.WARNING)

rows = []
zref = ins_z("rz")
z10 = ins_z("10")
print("ISMN 20-30 cm z: n days", zref.notna().sum(), zref.index.min(), zref.index.max())

# ERA5 sanity: R=0.583 [0.50,0.665], n=2976
p = pair(era5_rz_z(), zref)
r = r_ci(era5_rz_z(), zref)
print(f"ERA5 RZ vs ISMN 20-30: R={r['r']:.3f} [{r['lo']:.3f},{r['hi']:.3f}] n={r['n']}")

for site in ("VINEYARD_06", "SMOSMANIA_Condom_poly", "SMOSMANIA_Condom"):
    for prod in ("S2SR_2.5m", "S2_10m"):
        g = group(site, prod)
        for idx in INDICES:
            if idx not in g or g[idx].isna().all():
                continue
            z = scene_z(g, idx)
            a = r_ci(z, zref)
            b = r_ci(z, z10)
            ev = events(z, zref)
            rows.append(dict(site=site, product=prod, index=idx, r_rz=a["r"], lo=a["lo"], hi=a["hi"], n=a["n"],
                             r_10cm=b["r"], n10=b["n"], pod=ev["pod"], far=ev["far"], hss=ev["hss"],
                             hits=ev["hits"], n_obs_ev=ev["hits"] + ev["misses"]))
res = pd.DataFrame(rows)
pd.set_option("display.width", 200)
print(res.round(3).to_string(index=False))
res.to_csv(f"{OUT}/a0_baseline.csv", index=False)

# Cross-check against registry anomalies (gwl_anomalies.csv) for VINEYARD_06 NDVI SR
an = pd.read_csv(f"{DATA}/gwl_anomalies.csv")
reg = an[(an.site_id == "VINEYARD_06") & (an["product"] == "S2SR_2.5m_NDVI")].copy()
reg["date"] = pd.to_datetime(reg["date"])
mine = scene_z(group("VINEYARD_06", "S2SR_2.5m"), "ndvi")
mine_d = mine.groupby(mine.index.floor("D")).mean()
j = reg.set_index("date")["z"].to_frame("reg").join(mine_d.rename("mine"), how="outer")
print("registry vs recomputed NDVI SR z: n_reg", j["reg"].notna().sum(), "n_mine", j["mine"].notna().sum(),
      "max abs diff", float((j["reg"] - j["mine"]).abs().max()))
