"""
================================================================================
AgriWatch - KROK 10: STACJE REFERENCYJNE I WSPÓLNA WALIDACJA WARSTWY WODY (Plan v9 W2 + REF)
================================================================================
Protokół (zarejestrowany przed liczeniem, D-083): docs/evidence/W2_REF_protokol_walidacji.md
Stacje (D-082): docs/evidence/REF_obszar_pomocniczy_ICOS.md

  1. ICOS      : wyszukanie najnowszych plików stacji (SPARQL), pobranie po akceptacji licencji (CC BY 4.0),
                 wilgotność gleby co pół godziny na poziomach SWC_n (średnia profili, % -> m3/m3).
  2. QC        : zakres 0–0,60, FAST_DROP z A4 (spadek > 0,05 m3/m3 w <= 6 h -> dzień usunięty), dzień = średnia
                 z >= 24 z 48 półgodzin. LOW_IMPLAUSIBLE nie stosujemy (próg zależny od gleby Condom).
  3. Warstwa   : FR-Lus — średnia 0,20 i 0,30 m; FR-Aur — 0,30 m; wrażliwość: 0–1 m ważone grubością warstw.
  4. Walidacja : validate_layer — ta sama funkcja dla Condom (ISMN po A4) i stacji ICOS: R i ρ anomalii
                 klimatologicznych i 35-dniowych z CI z bootstrapu blokowego, zgodność klas i kappa, POD/FAR
                 suchych dekad. Bez dostrajania czegokolwiek pod stację.
  5. Bieżąco   : monitor_current — klasa ERA5 i SWI wobec znaku anomalii 35-dniowej czujnika (protokół §6).

Dane satelitarne tylko Copernicus (D-048); dane naziemne z sieci ICOS i ISMN.
================================================================================
"""

from __future__ import annotations

import io
import logging
import os
import zipfile
from typing import Any, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger("AgriWatch_REF")

ICOS_SPARQL = "https://meta.icos-cp.eu/sparql"
ICOS_OBJECTS = "https://data.icos-cp.eu/objects/"
ICOS_STATION = "http://meta.icos-cp.eu/resources/stations/ES_{}"

# Stacje z protokołu §1; głębokości poziomów z plików VARINFO_METEO w archiwach ICOS (odczyt 2026-10-15)
REF_SITES: Dict[str, Dict[str, Any]] = {
    "FR-Aur": {"name": "Auradé (Gers)", "lat": 43.54965, "lon": 1.106103, "specs": ("ETC L2 Meteo",),
               "depths": {1: 0.05, 2: 0.10, 3: 0.30, 4: 0.50, 5: 1.00}, "layer": (3,), "layer_label": "30cm",
               "period": ("2019-01-01", "2025-12-31"), "main": "anomaly_clim", "sens_from": "2020-10-19",
               "fetch_from": "2018-11-01"},
    "FR-Lus": {"name": "Lusignan", "lat": 46.414246, "lon": 0.1206518, "specs": ("ETC L2 Meteo", "ETC NRT Meteo"),
               "depths": {1: 0.05, 2: 0.10, 3: 0.20, 4: 0.30, 5: 0.60, 6: 1.00}, "layer": (3, 4),
               "layer_label": "20_30cm", "period": ("2023-01-01", None), "main": "anomaly_35d", "sens_from": None,
               "fetch_from": "2007-01-01"},   # od 2007: klasa bieżąca ERA5 i SWI wobec normy 2007–2024 (§6)
}
REF_QC = {"range": (0.0, 0.60), "fast_drop": 0.05, "fast_drop_hours": 6, "min_halfhours": 24}


# ------------------------------------------------------------------------------
# 1. ICOS: wyszukiwanie i pobieranie
# ------------------------------------------------------------------------------

