"""
v12 / tor 'agreement': czy wymaganie ZGODNOŚCI kilku wskaźników Sentinel-2 (NDVI, NDRE, NDMI) zmniejsza
fałszywe alarmy nogi roślinnej względem samego NDVI?

Odniesienie: anomalia klimatologiczna wilgotności gleby ISMN Condom 20-30 cm (średnia czujników 20 i 30 cm,
QC jak w potoku; clim_anomaly 2016-2024, ±15 dni, min_n = 20 — dokładnie jak step_07.validate_anomalies).
Zdarzenie = z ISMN <= -1.

Anomalie roślinności: step_04.scene_anomaly z konfiguracją step_05.MONITOR_CONFIG (przyczynowo, 5 lat
wcześniejszych, ten sam tor S-2, ±15 dni roku, z predykcyjne z rozkładu t), sezon IV-X, sceny clear_frac >= 0,9.
Filtr scen jak w step_05._veg_anomalies + task_scene_stats: wiersz S2SR_2.5m danego wskaźnika istnieje tylko,
gdy jego pasma przeszły kontrolę SR (sr_ok_<wskaźnik> w SR_QC bieżącej wersji) — sprawdzamy to jawnie.

Reguły nogi roślinnej (flaga, gdy wynik <= -1):
  a) NDVI z            b) NDRE z            c) NDMI z
  d) >= 2 z 3 (z <= -1)  ⟺  mediana trzech z <= -1   (wynik ciągły: mediana)
  e) wszystkie 3         ⟺  maksimum trzech z <= -1  (wynik ciągły: maksimum)
  f) średnia trzech z <= -1
Wszystkie reguły oceniane na TYM SAMYM zbiorze dni (dni scen z trzema z i z ISMN), żeby porównanie było uczciwe.

Poziomy oceny:
  1. dni scen (POD, FAR, CSI, HSS, n, flagi/rok, R Pearsona wyniku ciągłego z z ISMN),
  2. dekady (logika step_04.build_status): noga roślinna sama (ostatnia scena <= 30 dni) oraz
     ALERT = ostrzeżenie ERA5-Land RZ (SMA <= -1) ORAZ reguła; odniesienie = średnia dekadowa z ISMN <= -1
     (jak validate_anomalies, sekcja 4), dekady sezonu IV-X do 2024-12-31.
Niepewność: sparowany bootstrap blokowy (bloki = lata oraz bloki kalendarzowe 30 dni) różnicy FAR
(reguła − NDVI), POD i CSI. Wybór „najlepszej” reguły (CSI) sprawdzony bez podglądania: leave-one-year-out
(reguła wybierana na pozostałych latach, oceniana na roku wyłączonym).
Kontrola „surowszego progu”: NDVI z progiem dobranym tak, by liczba flag była równa liczbie flag reguły
zgodności (bez użycia ISMN) — odróżnia zysk z informacji od zysku z samego rzadszego flagowania.
"""
from __future__ import annotations

import json
import logging
import os
import sys
import warnings

import numpy as np
import pandas as pd

REPO = "/home/user/1_geoworldlook-agriscreen"
SCR = "/tmp/claude-0/-home-user-1-geoworldlook-agriscreen/0b6bc240-34e1-5fd3-a139-3c46967fd603/scratchpad"
DATA = os.path.join(SCR, "drive_data")
OUT = os.path.join(SCR, "v12", "agreement")
sys.path.insert(0, REPO)
import step_03_super_resolve as s3  # noqa: E402
import step_04_metrics_alert as s4  # noqa: E402
import step_05_colab_run as s5  # noqa: E402
import step_07_station_pipeline as s7  # noqa: E402

logging.basicConfig(level=logging.WARNING)
warnings.filterwarnings("ignore")

