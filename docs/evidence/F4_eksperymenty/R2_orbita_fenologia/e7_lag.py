"""E7: lagged response of vineyard vegetation anomaly to root-zone soil-moisture anomaly (ISMN 20-30 cm)."""
import numpy as np, pandas as pd
from common import insitu_z, r_ci, era5_rz_z
from e5_orbit_strat import build
ins = insitu_z(); erz = era5_rz_z()
for col in ("ndvi", "ndmi"):
    V = build("VINEYARD_06", "S2SR_2.5m", col)
    V = V[V.index.month.isin([6, 7, 8, 9])]
    print(col)
    for L in (0, 10, 20, 30, 45, 60):
        # reference anomaly = mean of ISMN z over the 30 days ending L days before the scene
        ref = ins.rolling(30, min_periods=20).mean().shift(L, freq="D")
        r, lo, hi, n = r_ci(V["harm_orbit"], ref)
        ref2 = erz.rolling(30, min_periods=20).mean().shift(L, freq="D")
        r2, lo2, hi2, n2 = r_ci(V["harm_orbit"], ref2)
        print(f"  lag {L:2d} d: r(ISMN 30d mean)={r:.3f} [{lo:.2f},{hi:.2f}] n={n} | r(ERA5 RZ)={r2:.3f}")
