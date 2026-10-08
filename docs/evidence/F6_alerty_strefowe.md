# F6 — alerty strefowe dla winnic i sadów (przegląd literatury + projekt MVP)

Data: 2026-10-08. Produkt: monitorujemy działkę klienta (FR, IT, CH, DE, PL); gdy w części działki dzieje się coś nietypowego,
wysyłamy e-mail/WhatsApp: „strefa X, około daty D — sprawdź”, z mapą, wykresem i kontekstem pogody. **Bez porad agronomicznych i bez diagnozy.**

Źródła: 3 przeglądy (wskaźniki optyczne i metody wykrywania stref; radar Sentinel-1; pogoda, dane krajowe i komunikacja).
Proxy blokowało strony wydawców, więc prawie wszystko pochodzi z abstraktów lub fragmentów wyszukiwarki — oznaczenia:
[P] pełny tekst, [A] abstrakt, [F] fragment, [W] wiedza własna niezweryfikowana. Pełne listy źródeł: §8.

## 1. Co satelita realnie widzi na działce 1–5 ha

- Rzędy co 2–3 m: piksel 10 m to ~4 rzędy, 20 m ~8. Piksel zawsze miesza winorośl z międzyrzędziem; przy zadarnionym międzyrzędziu
  trawa w dużej mierze steruje sygnałem (Khaliq 2019 [F]; nasze Plan v7). Zgodność S-2 z dronem jest dobra tylko bez trawy,
  po odcięciu brzegów i dla bloków ≥ 0,5 ha (Sozzi 2020 [F]).
- NDVI piksela mierzy **ilość liści** (Vélez 2020 [F]); geometria rzędów i orbit zmienia odbicie o > 10% (CESBIO [F]; nasze ustalenie o orbitach).
- **Wniosek:** S-2 wykrywa zmiany ilości lub barwy okrywy na płatach ≥ ~300–1000 m² przy szkodzie umiarkowanej lub silnej,
  na najbliższym bezchmurnym zdjęciu — nie przed objawami. Pojedyncze krzewy, niskie nasilenie chorób i wczesny stres wodny są poniżej szumu.

## 2. Wskaźniki: co wykrywają

| Grupa | Wskaźniki (rozdzielczość) | Reaguje na | Dowody dla winnic/sadów |
|---|---|---|---|
| Struktura | NDVI (10 m), fCover/LAI (SL2P) | ilość zielonej okrywy, w tym trawy | utrata okrywy: przymrozek, grad, silny upał, wypady; SL2P zaniża LAI w rzędach [F] |
| Chlorofil / red-edge | NDRE, CIre, MTCI, MCARI/OSAVI (20 m) | chlorofil łanu = LAI × chlorofil liścia | przymrozek w winnicach: spadek NIR/B7 ~17%, odbudowa ~40 dni (Cogato 2020 [F]) |
| Woda | NDMI, MSI, CRSWIR (20 m) | woda w łanie, nadal zdominowana przez LAI | w winnicach nie lepsze od NDVI (Plan v7); obiecujące dla gęstych koron sadów [W] |
| Barwniki / starzenie | PSRI, ARI (20 m) | żółknięcie, czerwienienie | choroby (FD, esca) rozróżnialne dopiero z drona/hiperspektralnie [F]; jesienią dominuje naturalne starzenie |

Problemy: **choroby winorośli** (FD, esca, mączniak) — brak badania S-2, które je wykrywa; z PlanetScope/SkySat mączniak dopiero > 10% nasilenia [F].
**Upał** — widoczne tylko silne uszkodzenia; czułość 40–62% (Pantaleoni Reluy 2022 [P]). **Grad** — brak badań S-2 w winnicach;
w innych uprawach spadek NDVI > 0,05 i |r| 0,8–0,9 z polem pod krzywą [F]. **Sady** — najlepszy przykład: Xylella w oliwkach
(szereg S-2 + model 3D, > 3000 drzew; Hornero 2020 [F]).

## 3. Radar (Sentinel-1) na małej działce

- Rzeczywista rozdzielczość GRD ~20×22 m, ENL 4,4 → ~22 niezależne komórki na ha. Szum średniej strefy ~0,7 dB dla 1 ha po odcięciu brzegu,
  ~0,33 dB dla 3 ha; zmiany po gradzie w literaturze to ~1–1,7 dB (Bell 2020 [A]). Para dat na strefie ≤ 1 ha jest na poziomie szumu.
