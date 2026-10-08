# Plan v7 — precyzja wyników (AgriWatch v1.1)

Status: PROPOSED, 2026-10-08. Zakres: jedna winnica (`VINEYARD_06`), architektura v1.0 bez zmian
(Colab + GEE, rejestr na Dysku, dashboard). Zmieniamy statystykę, walidację i warstwę „winnicy”.

Podstawa: przegląd literatury w 4 kierunkach, 3 eksperymenty na naszych danych (pełna historia SR, 414 scen),
każdy powtórzony przez niezależnego recenzenta, oraz własna kontrola kluczowych liczb.
Skrypty i wyniki: `docs/evidence/F4_eksperymenty/`.

## 1. Diagnoza: co naprawdę ogranicza precyzję

Wniosek główny: **samo NDVI nie jest wąskim gardłem.** Żaden inny wskaźnik ani przetworzenie nie jest lepszy
od NDVI względem wilgotności gleby. Precyzję ograniczają błędy statystyki anomalii i brak właściwej prawdy o stanie winorośli.

| # | Ustalenie | Liczby | Status |
|---|---|---|---|
| 1 | Klimatologia anomalii roślinności używa **lat przyszłych** („pozostałe lata”). Operacyjnie (tylko lata wcześniejsze) wynik jest dużo słabszy | te same 215 dni: R = 0,50 → **0,29**; recenzent: 0,51 → 0,34 (200 dni); usunięcie trendu nie pomaga (0,30) | potwierdzone 2× |
| 2 | Silny trend NDVI winnicy, prawdopodobnie zmiana gospodarki międzyrzędziem | NDVI w kwietniu: 0,30 (2016) → 0,62 (2024) | potwierdzone |
| 3 | **Błąd systematyczny orbit Sentinel-2** tylko na winnicy (geometria rzędów, BRDF) | średnie z: −0,19 (tor ~10:59) vs +0,21 (~11:09), p ≈ 0,001; na trawniku stacji brak różnicy (p = 0,59) | potwierdzone 2× |
| 4 | Progi z są źle skalibrowane (krótka historia, rozkład nie normalny) | z ≤ −1: 19,6% scen (powinno ~15,9%); \|z\| > 2: 9,4% (powinno ~4,6%) | potwierdzone 2× |
| 5 | Żaden z 15 wariantów roślinności nie bije NDVI (NDMI, NDRE, CRSWIR, kompozyty, wygładzanie, opóźnienia, klimatologia fenologiczna, kontrast winnica–trawa) | wszystkie sparowane CI obejmują 0 lub leżą poniżej; NDMI 0,41, NDRE 0,38, CRSWIR 0,37 vs NDVI 0,43 | potwierdzone |
| 6 | Roślinność nie wnosi informacji o glebie ponad ERA5 | korelacja cząstkowa przy danym ERA5: 0,11 [−0,19; 0,34]; dodanie NDVI do ERA5 obniża R w walidacji krzyżowej (0,558 → 0,536) | potwierdzone |
| 7 | Alarm (gleba + NDVI) nie poprawia precyzji względem samego ostrzeżenia | trafność dekad: 0,25 (alarm) vs 0,39 (ostrzeżenie), różnica nieistotna (p = 0,14) | potwierdzone |
| 8 | Związek NDVI z wilgotnością jest głównie **międzyroczny**, w sezonie słaby; najsłabszy w sierpniu | R średnich rocznych 0,59 (n = 9); wewnątrz roku 0,29 [0,08; 0,49]; sierpień 0,12, wrzesień 0,65 | potwierdzone (poprawione przez recenzenta) |
| 9 | Prawda referencyjna jest słaba latem: czujniki 20–30 cm pod trawą stacji schodzą do dna w suchych latach; czujnik 5 cm wymieniony w 2019 r.; flaga QC-4 (utrata kontaktu w glinie) z `Condom_QC.md` nie jest stosowana w `qc_insitu` | minima 2017/2019/2022 ≈ 0,01 m³/m³ przy 30 cm | potwierdzone |
| 10 | Warstwa gleby ERA5-Land 0–100 cm jest blisko tego, co jeden punkt może potwierdzić. Warstwa 7–28 cm daje R = 0,69 (+0,11), ale **cały zysk jest zimą**; w IV–X wykrywa mniej suchych dekad | XI–III ΔR +0,22; IV–X +0,02 (n.s.); IV–X trafione dekady 12/29 vs 17/29; VII–X 1/13 vs 8/13 | potwierdzone; zmiana wyzwalacza odrzucona |
| 11 | Bilans wodny FAO-56 z Kcb z NDVI nie poprawia zgodności z czujnikiem, a w sezonie jest gorszy; Kcb z S-2 nic nie wnosi | R 0,563 vs 0,583; IV–X ΔR −0,10 [−0,17; −0,03]; Kcb z S-2 vs klimatologiczny r = 0,997 | potwierdzone (zaufanie wysokie) |
| 12 | Bilans dwuskładnikowy (winorośl + międzyrzędzie) lepiej trafia **termin** wejścia w suszę | błąd średni 14–20 dni vs 66 dni dla warstwy ERA5 0–100 cm (n = 9 lat) | **hipoteza** — bez niezależnej recenzji |
| 13 | Sentinel-1 przy stacji jest słaby; po filtrze wykładniczym (SWI) dorównuje ERA5, fuzja daje mały zysk, który nie przetrwa korekty na wielokrotne porównania | surowy R = 0,19 (5 cm); SWI 0,55; fuzja +0,05 [+0,006; +0,09] | potwierdzone |
| 14 | SR 2,5 m jest **równoważny** 10 m dla sygnału | ΔR +0,004 [0,000; 0,009] | potwierdzone; SR zostaje do map |
| 15 | 2022 to nie „czysta” susza w Gers: przymrozek 3–4 IV i grad w VI | z odpisów podatkowych departamentu (fragment wyszukiwania) | **do potwierdzenia** |

