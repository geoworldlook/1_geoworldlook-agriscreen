# F5 — asymilacja danych i probabilistyczna decyzja o anomalii (przegląd + eksperyment)

Data: 2026-10-08. Uzupełnia `docs/plans/Plan_v7_precyzja.md`.
Źródła: 3 przeglądy literatury (systemy operacyjne; asymilacja na poziomie działki; łączenie wielu źródeł w jedną decyzję),
eksperyment EnKF na danych z Condom (`docs/evidence/F4_eksperymenty/D_asymilacja_EnKF/`) i własna kontrola obliczeń.
Uwaga o dostępie: strony wydawców były blokowane przez proxy, więc **żaden artykuł nie był czytany w pełnym tekście**.
Wszystkie twierdzenia literaturowe opierają się na abstraktach lub fragmentach z wyszukiwarki (oznaczenia w §8).

## 1. Pomysł „prognoza → przelot satelity → korekta → kolejna prognoza” to asymilacja danych

Schemat:
1. Stan A (np. woda w strefie korzeni).
2. Model napędzany pogodą przewiduje: A → A+3 (krok prognozy).
3. Satelita mierzy A+2. Analiza łączy prognozę i pomiar, ważąc je niepewnościami (krok analizy).
4. Z poprawionego stanu liczy się kolejną prognozę. Parametry (np. pojemność wodna gleby TAW) można dołączyć do wektora stanu
   i poprawiać razem ze stanem („rekalibracja”, tzw. rozszerzenie stanu).

Równanie analizy (filtr Kalmana): `x_a = x_f + K·(y − H·x_f)`, `K = σ_f² / (σ_f² + σ_o²)`.
Wszystko zależy od K. Przy prognozie z błędem σ_f = 0,03 m³/m³ i pomiarze z błędem σ_o = 0,06 m³/m³ K = 0,2:
analiza to A+2,8, nie A+2. Słaby pomiar jest słusznie traktowany ostrożnie.
Odmiany: EnKF (zespół prognoz, np. 100 członków), filtr cząsteczkowy (dla silnie nieliniowych zależności),
SEKF (wersja deterministyczna ECMWF/Météo-France), ES-MDA (wsadowe dopasowanie parametrów na całej historii).

## 2. Gdzie to działa operacyjnie i czego można użyć

| System | Metoda / co asymiluje | Rozdzielczość, okres | Dostęp | Dla AgriWatch |
|---|---|---|---|---|
| **SMAP L4** (NASA) | EnKF w modelu Catchment; temperatura jasnościowa SMAP | 9 km, co 3 h, od 2015-03 | **GEE `NASA/SMAP/SPL4SMGP/008`** | do sprawdzenia od razu (etap B); pasma percentyli były w v007, w v008 niepotwierdzone |
| **H SAF H145/H146/H26** (EUMETSAT) | SEKF w H-TESSEL; radar ASCAT | 0,1°, warstwy jak ERA5-Land (7–28, 28–100 cm), 1991–2024 + bieżące | FTP po rejestracji | „ERA5-Land z asymilacją” — prosta podmiana warstwy do testu |
| ERA5 / IFS (ECMWF) | SEKF; temp./wilgotność 2 m (+ ASCAT wg slajdów ECMWF) | 0,25° | CDS | test porównawczy |
| **LDAS-Monde** (Météo-France) | SEKF/EnSRF w ISBA; wilgotność powierzchni + LAI | Francja 8 km / 2,5 km | brak publicznych wyników | wzór metody, nie źródło danych |
| SIM2 (Météo-France) | bez asymilacji; deszcz z sieci stacji SAFRAN | 8 km, dziennie | data.gouv | niezależny deszcz i SWI — trzecie źródło do potrójnej kolokacji |
| GDO/EDO (JRC) | bez asymilacji; ważona średnia anomalii (LISFLOOD, CCI, LST) | 5 km / 0,1° | JRC | punkt odniesienia |
| VIDA (Kalifornia, winnice) | EnKF w bilansie 1-D; S-1 30 m + ET z termiki | 30 m | tylko metoda | najbliższy wzór dla winnicy |

