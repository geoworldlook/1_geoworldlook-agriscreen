"""
================================================================================
AgriWatch - KROK 5: STEROWANIE Z NOTATNIKA, REJESTR NA DYSKU I ZADANIA MONITORINGU
================================================================================
Architektura: kod na GitHub -> obliczenia w Colab -> Dysk Google jako baza danych (tabele gwl_*).

  I.  setup_runtime, run_task, run_history, registry_* — rejestr CSV z kluczem głównym (upsert).
  II. Konfiguracja monitoringu jednej winnicy (MONITOR_CONFIG) i zadania:
        task_ingest_s2       rastry Sentinel-2 (step_01, przyrostowo, manifest)
        task_ingest_era5     ERA5-Land 1991 -> dziś w punkcie winnicy (step_01, cache)
        task_scene_stats     indeksy obiektów: 10 m oraz SEN2SR 2,5 m z kontrolą H-SR0/H-SR1 (step_03, step_04)
        task_anomalies       anomalie ERA5 (SMA, SPI) i roślinności + status dekadowy (step_04)
        task_validate        błąd anomalii na profilu ISMN Condom (step_07)
        task_bulletin        raport, wykresy i JSON dla geoworldlook.vercel.app (step_04)

Architektura i uzasadnienie: docs/ARCHITEKTURA.md (literatura: docs/plans/Plan_v3_monitoring_winnic_SR.md, część A).
Poprzednia wersja (potok AgriScreen v2.5): legacy/step_05_colab_run_v1.py.
================================================================================
"""

import glob
import json
import logging
import os
import subprocess
import sys
import time
from datetime import datetime, timezone
from typing import Any, Callable, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger("AgriWatch_Run")

# ==============================================================================
# I. STEROWANIE Z NOTATNIKA I REJESTR NA DYSKU GOOGLE
# ==============================================================================
# Rejestr = pliki CSV w data/registry/ (w Colab: na Dysku Google). Nazwy tabel i kolumn
# są nazwami w przyszłej bazie danych, "keys" to klucz główny. Opis: docs/ARCHITEKTURA.md.
#
# Użycie w notatniku:
#     rt = setup_runtime(PROJECT_DIR)
#     res = run_task(rt, "station_condom", run_station_pipeline, rt)
#     run_history(rt)

REGISTRY_SCHEMA: Dict[str, Dict[str, List[str]]] = {
    "gwl_sites": {
        "keys": ["site_id"],
        "columns": ["site_id", "site_type", "name", "network", "land_use", "lat", "lon", "geometry_wkt",
                    "footprint", "area_m2", "source", "run_id", "updated_at"],
    },
    "gwl_observations": {
        "keys": ["site_id", "product", "variable", "time_utc", "orbit"],
        "columns": ["site_id", "product", "variable", "time_utc", "orbit", "value", "unit", "n_pixels",
                    "qc_flags", "calib_id", "run_id", "ingested_at"],
    },
    "gwl_anomalies": {
        "keys": ["site_id", "product", "date"],
        "columns": ["site_id", "product", "date", "value", "clim_mean", "z", "percentile",
                    "era5_percentile_1991_2020", "status", "confidence", "reason_codes", "expected_error",
                    "clim_id", "run_id"],
    },
    "gwl_validation_metrics": {
        # Bez run_id w kluczu: zmiana metryki (np. po nowych danych ISMN) zastępuje wiersz,
        # a run_id wskazuje uruchomienie, które ją policzyło. Historia raportów zostaje w gwl_runs.
        "keys": ["site_id", "product", "reference", "segment", "period", "subset", "metric"],
        "columns": ["site_id", "product", "reference", "segment", "period", "subset", "metric",
                    "value", "ci_low", "ci_high", "n", "date_from", "date_to", "run_id"],
    },
    "gwl_calibrations": {
        "keys": ["calib_id", "site_id", "product", "orbit", "param"],
        "columns": ["calib_id", "site_id", "product", "orbit", "param", "value", "period_start", "period_end",
                    "run_id"],
    },
    "gwl_status": {
        "keys": ["site_id", "date"],
        "columns": ["site_id", "date", "cdi_level", "cdi_class", "action", "spi1", "spi3", "sma_rz", "sma_l1",
                    "p_soil_drought", "veg_z",
                    "veg_source", "veg_age_days", "confidence", "reason_codes", "run_id"],
    },
    "gwl_runs": {
        "keys": ["run_id"],
        "columns": ["run_id", "task", "started_at", "finished_at", "duration_s", "status", "git_commit",
                    "pipeline_version", "params_json", "n_new_rows", "message"],
    },
}

# Kolumny techniczne: ich zmiana nie oznacza zmiany danych (wiersz z tą samą wartością nie jest nadpisywany)
_META_COLUMNS = {"run_id", "ingested_at", "updated_at"}


def _utc_now() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _git(project_dir: str, *args: str) -> str:
    try:
        out = subprocess.run(["git", "-C", project_dir, *args], capture_output=True, text=True, timeout=120)
        return (out.stdout or out.stderr).strip()
    except Exception as e:
        return f"git niedostępny ({e})"


def _git_commit(project_dir: str) -> str:
    """Skrót commita + '+dirty', jeśli w repozytorium są niezatwierdzone zmiany w kodzie."""
    if not os.path.exists(os.path.join(project_dir, ".git")):
        return "no-git"
    commit = _git(project_dir, "rev-parse", "--short", "HEAD")
    dirty = _git(project_dir, "status", "--porcelain", "--untracked-files=no")
    return commit + ("+dirty" if dirty else "")


def setup_runtime(
    project_dir: Optional[str] = None,
    gee_project: str = "ee-geoworldlook",
    pull: bool = True,
    install: bool = True,
    init_gee: bool = True,
) -> Dict[str, Any]:
    """
    Przygotowuje środowisko (Colab lub lokalnie) i zwraca słownik `rt` przekazywany do zadań.
    Dysk Google montuje komórka notatnika przed importem tego modułu (kod leży na Dysku).

    Kroki: git pull (tylko fast-forward) -> instalacja brakujących pakietów (tylko Colab)
    -> inicjalizacja GEE (step_01) -> katalog rejestru.
    """
    if not logging.getLogger().handlers:
        logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    project_dir = os.path.abspath(project_dir or os.getcwd())
    in_colab = "google.colab" in sys.modules

    if pull and os.path.exists(os.path.join(project_dir, ".git")):
        # lokalne zmiany blokują pull --ff-only; stash je zachowuje (git stash list)
        if _git(project_dir, "status", "--porcelain", "--untracked-files=no"):
            logger.info(f"git stash: {_git(project_dir, 'stash', 'push', '-m', 'colab-autostash')}")
        logger.info(f"git pull: {_git(project_dir, 'pull', '--ff-only')}")

    if install and in_colab:
        import importlib.util
        needed = {"ee": "earthengine-api", "geemap": "geemap", "geedim": "geedim", "rasterio": "rasterio",
                  "geopandas": "geopandas", "pytesmo": "pytesmo", "ismn": "ismn"}
        missing = [pkg for mod, pkg in needed.items() if importlib.util.find_spec(mod) is None]
        if missing:
            logger.info(f"Instalacja: {' '.join(missing)}")
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", *missing], check=True)
        # SR jest opcjonalny: błąd instalacji nie zatrzymuje monitoringu (task_scene_stats zgłosi brak SR)
        sr_missing = [p for p in ("sen2sr", "mlstac") if importlib.util.find_spec(p) is None]
        if sr_missing:
            r = subprocess.run([sys.executable, "-m", "pip", "install", "-q", *sr_missing], capture_output=True, text=True)
            if r.returncode != 0:
                logger.warning(f"Nie udało się zainstalować {sr_missing}: {r.stderr[-500:]}")

    if init_gee:
        from step_01_ingest import initialize_earth_engine
        initialize_earth_engine(project_id=gee_project)

    rt = {
        "PROJECT_DIR": project_dir,
        "DATA_DIR": os.path.join(project_dir, "data"),
        "REGISTRY_DIR": os.path.join(project_dir, "data", "registry"),
        "GEE_PROJECT": gee_project,
        "IN_COLAB": in_colab,
        "GIT_COMMIT": _git_commit(project_dir),
    }
    os.makedirs(rt["REGISTRY_DIR"], exist_ok=True)
    logger.info(f"Środowisko gotowe: {project_dir} (commit {rt['GIT_COMMIT']}, Colab={in_colab})")
    return rt


def _registry_path(rt: Dict[str, Any], table: str) -> str:
    if table not in REGISTRY_SCHEMA:
        raise KeyError(f"Nieznana tabela rejestru: {table}. Dostępne: {sorted(REGISTRY_SCHEMA)}")
    return os.path.join(rt["REGISTRY_DIR"], f"{table}.csv")


def registry_read(rt: Dict[str, Any], table: str) -> pd.DataFrame:
    """Czyta tabelę rejestru; brak pliku = pusta tabela z kolumnami ze schematu."""
    path = _registry_path(rt, table)
    cols = REGISTRY_SCHEMA[table]["columns"]
    if not os.path.exists(path):
        return pd.DataFrame(columns=cols)
    df = pd.read_csv(path, low_memory=False)
    return df.reindex(columns=cols)


