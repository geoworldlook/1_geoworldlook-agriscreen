# A4 — kontrola jakości czujników ISMN Condom: utrata kontaktu w glinie (notatka metodyczna)

> **Status:** `PROPOSED` (2026-10-14) — metoda do zatwierdzenia **przed** napisaniem kodu i przed policzeniem
> jakichkolwiek metryk walidacji (pre-rejestracja, D-063). Plan v7 krok A4, Plan v8 moduł 1.
> **Dane:** `data/7_isismn_data/SMOSMANIA/Condom/*.stm` (2016-01-01 → 2024-12-31), tylko rekordy z flagą ISMN `G`.
> **Odtworzenie liczb:** `python docs/evidence/A4_QC/a4_explore.py` (wynik: `docs/evidence/A4_QC/a4_explore.log`).
> Skrypt opisuje wyłącznie dane referencyjne; nie liczy metryk produktu.

## Wynik w skrócie

1. Czujniki 20 i 30 cm przez **35–41% dni** (zależnie od progu) pokazują wartości fizycznie niemożliwe dla tej gleby:
   0,01–0,05 m³/m³ przy punkcie więdnięcia ≈ 0,27 m³/m³. Dotyczy to prawie całego lata i jesieni w latach 2017–2019
   i 2022–2023. To nie jest drobna poprawka QC-4 z `Condom_QC.md`, tylko większość suchych okresów referencji.
2. Najbardziej prawdopodobna przyczyna to **utrata kontaktu czujnika z glebą** w pęczniejącej glinie (szczeliny przy
   wysychaniu). Flagi ISMN tego nie wychwytują (brak flagi D09 w całym okresie).
3. Wykluczenie tych dni usunęłoby większość suchych epizodów, czyli dokładnie to, co walidujemy. Proponuję więc
   **cenzurowanie**: dzień oznaczony traktujemy jako „sucho, wartość nieznana poniżej progu”, a nie jako brak danych.
4. Wszystkie obecne liczby walidacji gleby i roślinności (R 0,58, POD/FAR, Brier, ρ = 0,58 w prawdopodobieństwie suszy,
   R NDVI) policzono na referencji z tymi artefaktami. Zostaną przeliczone po wdrożeniu A4; nie zakładamy z góry, w którą
   stronę się zmienią.

## 1. Co pokazują dane

**Gleba in situ** (`static_variables.csv`): ił pylasty, 41–46% iłu. Punkt więdnięcia z tekstury i materii organicznej
(Saxton i Rawls 2006): 0,246 (5 cm), 0,264 (10 cm), 0,271 (20 cm), 0,273 m³/m³ (30 cm).

**Rozkład wartości godzinowych (flaga G):**

| Głębokość | min | 1. percentyl | 5. percentyl | mediana |
|---|---|---|---|---|
| 5 cm | 0,038 | 0,046 | 0,056 | 0,218 |
| 10 cm (do XI 2020) | 0,120 | 0,135 | 0,152 | 0,331 |
| 20 cm | 0,001 | 0,022 | 0,032 | 0,265 |
| 30 cm | 0,011 | 0,012 | 0,014 | 0,298 |

**Dni ze średnią dobową poniżej progu (20 cm / 30 cm):**

| Rok | < 0,05 | < 0,10 | < 0,135 (≈ 0,5·WP) |
|---|---|---|---|
| 2016 | 0 / 7 | 73 / 88 | 97 / 97 |
| 2017 | 148 / 192 | 196 / 218 | 208 / 222 |
| 2018 | 71 / 76 | 100 / 106 | 111 / 114 |
| 2019 | 90 / 99 | 114 / 113 | 134 / 151 |
| 2020 | 4 / 12 | 44 / 65 | 91 / 89 |
| 2021 | 0 / 18 | 20 / 107 | 70 / 120 |
| 2022 | 1 / 151 | 131 / 184 | 180 / 194 |
| 2023 | 0 / 90 | 101 / 103 | 119 / 107 |
| 2024 | 0 / 0 | 11 / 65 | 61 / 72 |

Na 3158 dni z obiema głębokościami co najmniej jeden czujnik jest poniżej 0,10 przez 1121 dni (35%),
poniżej 0,135 przez 1242 dni (39%).