ERA5-Land, którego używamy, **nie ma asymilacji** — to sam model napędzany pogodą.

## 3. Co mówi literatura o zysku

- **Południowo-zachodnia Francja:** asymilacja ASCAT + LAI w ISBA poprawiła korelację anomalii na 8 z 12 stacji SMOSMANIA (Barbu 2014).
  Sama wilgotność S-1+S-2 1 km zmieniła strefę korzeni nieznacznie; wyraźnie dopiero po dodaniu LAI (Rojas-Munoz 2023).
- **Sentinel-1:** poprawia warstwę powierzchniową; wpływ na strefę korzeni „przeważnie neutralny” (Lievens 2017);
  w modelu upraw AquaCrop tylko „niewielka” poprawa (de Roos 2024). C-band widzi 1–3 cm gleby.
- **Strefa korzeni i plon poprawiają się dopiero przy obserwacjach roślin** (LAI, ET z termiki, stres roślin), zwykle z danymi in situ
  (Ines 2013, Er-Raki 2008, Olivera-Guerra 2018).
- **Winnice:** w GRAPEX filtr cząsteczkowy był lepszy od EnKF (Lei 2020); VIDA dała „umiarkowaną” poprawę terminów i nie korygowała obciążeń.
  Nie znaleziono badania EnKF dla niezawodnionej, zadarnionej winnicy w Europie z samymi danymi satelitarnymi.
- **Rekalibracja parametrów:** działa, gdy obserwacja „widzi” to, co parametr kontroluje. TTSW winnicy dało się odzyskać
  z błędem ~30 mm dzięki **obserwacjom wzrostu pędów (ApeX)** + pogodzie + S-2 (Zhang, Pichon, Roux 2025).
  Z samych LAI/ET/SSM odtwarzanie pojemności wodnej gleby w winnicach południowej Francji było „dość słabe” (Alkassem 2022).
- **Wniosek z literatury:** asymilacja daje przede wszystkim skalibrowaną niepewność, prawdopodobieństwa i spójne prognozy;
  wyraźny wzrost korelacji w strefie korzeni jest rzadki.

## 4. Nasz eksperyment: EnKF z Sentinel-1 na stacji Condom

Model 2 warstw (0–10, 10–100 cm), deszcz ERA5-Land, ET0 Hargreavesa, 100 członków zespołu, strojenie tylko na latach 2016–2020,
test 2021–2024. Wynik v1.0 odtworzony dokładnie (R = 0,583). Odniesienie: ISMN 20–30 cm.

| Wariant | R 2016–24 [95% CI] | ΔR vs model bez asymilacji [CI] | ΔR vs ERA5 0–100 [CI] | Brier P(z ≤ −1) |
|---|---|---|---|---|
| ERA5 0–100 cm (v1.0) | 0,583 [0,50; 0,67] | — | — | 0,141 (tak/nie) |
| ERA5 7–28 cm | 0,693 [0,62; 0,75] | — | +0,11 | 0,115 (tak/nie) |
| V0 model bez asymilacji | 0,582 [0,49; 0,66] | — | −0,001 [−0,04; +0,04] | **0,103** |
| V1 + EnKF z S-1 | 0,558 [0,47; 0,64] | −0,024 [−0,09; +0,05] | −0,025 | 0,102 |
| V2 V1 + rekalibracja pojemności polowej | 0,556 [0,46; 0,64] | −0,027 [−0,09; +0,05] | −0,028 | 0,104 |
| V3 asymilacja warstwy 1 ERA5 | 0,564 [0,48; 0,64] | −0,016 [−0,04; +0,01] | −0,019 | 0,142 |
| V4 S-1 SWI → strefa korzeni | 0,598 [0,50; 0,67] | +0,016 [−0,06; +0,10] | +0,015 | 0,140 |