def _canon(df: pd.DataFrame) -> pd.DataFrame:
    """Tekstowa postać kanoniczna (porównanie kluczy i wartości niezależne od typu po odczycie CSV)."""
    def one(v: Any) -> str:
        if v is None or v is pd.NA or v is pd.NaT or (isinstance(v, float) and not np.isfinite(v)):
            return ""
        if isinstance(v, (float, np.floating)):
            return str(int(v)) if float(v).is_integer() else f"{float(v):.10g}"
        if isinstance(v, (int, np.integer, bool, np.bool_)):
            return str(int(v))
        if isinstance(v, str):
            return "" if v.lower() == "nan" else v
        return str(v)
    return df.apply(lambda col: col.map(one))


def registry_upsert(rt: Dict[str, Any], table: str, df: pd.DataFrame) -> Dict[str, int]:
    """
    Dopisuje wiersze do tabeli rejestru według klucza głównego:
      - nowy klucz -> wiersz dopisany,
      - istniejący klucz ze zmienioną wartością -> wiersz zastąpiony,
      - istniejący klucz bez zmian -> zostaje stary wiersz (z pierwotnym run_id i ingested_at).
    Zapis atomowy (plik tymczasowy + zamiana). Zwraca liczniki {"new", "changed", "unchanged"}.
    """
    keys = REGISTRY_SCHEMA[table]["keys"]
    cols = REGISTRY_SCHEMA[table]["columns"]
    missing = [k for k in keys if k not in df.columns]
    if missing:
        raise ValueError(f"{table}: brak kolumn klucza {missing}")
    extra = [c for c in df.columns if c not in cols]
    if extra:
        logger.warning(f"{table}: kolumny spoza schematu pominięte: {extra}")
    new = df.reindex(columns=cols)
    new_c = _canon(new)
    new_key = new_c[keys].agg("\x1f".join, axis=1)
    dup = new_key.duplicated(keep="last")
    if dup.any():
        logger.warning(f"{table}: {int(dup.sum())} zduplikowanych kluczy w nowych danych — zostaje ostatni.")
        new, new_c, new_key = new[~dup.values], new_c[~dup.values], new_key[~dup.values]

    old = registry_read(rt, table)
    old_c = _canon(old)
    old_key = old_c[keys].agg("\x1f".join, axis=1) if len(old) else pd.Series([], dtype=str)

    in_old = new_key.isin(set(old_key))
    value_cols = [c for c in cols if c not in keys and c not in _META_COLUMNS]
    changed_keys = set()
    if in_old.any():
        a = new_c[in_old.values].set_index(new_key[in_old].to_numpy())[value_cols]
        b = old_c.set_index(old_key.to_numpy())[value_cols].loc[a.index]
        changed_keys = set(a.index[(a != b).any(axis=1).values])

    write_mask = (~in_old.values) | new_key.isin(changed_keys).values
    keep_old = ~old_key.isin(changed_keys).values if len(old) else np.array([], bool)
    out = pd.concat([old[keep_old], new[write_mask]], ignore_index=True)
    out_key = _canon(out[keys]).agg("\x1f".join, axis=1) if len(out) else pd.Series([], dtype=str)
    out = out.iloc[np.argsort(out_key.to_numpy(), kind="stable")]

    path = _registry_path(rt, table)
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    out.to_csv(tmp, index=False)
    os.replace(tmp, path)
    counts = {"new": int((~in_old).sum()), "changed": len(changed_keys),
              "unchanged": int(in_old.sum()) - len(changed_keys)}
    logger.info(f"Rejestr {table}: +{counts['new']} nowych, {counts['changed']} zmienionych, "
                f"{counts['unchanged']} bez zmian (razem {len(out)}).")
    return counts


def _short_repr(v: Any, limit: int = 300) -> str:
    s = repr(v)
    return s if len(s) <= limit else s[:limit] + "..."


def run_task(
    rt: Dict[str, Any],
    name: str,
    fn: Callable[..., Any],
    *args: Any,
    raise_errors: bool = False,
    **kwargs: Any,
) -> Any:
    """
    Uruchamia jedno zadanie i zapisuje je w gwl_runs.

    Kontrakt zadania: fn(*args, **kwargs) może zwrócić słownik z kluczami:
      "registry": {tabela: DataFrame} -> wiersze trafiają do rejestru (z run_id tego uruchomienia),
      "skipped": True                 -> zadanie nie miało nic do zrobienia (status "skipped"),
      "pipeline_version": str         -> wersja modułu zapisana w gwl_runs.
    Błąd nie przerywa "Uruchom wszystko" (chyba że raise_errors=True): jest zapisany w gwl_runs i wypisany.
    """
    started = _utc_now()
    run_id = f"{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}_{name}"
    t0 = time.time()
    status, message, n_new, result, error = "ok", "", 0, None, None
    logger.info(f"=== ZADANIE {name} (run_id={run_id}) ===")
    try:
        result = fn(*args, **kwargs)
        if isinstance(result, dict):
            if result.get("skipped"):
                status = "skipped"
                message = str(result.get("message", ""))
            parts = []
            for table, df in (result.get("registry") or {}).items():
                df = df.copy()
                if "run_id" in REGISTRY_SCHEMA[table]["columns"]:
                    df["run_id"] = run_id
                c = registry_upsert(rt, table, df)
                n_new += c["new"]
                parts.append(f"{table}: +{c['new']}/~{c['changed']}")
            if parts:
                message = (message + "; " if message else "") + ", ".join(parts)
    except Exception as e:
        status, message, error = "error", f"{type(e).__name__}: {e}", e
        logger.exception(f"Zadanie {name} zakończone błędem")

    params = {"args": [_short_repr(a) for a in args], "kwargs": {k: _short_repr(v) for k, v in kwargs.items()}}
    run_row = pd.DataFrame([{
        "run_id": run_id, "task": name, "started_at": started, "finished_at": _utc_now(),
        "duration_s": round(time.time() - t0, 1), "status": status, "git_commit": rt.get("GIT_COMMIT", ""),
        "pipeline_version": result.get("pipeline_version", "") if isinstance(result, dict) else "",
        "params_json": json.dumps(params, ensure_ascii=False), "n_new_rows": n_new, "message": message[:2000],
    }])
    registry_upsert(rt, "gwl_runs", run_row)
    print(f"[{status.upper()}] {name} ({run_row['duration_s'].iat[0]} s) {message}")
    if error is not None and raise_errors:
        raise error
    return result


def run_history(rt: Dict[str, Any], n: int = 20) -> pd.DataFrame:
    """Ostatnie uruchomienia (najnowsze na górze)."""
    runs = registry_read(rt, "gwl_runs")
    cols = ["run_id", "task", "status", "duration_s", "n_new_rows", "git_commit", "message"]
    return runs.sort_values("started_at", ascending=False).head(n)[cols].reset_index(drop=True)


def registry_summary(rt: Dict[str, Any]) -> pd.DataFrame:
    """Liczba wierszy i rozmiar każdej tabeli rejestru."""
    rows = []
    for table in REGISTRY_SCHEMA:
        path = _registry_path(rt, table)
        exists = os.path.exists(path)
        rows.append({"table": table, "rows": len(registry_read(rt, table)) if exists else 0,
                     "size_kb": round(os.path.getsize(path) / 1024, 1) if exists else 0.0})
    return pd.DataFrame(rows)


# ==============================================================================
# II. MONITORING JEDNEJ WINNICY: KONFIGURACJA I ZADANIA
# ==============================================================================
# Ścieżki względne liczone od PROJECT_DIR. Progi statusu = progi EDO CDI (factsheet v4).
# Rozszerzenie na kolejne winnice: dopisać fid do VINEYARDS (np. {"VINEYARD_06": 6, "VINEYARD_07": 7}).

