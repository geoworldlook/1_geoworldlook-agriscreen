import numpy as np, pandas as pd
from common import DATA
from e5_orbit_strat import build
V = build("VINEYARD_06", "S2SR_2.5m", "ndvi")
s = pd.read_csv(f"{DATA}/gwl_status.csv"); s = s[(s.site_id == "VINEYARD_06") & (s.cdi_class == "alert")].copy()
s["scene"] = pd.to_datetime(s["date"]) - pd.to_timedelta(s["veg_age_days"], unit="D")
j = s.set_index("scene")[["date", "veg_z"]].join(V, how="left")
j["orbit"] = np.where(j["early"] == 1, "early", np.where(j["early"] == 0, "late", "both"))
print(j[["date", "veg_z", "orbit", "pooled", "orbit_strat", "harm_orbit"]].round(2).to_string())
print("alerts kept (z<=-1): pooled", (j.pooled <= -1).sum(), "orbit_strat", (j.orbit_strat <= -1).sum(), "harm_orbit", (j.harm_orbit <= -1).sum(), "of", len(j))