def icos_latest_objects(station: str, specs: Tuple[str, ...], session: Any = None) -> List[Dict[str, Any]]:
    """Najnowszy (niezastąpiony) plik każdej specyfikacji danej stacji: id, nazwa, początek i koniec okresu."""
    import requests
    s = session or requests
    out = []
    for spec in specs:
        q = f"""prefix cpmeta: <http://meta.icos-cp.eu/ontologies/cpmeta/>
prefix prov: <http://www.w3.org/ns/prov#>
select ?d ?fn ?start ?end where {{
  ?d cpmeta:hasObjectSpec ?sp ; cpmeta:wasAcquiredBy ?a ; cpmeta:hasName ?fn . ?sp rdfs:label "{spec}" .
  ?a prov:wasAssociatedWith <{ICOS_STATION.format(station)}> ; prov:startedAtTime ?start ; prov:endedAtTime ?end .
  filter not exists {{ [] cpmeta:isNextVersionOf ?d }}
}} order by desc(?end) limit 1"""
        r = s.post(ICOS_SPARQL, data={"query": q}, headers={"Accept": "application/json"}, timeout=120)
        if r.status_code != 200:
            raise RuntimeError(f"ICOS SPARQL: HTTP {r.status_code}")
        b = r.json()["results"]["bindings"]
        if b:
            out.append({"spec": spec, "id": b[0]["d"]["value"].rsplit("/", 1)[-1], "name": b[0]["fn"]["value"],
                        "start": b[0]["start"]["value"][:10], "end": b[0]["end"]["value"][:10]})
    return out


def icos_download(obj: Dict[str, Any], cache_dir: str, session: Any = None) -> str:
    """Plik CSV z obiektu ICOS (zip po akceptacji licencji CC BY 4.0), z cache po identyfikatorze obiektu."""
    import requests
    s = session or requests
    os.makedirs(cache_dir, exist_ok=True)
    path = os.path.join(cache_dir, f"{obj['id']}.csv")
    if os.path.exists(path):
        return path
    r = s.get(ICOS_OBJECTS + obj["id"], cookies={"CpLicenseAcceptedFor": obj["id"]}, timeout=600)
    if r.status_code != 200 or not r.content[:2] == b"PK":
        raise RuntimeError(f"ICOS: pobranie {obj['name']} nieudane (HTTP {r.status_code})")
    with zipfile.ZipFile(io.BytesIO(r.content)) as z:
        member = [n for n in z.namelist() if n.lower().endswith(".csv")][0]
        with open(path, "wb") as f:
            f.write(z.read(member))
    return path


def icos_read_swc(csv_path: str, levels: Tuple[int, ...]) -> pd.DataFrame:
    """Półgodzinna wilgotność gleby poziomów SWC_n (średnia profili) w m3/m3; indeks = środek półgodziny
    (koniec − 15 min), żeby półgodzina 23:30–00:00 należała do swojego dnia."""
    cols = pd.read_csv(csv_path, nrows=0).columns
    use = [f"SWC_{n}" for n in levels if f"SWC_{n}" in cols]
    df = pd.read_csv(csv_path, usecols=["TIMESTAMP_END"] + use, na_values=[-9999, "-9999"])
    df.index = (pd.to_datetime(df.pop("TIMESTAMP_END").astype(str), format="%Y%m%d%H%M")
                - pd.Timedelta(minutes=15))
    return (df / 100.0).sort_index()


# ------------------------------------------------------------------------------
# 2–3. QC, średnie dobowe, warstwa referencyjna
# ------------------------------------------------------------------------------

def icos_daily(hh: pd.DataFrame, qc: Dict[str, Any] = REF_QC) -> Tuple[pd.DataFrame, Dict[str, Dict[str, int]]]:
    """Średnie dobowe poziomów po QC (protokół §2) i liczby oznaczeń per poziom."""
    from step_07_station_pipeline import fast_drop_days
    lo, hi = qc["range"]
    out, rep = {}, {}
    for c in hh.columns:
        s = hh[c]
        bad = s.notna() & ((s < lo) | (s > hi))
        s = s.mask(bad)
        fast = fast_drop_days(s, "30min", int(qc["fast_drop_hours"]), float(qc["fast_drop"]))
        g = s.groupby(s.index.floor("D"))
        d = g.mean().where(g.count() >= int(qc["min_halfhours"]))
        d[d.index.isin(fast)] = np.nan
        out[c] = d
        rep[c] = {"out_of_range_halfhours": int(bad.sum()), "fast_drop_days": int(len(fast)),
                  "days_ok": int(d.notna().sum())}
    daily = pd.DataFrame(out)
    daily.index.name = "date"
    return daily, rep