MONITOR_CONFIG: Dict[str, Any] = {
    # Obiekty
    "PARCELS_PATH": "data/1_AOI_GBOV_CONDOM.geojson",
    "AOI_PATH": "data/1_AOI_GBOV_CONDOM_ZASIEG.geojson",
    "AOI_BUFFER_M": 320,                  # zapas wokół AOI (SR potrzebuje >= 128 px; brak efektów brzegowych)
    "VINEYARDS": {"VINEYARD_06": 6},      # winnica 2,9 ha, 136 m od stacji Condom
    "MAIN_SITE": "VINEYARD_06",
    "STATION_POLY_FID": 23,
    "STATION_BUFFER_M": 50,
    "NETWORK": "SMOSMANIA",
    "STATION": "Condom",
    "ISMN_DIR": "data/7_isismn_data",
    "EPSG": 32631,
    # Sentinel-2 (rastry jak w v1: 10 pasm + maska chmur, przyrostowo z manifestem)
    "S2_DIR": "data/01_Raw_Sentinel2",
    "S2_MANIFEST": "data/00_Metadata/ingest_manifest.json",
    "S2_START_YEAR": 2016,
    "S2_CLOUD_MAX_AOI": 40,               # % chmur nad AOI (s2cloudless)
    "S2_MONTHS": (4, 10),                 # sezon wegetacyjny winorośli; zimą NDVI = okrywa międzyrzędzi
    # ERA5-Land (seria punktowa: całe AOI to jedno oczko ~9 km)
    "ERA5_DIR": "data/02_ERA5_Land",
    "ERA5_START": "1991-01-01",
    "CLIM_REF": ("1991-01-01", "2020-12-31"),   # okres odniesienia WMO
    "CLIM_HALF_WINDOW_DAYS": 15,
    "SPI_DAYS": (30, 90),                 # SPI-1 i SPI-3
    # Roślinność
    "VEG_INDEX": "ndvi",
    "VEG_PRODUCT": "S2SR_2.5m",           # rozdzielczość detekcji: NDVI z SEN2SR 2,5 m (decyzja 2026-10-07);
                                          # sceny, które nie przeszły kontroli SR, nie wchodzą do detekcji.
                                          # S2_10m liczony dalej jako odniesienie (walidacja, porównanie paired)
    "VEG_HALF_WINDOW_DAYS": 15,
    "VEG_MIN_REF": 5,
    "VEG_MIN_CLEAR_FRAC": 0.9,
    "VEG_MAX_AGE_DAYS": 30,
    "VEG_CAUSAL": True,                   # klimatologia tylko z lat wcześniejszych (Plan v7 A1)
    "VEG_BY_TRACK": True,                 # odniesienie z tego samego toru orbity S-2 (A2)
    "VEG_PREDICTIVE_Z": True,             # z predykcyjne z rozkładu t (A3)
    "VEG_REF_YEARS": 5,                   # klimatologia z ostatnich 5 lat wcześniejszych (trend zarządzania międzyrzędziem)
    # Prawdopodobieństwo suszy gleby (A7): korelacja anomalii ERA5-Land 0-100 cm z ISMN Condom 20-30 cm
    "PSMA_RHO": 0.58,
    # Progi statusu (EDO CDI)
    "THR_SPI1": -2.0, "THR_SPI3": -1.0, "THR_SMA": -1.0, "THR_VEG": -1.0,
    "STATUS_START": "2016-01-01",
    # Super-resolution
    "USE_SR": True,
    "SR_MODEL_DIR": "data/models/SEN2SRLite_main",
    "SR_MAX_SCENES_PER_RUN": 150,         # limit na uruchomienie (sesja Colab); None = wszystkie. Od najnowszych
    "SR_MIN_DETAIL_RATIO": 0.02,          # H-SR0: v1 (interpolacja) = 0,005
    "SR_MAX_CONSISTENCY_RMSE": 0.01,      # H-SR1 pasm 10 m (NDVI, rdzeń detekcji): stały, surowy próg reflektancji
    "SR_20M_SPEC_FACTOR": 1.5,            # H-SR1 pasm 20 m: RMSE ≤ k·(0,05·ρ + 0,005), specyfikacja L2A (Vermote 2008);
                                          # k = 1,5 (decyzja 2026-10-07): przepuszcza B12 -> CRSWIR z 2,5 m do testów.
                                          # Ryzyko przyjęte świadomie: NDMI/NDRE ~0,03–0,04, CRSWIR ~0,05 na piksel
    "SR_DIR": "data/03_SR_2.5m",
    "SHOWCASE_MONTHS": ["2022-07", "2022-08"],
    "SHOWCASE_SEASON": 2022,
    # Zagrożenia pogodowe i walidacja na stacjach Météo-France (step_08)
    "MF_DEPTS": ["32", "47"],             # Gers + Lot-et-Garonne (Condom leży przy granicy departamentów)
    "MF_DIR": "data/08_MeteoFrance",
    "MF_MAX_KM": 30,
    "MF_MAX_STATIONS": 3,
    "MF_MIN_COVERAGE": 0.8,               # udział dni z TN i TX od WX_VAL_START
    "WX_VAL_START": "2016-01-01",
    "WX_CAL_SPLIT_YEAR": 2021,            # próg ERA5 kalibrowany na latach < 2021, oceniany na latach >= 2021
    "WX_REF_MAX_KM": 5.0,                 # stacja referencyjna dla progów winnicy (Condom: 0,2 km); dalsze tylko walidują
    "WX_MIN_CAL_EVENTS": 10,              # min. dni ze zdarzeniem do kalibracji progu (mniej = próg nominalny)
    "WX_MIN_TEST_EVENTS": 10,             # min. dni ze zdarzeniem w latach testowych, żeby podać POD/FAR
    "WX_MIN_CSI_GAIN": 0.05,              # próg skalibrowany tylko, gdy na latach kalibracji poprawia CSI o >= 0,05
    "FROST_SEASON": ("03-15", "05-15"),   # po pąkowaniu winorośli w Gers (przymrozki wiosenne)
    "FROST_TMIN": 0.0,                    # Tmin w klatce 2 m; pąki bywają 1-2 °C zimniejsze
    "HEAT_SEASON": ("06-01", "08-31"),
    "HEAT_TMAX": 35.0,
    # Wyniki
    "DASHBOARD_YEARS": 5,                 # okno wykresów i historii na dashboardzie (od dziś wstecz)
    "OUTPUT_DIR": "data/05_Final_Outputs/agriwatch",
    "BOOTSTRAP_N": 1000,
}

_PATH_KEYS = ("PARCELS_PATH", "AOI_PATH", "ISMN_DIR", "S2_DIR", "S2_MANIFEST", "ERA5_DIR", "SR_MODEL_DIR", "MF_DIR",
              "SR_DIR", "OUTPUT_DIR")