Klimatologia (stała częstość) ma Brier 0,130.

Wnioski:
1. **Asymilacja S-1 w prostym modelu nie poprawia wyniku względem ERA5-Land.** Model bez asymilacji już dorównuje ERA5,
   więc o jakości decyduje wymuszenie (deszcz). Wpływ S-1 waha się między latami od −0,14 do +0,09.
2. Poprawki z przelotów „niosą się” w czasie (autokorelacja 0,84 po 10 dniach), ale nie są trafne.
3. **Rekalibracja nie zbiega w 9 lat:** trzy starty pojemności polowej (0,30 / 0,36 / 0,42) kończą na 0,358 / 0,369 / 0,380.
   Przyczyna: dopasowanie S-1 do klimatologii modelu usuwa informację potrzebną do nauczenia parametru klimatologicznego.
4. **Prawdopodobieństwo zamiast progu poprawia Brier z 0,141 do 0,103** (skill względem klimatologii ~0,21) —
   zysk daje sama forma probabilistyczna, nie satelita.
5. Filtr jest dobrze skalibrowany na powierzchni (znormalizowana wariancja innowacji 0,99 / 0,98), a S-1 ma błąd ~0,04 m³/m³.

## 5. „Wzór”, który łączy wiele danych i odpowiada „anomalia tak/nie”

Istnieje: to twierdzenie Bayesa dla ukrytego stanu wilgotności `x_t`.
Każde źródło jest zaszumioną obserwacją `x_t`; wynik to `p_t = P(x_t ≤ c | wszystkie dane do chwili t)`,
a decyzja „tak” to `p_t ≥ p*`. Filtr Kalmana, EnKF, filtr cząsteczkowy, ukryty model Markowa i skalibrowana regresja logistyczna
to różne sposoby liczenia tej samej wielkości.

**Dlaczego obecna reguła ma FAR ≈ 0,57 (sprawdzone obliczeniem):** jeśli produkt i czujnik korelują z r = 0,58,
każda reguła „produkt z ≤ −1 ⇒ susza” daje oczekiwany FAR 0,56. Przy z = −1 prawdziwe zdarzenie ma tylko ~30% szans;
50% osiąga się dopiero przy z ≈ −1,7. Zmierzony FAR 0,57 to więc **granica wynikająca z korelacji, nie błąd progu**.

| r produktu z prawdą | POD | FAR | P(zdarzenie \| z = −1) |
|---|---|---|---|
| 0,58 (ERA5 0–100 cm) | 0,44 | 0,56 | 0,30 |
| 0,70 | 0,53 | 0,47 | 0,34 |
| 0,80 | 0,62 | 0,38 | 0,37 |
| 0,90 | 0,73 | 0,27 | 0,41 |

**Proponowany model PSMA (probabilistyczna anomalia wilgotności) — filtr Kalmana na anomaliach:**

1. Wyniki normalne z rang, przyczynowo (tylko lata wcześniejsze): `z_k,t = Φ⁻¹((r − 0,44)/(n + 0,12))` dla każdego źródła k
   (ERA5-Land, później SMAP L4 / H SAF / S-1 SWI).
2. Model obserwacji: `z_k,t = ρ_k,s · x_t + √(1 − ρ_k,s²) · ε_k,t`, sezon s (XI–III, IV–X).
3. Dynamika: `x_t = φ_s · x_{t−1} + √(1 − φ_s²) · η_t`.
4. Prognoza: `m⁻ = φ·m_{t−1}`, `P⁻ = φ²·P_{t−1} + 1 − φ²`.
   Aktualizacja dla każdego dostępnego źródła: `K = ρ_k·P⁻ / (ρ_k²·P⁻ + 1 − ρ_k²)`, `m = m⁻ + K·(z_k − ρ_k·m⁻)`, `P = (1 − K·ρ_k)·P⁻`.
   Brak sceny S-1 = brak aktualizacji.
