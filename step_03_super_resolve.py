"""
================================================================================
AgriWatch - KROK 3: SUPER-RESOLUTION SENTINEL-2 (SEN2SR, 10 m -> 2,5 m) Z KONTROLĄ JAKOŚCI
================================================================================
Model: SEN2SRLite "main" (ESA OpenSR; Aybar i in., RSE 2026), 10 pasm L2A -> 2,5 m, licencja CC0.
Użycie zgodne z README projektu (https://github.com/ESAOpenSR/SEN2SR):
  - kolejność pasm: B02, B03, B04, B05, B06, B07, B08, B8A, B11, B12 (pasma 20 m na siatce 10 m),
  - reflektancja w [0, 1] (L2A / 10 000), NaN -> 0,
  - duże obrazy: sen2sr.predict_large(model, X, overlap=32).

Zasady (wnioski z wersji v1 i z literatury):
  - BRAK cichego zastępstwa: jeśli modelu nie da się pobrać lub uruchomić, zgłaszamy błąd.
    (v1 po cichu używała interpolacji: różnica „SR” - bikubika = 0,5% zmienności obrazu.)
  - Każda scena przechodzi dwie kontrole i wynik trafia do rejestru:
      H-SR0  SR różni się od interpolacji bikubicznej (model naprawdę działał),
      H-SR1  SR uśredniony do natywnej rozdzielczości pasma zgadza się z obrazem wejściowym
             (spójność radiometryczna): pasma 10 m w blokach 4x4, pasma 20 m w blokach 8x8
             względem pikseli 20 m. Pasma 20 m na siatce 10 m to powielone piksele (eksport GEE
             bez resamplingu), więc porównanie ich z siatką 10 m karałoby SR za brak bloków 2x2.
    Kontrole są liczone osobno dla grup 10 m i 20 m: indeks z SR jest przyjmowany tylko wtedy,
    gdy wszystkie jego pasma przeszły (NDVI: grupa 10 m; NDMI, NDRE: grupa 20 m).
  - SR nie dodaje informacji o wodzie; służy do czystszych statystyk małych obiektów
    (poligon stacji ~210 m², brzegi winnic). Czy to coś daje, rozstrzyga walidacja w kroku 4/7.
  - Niezależna ocena (Hollendonner 2025, TU Wien): w zadaniu wyznaczania budynków SEN2SR-Lite
    nie był lepszy od interpolacji (F1 0,421 vs 0,423). Dlatego zawsze porównujemy z wersją 10 m.
================================================================================
"""

from __future__ import annotations

import gc
import logging
import os
from typing import Any, Dict, Optional, Tuple

import numpy as np

logger = logging.getLogger("AgriWatch_SR")

SEN2SR_BANDS = ["B02", "B03", "B04", "B05", "B06", "B07", "B08", "B8A", "B11", "B12"]
SEN2SR_MODEL_URL = "https://huggingface.co/tacofoundation/sen2sr/resolve/main/SEN2SRLite/main/mlm.json"
SR_FACTOR = 4
MODEL_TILE = 128          # sen2sr.predict_large tnie obraz na kafelki 128x128 px (i wymaga kwadratu)
# Wersja kontroli H-SR0/H-SR1 zapisywana w rejestrze (calib_id wierszy SR_QC). Zmiana wersji = sceny
# ocenione starszą kontrolą są przeliczane jeden raz; sceny odrzucone bieżącą wersją nie są powtarzane.
SR_QC_VERSION = "qc4"     # qc2: natywna rozdzielczość; qc3: pasma 20 m wg specyfikacji L2A, per wskaźnik; qc4: + CRSWIR, k = 1,5
BANDS_10M = ("B02", "B03", "B04", "B08")
BANDS_20M = ("B05", "B06", "B07", "B8A", "B11", "B12")
# Pasma wskaźników liczonych z SR (step_04.compute_indices). Wskaźnik z 2,5 m tylko, gdy wszystkie jego pasma przeszły.
INDEX_BANDS = {"ndvi": ("B04", "B08"), "ndmi": ("B8A", "B11"), "ndre": ("B8A", "B05"), "crswir": ("B8A", "B11", "B12")}
_W = (1610.0 - 865.0) / (2190.0 - 865.0)
_INDEX_FN = {
    "ndvi": lambda r, n: (n - r) / (n + r),
    "ndmi": lambda a, b: (a - b) / (a + b),
    "ndre": lambda a, b: (a - b) / (a + b),
    "crswir": lambda a8, b11, b12: b11 / (a8 + (b12 - a8) * _W),
}
# Specyfikacja dokładności odbicia powierzchniowego L2A: 0,05·ρ + 0,005 (Vermote i in. 2008; używana w walidacji
# korekcji atmosferycznej Sentinel-2, ACIX). Zasada dla pasm 20 m: SR nie dodaje więcej błędu, niż wynosi
# niepewność samych danych wejściowych (× SR_20M_SPEC_FACTOR). Ryzyko przyjęte świadomie (docs/ARCHITEKTURA.md).
L2A_SPEC_REL, L2A_SPEC_ABS = 0.05, 0.005