**Konsekwencja dla v1.0 już teraz:** liczba „NDVI R = 0,43” na dashboardzie to wynik retrospektywny.
Operacyjnie (klimatologia tylko z lat wcześniejszych) jest to około 0,3. Do poprawy w A6.

## 2. Co znaczy „profesjonalnie” w tym projekcie

Precyzja wyniku to trzy rzeczy, w tej kolejności:
1. **Poprawna statystyka** — bez wycieku z przyszłości, ze skalibrowanymi progami, bez błędu orbit, ze sparowanymi testami.
2. **Właściwy cel walidacji** — stan wodny winorośli, nie tylko wilgotność gleby pod trawnikiem 136 m dalej.
3. **Wielkość w jednostkach winorośli** — FTSW / deficyt w mm / współczynnik stresu, z niepewnością.

Dokładanie kolejnych wskaźników spektralnych nie spełnia żadnego z tych warunków (ustalenie 5).

## 3. Plan

### Etap A — poprawność obecnych warstw (v1.1; ok. 7 dni; bez nowych danych)

| Krok | Co | Kryterium akceptacji |
|---|---|---|
| A1 | Klimatologia przyczynowa roślinności (tylko lata wcześniejsze, min. 3 lata) w `step_04`; raportowanie skuteczności operacyjnej obok retrospektywnej. Trend obsłużony anomalią względem **innych winnic AOI z tej samej sceny** (różnica krzyżowa: „ta winnica vs sąsiedzi”) — wymaga statystyk dla wszystkich 15 winnic w `task_scene_stats` (klipy już powstają) | dashboard pokazuje liczby operacyjne; warstwa krzyżowa liczona dla 15 winnic |
| A2 | Klimatologia z podziałem na tor orbity (lub człon orbity w modelu bazowym) | różnica średnich z między torami < 0,1 i nieistotna |
| A3 | Skalibrowane z: klimatologia ważona latami + standaryzacja t-Studenta (predykcyjna) | częstość z ≤ −1: 13–19%; \|z\| > 2: 2,5–7% |
| A4 | ISMN: flaga QC-4 (utrata kontaktu) i flaga „dno czujnika” w `qc_insitu`; 5 cm wyłączone z walidacji klimatologicznej (wymiana czujnika 2019) | raport walidacji podaje dni odrzucone przez QC |
| A5 | Protokół walidacji v1.1 w kodzie (`validate_anomalies`): sparowane ΔR z blokiem = sezon, efektywne n, korelacja cząstkowa przy danym ERA5, test placebo (tasowanie lat), raport sezonowy XI–III / IV–X / VII–X, wiersz ERA5 7–28 cm, warianty wybierane walidacją krzyżową „zostaw rok” na 2016–2023 i potwierdzane na 2024 (+2025–2026 tam, gdzie jest referencja), korekta Holma przy wielu wariantach | warianty wchodzą do statusu tylko przy sparowanej przewadze lub równoważności (±0,05) z inną zaletą |
| A6 | Dashboard i README: liczby operacyjne z CI, dopiski (warstwa ERA5 dla POD/FAR, n dekad, pośredniość 136 m), zdanie o braku walidacji alarmu na danych z winnicy; próg zdarzeń gleby −1,2 zamiast −1 do rozważenia (obciążenie częstości 1,34 → 0,96) tylko jeśli przejdzie A5 | opisy zgodne z `run_summary.md` |
| A7 | **PSMA — probabilistyczna anomalia wilgotności** (filtr Kalmana na anomaliach, `docs/evidence/F5_asymilacja_danych.md` §5): ostrzeżenie z prawdopodobieństwa `p = P(x ≤ −1 \| dane)` z przedziałem niepewności zamiast progu z ≤ −1; wejście p ≥ 0,5, utrzymanie p ≥ 0,35. Na start jedno źródło (ERA5-Land), parametry z etapu B | Brier lepszy niż reguła tak/nie (w eksperymencie 0,141 → 0,103); diagram niezawodności bez systematycznego odchylenia |