- Większy szum niż speckle: deszcz, rosa, zamarznięta gleba (1–3 dB [W]); w winnicach VV widzi głównie glebę (Oltrepò [F]).
  Na naszej stacji S-1 vs 5 cm: R ≈ 0,37 (per orbita 0,34–0,45, najlepiej przy 32°).
- Co radar widzi realnie: **uprawę/koszenie międzyrzędzi** (koherencja: uprawa 100%, koszenie 54% na polach i łąkach [F]),
  **stojącą wodę** utrzymującą się ≥ 2 przeloty, **duże uszkodzenia konstrukcji** (karczowanie, przewrócone podpory; CUSUM, ≥ 0,4 ha [A]).
  Raczej nie widzi: gradu na liściach, przymrozku, zbioru.
- Rzędy prostopadłe do wiązki dają silny odbiór, zmienny w sezonie → nigdy nie mieszać orbit; odniesienie per strefa, orbita i pora roku.
- „Syntetyczne NDVI z radaru” (regresja/sieci) działa na dużych polach upraw jednorocznych; w winnicach korelacja radar–optyka r ≤ 0,24 [F]
  i modele ciągną do typowej trajektorii → **nigdy nie alarmować z syntetycznego NDVI**.
- Satelity: S-1A zakończył misję 30.06.2026, S-1C/D dają 6-dniowy cykl na orbitę [F]; NISAR (pasmo L) publiczne od 07.2026 [F];
  ROSE-L planowany na 2028 [F]. Nie budujemy produktu wokół przyszłych misji.

## 4. Metody wykrywania stref

- **Normalizacja do działki:** wartość piksela minus mediana działki z tego dnia (ESA openEO „variability map” [F]).
  Usuwa atmosferę, fenologię, koszenie całej działki i większość efektu orbity; usuwa też suszę całej działki — dla produktu strefowego to zaleta.
- **Model bazowy piksela z lat wcześniejszych:** FORDEAD (harmoniczne, próg, licznik potwierdzeń +1/−1, potwierdzenie przy 3) [P];
  EWMACD w GEE (`ee.Algorithms.TemporalSegmentation.Ewmacd`) [F]; BFAST, CCDC [W]. Przy trendzie międzyrzędzia lepiej modelować resztę względem działki [W].
- **Strefy:** komponenty spójne z minimalną powierzchnią, histereza progów; Getis-Ord Gi* tylko na natywnych 10 m
  (piksele SR 2,5 m są silnie skorelowane i zawyżają istotność) [W].
- **Wiele wskaźników naraz:** Isolation Forest / Mahalanobis dopiero przy etykietach z informacji zwrotnej [F/W].
- **Chmury:** Cloud Score+ `cs_cdf` ≥ 0,60 + klasy SCL [F].
- **Usługi komercyjne:** Farmers Edge (porównanie z obrazami do 14 dni, e-mail, czułość „agresywna/zachowawcza”), EOSDA („nietypowa zmiana NDVI”),
  OneSoil (powiadomienie o nowym zdjęciu, nie o anomalii), Œnoview (fCover winorośli z modelu rzędów; 50–80 €/ha), Spin.Works (S-2 + dron) [F].
  Użytkownicy cenią: wskazanie konkretnego miejsca zamiast chodzenia po całym polu i regulowaną czułość [F].
  Opublikowanej walidacji precyzji alertów względem informacji zwrotnej rolników nie znaleziono.

## 5. Pogoda jako kontekst (nie diagnoza)

Okno: od ostatniego bezchmurnego zdjęcia przed anomalią do pierwszego po (±1 dzień). Najwyżej 2 linie kontekstu, priorytet:
grad > przymrozek > ulewa > upał > wiatr > susza. Zawsze z poziomem pewności (siatka / stacja / radar); nigdy „spowodowane przez”.

