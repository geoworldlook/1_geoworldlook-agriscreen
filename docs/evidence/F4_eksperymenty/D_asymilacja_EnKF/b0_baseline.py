"""B0 - reproduce the v1.0 baselines with the repo definitions before any DA experiment.

Expected: ERA5-Land 0-100 cm clim-anomaly R vs ISMN 20-30 cm = 0.583 [0.50, 0.665], n = 2976;
          ERA5-Land 7-28 cm R ~ 0.69; dekadal events (ERA5 operational z, 1991-2020 clim) POD 0.574 FAR 0.571 n=312.
"""
import json

import numpy as np

import common as K
import config as C

e = K.era5()
ec = e.loc[C.COMMON[0]:C.COMMON[1]]
z_ins = K.z_common(K.ismn_ref())
res = {}
for name, s in (("ERA5_0_100", K.s4.rootzone(ec)), ("ERA5_7_28", ec["sm_l2"]), ("ERA5_0_7", ec["sm_l1"]),
                ("ERA5_28_100", ec["sm_l3"])):
    res[name] = K.r_ci(K.z_common(s), z_ins)
    print(f"{name:12s} R={res[name]['r']:.3f} [{res[name]['lo']:.3f},{res[name]['hi']:.3f}] n={res[name]['n']}")

ins_dk = K.to_dekad(z_ins)
for lab, z in (("oper_1991_2020", K.z_oper(K.s4.rootzone(e)).loc["2016-01-01":]),
               ("common_2016_2024", K.z_common(K.s4.rootzone(e)))):
    j = K.pair(K.to_dekad(z), ins_dk, names=["p", "o"])
    pf = K.pod_far((j["p"] <= C.THR).to_numpy(), (j["o"] <= C.THR).to_numpy())
    res[f"events_ERA5_0_100_{lab}"] = pf
    print(f"events ERA5 0-100 ({lab}): POD={pf['pod']:.3f} FAR={pf['far']:.3f} n={pf['n']} "
          f"(h={pf['hits']} m={pf['misses']} f={pf['false_alarms']})")

assert abs(res["ERA5_0_100"]["r"] - 0.583) < 0.001 and res["ERA5_0_100"]["n"] == 2976
assert abs(res["ERA5_0_100"]["lo"] - 0.50) < 0.005 and abs(res["ERA5_0_100"]["hi"] - 0.665) < 0.005
assert abs(res["events_ERA5_0_100_oper_1991_2020"]["pod"] - 0.574) < 0.001
assert abs(res["events_ERA5_0_100_oper_1991_2020"]["far"] - 0.571) < 0.001
print("baseline reproduced: OK")
json.dump(res, open(f"{K.OUT}/b0_baseline.json", "w"), indent=1, default=float)
