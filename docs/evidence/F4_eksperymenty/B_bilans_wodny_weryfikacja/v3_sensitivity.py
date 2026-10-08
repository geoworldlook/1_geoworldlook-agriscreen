"""Is 'the S-2 Kcb part of the WB anomaly is negligible' an artefact of the over-dry literature parameters?

Re-run V1 (observed Kcb) and V3 (climatological Kcb) with less water-limited settings:
larger TAW (Zr 1.5, 2.0, 3.0 m), ET0 scaled x0.8, and both; report the S-2 component size, Ks<1 days,
August RSW and R / dR vs ISMN. Uses the author's numpy loop (verified against pyfao56 in v2).
"""
import json
import sys

import numpy as np
import pandas as pd

SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
OUT = f"{SCR}/exp_wb_verify"
sys.path.insert(0, f"{SCR}/exp_wb")
sys.path.insert(0, OUT)
import common as C  # noqa: E402
import config as K  # noqa: E402
import wb_model as W  # noqa: E402
from v1_helpers import boot_dr  # noqa: E402

f = pd.read_csv(f"{C.OUT}/inputs_forcing.csv", index_col="date", parse_dates=True)
kc = pd.read_csv(f"{C.OUT}/inputs_kcb.csv", index_col="date", parse_dates=True)
y = C.ins_z("rz")
zb = C.anom_common(C.s4.rootzone(C.era5()))
VINE = dict(K.SOIL_BASE, **K.VINE)
ivx = lambda s: s[(s.index.month >= 4) & (s.index.month <= 10)]
out = {}
for zr in (1.0, 1.5, 2.0, 3.0):
    for sc in (1.0, 0.8):
        ff = f.copy()
        ff["et0"] = f["et0"] * sc
        soil = dict(VINE, zr_m=zr)
        r1 = W.run_wb(ff, kc["vine_SR"], soil)
        r3 = W.run_wb(ff, kc["vine_SR_clim"], soil)
        z1, z3 = C.anom_common(r1["RSW"]), C.anom_common(r3["RSW"])
        comp = z1 - z3
        rr = r1.loc["2016":"2024"]
        out[f"zr{zr}_et0x{sc}"] = {
            "R_V1": round(float(C.pair(z1, y).corr().iloc[0, 1]), 4),
            "R_V3": round(float(C.pair(z3, y).corr().iloc[0, 1]), 4),
            "dR_V1_minus_ERA5": boot_dr(z1, zb, y, 30)["d"],
            "dR_V1_minus_ERA5_IVX": boot_dr(ivx(z1), ivx(zb), ivx(y), 30),
            "dR_V1_minus_V3": boot_dr(z1, z3, y, 30),
            "S2comp_std_IVX": round(float(ivx(comp).std()), 3),
            "r_z1_z3": round(float(C.pair(z1, z3).corr().iloc[0, 1]), 4),
            "Ks_lt1_days_per_yr": round(float((rr["Ks"] < 1).groupby(rr.index.year).sum().mean()), 1),
            "RSW_Aug": round(float(rr.loc[rr.index.month == 8, "RSW"].mean()), 3),
        }
        print(f"zr{zr}_et0x{sc}", out[f"zr{zr}_et0x{sc}"])
json.dump(out, open(f"{OUT}/v3_sensitivity.json", "w"), indent=1, default=str)