5. Prawdopodobieństwo: `p_t = Φ((c − m_t)/√P_t)`, c = −1 (jak w v1.0) albo c = −0,84 (percentyl < 20%).
6. Parametry ρ z rozszerzonej potrójnej kolokacji na 21 stacjach SMOSMANIA (nie strojone na Condom); φ z autokorelacji.
   Przedział niepewności p z bootstrapu stacja-rok. Na dashboardzie np. „P(anomalia) = 0,62 [0,48–0,74]”.
7. Klasy: ostrzeżenie wchodzi przy p ≥ 0,5 i trwa, dopóki p ≥ 0,35 (probabilistyczny odpowiednik histerezy EDO);
   obserwacja (watch) zostaje na SPI; alarm = ostrzeżenie ∧ przyczynowa anomalia NDVI ≤ −1 (oznaczony jako niezwalidowany skutek).
8. Weryfikacja: Brier i skill względem klimatologii i względem ERA5 tak/nie, diagram niezawodności, AUC, CRPS, POD/FAR/CSI/SEDI przy p*.

Obecna reguła to szczególny przypadek PSMA z jednym źródłem i ρ = 1.

Etap C (ten sam schemat, zamiast kroku 4 zespół 100 przebiegów dwuskładnikowego bilansu wodnego z EnKF):
`p_t = (1/N) Σ_i 1[FTSW_i ≤ 0,4]` oraz „dni do stresu” z 7-dniowej prognozy zespołowej.

## 6. Rekomendacja dla AgriWatch

1. **Teraz (etap A, nowy krok A7): PSMA z samym ERA5-Land.** Zamienia próg z ≤ −1 na prawdopodobieństwo z niepewnością.
   W eksperymencie sama forma probabilistyczna poprawiła Brier 0,141 → 0,103. Parametry z wielu stacji (etap B).
2. **Etap B rozszerzony:** do walidacji wielostanowiskowej dodać SMAP L4 (GEE), H SAF H145/H146 i SIM2 jako członków PSMA.
   Członek wchodzi tylko przy sparowanej poprawie Brier (korekta Holma).
3. **Etap C jako wersja zespołowa:** dwuskładnikowy bilans + EnKF; S-1 osobno dla każdej orbity (geometria rzędów), z dopasowaniem
   sezonowym; TAW dopasowywane raz w roku metodą wsadową (ES-MDA) zamiast dryfu w filtrze; 7-dniowa prognoza zespołowa
   (pogoda z tych samych tygodni lat poprzednich albo ECMWF open data) i „dni do stresu”.
   Przyjmujemy tylko, jeśli na wielu stacjach nie jest gorszy od modelu bez asymilacji.
4. **Etap D:** obserwacje ApeX i δ13C nie tylko do walidacji, ale jako obserwacje asymilowane stanu winorośli —
   tylko one czynią TAW winnicy identyfikowalnym (Zhang, Pichon, Roux 2025).

Czego nie robić: asymilować surowego wstecznego rozpraszania S-1 przez model Water Cloud dla winnicy (wymaga kalibracji w terenie);
instalować LIS lub SURFEX dla jednej winnicy; uczyć sieci/ML na jednej stacji; liczyć na skok POD/FAR — przy r ≈ 0,6–0,65 FAR zostanie ~0,5.

## 7. Uczciwe oczekiwania

Asymilacja ani fuzja nie podniosą korelacji ze stacją powyżej tego, na co pozwala jakość deszczu i pomiaru (ERA5 7–28 cm już daje 0,69).
Wartość profesjonalna to: prawdopodobieństwo zamiast progu, przedział niepewności, prognoza na tydzień, poprawne zachowanie przy braku scen,
jawne parametry i weryfikacja Brier/niezawodności na wielu stacjach. To jest standard produktów SMAP L4, LDAS-Monde i GDO.

