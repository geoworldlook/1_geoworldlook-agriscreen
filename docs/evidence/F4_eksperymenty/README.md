# F4 — eksperymenty precyzji (2026-10-08)

Dowody do `docs/plans/Plan_v7_precyzja.md`. Wszystko liczone offline na danych z rejestru na Dysku
(`gwl_observations.csv`, `era5_land_daily.csv`, `gwl_anomalies.csv`, `gwl_status.csv`; przebieg z commita `277d162`,
pełna historia SR 414 scen) i surowych plikach ISMN Condom z `data/7_isismn_data`.

Każdy eksperyment najpierw odtwarzał wynik v1.0 tą samą metodą co `step_07.validate_anomalies`
(wszystkie trzy odtworzyły go dokładnie: ERA5 RZ R = 0,583, n = 2976; POD/FAR 0,574/0,571; NDVI SR R = 0,433, n = 245),
a potem był sprawdzany przez niezależnego recenzenta, który powtarzał obliczenia i szukał błędów (katalogi `*_weryfikacja`).

| Katalog | Co | Werdykt recenzenta |
|---|---|---|
| `A_roslinnosc/` | 15 wariantów warstwy roślinności (wygładzanie, NDMI/NDRE/CRSWIR, kompozyty, kontrast winnica–trawa, opóźnienia, klimatologia fenologiczna, spadek w sezonie) | wynik negatywny potwierdzony; wykryty wyciek klimatologii z lat przyszłych |
| `B_bilans_wodny/` | FAO-56 z Kcb z NDVI (SR i 10 m), SPEI-podobne, kombinacje z ERA5 | wynik negatywny potwierdzony (zaufanie wysokie), w tym niezależnym przebiegiem `pyfao56` |
| `C_wilgotnosc_gleby/` | warstwy ERA5-Land, okna anomalii, Sentinel-1 (SWI), fuzja, progi zdarzeń | zysk L2 tylko zimą; zmiana wyzwalacza odrzucona |
| `R1_bilans_wodny_prototyp/` | prototyp dwuskładnikowego bilansu (winorośl + międzyrzędzie), termin wejścia w suszę | bez osobnej recenzji — traktować jako hipotezę |
| `R2_orbita_fenologia/` | błąd orbit, klimatologia harmoniczna | błąd orbit potwierdzony własnym skryptem (`weryfikacja_wlasna/`) |
| `R3_gleba/`, `R4_statystyka/` | analizy pomocnicze (efektywne n, placebo, kalibracja progów, mróz 2022) | kalibracja progów potwierdzona własnym skryptem |
| `D_asymilacja_EnKF/` | EnKF (100 członków) z Sentinel-1 w 2-warstwowym modelu na stacji Condom; rekalibracja parametru; prawdopodobieństwo P(z ≤ −1), Brier, niezawodność. Opis: `docs/evidence/F5_asymilacja_danych.md` | bez osobnej recenzji; testy: bilans wody zamknięty do 1e-13 mm, zgodność z dokładnym filtrem Kalmana w przypadku liniowym |
| `weryfikacja_wlasna/` | moja kontrola: orbita, klimatologia przyczynowa, kalibracja z | — |
| `wyniki_workflow.json` | pełne wyniki: 4 przeglądy literatury, 3 eksperymenty, 3 recenzje | — |
| `zrodla_przeglad.txt` | lista źródeł z poziomem dostępu (fulltext / abstract / snippet / own_knowledge_unverified) | — |

Skrypty mają wpisane ścieżki do katalogu roboczego sesji (`.../scratchpad/drive_data/`). Żeby je powtórzyć, pobierz
tabele `gwl_*` i `era5_land_daily.csv` z Dysku do jednego katalogu i podmień stałą ze ścieżką na początku `common.py`
(albo `check2.py`). Nie są częścią potoku i nie są uruchamiane przez notatnik.
