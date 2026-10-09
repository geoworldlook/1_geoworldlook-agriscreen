"""
Szkic (track 'thermal'): punktowy szereg czasowy LST z Sentinel-3 SLSTR L2 (SL_2_LST___) dla Condom, uruchamiany w Colab.

Dwie ścieżki, obie wyłącznie Copernicus (CDSE):
  A) Sentinel Hub Process API na CDSE, kolekcja `sentinel-3-slstr-l2` (dodana w dokumentacji CDSE 2026-08) —
     ekstrakcja po stronie serwera, kilobajty na miesiąc; brak kątów widzenia (VZA) w paśmie.
  B) STAC (stac.dataspace.copernicus.eu/v1) + S3 eodata — pobranie 5 małych plików na granulę, pełna kontrola
     (flagi surowe, VZA z geometry_tn, wersja baseline z nazwy produktu). ~10-15 MB na granulę.
Wyniki: jeden wiersz na granulę (surowe flagi + metadane), cache miesięczny CSV na Dysku Google; QC i agregacja
dekadowa są osobnym krokiem (qc_rows / dedupe), żeby progi QC nie były zaszyte w pobieraniu.

Niezweryfikowane tu (brak dostępu do CDSE z sandboxa): zasięg czasowy kolekcji SH, nazwy kluczy assetów STAC,
dokładne znaczenia bitów flag (czytamy je z atrybutów flag_masks/flag_meanings w pliku).
"""
from __future__ import annotations

import concurrent.futures as cf
import datetime as dt
import json
import os
import re
import tempfile

import numpy as np
import pandas as pd

# --- Konfiguracja punktu i czasu -------------------------------------------------------------------------
LAT0, LON0 = 43.9744, 0.3361          # stacja SMOSMANIA Condom (winnica VINEYARD_06 136 m dalej)
START, END = "2016-04-01", None        # END=None -> dziś
MAX_PIX_DIST_KM = 0.75                 # odrzucamy granulę, gdy najbliższy piksel 1 km jest dalej (krawędź pasa)
GRID_DEG = 1 / 112                     # siatka openEO/CDSE dla SLSTR (0.008928571°)

STAC_URL = "https://stac.dataspace.copernicus.eu/v1"
STAC_COLLECTIONS_NTC = ["sentinel-3-sl-2-lst-ntc"]
STAC_COLLECTIONS_NRT = ["sentinel-3-sl-2-lst-nrt"]   # tylko dla ostatnich ~2 miesięcy (NTC jeszcze brak)
S3_ENDPOINT = "https://eodata.dataspace.copernicus.eu"
SH_BASE_URL = "https://sh.dataspace.copernicus.eu"
TOKEN_URL = "https://identity.dataspace.copernicus.eu/auth/realms/CDSE/protocol/openid-connect/token"

# Pliki potrzebne do ekstrakcji punktu (rozmiary z manifestu przykładowej granuli 2021, 21 % lądu):
# LST_in 0.8 MB, flags_in 2.0 MB, geodetic_in 7.8 MB, geodetic_tx 1.7 MB, geometry_tn 3.4 MB.
NEEDED_FILES = ("LST_in.nc", "flags_in.nc", "geodetic_in.nc", "geodetic_tx.nc", "geometry_tn.nc")

# Nazwa produktu: S3A_SL_2_LST____20210510T002955_20210510T003255_20210511T101010_0179_071_301_5760_LN2_O_NT_004.SEN3
NAME_RE = re.compile(
    r"(?P<platform>S3[AB])_SL_2_LST____(?P<start>\d{8}T\d{6})_(?P<stop>\d{8}T\d{6})_(?P<created>\d{8}T\d{6})_"
    r"(?P<duration>\d{4})_(?P<cycle>\d{3})_(?P<rel_orbit>\d{3})_(?P<frame>\d{4})_(?P<centre>\w{3})_"
    r"(?P<pclass>\w)_(?P<timeliness>NR|ST|NT)_(?P<baseline>\d{3})"
)


# --- Sekrety (Colab -> zmienne środowiskowe) -------------------------------------------------------------
def secret(name: str) -> str | None:
    """Sekret z panelu Colab (ikona klucza, dostęp per notatnik); poza Colab ze zmiennej środowiskowej."""
    try:
        from google.colab import userdata  # type: ignore
        try:
            return userdata.get(name)
        except Exception:  # SecretNotFoundError / NotebookAccessError
            pass
    except ImportError:
        pass
    return os.environ.get(name)


