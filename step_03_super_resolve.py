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
      H-SR1  SR uśredniony 4x4 zgadza się z obrazem 10 m (spójność radiometryczna).
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
    x = torch.from_numpy(np.nan_to_num(arr10, nan=0.0, posinf=0.0, neginf=0.0).astype("float32")).to(device)
    with torch.no_grad():
        y = sen2sr.predict_large(model=model, X=x, overlap=overlap)
    out = y.detach().float().cpu().numpy()
    del x, y
    if hasattr(torch, "cuda") and torch.cuda.is_available():
        torch.cuda.empty_cache()
    gc.collect()

    c, h, w = arr10.shape
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


def sr_checks(arr10: np.ndarray, arr25: np.ndarray, cfg: Dict[str, Any]) -> Dict[str, Any]:
    """
    H-SR0: detail_ratio = std(SR - bikubika) / std(SR). Interpolacja daje ~0 (v1: 0,005).
    H-SR1: consistency_rmse = RMSE(średnia 4x4 z SR, obraz 10 m) w jednostkach reflektancji.
    Liczone dla pasm 10 m (B02, B03, B04, B08) i SWIR (B11, B12); wynik = najgorsze pasmo.
    """
    out: Dict[str, Any] = {}
    ratios, rmses = [], []
    for name in ("B02", "B03", "B04", "B08", "B11", "B12"):
        i = SEN2SR_BANDS.index(name)
        lo, hi = arr10[i], arr25[i]
        valid = np.isfinite(lo)
        if valid.mean() < 0.5:
            continue
        agg = block_mean(hi)
        h, w = agg.shape
        d = (agg - lo[:h, :w])[valid[:h, :w] & np.isfinite(agg)]
        rmse = float(np.sqrt(np.mean(d ** 2))) if d.size else np.nan
        bic = bicubic_upsample(lo)[: hi.shape[0], : hi.shape[1]]
        m = np.isfinite(hi)
        ratio = float(np.std((hi - bic)[m]) / max(np.std(hi[m]), 1e-9))
        out[f"consistency_rmse_{name}"] = rmse
        out[f"detail_ratio_{name}"] = ratio
        ratios.append(ratio)
        rmses.append(rmse)
    out["detail_ratio_min"] = float(np.nanmin(ratios)) if ratios else np.nan
    out["consistency_rmse_max"] = float(np.nanmax(rmses)) if rmses else np.nan
    out["pass_hsr0"] = bool(out["detail_ratio_min"] >= cfg["SR_MIN_DETAIL_RATIO"])
    out["pass_hsr1"] = bool(out["consistency_rmse_max"] <= cfg["SR_MAX_CONSISTENCY_RMSE"])
    out["sr_ok"] = out["pass_hsr0"] and out["pass_hsr1"]
    return out


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
