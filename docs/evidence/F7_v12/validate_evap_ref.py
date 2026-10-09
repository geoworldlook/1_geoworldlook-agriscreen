"""
Wzorzec step_07.validate_evap — test wstępnie zarejestrowany warstwy parowania vs ISMN Condom (protokół evap-prereg-1.0).
Wiersze w schemacie gwl_validation_metrics (jak validate_anomalies) + tabela epizodów + werdykt.
Nic tutaj nie wybiera metody na podstawie ISMN: okna, progi, sezon, schemat walidacji i kryteria są w EVAP_PROTOCOL.
"""
from __future__ import annotations

import hashlib
import json
import os
import sys
from typing import Any, Dict, List, Tuple

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import evap_v2 as E  # noqa: E402  (w repo: from step_04_metrics_alert import ...)

# ------------------------------------------------------------------------------
# PROTOKÓŁ (zamrożony przed pierwszym uruchomieniem; skrót SHA-256 trafia do każdego wiersza i do run_summary)
# ------------------------------------------------------------------------------
EVAP_PROTOCOL: Dict[str, Any] = {
    "version": "evap-prereg-1.0",
    "frozen": "2026-10-09",
    "period": ("2016-01-01", "2024-12-31"),
    "ref_test": ("1991-01-01", "2015-12-31"),          # klimatologia predyktorów: tylko lata przed ISMN (brak wycieku)
    "half_window": 15,
    "confirmatory": {"EDDI14": ("eddi", 14), "SESR14": ("sesr", 14)},   # EDDI = główny, SESR = zapasowy
    "exploratory": {"EDDI7": ("eddi", 7), "EDDI30": ("eddi", 30), "SESR7": ("sesr", 7), "SESR30": ("sesr", 30)},
    "season_primary": "IV-X",
    "seasons": {"all": (1, 12), "IV-X": (4, 10), "VII-X": (7, 10), "XI-III": (11, 3)},
    "cv_primary": "forward", "cv_secondary": "loyo", "min_train_years": 3,
    "boot_n": 2000, "boot_block": "30d", "boot_sensitivity": "year", "seed": 42,
    "placebo_n": 500,
    "onset_placebo_n": 200,
    "lead_h": 14, "lead_h_report": (7, 30),
    "ccf_lags": (-30, 60),
    "onset": {"thr": -1.0, "min_days": 14, "merge_gap": 5, "quiet": 30, "cover": 0.8, "months": (3, 10),
              "before": 60, "after": 30},
    "alpha": 0.05,
    "min_effect": {"H1": 0.02, "H2": 0.10, "H3": 0.02},
    "no_harm_drop": 0.02,                              # brak szkody: CI obejmuje 0 lub > 0 i spadek R <= 0,02
    "gate": {"r": 0.583, "tol": 0.005, "n": 2976},
}


def protocol_hash(p: Dict[str, Any] = EVAP_PROTOCOL) -> str:
    return hashlib.sha256(json.dumps(p, sort_keys=True, default=str).encode()).hexdigest()[:12]


def _season_mask(idx: pd.DatetimeIndex, months: Tuple[int, int]) -> np.ndarray:
    a, b = months
    m = idx.month
    return ((m >= a) & (m <= b)) if a <= b else ((m >= a) | (m <= b))


