"""C8 - multiple-comparison check: Bonferroni-style 99.76 % (=1-0.05/21) paired block-bootstrap CI for the two
correlation gains whose 95 % CI excluded zero (L2 vs RZ; equal-weight ERA5 RZ + S1-SWI vs RZ), 5000 draws,
30-day and 90-day blocks."""
import numpy as np, pandas as pd
from common import COMMON, OUT, era5_full, era5_layers, ismn_ref, pair, zclim, _blocks
e = era5_full().loc[COMMON[0]:COMMON[1]]; lay = era5_layers(e); z_ins = zclim(ismn_ref())
cv = pd.read_csv(f"{OUT}/c4_cv_series.csv", index_col=0, parse_dates=True)
tests = {"L2 vs RZ (2016-2024 clim)": (zclim(lay["L2_7_28"]), zclim(lay["RZ_0_100"])),
         "L2 vs RZ (LOYO clim)": (cv["E_L2"], cv["E_RZ"]),
         "EQ RZ+S1 vs RZ (LOYO)": (cv["EQ_RZ_S"], cv["E_RZ"])}
q = 100 * 0.05 / 21 / 2
rows = []
for name, (a, b) in tests.items():
    p = pair(a, b, z_ins, names=["a", "b", "y"]); A, B, Y = (p[c].to_numpy() for c in "aby")
    for blk in (30, 90):
        u, ib = _blocks(p.index, blk); rng = np.random.default_rng(7)
        ds = []
        for _ in range(5000):
            ii = np.concatenate([ib[k] for k in rng.choice(u, len(u))])
            ds.append(np.corrcoef(A[ii], Y[ii])[0, 1] - np.corrcoef(B[ii], Y[ii])[0, 1])
        ds = np.array(ds)
        rows.append({"test": name, "block_days": blk, "dR": np.corrcoef(A, Y)[0, 1] - np.corrcoef(B, Y)[0, 1],
                     "lo_95": np.percentile(ds, 2.5), "hi_95": np.percentile(ds, 97.5),
                     "lo_bonf": np.percentile(ds, q), "hi_bonf": np.percentile(ds, 100 - q), "n": len(p)})
df = pd.DataFrame(rows); print(df.round(3).to_string(index=False)); df.to_csv(f"{OUT}/c8_multcomp.csv", index=False)