CFG = dict(s5.MONITOR_CONFIG)                    # konfiguracja potoku bez zmian
SITE = CFG["MAIN_SITE"]                          # VINEYARD_06
COMMON = ("2016-01-01", "2024-12-31")            # wspólny okres walidacji (step_07 START/END)
HW = CFG["CLIM_HALF_WINDOW_DAYS"]
THR = CFG["THR_VEG"]                             # -1
IDX = ("ndvi", "ndre", "ndmi")
VCFG = {"BOOTSTRAP_N": 1000, "BOOTSTRAP_BLOCK_DAYS": 30, "RANDOM_SEED": 42, "MIN_N_METRICS": 10}
N_BOOT = 2000
RULES = {
    "a_ndvi": "NDVI z<=-1",
    "b_ndre": "NDRE z<=-1",
    "c_ndmi": "NDMI z<=-1",
    "d_2of3": ">=2 z 3 z<=-1 (mediana)",
    "e_3of3": "wszystkie 3 z<=-1 (maksimum)",
    "f_mean": "srednia 3 z<=-1",
}


# ==============================================================================
# I. DANE
# ==============================================================================

def obs_wide() -> pd.DataFrame:
    """Obserwacje S-2 obiektów w układzie szerokim — jak step_05._veg_anomalies (pivot, czas bez strefy, IV-X)."""
    o = pd.read_csv(os.path.join(DATA, "gwl_observations.csv"))
    qc = o[(o["product"] == "SR_QC") & (o["calib_id"].astype(str) == f"SEN2SRLite_main_{s3.SR_QC_VERSION}")]
    qc = qc.pivot_table(index="time_utc", columns="variable", values="value")
    o = o[o["product"].isin(["S2_10m", "S2SR_2.5m"]) & (o["site_id"] == SITE)]
    w = o.pivot_table(index=["site_id", "product", "time_utc"], columns="variable", values="value").reset_index()
    # Kontrola SR per wskaźnik: wartość 2,5 m tylko, gdy sr_ok_<idx> = 1 w bieżącej wersji kontroli
    sr = w["product"] == "S2SR_2.5m"
    for idx in IDX:
        ok = w.loc[sr, "time_utc"].map(qc.get(f"sr_ok_{idx}", pd.Series(dtype=float))) == 1
        bad = w.loc[sr, idx].notna() & ~ok
        print(f"[QC] S2SR_2.5m {idx}: {int(w.loc[sr, idx].notna().sum())} wartości, "
              f"{int(bad.sum())} bez sr_ok_{idx}=1 (maskowane)")
        w.loc[bad[bad].index, idx] = np.nan
    w["time"] = pd.to_datetime(w["time_utc"]).dt.tz_localize(None)
    m0, m1 = CFG["S2_MONTHS"]
    return w[w["time"].dt.month.between(m0, m1)].sort_values("time").reset_index(drop=True)


def veg_scene_z(w: pd.DataFrame, product: str) -> pd.DataFrame:
    """z każdego wskaźnika per scena (step_04.scene_anomaly, MONITOR_CONFIG); wiersz = scena."""
    g = w[w["product"] == product]
    parts = []
    for idx in IDX:
        a = s4.scene_anomaly(g, idx, CFG)
        parts.append(pd.Series(a["z"].to_numpy(float), index=pd.DatetimeIndex(a["time"]), name=idx))
    z = pd.concat(parts, axis=1).sort_index()
    return z


def ins_z_rz() -> pd.Series:
    """z ISMN 20-30 cm dokładnie jak step_07.validate_anomalies (wspólny okres 2016-2024, hw=15, min_n=20)."""
    ov = {"PROJECT_DIR": REPO}
    d20 = s7.insitu_daily_depth(0.20, ov)["sm"]
    d30 = s7.insitu_daily_depth(0.30, ov)["sm"]
    rz = pd.concat([d20, d30], axis=1).dropna().mean(axis=1)
    return s4.clim_anomaly(rz, COMMON, HW, min_n=20)["z"]