# ==============================================================================
# I. MODEL
# ==============================================================================

def load_sen2sr(model_dir: str, device: Optional[str] = None) -> Tuple[Any, Any]:
    """
    Pobiera model (raz, do model_dir na Dysku) i ładuje go. Błąd = wyjątek z jasnym komunikatem.
    Zwraca (model, torch.device).
    """
    try:
        import mlstac
        import torch
    except ImportError as e:
        raise RuntimeError(f"SEN2SR wymaga pakietów torch, mlstac i sen2sr ({e}). "
                           "W Colab: pip install sen2sr mlstac") from e
    dev = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))
    if not os.path.exists(os.path.join(model_dir, "mlm.json")):
        logger.info(f"SEN2SR: pobieranie modelu do {model_dir}")
        mlstac.download(file=SEN2SR_MODEL_URL, output_dir=model_dir)
    model = mlstac.load(model_dir).compiled_model(device=dev)
    model = model.to(dev)
    logger.info(f"SEN2SR: model gotowy ({dev}).")
    if dev.type == "cpu":
        logger.warning("SEN2SR działa na CPU (brak GPU): około 1 min na scenę. "
                       "W Colab: Środowisko wykonawcze -> Zmień typ -> GPU.")
    return model, dev


def super_resolve(arr10: np.ndarray, model: Any, device: Any, overlap: int = 32) -> np.ndarray:
    """
    arr10: (10, H, W) reflektancja [0, 1] w kolejności SEN2SR_BANDS (NaN dozwolone).
    Zwraca (10, 4H, 4W) float32; piksele NaN na wejściu są NaN także na wyjściu.
    """
    import sen2sr
    import torch

    if arr10.shape[0] != len(SEN2SR_BANDS):
        raise ValueError(f"Oczekiwano {len(SEN2SR_BANDS)} pasm, otrzymano {arr10.shape[0]}")
    nan_mask = ~np.isfinite(arr10).all(axis=0)
    c, h, w = arr10.shape
    x = np.nan_to_num(arr10, nan=0.0, posinf=0.0, neginf=0.0).astype("float32")
    # Model pracuje zawsze na kafelkach 128x128. predict_large z sen2sr 0.8.5 (PyPI) działa poprawnie
    # tylko dla obrazów kwadratowych (zamienione indeksy wiersz/kolumna, wyjście H x H) i nie dopełnia
    # osi < 128 px; dla obrazu dokładnie 128x128 zostawia w wyniku zera (~23%). Dopełniamy odbiciem
    # do kwadratu o boku max(H, W, 128); pojedynczy kafelek idzie wprost do modelu. Wynik przycinamy.
    side = max(h, w, MODEL_TILE)
    ph, pw = side - h, side - w
    if ph or pw:
        x = np.pad(x, ((0, 0), (0, ph), (0, pw)), mode="reflect" if min(h, w) > 1 else "edge")
    x = torch.from_numpy(x).to(device)
    with torch.no_grad():
        if side == MODEL_TILE:
            y = model(x[None]).squeeze(0)
        else:
            y = sen2sr.predict_large(model=model, X=x, overlap=overlap)
    out = y.detach().float().cpu().numpy()[:, : h * SR_FACTOR, : w * SR_FACTOR]
    del x, y
    if hasattr(torch, "cuda") and torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

    if out.shape != (c, h * SR_FACTOR, w * SR_FACTOR):
        raise RuntimeError(f"SEN2SR: nieoczekiwany kształt wyjścia {out.shape}, oczekiwano {(c, h * 4, w * 4)}")
    out[:, np.repeat(np.repeat(nan_mask, SR_FACTOR, 0), SR_FACTOR, 1)] = np.nan
    return out.astype(np.float32)