def layer_series(daily: pd.DataFrame, levels: Tuple[int, ...]) -> pd.Series:
    """Warstwa referencyjna: średnia wskazanych poziomów w dniach, gdy są wszystkie (jak 20–30 cm w Condom)."""
    cols = [f"SWC_{n}" for n in levels]
    if not set(cols) <= set(daily.columns):
        return pd.Series(dtype=float)
    return daily[cols].dropna().mean(axis=1)


def profile_weights(depths: Dict[int, float], bottom: float = 1.0) -> Dict[int, float]:
    """Wagi poziomów w warstwie 0–bottom: grubość od połowy odstępu do sąsiada wyżej do połowy odstępu do sąsiada niżej."""
    lv = sorted(depths, key=lambda n: depths[n])
    z = [depths[n] for n in lv]
    edges = [0.0] + [(a + b) / 2 for a, b in zip(z[:-1], z[1:])] + [bottom]
    return {n: max(0.0, min(edges[i + 1], bottom) - edges[i]) for i, n in enumerate(lv)}


def profile_series(daily: pd.DataFrame, depths: Dict[int, float]) -> pd.Series:
    """Wrażliwość: warstwa 0–1 m ważona grubością warstw; tylko dni ze wszystkimi poziomami."""
    w = profile_weights(depths)
    cols = [f"SWC_{n}" for n in w]
    if not set(cols) <= set(daily.columns):
        return pd.Series(dtype=float)
    d = daily[cols].dropna()
    return (d * np.array([w[n] for n in w])).sum(axis=1) / sum(w.values())


# ------------------------------------------------------------------------------
# 4. Wspólna walidacja (protokół §4)
# ------------------------------------------------------------------------------

def _spearman(a: np.ndarray, b: np.ndarray) -> float:
    return float(np.corrcoef(pd.Series(a).rank().to_numpy(), pd.Series(b).rank().to_numpy())[0, 1])


def _pct_class(p: pd.Series, dry: float = 30.0, wet: float = 70.0) -> pd.Series:
    return pd.Series(np.where(p <= dry, "dry", np.where(p >= wet, "wet", "normal")), index=p.index).where(p.notna())