def scores(z: pd.DataFrame) -> pd.DataFrame:
    """Wyniki ciągłe reguł; flaga = wynik <= -1. Reguły zgodności wymagają wszystkich trzech z."""
    s = pd.DataFrame(index=z.index)
    s["a_ndvi"], s["b_ndre"], s["c_ndmi"] = z["ndvi"], z["ndre"], z["ndmi"]
    full = z[list(IDX)].notna().all(axis=1)
    arr = z[list(IDX)].to_numpy(float)
    with np.errstate(all="ignore"):
        s["d_2of3"] = np.where(full, np.nanmedian(arr, axis=1), np.nan)
        s["e_3of3"] = np.where(full, np.nanmax(arr, axis=1), np.nan)
        s["f_mean"] = np.where(full, np.nanmean(arr, axis=1), np.nan)
    return s


def daily(df: pd.DataFrame) -> pd.DataFrame:
    """Średnia dzienna (jak validate_anomalies: z sceny -> dzień)."""
    return df.groupby(df.index.floor("D")).mean()


# ==============================================================================
# II. METRYKI
# ==============================================================================

def contingency(flag: np.ndarray, obs: np.ndarray) -> dict:
    flag, obs = np.asarray(flag, bool), np.asarray(obs, bool)
    h, fa = int((flag & obs).sum()), int((flag & ~obs).sum())
    m, cn = int((~flag & obs).sum()), int((~flag & ~obs).sum())
    n = h + fa + m + cn
    exp = ((h + m) * (h + fa) + (cn + m) * (cn + fa)) / n if n else np.nan
    return {"n": n, "n_obs": h + m, "n_flag": h + fa, "hits": h, "fa": fa, "misses": m,
            "pod": h / (h + m) if h + m else np.nan,
            "far": fa / (h + fa) if h + fa else np.nan,
            "csi": h / (h + m + fa) if h + m + fa else np.nan,
            "hss": (h + cn - exp) / (n - exp) if n and n != exp else np.nan}


def r_ci(t: pd.Series, x: np.ndarray, y: np.ndarray):
    """R Pearsona z 95% CI bootstrapu blokowego 30 dni (step_07._r_with_ci)."""
    return s7._r_with_ci(pd.Series(t).reset_index(drop=True), x, y, VCFG)


def block_ids(index: pd.DatetimeIndex, kind: str) -> np.ndarray:
    if kind == "year":
        return index.year.to_numpy()
    t = pd.Series(index)
    return ((t - t.min()) / pd.Timedelta(days=30)).astype(int).to_numpy()


def paired_boot(flags: pd.DataFrame, obs: np.ndarray, rule: str, base: str, kind: str, n_boot: int = N_BOOT,
                seed: int = 42) -> dict:
    """Sparowany bootstrap blokowy różnic (reguła − baza): FAR, POD, CSI, liczba flag."""
    rng = np.random.default_rng(seed)
    blk = block_ids(flags.index, kind)
    ub = np.unique(blk)
    by = {b: np.flatnonzero(blk == b) for b in ub}
    A, B = flags[rule].to_numpy(bool), flags[base].to_numpy(bool)
    out = {k: [] for k in ("far", "pod", "csi", "nflag")}
    for _ in range(n_boot):
        idx = np.concatenate([by[b] for b in rng.choice(ub, len(ub), replace=True)])
        ca, cb = contingency(A[idx], obs[idx]), contingency(B[idx], obs[idx])
        for k in ("far", "pod", "csi"):
            out[k].append(ca[k] - cb[k])
        out["nflag"].append(ca["n_flag"] - cb["n_flag"])
    res = {"blocks": kind, "n_blocks": len(ub)}
    for k, v in out.items():
        v = np.asarray(v, float)
        fin = v[np.isfinite(v)]
        res[f"d{k}_lo"], res[f"d{k}_hi"] = (np.percentile(fin, [2.5, 97.5]) if len(fin) >= 50 else (np.nan, np.nan))
        res[f"d{k}_p_le0"] = float(np.mean(fin <= 0)) if len(fin) else np.nan
        res[f"d{k}_p_lt0"] = float(np.mean(fin < 0)) if len(fin) else np.nan     # ściśle lepiej (mniej FA)
        res[f"d{k}_valid"] = len(fin)
    return res


