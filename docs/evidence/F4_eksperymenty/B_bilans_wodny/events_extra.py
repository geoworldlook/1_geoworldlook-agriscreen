"""Extra dekadal event table: growing-season subset (IV-X dekads) and the ERA5 0-28 cm diagnostic."""
import pandas as pd

import common as C

ser = pd.read_csv(f"{C.OUT}/series_daily_z.csv", index_col="date", parse_dates=True)
oper = pd.read_csv(f"{C.OUT}/series_daily_z_operational.csv", index_col="date", parse_dates=True)
e = C.era5()
era28 = (7 * e["sm_l1"] + 21 * e["sm_l2"]) / 28.0
oper["zoper_D_ERA5L_0-28cm"] = C.anom_oper(era28).loc["1991":]
ser["z_D_ERA5L_0-28cm"] = C.anom_common(era28)

ins_dk = C.dekad_mean(C.ins_z("rz"))
rows = []
for name in ["B0_ERA5L_RZ", "V1_WB_vine_SR", "V2_WB_vine_10m", "V3_WB_vine_clim", "V4_WB_station",
             "V5_WB_vine_SR_cvZr", "V6_SPEI30_like", "D_ERA5L_0-28cm"]:
    for refkind, z in (("operational_1991-2020", oper[f"zoper_{name}"].loc["2016":]), ("common_2016-2024", ser[f"z_{name}"])):
        dk = C.dekad_mean(z)
        for sub, sel in (("all", None), ("IV-X", (4, 10))):
            d, o = dk, ins_dk
            if sel:
                d = d[(d.index.month >= sel[0]) & (d.index.month <= sel[1])]
                o = o[(o.index.month >= sel[0]) & (o.index.month <= sel[1])]
            rows.append({"variant": name, "anomaly_ref": refkind, "subset": sub, **C.pod_far_ci(d, o)})
t = pd.DataFrame(rows)
t.to_csv(f"{C.OUT}/results_events_extra.csv", index=False)
pd.set_option("display.width", 220)
print(t.round(3).to_string(index=False))