# --- Metadane z nazwy produktu ---------------------------------------------------------------------------
def parse_name(name: str) -> dict:
    m = NAME_RE.search(name)
    if not m:
        return {"product": name}
    d = m.groupdict()
    out = {"product": name, "platform": d["platform"], "timeliness": d["timeliness"], "baseline": d["baseline"],
           "centre": d["centre"], "cycle": int(d["cycle"]), "rel_orbit": int(d["rel_orbit"]), "frame": int(d["frame"])}
    for k in ("start", "stop", "created"):
        out[k] = pd.Timestamp(dt.datetime.strptime(d[k], "%Y%m%dT%H%M%S"), tz="UTC")
    return out


# --- Ekstrakcja piksela z plików granuli -----------------------------------------------------------------
def _scaled(var, raw):
    """Skalowanie CF ręcznie (auto-mask wyłączony, bo w baseline 005 bayes_in=0 (czysto) jest _FillValue)."""
    raw = np.asarray(raw, dtype="float64")
    fill = getattr(var, "_FillValue", None)
    out = raw * getattr(var, "scale_factor", 1.0) + getattr(var, "add_offset", 0.0)
    if fill is not None:
        out = np.where(raw == fill, np.nan, out)
    return out


def nearest_index(lat2d: np.ndarray, lon2d: np.ndarray, lat0: float, lon0: float) -> tuple[int, int, float]:
    """Najbliższy piksel (odległość na płaszczyźnie lokalnej, km). NaN w siatce są pomijane."""
    dy = (lat2d - lat0) * 111.32
    dx = (lon2d - lon0) * 111.32 * np.cos(np.radians(lat0))
    d2 = dx * dx + dy * dy
    if not np.isfinite(d2).any():
        return -1, -1, np.inf
    k = int(np.nanargmin(d2))
    r, c = np.unravel_index(k, d2.shape)
    return int(r), int(c), float(np.sqrt(d2[r, c]))


def flag_names(var) -> dict[str, int]:
    """Mapa nazwa_bitu -> maska z atrybutów pliku (źródło prawdy dla danego baseline)."""
    masks = np.atleast_1d(getattr(var, "flag_masks", []))
    names = str(getattr(var, "flag_meanings", "")).split()
    return {n: int(m) for n, m in zip(names, masks)}


def extract_granule(paths: dict[str, str], lat0: float = LAT0, lon0: float = LON0) -> dict:
    """Wartości w najbliższym pikselu 1 km + kąty z siatki tie-point (16 km), flagi surowe (bez maskowania)."""
    from netCDF4 import Dataset

    row: dict = {}
    with Dataset(paths["geodetic_in.nc"]) as g:
        g.set_auto_maskandscale(False)
        lat = _scaled(g["latitude_in"], g["latitude_in"][:])
        lon = _scaled(g["longitude_in"], g["longitude_in"][:])
    r, c, dkm = nearest_index(lat, lon, lat0, lon0)
    row.update(row_in=r, col_in=c, pix_dist_km=dkm, n_rows=lat.shape[0], n_cols=lat.shape[1])
    if dkm > MAX_PIX_DIST_KM:
        return row
    row["pix_lat"], row["pix_lon"] = float(lat[r, c]), float(lon[r, c])

    with Dataset(paths["LST_in.nc"]) as f:
        f.set_auto_maskandscale(False)
        for v in ("LST", "LST_uncertainty"):
            row[v] = float(_scaled(f[v], f[v][r, c]))
        row["exception"] = int(f["exception"][r, c]) if "exception" in f.variables else -1
    with Dataset(paths["flags_in.nc"]) as f:
        f.set_auto_maskandscale(False)
        for v in ("confidence_in", "cloud_in", "bayes_in", "pointing_in"):
            if v in f.variables:
                row[v] = int(f[v][r, c])
                row[v + "_fill"] = getattr(f[v], "_FillValue", None)
                row[v + "_meanings"] = json.dumps(flag_names(f[v]))
    with Dataset(paths["geodetic_tx.nc"]) as g:
        g.set_auto_maskandscale(False)
        latx = _scaled(g["latitude_tx"], g["latitude_tx"][:])
        lonx = _scaled(g["longitude_tx"], g["longitude_tx"][:])
    rt, ct, _ = nearest_index(latx, lonx, lat0, lon0)
    with Dataset(paths["geometry_tn.nc"]) as f:
        f.set_auto_maskandscale(False)
        for v in ("sat_zenith_tn", "solar_zenith_tn", "sat_azimuth_tn", "solar_azimuth_tn"):
            if v in f.variables and rt >= 0:
                row[v] = float(_scaled(f[v], f[v][rt, ct]))
    return row