| Flaga | Reguła (wstępna, do kalibracji) | Etykieta |
|---|---|---|
| Przymrozek | Tmin ≤ 0 °C w oknie wrażliwości (winorośl: od pękania pąków wg modelu BRIN lub sumy temperatur do zawiązania owoców; jabłoń: od zielonego pąka do zawiązania); stopnie ≤ 0 / ≤ −2 / ≤ −3,5 °C; dopisek o zagłębieniu terenu z DEM | „estymacja z siatki, lokalnie może być zimniej” — ERA5-Land nie widzi zastoisk zimnego powietrza (różnice do 2,5 °C w jednej winnicy [F]) |
| Grad | CH: MeteoSwiss POH ≥ 80% lub MESHS ≥ 2 cm w promieniu 2 km; inne kraje: intensywna komórka burzowa w radarze opadowym + CAPE z ERA5 → „silna burza w pobliżu” (nigdy „grad” bez produktu gradowego) | radar / burza prawdopodobna |
| Ulewa | doba ≥ lokalny 99. percentyl lub ≥ 40 mm [W] | siatka / radar |
| Upał | Tmax ≥ 35 °C (winorośl), ≥ 32 °C (jabłoń, oparzenia owoców) [F/W] | siatka |
| Susza | obecna reguła EDO (SPI, anomalia wilgotności) | „dotyczy całej okolicy” |
| Warunki infekcyjne (tylko na życzenie) | ≥ 2 mm deszczu i Tmean ≥ 11 °C po pękaniu pąków → „warunki często wymieniane przy infekcjach grzybowych; zobacz biuletyn regionalny (BSV / Agrometeo / VitiMeteo)” [F] | sam kontekst |

Dane krajowe (licencje wg fragmentów, do potwierdzenia przed użyciem komercyjnym):
- wszędzie: ERA5-Land (klimatologia, anomalie); prognozy: **ECMWF open data (CC BY 4.0 od 10.2025)** albo płatny plan Open-Meteo;
- FR: Météo-France, dane otwarte od 01.2024 (Licence Ouverte/Etalab 2.0), stacje + radar;
- CH: MeteoSwiss, dane otwarte od 05.2025, produkty gradowe POH/MESHS (archiwizować codziennie — okno 14 dni);
- DE: DWD (opendata.dwd.de), stacje + RADOLAN;
- IT: regionalne ARPA (np. ARPAE CC BY 4.0) + radar DPC (CC BY-SA — wymóg udostępniania na tych samych warunkach);
- PL: IMGW-PIB (danepubliczne.imgw.pl).
- **Nie używać bazy ESWD w produkcie** bez licencji komercyjnej [F].

**Uwaga dla repozytorium:** `step_06_dashboard.py` pobiera prognozę z darmowego API Open-Meteo, które jest **tylko do użytku niekomercyjnego**
(dane CC BY 4.0 wymagają atrybucji) [F]. W płatnym produkcie: plan komercyjny Open-Meteo albo ECMWF open data.

## 6. Komunikacja

- Dowody: doradztwo przez telefon/SMS zwiększa wiedzę i stosowanie praktyk (metaanaliza Fabregas i in. 2019, *Science* [F]), ale zbyt częste
  wiadomości zwiększają rezygnacje; wybór częstotliwości przez rolnika zwiększa uwagę; prośba o ocenę obniżyła rezygnacje o 20% (PxD, Kenia) [F].
  Fałszywe alarmy obniżają zaufanie; pomaga przejrzystość niepewności i rozliczanie trafień/pudłowań [F].
- **WhatsApp Business:** wymagana zgoda (opt-in) z nazwą firmy; od 07.2025 płatność za wiadomość szablonową; wiadomości „utility” w oknie 24 h
  po odpowiedzi klienta są bezpłatne; orientacyjnie ~0,03 (FR, IT) – 0,06 (DE) za wiadomość [F, źródła pośrednie].
  Treść czysto informacyjna, bez promocji [W].
- **RODO:** alerty dla abonenta na podstawie umowy (art. 6 ust. 1 lit. b); marketing osobna zgoda; informacja o przetwarzaniu wskazująca kanał [F].
  We Francji obowiązuje rozdział doradztwa fitosanitarnego od sprzedaży — kontekst infekcyjny nigdy nie może sugerować zabiegu [W].
- **Rynek:** stacje meteo (Sencrop ~350 € + ~399 €/rok, Weenat, Pessl), bezpłatne serwisy chorobowe (VitiMeteo/Agrometeo), eDWIN w Polsce,
  płatne serwisy regionalne (vite.net we Włoszech) [F]. Żaden nie mówi **gdzie w działce** coś się zmieniło — to nasza luka.
  Sprzedaż przez spółdzielnie, doradców i ubezpieczycieli; cena poniżej abonamentu stacji (hipoteza 100–300 € na gospodarstwo rocznie [W]).

## 7. Rekomendowany projekt MVP

**Dane i wstępne przetwarzanie**
1. S-2 L2A, klasy SCL + Cloud Score+ `cs_cdf` ≥ 0,60; scena tylko gdy ≥ 80% wnętrza działki jest czyste; bufor wewnętrzny 10 m;
   maska pikseli trwale niskiego NDVI w lipcu (luki, młode nasadzenia).