def matched_threshold(score: pd.Series, n_flag: int) -> float:
    """Próg NDVI z, przy którym liczba flag = n_flag (tylko rozkład predyktora, bez ISMN)."""
    v = np.sort(score.dropna().to_numpy())
    if n_flag <= 0:
        return -np.inf
    return float(v[min(n_flag, len(v)) - 1])


# ==============================================================================
# III. OCENA NA DNIACH SCEN
# ==============================================================================

def scene_level(product: str, w: pd.DataFrame, yz: pd.Series) -> dict:
    z = veg_scene_z(w, product)
    sc = daily(scores(z))
    p = sc.join(yz.rename("ins"), how="inner")
    p = p[p["ins"].notna()]
    # Zbiór wspólny: dzień z trzema z (wszystkie reguły zdefiniowane) i z ISMN
    pc = p.dropna(subset=list(RULES)).copy()
    obs = (pc["ins"] <= THR).to_numpy()
    flags = pd.DataFrame({r: (pc[r] <= THR).to_numpy() for r in RULES}, index=pc.index)

    # Korelacje między wskaźnikami (dlaczego zgodność może niewiele dodać)
    cz = pc[["a_ndvi", "b_ndre", "c_ndmi"]].corr()
    rows = []
    # Odniesienie: NDVI na pełnym własnym zbiorze (porównanie z R = 0,38, n = 200 z walidacji)
    own = p.dropna(subset=["a_ndvi"])
    r, lo, hi = r_ci(own.index, own["a_ndvi"].to_numpy(), own["ins"].to_numpy())
    c = contingency(own["a_ndvi"] <= THR, own["ins"] <= THR)
    yrs = own[own["a_ndvi"] <= THR].index.year.value_counts().sort_index()
    rows.append({"product": product, "set": "own_ndvi", "rule": "a_ndvi", "desc": RULES["a_ndvi"], **c,
                 "r": r, "r_lo": lo, "r_hi": hi, "n_years": own.index.year.nunique(),
                 "flags_per_year": c["n_flag"] / own.index.year.nunique(),
                 "flags_by_year": json.dumps({int(k): int(v) for k, v in yrs.items()})})
    n_years = pc.index.year.nunique()
    for rule in RULES:
        c = contingency(flags[rule], obs)
        r, lo, hi = r_ci(pc.index, pc[rule].to_numpy(), pc["ins"].to_numpy())
        yrs = pc[flags[rule].to_numpy()].index.year.value_counts().sort_index()
        rows.append({"product": product, "set": "common", "rule": rule, "desc": RULES[rule], **c,
                     "r": r, "r_lo": lo, "r_hi": hi, "n_years": n_years, "flags_per_year": c["n_flag"] / n_years,
                     "flags_by_year": json.dumps({int(k): int(v) for k, v in yrs.items()})})
    # Kontrola: NDVI z progiem dopasowanym do liczby flag reguł zgodności (bez ISMN)
    for rule in ("d_2of3", "e_3of3", "f_mean"):
        k = int(flags[rule].sum())
        thr = matched_threshold(pc["a_ndvi"], k)
        fl = (pc["a_ndvi"] <= thr).to_numpy()
        c = contingency(fl, obs)
        name = f"a_ndvi@{rule}"
        flags[name] = fl
        rows.append({"product": product, "set": "common", "rule": name,
                     "desc": f"NDVI z<={thr:.2f} (liczba flag jak {rule})", **c,
                     "r": np.nan, "r_lo": np.nan, "r_hi": np.nan, "n_years": n_years,
                     "flags_per_year": c["n_flag"] / n_years, "flags_by_year": ""})
    tab = pd.DataFrame(rows)

    # Sparowany bootstrap: każda reguła vs NDVI (bloki lat i 30 dni)
    boots = []
    for rule in [r for r in flags.columns if r != "a_ndvi"]:
        for kind in ("year", "30d"):
            boots.append({"product": product, "rule": rule, "base": "a_ndvi",
                          **paired_boot(flags, obs, rule, "a_ndvi", kind)})
    # Kontrola surowszego progu: reguła zgodności vs NDVI z tą samą liczbą flag
    for rule in ("d_2of3", "e_3of3", "f_mean"):
        for kind in ("year", "30d"):
            boots.append({"product": product, "rule": rule, "base": f"a_ndvi@{rule}",
                          **paired_boot(flags, obs, rule, f"a_ndvi@{rule}", kind)})
    boot = pd.DataFrame(boots)

    # Różnica R (wynik ciągły reguły − NDVI), sparowany bootstrap 30 dni
    dr = []
    for rule in ("b_ndre", "c_ndmi", "d_2of3", "e_3of3", "f_mean"):
        dr.append({"product": product, "rule": rule, **paired_r_diff(pc, rule, "a_ndvi")})
    dr = pd.DataFrame(dr)

    # Leave-one-year-out: wybór reguły (max CSI) na pozostałych latach, ocena na roku wyłączonym
    loyo = loyo_selection(flags[list(RULES)], obs)
    loyo["product"] = product
    # Czułość (ustalona z góry, nie służy do wyboru): zdarzenie ISMN z <= -0,5 zamiast -1; flagi reguł bez zmian
    sens = []
    for ev_thr in (-0.5,):
        o2 = (pc["ins"] <= ev_thr).to_numpy()
        for rule in RULES:
            sens.append({"product": product, "event_thr": ev_thr, "rule": rule, **contingency(flags[rule], o2)})
        for rule in ("d_2of3", "e_3of3", "f_mean"):
            b2 = paired_boot(flags, o2, rule, "a_ndvi", "year")
            sens.append({"product": product, "event_thr": ev_thr, "rule": f"{rule}-a_ndvi (dFAR, lata)",
                         "far": np.nan, "dfar_lo": b2["dfar_lo"], "dfar_hi": b2["dfar_hi"]})
    return {"z": z, "pairs": pc, "table": tab, "boot": boot, "dr": dr, "loyo": loyo, "corr": cz, "flags": flags,
            "obs": obs, "sens": pd.DataFrame(sens)}