def validate_evap(era5: pd.DataFrame, ins_rz: pd.Series, ins_5: pd.DataFrame, lat: float, elev: float,
                  clim_anomaly, rootzone, site: str = "SMOSMANIA_Condom",
                  P: Dict[str, Any] = EVAP_PROTOCOL) -> Tuple[pd.DataFrame, pd.DataFrame, Dict[str, Any]]:
    """
    era5   : dzienna ramka ERA5-Land (indeks = dni) z kolumnami sm_l1..3, t2m_*, td2m_c, u10_ms, v10_ms, sp_kpa, ssrd_mj,
             et_mm (i opcjonalnie ssr_mj, str_mj, pev_mm),
    ins_rz : dzienna wilgotność ISMN 20-30 cm (średnia 20 i 30 cm), ins_5: ISMN 5 cm (kolumny sm, segment),
    clim_anomaly, rootzone: funkcje ze step_04 (wstrzyknięte, żeby wzorzec działał poza repo).
    """
    per, ref, hw = P["period"], P["ref_test"], P["half_window"]
    tag = f"{P['version']}#{protocol_hash(P)}"
    rows: List[Dict[str, Any]] = []

    def add(product, reference, kind, subset, metric, value, lo=np.nan, hi=np.nan, n=np.nan, extra=""):
        rows.append({"site_id": site, "product": product, "reference": reference, "segment": kind,
                     "period": f"{per[0][:4]}-{per[1][:4]}", "subset": subset, "metric": metric,
                     "value": value, "ci_low": lo, "ci_high": hi, "n": n, "date_from": per[0], "date_to": per[1],
                     "note": f"{tag}{(' ' + extra) if extra else ''}"})

    # --- Referencja (konwencja validate_anomalies: klimatologia wspólnego okresu, ±15 dni, min_n 20)
    y = clim_anomaly(ins_rz.loc[per[0]:per[1]], per, hw, min_n=20)["z"].rename("y")
    y5 = pd.concat([clim_anomaly(g["sm"], (str(g.index.min().date()), str(g.index.max().date())), hw, min_n=20)["z"]
                    for _, g in ins_5.groupby("segment")]).sort_index()
    y5 = y5[~y5.index.duplicated()].rename("y")

    # --- Brama 0: odtworzenie wyniku v1.0 tą samą ścieżką (ERA5 0-100 cm, klimatologia wspólnego okresu)
    era_c = clim_anomaly(rootzone(era5).loc[per[0]:per[1]], per, hw, min_n=20)["z"]
    g = pd.concat([era_c.rename("x"), y], axis=1).dropna()
    r_gate = float(np.corrcoef(g["x"], g["y"])[0, 1])
    gate_ok = abs(r_gate - P["gate"]["r"]) <= P["gate"]["tol"] and len(g) == P["gate"]["n"]
    add("ERA5L_SM_RZ", "ISMN_20_30cm", "evap_gate", "all", "pearson_r", r_gate, n=len(g),
        extra="OK" if gate_ok else "FAIL")

    # --- Predyktory (klimatologia REF_TEST = lata przed ISMN)
    l1, l2 = era5["sm_l1"], era5["sm_l2"]
    base = pd.DataFrame({
        "B_rz": clim_anomaly(rootzone(era5), ref, hw)["z"],
        "B_28": clim_anomaly((7 * l1 + 21 * l2) / 28.0, ref, hw)["z"],
        "B_l1": clim_anomaly(l1, ref, hw)["z"],
    })
    et0 = E.fao56_et0(era5, lat, elev)["et0_mm"]
    X: Dict[str, pd.Series] = {}
    for name, (kind, w) in {**P["confirmatory"], **P["exploratory"]}.items():
        if kind == "eddi":
            X[name] = E.eddi(et0, w, ref, hw)["z"]                 # z = -EDDI: <= -1 = sucho
        else:
            X[name] = E.sesr(era5["et_mm"], et0, w, ref, hw)["z"]
    q = P["onset"]
    res: Dict[str, Dict[str, Any]] = {}

    for name, x in X.items():
        conf = name in P["confirmatory"]
        r: Dict[str, Any] = {}
        d = pd.concat([y, base[["B_rz", "B_28"]], x.rename("x")], axis=1).loc[per[0]:per[1]].dropna()
        for scheme in (P["cv_primary"], P["cv_secondary"]):
            p0, p1 = E.fit_predict(d, ["B_rz"], scheme=scheme), E.fit_predict(d, ["B_rz", "x"], scheme=scheme)
            q0, q1 = E.fit_predict(d, ["B_rz", "B_28"], scheme=scheme), E.fit_predict(d, ["B_rz", "B_28", "x"], scheme=scheme)
            for sname, months in P["seasons"].items():
                m = _season_mask(d.index, months)
                for how in ((P["boot_block"], P["boot_sensitivity"]) if sname == P["season_primary"] else (P["boot_block"],)):
                    dr = E.paired_delta_r(p1[m], p0[m], d["y"][m], how, P["boot_n"], P["seed"])
                    seg = f"evap_dR_{scheme}" + ("" if how == P["boot_block"] else "_yearblk")
                    add(name, "ISMN_20_30cm", seg, sname, "delta_r", dr["delta"], dr["lo"], dr["hi"],
                        dr["n"], f"base=ERA5_RZ block={how} r1={dr['r_a']:.3f} r0={dr['r_b']:.3f} p={dr['p_le0']:.4f}")
                    if scheme == P["cv_primary"] and how == P["boot_block"]:
                        r[f"dR_{sname}"] = dr
                    if scheme == P["cv_primary"] and how == P["boot_sensitivity"]:
                        r[f"dR_{sname}_year"] = dr
                if scheme == P["cv_primary"]:
                    dq = E.paired_delta_r(q1[m], q0[m], d["y"][m], P["boot_block"], P["boot_n"], P["seed"])
                    add(name, "ISMN_20_30cm", f"evap_dR_{scheme}_depthctrl", sname, "delta_r", dq["delta"], dq["lo"],
                        dq["hi"], dq["n"], "base=ERA5_RZ+ERA5_0-28")
                    raw = E.paired_delta_r(p1[m], d["B_rz"][m], d["y"][m], P["boot_block"], P["boot_n"], P["seed"])
                    add(name, "ISMN_20_30cm", f"evap_dR_{scheme}_vs_raw", sname, "delta_r", raw["delta"], raw["lo"],
                        raw["hi"], raw["n"], "base=ERA5_RZ bez dopasowania")
        for sname, months in P["seasons"].items():
            dm = d[_season_mask(d.index, months)]
            for ctrl, lab in ((["B_rz"], "rz"), (["B_rz", "B_28"], "rz+0-28")):
                pr = E.partial_r_ci(dm, "x", ctrl, "y", P["boot_block"], P["boot_n"], P["seed"])
                add(name, "ISMN_20_30cm", f"evap_partial_{lab}", sname, "partial_r", pr["r"], pr["lo"], pr["hi"], pr["n"],
                    f"p={pr['p_le0']:.4f}")
                if lab == "rz+0-28":
                    r[f"pr_{sname}"] = pr
        m0 = P["seasons"][P["season_primary"]]
        if conf:
            pl = E.placebo_delta_r(d, ["B_rz"], "x", "y", P["cv_primary"], P["placebo_n"], P["seed"], m0)
            r["placebo_q95_H1"] = float(np.quantile(pl, 0.95))
            add(name, "ISMN_20_30cm", "evap_placebo_H1", P["season_primary"], "q95_delta_r", r["placebo_q95_H1"],
                n=P["placebo_n"])
        # wyprzedzanie (Granger): zmiana y w h dni ponad [y_t, ERA5 RZ_t, ERA5 0-28_t]
        for h in (P["lead_h"],) + tuple(P["lead_h_report"]):
            gl = E.granger_lead(y, base[["B_rz", "B_28"]], x, h, P["cv_primary"], P["boot_block"], P["boot_n"], m0)
            add(name, "ISMN_20_30cm", f"evap_lead_h{h}", P["season_primary"], "delta_r", gl["delta"], gl["lo"], gl["hi"],
                gl["n"], f"p={gl['p_le0']:.4f}")
            if h == P["lead_h"]:
                r["lead"] = gl
                if conf:
                    lf = E.lead_frame(y, base[["B_rz", "B_28"]], x, h)
                    pl = E.placebo_delta_r(lf, ["y0", "B_rz", "B_28"], "x", "dy", P["cv_primary"], P["placebo_n"],
                                           P["seed"], m0)
                    r["placebo_q95_H3"] = float(np.quantile(pl, 0.95))
                    add(name, "ISMN_20_30cm", "evap_placebo_H3", P["season_primary"], "q95_delta_r",
                        r["placebo_q95_H3"], n=P["placebo_n"])
        # korelacja krzyżowa (opisowo)
        lags = list(range(P["ccf_lags"][0], P["ccf_lags"][1] + 1))
        mask_y = y.where(_season_mask(y.index, m0))
        cp = E.ccf_peak_ci(x.loc[per[0]:per[1]], mask_y, lags, n_boot=300, seed=P["seed"])
        add(name, "ISMN_20_30cm", "evap_ccf_peak", P["season_primary"], "lag_days", cp["peak_lag"], cp["lo"], cp["hi"],
            extra=f"r_peak={cp['peak_r']:.3f}")
        # 5 cm: brak szkody (ERA5 0-7 cm + indeks vs ERA5 0-7 cm)
        d5 = pd.concat([y5, base[["B_l1"]], x.rename("x")], axis=1).loc[per[0]:per[1]].dropna()
        m5 = _season_mask(d5.index, m0)
        dr5 = E.paired_delta_r(E.fit_predict(d5, ["B_l1", "x"], scheme=P["cv_primary"])[m5],
                               E.fit_predict(d5, ["B_l1"], scheme=P["cv_primary"])[m5], d5["y"][m5],
                               P["boot_block"], P["boot_n"], P["seed"])
        add(name, "ISMN_5cm", f"evap_dR_{P['cv_primary']}", P["season_primary"], "delta_r", dr5["delta"], dr5["lo"],
            dr5["hi"], dr5["n"], "base=ERA5_L1")
        r["dR5"] = dr5
        res[name] = r

    # --- Epizody (b): progi nominalne i dopasowane częstością (bez par z ISMN)
    ons = E.onsets(y, q["thr"], q["min_days"], q["merge_gap"], q["quiet"], q["months"], q["cover"])
    rate = float((y[_season_mask(y.index, P["seasons"][P["season_primary"]])] <= q["thr"]).mean())
    preds = {"ERA5L_SM_RZ": base["B_rz"], "ERA5L_SM_0_28": base["B_28"], **{k: X[k] for k in P["confirmatory"]}}
    tabs, false_frac = [], {}
    for mode in ("nominal", "freq_matched"):
        thr = {k: (q["thr"] if mode == "nominal" else E.freq_matched_threshold(v, rate, P["seasons"][P["season_primary"]], per))
               for k, v in preds.items()}
        t = pd.concat([E.onset_leads({k: v}, ons, q["before"], q["after"], thr[k]).set_index("onset") for k, v in preds.items()],
                      axis=1) if ons else pd.DataFrame()
        if len(t):
            t["mode"] = mode
            tabs.append(t.reset_index())
        for k, v in preds.items():
            nf, nc = E.false_onsets(v.loc[per[0]:per[1]], y, thr[k], 60, 30, q["months"])
            false_frac[(mode, k)] = nf / nc if nc else np.nan
            add(k, "ISMN_20_30cm<=-1", f"evap_onset_{mode}", "III-X", "false_onset_frac", nf / nc if nc else np.nan,
                n=nc, extra=f"thr={thr[k]:.2f}")
            if len(t):
                add(k, "ISMN_20_30cm<=-1", f"evap_onset_{mode}", "III-X", "median_lead_days", float(t[k].median()),
                    n=len(t), extra=f"thr={thr[k]:.2f} hits={int((t[k + '_status'] == 'hit').sum())}")
    onset_tab = pd.concat(tabs, ignore_index=True) if tabs else pd.DataFrame()

    # --- Werdykt (Holm w rodzinie potwierdzającej: H1, H2, H3 x 2 indeksy)
    mf = P["min_effect"]
    pv = {}
    for name in P["confirmatory"]:
        r = res[name]
        pv[f"H1_{name}"] = r[f"dR_{P['season_primary']}"]["p_le0"]
        pv[f"H2_{name}"] = r[f"pr_{P['season_primary']}"]["p_le0"]
        pv[f"H3_{name}"] = r["lead"]["p_le0"]
    hol = E.holm(pv, P["alpha"])
    verdict: Dict[str, Any] = {"protocol": tag, "gate_ok": bool(gate_ok), "gate_r": r_gate, "n_onsets": len(ons),
                               "base_rate_IV-X": rate, "holm": hol, "p": pv, "indices": {}}
    for name in P["confirmatory"]:
        r = res[name]
        h1 = r[f"dR_{P['season_primary']}"]
        h1_ok = hol[f"H1_{name}"] and h1["delta"] >= mf["H1"] and h1["delta"] > r["placebo_q95_H1"]
        h2 = r[f"pr_{P['season_primary']}"]
        h2_ok = hol[f"H2_{name}"] and h2["r"] >= mf["H2"]
        h3 = r["lead"]
        h3_ok = hol[f"H3_{name}"] and h3["delta"] >= mf["H3"] and h3["delta"] > r["placebo_q95_H3"]
        # szkoda = istotnie gorzej (górna granica CI < 0) albo spadek R większy niż no_harm_drop
        harm = {s: (r[f"dR_{s}"]["delta"], r[f"dR_{s}"]["hi"]) for s in ("all", "XI-III")}
        harm["5cm"] = (r["dR5"]["delta"], r["dR5"]["hi"])
        no_harm = all(np.isfinite(dv) and hv >= 0 and dv >= -P["no_harm_drop"] for dv, hv in harm.values())
        fragile = not (r.get(f"dR_{P['season_primary']}_year", {}).get("lo", -1) > 0)
        if not gate_ok:
            decision = "BLOKADA: nie odtworzono wyniku bazowego (brama 0)"
        elif h1_ok and h2_ok and no_harm:
            decision = "PRZYJĘTY do prawdopodobieństwa suszy gleby (PSMA)"
        elif h1_ok and not h2_ok:
            decision = "ODRZUCONY: przyrost tylko względem 0-100 cm — artefakt głębokości (jak F4 B V10)"
        else:
            decision = "ODRZUCONY: brak przyrostu informacji — warstwa tylko informacyjna"
        # H4 (wspierające, opisowe; n epizodów ~6): progi dopasowane częstością, X wcześniej niż ERA5 0-100 I 0-28 cm
        h4 = {"n": 0, "earlier_both": 0, "median_adv_vs_0_28": np.nan, "ok": False}
        ft = onset_tab[onset_tab["mode"] == "freq_matched"] if len(onset_tab) else onset_tab
        if len(ft):
            adv28 = ft[name] - ft["ERA5L_SM_0_28"]
            both = (ft[name] > ft["ERA5L_SM_RZ"]) & (ft[name] > ft["ERA5L_SM_0_28"])
            ff_x, ff_28 = false_frac.get(("freq_matched", name)), false_frac.get(("freq_matched", "ERA5L_SM_0_28"))
            h4 = {"n": int(len(ft)), "earlier_both": int(both.sum()), "median_adv_vs_0_28": float(adv28.median()),
                  "false_x": ff_x, "false_0_28": ff_28}
            # placebo: ten sam indeks z przestawionych lat (n_perm 200) -> rozkład mediany przewagi nad 0-28 cm
            rng = np.random.default_rng(P["seed"])
            yrs = range(int(per[0][:4]), int(per[1][:4]) + 1)
            ref28 = ft.set_index("onset")["ERA5L_SM_0_28"]
            null = []
            for _ in range(P["onset_placebo_n"]):
                xp = E.year_permuted(X[name], yrs, rng)
                thp = E.freq_matched_threshold(xp, rate, P["seasons"][P["season_primary"]], per)
                lp = E.onset_leads({"x": xp}, ons, q["before"], q["after"], thp).set_index("onset")["x"]
                null.append(float((lp - ref28.reindex(lp.index)).median()))
            h4["placebo_q95_adv"] = float(np.nanquantile(null, 0.95))
            h4["ok"] = bool(len(ft) >= 6 and both.sum() >= np.ceil(5 / 6 * len(ft)) and adv28.median() >= 7
                            and adv28.median() > h4["placebo_q95_adv"]
                            and np.isfinite(ff_x) and ff_x <= (ff_28 or 0) + 0.15)
        verdict["indices"][name] = {"H1": h1_ok, "H2": h2_ok, "H3_lead": h3_ok, "H4_onset": h4, "no_harm": no_harm,
                                    "fragile_year_blocks": fragile, "harm_lo": harm, "decision": decision,
                                    "lead_text": bool(gate_ok and h3_ok and h4["ok"])}
        for hk, ok in (("H1", h1_ok), ("H2", h2_ok), ("H3", h3_ok), ("no_harm", no_harm)):
            add(name, "ISMN_20_30cm", "evap_verdict", P["season_primary"], hk, float(ok), extra=decision)
    a, b = list(P["confirmatory"])[:2]
    va, vb = verdict["indices"][a], verdict["indices"][b]
    chosen = None
    if va["decision"].startswith("PRZYJĘTY") and vb["decision"].startswith("PRZYJĘTY"):
        d = pd.concat([y, base[["B_rz"]], X[a].rename("xa"), X[b].rename("xb")], axis=1).loc[per[0]:per[1]].dropna()
        m = _season_mask(d.index, P["seasons"][P["season_primary"]])
        cmp_ = E.paired_delta_r(E.fit_predict(d, ["B_rz", "xb"])[m], E.fit_predict(d, ["B_rz", "xa"])[m], d["y"][m],
                                P["boot_block"], P["boot_n"], P["seed"])
        chosen = b if cmp_["lo"] > 0 else a
    elif va["decision"].startswith("PRZYJĘTY"):
        chosen = a
    elif vb["decision"].startswith("PRZYJĘTY"):
        chosen = b
    verdict["chosen_for_psma"] = chosen
    out = pd.DataFrame(rows)
    return out, onset_tab, verdict