**Trzy znaki, że to artefakt, a nie susza:**

1. **Odwrócony profil.** W dniach, gdy 20 cm < 0,05, mediana tego samego dnia wynosi 0,199 na 5 cm i 0,232 na 10 cm;
   w 100% tych dni głębsza warstwa jest „suchsza” od powierzchni. Pod trawą w lecie jest odwrotnie: powierzchnia
   wysycha pierwsza. W latach 2016–2020, gdy działał czujnik 10 cm (ten sam typ ML3, ta sama glina), jego minimum
   wyniosło 0,122, a 20 i 30 cm schodziły do 0,020 i 0,011.
2. **Wartości poniżej możliwych fizycznie.** 0,01–0,05 m³/m³ to 4–18% punktu więdnięcia. Na głębokości 20–30 cm
   w klimacie umiarkowanym korzenie trawy nie odbierają wody tak daleko poniżej punktu więdnięcia.
3. **Niefizyczne skoki.** Wzrosty do +0,33 m³/m³ w ciągu godziny (np. 2019-08-07 01:00: 0,030 → 0,291), z czego
   33 (20 cm) i 38 (30 cm) bez żadnego wzrostu na 5 cm w poprzednich 48 h. Spadki o więcej niż 0,05 w ≤ 6 h: 41 dni
   (20 cm) i 27 dni (30 cm), a dla porównania 0 dni na 10 cm. Utrata 0,05 m³/m³ w warstwie ok. 10 cm to 5 mm wody
   w 6 h — więcej niż parowanie terenowe może odebrać w tym czasie.

## 2. Mechanizm i literatura

- **Szczelina powietrzna zaniża odczyt.** Czujniki dielektryczne mierzą przenikalność w małej objętości wokół prętów;
  powietrze (przenikalność ≈ 1) obok prętów obniża odczyt wilgotności. W laboratorium szczelina z powietrzem między
  prętami TDR zaniżała pomiar nawet o 46%, ale głównie w wilgotniejszej glebie; w suchej efekt był mały (Hokett i in.
  1992). To dowód kierunku, nie wielkości: tamten układ (jedna szczelina między prętami TDR) różni się od czujnika,
  wokół którego gleba kurczy się ze wszystkich stron. W glinie pęczniejącej szczeliny otwierają się przy
  wysychaniu, a zamykają po nawilżeniu, co pasuje do obrazu: powolny spadek do 0,01–0,05 latem i nagły powrót po deszczu
  (woda spływa szczelinami do czujnika albo kontakt wraca po pęcznieniu).
- **Kalibracja tego nie tłumaczy.** W czarnej glinie (Vertosol) fabryczna kalibracja ThetaProbe zawyżała odczyt na sucho,
  a zaniżała na mokro (Foley i Harris 2007). Błąd kalibracji przesuwałby więc suche odczyty w górę, a nie do 0,01.
  Ten sam typ czujnika na 10 cm w tej samej glinie nie schodzi poniżej 0,12.
- **Flagi ISMN tego nie łapią.** Automatyczna kontrola ISMN (Dorigo i in. 2013) ma flagę D09 „stałe niskie wartości
  po spadku”, ale tu spadek jest powolny, a wartości nie są stałe; w plikach Condom nie ma ani jednego D09. Flagi D08
  („skoki”) oznaczyły tylko 45 godzin na 20 cm i 36 na 30 cm, przy 249 i 187 godzinowych wzrostach ≥ 0,03.
- **Zasada walidacji.** Dobre praktyki walidacji wilgotności gleby (Gruber i in. 2020) wymagają opisania wpływu kontroli
  jakości referencji na wynik, a nie tylko podania wyniku po kontroli.

## 3. Proponowane reguły (ustalone przed policzeniem metryk)

Dotyczą czujników 20 i 30 cm (strefa korzeni w walidacji). Dotychczasowe reguły zostają: flaga ISMN `G`, zakres
0–0,60, wartość stała ≥ 7 dni (QC-5), okres wymiany czujnika 5 cm (QC-1).

