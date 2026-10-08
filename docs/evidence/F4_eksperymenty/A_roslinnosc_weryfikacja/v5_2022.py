import os, sys, warnings, logging
import numpy as np, pandas as pd
warnings.filterwarnings("ignore"); logging.basicConfig(level=logging.WARNING)
HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)
from v0_base import ismn, SCR, clim_z
import step_04_metrics_alert as s4
d20, d30, d10 = ismn(0.20), ismn(0.30), ismn(0.10)
e = pd.read_csv(os.path.join(SCR, "drive_data/era5_land_daily.csv"), parse_dates=["time"])
e = e.set_index(e.time.dt.floor("D")); e = e[~e.index.duplicated(keep="last")].sort_index()
rz = s4.rootzone(e)
ez = clim_z(rz.loc["1991":"2024"], ref=("1991-01-01", "2020-12-31"))
rows = []
for yv in range(2016, 2025):
    sl = slice(f"{yv}-07-01", f"{yv}-09-15")
    rows.append(dict(year=yv, ismn20_min=d20[sl].min(), ismn30_min=d30[sl].min(), ismn20_mean=d20[sl].mean(), ismn30_mean=d30[sl].mean(),
                     era5_rz_mean=rz[sl].mean(), era5_rz_z_mean=ez[sl].mean(), era5_l3_mean=e.sm_l3[sl].mean(),
                     precip_JunAug=e.precip_mm[f"{yv}-06-01":f"{yv}-08-31"].sum(), precip_AprSep=e.precip_mm[f"{yv}-04-01":f"{yv}-09-30"].sum(),
                     t2m_JJA=e.t2m_c[f"{yv}-06-01":f"{yv}-08-31"].mean()))
print(pd.DataFrame(rows).round(3).to_string(index=False))
print("2022 monthly precip:", e.precip_mm["2022-04":"2022-09"].resample("ME").sum().round(0).to_dict())
z20, z30 = clim_z(d20.loc["2016":"2024"]), clim_z(d30.loc["2016":"2024"])
rzi = pd.concat([d20, d30], axis=1).dropna().mean(axis=1); zr = clim_z(rzi)
dk = s4.dekad_end(pd.Series(zr.index))
t = pd.DataFrame({"z20": z20.reindex(zr.index).values, "z30": z30.reindex(zr.index).values, "z2030": zr.values, "dk": dk.values}).groupby("dk").mean()
alerts = ["2022-07-20", "2022-08-20", "2022-08-31", "2022-09-10", "2022-09-20", "2022-09-30"]
print(t.loc[pd.to_datetime(alerts)].round(2).to_string())
for yv in (2017, 2019, 2022):
    sl = slice(f"{yv}-07-01", f"{yv}-09-15")
    print(yv, "Jul-midSep mean z20 %.2f z30 %.2f z20-30 %.2f; 30cm clim SD Aug %.3f" % (z20[sl].mean(), z30[sl].mean(), zr[sl].mean(), d30[d30.index.month == 8].std()))
