# AgriWatch v3: ciągły monitoring wilgotności gleby w winnicach z eksperymentem super-resolution

> **Status:** `APPROVED` (2026-10-06, zatwierdzone przez użytkownika: decyzje D-020…D-023, progi z B.9 i hipotezy z B.5).
> **Zasoby:** 1 osoba, około 10 h tygodniowo, darmowe narzędzia.
> **Architektura (bez zmian):** kod na GitHub → obliczenia w Colab (Jupyter) → Dysk Google jako baza danych (tabele CSV w schemacie gotowym do eksportu do bazy).
> **Struktura repozytorium (bez zmian):** `step_01…07`, `data/`, `docs/`, `notebooks/`.
> **Rozwija:** `docs/evidence/F1_evidence_brief.md` (źródła S01–S20) oraz `docs/plans/Plan_wdrozenia_pipeline.md`. Walidacja z sekcji 5 tego planu pozostaje w mocy.
> **Kod już gotowy:** `step_07_station_pipeline.py` v0.1.0 (stacja Condom, Sentinel-1 change detection, ERA5-Land, walidacja z CI). Selftest przechodzi. Części korzystające z GEE nie były jeszcze uruchomione na prawdziwych danych.

---

## Część A. Przegląd literatury

### A.1 Pytanie

Jak z otwartych danych (Sentinel-1, Sentinel-2, ERA5-Land) zbudować **ciągły monitoring wilgotności powierzchniowej gleby i jej anomalii** dla winnic w Gers? Jak uczciwie podać błąd na podstawie stacji ISMN Condom? Czy super-resolution Sentinel-2 (SEN2SR, 10 → 2,5 m) może coś realnie poprawić? Jeśli tak, to jak to sprawdzić?

### A.2 Nowe źródła (uzupełnienie S01–S20)

Kolumna „Weryfikacja” mówi, jak dokładnie przeczytano źródło. Prace oznaczone `abstrakt` trzeba przeczytać w całości, zanim przejmiemy z nich konkretne parametry.