| Kod | Reguła | Uzasadnienie a priori |
|---|---|---|
| `LOW_IMPLAUSIBLE` | średnia dobowa < **θ_dno = 0,10 m³/m³** | 37% punktu więdnięcia (0,27); niżej niż minimum czujnika 10 cm w tym samym profilu (0,122). Próg ostrożny: oznacza tylko wartości jednoznacznie niemożliwe |
| `FAST_DROP` | spadek o > 0,05 m³/m³ w ≤ 6 h (cały dzień oznaczony) | 5 mm wody w 6 h z warstwy ok. 10 cm — więcej, niż parowanie może odebrać; reguła nie oznacza żadnego dnia na dobrze działającym czujniku 10 cm |

**Wrażliwość (raportowana, nie główna):** θ_dno = 0,5·WP (0,136 na 20 cm, 0,137 na 30 cm) i 0,15.
Wzrostów nie oznaczamy: szybki wzrost po deszczu w pękającej glinie może być prawdziwy (woda w szczelinach).

## 4. Co robimy z dniami oznaczonymi — najważniejsza decyzja

| Wariant | Co | Zaleta | Wada |
|---|---|---|---|
| **W1 cenzurowanie (proponowany główny)** | dzień `LOW_IMPLAUSIBLE`: wartość czujnika = θ_dno i flaga „cenzurowany”; dzień `FAST_DROP`: brak danych | zachowuje informację „sucho” (szczeliny otwierają się, bo gleba wyschła); wszystkie dni oznaczone mają tę samą, najniższą rangę | wartość bezwzględna umowna; w cenzurowanym okresie nie ma informacji o zmienności |
| W2 wykluczenie | dni oznaczone usunięte (dosłownie wg Planu v7 A4) | prosty | usuwa 35–41% dni, prawie wszystkie suche epizody; POD/FAR i Brier liczone głównie na sezonie mokrym |
| W3 bez nowego QC | jak dziś | ciągłość z dotychczasowymi liczbami | referencja z artefaktami |

**Jak liczymy metryki w W1:**
- strefa korzeni = średnia 20 i 30 cm po cenzurowaniu; dzień jest cenzurowany, gdy którykolwiek czujnik jest cenzurowany;
- R Pearsona anomalii (jak dziś) **i** ρ Spearmana: miara rangowa nie zależy od umownej wartości θ_dno;
- zdarzenia suche (z ≤ −1): dni cenzurowane zostają w zbiorze jako suche;
- W2 i W3 zawsze w tej samej tabeli, z tymi samymi przedziałami ufności (bootstrap blokowy 30 dni).

## 5. Raport i kryteria akceptacji

- Tabela: liczba dni oznaczonych per rok, głębokość i reguła (oraz dla progu z wrażliwości).
- Metryki walidacji dla W1, W2, W3 obok siebie, z CI i liczbą dni lub dekad: R i ρ anomalii gleby, POD/FAR suchych
  dekad, R NDVI winnicy. Brier dochodzi w kroku A5 na tej samej referencji.
- **Kryterium akceptacji A4:** reguły i wariant główny wdrożone dokładnie jak zahashowano (D-063); raport podaje dni
  oznaczone i wpływ na metryki; selftest przechodzi. Akceptacja nie zależy od tego, czy metryki wzrosną, czy spadną.

## 6. Czujnik 5 cm

Zgodnie z Planem v7 A4: 5 cm **poza walidacją klimatologiczną** (wymiana czujnika w 2019 r., skok poziomu, QC-2),
zostaje tylko anomalia 35-dniowa w obrębie każdego segmentu czujnika. Na dashboardzie wiersz „0–7 cm vs czujnik 5 cm”
pokaże anomalię 35-dniową zamiast klimatologicznej. Możliwy dryf czujnika ML2x od końca 2022 r. (QC-3) zostaje
opisany jako ograniczenie; nie korygujemy go.

## 7. Skutki dla dalszych kroków

- **A5:** Brier, diagram niezawodności i trafność alarmu liczymy już na referencji po A4 (W1, z W2 i W3 obok).
- **ρ w prawdopodobieństwie suszy** (`PSMA_RHO` = 0,58) pochodzi z walidacji na referencji z artefaktami. Po A4 trzeba
  ją oszacować ponownie, na latach innych niż te, na których liczymy Brier (inaczej Brier byłby zawyżony); szczegóły w A5.