def paired_r_diff(pc: pd.DataFrame, a: str, b: str, n_boot: int = N_BOOT, seed: int = 42) -> dict:
    ra = np.corrcoef(pc[a], pc["ins"])[0, 1]
    rb = np.corrcoef(pc[b], pc["ins"])[0, 1]
    blk = block_ids(pc.index, "30d")
    ub = np.unique(blk)
    by = {k: np.flatnonzero(blk == k) for k in ub}
    rng = np.random.default_rng(seed)
    A, B, Y = pc[a].to_numpy(), pc[b].to_numpy(), pc["ins"].to_numpy()
    ds = []
    for _ in range(n_boot):
        idx = np.concatenate([by[k] for k in rng.choice(ub, len(ub), replace=True)])
        ds.append(np.corrcoef(A[idx], Y[idx])[0, 1] - np.corrcoef(B[idx], Y[idx])[0, 1])
    ds = np.asarray(ds)
    ds = ds[np.isfinite(ds)]
    return {"r_rule": ra, "r_ndvi": rb, "dr": ra - rb, "dr_lo": np.percentile(ds, 2.5),
            "dr_hi": np.percentile(ds, 97.5), "n": len(pc)}


def loyo_selection(flags: pd.DataFrame, obs: np.ndarray) -> pd.DataFrame:
    """Dla każdego roku: reguła o najwyższym CSI na pozostałych latach, oceniona na roku wyłączonym."""
    yrs = flags.index.year.to_numpy()
    rows = []
    agg_sel = np.zeros(len(flags), bool)
    for y in np.unique(yrs):
        tr, te = yrs != y, yrs == y
        csi = {r: contingency(flags[r].to_numpy()[tr], obs[tr])["csi"] for r in flags.columns}
        best = max(csi, key=lambda r: -np.inf if not np.isfinite(csi[r]) else csi[r])
        agg_sel[te] = flags[best].to_numpy()[te]
        rows.append({"year": int(y), "chosen": best, "train_csi": csi[best], "train_csi_ndvi": csi["a_ndvi"],
                     **{f"test_{k}": v for k, v in contingency(flags[best].to_numpy()[te], obs[te]).items()
                        if k in ("n", "n_obs", "n_flag", "hits", "fa")}})
    tab = pd.DataFrame(rows)
    sel, base = contingency(agg_sel, obs), contingency(flags["a_ndvi"].to_numpy(), obs)
    tab = pd.concat([tab, pd.DataFrame([
        {"year": "ALL_selected", **{f"test_{k}": sel[k] for k in ("n", "n_obs", "n_flag", "hits", "fa")},
         "test_pod": sel["pod"], "test_far": sel["far"], "test_csi": sel["csi"]},
        {"year": "ALL_ndvi", **{f"test_{k}": base[k] for k in ("n", "n_obs", "n_flag", "hits", "fa")},
         "test_pod": base["pod"], "test_far": base["far"], "test_csi": base["csi"]}])], ignore_index=True)
    return tab