# --- Ścieżka B: STAC + S3 --------------------------------------------------------------------------------
def month_starts(start: str, end: str | None) -> list[pd.Timestamp]:
    end_ts = pd.Timestamp(end) if end else pd.Timestamp.utcnow().tz_localize(None)
    return list(pd.date_range(pd.Timestamp(start).to_period("M").to_timestamp(), end_ts, freq="MS"))


def stac_products(month: pd.Timestamp, collections: list[str]) -> list[dict]:
    """Granule przecinające punkt w danym miesiącu: nazwa + prefiks S3 (z dowolnego assetu z '.SEN3')."""
    from pystac_client import Client

    stop = month + pd.offsets.MonthBegin(1) - pd.Timedelta(seconds=1)
    search = Client.open(STAC_URL).search(
        collections=collections, intersects={"type": "Point", "coordinates": [LON0, LAT0]},
        datetime=f"{month:%Y-%m-%dT00:00:00Z}/{stop:%Y-%m-%dT%H:%M:%SZ}", limit=200)
    out = []
    for item in search.items():
        href = next((a.href for a in item.assets.values() if ".SEN3" in a.href), None)
        if href is None:
            continue
        prefix = href.split(".SEN3")[0] + ".SEN3"          # s3://eodata/Sentinel-3/SLSTR/SL_2_LST___/YYYY/MM/DD/<nazwa>.SEN3
        out.append({"stac_id": item.id, "s3_prefix": prefix, **parse_name(prefix.rsplit("/", 1)[-1]),
                    "orbit_state": item.properties.get("sat:orbit_state"),
                    "abs_orbit": item.properties.get("sat:absolute_orbit")})
    return out


def s3_client():
    import boto3

    return boto3.client("s3", endpoint_url=S3_ENDPOINT, region_name="default",
                        aws_access_key_id=secret("CDSE_S3_ACCESS_KEY"),
                        aws_secret_access_key=secret("CDSE_S3_SECRET_KEY"))


def process_product(prod: dict, s3) -> dict:
    """Pobiera 5 plików do katalogu tymczasowego (dysk lokalny Colab, nie Drive), ekstrahuje punkt, kasuje pliki."""
    key0 = prod["s3_prefix"].replace("s3://eodata/", "").replace("/eodata/", "")
    with tempfile.TemporaryDirectory(dir="/tmp") as tmp:
        paths = {}
        for fn in NEEDED_FILES:
            paths[fn] = os.path.join(tmp, fn)
            s3.download_file("eodata", f"{key0}/{fn}", paths[fn])
        row = extract_granule(paths)
        row["bytes"] = sum(os.path.getsize(p) for p in paths.values())
    return {**prod, **row}


def run_direct(cache_dir: str, start: str = START, end: str | None = END, workers: int = 4,
               nrt_months: int = 2) -> pd.DataFrame:
    """Miesiąc po miesiącu; miesiąc z pliku cache jest pomijany (wznawianie po rozłączeniu Colab).
    workers=4 = limit równoległych połączeń S3 w darmowym planie CDSE."""
    os.makedirs(cache_dir, exist_ok=True)
    s3 = s3_client()
    months = month_starts(start, end)
    for i, m in enumerate(months):
        fp = os.path.join(cache_dir, f"s3lst_{m:%Y-%m}.csv")
        recent = i >= len(months) - nrt_months
        if os.path.exists(fp) and not recent:
            continue
        cols = STAC_COLLECTIONS_NTC + (STAC_COLLECTIONS_NRT if recent else [])
        prods = stac_products(m, cols)
        rows = []
        with cf.ThreadPoolExecutor(max_workers=workers) as ex:
            futs = {ex.submit(process_product, p, s3): p for p in prods}
            for fu in cf.as_completed(futs):
                try:
                    rows.append(fu.result())
                except Exception as e:  # pojedyncza granula nie zatrzymuje miesiąca; błąd zapisany w wierszu
                    rows.append({**futs[fu], "error": repr(e)[:300]})
        pd.DataFrame(rows).to_csv(fp, index=False)
        print(f"{m:%Y-%m}: {len(prods)} granul, {sum(r.get('bytes', 0) for r in rows) / 1e6:.0f} MB")
    return pd.concat([pd.read_csv(os.path.join(cache_dir, f)) for f in sorted(os.listdir(cache_dir))
                      if f.startswith("s3lst_")], ignore_index=True)


