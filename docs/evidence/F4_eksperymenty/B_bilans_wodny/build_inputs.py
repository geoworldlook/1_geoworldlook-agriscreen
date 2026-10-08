"""Build daily forcing (P, ET0 Hargreaves) and daily Kcb series for each NDVI source.

Outputs: inputs_forcing.csv, inputs_kcb.csv, inputs_summary.json
"""
import json

import numpy as np
import pandas as pd

import common as C
import config as K
import wb_model as W

e = C.era5()
days = e.index
et = W.et0_hargreaves(e["t2m_c"], e["t2m_min_c"], C.LAT_DEG)
forcing = pd.DataFrame({"precip_mm": e["precip_mm"], "et0": et["et0"], "tmax_approx": et["tmax_approx"],
                        "t2m_c": e["t2m_c"], "t2m_min_c": e["t2m_min_c"]}, index=days)
forcing.to_csv(f"{C.OUT}/inputs_forcing.csv", index_label="date")

obs = pd.read_csv(f"{C.DATA}/gwl_observations.csv")
sources = {
    # name: (site, product, min_clear, months of observation season)
    "vine_SR": ("VINEYARD_06", "S2SR_2.5m", K.NDVI["min_clear"], (4, 10)),
    "vine_10m": ("VINEYARD_06", "S2_10m", K.NDVI["min_clear"], (4, 10)),
    "station_L2A": ("SMOSMANIA_Condom", "S2_L2A", None, None),       # 50 m buffer, all months, no clear_frac
    "stationplot_SR": ("SMOSMANIA_Condom_poly", "S2SR_2.5m", K.NDVI["min_clear"], (4, 10)),
}
kcb = {}
summ = {}
for name, (site, prod, mc, months) in sources.items():
    s = W.ndvi_scenes(obs, site, prod, mc)
    if months is not None:
        s = s[(s.index.month >= months[0]) & (s.index.month <= months[1])]
    sd = W.despike(s, K.NDVI["despike_window"])
    k = W.daily_kcb(sd, days, K.NDVI["max_gap_days"], months, K.SOIL_BASE["kc_min"])
    kcb[name] = k["kcb"]
    kcb[name + "_clim"] = k["kcb_clim"]
    kcb[name + "_isobs"] = (k["source"] == "obs").astype(int)
    frac_obs = {str(y): float((k.loc[str(y), "source"] == "obs").mean()) for y in range(2016, 2027)}
    summ[name] = dict(n_scenes=int(len(s)), first=str(s.index.min().date()), last=str(s.index.max().date()),
                      ndvi_mean=float(s.mean()), kcb_obs_mean=float(k["kcb_obs"].mean()),
                      kcb_clim_min=float(k["kcb_clim"].min()), kcb_clim_max=float(k["kcb_clim"].max()),
                      frac_days_obs_by_year=frac_obs)
kcb = pd.DataFrame(kcb, index=days)
kcb.to_csv(f"{C.OUT}/inputs_kcb.csv", index_label="date")

yr = forcing.resample("YE").sum(numeric_only=True)
summ["et0_hargreaves_annual_mm"] = {str(i.year): round(float(v), 1) for i, v in yr["et0"].items()}
summ["et0_mean_annual_1991_2020_mm"] = float(yr.loc["1991":"2020", "et0"].mean())
summ["precip_mean_annual_1991_2020_mm"] = float(yr.loc["1991":"2020", "precip_mm"].mean())
mon = forcing.loc["1991":"2020"].groupby(forcing.loc["1991":"2020"].index.month)["et0"].mean()
summ["et0_monthly_mean_mm_per_day"] = {int(m): round(float(v), 2) for m, v in mon.items()}
print(json.dumps(summ, indent=1))
with open(f"{C.OUT}/inputs_summary.json", "w") as f:
    json.dump(summ, f, indent=1)