def validate_layer(ref: pd.Series, products: Dict[str, Tuple[pd.Series, str]], period: Tuple[str, str],
                   site_id: str, reference: str, s7cfg: Dict[str, Any], half_window: int = 15,
                   thr_z: float = -1.0, segment_suffix: str = "") -> pd.DataFrame:
    """
    Metryki jednej warstwy referencyjnej wobec produktów {nazwa: (seria dzienna, opis piksela)} w okresie `period`
    (protokół §4): R i ρ anomalii klimatologicznych (z wobec okresu, okno ±half_window, >= 20 w puli) i 35-dniowych
    z CI z bootstrapu blokowego; zgodność klas (≤ 30 / ≥ 70 percentyla) i kappa z CI po latach; POD/FAR dekad z ≤ −1.
    Wiersze w schemacie gwl_validation_metrics (bez run_id).
    """
    from step_04_metrics_alert import clim_anomaly, dekad_end
    from step_07_station_pipeline import _block_bootstrap_ci, _moving_anomaly, _r_with_ci
    from step_09_panels import swi_agreement

    p0, p1 = period
    ref = ref.dropna().sort_index().loc[p0:p1]
    rows: List[Dict[str, Any]] = []
    if len(ref) < 30:
        return pd.DataFrame(rows)
    per = (str(ref.index.min().date()), str(ref.index.max().date()))
    win = int(s7cfg["ANOMALY_WINDOW_DAYS"])

    def add(product, footprint, seg, metric, value, lo=np.nan, hi=np.nan, n=0, d0=None, d1=None):
        rows.append({"site_id": site_id, "product": product, "reference": reference, "segment": seg + segment_suffix,
                     "period": f"{per[0][:4]}-{per[1][:4]}", "subset": footprint, "metric": metric, "value": value,
                     "ci_low": lo, "ci_high": hi, "n": int(n),
                     "date_from": str(d0.date()) if d0 is not None else None,
                     "date_to": str(d1.date()) if d1 is not None else None})

    ref_clim = clim_anomaly(ref, per, half_window, min_n=20)
    ref_35 = _moving_anomaly(ref, win, 15)
    for name, (prod, foot) in products.items():
        prod = prod.dropna().sort_index()
        prod = prod[~prod.index.duplicated(keep="last")]
        if prod.empty:
            continue
        pc = clim_anomaly(prod.loc[:per[1]], per, half_window, min_n=20)
        for seg, x_s, y_s in (("anomaly_clim", pc["z"], ref_clim["z"]),
                              ("anomaly_35d", _moving_anomaly(prod, win, 15), ref_35)):
            p = pd.concat([x_s.rename("x"), y_s.rename("y")], axis=1).loc[per[0]:per[1]].dropna()
            t = pd.Series(p.index)
            r, lo, hi = _r_with_ci(t, p["x"].to_numpy(), p["y"].to_numpy(), s7cfg)
            add(name, foot, seg, "pearson_r", r, lo, hi, len(p), p.index.min() if len(p) else None,
                p.index.max() if len(p) else None)
            if len(p) >= s7cfg["MIN_N_METRICS"]:
                rho = _spearman(p["x"].to_numpy(), p["y"].to_numpy())
                lo, hi = _block_bootstrap_ci(t.reset_index(drop=True), p["x"].to_numpy(), p["y"].to_numpy(),
                                             _spearman, s7cfg)
                add(name, foot, seg, "spearman_rho", rho, lo, hi, len(p), p.index.min(), p.index.max())
        # zgodność klas (percentyle obu serii wobec tego samego okresu) i kappa z CI po latach
        ag = swi_agreement(ref_clim["percentile"], pc["percentile"], {"SWI_NORM": per})
        if ag["n_days"]:
            add(name, foot, "class_agreement", "agreement", ag["po"], *ag["po_ci"], ag["n_days"])
            add(name, foot, "class_agreement", "kappa", ag["kappa"], *ag["kappa_ci"], ag["n_days"])
        # suche dekady: średnia dekadowa z ≤ thr_z w referencji i w produkcie
        zz = pd.concat([pc["z"].rename("x"), ref_clim["z"].rename("y")], axis=1).loc[per[0]:per[1]].dropna()
        if len(zz):
            dk = zz.groupby(dekad_end(pd.Series(zz.index)).to_numpy()).mean()
            obs, prd = dk["y"] <= thr_z, dk["x"] <= thr_z
            hits, miss, fa = int((obs & prd).sum()), int((obs & ~prd).sum()), int((~obs & prd).sum())
            add(name, foot, "events_dekad", "pod", hits / (hits + miss) if hits + miss else np.nan, n=len(dk))
            add(name, foot, "events_dekad", "far", fa / (hits + fa) if hits + fa else np.nan, n=len(dk))
    return pd.DataFrame(rows)


# ------------------------------------------------------------------------------
# 5. Kontrola bieżąca (protokół §6) i przebieg dla stacji ICOS
# ------------------------------------------------------------------------------

def monitor_current(ref: pd.Series, products: Dict[str, Tuple[pd.Series, str]], norm: Tuple[str, str],
                    s7cfg: Dict[str, Any], half_window: int = 15) -> Dict[str, Any]:
    """Ostatni dzień z danymi czujnika: znak anomalii 35-dniowej czujnika i klasy produktów (percentyl wobec `norm`)."""
    from step_04_metrics_alert import clim_anomaly
    from step_07_station_pipeline import _moving_anomaly
    a = _moving_anomaly(ref.dropna(), int(s7cfg["ANOMALY_WINDOW_DAYS"]), 15).dropna()
    if a.empty:
        return {}
    t = a.index.max()
    out = {"date": str(t.date()), "sensor_anomaly_35d": float(a.iat[-1]), "products": {}}
    for name, (prod, _) in products.items():
        pc = clim_anomaly(prod.dropna().sort_index(), norm, half_window)["percentile"].dropna()
        if t in pc.index:
            cl = _pct_class(pc.loc[[t]]).iat[0]
            out["products"][name] = {"percentile": float(pc.loc[t]), "class": cl}
    return out


