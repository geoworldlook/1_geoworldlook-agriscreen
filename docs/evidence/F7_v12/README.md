# F7 — wersja 1.2: zgodność wskaźników, projekty parowania i termiki (2026-10-09)

Dowody do decyzji D-051 w `docs/plans/Plan_v7_precyzja.md`. Liczone offline na migawce rejestru (commit 277d162)
i surowych plikach ISMN Condom; skrypty mają wpisane ścieżki katalogu roboczego sesji (podmień `SCR` na początku pliku).

## 1. Czy zgodność kilku wskaźników poprawia warstwę roślinności? — NIE

`agreement.py`, wyniki: `scene_rules.csv`, `dekad_rules.csv`, `scene_r_diff.csv`. Wynik powtórzyło niezależnie dwóch
weryfikatorów (każdy własną implementacją klimatologii przyczynowej; zgodność co do liczby).

| Reguła (SR 2,5 m, dni ze sceną 2018–2024, n = 200, 34 zdarzenia ISMN z ≤ −1) | flagi / trafienia | FAR | R z ISMN |
|---|---|---|---|
| NDVI z ≤ −1 (status) | 31 / 1 | 0,97 | 0,38 [0,16; 0,58] |
| NDRE | 29 / 0 | 1,00 | 0,29 [0,06; 0,51] |
| NDMI | 47 / 4 | 0,92 | 0,40 [0,16; 0,60] |
| ≥ 2 z 3 | 33 / 1 | 0,97 | 0,37 |
| wszystkie 3 | 26 / 0 | 1,00 | 0,33 |
| średnia z | 36 / 1 | 0,97 | 0,37 |

- Indeksy są niemal redundantne (korelacje z: NDVI–NDRE 0,97, NDVI–NDMI 0,92). Reguły „zgodności” zmieniają liczbę flag,
  nie informację (kontrola NDVI z dopasowaną liczbą flag daje to samo).
- Przewaga NDMI (FAR 0,92) to 3 trafienia z 2 epizodów, McNemar p = 0,25; znika przy dopasowanej liczbie flag.
- Warstwa roślinności w tym samym dniu nie ma umiejętności wobec ISMN z ≤ −1 (HSS < 0 dla każdej reguły). Przyczyna:
  opóźnienie — 22 z 31 flag NDVI to lipiec–wrzesień 2022, po czerwcowej suszy w glebie. Z opóźnieniem 30–60 dni
  (sprawdzenie post hoc, nieużyte do wyboru) FAR NDVI spada do ok. 0,45.
- Alarm (gleba ERA5 + NDVI) na dekadach 2018–2024: 9 dekad, 0 trafień wobec suchych dekad ISMN — dlatego dashboard
  nazywa alarm niezwalidowanym na winorośli i pokazuje NDRE/NDMI wyłącznie informacyjnie.

## 2. Stres parowania z ERA5-Land (EDDI z ET0 FAO-56, SESR) — projekt gotowy, protokół do poprawy

`evap_v2.py` (ET0 FAO-56 odtwarza przykład 18: 3,880 mm vs 3,9), `validate_evap_ref.py`, `evap_preregistration.json`.
Krytyk: rdzeń poprawny (pasma GEE i znaki zweryfikowane w STAC), ale przed zamrożeniem protokołu trzeba:
usunąć test „wyprzedzenia” H4 (szum go spełnia), objąć haszem wszystkie stałe decyzyjne, zamrozić wersję QC ISMN
(dno skali latem), doprecyzować rho dla połączonego predyktora. Minimalny wykrywalny efekt: częściowe r ≈ 0,15–0,2.
Najtańsza wartościowa walidacja: ET0 z ERA5-Land wobec ETP Météo-France (stacja Condom).

## 3. Termika Sentinel-3 SLSTR (1 km) — wykonalna, odłożona na v1.3

`s3_lst_point.py` (szkic; trasy: Sentinel Hub na CDSE, STAC+S3, openEO). Krytyk: archiwum niejednorodne (kolekcje 003
i 004 przed 2020, zmiana przetwarzania 2025-04-07 niewidoczna w nazwie produktu); ISMN kończy się 2024-12-31, więc okresu
po zmianie nie da się zwalidować; minimalny wykrywalny efekt 0,20–0,30 wobec realnego 0,1–0,2. Jeśli termika — rozważyć
CLMS LST 3 km co godzinę (jedna wersja od 2018) jako źródło lub pomost.