Status logiki EDO zostaje. NDVI zostaje jako warstwa „skutku” (jak fAPAR w EDO), po poprawkach A1–A3.
FAR ≈ 0,57 obecnej reguły to granica wynikająca z korelacji ERA5 z czujnikiem (r = 0,58 daje oczekiwany FAR 0,56), nie błąd progu —
dlatego A7 zamienia próg na prawdopodobieństwo.

### Etap B — walidacja wielostanowiskowa warstwy gleby (ok. 4 dni; GEE w Colab)

- 21 stacji SMOSMANIA już leży w repozytorium. Dla każdej: ERA5-Land 0–100 cm i 7–28 cm z GEE, ta sama metoda co dla Condom.
- Wynik w formacie publikacji: mediana R, odsetek stacji z dolną granicą CI > 0,30, ΔR sparowane zbiorczo.
- Trzecie niezależne źródło do potrójnej kolokacji: SMAP L4 (jest w katalogu GEE). Opcjonalnie Météo-France SIM2 (8 km, otwarte dane) jako niezależny model.
- Kryteria: mediana R ≥ 0,50; ≥ 70% stacji z dolnym CI > 0,30.
- Dopiero tu można rozstrzygnąć: warstwa 0–100 vs 7–28 cm, fuzja z Sentinel-1, próg −1 vs −1,2.
- Produkty z asymilacją danych jako kandydaci na członków PSMA (A7): **SMAP L4** (EnKF, GEE `NASA/SMAP/SPL4SMGP/008`)
  i **H SAF H145/H146** (SEKF z ASCAT, te same warstwy co ERA5-Land). Członek wchodzi tylko przy sparowanej poprawie Brier (korekta Holma).
- Parametry PSMA (ρ każdego źródła) z rozszerzonej potrójnej kolokacji na wszystkich stacjach, nie strojone na Condom.

### Etap C — warstwa winnicy w jednostkach winorośli (ok. 15 dni; po A i B)

- **C1. ET0 Penmana–Monteitha z ERA5-Land** (GEE, zmienne godzinowe) zamiast Hargreavesa; kontrola z SIM2.
- **C2. Bilans wodny dwuskładnikowy** (winorośl + międzyrzędzie, typ WaLIS; nowy `step_08_water_balance`):
  parametry FAO-56 dla winorośli (Kcb 0,15/0,65/0,40, fazy 30/60/40/80 dni od kwietnia, Zr 1,2 m, p 0,45);
  S-2 jako **parametr strukturalny** (wieloletni wigor z VII–VIII, fenologia międzyrzędzia), nigdy jako bieżący Kcb
  (ustalenie 11: bieżące NDVI tłumi suszę w modelu); TAW z mapy gleb (OpenLandMap / francuska mapa RU) jako zespół ±30%.