# --- Ścieżka A: Sentinel Hub Process API na CDSE ---------------------------------------------------------
SH_BANDS = ["LST", "LST_uncertainty", "CLOUD", "BAYES", "CONFIDENCE", "POINTING", "dataMask"]
SH_EVALSCRIPT = """
//VERSION=3
var B = %s;
function setup() {
  return {input: [{bands: B}], output: {id: "default", bands: 1, sampleType: "FLOAT32"}, mosaicking: "TILE"};
}
function updateOutput(outputs, collection) { outputs.default.bands = Math.max(1, collection.scenes.length * B.length); }
function evaluatePixel(samples) {
  var out = [];
  for (var i = 0; i < samples.length; i++) { for (var j = 0; j < B.length; j++) { out.push(samples[i][B[j]]); } }
  return out.length ? out : [NaN];
}
function updateOutputMetadata(scenes, inputMetadata, outputMetadata) {
  outputMetadata.userData = {tiles: scenes.tiles.map(function (t) {
    return {date: t.date, product: t.sentinel3ProductId || null, cloud: t.cloudCoverage}; })};
}
""" % json.dumps(SH_BANDS)


def sh_setup():
    from sentinelhub import DataCollection, SHConfig

    cfg = SHConfig()
    cfg.sh_base_url = SH_BASE_URL
    cfg.sh_token_url = TOKEN_URL
    cfg.sh_client_id = secret("CDSE_SH_CLIENT_ID")          # klient OAuth z panelu shapps.dataspace.copernicus.eu
    cfg.sh_client_secret = secret("CDSE_SH_CLIENT_SECRET")
    try:
        col = DataCollection.SENTINEL3_SLSTR_L2
    except AttributeError:  # sentinelhub-py 3.12.0 nie ma tej kolekcji wbudowanej
        col = DataCollection.define("SENTINEL3_SLSTR_L2", api_id="sentinel-3-slstr-l2",
                                    catalog_id="sentinel-3-slstr-l2", service_url=SH_BASE_URL)
    return cfg, col


def sh_month(month: pd.Timestamp, cfg, col, half_px: int = 1) -> pd.DataFrame:
    """(2*half_px+1)^2 pikseli siatki 1/112° wokół punktu; zwracany środkowy piksel każdej granuli (TILE)."""
    from sentinelhub import BBox, CRS, MimeType, SentinelHubRequest

    h = (half_px + 0.5) * GRID_DEG
    bbox = BBox((LON0 - h, LAT0 - h, LON0 + h, LAT0 + h), crs=CRS.WGS84)
    stop = month + pd.offsets.MonthBegin(1) - pd.Timedelta(seconds=1)
    req = SentinelHubRequest(
        evalscript=SH_EVALSCRIPT,
        input_data=[SentinelHubRequest.input_data(col, time_interval=(month.to_pydatetime(), stop.to_pydatetime()))],
        responses=[SentinelHubRequest.output_response("default", MimeType.TIFF),
                   SentinelHubRequest.output_response("userdata", MimeType.JSON)],
        bbox=bbox, size=(2 * half_px + 1, 2 * half_px + 1), config=cfg)
    data = req.get_data()[0]
    img = np.asarray(data["default.tif"], dtype="float64")
    tiles = data["userdata.json"]["tiles"]
    if img.ndim == 2:
        img = img[..., None]
    centre = img[half_px, half_px, :]
    nb = len(SH_BANDS)
    rows = []
    for i, t in enumerate(tiles):
        vals = centre[i * nb:(i + 1) * nb]
        if vals.size < nb:
            break
        rows.append({"date": t["date"], "product_sh": t.get("product"), "tile_cloud": t.get("cloud"),
                     **{b: float(v) for b, v in zip(SH_BANDS, vals)}})
    return pd.DataFrame(rows)