| ID | Rok | Źródło | Wniosek dla projektu | Weryfikacja |
|---|---:|---|---|---|
| S21 | 1999 | Wagner, Lemoine, Rott, *A method for estimating soil moisture from ERS scatterometer and soil data*, RSE 70:191–207 | Podstawa change detection: wilgotność względna z położenia σ⁰ między odniesieniem suchym i mokrym. Wpływ geometrii stałej w czasie znosi się, jeśli odniesienia liczymy osobno dla każdego piksela i każdej orbity | znana praca |
| S22 | 2017 | Gao, Zribi, Escorihuela, Baghdadi, *Synergetic Use of Sentinel-1 and Sentinel-2 Data for Soil Moisture Mapping at 100 m Resolution*, Sensors 17(9):1966 — [link](https://www.ncbi.nlm.nih.gov/pmc/articles/PMC5621168/) | Change detection S-1 z korektą roślinności przez NDVI z S-2. Najprostszy sprawdzony sposób na wpływ okrywy | abstrakt |
| S23 | 2017 | El Hajj, Baghdadi, Zribi, Bazzi, *Synergic use of Sentinel-1 and Sentinel-2 images for operational soil moisture mapping at high spatial resolution over agricultural areas*, Remote Sensing 9(12):1292 | Podstawa produktu S²MP (S06): inwersja WCM w skali działki, sieć neuronowa, NDVI jako opis roślinności | znana praca |
| S24 | 2025 | Faridani, Mataffo, Corrado, Dente i in., *Integration of Sentinel-1 and -2 imagery through advanced cloud computing improves hillside vineyard soil moisture analysis*, Agric. Water Manag. — [link](https://www.sciencedirect.com/science/article/pii/S0378377425002550) | **Jedyna znaleziona praca o S-1 w winnicach.** Dwie metody change detection w rozdzielczości 20 m (VV + S-2), winnice na stokach we Włoszech, dobrze oddają dynamikę wilgotności w porównaniu z pomiarami in situ. Potwierdza, że nasz rdzeń ma sens w winnicach | abstrakt (pełny tekst za paywallem) |
| S25 | 2021 | Laroche-Pinel i in., *Towards Vine Water Status Monitoring on a Large Scale Using Sentinel-2 Images*, Remote Sensing 13(9):1837 — [RG](https://www.researchgate.net/publication/351437843) | S-2 (czerwone, NIR, red-edge, SWIR) wobec potencjału wodnego łodygi: R² = 0,40. **Sam S-2 słabo mierzy stan wodny winorośli**, więc wilgotność z radaru jest potrzebnym uzupełnieniem | abstrakt |
| S26 | 2020 | Sozzi, Kayad, Marinello, Taylor, Tisseyre, *Comparing vineyard imagery acquired from Sentinel-2 and UAV platform*, OENO One 54(2):189–197 — [HAL](https://hal.inrae.fr/hal-02942190) | Piksel S-2 10 m w winnicy miesza rzędy i międzyrzędzia. Zgodność z NDVI z drona jest umiarkowana. **To uzasadnia eksperyment SR**: problem mieszanych pikseli jest udokumentowany | abstrakt |
| S27 | 2024 | Aybar i in., *A Comprehensive Benchmark for Optical Remote Sensing Image Super-Resolution* (opensr-test) — [GitHub](https://github.com/ESAOpenSR/opensr-test), [preprint](https://www.techrxiv.org/doi/pdf/10.36227/techrxiv.171177496.69538893) | Gotowa biblioteka metryk SR: **spójność** (czy SR zachowuje reflektancję obrazu 10 m), **synteza**, **poprawa / pominięcie / halucynacja** (wymaga obrazu referencyjnego w wysokiej rozdzielczości). Te metryki stosujemy | abstrakt + README |
| S28 | 2025 | Major, Horváth, Kröber i in., *A holistic approach for multi-spectral Sentinel-2 super-resolution and spectral evaluation*, IJRS 46(20):7437–7464 — [link](https://www.tandfonline.com/doi/full/10.1080/01431161.2025.2549132) | SR trzeba oceniać spektralnie pod kątem konkretnego zadania rolniczego, a nie tylko wizualnie | tytuł + streszczenie wyszukiwarki |
| S29 | 2004 | Reichle & Koster, *Bias reduction in short records of satellite soil moisture*, GRL 31:L19501 — [link](https://agupubs.onlinelibrary.wiley.com/doi/10.1029/2004GL020938) | Dopasowanie dystrybuant (CDF matching) pozwala przenieść krótką serię satelitarną na dystrybuantę długiej serii, np. ERA5-Land 1991–2020. Rozwiązuje problem krótkiej klimatologii S-1 (S17) | abstrakt |
| S30 | 2016 | Gruber i in., *Recent advances in (soil moisture) triple collocation analysis*, JAG 45:200–211 — [ADS](https://ui.adsabs.harvard.edu/abs/2016IJAEO..45..200G/abstract) | Triple collocation (S-1, ERA5-Land, in situ) szacuje błąd każdego z trzech źródeł, **także błąd reprezentatywności stacji**. Funkcje są w pytesmo | abstrakt |
| S31 | 2021 | Muñoz-Sabater i in., *ERA5-Land: a state-of-the-art global reanalysis dataset for land applications*, ESSD 13:4349–4383 | Benchmark i długa klimatologia (od 1950) | znana praca |
| S32 | 2023 | Pasquarella i in., *Comprehensive quality assessment of optical satellite imagery using weakly supervised video learning* (Cloud Score+), CVPR Workshops | Maska chmur S-2 lepsza od s2cloudless i dostępna w GEE (`GOOGLE/CLOUD_SCORE_PLUS/V1/S2_HARMONIZED`) | znana praca |
| S33 | 2007 | Calvet i in., *In situ soil moisture observations for the CAL/VAL of SMOS: the SMOSMANIA network*, IGARSS | Opis sieci, czujników i głębokości | znana praca |
| S34 | 2021 | Dorigo i in., *The International Soil Moisture Network: serving Earth system science for over a decade*, HESS 25:5749–5804 | Flagi jakości ISMN i ich ograniczenia (flaga `G` nie wychwytuje dryfu, zob. `Condom_QC.md`) | znana praca |
| S35 | 2012 | Crow i in., *Upscaling sparse ground-based soil moisture observations for the validation of coarse-resolution satellite soil moisture products*, Rev. Geophys. 50:RG2002 | Pojedyncza stacja reprezentuje punkt, a nie piksel. Część „błędu” satelity to w rzeczywistości błąd punktu | znana praca |
| S36 | 2012 | Sepulcre-Canto i in., *Development of a Combined Drought Indicator to detect agricultural drought in Europe*, NHESS 12:3519–3531 | Wzorzec przejścia od anomalii do statusu (obserwacja → ostrzeżenie → alarm) z kilku wskaźników. Podstawa naszego statusu `normal / watch / inspect` | znana praca |
| S37 | 2018 | Lanaras i in., *Super-resolution of Sentinel-2 images: Learning a globally applicable deep neural network* (DSen2), ISPRS J. 146:305–319 | Wyostrzanie pasm 20 m (w tym SWIR) do 10 m sieciami neuronowymi. To dojrzały, sprawdzony krok i dolna granica tego, co robi SEN2SR | znana praca |

### A.3 Dane z repozytorium, które zmieniają plan

**1. Winnice w AOI** (`data/1_AOI_GBOV_CONDOM.geojson`, 15 poligonów, łącznie 33,2 ha)

Policzyłem, jaka część powierzchni działki zostaje po odcięciu jednego piksela od brzegu. Brzeg odcinamy, bo piksel graniczny miesza winnicę z drogą lub sąsiednią uprawą:

| Rozdzielczość | Średnio zostaje | Najmniejsza działka (0,68 ha) |
|---|---:|---:|
| 20 m (S-1, pasma SWIR S-2) | 45% | 22% |
| 10 m (S-2) | 70% | 54% |
| 2,5 m (SEN2SR) | 92% | 87% |

To **mierzalna i uczciwa hipoteza dla SR**: więcej czystych pikseli w małych działkach i mniej zanieczyszczenia brzegiem. Nie zakładamy żadnej „ukrytej informacji” w obrazie.

**2. Rzędy winorośli nie zostaną rozdzielone w 2,5 m.** Rozstaw rzędów to typowo 2–3 m (do sprawdzenia na ortofotomapie IGN). Okresowy wzór rozróżnimy dopiero przy pikselu co najmniej dwa razy mniejszym niż okres, czyli 1–1,5 m. SR 2,5 m **nie oddzieli rzędu od międzyrzędzia**. Usuwamy to z celów projektu (w planie z 26 IX było jako eksperyment).

**3. Stacja Condom nie leży w winnicy.** Poligon `stacja` ma 210 m² i jest oddalony o 136 m od najbliższej winnicy. ESA CCI klasyfikuje okolicę jako „Cropland, rainfed / Tree or shrub cover”.

**4. Stacje SMOSMANIA w podobnym otoczeniu.** Ten sam typ terenu (CCI 12) mają Cabrières-d'Avignon, Pézenas (oraz Pézenas-old i Prades-le-Lez, liczone jako jedna grupa) i Villevielle. Wszystkie leżą w regionach winiarskich. Najbliższe Condom stacje w Gers i okolicy (CCI 10) to Peyrusse-Grande, Créon-d'Armagnac, Montaut i Lahas.

**Konsekwencja:** stacja Condom jest **pełnoprawnym obiektem monitoringu** (`site_type = station`). Wilgotność liczymy w miejscu, w którym stoi czujnik, tym samym kodem co dla winnic, i porównujemy z pomiarem. To jest walidacja. W winnicach podajemy produkt z etykietą „niezwalidowany lokalnie” i z błędem przeniesionym ze stacji, bo metoda i kod są identyczne.

**Rozmiar obszaru wokół stacji.** Poligon `stacja` ma 210 m²: to około 2 piksele S-2 10 m, około 34 piksele SR 2,5 m i mniej niż jeden niezależny piksel S-1, którego rzeczywista rozdzielczość to około 20 m. Dlatego wilgotność z S-1 dla stacji liczymy w kilku obszarach i sprawdzamy, jak zmienia się wynik (B.4):

| Obszar | S-1 | S-2 10 m | SR 2,5 m |
|---|---|---|---|
| Poligon stacji (210 m²) | za mały, tylko kontrola | ~2 piksele | ~34 piksele |
| Bufor 50 m (obecny `STATION_BUFFER_M`) | ~20 niezależnych pikseli | ~78 | ~1250 |
| Bufor 100 m | ~80 | ~310 | ~5000 |
| To samo pole uprawne co stacja (do wyrysowania na ortofotomapie) | zależnie od pola | zależnie od pola | zależnie od pola |

### A.4 Synteza: co jest dobrą praktyką, a co eksperymentem

| Element | Status w literaturze | Decyzja |
|---|---|---|
| S-1 change detection, odniesienia per piksel i per orbita (S08, S21) | Dojrzałe, operacyjne (CLMS) | **Rdzeń**, już w `step_07` |
| Korekta roślinności przez NDVI z S-2 (S22, S23) | Sprawdzone na uprawach polowych; w winnicach tylko S24 | **Wariant B** rdzenia, porównany z A |
| S-1 w winnicach: konstrukcja szpalerów, rzędy, stoki | Stała geometria znosi się w odniesieniach per orbita (S21). Zmienność sezonowa liści już nie | Flagi `DENSE_VEGETATION` i NDVI w modelu B |
| Głębokość pomiaru: S-1 ~1–3 cm, czujnik 5 cm (S10) | Udokumentowany rozjazd w suchych okresach | Raportujemy metryki osobno dla lata i zimy |
| Anomalia krótkoterminowa, okno 35 dni (S03) | Standard QA4SM | Do walidacji dynamiki |
| Anomalia klimatologiczna z krótkiej serii (S17) | Niestabilna przy ~9 latach | Klimatologia S-1 plus kontekst ERA5-Land 1991–2020 i CDF matching (S29) |
| Status z anomalii (S36) | Sprawdzony wzorzec EDO | `normal / watch / inspect` + `confidence` + `reason_codes` |
| Błąd względem stacji (S01, S02, S35) | R, ubRMSD, bias dla wartości surowych i anomalii, CI, n | Już w `step_07` |
| Triple collocation (S30) | Standard dla rozdzielenia błędów | **Nowe**: oddziela błąd satelity od błędu reprezentatywności stacji |
| SR S-2 10 → 2,5 m (S16, S27, S28) | Nowe; brak prac o wilgotności | **Eksperyment** z hipotezami zapisanymi przed testem (B.5) |
| OPTRAM z SR (S12) | OPTRAM sprawdzony na 10–30 m; na SR nikt nie testował | Część eksperymentu SR |

### A.5 Zdania, których nie używamy

- „Wilgotność gleby w rozdzielczości 2,5 m”. Poprawnie: „indeksy optyczne 2,5 m (SR) jako wzór w działce, wilgotność z radaru w skali działki”.
- „Zwalidowane w winnicach”. Poprawnie: „zwalidowane na stacji Condom i stacjach SMOSMANIA w podobnym otoczeniu”.
- „SR rozdziela rzędy winorośli”. Jest to fizycznie niemożliwe przy 2,5 m.
- „Anomalia = susza”. Poprawnie: „anomalia zgodna z przesuszeniem warstwy powierzchniowej”.

---

## Część B. Plan wdrożenia

### B.1 Co dostajesz na końcu

Jeden notatnik w Colab. Raz w tygodniu wykonujesz „Uruchom wszystko” (około 10–15 minut, bez ręcznych kroków). Notatnik:

1. dociąga **tylko nowe dane** S-1, S-2 i ERA5-Land dla wszystkich obiektów: stacji i 15 winnic,
2. liczy wilgotność z S-1, anomalie i status każdej winnicy,
3. uruchamia SR dla nowych bezchmurnych scen (eksperyment),
4. gdy pojawią się nowe dane ISMN, ponownie liczy walidację i tabelę błędów,
5. pokazuje panel: status dziś, wykres serii, tabelę błędów i historię uruchomień.

Wszystko jest zapisywane na Dysku w tabelach `gwl_*`, gotowych do importu do bazy danych.

### B.2 Przepływ danych

```text
                ┌─────────────── co tydzień, przyrostowo ───────────────┐
GEE: S-1 GRD ───┤ reduceRegions dla wszystkich obiektów naraz           ├─► gwl_observations
GEE: S-2 + CS+ ─┤ (stacja + 15 winnic + pozostałe działki)              │   (dopisywanie z kluczem,
GEE: ERA5-Land ─┤ okno: od znacznika ostatniej daty minus 30 dni do dziś│    bez duplikatów)
                └───────────────────────────────────────────────────────┘
                                         │
         zamrożona kalibracja (calib_id) ▼
   S-1 change detection A (bazowy) i B (z korektą NDVI) ─► SM per obiekt i data
                                         │
       zamrożona klimatologia (clim_id)  ▼
   anomalie: 35-dniowe, klimatologiczne (z, percentyl), kontekst ERA5 1991–2020 ─► gwl_anomalies
                                         │
                                         ▼
   status normal / watch / inspect + confidence + reason_codes ─► panel w notatniku

ISMN (ręcznie, co kwartał: zip do data/7_isismn_data) ─► walidacja ─► gwl_validation_metrics
                                                              └─► tabela błędów wg sezonu i NDVI
                                                                  (niepewność każdego wyniku)

S-2 (bezchmurne sceny AOI) ─► SEN2SR 2,5 m ─► test spójności ─► NDVI / STR / OPTRAM per działka
                                                              └─► gwl_observations (product = S2SR)
```

### B.3 Zasady ciągłej obserwacji

| Zasada | Wykonanie |
|---|---|
| **Pobieramy tylko brakujące dane** | Każde źródło ma w `gwl_runs` znacznik ostatniej daty. Pobieranie zaczyna się 30 dni przed znacznikiem, bo dane ERA5-Land i S-1 dochodzą z opóźnieniem. Obecny cache fragmentów CSV w `step_07` zostaje jako warstwa pośrednia |
| **Bez duplikatów** | Dopisywanie z kluczem `(site_id, product, variable, time_utc, orbit)`. Nowsza wersja wiersza zastępuje starszą (upsert) |
| **Historia się nie zmienia** | Odniesienia suche i mokre S-1 oraz klimatologia są **zamrożone** (`calib_id`, `clim_id`) i liczone z okresu kalibracji. Nowe dane nie przesuwają starych wyników. Rekalibracja to osobne, świadome zadanie, np. raz w roku, z nowym identyfikatorem |
| **Każde uruchomienie jest zapisane** | `gwl_runs`: czas, zadanie, commit Git, wersja, parametry, liczba nowych wierszy, status, komunikat błędu |
| **Kontrola jakości przy każdym uruchomieniu** | Brak S-1 przez ponad 14 dni → ostrzeżenie. σ⁰ odchylone o ponad 3 dB od mediany orbity → flaga. Pojawienie się Sentinel-1C → porównanie poziomu σ⁰ z S-1A na tych samych orbitach, zanim użyjemy go w kalibracji |
| **Dane naziemne** | ISMN nie ma otwartego API. Raz na kwartał pobierasz zip z portalu (logowanie robisz sam) i wrzucasz do `data/7_isismn_data`. Pipeline rozpoznaje nowe pliki po sumie kontrolnej i ponownie liczy walidację |
| **Brak harmonogramu w darmowym Colab** | „Ciągła obserwacja” to jedno kliknięcie w tygodniu. Automatyczny harmonogram (GitHub Actions z kontem serwisowym GEE) zostaje na liście „później” |

### B.4 Metody (wybrane na podstawie Części A)

**Wilgotność z S-1** (`step_07`, rozszerzenie)
- **A, bazowy:** change detection per orbita z obecnego `step_07` (S08, S21).
- **B, z korektą roślinności:** odniesienie suche zależne od NDVI, dopasowane na niskich percentylach σ⁰ w klasach NDVI (S22). Wariant B wchodzi do produktu tylko wtedy, gdy na stacji testowej poprawi R lub ubRMSD, a przedział ufności różnicy nie obejmuje zera.
- Agregacja: średnia σ⁰ w skali liniowej w obrębie działki po odcięciu 20 m od brzegu. Liczba pikseli trafia do tabeli. Działka z mniej niż 20 pikselami S-1 dostaje `confidence = low`.

**Anomalie** (trzy rodzaje, każdy do innego celu)
1. **35-dniowa** (`pytesmo calc_anomaly`, okno 35 dni): tylko do walidacji dynamiki.
2. **Klimatologiczna S-1:** klimatologia dnia roku z okresu kalibracji (`pytesmo calc_climatology`) i rozrzut z okna ±15 dni. Wynik: z-score oraz percentyl.
3. **Kontekst długoterminowy:** percentyl ERA5-Land wobec lat 1991–2020 w tym samym punkcie. Eksperymentalnie: S-1 przeskalowany na dystrybuantę ERA5-Land (CDF matching, S29), żeby wyrazić anomalię S-1 w klimatologii 30-letniej.

**Status** (wzorzec z S36; progi zapisane przed testem)

| Status | Warunek |
|---|---|
| `watch` | Percentyl S-1 < 20 |
| `inspect` | Percentyl S-1 < 10 w dwóch kolejnych przelotach **i** zgodny kierunek ERA5-Land |
| `confidence` | Niższa przy flagach `DENSE_VEGETATION`, `POSSIBLE_FROZEN`, opadzie w ciągu 24 h, małej liczbie pikseli albo rozbieżności z ERA5-Land |
| `reason_codes` | Lista powodów, np. `S1_P10_2X;ERA5_AGREE;NDVI_HIGH` |

Status sprawdzamy na stacji: POD i FAR dla epizodów, w których czujnik spada poniżej 20. percentyla.

**Błąd względem obserwacji naziemnych** (`step_07`, rozszerzenie)
- Bez zmian: R, ρ, bias, ubRMSD i R anomalii, z 95% CI z bootstrapu blokowego. Liczone osobno dla segmentów czujnika, okresu kalibracji i testu, oraz zbiorów `all` i `ndvi≤0,7`.
- **Nowe — tabela błędów:** ubRMSD i R w podziale na sezon (DJF, MAM, JJA, SON) i klasę NDVI. Każdy nowy wynik w winnicy dostaje oczekiwany błąd z odpowiedniej komórki tej tabeli (np. „±0,06 m³/m³, lato, NDVI > 0,6”).
- **Nowe — triple collocation** (S-1, ERA5-Land, in situ; S30): odchylenie standardowe błędu każdego źródła. Odpowiada na pytanie, czy rozjazd z czujnikiem wynika z błędu satelity, czy z reprezentatywności punktu (S35).
- **Nowe — reprezentatywność obszaru stacji:** te same metryki dla S-1 w poligonie, buforze 50 m, buforze 100 m i polu, na którym stoi czujnik. Jeśli wynik mocno zależy od obszaru, część błędu wynika z niejednorodności otoczenia, a nie z metody. Obszar referencyjny wybieramy na okresie kalibracji i zamrażamy przed testem, żeby nie dopasować go do wyniku.
- **Nowe — druga linia dowodu:** ta sama walidacja dla stacji z A.3 pkt 4. Wynik pokazuje przenośność metody, bo w change detection nie ma treningu. Tabela per stacja to najmocniejszy argument dla rekrutera.

### B.5 Eksperyment super-resolution

**Cel:** sprawdzić w sposób powtarzalny i opublikowalny, **czy i gdzie** SEN2SR pomaga w monitoringu małych winnic. Wynik negatywny też jest wynikiem, który pokazujemy.

**Przygotowanie** (`step_03`, naprawy już opisane):
- K-09: pobranie modelu `mlstac`; brak modelu kończy się wyraźnym błędem, bez cichego przejścia na interpolację.
- K-17: poprawna kolejność pasm.
- K-14: siatka przez `rasterio`.
- Model `SEN2SRLite/main` (10 pasm, w tym SWIR).
- AOI ma tylko ~1,8 × 1,5 km (180 × 150 pikseli 10 m), więc SR jednej sceny jest tani i wykonalny także na CPU. Zapisujemy indeksy per działka; rastry tylko dla dat pokazowych.

**Hipotezy** (zapisane przed testem; progi do zatwierdzenia):

| ID | Hipoteza | Test | Biblioteka / dane | Próg sukcesu |
|---|---|---|---|---|
| H-SR1 | SR zachowuje radiometrię S-2 | SR uśredniony do 10 m wobec oryginału, per pasmo i scena | opensr-test (spójność, S27) | Błąd reflektancji ≤ 0,01; scena powyżej progu jest odrzucana |
| H-SR2 | Struktury 2,5 m są prawdziwe, a nie wymyślone | Porównanie SR (RGBN) z ortofotomapą IGN BD ORTHO IRC 20 cm (otwarta), uśrednioną do 2,5 m | opensr-test (poprawa / halucynacja) | Udział „poprawy” > udział „halucynacji” na krawędziach działek |
| H-SR3 | Więcej czystych pikseli daje mniej szumu w serii czasowej działki | Seria NDVI / STR / OPTRAM per winnica: 10 m (rdzeń bez brzegu 10 m) wobec SR 2,5 m (rdzeń bez brzegu 2,5 m). Miara: szum między kolejnymi scenami | pandas | Szum mniejszy o co najmniej 10%, z CI, w działkach < 2 ha |
| H-SR3b | SR pozwala opisać optycznie dokładnie miejsce czujnika | NDVI / STR / OPTRAM w poligonie stacji: 10 m (~2 piksele, praktycznie piksel mieszany) wobec SR (~34 piksele). Miara: korelacja OPTRAM z czujnikiem 5 cm w dni bezchmurne | pytesmo | R dla SR wyższe o ≥ 0,05, CI różnicy bez zera |
| H-SR4 | Wzór SR wnosi informację o wilgotności | Ablacja na stacji: S-1 (A/B) wobec S-1 + OPTRAM 10 m wobec S-1 + OPTRAM SR. Okres testowy; potem stacje z A.3 pkt 4 | pytesmo, scikit-learn (regresja liniowa) | ΔR ≥ 0,05 i CI różnicy bez zera |

**Interpretacja:**
- H-SR1 i H-SR2 zaliczone, H-SR3 zaliczone, H-SR4 nie: SR to **lepsza statystyka działki** (wiarygodna i pokazywalna), a nie lepsza wilgotność. Tak to opisujemy.
- Wszystkie zaliczone: SR wchodzi do produktu jako wzór przestrzenny w fuzji z S-1 (fuzja z zachowaniem średniej z `Plan_wdrozenia_pipeline.md`, pkt 3).
- H-SR1 niezaliczone: SR zostaje tylko jako wizualizacja.

**Dlaczego to jest nowatorskie:** w znalezionej literaturze nie ma testu SR S-2 pod kątem monitoringu wilgotności w winnicach z kontrolą halucynacji na ortofotomapie i ablacją na stacjach ISMN. Każdy element jest gotowy i opublikowany (SEN2SR, opensr-test, change detection, pytesmo). Nowe jest ich połączenie i uczciwy test.

### B.6 Zmiany w kodzie (w istniejących plikach)

| Plik | Zmiana | Nowe funkcje |
|---|---|---|
| `step_05_colab_run.py` | Sterowanie i rejestr na Dysku | `setup_runtime()` (Dysk, git, GEE, ścieżki, Colab lub lokalnie), `run_task(name, fn, rt)` (log do `gwl_runs`, wyłapanie błędu, pominięcie zadania, jeśli brak nowych danych), `run_history()`, `registry_read(table)`, `registry_upsert(table, df, keys)` |
| `step_07_station_pipeline.py` | Z „jednej stacji” na „listę obiektów”; tryb przyrostowy | `load_sites()` (geojson + stacje ISMN → `gwl_sites`), `update_observations()` (znacznik daty, `reduceRegions` dla wszystkich obiektów), `s1_change_detection` z wariantem B, `compute_anomalies()`, `site_status()`, `error_budget()`, `triple_collocation()`. `END_DATE = "today"` |
| `step_03_super_resolve.py` | Naprawy K-09, K-17, K-14; SR przyrostowo | `update_sr_scenes()`, `sr_consistency()` (opensr-test), `sr_parcel_indices()` |
| `step_01_ingest.py` | Bez przebudowy | Opcjonalnie Cloud Score+ jako alternatywna maska (S32) |
| `build_colab_master.py` | Generuje notatnik sterujący | `notebooks/AgriWatch_Monitor.ipynb` (6 komórek, B.7) |
| `step_02`, `step_04`, `step_06` | **Bez zmian, wyłączone z cotygodniowego uruchomienia** | — |

**Tabele na Dysku** (`data/registry/`, CSV; nazwy kolumn są nazwami kolumn przyszłej bazy):

| Tabela | Klucz | Najważniejsze kolumny |
|---|---|---|
| `gwl_sites` | `site_id` | `site_type` (station / parcel), `name`, `land_use`, `lat`, `lon`, `geometry_wkt`, `area_m2`, `network` |
| `gwl_observations` | `site_id, product, variable, time_utc, orbit` | `value`, `unit`, `n_pixels`, `qc_flags`, `calib_id`, `run_id`, `ingested_at` |
| `gwl_anomalies` | `site_id, product, date` | `value`, `clim_mean`, `z`, `percentile`, `era5_percentile_1991_2020`, `status`, `confidence`, `reason_codes`, `expected_error`, `clim_id` |
| `gwl_validation_metrics` | `site_id, product, reference, segment, period, subset, metric` | `value`, `ci_low`, `ci_high`, `n`, `date_from`, `date_to`, `run_id` (ostatnie uruchomienie, które zmieniło wartość) |
| `gwl_calibrations` | `calib_id, site_id, product, orbit, param` | `value`, `period_start`, `period_end` |
| `gwl_runs` | `run_id` | `task`, `started_at`, `finished_at`, `git_commit`, `pipeline_version`, `params_json`, `status`, `n_new_rows`, `message` |

### B.7 Notatnik `AgriWatch_Monitor.ipynb`

| Komórka | Kod | Czas |
|---|---|---|
| 1. Start | `rt = setup_runtime()` (Dysk, `git pull`, instalacja, GEE) | ~2 min |
| 2. Nowe dane | `run_task("update", update_observations, rt)` | 1–5 min |
| 3. Wilgotność i status | `run_task("sm_status", update_status, rt)` | < 1 min |
| 4. Walidacja | `run_task("validate", run_station_pipeline, rt)` (pomijana, gdy brak nowych danych ISMN) | ~1 min |
| 5. SR (opcjonalnie) | `run_task("sr", update_sr_scenes, rt)` | 1–2 min na scenę |
| 6. Panel | Status winnic dziś, wykres Condom, tabela błędów, `run_history()` | — |

### B.8 Harmonogram (około 10 h tygodniowo; zastępuje część projektową `Plan_6_tygodni.md`, część kariery zostaje)

| Etap | Termin | Zakres | Artefakt do pokazania |
|---|---|---|---|
| **E0. Pierwszy prawdziwy wynik** | 6–12 X | `setup_runtime`, `run_task`, rejestr; pierwsze uruchomienie `step_07` na GEE dla Condom; poprawki błędów GEE | `station_report.md` na prawdziwych danych: S-1 wobec czujnika i ERA5-Land, metryki z CI |
| **E1. Tryb ciągły** | 13–19 X | Znaczniki dat, upsert, `END_DATE = today`, kontrola S-1C, zamrożona kalibracja i klimatologia, trzy rodzaje anomalii, status | Wykres 2016 → dziś z anomaliami i statusem; drugie uruchomienie dopisuje tylko nowe dane |
| **E2. Winnice** | 20–26 X | `gwl_sites` z geojson; S-1 A/B i indeksy S-2 per działka; status per winnica; tabela błędów | Tabela i mapa statusu 15 winnic z oczekiwanym błędem |
| **E3. Walidacja szersza** | 27 X – 2 XI | Wariant B wobec A; obszary stacji (poligon, 50 m, 100 m, pole); triple collocation; walidacja na 4–6 stacjach SMOSMANIA | Tabela błędów per stacja + tabela TC |
| **E4. SR — przygotowanie** | 3–9 XI | Naprawy `step_03`; SR dla bezchmurnych scen AOI; H-SR1; pobranie ortofotomapy IGN dla AOI | Porównanie 10 m i 2,5 m + metryki spójności |
| **E5. SR — test** | 10–16 XI | H-SR2, H-SR3, H-SR4 | Tabela ablacji z CI: co daje SR |
| **E6. Publikacja** | 17–30 XI | README EN, raport EN, sekcja na stronie GeoWorldLook, film 5 min; przeniesienie repozytorium poza firmowy OneDrive | Publiczny projekt + link w CV |

**Kolejność cięć przy opóźnieniu:** najpierw CDF matching i H-SR2, potem wariant B, potem stacje dodatkowe ponad dwie. **Nigdy nie tniemy E0, E1 ani E2**: bez nich nie ma działającego produktu.

### B.9 Kryteria sukcesu (zapisane przed testem)

| Wynik | Próg „działa” | Źródło progu |
|---|---|---|
| S-1 wobec czujnika Condom, okres testowy, R danych surowych | ≥ 0,5 | S07: R ≈ 0,56 dla S-1 + S-2 w 1 km na SMOSMANIA |
| ubRMSD | ≤ 0,06 m³/m³ | S07: SDD 0,05–0,06; S05: RMSD ≈ 0,076 |
| R anomalii 35-dniowych | ≥ 0,4 | Wartość robocza do zatwierdzenia |
| Status `inspect` wobec suszy w czujniku | POD ≥ 0,6 przy FAR ≤ 0,4 | Wartość robocza do zatwierdzenia |
| SR | Zgodnie z B.5 | — |

Jeśli S-1 nie przejdzie progów, a ERA5-Land wypadnie lepiej, piszemy to wprost. Dla rekrutera to też wartościowy wynik: pokazuje, że umiesz walidować, a nie tylko produkować mapy.

### B.10 Ryzyka

| Ryzyko | Obejście |
|---|---|
| Limity GEE przy `reduceRegions` dla wielu działek | Fragmenty 6–12 miesięcy (już są); tylko punkty i poligony, bez rastrów |
| S-1C nie ma jeszcze w GEE albo ma inny poziom kalibracji | Kontrola w E1; do czasu sprawdzenia S-1C nie wchodzi do kalibracji |
| Okres testowy 2022–2024 ma tylko S-1A (rewizyta 12 dni) | Mniej par do walidacji; raportujemy n i CI |
| Ortofotomapa IGN z innego roku lub sezonu niż sceny S-2 | H-SR2 tylko dla stałych struktur (granice działek, drogi) |
| Opóźnienie danych ISMN (miesiące) | Bieżący błąd = tabela błędów z ostatniej walidacji; data walidacji widoczna w panelu |
| Brak czasu | Cięcia z B.8 |
| GEE i Colab tylko do użytku niekomercyjnego | Projekt jest portfolio; sprzedaż wymagałaby ingestii z CDSE (lista „później”) |

### B.11 Lista „później”

GitHub Actions z harmonogramem; Supabase i mapa na stronie; LST i pyDMS; model ML na wielu stacjach (LOSO); wilgotność strefy korzeniowej (filtr wykładniczy, S04); CLMS SSM 1 km jako dodatkowy benchmark.

---

## Decyzje (zatwierdzone 2026-10-06)

| ID | Decyzja |
|---|---|
| D-020 | Produkt v3 = ciągły monitoring wilgotności z S-1 i anomalii dla winnic, z błędem podanym na podstawie stacji ISMN; SR jako eksperyment z hipotezami H-SR1…4 |
| D-021 | `step_07` rozszerzony z jednej stacji na listę obiektów; rejestr `gwl_*` w `data/registry/` na Dysku; notatnik `AgriWatch_Monitor.ipynb` |
| D-022 | Cel „SR rozdziela rzędy i międzyrzędzia” usunięty (niemożliwy fizycznie przy 2,5 m) |
| D-023 | Harmonogram E0–E6 (do 30 XI 2026) zastępuje część projektową `Plan_6_tygodni.md` |