2. Wskaźniki alarmowe: **NDVI 10 m** (główny), **NDRE 20 m** (chlorofil), **NDMI 20 m** (woda; ważniejszy w sadach).
   PSRI i CIre tylko zapisywane, dopóki informacja zwrotna nie pokaże ich wartości. **SR 2,5 m tylko do mapy i obrysu strefy.**

**Statystyka anomalii (podwójna różnica, przyczynowo)**
3. `r(p,t) = x(p,t) − mediana_działki(t)`; baza `b(p)` = mediana `r` tego piksela z **lat wcześniejszych** (≥ 3), ±15 dni, **ta sama orbita**
   (przy braku danych: wspólna baza + poprawka orbity); `z = (r − b) / max(1,4826·MAD_p, próg szumu)`.
   Progi z empirycznych kwantyli z odtworzenia sezonów 2018–2025, nie z rozkładu normalnego.
4. Piksel kandydujący: NDVI w 1% dolnym ogonie **albo** ≥ 2 z 3 wskaźników w 5% ogonie „złego” kierunku
   (ogony dobrane tak, by każdy wskaźnik dawał tę samą częstość fałszywych alarmów).

**Strefy i potwierdzenie**
5. Histereza na siatce 10 m (zarodki w 1% ogonie, rozrost do 10%), łączność 8-sąsiedztwa; strefa ≥ 400 m² i ≥ 3% działki;
   kształty prostokątne, wzdłuż rzędów lub przy brzegu → oznaczenie „możliwe prace polowe”.
6. Licznik w stylu FORDEAD (+1 / −1 / bez zmian pod chmurą); potwierdzenie: 2 obserwacje w ≤ 20 dni, w tym **z innej orbity**.
   Szybka ścieżka: jedno zdjęcie wystarczy, gdy z ≤ −4, strefa ≥ 0,1 ha i pogoda/radar wskazuje grad lub przymrozek.
7. Radar: cechy VV, VH, VH−VV (γ0, korekcja terenu), tylko ta sama orbita; strefy radarowe ≥ 1 ha po buforze 20 m
   (działki < 2 ha: radar tylko dla całej działki). Alarm S-2 + zgodny radar w ±12 dni → „widziane przez dwa niezależne czujniki”.
   Sam radar tylko przy przerwie S-2 ≥ 10 dni w sezonie i z dodatkowym wyzwalaczem (burza, przymrozek, ulewa) lub ≥ 2 przeloty;
   oznaczony „wstępny”, zamykany automatycznie przy następnym czystym zdjęciu S-2. Brak sygnału radaru nie osłabia alarmu S-2.

**Wysyłka**
8. Push tylko od ~3 tygodni po pękaniu pąków do zbioru; poza tym wyniki tylko na dashboardzie (prace w międzyrzędziach dominują).
   Poziomy: „info” (dashboard), „sprawdź przy okazji” (potwierdzone), „sprawdź wkrótce” (≥ 3 daty, rośnie, kilka wskaźników, ≥ 0,1 ha).
9. Limity: najwyżej 1 alert na działkę na 7–14 dni i 2 na użytkownika na tydzień (reszta w tygodniowym zestawieniu);
   ponowny alert dla tej samej strefy tylko przy wzroście ≥ 50% lub nowym zdarzeniu; cisza 21:00–07:00; tryb do wyboru: od razu / tygodniowo / wyłączone.
10. Treść: nazwa działki, obrys strefy na obrazie 2,5 m, powierzchnia, link nawigacyjny do środka strefy, zdanie opisowe
    („zieleń w tej części jest niższa niż w reszcie działki i niż w poprzednich latach”), daty, poziom pewności, liczba czystych zdjęć,
    wykres strefa vs reszta działki z pasmem lat poprzednich, 1–2 linie kontekstu pogody, neutralna uwaga o możliwych przyczynach
    (prace polowe, pogoda, zdrowie roślin, wypady) i stopka „automatyczna obserwacja, nie porada ani diagnoza; dane: Copernicus, [służba krajowa]”.
11. Przyciski odpowiedzi: **Znalazłem problem / Znane prace / Nic nie widać / Nie sprawdzałem** (+ opcjonalnie zdjęcie);
    jedno przypomnienie po 5 dniach; ankieta na koniec sezonu; publiczne podsumowanie trafień i pudłowań.