- **Audyt w `docs/MIGRACJA_PODSUMOWANIE.md` §5.1:** po A4 przy liczbach gleby i roślinności trzeba dopisać „przeliczone
  na referencji po QC A4” albo nowe wartości.

## 8. Ograniczenia

- Próg θ_dno oznacza tylko oczywiste artefakty. Odczyty tuż przed utratą kontaktu (np. 0,10–0,20) mogą być już zaniżone;
  tego nie wykryjemy bez drugiego czujnika na tej głębokości. Wrażliwość na próg 0,136 i 0,15 pokazuje skalę problemu.
- Cenzurowanie zakłada, że utrata kontaktu oznacza suchą glebę. To uzasadnione fizycznie (szczeliny powstają przy
  wysychaniu), ale tuż po deszczu szczeliny mogą być jeszcze otwarte przy wilgotniejszej glebie.
- Problem dotyczy jednej stacji. Czy inne stacje SMOSMANIA mają podobne artefakty, sprawdzi etap B Planu v7
  (po module 1).
- Przed napisaniem tej notatki oglądaliśmy rozkłady danych referencyjnych (sekcja 1), ale nie metryki produktu.
  Progi wynikają z fizyki gleby i z czujnika 10 cm, nie z wyników walidacji.

## 9. Decyzje do zatwierdzenia

- **D-060:** reguły `LOW_IMPLAUSIBLE` (θ_dno = 0,10 m³/m³) i `FAST_DROP` (> 0,05 m³/m³ w ≤ 6 h) dla 20 i 30 cm;
  wrażliwość: θ_dno = 0,5·WP i 0,15.
- **D-061:** wariant główny W1 (cenzurowanie), W2 i W3 raportowane obok; do metryk ciągłych dochodzi ρ Spearmana.
- **D-062:** 5 cm tylko z anomalią 35-dniową w obrębie segmentu; bez walidacji klimatologicznej.
- **D-063:** sekcje 3–4 tej notatki hashujemy (SHA-256) przed wdrożeniem i przed policzeniem metryk; hash zapisujemy
  w Planie v8 przy kroku A4.

## 10. Źródła

Poziom dostępu: P = pełny tekst, A = abstrakt lub streszczenie, F = fragment z wyszukiwania, W = wiedza własna (do sprawdzenia w pełnym tekście).

- Dorigo W. i in. 2013. Global automated quality control of in situ soil moisture data from the International Soil
  Moisture Network. Vadose Zone Journal 12(3), doi:10.2136/vzj2012.0097. Definicje flag C01–C03, D01–D10 z dokumentacji
  implementacji referencyjnej `flagit` (TU Wien): https://github.com/TUW-GEO/flagit [P dla definicji flag, W dla artykułu].
- Foley J.L., Harris E. 2007. Field calibration of ThetaProbe (ML2x) and ECHO probe (EC-20) soil water sensors in a Black
  Vertosol. Australian Journal of Soil Research 45(3): 233–236, https://publish.csiro.au/SR/SR06156 [A].
- Hokett S.L. i in. 1992. Laboratoryjna ocena TDR przy szczelinie z powietrzem między prętami (zaniżenie do 46%
  w wilgotniejszej glebie, mały efekt w suchej) [F — pełny opis bibliograficzny do uzupełnienia].
- Saxton K.E., Rawls W.J. 2006. Soil water characteristic estimates by texture and organic matter for hydrologic
  solutions. Soil Science Society of America Journal 70: 1569–1578, doi:10.2136/sssaj2005.0117 [W — współczynniki
  równania 1 z pamięci; wynik 0,27 m³/m³ zgodny z typową wartością dla iłu pylastego].
- Gruber A. i in. 2020. Validation practices for satellite soil moisture retrievals: What are (the) errors?
  Remote Sensing of Environment 244: 111806, doi:10.1016/j.rse.2020.111806 [F].
- Calvet J.-C. i in. 2016. Deriving pedotransfer functions for soil quartz fraction in southern France from reverse
  modeling. SOIL 2: 615–629 (właściwości gleb 21 stacji SMOSMANIA) [F].
- `docs/evidence/Condom_QC.md` (analiza z 2026-09-26, QC-1 … QC-6).
