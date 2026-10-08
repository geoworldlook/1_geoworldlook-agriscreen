"""Regression test: own FAO-56 implementation (wb_model.fao56_dual) vs pyfao56 v1.4.3 (Thorp 2022).

Same inputs (ERA5-Land rain, Hargreaves ET0, vineyard Kcb from S-2 SR), 2016-01-01..2018-12-31.
pyfao56: ETref supplied directly, Wndsp = 2 m/s at 2 m, RHmin = 45 % (-> Kcmax = 1.2), Kcb and h via Update.
"""
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad/pkgs/pyfao56_lib")
import pyfao56 as fao  # noqa: E402

import common as C  # noqa: E402
import config as K  # noqa: E402
import wb_model as W  # noqa: E402

f = pd.read_csv(f"{C.OUT}/inputs_forcing.csv", index_col="date", parse_dates=True).loc["2016":"2018"]
kcb = pd.read_csv(f"{C.OUT}/inputs_kcb.csv", index_col="date", parse_dates=True).loc["2016":"2018", "vine_SR"]
soil = dict(K.SOIL_BASE, **K.VINE)

own = W.run_wb(f, kcb, soil)

par = fao.Parameters(Kcbini=soil["kc_min"], Kcbmid=0.65, Kcbend=0.40, Lini=1, Ldev=1, Lmid=10000, Lend=1,
                     hini=soil["h_m"], hmax=soil["h_m"], thetaFC=soil["theta_fc"], thetaWP=soil["theta_wp"],
                     theta0=soil["theta_fc"], Zrini=soil["zr_m"], Zrmax=soil["zr_m"], pbase=soil["p_base"],
                     Ze=soil["ze_m"], REW=soil["rew_mm"])
wth = fao.Weather()
wth.wndht = 2.0
wth.rfcrp = "S"
keys = f.index.strftime("%Y-%j")
wd = pd.DataFrame(np.nan, index=keys, columns=wth.cnames)
wd["Rain"] = f["precip_mm"].to_numpy()
wd["ETref"] = f["et0"].to_numpy()
wd["Wndsp"] = 2.0
wd["RHmin"] = 45.0
wd["Tmax"] = f["tmax_approx"].to_numpy()
wd["Tmin"] = f["t2m_min_c"].to_numpy()
wth.wdata = wd
upd = fao.Update()
upd.udata = pd.DataFrame({"Kcb": kcb.to_numpy(), "h": soil["h_m"], "fc": np.nan}, index=keys)
mdl = fao.Model(keys[0], keys[-1], par, wth, upd=upd)
mdl.run()
ref = mdl.odata
ref.index = f.index
out = {}
for a, b in (("Dr", "Dr"), ("De", "De"), ("Ks", "Ks"), ("ETa", "ETa"), ("E", "E"), ("T", "T"), ("fc", "fc")):
    d = (own[a].to_numpy() - ref[b].astype(float).to_numpy())
    out[a] = float(np.nanmax(np.abs(d)))
print("max |own - pyfao56| over 2016-2018:", out)
print("Kcmax pyfao56 range:", ref["Kcmax"].astype(float).min(), ref["Kcmax"].astype(float).max())
print("annual ETa own (mm):", own["ETa"].resample("YE").sum().round(1).to_dict())
assert out["Dr"] < 0.05 and out["ETa"] < 0.01, out
print("PASS")
