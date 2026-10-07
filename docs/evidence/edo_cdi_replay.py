"""
Odtworzenie logiki EDO Combined Drought Indicator v4.1.1 (factsheet JRC 2026, tabele 2a i 2b) na dekadowych
seriach AgriWatch i porównanie z obecnym statusem (step_04.build_status). Analiza do docs/evidence/F3_*.md.

Użycie:
    python docs/evidence/edo_cdi_replay.py <status_dekads.csv> [SITE_ID]

Wejście: status_dekads.csv z task_anomalies (kolumny date, spi1, spi3, sma_rz, veg_z, cdi_class).
Odczyt tabeli 2a (obraz w factsheecie, s. 6) — interpretacja autora, do potwierdzenia z JRC:
  - E/H: SMA <= -1 i roślinność <= -1 -> alert;   G: deficyt opadu i roślinność <= -1 -> alert;
  - D:   bez deficytu, SMA > -1, roślinność <= -1 -> alert, chyba że poprzednio no drought / recovery;
  - C/F: SMA <= -1, roślinność > -1 -> warning; po no drought / recovery bez deficytu i przy SPI-1 > 0,5
         oraz SPI-3 > 0 -> no drought; po alert: roślinność <= -0,5 alert, (-0,5; 0] temp. veg. recovery;
  - A/B: SMA > -1, roślinność > -1: po warning: SMA <= -0,5 warning, (-0,5; 0] temp. SM recovery,
         > 0 recovery (A) / watch (B); po alert analogicznie z roślinnością; inaczej watch (B) lub
         przejście do recovery / no drought (A);
  - v4.1: ujemna anomalia roślinności pomijana przy SPI-1 > 1; brak roślinności (poza sezonem) = tabela 2b.
"""
import sys

import numpy as np
import pandas as pd

ND, REC, WAT, WAR, TSM, ALE, TVR = ("normal", "recovery", "watch", "warning", "temp_sm_recovery", "alert",
                                    "temp_veg_recovery")
GROUP = {ND: "normal", REC: "recovery", TSM: "recovery", TVR: "recovery", WAT: "watch", WAR: "warning", ALE: "alert"}


def step(prev: str, spi1: float, spi3: float, sma: float, veg: float) -> str:
    """Klasa CDI w dekadzie T z anomalii w T i klasy w T-1."""
    d = (spi1 <= -2) or (spi3 <= -1)
    if np.isfinite(veg) and spi1 > 1:
        veg = np.nan
    has_veg = np.isfinite(veg)
    vlow = has_veg and veg <= -1
    smlow = np.isfinite(sma) and sma <= -1

    def veg_persist(otherwise):
        if not has_veg:
            return otherwise
        return ALE if veg <= -0.5 else TVR if veg <= 0 else otherwise

    if smlow and vlow:
        return ALE
    if vlow:
        return ALE if d or prev not in (ND, REC) else ND
    if smlow:
        if prev in (ND, REC) and not d:
            return ND if (spi1 > 0.5 and spi3 > 0) else WAR
        return veg_persist(WAR) if prev == ALE else WAR
    if prev == WAR:
        return WAR if sma <= -0.5 else TSM if sma <= 0 else (WAT if d else REC)
    if prev == ALE:
        return veg_persist(WAT if d else REC)
    if d:
        return WAT
    return {ND: ND, REC: ND, WAT: REC, TSM: REC, TVR: REC}[prev]


def replay(s: pd.DataFrame, veg_months=range(4, 11)) -> pd.Series:
    month = pd.to_datetime(s["date"]).dt.month
    veg = s["veg_z"].where(month.isin(list(veg_months)))
    prev, out = ND, []
    for r, v in zip(s.itertuples(), veg):
        prev = step(prev, r.spi1, r.spi3, r.sma_rz if np.isfinite(r.sma_rz) else 0.0, v)
        out.append(prev)
    return pd.Series(out, index=s.index)


if __name__ == "__main__":
    site = sys.argv[2] if len(sys.argv) > 2 else "VINEYARD_06"
    s = pd.read_csv(sys.argv[1])
    s = s[s["site_id"] == site].sort_values("date").reset_index(drop=True)
    year = pd.to_datetime(s["date"]).dt.year
    edo = replay(s)
    print(f"{site}: {len(s)} dekad; zgodność klas (recovery zgrupowane): {(edo.map(GROUP) == s['cdi_class']).mean():.3f}")
    print(pd.crosstab(s["cdi_class"], edo.map(GROUP), rownames=["AgriWatch"], colnames=["EDO v4.1.1"]))
    for name, months in (("roślinność IV-X", range(4, 11)), ("roślinność VI-IX", range(6, 10))):
        e = replay(s, months)
        veg = s["veg_z"].where(pd.to_datetime(s["date"]).dt.month.isin(list(months)))
        simple = (s["sma_rz"] <= -1) & (veg <= -1)
        print(f"{name}: alert EDO = {int((e == ALE).sum())} {e[e == ALE].groupby(year).size().to_dict()}; "
              f"alert uproszczony = {int(simple.sum())}")