## 8. Źródła (poziom dostępu: A = abstrakt z wyników wyszukiwania, F = fragment, W = wiedza własna niezweryfikowana)

Systemy: Reichle i in. 2017 J. Hydrometeorol. 18:2621 [A]; Reichle i in. 2019 JAMES [A]; katalog GEE SPL4SMGP/007 i /008 [F];
Albergel i in. 2017 GMD 10:3889 (LDAS-Monde) [A]; Bonan i in. 2020 HESS 24:325 [A]; Barbu i in. 2014 HESS 18:173 [A];
Albergel i in. 2020 HESS 24:4291 [A]; Fairbairn i in. 2017 HESS 21:2015 [A]; Draper i in. 2011 HESS 15:3829 [A];
Rojas-Munoz i in. 2023 Remote Sens. 15:4329 [A]; de Rosnay i in. 2013 QJRMS 139:1199 [A]; strony produktów H SAF H26/H145/H146 [F];
Muñoz-Sabater i in. 2021 ESSD 13:4349 [F]; Cammalleri i in. 2017 HESS 21:6329 [F]; Chen i in. 2022 Irrig. Sci. 40:779 (VIDA) [A].

Asymilacja na poziomie działki: Lievens i in. 2017 GRL 44:6145 [A]; de Roos i in. 2024 JGR-Biogeosci. 129 [A];
Modanesi i in. 2022 HESS 26:4685 [A]; Ouaadi i in. 2021 Remote Sens. 13:2667 [F]; Laluet i in. 2024 Agric. Water Manag. 293 [F];
Ines i in. 2013 RSE [F]; Nearing i in. 2012 WRR 48 [F]; Zhuo i in. 2019 Remote Sens. 11:1618 [F]; Pan i in. 2019 Sensors 19:3161 [F];
Er-Raki i in. 2008 Agric. Water Manag. 95:309 [F]; Olivera-Guerra i in. 2018 Agric. Water Manag. 208 [F];
Lei i in. 2020 RSE 239:111622 [F]; Zhang, Pichon, Roux i in. 2025 Agric. Water Manag. 318 [F]; Alkassem i in. 2022 Geoderma 425 [F];
Montzka i in. 2011 J. Hydrol. 399 [F]; Moradkhani i in. 2005 Adv. Water Resour. 28 [F]; Reichle i Koster 2004 GRL [F];
De Lannoy i in. 2007 WRR 43 [F]; Faridani i in. 2025 Agric. Water Manag. 315 [F]; Liu i West 2001 [F];
Evensen 2003, Emerick i Reynolds 2013 (ES-MDA), Desroziers i in. 2005, Attema i Ulaby 1978 [W].

Łączenie źródeł i weryfikacja: McColl i in. 2014 GRL 41:6229 [A]; Gruber i in. 2017 IEEE TGRS 55:6780 [A]; Yilmaz i in. 2012 WRR 48 [A];
Hao i AghaKouchak 2013 Adv. Water Resour. 57 [A]; Kao i Govindaraju 2010 J. Hydrol. 380 [A]; Mallya i in. 2013 J. Hydrol. Eng. 18 [A];
Salakpi i in. 2022 NHESS 22:2725 [A]; Chen i in. 2018 Water Resour. Manag. 32 [A]; Blauhut i in. 2016 HESS 20:2779 [A];
Dutra i in. 2014 HESS 18:2669 [A]; Hersbach 2000 Wea. Forecasting 15:559 [F]; Niculescu-Mizil i Caruana 2005 ICML [F];
Xia i in. 2014 (NLDAS blend) [F]; Kumar i in. 2014 J. Hydrometeorol. 15 [A]; West i Harrison 1997, Rabiner 1989, Ferro 2017 [W].

Obliczenie granicy POD/FAR (§5): własne, rozkład dwuwymiarowy normalny, `scipy`.