# ==============================================================================
# IV. OCENA NA DEKADACH (logika build_status)
# ==============================================================================

def ins_dekads(yz: pd.Series) -> pd.Series:
    """Średnia dekadowa z ISMN (validate_anomalies, sekcja 4)."""
    d = yz.dropna()
    tmp = pd.DataFrame({"z": d.to_numpy(), "dk": s4.dekad_end(pd.Series(d.index)).to_numpy()})
    return tmp.groupby("dk")["z"].mean()


def dekad_level(product: str, z: pd.DataFrame, an: dict, ins_dk: pd.Series) -> tuple:
    sc = scores(z)                                # wynik per scena (czas sceny jak w potoku)
    sts = {}
    for rule in RULES:
        s = sc[rule].dropna()
        veg = pd.DataFrame({"site_id": SITE, "time": s.index, "z": s.to_numpy(), "product": f"{product}:{rule}"})
        st = s4.build_status(an, veg, SITE, CFG, CFG["STATUS_START"])
        st["date"] = pd.to_datetime(st["date"])
        sts[rule] = st.set_index("date")
    base = sts["a_ndvi"].join(ins_dk.rename("ins"), how="inner").dropna(subset=["ins", "sma_rz"])
    # Kontrola odtworzenia: ostrzeżenie ERA5 RZ vs ISMN na wszystkich dekadach (POD 0,574 / FAR 0,571)
    c_all = contingency(base["sma_rz"] <= CFG["THR_SMA"], base["ins"] <= CFG["THR_SMA"])
    m0, m1 = CFG["S2_MONTHS"]
    sea = base[(base.index <= COMMON[1]) & base.index.month.isin(range(m0, m1 + 1))]
    obs = (sea["ins"] <= THR).to_numpy()
    warn = (sea["sma_rz"] <= CFG["THR_SMA"]).to_numpy()
    n_years = sea.index.year.nunique()
    fin_any = np.isfinite(sts["a_ndvi"].reindex(sea.index)["veg_z"].to_numpy(float))
    cw = contingency(warn[fin_any], obs[fin_any])
    rows = [{"product": product, "level": "warning (ERA5 RZ)", "rule": "-", **contingency(warn, obs),
             "n_veg_available": int(fin_any.sum()), "n_obs_veg_avail": cw["n_obs"], "pod_veg_avail": cw["pod"],
             "far_veg_avail": cw["far"],
             "flags_per_year": warn.sum() / n_years,
             "flags_by_year": json.dumps({int(k): int(v) for k, v in
                                          sea[warn].index.year.value_counts().sort_index().items()})}]
    flags_alert, flags_veg = {}, {}
    for rule, st in sts.items():
        st = st.reindex(sea.index)
        vz = st["veg_z"].to_numpy(float)
        vflag = np.isfinite(vz) & (vz <= THR)
        alert = (st["cdi_level"] == 3).to_numpy()
        assert np.array_equal(alert, warn & vflag)       # alert = warning AND reguła
        flags_alert[rule], flags_veg[rule] = alert, vflag
        fin = np.isfinite(vz)
        r_dk = float(np.corrcoef(vz[fin], sea["ins"].to_numpy()[fin])[0, 1]) if fin.sum() >= 10 else np.nan
        for lvl, fl in (("veg leg (dekad)", vflag), ("ALERT = warning AND veg", alert)):
            c = contingency(fl, obs)
            # podzbiór: tylko dekady, w których jest wynik roślinności (bez 2016-2017: klimatologia przyczynowa)
            cv = contingency(fl[fin], obs[fin])
            rows.append({"product": product, "level": lvl, "rule": rule, **c, "flags_per_year": c["n_flag"] / n_years,
                         "n_veg_available": int(fin.sum()), "n_obs_veg_avail": cv["n_obs"],
                         "pod_veg_avail": cv["pod"], "far_veg_avail": cv["far"], "r_dekad_vegz_ins": r_dk,
                         "flags_by_year": json.dumps({int(k): int(v) for k, v in
                                                      sea[fl].index.year.value_counts().sort_index().items()})})
    tab = pd.DataFrame(rows)
    fa = pd.DataFrame(flags_alert, index=sea.index)
    fv = pd.DataFrame(flags_veg, index=sea.index)
    boots = []
    for rule in RULES:
        if rule == "a_ndvi":
            continue
        for kind in ("year", "30d"):
            boots.append({"product": product, "level": "alert", "rule": rule, "base": "a_ndvi",
                          **paired_boot(fa, obs, rule, "a_ndvi", kind)})
            boots.append({"product": product, "level": "veg leg (dekad)", "rule": rule, "base": "a_ndvi",
                          **paired_boot(fv, obs, rule, "a_ndvi", kind)})
    return tab, pd.DataFrame(boots), c_all, len(base)


