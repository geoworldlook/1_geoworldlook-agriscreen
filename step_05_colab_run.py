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
        "columns": ["site_id", "date", "cdi_level", "cdi_class", "action", "spi1", "spi3", "sma_rz", "veg_z",
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
    "VEG_PRODUCT": "S2_10m",              # produkt do statusu; SR wchodzi tylko, jeśli walidacja pokaże przewagę
    "VEG_HALF_WINDOW_DAYS": 15,
    "VEG_MIN_REF": 5,
    "VEG_MIN_CLEAR_FRAC": 0.9,
    "VEG_MAX_AGE_DAYS": 30,
    # Progi statusu (EDO CDI)
    "THR_SPI1": -2.0, "THR_SPI3": -1.0, "THR_SMA": -1.0, "THR_VEG": -1.0,
    "STATUS_START": "2016-01-01",
    # Super-resolution
    "USE_SR": True,
    "SR_MODEL_DIR": "data/models/SEN2SRLite_main",
    "SR_MAX_SCENES_PER_RUN": 150,
    "SR_MIN_DETAIL_RATIO": 0.02,          # H-SR0: v1 (interpolacja) = 0,005
    "SR_MAX_CONSISTENCY_RMSE": 0.01,      # H-SR1: reflektancja, w natywnej rozdzielczości pasma (10 m / 20 m)
    "SR_DIR": "data/03_SR_2.5m",
    "SHOWCASE_MONTHS": ["2022-07", "2022-08"],
    "SHOWCASE_SEASON": 2022,
    # Wyniki
    "OUTPUT_DIR": "data/05_Final_Outputs/agriwatch",
    "BOOTSTRAP_N": 1000,
}

_PATH_KEYS = ("PARCELS_PATH", "AOI_PATH", "ISMN_DIR", "S2_DIR", "S2_MANIFEST", "ERA5_DIR", "SR_MODEL_DIR",
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
                  variables: tuple = ("ndvi", "ndmi", "ndre", "clear_frac")) -> pd.DataFrame:
    rows = []
    for r in recs:
        for var in variables:
            rows.append({"site_id": r["site_id"], "product": r["product"], "variable": var,
                         "time_utc": r["time"].strftime("%Y-%m-%dT%H:%M:%SZ"), "orbit": 0, "value": r[var],
                         "unit": "1", "n_pixels": r["n_pixels"], "qc_flags": r["px_method"], "calib_id": "",
                         "run_id": run_tag, "ingested_at": _utc_now()})
    return pd.DataFrame(rows)


