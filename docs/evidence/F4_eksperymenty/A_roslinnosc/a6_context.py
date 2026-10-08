"""A6: context — the same key variants for the station grass plot (210 m2) and for VINEYARD_06 at 10 m."""
import logging, warnings
import pandas as pd
logging.basicConfig(level=logging.WARNING); warnings.filterwarnings("ignore")
from common import OUT, ins_z, r_ci, paired_diff_ci, pair
import variants as V

y, y10 = ins_z("rz"), ins_z("10")
rows = []
for site, prod in (("SMOSMANIA_Condom_poly", "S2SR_2.5m"), ("SMOSMANIA_Condom_poly", "S2_10m"),
                   ("VINEYARD_06", "S2_10m")):
    S = {"B0_ndvi": V.b0(site, prod), "V1a_whittaker": V.whit(site, prod),
         "V3a_ndmi": V.b0(site, prod, "ndmi"), "V6_harmonic": V.harmonic_loyo(site, prod)}
    if prod == "S2SR_2.5m":
        S["V3d_meanz"] = V.mean_z([S["B0_ndvi"], S["V3a_ndmi"], V.b0(site, prod, "crswir")])
    days = pair(S["B0_ndvi"], y).index
    for k, s in S.items():
        s = s[s.index.isin(days)]
        a, b, d = r_ci(s, y), r_ci(s, y10), paired_diff_ci(s, S["B0_ndvi"], y)
        rows.append(dict(site=site, product=prod, variant=k, n=a["n"], r_20_30=a["r"], lo=a["lo"], hi=a["hi"],
                         dR_vs_B0=d["d"], dR_lo=d["lo"], dR_hi=d["hi"], r_10cm=b["r"], lo10=b["lo"], hi10=b["hi"],
                         n_10cm=b["n"]))
out = pd.DataFrame(rows)
out.to_csv(f"{OUT}/a6_context.csv", index=False)
pd.set_option("display.width", 220)
print(out.round(3).to_string(index=False))
