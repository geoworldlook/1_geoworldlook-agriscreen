"""
A4 — eksploracja czujników ISMN Condom przed ustaleniem reguł QC (Plan v7 A4, Plan v8 moduł 1).
Liczy wyłącznie opis danych referencyjnych (rozkłady, epizody, spójność profilu). NIE liczy metryk walidacji
produktu — te powstaną dopiero po zatwierdzeniu reguł (pre-rejestracja, docs/evidence/A4_QC_czujnikow_ISMN.md).
Uruchomienie z katalogu repozytorium:  python docs/evidence/A4_QC/a4_explore.py
"""
import glob
import os
import sys

import pandas as pd

REPO = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
sys.path.insert(0, REPO)
from step_07_station_pipeline import read_ismn_stm  # noqa: E402

D = os.path.join(REPO, "data/7_isismn_data/SMOSMANIA/Condom")


def wp_saxton_rawls(sand, clay, om_pct):
    """Wilgotność przy -1500 kPa (Saxton i Rawls 2006, równ. 1); sand, clay jako frakcje, OM w % wag."""
    t = -0.024 * sand + 0.487 * clay + 0.006 * om_pct + 0.005 * sand * om_pct - 0.013 * clay * om_pct \
        + 0.068 * sand * clay + 0.031
    return t + (0.14 * t - 0.02)


def hourly_g(depth_cm):
    """Godzinowe wartości z flagą ISMN „G” dla głębokości (oba czujniki 5 cm sklejone, nowszy wygrywa)."""
    parts = []
    for p in sorted(glob.glob(os.path.join(D, "*_sm_*.stm"))):
        s = read_ismn_stm(p)
        if int(round(s["depth_from"].iat[0] * 100)) == depth_cm:
            parts.append(s[s["flag"] == "G"]["sm"])
    h = pd.concat(parts).sort_index()
    return h[~h.index.duplicated(keep="last")].asfreq("h")


def main():
    sv = pd.read_csv(glob.glob(os.path.join(D, "*static_variables.csv"))[0], sep=";")
    ins = sv[sv["quantity_source_name"] == "insitu"]
    print("== Tekstura in situ i punkt więdnięcia (Saxton-Rawls 2006) ==")
    for d in (0.05, 0.10, 0.20, 0.30):
        q = ins[ins["depth_from[m]"] == d].set_index("quantity_name")["value"].astype(float)
        wp = wp_saxton_rawls(q["sand fraction"] / 100, q["clay fraction"] / 100, q["organic carbon"] * 1.724)
        print(f"{int(d * 100):>2} cm: ił {q['clay fraction']:.1f}%, piasek {q['sand fraction']:.1f}%, "
              f"OC {q['organic carbon']:.2f}% -> WP = {wp:.3f} m3/m3, 0,5·WP = {wp / 2:.3f}")

    h = {d: hourly_g(d) for d in (5, 10, 20, 30)}
    print("\n== Rozkład wartości godzinowych (flaga G) ==")
    for d, s in h.items():
        v = s.dropna()
        print(f"{d:>2} cm: n = {len(v)}, min {v.min():.3f}, p01 {v.quantile(.01):.3f}, p05 {v.quantile(.05):.3f}, "
              f"mediana {v.median():.3f}, maks {v.max():.3f}")

    day = pd.concat({f"d{d}": s.resample("D").mean() for d, s in h.items()}, axis=1)
    print("\n== Dni (średnia dobowa) poniżej progów, per rok: 20 cm / 30 cm ==")
    rows = []
    for y, g in day.groupby(day.index.year):
        r = {"rok": y}
        for d in (20, 30):
            x = g[f"d{d}"].dropna()
            r[f"min_{d}"] = round(x.min(), 3)
            for thr in (0.05, 0.10, 0.135):
                r[f"<{thr}_{d}"] = int((x < thr).sum())
        rows.append(r)
    print(pd.DataFrame(rows).set_index("rok").to_string())

    both = day.dropna(subset=["d20", "d30"])
    print(f"\nDni z obiema głębokościami 20 i 30 cm: {len(both)}")
    for thr in (0.10, 0.135, 0.15):
        f = (both["d20"] < thr) | (both["d30"] < thr)
        print(f"  próg {thr}: dni z 20 lub 30 cm poniżej progu: {int(f.sum())} ({100 * f.mean():.0f}%)")

    print("\n== Spójność profilu ==")
    o = day.loc["2016":"2020-11"].dropna(subset=["d10", "d20", "d30"])
    print(f"2016-2020 (10 cm działa): {len(o)} dni; minimum 10 cm {o.d10.min():.3f}, 20 cm {o.d20.min():.3f}, "
          f"30 cm {o.d30.min():.3f}; dni 20 cm < 10 cm - 0,10: {int((o.d20 < o.d10 - .10).sum())}, "
          f"30 cm < 10 cm - 0,10: {int((o.d30 < o.d10 - .10).sum())}")
    low = day[day["d20"] < 0.05]
    print(f"dni 20 cm < 0,05: {len(low)}; mediany tego dnia: 30 cm {low.d30.median():.3f}, 10 cm {low.d10.median():.3f}, "
          f"5 cm {low.d5.median():.3f}; odsetek dni z 20 cm < 5 cm: {(low.d20 < low.d5).mean():.2f}")

    print("\n== Nagłe zmiany (godzinowe) ==")
    for d in (20, 30):
        s = h[d]
        dd = s.diff()
        up = dd[dd >= 0.03]
        no5 = sum(1 for t in up.index
                  if (w := h[5].loc[t - pd.Timedelta(hours=48):t].dropna()).empty or w.max() - w.min() < 0.03)
        drop6 = (s.rolling(7, min_periods=2).max() - s) > 0.05
        print(f"{d} cm: wzrosty >= 0,03/h: {len(up)} (bez wzrostu 5 cm w 48 h: {no5}); maks. wzrost {dd.max():.3f}/h; "
              f"spadek > 0,05 w <= 6 h: {int(drop6.sum())} h w {drop6[drop6].index.normalize().nunique()} dniach")
    for d in (5, 10):
        s = h[d]
        drop6 = (s.rolling(7, min_periods=2).max() - s) > 0.05
        print(f"{d} cm (porównanie): spadek > 0,05 w <= 6 h: {drop6[drop6].index.normalize().nunique()} dni")


if __name__ == "__main__":
    main()