# ==============================================================================
# V. URUCHOMIENIE
# ==============================================================================

def fmt(x, nd=2):
    return "—" if x is None or (isinstance(x, float) and not np.isfinite(x)) else f"{x:.{nd}f}"


def main() -> None:
    os.makedirs(OUT, exist_ok=True)
    pd.set_option("display.width", 250, "display.max_columns", 40, "display.max_colwidth", 60)
    w = obs_wide()
    yz = ins_z_rz()
    era5 = pd.read_csv(os.path.join(DATA, "era5_land_daily.csv"), parse_dates=["time"])
    an = s4.era5_anomalies(era5, CFG)
    ins_dk = ins_dekads(yz)

    # Kontrola odtworzenia: ERA5 RZ vs ISMN (R = 0,58, n = 2976)
    e = era5.set_index(pd.to_datetime(era5["time"]).dt.floor("D")).sort_index()
    e = e[~e.index.duplicated(keep="last")].loc[COMMON[0]:COMMON[1]]
    ez = s4.clim_anomaly(s4.rootzone(e), COMMON, HW, min_n=20)["z"]
    pe = pd.concat([ez.rename("x"), yz.rename("y")], axis=1).dropna()
    print(f"[sanity] ERA5 RZ vs ISMN 20-30 cm: R={np.corrcoef(pe['x'], pe['y'])[0, 1]:.3f} n={len(pe)}")

    all_tab, all_boot, all_dr, all_loyo, all_dk, all_dkb, all_sens = [], [], [], [], [], [], []
    # Rejestr z commita 277d162 liczony klimatologią nieprzyczynową ('other_years') — status z rejestru nie jest
    # punktem odniesienia dla tej konfiguracji; odtwarzamy liczby walidacji (R ERA5 0,58; R NDVI SR 0,38, n = 200)
    reg = pd.read_csv(os.path.join(DATA, "gwl_anomalies.csv"), usecols=["clim_id"])
    print("[info] klimatologie w gwl_anomalies (rejestr):", sorted(reg["clim_id"].dropna().unique()))
    for product in ("S2SR_2.5m", "S2_10m"):
        res = scene_level(product, w, yz)
        t = res["table"]
        own = t[t["set"] == "own_ndvi"].iloc[0]
        print(f"\n=== {product}: dni scen ===")
        print(f"[sanity] NDVI (pełny zbiór) vs ISMN: R={own['r']:.3f} [{own['r_lo']:.2f},{own['r_hi']:.2f}] n={own['n']}")
        print(f"zbiór wspólny (3 z + ISMN): n={int(t[t['set'] == 'common']['n'].iloc[0])} dni, "
              f"zdarzeń ISMN={int(t[t['set'] == 'common']['n_obs'].iloc[0])}, lata={sorted(set(res['pairs'].index.year))}")
        print("korelacje z między wskaźnikami (zbiór wspólny):\n", res["corr"].round(2).to_string())
        print(t[["set", "rule", "n", "n_obs", "n_flag", "hits", "fa", "pod", "far", "csi", "hss", "r", "r_lo", "r_hi",
                 "flags_per_year", "flags_by_year"]].round(3).to_string(index=False))
        b = res["boot"]
        print("\nsparowany bootstrap (reguła − baza):")
        print(b[["rule", "base", "blocks", "n_blocks", "dfar_lo", "dfar_hi", "dfar_p_lt0", "dfar_p_le0", "dfar_valid",
                 "dpod_lo", "dpod_hi", "dcsi_lo", "dcsi_hi"]].round(3).to_string(index=False))
        print("\nróżnica R (wynik ciągły − NDVI), bootstrap 30 dni:")
        print(res["dr"].round(3).to_string(index=False))
        print("\nLOYO wybór reguły (max CSI na pozostałych latach):")
        print(res["loyo"].round(3).to_string(index=False))
        print("\nczułość: zdarzenie ISMN z <= -0,5 (ustalone z góry, bez wyboru):")
        print(res["sens"].round(3).to_string(index=False))
        all_tab.append(t), all_boot.append(b), all_dr.append(res["dr"]), all_loyo.append(res["loyo"])
        all_sens.append(res["sens"])
        out_pairs = res["pairs"].copy()
        out_pairs.index.name = "day"
        out_pairs.to_csv(os.path.join(OUT, f"scene_pairs_{product}.csv"))

        dk, dkb, c_all, n_all = dekad_level(product, res["z"], an, ins_dk)
        print(f"\n=== {product}: dekady sezonu IV-X 2016-2024 ===")
        print(f"[sanity] ostrzeżenie ERA5 RZ, wszystkie dekady: POD={c_all['pod']:.3f} FAR={c_all['far']:.3f} n={n_all}")
        print(dk[["level", "rule", "n", "n_obs", "n_flag", "hits", "fa", "pod", "far", "csi", "hss", "flags_per_year",
                  "n_veg_available", "n_obs_veg_avail", "pod_veg_avail", "far_veg_avail", "r_dekad_vegz_ins",
                  "flags_by_year"]].round(3).to_string(index=False))
        print("\nsparowany bootstrap dekad (reguła − NDVI):")
        print(dkb[["level", "rule", "blocks", "n_blocks", "dfar_lo", "dfar_hi", "dfar_p_lt0", "dfar_p_le0", "dfar_valid", "dpod_lo",
                   "dpod_hi", "dcsi_lo", "dcsi_hi"]].round(3).to_string(index=False))
        all_dk.append(dk), all_dkb.append(dkb)

    pd.concat(all_tab).to_csv(os.path.join(OUT, "scene_rules.csv"), index=False)
    pd.concat(all_boot).to_csv(os.path.join(OUT, "scene_boot.csv"), index=False)
    pd.concat(all_dr).to_csv(os.path.join(OUT, "scene_r_diff.csv"), index=False)
    pd.concat(all_loyo).to_csv(os.path.join(OUT, "scene_loyo.csv"), index=False)
    pd.concat(all_dk).to_csv(os.path.join(OUT, "dekad_rules.csv"), index=False)
    pd.concat(all_dkb).to_csv(os.path.join(OUT, "dekad_boot.csv"), index=False)
    pd.concat(all_sens).to_csv(os.path.join(OUT, "scene_sensitivity_event_thr.csv"), index=False)
    print(f"\nZapisano CSV w {OUT}")


if __name__ == "__main__":
    main()