def profile_25m(profile10: Dict[str, Any]) -> Dict[str, Any]:
    """Profil rasterio siatki 2,5 m: ten sam narożnik i CRS, piksel 4 razy mniejszy."""
    from affine import Affine
    t = profile10["transform"]
    p = profile10.copy()
    p.update(transform=Affine(t.a / SR_FACTOR, t.b, t.c, t.d, t.e / SR_FACTOR, t.f),
             width=profile10["width"] * SR_FACTOR, height=profile10["height"] * SR_FACTOR)
    return p


# ==============================================================================
# II. KONTROLA JAKOŚCI SR (H-SR0, H-SR1)
# ==============================================================================

def block_mean(arr: np.ndarray, f: int = SR_FACTOR) -> np.ndarray:
    """Średnia w blokach f x f (ostatnia oś: szerokość). Działa dla (H, W) i (C, H, W)."""
    *lead, h, w = arr.shape
    a = arr[..., : h - h % f, : w - w % f].reshape(*lead, h // f, f, w // f, f)
    with np.errstate(all="ignore"):
        return np.nanmean(np.nanmean(a, axis=-1), axis=-2)


def bicubic_upsample(arr10: np.ndarray, f: int = SR_FACTOR) -> np.ndarray:
    """Interpolacja bikubiczna z wyrównaniem krawędzi pikseli (grid_mode) — punkt odniesienia dla H-SR0."""
    from scipy.ndimage import zoom
    a = np.nan_to_num(arr10, nan=float(np.nanmean(arr10)) if np.isfinite(arr10).any() else 0.0)
    factors = (1,) * (a.ndim - 2) + (f, f)          # tylko osie przestrzenne
    return zoom(a, factors, order=3, grid_mode=True, mode="grid-mirror")


def grid20_offset(band10: np.ndarray) -> Tuple[int, int]:
    """
    Przesunięcie (wiersz, kolumna) ∈ {0, 1}² siatki 20 m względem siatki 10 m: pasmo 20 m pobrane
    na siatce 10 m metodą najbliższego sąsiada ma pary identycznych pikseli zaczynające się od tego
    przesunięcia. Brak wyraźnego wzorca (np. resampling bilinearny) -> (0, 0).
    """
    a = band10
    best, frac_best = (0, 0), 0.0
    for oy in (0, 1):
        for ox in (0, 1):
            b = a[oy:, ox:]
            h, w = (b.shape[0] // 2) * 2, (b.shape[1] // 2) * 2
            if h < 2 or w < 2:
                continue
            b = b[:h, :w]
            with np.errstate(invalid="ignore"):
                same = (b[:, 0::2] == b[:, 1::2])[0::2] & (b[0::2] == b[1::2])[:, 0::2]
            fin = np.isfinite(b[0::2, 0::2])
            frac = float(same[fin].mean()) if fin.any() else 0.0
            if frac > frac_best:
                best, frac_best = (oy, ox), frac
    return best if frac_best >= 0.9 else (0, 0)


def _band_checks(lo10: np.ndarray, hi: np.ndarray, native_20m: bool) -> Tuple[float, float]:
    """(detail_ratio, consistency_rmse) jednego pasma; spójność w natywnej rozdzielczości pasma."""
    m = np.isfinite(hi)
    bic = bicubic_upsample(lo10)[: hi.shape[0], : hi.shape[1]]
    ratio = float(np.std((hi - bic)[m]) / max(np.std(hi[m]), 1e-9))
    if native_20m:
        oy, ox = grid20_offset(lo10)
        ref = block_mean(lo10[oy:, ox:], 2)
        agg = block_mean(hi[oy * SR_FACTOR:, ox * SR_FACTOR:], 2 * SR_FACTOR)
    else:
        ref, agg = lo10, block_mean(hi)
    h, w = min(ref.shape[0], agg.shape[0]), min(ref.shape[1], agg.shape[1])
    d = agg[:h, :w] - ref[:h, :w]
    d = d[np.isfinite(d)]
    rmse = float(np.sqrt(np.mean(d ** 2))) if d.size else np.nan
    return ratio, rmse


def sr_checks(arr10: np.ndarray, arr25: np.ndarray, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    H-SR0: detail_ratio = std(SR - bikubika) / std(SR). Interpolacja daje ~0 (v1: 0,005).
    H-SR1: consistency_rmse = RMSE(SR uśredniony do natywnej rozdzielczości pasma, wejście) w reflektancji.
    Wynik dla grup pasm 10 m (BANDS_10M) i 20 m (BANDS_20M) = najgorsze pasmo w grupie.
      sr_ok      — grupa 10 m przeszła obie kontrole (SR można użyć do NDVI),
      sr_ok_20m  — wszystkie pasma 20 m przeszły (informacyjnie).
    Pasma 10 m: H-SR1 = RMSE ≤ SR_MAX_CONSISTENCY_RMSE (stały, surowy próg: NDVI jest rdzeniem detekcji).
    Pasma 20 m: H-SR1 = RMSE ≤ SR_20M_SPEC_FACTOR · (0,05·ρ̄ + 0,005), ρ̄ = średnia reflektancja pasma w scenie.
    Decyzja per wskaźnik (INDEX_BANDS): sr_ok_indices = wskaźniki, których wszystkie pasma przeszły H-SR0 i H-SR1;
    {idx}_sr_err = szacowany błąd wskaźnika z RMSE jego pasm (propagacja błędu, pasma niezależne).
    """
    factor = cfg.get("SR_20M_SPEC_FACTOR", 1.0)
    band_ok: Dict[str, bool] = {}
    out: Dict[str, Any] = {}
    for group, bands, suffix in (("10m", BANDS_10M, ""), ("20m", BANDS_20M, "_20m")):
        ratios, rmses = [], []
        for name in bands:
            i = SEN2SR_BANDS.index(name)
            if np.isfinite(arr10[i]).mean() < 0.5:
                continue
            ratio, rmse = _band_checks(arr10[i], arr25[i], native_20m=(group == "20m"))
            rho = float(np.nanmean(arr10[i]))
            limit = (factor * (L2A_SPEC_REL * rho + L2A_SPEC_ABS)) if group == "20m" else cfg["SR_MAX_CONSISTENCY_RMSE"]
            out[f"detail_ratio_{name}"] = ratio
            out[f"consistency_rmse_{name}"] = rmse
            out[f"consistency_limit_{name}"] = limit
            out[f"mean_reflectance_{name}"] = rho
            band_ok[name] = bool(ratio >= cfg["SR_MIN_DETAIL_RATIO"] and rmse <= limit)
            ratios.append(ratio)
            rmses.append(rmse)
        dr = float(np.nanmin(ratios)) if ratios else np.nan
        cr = float(np.nanmax(rmses)) if rmses else np.nan
        out[f"detail_ratio_min{suffix}"] = dr
        out[f"consistency_rmse_max{suffix}"] = cr
        out[f"pass_hsr0{suffix}"] = bool(dr >= cfg["SR_MIN_DETAIL_RATIO"])
        checked = [b for b in bands if f"consistency_rmse_{b}" in out]
        out[f"pass_hsr1{suffix}"] = bool(checked) and all(
            out[f"consistency_rmse_{b}"] <= out[f"consistency_limit_{b}"] for b in checked)
        out[f"sr_ok{suffix}"] = out[f"pass_hsr0{suffix}"] and out[f"pass_hsr1{suffix}"]
    out["sr_ok_indices"] = [idx for idx, bs in INDEX_BANDS.items() if all(band_ok.get(b, False) for b in bs)]
    for idx in INDEX_BANDS:
        out[f"{idx}_sr_err"] = _index_error(out, idx)
    return out


def _index_error(chk: Dict[str, Any], idx: str) -> float:
    """
    Błąd wskaźnika z RMSE jego pasm: propagacja liniowa (gradient numeryczny w średnich reflektancjach sceny),
    błędy pasm traktowane jako niezależne. Zwraca odchylenie standardowe błędu wskaźnika na piksel.
    """
    bands = INDEX_BANDS[idx]
    try:
        rho = np.array([chk[f"mean_reflectance_{b}"] for b in bands], float)
        err = np.array([chk[f"consistency_rmse_{b}"] for b in bands], float)
    except KeyError:
        return float("nan")
    f = _INDEX_FN[idx]
    grad = []
    for k in range(len(bands)):
        h = 1e-5
        up, dn = rho.copy(), rho.copy()
        up[k] += h
        dn[k] -= h
        grad.append((f(*up) - f(*dn)) / (2 * h))
    v = float(np.sqrt(np.sum((np.array(grad) * err) ** 2)))
    return v if np.isfinite(v) else float("nan")


# ==============================================================================
# III. WIZUALIZACJA (dla raportu i strony)
# ==============================================================================

def plot_sr_comparison(arr10: np.ndarray, arr25: np.ndarray, title: str, out_png: str,
                       sites: Optional[Any] = None, profile10: Optional[Dict[str, Any]] = None) -> str:
    """Kolor naturalny i NDVI: 10 m obok SR 2,5 m (opcjonalnie granice obiektów)."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    def rgb(a):
        x = np.stack([a[SEN2SR_BANDS.index(b)] for b in ("B04", "B03", "B02")], -1)
        return np.clip(np.nan_to_num(x) / 0.25, 0, 1)

    def ndvi(a):
        r, n = a[SEN2SR_BANDS.index("B04")], a[SEN2SR_BANDS.index("B08")]
        with np.errstate(all="ignore"):
            return (n - r) / (n + r)

    fig, ax = plt.subplots(2, 2, figsize=(12, 11))
    h, w = arr10.shape[1:]
    ext = None
    if profile10 is not None:
        t = profile10["transform"]
        ext = (t.c, t.c + t.a * w, t.f + t.e * h, t.f)
    panels = [(rgb(arr10), "Sentinel-2 10 m"), (rgb(arr25), "SEN2SR 2.5 m"),
              (ndvi(arr10), "NDVI 10 m"), (ndvi(arr25), "NDVI SEN2SR 2.5 m")]
    for a, (img, lab) in zip(ax.ravel(), panels):
        kw = dict(cmap="RdYlGn", vmin=0, vmax=0.9) if img.ndim == 2 else {}
        a.imshow(img, extent=ext, interpolation="nearest", **kw)
        if sites is not None and ext is not None:
            sites.boundary.plot(ax=a, color="cyan", lw=1.2)
        a.set_title(lab)
        a.set_xticks([]); a.set_yticks([])
    fig.suptitle(title)
    fig.tight_layout()
    os.makedirs(os.path.dirname(out_png) or ".", exist_ok=True)
    fig.savefig(out_png, dpi=110)
    plt.close(fig)
    return out_png
