"""A1: choose Whittaker lambda per index by leave-one-observation-out CV on S-2 data only (no ISMN)."""
import logging
import numpy as np
import pandas as pd
from common import OUT, group
from smooth import loo_cv_lambda
logging.basicConfig(level=logging.WARNING)
lams = [10, 30, 100, 300, 1000, 3000, 10000]
rows = []
for site in ("VINEYARD_06", "SMOSMANIA_Condom_poly"):
    g = group(site, "S2SR_2.5m")
    for idx in ("ndvi", "ndmi", "ndre", "crswir"):
        cv = loo_cv_lambda(g, idx, lams)
        cv["site"], cv["index"] = site, idx
        rows.append(cv)
        best = cv.loc[cv["rmse"].idxmin()]
        print(site, idx, "best lam", best["lam"], "rmse", round(best["rmse"], 4), cv["rmse"].round(4).tolist())
pd.concat(rows).to_csv(f"{OUT}/a1_lambda_cv.csv", index=False)
