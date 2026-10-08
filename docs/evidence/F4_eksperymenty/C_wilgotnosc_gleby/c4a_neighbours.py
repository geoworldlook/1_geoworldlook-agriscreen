"""C4a - neighbouring SMOSMANIA stations (20-30 cm) as an independent third source for triple collocation.
Checks data coverage and agreement with Condom (anomaly R) - only used to choose the TC instrument."""
import numpy as np, pandas as pd
from common import OUT, ismn_ref, zclim, r_ci
z_c = zclim(ismn_ref())
rows = []
for st, km in (("PeyrusseGrande", 35), ("CreondArmagnac", 31), ("Lahas", 63), ("Savenes", 69)):
    try:
        ref = ismn_ref(st)
    except Exception as ex:
        print(st, ex); continue
    z = zclim(ref)
    r, lo, hi, n = r_ci(z, z_c)
    rows.append({"station": st, "dist_km": km, "n_days": len(ref), "first": ref.index.min().date(), "last": ref.index.max().date(),
                 "R_z_vs_Condom": r, "ci_lo": lo, "ci_hi": hi, "n": n})
df = pd.DataFrame(rows); print(df.round(3).to_string(index=False)); df.to_csv(f"{OUT}/c4a_neighbours.csv", index=False)