def ingest_icos_site(site: str, cache_dir: str, session: Any = None) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Dzienne poziomy stacji z najnowszych plików L2 (+ NRT po końcu L2), po QC; raport plików i oznaczeń."""
    sc = REF_SITES[site]
    objs = icos_latest_objects(site, sc["specs"], session=session)
    frames, l2_end = [], None
    for o in sorted(objs, key=lambda o: o["spec"] != "ETC L2 Meteo"):     # najpierw L2, potem NRT
        hh = icos_read_swc(icos_download(o, cache_dir, session=session), tuple(sc["depths"]))
        if o["spec"] == "ETC L2 Meteo":
            l2_end = hh.index.max()
        elif l2_end is not None:
            hh = hh[hh.index > l2_end]
        frames.append(hh)
    hh = pd.concat(frames).sort_index() if frames else pd.DataFrame()
    hh = hh[~hh.index.duplicated(keep="first")]
    daily, rep = icos_daily(hh) if len(hh) else (pd.DataFrame(), {})
    keep = {o["id"] for o in objs}
    for f in os.listdir(cache_dir) if os.path.isdir(cache_dir) else []:   # starsze wersje plików są zbędne
        if f.endswith(".csv") and f[:-4] not in keep:
            os.remove(os.path.join(cache_dir, f))
    nrt_days = int(daily.index.to_series().gt(l2_end.normalize()).sum()) if l2_end is not None and len(daily) else 0
    return daily, {"objects": objs, "qc": rep, "nrt_days": nrt_days,
                   "first": str(daily.index.min().date()) if len(daily) else None,
                   "last": str(daily.index.max().date()) if len(daily) else None}


def validate_icos_site(site: str, daily: pd.DataFrame, era5: pd.DataFrame, swi: Optional[pd.DataFrame],
                       cfg: Dict[str, Any], s7cfg: Dict[str, Any]) -> Tuple[pd.DataFrame, Dict[str, Any]]:
    """Protokół §4–§6 dla stacji ICOS: warstwa główna, wrażliwość 0–1 m (i okres od zmiany czujnika), kontrola bieżąca."""
    from step_04_metrics_alert import rootzone
    sc = REF_SITES[site]
    e = era5.set_index(pd.to_datetime(era5["time"]).dt.floor("D")).sort_index()
    e = e[~e.index.duplicated(keep="last")]
    products = {"ERA5L_SM_RZ": (rootzone(e), "ERA5 cell")}
    if swi is not None and len(swi):
        sw = swi.set_index(pd.to_datetime(swi["date"]).dt.floor("D")).sort_index()
        for t in (int(cfg["SWI_T"]),) + tuple(int(x) for x in cfg.get("SWI_T_SENS", ())):
            if f"swi{t:03d}" in sw:
                products[f"SWI_v4_T{t:03d}"] = (sw[f"swi{t:03d}"].astype(float), "SWI 0.1° cell")
    p0, p1 = sc["period"]
    p1 = p1 or str(daily.index.max().date())
    hw = int(cfg["CLIM_HALF_WINDOW_DAYS"])
    main = layer_series(daily, sc["layer"])
    val = [validate_layer(main, products, (p0, p1), site, f"ICOS_{site}_{sc['layer_label']}", s7cfg, hw)]
    val.append(validate_layer(profile_series(daily, sc["depths"]), products, (p0, p1), site, f"ICOS_{site}_0_100cm",
                              s7cfg, hw))
    if sc.get("sens_from"):
        val.append(validate_layer(main, products, (sc["sens_from"], p1), site, f"ICOS_{site}_{sc['layer_label']}",
                                  s7cfg, hw, segment_suffix=f"_from_{sc['sens_from']}"))
    # kontrola bieżąca (protokół §6) tylko na stacji z danymi bieżącymi (NRT)
    cur = monitor_current(main, products, tuple(cfg["SWI_NORM"]), s7cfg, hw) if "ETC NRT Meteo" in sc["specs"] else {}
    return pd.concat([v for v in val if len(v)], ignore_index=True) if any(len(v) for v in val) else pd.DataFrame(), cur


# ------------------------------------------------------------------------------
# 6. Raport (run_summary.md)
# ------------------------------------------------------------------------------

MAIN_SEGMENT = {"SMOSMANIA_Condom": "anomaly_clim", **{k: v["main"] for k, v in REF_SITES.items()}}


def ref_summary_md(val: pd.DataFrame, qc: Optional[pd.DataFrame] = None, cur: Optional[Dict[str, Any]] = None,
                   a4: Optional[pd.DataFrame] = None) -> str:
    """Sekcja raportu W2 + REF: miara główna każdego miejsca (R i ρ z CI), zgodność klas, POD/FAR; QC; kontrola bieżąca."""
    def f(x, nd=2):
        return "" if x is None or not np.isfinite(float(x)) else f"{float(x):.{nd}f}"

    lines = ["Protokół: `docs/evidence/W2_REF_protokol_walidacji.md` (D-083). Miara główna: Condom i FR-Aur — anomalie "
             "klimatologiczne, FR-Lus — anomalie 35-dniowe. Bez dostrajania pod stacje.", ""]
    if val is not None and len(val):
        lines += ["| miejsce | referencja | produkt | segment | R [CI] | ρ [CI] | n | zgodność klas | kappa | POD | FAR |",
                  "|---|---|---|---|---|---|---|---|---|---|---|"]
        site_rank = {"SMOSMANIA_Condom": 0, **{k: i + 1 for i, k in enumerate(REF_SITES)}}

        def ref_rank(ref):      # warstwa główna przed wrażliwością
            return (1 if ref.endswith(("0_100cm", "_05WP", "_015")) else 0, 0 if ref.endswith("A4W1") else 1, ref)

        def prod_rank(p):
            return ({"ERA5L_SM_RZ": 0, "SWI_v4_T015": 1}.get(p, 2), p)
        keys = sorted(val.groupby(["site_id", "reference", "product"]).groups,
                      key=lambda k: (site_rank.get(k[0], 9), ref_rank(k[1]), prod_rank(k[2])))
        groups = val.groupby(["site_id", "reference", "product"])
        for site, ref, prod in keys:
            g = groups.get_group((site, ref, prod))
            seg = MAIN_SEGMENT.get(site, "anomaly_clim")
            gi = g.set_index(["segment", "metric"])

            def pick(sg, m):
                return gi.loc[(sg, m)] if (sg, m) in gi.index else None
            r, rho = pick(seg, "pearson_r"), pick(seg, "spearman_rho")
            ag, ka = pick("class_agreement", "agreement"), pick("class_agreement", "kappa")
            pod, far = pick("events_dekad", "pod"), pick("events_dekad", "far")
            if r is None:
                continue
            lines.append(f"| {site} | {ref} | {prod} | {seg} | {f(r['value'])} [{f(r['ci_low'])}; {f(r['ci_high'])}] | "
                         + (f"{f(rho['value'])} [{f(rho['ci_low'])}; {f(rho['ci_high'])}]" if rho is not None else "")
                         + f" | {int(r['n'])} | " + (f"{100 * float(ag['value']):.0f}%" if ag is not None else "")
                         + f" | {f(ka['value']) if ka is not None else ''} | {f(pod['value']) if pod is not None else ''}"
                         + f" | {f(far['value']) if far is not None else ''} |")
    else:
        lines.append("(brak wyników)")
    if a4 is not None and len(a4):
        t = a4.groupby("depth_cm")[["days", "fast_drop", "low_010", "low_05wp", "low_015"]].sum()
        lines += ["", "A4 (Condom, dni oznaczone 2016–2024): " + "; ".join(
            f"{d} cm: {int(r.days)} dni, FAST_DROP {int(r.fast_drop)}, < 0,10: {int(r.low_010)}, < 0,5·WP: "
            f"{int(r.low_05wp)}, < 0,15: {int(r.low_015)}" for d, r in t.iterrows())]
    if qc is not None and len(qc):
        lines += ["", "QC stacji ICOS: " + "; ".join(
            f"{r.site} {r.level}: {int(r.days_ok)} dni, FAST_DROP {int(r.fast_drop_days)}, poza zakresem "
            f"{int(r.out_of_range_halfhours)} półgodzin" for r in qc.itertuples())]
    for site, c in (cur or {}).items():
        if c and c.get("products"):
            sign = "sucho" if c["sensor_anomaly_35d"] < 0 else "wilgotno"
            cl = {"dry": "sucho", "normal": "w normie", "wet": "wilgotno"}
            pr = ", ".join(f"{k}: {cl.get(v['class'], v['class'])} (percentyl {v['percentile']:.0f} wobec normy "
                           f"2007–2024)" for k, v in c["products"].items())
            lines += ["", f"Kontrola bieżąca {site} ({c['date']}, protokół §6): czujnik — anomalia 35-dniowa "
                          f"{c['sensor_anomaly_35d']:+.3f} m³/m³ ({sign} wobec ostatnich tygodni); {pr}."]
    return "\n".join(lines)


# ------------------------------------------------------------------------------
# Test bez sieci: udawany portal ICOS, syntetyczne dane
# ------------------------------------------------------------------------------

def _selftest() -> None:
    """ICOS: wyszukiwanie i pobieranie (atrapa), QC (zakres, FAST_DROP, kompletność dnia), warstwa i wagi profilu,
    sklejenie L2 + NRT; validate_layer na syntetycznych seriach (zależność znana z góry)."""
    import tempfile
    from step_07_station_pipeline import build_config

    t = pd.date_range("2023-01-01 00:30", "2023-03-31 23:30", freq="30min")
    rng = np.random.default_rng(3)
    base = 30 + 5 * np.sin(np.arange(len(t)) / 500.0)
    hh = pd.DataFrame({f"SWC_{n}": base + n + rng.normal(0, 0.1, len(t)) for n in (1, 2, 3, 4, 5, 6)}, index=t)
    hh.loc["2023-02-10 12:00":"2023-02-10 13:00", "SWC_3"] = 20.0       # spadek 0,10 m3/m3 w 1 h -> FAST_DROP
    hh.loc["2023-03-05", "SWC_4"] = 75.0                                  # poza zakresem
    hh.loc["2023-03-20 00:00":"2023-03-20 15:00", "SWC_2"] = np.nan      # < 24 półgodzin w dniu

    def csv_bytes(df, start):
        d = df.loc[start:].copy()
        d.insert(0, "TIMESTAMP_START", (d.index - pd.Timedelta(minutes=30)).strftime("%Y%m%d%H%M"))
        d.insert(1, "TIMESTAMP_END", d.index.strftime("%Y%m%d%H%M"))
        b = io.BytesIO()
        with zipfile.ZipFile(b, "w") as z:
            z.writestr("data.csv", d.fillna(-9999).to_csv(index=False))
        return b.getvalue()

    l2 = csv_bytes(hh.loc[:"2023-03-15 00:00"], "2023-01-01")
    nrt = csv_bytes(hh, "2023-03-10")                                       # nakłada się z L2 — NRT tylko po końcu L2

    class R:
        def __init__(self, code, js=None, content=b""):
            self.status_code, self._js, self.content = code, js, content

        def json(self):
            return self._js

    class Portal:
        def post(self, url, data=None, headers=None, timeout=None):
            spec = "ETC NRT Meteo" if "ETC NRT Meteo" in data["query"] else "ETC L2 Meteo"
            oid = "NRT1" if spec == "ETC NRT Meteo" else "L2A"
            b = {"d": {"value": f"https://meta.icos-cp.eu/objects/{oid}"}, "fn": {"value": f"{spec}.zip"},
                 "start": {"value": "2023-01-01T00:00:00Z"}, "end": {"value": "2023-03-31T00:00:00Z"}}
            return R(200, {"results": {"bindings": [b]}})

        def get(self, url, cookies=None, timeout=None):
            oid = url.rsplit("/", 1)[-1]
            assert cookies == {"CpLicenseAcceptedFor": oid}
            return R(200, content=l2 if oid == "L2A" else nrt)

    with tempfile.TemporaryDirectory() as d:
        open(os.path.join(d, "STARY.csv"), "w").close()
        daily, info = ingest_icos_site("FR-Lus", d, session=Portal())
        assert not os.path.exists(os.path.join(d, "STARY.csv")) and info["nrt_days"] == 17, info
        assert np.isnan(daily.loc["2023-02-10", "SWC_3"]) and info["qc"]["SWC_3"]["fast_drop_days"] == 1, info["qc"]
        assert np.isnan(daily.loc["2023-03-05", "SWC_4"]) and info["qc"]["SWC_4"]["out_of_range_halfhours"] == 48
        assert np.isnan(daily.loc["2023-03-20", "SWC_2"]) and daily.index.max() == pd.Timestamp("2023-03-31")
        assert abs(daily.loc["2023-01-15", "SWC_3"] - (hh.loc["2023-01-15 00:30":"2023-01-16 00:00", "SWC_3"].mean()
                                                      / 100)) < 0.002
    w = profile_weights(REF_SITES["FR-Lus"]["depths"])
    assert abs(sum(w.values()) - 1.0) < 1e-12 and abs(w[1] - 0.075) < 1e-12 and abs(w[6] - 0.2) < 1e-12, w
    lay = layer_series(pd.DataFrame({"SWC_3": [0.2, 0.3, np.nan], "SWC_4": [0.4, np.nan, 0.1]}), (3, 4))
    assert list(lay.round(3)) == [0.3], lay

    # validate_layer: produkt = referencja + szum -> wysokie R i zgodność klas, POD/FAR policzone
    days = pd.date_range("2016-01-01", "2024-12-31", freq="D")
    doy = days.dayofyear.to_numpy()
    ar = np.zeros(len(days))
    for i in range(1, len(days)):
        ar[i] = 0.97 * ar[i - 1] + rng.normal(0, 0.01)
    refs = pd.Series(0.30 + 0.05 * np.cos(2 * np.pi * doy / 365.25) + ar, index=days)
    prod = refs + rng.normal(0, 0.005, len(days))
    noise = pd.Series(rng.normal(0.3, 0.05, len(days)), index=days)
    s7 = build_config({"BOOTSTRAP_N": 200})
    v = validate_layer(refs, {"GOOD": (prod, "cell"), "NOISE": (noise, "cell")}, ("2016-01-01", "2024-12-31"),
                       "X", "REF_X", s7)
    g = v.set_index(["product", "segment", "metric"])["value"]
    assert g[("GOOD", "anomaly_clim", "pearson_r")] > 0.8 and abs(g[("NOISE", "anomaly_clim", "pearson_r")]) < 0.15, g
    assert g[("GOOD", "class_agreement", "agreement")] > 0.8 and g[("GOOD", "events_dekad", "pod")] > 0.7, g
    assert {"spearman_rho", "kappa", "far"} <= set(v["metric"]) and v["ci_low"].notna().any(), v
    assert set(v.columns) >= {"site_id", "product", "reference", "segment", "period", "subset", "metric", "value",
                              "ci_low", "ci_high", "n", "date_from", "date_to"}
    cur = monitor_current(refs, {"GOOD": (prod, "cell")}, ("2016-01-01", "2023-12-31"), s7)
    assert cur["date"] == "2024-12-31" and cur["products"]["GOOD"]["class"] in ("dry", "normal", "wet"), cur
    print(f"[OK] Stacje ICOS: pobieranie (atrapa portalu), QC (FAST_DROP, zakres, kompletność), L2 + NRT, warstwy; "
          f"walidacja: R anomalii {g[('GOOD', 'anomaly_clim', 'pearson_r')]:.2f} (produkt zgodny), "
          f"{g[('NOISE', 'anomaly_clim', 'pearson_r')]:.2f} (szum).")


if __name__ == "__main__":
    _selftest()