- **C3. Atrybuty działek z IGN BD ORTHO 20 cm (IRC, licencja Etalab):** rozstaw i azymut rzędów, udział okrywy winorośli, typ międzyrzędzia. Służą C2 i A2. SR 2,5 m nie rozdziela rzędów rozstawionych co 2,2–3 m.
- **C4. Wyjście:** FTSW, współczynnik stresu Ks, deficyt w mm, anomalia FTSW, dni do stresu.
  Status: ostrzeżenie = gleba; nowe pole `vine_stress` = model; alarm = `vine_stress` ∧ obserwowana anomalia S-2.
- **C5. Wersja zespołowa z asymilacją (cykl prognoza → przelot satelity → korekta):** 100 przebiegów bilansu z zaburzonym deszczem,
  ET0 i TAW; EnKF aktualizuje stan przy każdym przelocie S-1 (osobna klimatologia dla każdej orbity); TAW dopasowywane raz w roku
  wsadowo (ES-MDA), nie przez dryf w filtrze; wynik `P(FTSW ≤ 0,4)` i „dni do stresu” z 7-dniowej prognozy zespołowej.
  Eksperyment F5: EnKF z S-1 na stacji nie poprawił R (ΔR −0,024 [−0,09; +0,05]), a rekalibracja parametru nie zbiegła w 9 lat —
  przyjmujemy C5 tylko, jeśli na wielu stacjach nie jest gorszy od przebiegu bez asymilacji.
- Uczciwie: C nie podniesie R względem czujnika ISMN (ustalenie 11). Wartość to jednostki fizyczne, termin (ustalenie 12, hipoteza)
  i różnicowanie działek przez TAW i wigor. Dowód musi przyjść z etapu D.

### Etap D — prawda o winorośli (sezon 2027) — jedyna droga do udowodnienia precyzji alarmu

- **D1. δ13C cukrów moszczu przy zbiorze** z 15 działek (zintegrowany stres wodny sezonu; metoda standardowa w Bordeaux).
- **D2. Obserwacje ApeX** (wzrost wierzchołków pędów, darmowa aplikacja IFV/INRAE) co tydzień VI–VIII na 3–5 działkach.
- **D3. Opcjonalnie potencjał wodny przedświtowy** (komora ciśnieniowa) na 3–5 działkach — kalibracja TTSW w C2.
- Kryterium: korelacja Spearmana ρ ≥ 0,52 (n = 15, α = 0,05) między sezonową anomalią / FTSW a δ13C.
- Obserwacje ApeX służą też jako **obserwacje asymilowane** w C5: tylko obserwacja stanu winorośli czyni TAW działki identyfikowalnym
  (TTSW z błędem ~30 mm z ApeX + pogody + S-2; Zhang, Pichon, Roux 2025). Z samego S-1 parametr się nie uczy (F5 §4).
