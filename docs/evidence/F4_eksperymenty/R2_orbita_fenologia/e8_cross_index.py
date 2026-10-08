import numpy as np, pandas as pd
from common import insitu_z, r_ci
from e5_orbit_strat import build, dr_ci
ins = insitu_z()
A = {c: build("VINEYARD_06", "S2SR_2.5m", c) for c in ("ndvi", "ndmi", "crswir")}
A["crswir"][["pooled", "harm", "harm_orbit", "orbit_strat"]] *= -1
for per, months in (("IV-X", range(4, 11)), ("VI-IX", range(6, 10))):
    sel = lambda s: s[s.index.month.isin(months)]
    base = sel(A["ndvi"]["pooled"])
    for c in ("ndmi", "crswir"):
        for v in ("harm_orbit",):
            d = dr_ci(sel(A[c][v]), base, ins)
            print(per, f"dR({c}_{v} - ndvi_pooled) = {d[0]:+.3f} [{d[1]:+.3f},{d[2]:+.3f}] n={d[3]}")
    d = dr_ci(sel(A["ndmi"]["harm_orbit"]), sel(A["ndvi"]["harm_orbit"]), ins)
    print(per, f"dR(ndmi_harm_orbit - ndvi_harm_orbit) = {d[0]:+.3f} [{d[1]:+.3f},{d[2]:+.3f}]")
    # 30-day target
    ins30 = ins.rolling(30, min_periods=20).mean()
    for c in ("ndvi", "ndmi"):
        r = r_ci(sel(A[c]["harm_orbit"]), ins30); r0 = r_ci(sel(A["ndvi"]["pooled"]), ins30)
        print(per, f"vs ISMN 30-d mean: {c}_harm_orbit r={r[0]:.3f} [{r[1]:.2f},{r[2]:.2f}]; ndvi_pooled r={r0[0]:.3f} [{r0[1]:.2f},{r0[2]:.2f}]")