**Walidacja**
12. Precyzja per poziom alertu z przedziałem Wilsona, osobno odsetek „prawdziwa zmiana, ale nieprzydatna” (znane prace).
    Czułość (której informacja zwrotna nie da): ~10% wiadomości prosi też o sprawdzenie losowej niezaalarmowanej strefy;
    syntetyczne wstrzykiwanie spadków NDVI w archiwalne obrazy (minimalna wykrywalna anomalia); znane zdarzenia (grad, przymrozek, Gers 2022).
    Cel: ≥ 50% „znalazłem problem” wśród odpowiedzi; poniżej — podnieść progi.

**Pierwszy krok:** odtworzenie wsteczne na VINEYARD_06 (2016–2026), bez wysyłki: liczba alertów na sezon, wygląd stref, zgodność ze znanymi zdarzeniami.

## 8. Źródła (wybór; poziom dostępu w nawiasie)

Optyka i metody: Sozzi i in. 2020 [F]; Khaliq i in. 2019 RS 11:436 [F]; Vélez i in. 2020 [F]; De Petris i in. 2024 [F]; Abubakar i in. 2023 [F];
CESBIO MultiTemp, efekty orientacji rzędów [F]; Cogato i in. 2020 (przymrozek, S-2) [F]; Pantaleoni Reluy i in. 2022 OENO One 56(1) [P];
Laroche-Pinel i in. 2021 OENO One 55(4) [P]; Albetis i in. 2018 [F]; Bendel i in. 2020 [F]; Cornell (mączniak, PlanetScope) [F];
Hornero i in. 2020 RSE [F]; Clevers i Gitelson 2013 [F]; Meroni i in. 2019 RSE 221:508 [A]; dokumentacja FORDEAD (GitLab) [P];
EWMACD w GEE [F]; Mouret i in. 2021 (Isolation Forest) [F]; ESA APEx variability map [F]; Cloud Score+ (katalog GEE; RS 16:4791) [F];
strony FieldView, Farmers Edge, OneSoil, EOSDA, xarvio, xFarm, Taranis, Œnoview, Spin.Works [F]; Agriland (powiadomienia AMS w Irlandii) [F].

Radar: specyfikacja S-1 IW GRD (ESA) [F]; Bell i in. 2020 J. Appl. Meteor. Climatol. 59 (grad) [A]; Streifeneder i in. EGU23-2551 [F];
Shang i in. 2020 (koherencja, siew/zbiór) [A]; De Vroey i in. 2021/2022 (koszenie) [A]; Ruiz-Ramos i in. 2020 (CUSUM) [A];
Conradsen i in. 2016/2024 (test omnibus) [W/F]; Bergamaschi i in. 2025 (DpRVI, Oltrepò) [F]; Mandal i in. 2020 [F]; ESA STATEO26 ID_226 [F];
Palmisano i in. 2021 (kąt padania) [F]; HAL hal-02879608 (wykrywanie przymarzania z S-1) [F]; Bae i in. 2022 [F];
Filgueiras i in. 2019, Mohite i in. 2020, Tsardanidis i in. 2024, Rosberg i Schmitt 2024, SAR2NDVI 2024 (synteza NDVI z radaru) [A/F];
ESA/CDSE (koniec S-1A, S-1C/D) [F]; ASF (NISAR) [F]; ESA (ROSE-L) [F]; Quegan i Yu 2001, Touzi i in. 1999 [W].

Pogoda i komunikacja: rozporządzenie UE 2023/138 (zbiory danych o wysokiej wartości) [F]; Météo-France, MeteoSwiss, DWD, ARPAE, DPC, IMGW (strony danych otwartych) [F];
ECMWF open data [F]; warunki Open-Meteo [F]; umowa użytkownika ESWD [F]; Battaglioli i in. 2023 NHESS 23:3651 [F];
modele pękania pąków (BRIN; Costafreda-Aumedes i in. 2025) [F]; Rea i Eccel 2006 (kwitnienie jabłoni) [F];
temperatury krytyczne (PSU, MSU, WSU) [F]; oparzenia słoneczne (WSU; Frontiers 2023) [F]; biuletyny BSV (mączniak) [F];
Fabregas, Kremer i Schilbach 2019 *Science* [F]; rejestr eksperymentów PxD [F]; WhatsApp Business (ceny, opt-in) [F]; RODO i WhatsApp [F];
Sencrop, Weenat, Pessl, vite.net, VitiMeteo/Agrometeo, eDWIN [F].
