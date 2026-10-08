"""A4c: threshold-free alert diagnostic: mean ISMN 20-30 cm dekadal z in alert dekads vs warning-only dekads
(in-season IV-X, 2016-2024). Negative difference = vegetation confirmation selects drier soil."""
import logging, warnings
import numpy as np
import pandas as pd
logging.basicConfig(level=logging.WARNING); warnings.filterwarnings("ignore")
import a4_alert as A

rows = []
for var in A.VARS:
    for months, tag in (((4, 10), "IV-X"), ((6, 9), "VI-IX")):
        st = A.status_for(A.ser[var].rename(var), months)
        j = st.join(A.ins_dk.rename("ins"), how="inner").dropna(subset=["ins"])
        j = j[(j.index <= "2024-12-31") & j.index.month.isin(range(4, 11)) & (j["cdi_level"] >= 2)]
        al, wo = j["cdi_level"] == 3, j["cdi_level"] == 2
        d = j.loc[al, "ins"].mean() - j.loc[wo, "ins"].mean()
        rng = np.random.default_rng(42); yrs = j.index.year.to_numpy(); uy = np.unique(yrs); bs = []
        for _ in range(2000):
            q = j.iloc[np.concatenate([np.flatnonzero(yrs == k) for k in rng.choice(uy, len(uy))])]
            a_, w_ = q.loc[q["cdi_level"] == 3, "ins"], q.loc[q["cdi_level"] == 2, "ins"]
            if len(a_) and len(w_):
                bs.append(a_.mean() - w_.mean())
        rows.append(dict(variant=var, veg_months=tag, n_alert=int(al.sum()), n_warn_only=int(wo.sum()),
                         ismn_z_alert=j.loc[al, "ins"].mean(), ismn_z_warn_only=j.loc[wo, "ins"].mean(),
                         diff=d, lo=np.percentile(bs, 2.5), hi=np.percentile(bs, 97.5)))
out = pd.DataFrame(rows)
out.to_csv(f"{A.OUT}/a4c_graded_alert.csv", index=False)
pd.set_option("display.width", 200)
print(out.round(3).to_string(index=False))