def run_sh(cache_dir: str, start: str = START, end: str | None = END, workers: int = 4) -> pd.DataFrame:
    os.makedirs(cache_dir, exist_ok=True)
    cfg, col = sh_setup()
    months = [m for m in month_starts(start, end) if not os.path.exists(os.path.join(cache_dir, f"sh_{m:%Y-%m}.csv"))]
    with cf.ThreadPoolExecutor(max_workers=workers) as ex:
        for m, df in zip(months, ex.map(lambda mm: sh_month(mm, cfg, col), months)):
            df.to_csv(os.path.join(cache_dir, f"sh_{m:%Y-%m}.csv"), index=False)
    return pd.concat([pd.read_csv(os.path.join(cache_dir, f)) for f in sorted(os.listdir(cache_dir))
                      if f.startswith("sh_")], ignore_index=True)


# --- QC i deduplikacja (osobno od pobierania) ------------------------------------------------------------
TIMELINESS_RANK = {"NT": 0, "ST": 1, "NR": 2}


def dedupe(df: pd.DataFrame) -> pd.DataFrame:
    """Jeden przelot = (platforma, cykl, orbita względna). Ta sama akwizycja bywa w NRT i NTC, a punkt na granicy
    ramek 3-min może trafić do dwóch granul: NT > ST > NR, potem najbliższy piksel, potem najnowszy 'created'."""
    d = df.copy()
    d["created"] = pd.to_datetime(d["created"], utc=True)
    d["t_rank"] = d["timeliness"].map(TIMELINESS_RANK).fillna(9)
    if "pix_dist_km" not in d:
        d["pix_dist_km"] = np.nan
    d = d.sort_values(["platform", "cycle", "rel_orbit", "t_rank", "pix_dist_km", "created"],
                      ascending=[True, True, True, True, True, False], na_position="last")
    return d.drop_duplicates(["platform", "cycle", "rel_orbit"]).drop(columns=["t_rank"])


def has_bit(value, meanings_json: str, name: str) -> bool | None:
    m = json.loads(meanings_json) if isinstance(meanings_json, str) else {}
    if name not in m or pd.isna(value):
        return None
    return bool(int(value) & m[name])


def qc_rows(df: pd.DataFrame, vza_max: float = 45.0, unc_max: float = 3.0) -> pd.DataFrame:
    """Flagi QC jako kolumny (nie filtr): klasyfikacja dzień/noc po kącie Słońca, chmury z dwóch źródeł."""
    d = df.copy()
    d["is_day"] = d["solar_zenith_tn"] < 90
    d["cloud_summary"] = [has_bit(v, mj, "summary_cloud") for v, mj in zip(d["confidence_in"], d["confidence_in_meanings"])]
    d["snow"] = [has_bit(v, mj, "snow") for v, mj in zip(d["confidence_in"], d["confidence_in_meanings"])]
    # bayes_in: w baseline 005 wartość 0 (czysto) zapisana jako _FillValue -> czytamy surowo; >0 z flagą
    # 'single_moderate' = chmura (Land Handbook). Znaczenia bitów z atrybutów pliku.
    d["cloud_bayes"] = [has_bit(v, mj, "single_moderate") for v, mj in zip(d["bayes_in"], d["bayes_in_meanings"])]
    d["qc_ok"] = (
        d["LST"].notna() & (d["exception"].fillna(1) == 0) & (d["pix_dist_km"] <= MAX_PIX_DIST_KM)
        & (d["cloud_summary"] == False) & (d["cloud_bayes"] != True) & (d["snow"] != True)  # noqa: E712
        & (d["sat_zenith_tn"] <= vza_max) & (d["LST_uncertainty"] <= unc_max)
    )
    return d


# --- Szacunek wolumenu (ścieżka B) -----------------------------------------------------------------------
def volume_estimate(mb_per_granule: float = 16.0, passes_per_sat_day: float = 1.4) -> pd.DataFrame:
    """passes_per_sat_day: ~0.7 dzień + ~0.7 noc przy pasie 1400 km na 44°N (szacunek geometryczny)."""
    today = pd.Timestamp.utcnow().tz_localize(None)
    # S3A: STAC NTC od 2016-04-19; S3B: reprocessing *_LR1_R_NT_004 od 2018-05-09 (z fazą tandem 2018)
    span = {"S3A": (pd.Timestamp("2016-04-19"), today), "S3B": (pd.Timestamp("2018-05-09"), today)}
    rows = []
    for sat, (a, b) in span.items():
        n = (b - a).days * passes_per_sat_day
        rows.append({"sat": sat, "granules": round(n), "GB": round(n * mb_per_granule / 1e3, 1)})
    return pd.DataFrame(rows)


if __name__ == "__main__":
    print(volume_estimate())
