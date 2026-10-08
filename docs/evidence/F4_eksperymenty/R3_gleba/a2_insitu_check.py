import warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
from common import insitu, ismn_rz, zclim, s7, era5, COMMON
d = {k: insitu(v) for k, v in (("5", 0.05), ("10", 0.10), ("20", 0.20), ("30", 0.30))}
for k, v in d.items():
    s = v["sm"]
    print(k, "n", len(s), "segments", v["segment"].value_counts().to_dict())
    print("   annual max/min:", s.groupby(s.index.year).agg(["max", "min", "count"]).round(3).T.to_dict())
z = pd.concat({k: zclim(v["sm"]) for k, v in d.items()}, axis=1)
print("clim-z corr\n", z.corr().round(3))
m = pd.concat({k: s7._moving_anomaly(v["sm"], 35, 15) for k, v in d.items()}, axis=1)
print("35d corr\n", m.corr().round(3))
e = era5().loc[COMMON[0]:COMMON[1]]
m2 = pd.concat({"e1": s7._moving_anomaly(e["sm_l1"], 35, 15), "e2": s7._moving_anomaly(e["sm_l2"], 35, 15), "e3": s7._moving_anomaly(e["sm_l3"], 35, 15)}, axis=1)
print(pd.concat([m, m2], axis=1).corr().round(3).loc[["5","10","20","30"], ["e1","e2","e3"]])