def task_scene_stats(rt: Dict[str, Any], cfg: Dict[str, Any], use_sr: Optional[bool] = None) -> Dict[str, Any]:
    """
    Dla każdej nowej sceny: indeksy obiektów z 10 m; jeśli SR włączony — SEN2SR 2,5 m, kontrola H-SR0/H-SR1,
    indeksy obiektów z 2,5 m tylko dla scen, które przeszły kontrolę. Postęp zapisywany co 25 scen,
    więc przerwana sesja Colab wznawia się od miejsca przerwania.
    """
    import step_01_ingest as s1
    import step_03_super_resolve as s3
    import step_04_metrics_alert as s4

    use_sr = cfg["USE_SR"] if use_sr is None else use_sr
    tag = f"scene_stats_{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}"
    scenes = sorted(glob.glob(os.path.join(cfg["S2_DIR"], "S2_L2A_*.tif")))
    obs = registry_read(rt, "gwl_observations")
    done = {p: set(obs.loc[obs["product"] == p, "time_utc"].astype(str)) for p in ("S2_10m", "S2SR_2.5m")}
    state = {"sites": None, "model": None, "dev": None, "sr_error": None}
    buf: List[Dict[str, Any]] = []
    buf_sr: Dict[tuple, List[Dict[str, Any]]] = {}     # zmienne SR przyjęte przez kontrolę -> rekordy
    qc: List[Dict[str, Any]] = []
    n10 = nsr = nsr_ok = nsr_ok20 = 0
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

    for k, path in enumerate(scenes):
        t = s4.scene_time(path)
        tkey = t.strftime("%Y-%m-%dT%H:%M:%SZ")
        need10 = tkey not in done["S2_10m"]
        needsr = (use_sr and state["sr_error"] is None and tkey not in done["S2SR_2.5m"]
                  and nsr < cfg["SR_MAX_SCENES_PER_RUN"])
        if not (need10 or needsr):
            continue
        data, prof = s1.read_geotiff_to_numpy(path)
        arr, cloud = data[:10], np.nan_to_num(data[s4.RASTER_CLOUD_BAND], nan=1.0)
        if state["sites"] is None:
            state["sites"] = s4.load_sites(cfg, prof["crs"], _station_lonlat(cfg))
        sites = state["sites"]
        if need10:
            buf.extend(s4.site_stats(arr, cloud, prof, sites, "S2_10m", t))
            n10 += 1
        if needsr:
            if state["model"] is None:
                try:
                    state["model"], state["dev"] = s3.load_sen2sr(cfg["SR_MODEL_DIR"])
                except Exception as e:
                    state["sr_error"] = f"{type(e).__name__}: {e}"
                    logger.error(f"SEN2SR niedostępny — SR pominięty (bez zastępstwa interpolacją): {state['sr_error']}")
            if state["model"] is not None:
                arr25 = s3.super_resolve(arr, state["model"], state["dev"])
                chk = s3.sr_checks(arr, arr25, cfg)
                nsr += 1
                for var in ("detail_ratio_min", "consistency_rmse_max", "sr_ok",
                            "detail_ratio_min_20m", "consistency_rmse_max_20m", "sr_ok_20m"):
                    qc.append({"site_id": "AOI", "product": "SR_QC", "variable": var, "time_utc": tkey, "orbit": 0,
                               "value": float(chk[var]), "unit": "1", "n_pixels": np.nan, "qc_flags": "",
                               "calib_id": "SEN2SRLite_main", "run_id": tag, "ingested_at": _utc_now()})
                if chk["sr_ok"]:
                    # NDVI z SR tylko po kontroli grupy 10 m; NDMI i NDRE (pasma 20 m) tylko po kontroli grupy 20 m
                    nsr_ok += 1
                    nsr_ok20 += int(chk["sr_ok_20m"])
                    variables = ("ndvi", "ndmi", "ndre", "clear_frac") if chk["sr_ok_20m"] else ("ndvi", "clear_frac")
                    p25 = s3.profile_25m(prof)
                    c25 = np.repeat(np.repeat(cloud, 4, 0), 4, 1)
                    buf_sr.setdefault(variables, []).extend(s4.site_stats(arr25, c25, p25, sites, "S2SR_2.5m", t))
                    if t.strftime("%Y-%m") in showcase or k == len(scenes) - 1:
                        stem = os.path.join(cfg["SR_DIR"], f"{t:%Y%m%d}")
                        s1.write_geotiff(s4.compute_indices(arr25)["ndvi"], p25, stem + "_NDVI_2.5m.tif")
                        s1.write_geotiff(s4.compute_indices(arr)["ndvi"], prof, stem + "_NDVI_10m.tif")
                        s3.plot_sr_comparison(arr, arr25, f"Sentinel-2 {t:%Y-%m-%d}: 10 m vs SEN2SR 2.5 m",
                                              stem + "_comparison.png", sites, prof)
                else:
                    logger.warning(f"{tkey}: SR odrzucony (pasma 10 m: H-SR0={chk['pass_hsr0']}, "
                                   f"H-SR1={chk['pass_hsr1']}, RMSE={chk['consistency_rmse_max']:.4f})")
                if not chk["sr_ok_20m"]:
                    logger.info(f"{tkey}: SR pasm 20 m odrzucony (H-SR0={chk['pass_hsr0_20m']}, "
                                f"H-SR1={chk['pass_hsr1_20m']}, RMSE={chk['consistency_rmse_max_20m']:.4f}) "
                                f"— bez NDMI/NDRE z 2,5 m")
        if (n10 + nsr) % 25 == 0:
            flush()
    flush()
    msg = (f"10 m: {n10} nowych scen; SR: {nsr} scen, {nsr_ok} przeszło kontrolę pasm 10 m (NDVI), "
           f"{nsr_ok20} pasm 20 m (NDMI, NDRE)")
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
        for idx in ("ndvi", "ndmi"):
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
    veg_clim = f"other_years_doy{cfg['VEG_HALF_WINDOW_DAYS']}"
    for r in veg.itertuples():
        rows.append({"site_id": r.site_id, "product": f"{r.product}_{r.index.upper()}",
                     "date": pd.Timestamp(r.time).strftime("%Y-%m-%d"), "value": r.value,
                     "clim_mean": r.clim_mean, "z": r.z, "clim_id": veg_clim})
    anomalies = pd.DataFrame(rows).drop_duplicates(["site_id", "product", "date"], keep="last")
    cur = status[status["site_id"] == cfg["MAIN_SITE"]].iloc[-1]
    return {"message": f"{cfg['MAIN_SITE']} {cur['date']}: {cur['cdi_class']} ({cur['reason_codes']})",
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
    paths = s4.build_bulletin(status, veg_main, val, site, cfg, cfg["OUTPUT_DIR"])
    return {"message": ", ".join(os.path.relpath(p, cfg["PROJECT_DIR"]) for p in paths.values())}


def run_monitoring(rt: Dict[str, Any], cfg: Optional[Dict[str, Any]] = None, ingest: bool = True) -> None:
    """Wszystkie zadania po kolei (każde zapisane w gwl_runs; błąd jednego nie zatrzymuje kolejnych)."""
    cfg = cfg or monitor_config(rt)
    if ingest:
        run_task(rt, "ingest_s2", task_ingest_s2, rt, cfg)
        run_task(rt, "ingest_era5", task_ingest_era5, rt, cfg)
    run_task(rt, "scene_stats", task_scene_stats, rt, cfg)
    run_task(rt, "anomalies", task_anomalies, rt, cfg)
    run_task(rt, "validate", task_validate, rt, cfg)
    run_task(rt, "bulletin", task_bulletin, rt, cfg)


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
                              "BOOTSTRAP_N": 200, "USE_SR": False})
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
                         "t2m_min_c": 8 - 6 * seas, "t2m_c": 13 - 7 * seas})
    os.makedirs(cfg["ERA5_DIR"], exist_ok=True)
    era5.to_csv(_era5_csv(cfg), index=False)
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
    print("[OK] Kontrola SR: interpolacja odrzucona, spójny SR przyjęty (pasma 10 m i 20 m w natywnej rozdzielczości).")

    for name, fn in (("scene_stats", task_scene_stats), ("anomalies", task_anomalies),
                     ("validate", task_validate), ("bulletin", task_bulletin)):
        run_task(rt, name, fn, rt, cfg, raise_errors=True)
    res = run_task(rt, "scene_stats_repeat", task_scene_stats, rt, cfg, raise_errors=True)
    assert res["skipped"], "Drugie uruchomienie nie powinno przetwarzać scen ponownie"

    st = registry_read(rt, "gwl_status")
    assert "VINEYARD_06" in set(st["site_id"]) and st["cdi_class"].notna().all()
    val = registry_read(rt, "gwl_validation_metrics")
    assert len(val) >= 5, val
    with open(os.path.join(cfg["OUTPUT_DIR"], "agriwatch_latest.json"), encoding="utf-8") as f:
        js = json.load(f)
    assert js["current"]["cdi_class"] in ("normal", "watch", "warning", "alert", "recovery")
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