- Wymaga partnera w terenie (winiarz, spółdzielnia, Chambre d'agriculture du Gers lub IFV). To także kontakt zawodowy.

### Kolejność i nakład

| Etap | Dni pracy | Zależy od | Wynik dla CV |
|---|---|---|---|
| A | ~7 | — | „wykryłem i usunąłem wyciek klimatologii i błąd orbit; liczby operacyjne z CI” |
| B | ~4 | A5 | walidacja na 21 stacjach w standardzie publikacji |
| C | ~15 | A, B | model stresu wodnego winorośli z EO |
| D | sezon 2027 | C | pierwsza walidacja na stanie wodnym winorośli |

## 4. Czego nie robimy (i dlaczego)

- Zamiana NDVI na NDMI / CRSWIR / NDRE lub kompozyt — gorsze albo równe (ustalenie 5).
- Wygładzanie Whittakera, okna fenologiczne (GDD), opóźnienia — bez zysku; wygładzanie nieprzyczynowe nie jest operacyjne.
- Rozdział rzędów i międzyrzędzi z SR 2,5 m — fizycznie niemożliwy przy rozstawie 2,2–3 m (brak sygnału powyżej częstotliwości Nyquista S-2).
- Bieżące NDVI → Kcb w bilansie wodnym winnicy z zielonym międzyrzędziem — tłumi suszę (ustalenie 11).
- Zmiana wyzwalacza ostrzeżenia na ERA5 7–28 cm — zysk tylko zimą, w sezonie gorsza detekcja (ustalenie 10).
- Hargreaves jako operacyjne ET0 — ERA5-Land ma wszystkie zmienne do Penmana–Monteitha.
- Surowe Sentinel-1 jako wejście statusu; termika (Landsat, ECOSTRESS) jako rdzeń dla 3 ha — najwyżej test „tak/nie” później.
- Uczenie maszynowe trenowane na jednej stacji; kalibracja parametrów winorośli na trawniku stacji.
- Raportowanie niesparowanych R z osobnymi CI jako dowodu, że jedna metoda jest lepsza (CI ±0,18 zawsze się nakładają).

## 5. Decyzje do zatwierdzenia

- D-040: Etap A wchodzi do v1.1 jako poprawka poprawności (nie rozwój metody).
- D-041: Dashboard pokazuje skuteczność operacyjną, nie retrospektywną.
- D-042: Ostrzeżenie zostaje na ERA5-Land 0–100 cm do czasu etapu B.
- D-043: S-2 w bilansie wodnym tylko jako parametr strukturalny.
- D-044: Alarm walidujemy na stanie wodnym winorośli (etap D); do tego czasu opisujemy go jako niezwalidowany.
- D-045: Ostrzeżenie o glebie wyrażamy jako prawdopodobieństwo (PSMA, A7) z przedziałem niepewności, weryfikowane Brierem i diagramem niezawodności.
- D-046: Produkty z asymilacją (SMAP L4, H SAF) testujemy jako członków PSMA w etapie B; własną asymilację (C5) budujemy dopiero po B.
- D-047: Parametrów gleby nie kalibrujemy z S-1; kalibracja TAW wymaga obserwacji winorośli (ApeX, etap D).

## 6. Najważniejsze źródła

Poziom dostępu: P = pełny tekst, A = abstrakt, F = fragment z wyszukiwania (strony wydawców były częściowo blokowane).

- FAO-56, Allen i in. 1998 — tabele dla winorośli (Kcb, Zr, p, fazy) w transkrypcji `pyfao56` 1.4.3 [P].
- Lebon i in. 2003, Funct. Plant Biol. 30:699 — bilans wodny winnicy, FTSW ↔ potencjał przedświtowy [A].
- Celette, Ripoche, Gary 2010, Agric. Water Manag. 97:1749 — WaLIS, winnica z międzyplonem [F].
- Pellegrino i in. 2004/2005, Plant and Soil 266 — FTSW i potencjał przedświtowy [F].
- Gaudin i in. 2014, J. Int. Sci. Vigne Vin 48 — wskaźnik FTSW vs plon i jakość, 102 sytuacje [F].
- Roux i in. 2025, Agric. Water Manag. (HAL hal-05223516) — TTSW z obserwacji pędów, pogody i S-2 [F].
- Campos i in. 2010, Agric. Water Manag. 98:45 — Kcb z NDVI w winnicy nawadnianej [F].
- Pantaleoni Reluy i in. 2022, OENO One 56(1) — NDVI winnicy a międzyrzędzie [P].
- Laroche-Pinel i in. 2021, Remote Sens. 13:1837 — stan wodny winorośli z S-2 [F].
- van Leeuwen i in. 2009, J. Int. Sci. Vigne Vin 43:121 — δ13C i potencjał łodygowy [A].
- Pichon i in. 2023, OENO One — metoda ApeX vs potencjał przedświtowy [F].
- Gruber i in. 2020, Remote Sens. Environ. 244:111806 — dobre praktyki walidacji wilgotności gleby [F].
- McColl i in. 2014, GRL 41:6229 — rozszerzona potrójna kolokacja [A].
- Albergel i in. 2008, HESS 12:1323 — filtr wykładniczy na SMOSMANIA [F].
- Cammalleri i in. 2021, NHESS 21:481 — rewizja CDI w EDO [A].
- Muñoz-Sabater i in. 2021, ESSD 13:4349 — ERA5-Land [F].
- Ferro i Stephenson 2011, Wea. Forecasting 26:699 — miary dla rzadkich zdarzeń (SEDI) [A].

Pełna lista (ok. 110 pozycji) ze statusem dostępu: `docs/evidence/F4_eksperymenty/zrodla_przeglad.txt`;
pełne wyniki przeglądu, eksperymentów i recenzji: `docs/evidence/F4_eksperymenty/wyniki_workflow.json`.
