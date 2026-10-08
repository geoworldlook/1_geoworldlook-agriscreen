"""A4b: list of v1.0 alert dekads (B0, IV-X) and V1c with ISMN 20-30 cm dekadal z."""
import logging, warnings
import pandas as pd
logging.basicConfig(level=logging.WARNING); warnings.filterwarnings("ignore")
import a4_alert as A
for var in ("B0_ndvi_scene", "V1c_ndvi_trailing30d"):
    st = A.status_for(A.ser[var].rename(var), (4, 10))
    j = st.join(A.ins_dk.rename("ins_z_dekad"), how="left")
    j = j[(j["cdi_level"] == 3) & (j.index <= "2024-12-31")]
    print(var); print(j[["sma_rz", "veg_z", "veg_age_days", "ins_z_dekad"]].round(2).to_string())
    j.to_csv(f"{A.OUT}/a4b_alerts_{var}.csv")