def monitor_config(rt: Dict[str, Any], overrides: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """MONITOR_CONFIG z nadpisaniami; ścieżki względne -> bezwzględne względem PROJECT_DIR."""
    cfg = dict(MONITOR_CONFIG)
    cfg.update(overrides or {})
    for k in _PATH_KEYS:
        if not os.path.isabs(cfg[k]):
            cfg[k] = os.path.join(rt["PROJECT_DIR"], cfg[k])
    cfg["PROJECT_DIR"] = rt["PROJECT_DIR"]
    return cfg


def _station_lonlat(cfg: Dict[str, Any]):
    from step_07_station_pipeline import read_station_metadata
    m = read_station_metadata(os.path.join(cfg["ISMN_DIR"], cfg["NETWORK"], cfg["STATION"]))
    return m["lon"], m["lat"]


def _main_site_lonlat(cfg: Dict[str, Any]):
    import geopandas as gpd
    p = gpd.read_file(cfg["PARCELS_PATH"])
    g = p.loc[p["fid"] == cfg["VINEYARDS"][cfg["MAIN_SITE"]]].to_crs(cfg["EPSG"]).geometry.centroid
    c = g.to_crs(4326).iloc[0]
    return c.x, c.y


def _era5_csv(cfg: Dict[str, Any]) -> str:
    return os.path.join(cfg["ERA5_DIR"], "era5_land_daily.csv")


def task_ingest_s2(rt: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Rastry Sentinel-2 dla AOI (step_01.sync_sentinel2_time_series, jak w v1; dodany filtr sezonu)."""
    import step_01_ingest as s1
    before = set(glob.glob(os.path.join(cfg["S2_DIR"], "S2_L2A_*.tif")))
    aoi, _, _ = s1.load_aoi_geometry(cfg["AOI_PATH"], buffer_m=cfg["AOI_BUFFER_M"])
    s1.sync_sentinel2_time_series(aoi, start_year=cfg["S2_START_YEAR"], output_dir=cfg["S2_DIR"],
                                  manifest_path=cfg["S2_MANIFEST"], cloud_thresh=cfg["S2_CLOUD_MAX_AOI"],
                                  epsg_code=cfg["EPSG"], months=cfg["S2_MONTHS"])
    after = set(glob.glob(os.path.join(cfg["S2_DIR"], "S2_L2A_*.tif")))
    new = len(after - before)
    return {"skipped": new == 0, "message": f"{len(after)} scen na Dysku, {new} nowych"}


def task_ingest_era5(rt: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """ERA5-Land 1991 -> dziś w punkcie winnicy, przyrostowo (cache fragmentów roku)."""
    import step_01_ingest as s1
    lon, lat = _main_site_lonlat(cfg)
    end = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    df = s1.sync_era5_land_point(lat, lon, cfg["ERA5_START"], end, os.path.join(cfg["ERA5_DIR"], "cache"))
    df.to_csv(_era5_csv(cfg), index=False)
    return {"message": f"ERA5-Land: {len(df)} dni do {df['time'].max():%Y-%m-%d}"}


def _sites_rows(sites, cfg: Dict[str, Any]) -> pd.DataFrame:
    g = sites.to_crs(4326)
    c = sites.geometry.centroid.to_crs(4326)
    return pd.DataFrame({
        "site_id": sites["site_id"].to_numpy(), "site_type": sites["site_type"].to_numpy(),
        "name": sites["name"].to_numpy(),
        "network": [cfg["NETWORK"] if t == "station" else "" for t in sites["site_type"]],
        "land_use": ["vineyard" if t == "vineyard" else "station plot" for t in sites["site_type"]],
        "lat": c.y.round(6).to_numpy(), "lon": c.x.round(6).to_numpy(), "geometry_wkt": g.geometry.to_wkt().to_numpy(),
        "footprint": ["inner pixels (1 px edge removed)" if b else "all pixels" for b in sites["inner_buffer"]],
        "area_m2": sites.geometry.area.round(1).to_numpy(), "source": "AgriWatch AOI", "updated_at": _utc_now(),
    })


def _stats_to_obs(recs: List[Dict[str, Any]], run_tag: str,
                  variables: tuple = ("ndvi", "ndmi", "ndre", "crswir", "clear_frac")) -> pd.DataFrame:
    rows = []
    for r in recs:
        for var in variables:
            rows.append({"site_id": r["site_id"], "product": r["product"], "variable": var,
                         "time_utc": r["time"].strftime("%Y-%m-%dT%H:%M:%SZ"), "orbit": 0, "value": r[var],
                         "unit": "1", "n_pixels": r["n_pixels"], "qc_flags": r["px_method"], "calib_id": "",
                         "run_id": run_tag, "ingested_at": _utc_now()})
    return pd.DataFrame(rows)


def _sr_qc_current(obs: pd.DataFrame, variable: str = "sr_ok") -> pd.DataFrame:
    """Wiersze SR_QC bieżącej wersji kontroli (step_03.SR_QC_VERSION) dla jednej zmiennej."""
    import step_03_super_resolve as s3
    m = ((obs["product"] == "SR_QC") & (obs["variable"] == variable)
         & (obs["calib_id"].astype(str) == f"SEN2SRLite_main_{s3.SR_QC_VERSION}"))
    return obs.loc[m]


def _sr_qc_done(obs: pd.DataFrame) -> set:
    """Sceny ocenione bieżącą wersją kontroli SR. Starsze wersje (bez NDMI/NDRE z 2,5 m) są przeliczane raz."""
    return set(_sr_qc_current(obs)["time_utc"].astype(str))


def sr_coverage(rt: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, int]:
    """
    Ile scen sezonu (S2_MONTHS) ma już SR: przetworzone (wiersz SR_QC), przyjęte do detekcji (NDVI S2SR_2.5m),
    w kolejce. Detekcja korzysta tylko z przyjętych; klimatologia anomalii SR jest pełna dopiero bez kolejki.
    """
    import step_04_metrics_alert as s4
    m0, m1 = cfg["S2_MONTHS"]
    keys = set()
    for p in glob.glob(os.path.join(cfg["S2_DIR"], "S2_L2A_*.tif")):
        t = s4.scene_time(p)
        if m0 <= t.month <= m1:
            keys.add(t.strftime("%Y-%m-%dT%H:%M:%SZ"))
    obs = registry_read(rt, "gwl_observations")
    cur = _sr_qc_current(obs)
    done = set(cur["time_utc"].astype(str))
    ok = set(cur.loc[pd.to_numeric(cur["value"], errors="coerce") == 1, "time_utc"].astype(str))
    return {"scenes": len(keys), "sr_done": len(keys & done), "sr_ok": len(keys & ok),
            "remaining": len(keys - done)}


def task_scene_stats(rt: Dict[str, Any], cfg: Dict[str, Any], use_sr: Optional[bool] = None) -> Dict[str, Any]:
    """
    Dla każdej nowej sceny: indeksy obiektów z 10 m; jeśli SR włączony — SEN2SR 2,5 m, kontrola H-SR0/H-SR1,
    indeksy obiektów z 2,5 m tylko dla scen, które przeszły kontrolę. Sceny idą od najnowszej, więc przy limicie
    SR_MAX_SCENES_PER_RUN bieżący status dostaje SR od razu, a historia (klimatologia) uzupełnia się w kolejnych
    uruchomieniach. Postęp zapisywany co 25 scen, więc przerwana sesja Colab wznawia się od miejsca przerwania.
    """
    import step_01_ingest as s1
    import step_03_super_resolve as s3
    import step_04_metrics_alert as s4
    import step_06_dashboard as s6

    use_sr = cfg["USE_SR"] if use_sr is None else use_sr
    clip_dir = os.path.join(cfg["SR_DIR"], s6.SITE_CLIP_DIR, cfg["MAIN_SITE"])

    def site_clip(ndvi, profile, t, res):
        """Wycinek NDVI winnicy do mapy w dashboardzie (mały GeoTIFF int16)."""
        g = state["sites"].loc[state["sites"]["site_id"] == cfg["MAIN_SITE"], "geometry"]
        if len(g):
            s6.save_site_ndvi(np.where(cloud_mask(profile, ndvi.shape) == 0, ndvi, np.nan), profile, g.iloc[0],
                              os.path.join(clip_dir, f"{t:%Y%m%d}_NDVI_{res}.tif"))

    def cloud_mask(profile, shape):
        return cloud if shape == cloud.shape else np.repeat(np.repeat(cloud, 4, 0), 4, 1)
    tag = f"scene_stats_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    scenes = sorted(glob.glob(os.path.join(cfg["S2_DIR"], "S2_L2A_*.tif")))
    obs = registry_read(rt, "gwl_observations")
    done = {p: set(obs.loc[obs["product"] == p, "time_utc"].astype(str)) for p in ("S2_10m", "S2SR_2.5m")}
    done["S2SR_2.5m"] = _sr_qc_done(obs)       # „zrobione” = ocenione bieżącą wersją kontroli (także odrzucone)
    qc_calib = f"SEN2SRLite_main_{s3.SR_QC_VERSION}"
    state = {"sites": None, "model": None, "dev": None, "sr_error": None, "sr_seconds": 0.0}
    sr_cap = cfg["SR_MAX_SCENES_PER_RUN"] if cfg["SR_MAX_SCENES_PER_RUN"] is not None else len(scenes)
    newest = scenes[-1] if scenes else None
    buf: List[Dict[str, Any]] = []
    buf_sr: Dict[tuple, List[Dict[str, Any]]] = {}     # zmienne SR przyjęte przez kontrolę -> rekordy
    qc: List[Dict[str, Any]] = []
    n10 = nsr = nsr_ok = nsr_ok20 = nsr_cr = 0
    showcase = set(cfg["SHOWCASE_MONTHS"])

    def flush():
        if buf:
            registry_upsert(rt, "gwl_observations", _stats_to_obs(buf, tag))
            buf.clear()
        for variables, recs in buf_sr.items():
            if recs:
                registry_upsert(rt, "gwl_observations", _stats_to_obs(recs, tag, variables))
        buf_sr.clear()
        if qc:
            registry_upsert(rt, "gwl_observations", pd.DataFrame(qc))
            qc.clear()

    for path in reversed(scenes):
        t = s4.scene_time(path)
        tkey = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        need10 = tkey not in done["S2_10m"]
        needsr = (use_sr and state["sr_error"] is None and tkey not in done["S2SR_2.5m"]
                  and nsr < sr_cap)
        if not (need10 or needsr):
            continue
        data, prof = s1.read_geotiff_to_numpy(path)
        arr, cloud = data[:10], np.nan_to_num(data[s4.RASTER_CLOUD_BAND], nan=1.0)
        if state["sites"] is None:
            state["sites"] = s4.load_sites(cfg, prof["crs"], _station_lonlat(cfg))
        sites = state["sites"]
        if need10:
            buf.extend(s4.site_stats(arr, cloud, prof, sites, "S2_10m", t))
            site_clip(s4.compute_indices(arr)["ndvi"], prof, t, "10m")
            n10 += 1
        if needsr:
            if state["model"] is None:
                try:
                    state["model"], state["dev"] = s3.load_sen2sr(cfg["SR_MODEL_DIR"])
                except Exception as e:
                    state["sr_error"] = f"{type(e).__name__}: {e}"
                    logger.error(f"SEN2SR niedostępny — SR pominięty (bez zastępstwa interpolacją): {state['sr_error']}")
            if state["model"] is not None:
                t_sr = time.time()
                arr25 = s3.super_resolve(arr, state["model"], state["dev"])
                state["sr_seconds"] += time.time() - t_sr
                chk = s3.sr_checks(arr, arr25, cfg)
                nsr += 1
                idx_ok = chk["sr_ok_indices"]
                qc_vals = {v: chk[v] for v in ("detail_ratio_min", "consistency_rmse_max", "sr_ok",
                                               "detail_ratio_min_20m", "consistency_rmse_max_20m", "sr_ok_20m")}
                for idx in s3.INDEX_BANDS:
                    qc_vals[f"sr_ok_{idx}"] = idx in idx_ok
                    qc_vals[f"{idx}_sr_err"] = chk[f"{idx}_sr_err"]
                for var, val in qc_vals.items():
                    qc.append({"site_id": "AOI", "product": "SR_QC", "variable": var, "time_utc": tkey, "orbit": 0,
                               "value": float(val), "unit": "1", "n_pixels": np.nan, "qc_flags": "",
                               "calib_id": qc_calib, "run_id": tag, "ingested_at": _utc_now()})
                if idx_ok:
                    # Każdy wskaźnik z 2,5 m tylko wtedy, gdy wszystkie jego pasma przeszły kontrolę (INDEX_BANDS)
                    nsr_ok += int("ndvi" in idx_ok)
                    nsr_ok20 += int("ndmi" in idx_ok)
                    nsr_cr += int("crswir" in idx_ok)
                    variables = tuple(idx_ok) + ("clear_frac",)
                    p25 = s3.profile_25m(prof)
                    c25 = np.repeat(np.repeat(cloud, 4, 0), 4, 1)
                    buf_sr.setdefault(variables, []).extend(s4.site_stats(arr25, c25, p25, sites, "S2SR_2.5m", t))
                    if "ndvi" in idx_ok:
                        site_clip(s4.compute_indices(arr25)["ndvi"], p25, t, "2.5m")
                if chk["sr_ok"]:
                    if t.strftime("%Y-%m") in showcase or path == newest:
                        stem = os.path.join(cfg["SR_DIR"], f"{t:%Y%m%d}")
                        s1.write_geotiff(s4.compute_indices(arr25)["ndvi"], p25, stem + "_NDVI_2.5m.tif")
                        s1.write_geotiff(s4.compute_indices(arr)["ndvi"], prof, stem + "_NDVI_10m.tif")
                        s3.plot_sr_comparison(arr, arr25, f"Sentinel-2 {t:%Y-%m-%d}: 10 m vs SEN2SR 2.5 m",
                                              stem + "_comparison.png", sites, prof)
                else:
                    logger.warning(f"{tkey}: SR odrzucony (pasma 10 m: H-SR0={chk['pass_hsr0']}, "
                                   f"H-SR1={chk['pass_hsr1']}, RMSE={chk['consistency_rmse_max']:.4f})")
                rejected = [i for i in s3.INDEX_BANDS if i not in idx_ok]
                if rejected:
                    logger.info(f"{tkey}: z 2,5 m bez {', '.join(rejected)} (pasma poza progiem); "
                                f"przyjęte: {', '.join(idx_ok) or '—'}")
        if (n10 + nsr) % 25 == 0:
            flush()
    flush()
    msg = (f"10 m: {n10} nowych scen; SR: {nsr} scen, NDVI 2,5 m przyjęte w {nsr_ok}, "
           f"NDMI 2,5 m w {nsr_ok20}, CRSWIR 2,5 m w {nsr_cr} (próg 20 m: specyfikacja L2A × {cfg.get('SR_20M_SPEC_FACTOR', 1.0)})")
    if nsr:
        msg += f"; SR {state['sr_seconds'] / nsr:.1f} s/scenę na {state['dev']}"
    cov = sr_coverage(rt, cfg)
    if cov["scenes"]:
        msg += (f"; pokrycie SR (detekcja): {cov['sr_done']}/{cov['scenes']} scen przetworzonych, "
                f"{cov['sr_ok']} przyjętych, {cov['remaining']} w kolejce")
    if state["sr_error"]:
        msg += f"; SR niedostępny: {state['sr_error'][:200]}"
    reg = {"gwl_sites": _sites_rows(state["sites"], cfg)} if state["sites"] is not None else {}
    return {"skipped": n10 + nsr == 0, "message": msg, "registry": reg}


def _veg_anomalies(rt: Dict[str, Any], cfg: Dict[str, Any]) -> pd.DataFrame:
    """Anomalie NDVI i NDMI dla każdego obiektu i produktu (10 m, SR 2,5 m) w sezonie S2_MONTHS."""
    import step_04_metrics_alert as s4
    cols = ["site_id", "product", "index", "time", "value", "clim_mean", "clim_std", "z", "n_ref"]
    obs = registry_read(rt, "gwl_observations")
    obs = obs[obs["product"].isin(["S2_10m", "S2SR_2.5m"])]
    if obs.empty:
        return pd.DataFrame(columns=cols)
    w = obs.pivot_table(index=["site_id", "product", "time_utc"], columns="variable", values="value").reset_index()
    w["time"] = pd.to_datetime(w["time_utc"]).dt.tz_localize(None)
    m0, m1 = cfg["S2_MONTHS"]
    w = w[w["time"].dt.month.between(m0, m1)]
    parts = []
    for (site, prod), g in w.groupby(["site_id", "product"]):
        for idx in ("ndvi", "ndmi", "crswir"):
            if idx not in g or g[idx].isna().all():      # np. NDMI z SR, gdy pasma 20 m nie przeszły kontroli
                continue
            a = s4.scene_anomaly(g, idx, cfg)
            if len(a):
                parts.append(pd.DataFrame({"site_id": site, "product": prod, "index": idx, "time": a["time"].to_numpy(),
                                           "value": a[idx].to_numpy(), "clim_mean": a["clim_mean"].to_numpy(),
                                           "clim_std": a["clim_std"].to_numpy(), "z": a["z"].to_numpy(),
                                           "n_ref": a["n_ref"].to_numpy()}))
    return pd.concat(parts, ignore_index=True) if parts else pd.DataFrame(columns=cols)


def task_anomalies(rt: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Anomalie ERA5 (SMA 0-7 i 0-100 cm, SPI-1, SPI-3), anomalie roślinności i status dekadowy."""
    import step_04_metrics_alert as s4
    os.makedirs(cfg["OUTPUT_DIR"], exist_ok=True)
    era5 = pd.read_csv(_era5_csv(cfg), parse_dates=["time"])
    an = s4.era5_anomalies(era5, cfg)
    veg = _veg_anomalies(rt, cfg)
    veg_status = veg[(veg["index"] == cfg["VEG_INDEX"]) & (veg["product"] == cfg["VEG_PRODUCT"])]
    site_ids = list(cfg["VINEYARDS"]) + [f"{cfg['NETWORK']}_{cfg['STATION']}_poly", f"{cfg['NETWORK']}_{cfg['STATION']}"]
    status = pd.concat([s4.build_status(an, veg_status, sid, cfg, cfg["STATUS_START"]) for sid in site_ids],
                       ignore_index=True)

    daily = pd.concat({k: v[[c for c in ("value", "z", "percentile") if c in v]] for k, v in an.items()}, axis=1)
    daily.to_csv(os.path.join(cfg["OUTPUT_DIR"], "era5_daily_anomalies.csv"))
    veg.to_csv(os.path.join(cfg["OUTPUT_DIR"], "veg_anomalies.csv"), index=False)
    status.to_csv(os.path.join(cfg["OUTPUT_DIR"], "status_dekads.csv"), index=False)

    clim_id = f"{cfg['CLIM_REF'][0][:4]}-{cfg['CLIM_REF'][1][:4]}_doy{cfg['CLIM_HALF_WINDOW_DAYS']}"
    rows = []
    for name, d in an.items():
        d = d.loc[cfg["STATUS_START"]:].copy()
        d["dk"] = s4.dekad_end(pd.Series(d.index)).to_numpy()
        for c in ("clim_mean", "percentile"):
            if c not in d:
                d[c] = np.nan
        agg = d.groupby("dk")[["value", "z", "clim_mean", "percentile"]].mean()
        for dk, r in agg.iterrows():
            rows.append({"site_id": "AOI_ERA5L", "product": name, "date": dk.strftime("%Y-%m-%d"),
                         "value": r["value"], "clim_mean": r["clim_mean"], "z": r["z"],
                         "percentile": r["percentile"], "clim_id": clim_id})
    veg_clim = (f"{'prior' if cfg.get('VEG_CAUSAL', True) else 'other'}_years_doy{cfg['VEG_HALF_WINDOW_DAYS']}"
                f"{'_track' if cfg.get('VEG_BY_TRACK', True) else ''}{'_tz' if cfg.get('VEG_PREDICTIVE_Z', True) else ''}")
    for r in veg.itertuples():
        rows.append({"site_id": r.site_id, "product": f"{r.product}_{r.index.upper()}",
                     "date": pd.Timestamp(r.time).strftime("%Y-%m-%d"), "value": r.value,
                     "clim_mean": r.clim_mean, "z": r.z, "clim_id": veg_clim})
    anomalies = pd.DataFrame(rows).drop_duplicates(["site_id", "product", "date"], keep="last")
    cur = status[status["site_id"] == cfg["MAIN_SITE"]].iloc[-1]
    msg = f"{cfg['MAIN_SITE']} {cur['date']}: {cur['cdi_class']} ({cur['reason_codes']})"
    if cfg["VEG_PRODUCT"] == "S2SR_2.5m":
        cov = sr_coverage(rt, cfg)
        if cov["remaining"]:
            msg += (f"; UWAGA: SR niepełny ({cov['remaining']} z {cov['scenes']} scen w kolejce) — klimatologia "
                    f"anomalii 2,5 m jest krótsza, dopóki task_scene_stats nie przetworzy wszystkich scen")
        if veg_status.empty:
            msg += "; brak anomalii NDVI 2,5 m — status bez warstwy roślinności (alert niemożliwy)"
    return {"message": msg,
            "registry": {"gwl_anomalies": anomalies, "gwl_status": status}}


def task_validate(rt: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Błąd anomalii względem profilu glebowego ISMN Condom (step_07.validate_anomalies)."""
    import step_07_station_pipeline as s7
    era5 = pd.read_csv(_era5_csv(cfg), parse_dates=["time"])
    veg = pd.read_csv(os.path.join(cfg["OUTPUT_DIR"], "veg_anomalies.csv"), parse_dates=["time"])
    status = pd.read_csv(os.path.join(cfg["OUTPUT_DIR"], "status_dekads.csv"))
    overrides = {"PROJECT_DIR": cfg["PROJECT_DIR"], "NETWORK": cfg["NETWORK"], "STATION": cfg["STATION"],
                 "BOOTSTRAP_N": cfg["BOOTSTRAP_N"], "STATION_BUFFER_M": cfg["STATION_BUFFER_M"]}
    val = s7.validate_anomalies(era5, veg, status, overrides, cfg, list(cfg["VINEYARDS"]))
    val.to_csv(os.path.join(cfg["OUTPUT_DIR"], "validation_anomalies.csv"), index=False)
    best = val[(val["product"] == "ERA5L_SM_RZ") & (val["segment"] == "anomaly_clim")]
    msg = f"{len(val)} metryk" + (f"; R anomalii 0-100 cm vs 20-30 cm = {best['value'].iat[0]:.2f}" if len(best) else "")
    return {"message": msg, "registry": {"gwl_validation_metrics": val}}


def task_weather(rt: Dict[str, Any], cfg: Dict[str, Any], fetch: bool = True) -> Dict[str, Any]:
    """
    Przymrozki i upały dla winnicy (ERA5-Land) + walidacja ERA5 (Tmin, Tmax, opad, SPI) na najbliższych stacjach
    Météo-France. ERA5-Land jest pobierany w punkcie każdej stacji (cache). Wyniki: validation_weather.csv,
    weather_hazards.csv, hazard_summary.csv; metryki do gwl_validation_metrics.
    """
    import step_01_ingest as s1
    import step_08_weather as s8
    os.makedirs(cfg["OUTPUT_DIR"], exist_ok=True)
    lon, lat = _main_site_lonlat(cfg)
    paths = s8.download_mf(cfg["MF_DEPTS"], cfg["MF_DIR"]) if fetch else \
        sorted(glob.glob(os.path.join(cfg["MF_DIR"], "Q_*_RR-T-Vent.csv.gz")))
    mf = s8.read_mf(paths, cfg["CLIM_REF"][0])
    stations = s8.select_stations(mf, lat, lon, cfg) if len(mf) else pd.DataFrame()
    era_by = {}
    end = pd.Timestamp.now(tz="UTC").strftime("%Y-%m-%d")
    for st in stations.itertuples():
        cache = os.path.join(cfg["MF_DIR"], f"era5_{st.num_poste}")
        if fetch:
            era_by[st.num_poste] = s1.sync_era5_land_point(st.lat, st.lon, cfg["CLIM_REF"][0], end, cache)
        elif os.path.isdir(cache):
            fr = [pd.read_csv(p, parse_dates=["time"]) for p in sorted(glob.glob(os.path.join(cache, "*.csv")))]
            era_by[st.num_poste] = pd.concat(fr, ignore_index=True).drop_duplicates("time") if fr else pd.DataFrame()
    val = s8.validate_weather(stations, mf, era_by, cfg) if len(stations) else pd.DataFrame()
    val.to_csv(os.path.join(cfg["OUTPUT_DIR"], "validation_weather.csv"), index=False)
    stations.to_csv(os.path.join(cfg["OUTPUT_DIR"], "mf_stations.csv"), index=False)

    era5 = pd.read_csv(_era5_csv(cfg), parse_dates=["time"])
    thr = s8.calibrated_thresholds(val, stations, cfg)
    if "t2m_max_c" not in era5:
        era5["t2m_max_c"] = np.nan
    hz = s8.weather_hazards(era5, cfg, thr)
    hz.to_csv(os.path.join(cfg["OUTPUT_DIR"], "weather_hazards.csv"))
    summ = s8.hazard_summary(hz, cfg, cfg["DASHBOARD_YEARS"])
    summ.to_csv(os.path.join(cfg["OUTPUT_DIR"], "hazard_summary.csv"), index=False)
    with open(os.path.join(cfg["OUTPUT_DIR"], "hazard_thresholds.json"), "w") as f:
        json.dump(thr, f)
    msg = (f"{len(stations)} stacji MF ({', '.join(f'{r.name} {r.dist_km:.0f} km' for r in stations.itertuples())}); "
           f"progi ERA5: przymrozek Tmin ≤ {thr['frost']:+.2f} °C ({thr['frost_source']}), "
           f"upał Tmax ≥ {thr['heat']:.2f} °C ({thr['heat_source']}); "
           f"{len(val)} metryk")
    out = {"message": msg}
    if len(val):
        out["registry"] = {"gwl_validation_metrics": val}
    return out


def task_bulletin(rt: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """Biuletyn dla winnicy: bulletin.md, wykresy, agriwatch_latest.json (do publikacji na stronie)."""
    import step_04_metrics_alert as s4
    status = pd.read_csv(os.path.join(cfg["OUTPUT_DIR"], "status_dekads.csv"))
    veg = pd.read_csv(os.path.join(cfg["OUTPUT_DIR"], "veg_anomalies.csv"), parse_dates=["time"])
    vpath = os.path.join(cfg["OUTPUT_DIR"], "validation_anomalies.csv")
    val = pd.read_csv(vpath) if os.path.exists(vpath) else pd.DataFrame()
    sites = registry_read(rt, "gwl_sites")
    s = sites[sites["site_id"] == cfg["MAIN_SITE"]]
    site = s.iloc[0].to_dict() if len(s) else {"site_id": cfg["MAIN_SITE"], "name": cfg["MAIN_SITE"]}
    veg_main = veg[veg["index"] == cfg["VEG_INDEX"]] if len(veg) else veg
    paths = s4.build_bulletin(status, veg_main, val, site, dict(cfg, SR_COVERAGE=sr_coverage(rt, cfg)),
                              cfg["OUTPUT_DIR"])
    return {"message": ", ".join(os.path.relpath(p, cfg["PROJECT_DIR"]) for p in paths.values())}


def task_dashboard(rt: Dict[str, Any], cfg: Dict[str, Any], forecast: bool = True) -> Dict[str, Any]:
    """Dashboard winnicy (step_06): dashboard.html w OUTPUT_DIR — mapa NDVI, status, ryzyko, pogoda, wiarygodność."""
    import step_06_dashboard as s6
    path = s6.build_dashboard(rt, cfg, forecast=forecast)
    return {"message": os.path.relpath(path, cfg["PROJECT_DIR"])}


def task_summary(rt: Dict[str, Any], cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    Raport z uruchomienia do analizy po fakcie: run_summary.md (do wklejenia) i run_summary.json w OUTPUT_DIR.
    Zawiera wersje (commit, pakiety, GPU), konfigurację, pokrycie danych, statystyki kontroli SR, status per rok,
    walidację i ostatnie uruchomienia z błędami. Bez danych surowych (kilka kB).
    """
    import importlib.metadata as md
    import step_03_super_resolve as s3

    def ver(pkg):
        try:
            return md.version(pkg)
        except Exception:
            return None

    try:
        import torch
        gpu = torch.cuda.get_device_name(0) if torch.cuda.is_available() else "cpu"
    except Exception:
        gpu = "brak torch"
    out = cfg["OUTPUT_DIR"]
    obs = registry_read(rt, "gwl_observations")
    scenes = sorted(glob.glob(os.path.join(cfg["S2_DIR"], "S2_L2A_*.tif")))
    era5_path = _era5_csv(cfg)
    era5_last = str(pd.read_csv(era5_path, usecols=["time"])["time"].max())[:10] if os.path.exists(era5_path) else None

    qc = obs[(obs["product"] == "SR_QC") & (obs["calib_id"].astype(str) == f"SEN2SRLite_main_{s3.SR_QC_VERSION}")]
    qcw = qc.pivot_table(index="time_utc", columns="variable", values="value") if len(qc) else pd.DataFrame()
    sr = {"qc_version": s3.SR_QC_VERSION, "scenes_checked": int(len(qcw)), **sr_coverage(rt, cfg)}
    for col in qcw.columns:
        v = pd.to_numeric(qcw[col], errors="coerce").dropna()
        if len(v):
            sr[col] = ({"accept_rate": round(float(v.mean()), 3)} if col.startswith("sr_ok")
                       else {"median": round(float(v.median()), 4), "p90": round(float(v.quantile(0.9)), 4)})

    st_path = os.path.join(out, "status_dekads.csv")
    status, per_year, current = {}, {}, None
    if os.path.exists(st_path):
        st = pd.read_csv(st_path)
        st = st[st["site_id"] == cfg["MAIN_SITE"]]
        if len(st):
            current = st.sort_values("date").iloc[-1][["date", "cdi_class", "confidence", "reason_codes"]].to_dict()
            st["year"] = st["date"].str[:4]
            per_year = st.pivot_table(index="year", columns="cdi_class", values="date", aggfunc="count",
                                      fill_value=0).astype(int)
            status = per_year.to_dict(orient="index")
    vpath = os.path.join(out, "validation_anomalies.csv")
    val = pd.read_csv(vpath) if os.path.exists(vpath) else pd.DataFrame()
    runs = run_history(rt, n=15)

    def csv_or_empty(name):
        q = os.path.join(out, name)
        return pd.read_csv(q) if os.path.exists(q) else pd.DataFrame()
    wval, hsum, mfst = (csv_or_empty("validation_weather.csv"), csv_or_empty("hazard_summary.csv"),
                        csv_or_empty("mf_stations.csv"))
    thr_path = os.path.join(out, "hazard_thresholds.json")
    thr = json.load(open(thr_path)) if os.path.exists(thr_path) else {}

    summary = {
        "generated_utc": _utc_now(), "git_commit": rt.get("GIT_COMMIT", ""), "device": gpu,
        "versions": {p: ver(p) for p in ("numpy", "pandas", "rasterio", "geopandas", "earthengine-api", "torch",
                                         "sen2sr", "mlstac", "scipy")},
        "config": {k: cfg[k] for k in ("MAIN_SITE", "VEG_PRODUCT", "VEG_INDEX", "S2_MONTHS", "S2_CLOUD_MAX_AOI",
                                       "THR_SPI1", "THR_SPI3", "THR_SMA", "THR_VEG", "SR_MAX_CONSISTENCY_RMSE",
                                       "SR_20M_SPEC_FACTOR", "SR_MIN_DETAIL_RATIO", "SR_MAX_SCENES_PER_RUN")},
        "data": {"s2_scenes": len(scenes),
                 "s2_first": os.path.basename(scenes[0])[7:15] if scenes else None,
                 "s2_last": os.path.basename(scenes[-1])[7:15] if scenes else None, "era5_last_day": era5_last},
        "sr": sr, "status_current": current, "status_per_year": status,
        "validation": val.round(3).to_dict(orient="records") if len(val) else [],
        "weather": {"stations": mfst.round(3).to_dict(orient="records"), "thresholds": thr,
                    "validation": wval.round(3).to_dict(orient="records") if len(wval) else [],
                    "hazards_per_year": hsum.round(1).to_dict(orient="records") if len(hsum) else []},
        "runs": runs.to_dict(orient="records"),
    }
    js = os.path.join(out, "run_summary.json")
    with open(js, "w", encoding="utf-8") as f:
        json.dump(summary, f, indent=1, ensure_ascii=False, default=str)

    def table(df):
        if not len(df):
            return "(brak)"
        cols = [str(c) for c in df.columns]
        rows = ["| " + " | ".join(cols) + " |", "|" + "---|" * len(cols)]
        rows += ["| " + " | ".join("" if pd.isna(v) else str(v) for v in r) + " |" for r in df.itertuples(index=False)]
        return "\n".join(rows)
    srt = pd.DataFrame([{"zmienna": k, **(v if isinstance(v, dict) else {"wartość": v})} for k, v in sr.items()])
    md_txt = f"""# AgriWatch — raport z uruchomienia {summary['generated_utc']}

Commit `{summary['git_commit']}` · urządzenie: {gpu} · sen2sr {summary['versions']['sen2sr']} · torch {summary['versions']['torch']}

## Dane
{json.dumps(summary['data'], ensure_ascii=False)}

## Konfiguracja
{json.dumps(summary['config'], ensure_ascii=False, default=str)}

## Super-resolution (kontrola {s3.SR_QC_VERSION})
{table(srt)}

## Status bieżący
{json.dumps(current, ensure_ascii=False, default=str)}

## Status: liczba dekad w klasach per rok
{table(per_year.reset_index()) if len(status) else "(brak)"}

## Walidacja
{table(val.round(3)) if len(val) else "(brak)"}

## Pogoda: stacje Météo-France i walidacja ERA5-Land
Stacje:
{table(mfst.round(3))}

Progi ERA5 dla zagrożeń: {json.dumps(thr)}

{table(wval.drop(columns=[c for c in ("site_id", "ci_low", "ci_high", "date_from", "date_to") if c in wval]).round(3)) if len(wval) else "(brak)"}

## Zagrożenia pogodowe w winnicy (ERA5-Land, progi skalibrowane)
{table(hsum.round(1))}

## Ostatnie uruchomienia
{table(runs)}
"""
    mdp = os.path.join(out, "run_summary.md")
    with open(mdp, "w", encoding="utf-8") as f:
        f.write(md_txt)
    return {"message": f"{os.path.relpath(mdp, cfg['PROJECT_DIR'])} ({len(md_txt) // 1024} kB)"}


def run_monitoring(rt: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None, ingest: bool = True) -> None:
    """Wszystkie zadania po kolei (każde zapisane w gwl_runs; błąd jednego nie zatrzymuje kolejnych)."""
    cfg = cfg or monitor_config(rt)
    if ingest:
        run_task(rt, "ingest_s2", task_ingest_s2, rt, cfg)
        run_task(rt, "ingest_era5", task_ingest_era5, rt, cfg)
    run_task(rt, "scene_stats", task_scene_stats, rt, cfg)
    run_task(rt, "anomalies", task_anomalies, rt, cfg)
    run_task(rt, "validate", task_validate, rt, cfg)
    run_task(rt, "weather", task_weather, rt, cfg, fetch=ingest)
    run_task(rt, "bulletin", task_bulletin, rt, cfg)
    run_task(rt, "dashboard", task_dashboard, rt, cfg)
    run_task(rt, "summary", task_summary, rt, cfg)


# ==============================================================================
# III. TEST OFFLINE (bez GEE i bez GPU): syntetyczne rastry i ERA5 + prawdziwe dane ISMN i działki
# ==============================================================================

def _selftest(out_dir: str) -> None:
    import shutil
    import geopandas as gpd
    from rasterio.transform import from_origin
    import step_01_ingest as s1
    import step_03_super_resolve as s3

    project = os.path.dirname(os.path.abspath(__file__))
    shutil.rmtree(out_dir, ignore_errors=True)
    rt = {"PROJECT_DIR": project, "REGISTRY_DIR": os.path.join(out_dir, "registry"), "GIT_COMMIT": "selftest"}
    cfg = monitor_config(rt, {"S2_DIR": os.path.join(out_dir, "s2"), "ERA5_DIR": os.path.join(out_dir, "era5"),
                              "OUTPUT_DIR": os.path.join(out_dir, "out"), "SR_DIR": os.path.join(out_dir, "sr"),
                              "BOOTSTRAP_N": 200, "USE_SR": True, "SR_MAX_SCENES_PER_RUN": None,
                              "SR_MODEL_DIR": os.path.join(out_dir, "model"), "MF_DIR": os.path.join(out_dir, "mf")})
    rng = np.random.default_rng(1)

    # Syntetyczne ERA5-Land 1991-2024: cykl roczny + szum AR(1); opad gamma
    days = pd.date_range("1991-01-01", "2024-12-31", freq="D")
    doy = days.dayofyear.to_numpy()
    seas = np.cos(2 * np.pi * (doy - 30) / 365.25)
    ar = np.zeros(len(days))
    for i in range(1, len(days)):
        ar[i] = 0.97 * ar[i - 1] + rng.normal(0, 0.01)
    era5 = pd.DataFrame({"time": days, "sm_l1": 0.25 + 0.08 * seas + ar, "sm_l2": 0.27 + 0.06 * seas + 0.8 * ar,
                         "sm_l3": 0.30 + 0.04 * seas + 0.6 * ar, "precip_mm": rng.gamma(0.4, 6.0, len(days)),
                         "t2m_min_c": 8 - 6 * seas + rng.normal(0, 3, len(days)), "t2m_c": 13 - 7 * seas,
                         "t2m_max_c": 18 - 9 * seas + rng.normal(0, 3, len(days))})
    os.makedirs(cfg["ERA5_DIR"], exist_ok=True)
    era5.to_csv(_era5_csv(cfg), index=False)
    # Syntetyczna stacja Météo-France 5 km od winnicy (Tmin 1 °C chłodniej niż ERA5) + ERA5 w jej punkcie (cache)
    import gzip
    os.makedirs(os.path.join(cfg["MF_DIR"], "era5_32999001"), exist_ok=True)
    mf = pd.DataFrame({"NUM_POSTE": "32999001", "NOM_USUEL": "SELFTEST", "LAT": 43.98, "LON": 0.37, "ALTI": 100,
                       "AAAAMMJJ": days.strftime("%Y%m%d").astype(int), "RR": (era5["precip_mm"] * 1.1).round(1),
                       "QRR": 1, "TN": (era5["t2m_min_c"] - 1 + rng.normal(0, 1, len(days))).round(1), "QTN": 1,
                       "TX": (era5["t2m_max_c"] + rng.normal(0, 1, len(days))).round(1), "QTX": 1})
    with gzip.open(os.path.join(cfg["MF_DIR"], "Q_32_previous-1950-2023_RR-T-Vent.csv.gz"), "wt") as f:
        mf.to_csv(f, sep=";", index=False)
    era5.to_csv(os.path.join(cfg["MF_DIR"], "era5_32999001", "era5land_19910101_20250101.csv"), index=False)
    ar_s = pd.Series(ar, index=days)

    # Syntetyczne sceny S-2 (12 pasm jak w step_01) na siatce obejmującej winnicę i stację
    parcels = gpd.read_file(cfg["PARCELS_PATH"]).to_crs(cfg["EPSG"])
    x0, y0, x1, y1 = parcels.total_bounds
    x0, y1 = np.floor(x0 / 10) * 10 - 200, np.ceil(y1 / 10) * 10 + 200
    w, h = int((x1 - x0 + 400) / 10) + 1, int((y1 - y0 + 400) / 10) + 1
    prof = {"driver": "GTiff", "crs": f"EPSG:{cfg['EPSG']}", "transform": from_origin(x0, y1, 10, 10),
            "width": w, "height": h, "count": 12, "dtype": "float32"}
    os.makedirs(cfg["S2_DIR"], exist_ok=True)
    for year in range(2016, 2025):
        for month in range(4, 11):
            for day in (5, 20):
                t = pd.Timestamp(year=year, month=month, day=day, hour=10, minute=50)
                anom = float(ar_s.loc[t.normalize()])
                ndvi_target = 0.35 + 0.25 * np.sin(np.pi * (t.dayofyear - 90) / 200) + 2.0 * anom
                red = np.full((h, w), 0.08) + rng.normal(0, 0.005, (h, w))
                nir = red * (1 + ndvi_target) / (1 - ndvi_target)
                arr = np.stack([red * 0.8, red * 0.9, red, red * 1.5, nir * 0.7, nir * 0.9, nir, nir,
                                np.full((h, w), 0.25 - anom), np.full((h, w), 0.18 - anom),
                                np.zeros((h, w)), np.full((h, w), 4.0)]).astype("float32")
                s1.write_geotiff(arr, prof, os.path.join(cfg["S2_DIR"], f"S2_L2A_{t:%Y%m%d_%H%M%S}.tif"))

    # Kontrola SR bez modelu: interpolacja ma być odrzucona (H-SR0), SR ze szczegółem i spójny — przyjęty
    lo = np.stack([np.clip(rng.normal(0.1, 0.03, (64, 64)), 0.01, 1) for _ in range(10)]).astype("float32")
    fake_interp = s3.bicubic_upsample(lo)
    detail = rng.normal(0, 0.02, fake_interp.shape)
    fake_sr = (np.repeat(np.repeat(lo, 4, 1), 4, 2) + detail
               - np.repeat(np.repeat(s3.block_mean(detail), 4, 1), 4, 2)).astype("float32")
    assert not s3.sr_checks(lo, fake_interp, cfg)["pass_hsr0"], "Interpolacja nie może przejść H-SR0"
    chk = s3.sr_checks(lo, fake_sr, cfg)
    assert chk["sr_ok"], chk
    # Pasma 20 m jak z eksportu GEE (piksele 20 m powielone 2x2 na siatce 10 m, przesunięte o 1 px).
    # SR z detalem wewnątrz pikseli 20 m: spójny w 20 m, ale w siatce 10 m różni się od wejścia o ten detal.
    lo20, sr20 = lo.copy(), fake_sr.copy()
    for name in s3.BANDS_20M:
        i = s3.SEN2SR_BANDS.index(name)
        c = np.clip(rng.normal(0.25, 0.05, (33, 33)), 0.01, 1)
        noise = rng.normal(0, 0.06, (264, 264))
        noise -= np.repeat(np.repeat(s3.block_mean(noise, 8), 8, 0), 8, 1)
        lo20[i] = np.repeat(np.repeat(c, 2, 0), 2, 1)[1:65, 1:65]
        sr20[i] = (np.repeat(np.repeat(c, 8, 0), 8, 1) + noise)[4:260, 4:260]
    b11 = s3.SEN2SR_BANDS.index("B11")
    assert s3._band_checks(lo20[b11], sr20[b11], native_20m=False)[1] > cfg["SR_MAX_CONSISTENCY_RMSE"]
    assert s3.grid20_offset(lo20[s3.SEN2SR_BANDS.index("B11")]) == (1, 1)
    chk20 = s3.sr_checks(lo20, sr20, cfg)
    assert chk20["sr_ok"] and chk20["sr_ok_20m"], chk20
    # Próg pasm 20 m wg specyfikacji L2A (0,05·ρ + 0,005): B05 z błędem 0,015 (> 0,01, ale < specyfikacja) przechodzi,
    # B12 z błędem 0,03 nie; decyzja per wskaźnik: NDRE (B8A, B05) i NDMI (B8A, B11) tak, grupa 20 m jako całość nie.
    sr20b = sr20.copy()
    sr20b[s3.SEN2SR_BANDS.index("B05")] += 0.015
    sr20b[s3.SEN2SR_BANDS.index("B12")] += 0.03
    chk20b = s3.sr_checks(lo20, sr20b, cfg)
    assert set(chk20b["sr_ok_indices"]) == {"ndvi", "ndmi", "ndre"} and not chk20b["sr_ok_20m"], chk20b
    assert 0 < chk20b["ndre_sr_err"] < 0.1, chk20b["ndre_sr_err"]
    assert "crswir" in s3.sr_checks(lo20, sr20, cfg)["sr_ok_indices"], "CRSWIR z 2,5 m przy spójnych B8A, B11, B12"
    print("[OK] Kontrola SR: interpolacja odrzucona, spójny SR przyjęty (pasma 10 m i 20 m w natywnej rozdzielczości).")

    # Atrapa SEN2SR (bez GPU i pobierania modelu): powielenie pikseli 4x4 + szczegół o zerowej średniej w bloku,
    # więc kontrola H-SR0/H-SR1 przechodzi, a NDVI 2,5 m = NDVI 10 m + szum. Jedna scena celowo zepsuta (odrzucona).
    real_load, real_sr = s3.load_sen2sr, s3.super_resolve
    bad = {"n": 0}

    def fake_super_resolve(arr10, model, device, overlap=32):
        up = np.repeat(np.repeat(arr10, 4, 1), 4, 2)
        d = rng.normal(0, 0.01, up.shape)
        out = up + d - np.repeat(np.repeat(s3.block_mean(d), 4, 1), 4, 2)
        bad["n"] += 1
        if bad["n"] == 2:
            out[:4] += 0.05                       # zła radiometria pasm 10 m -> scena poza detekcją
        return out.astype("float32")

    s3.load_sen2sr = lambda model_dir, device=None: ("fake", "cpu")
    s3.super_resolve = fake_super_resolve
    try:
        for name, fn in (("scene_stats", task_scene_stats), ("anomalies", task_anomalies),
                         ("validate", task_validate),
                         ("weather", lambda r, c: task_weather(r, c, fetch=False)), ("bulletin", task_bulletin),
                         ("dashboard", lambda r, c: task_dashboard(r, c, forecast=False)),
                         ("summary", task_summary)):
            run_task(rt, name, fn, rt, cfg, raise_errors=True)
        res = run_task(rt, "scene_stats_repeat", task_scene_stats, rt, cfg, raise_errors=True)
    finally:
        s3.load_sen2sr, s3.super_resolve = real_load, real_sr
    assert res["skipped"], "Drugie uruchomienie nie powinno przetwarzać scen ponownie (także odrzuconych przez SR)"
    cov = sr_coverage(rt, cfg)
    assert cov["remaining"] == 0 and cov["sr_ok"] == cov["scenes"] - 1, cov
    st_main = registry_read(rt, "gwl_status")
    st_main = st_main[st_main["site_id"] == "VINEYARD_06"]
    assert set(st_main["veg_source"].dropna()) == {"S2SR_2.5m"}, "Detekcja ma używać wyłącznie NDVI 2,5 m"
    print(f"[OK] Detekcja na SR 2,5 m: {cov['sr_ok']}/{cov['scenes']} scen przyjętych, 1 odrzucona.")

    st = registry_read(rt, "gwl_status")
    assert "VINEYARD_06" in set(st["site_id"]) and st["cdi_class"].notna().all()
    val = registry_read(rt, "gwl_validation_metrics")
    assert len(val) >= 5, val
    with open(os.path.join(cfg["OUTPUT_DIR"], "agriwatch_latest.json"), encoding="utf-8") as f:
        js = json.load(f)
    assert js["current"]["cdi_class"] in ("normal", "watch", "warning", "alert", "recovery")
    dash = open(os.path.join(cfg["OUTPUT_DIR"], "dashboard.html"), encoding="utf-8").read()
    n_layers = dash.count('"png": "')
    assert "Ryzyko suszy" in dash and "L.imageOverlay" in dash and n_layers >= 5, n_layers
    assert "Przymrozki i upały" in dash and "Météo-France" in dash and "Ostatnie 5 lat" in dash
    wv = pd.read_csv(os.path.join(cfg["OUTPUT_DIR"], "validation_weather.csv"))
    b = wv[(wv["product"] == "ERA5L_TMIN") & (wv["period"] == "all") & (wv["metric"] == "bias")]["value"].iat[0]
    assert abs(b - 1.0) < 0.1, b                    # ERA5 cieplejsze o 1 °C od stacji
    thr = json.load(open(os.path.join(cfg["OUTPUT_DIR"], "hazard_thresholds.json")))
    assert 0.0 <= thr["frost"] < 2.0 and thr["reference"] == "MF_32999001", thr
    print(f"[OK] Pogoda: {len(wv)} metryk MF, progi {thr}")
    print(f"[OK] Dashboard: {n_layers} dat mapy NDVI, {len(dash) // 1024} kB")
    summ = json.load(open(os.path.join(cfg["OUTPUT_DIR"], "run_summary.json"), encoding="utf-8"))
    assert summ["sr"]["scenes_checked"] == 126 and summ["status_current"] and summ["validation"], summ["sr"]
    print(f"[OK] Raport z uruchomienia: {len(open(os.path.join(cfg['OUTPUT_DIR'], 'run_summary.md'), encoding='utf-8').read()) // 1024} kB")
    print("[OK] Selftest monitoringu. Status:", js["current"]["date"], js["current"]["cdi_class"])
    print(val[["product", "reference", "segment", "subset", "metric", "value", "n"]].round(3).to_string(index=False))


if __name__ == "__main__":
    import argparse
    ap = argparse.ArgumentParser(description="AgriWatch: test offline monitoringu")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--out", default="data/_selftest_monitor")
    a = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
    if a.selftest:
        _selftest(a.out)
