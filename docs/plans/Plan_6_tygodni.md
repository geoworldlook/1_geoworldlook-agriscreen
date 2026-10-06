# Plan 6 tygodni — od kodu do pokazywalnego projektu i pierwszych aplikacji

> **Status:** `PROPOSED` (2026-10-01) · **Zasoby:** 1 osoba, ~10 h/tydzień, darmowe narzędzia (VS Code, Colab, GEE, Dysk Google, GitHub)
> **Struktura repozytorium:** bez zmian (`step_01…07`, `data/`, `docs/`, `notebooks/`)
> **2026-10-06:** część projektowa (kolumna „Projekt”) zastąpiona harmonogramem E0–E6 z `Plan_v3_monitoring_winnic_SR.md` (D-023). Kolumna „Kariera” obowiązuje dalej.

## Cel

Do **15 listopada 2026** mieć:
1. działający, uczciwie zwalidowany projekt do pokazania (jedna strona + jeden notatnik + README po angielsku),
2. wysłane pierwsze aplikacje do firm EO we Francji, Włoszech i DACH,
3. jedną ofertę pilotażu lub zlecenia (opcjonalnie).

## Pomysł w jednym zdaniu

**„Soil moisture from Sentinel-1, validated against an in situ station, with super-resolution context — and an honest QC of the reference data.”**

Trzy elementy, które rekruter zrozumie w 2 minuty:
- wykres: wilgotność z Sentinel-1 vs czujnik Condom vs ERA5-Land (2016–2024),
- tabela metryk z 95% CI — wynik dobry albo zły, ale uczciwy,
- obraz Sentinel-2 10 m vs SEN2SR 2,5 m nad winnicami.

## Zasady

- Aktywne moduły: `step_01` (dane), `step_07` (stacja i walidacja), `step_05` (sterowanie), `step_03` (SR, tydzień 4). Reszta czeka.
- Każdy tydzień kończy się **artefaktem** (wykres, raport, commit, aplikacja).
- Nowy pomysł trafia do listy „później”, nie do planu.

## Harmonogram

| Tydzień | Projekt (~7 h) | Kariera (~3 h) | Artefakt |
|---|---|---|---|
| **1** · 1–6 X | `step_05`: `setup_runtime`, `run_task`, `run_history`; notatnik `GWL_Control.ipynb`; rozszerzenia Jupyter i Colab w VS Code; **pierwsze uruchomienie `step_07` na prawdziwych danych** | Lista 20 firm (FR/IT/DACH) z wymaganiami | Raport Condom na prawdziwych danych S-1 |
| **2** · 7–13 X | Poprawki po pierwszym uruchomieniu (GEE, maska chmur); interpretacja wyników; decyzja: co działa, co nie | CV po angielsku (wersja EO / data) | `station_report.md` v1 + wnioski |
| **3** · 14–20 X | Wilgotność strefy korzeniowej (filtr wykładniczy, czujniki 20/30 cm) jako druga warstwa w `step_07`; test na drugiej stacji SMOSMANIA (zmiana konfiguracji) | Profil LinkedIn EN + 3 posty-szkice | Wyniki dla 2 stacji |
| **4** · 21–27 X | `step_03`: naprawa SEN2SR (pobranie modelu, kolejność pasm, test spójności); jedna scena letnia nad winnicami Condom | 3 aplikacje | Porównanie 10 m vs 2,5 m + metryki spójności |
| **5** · 28 X–3 XI | README po angielsku, jeden notatnik demonstracyjny, strona projektu (GeoWorldLook lub GitHub Pages) | 3 aplikacje; 1 post na LinkedIn z wykresem | Publiczny projekt |
| **6** · 4–15 XI | Nagranie 5 min (walkthrough); poprawki; opcjonalnie oferta pilotażu dla 3 doradców winiarskich | 3–4 aplikacje; przygotowanie do rozmów | Wideo + 10 wysłanych aplikacji |

## Ryzyka i obejścia

| Ryzyko | Obejście |
|---|---|
| Błędy GEE przy pierwszym uruchomieniu | Tydzień 2 zarezerwowany na poprawki |
| Wynik S-1 gorszy niż ERA5 | Pokazujemy uczciwie — to też wartościowy wynik dla rekrutera |
| Brak czasu | Tnij tydzień 3 (druga warstwa), nigdy tygodni 1, 2, 5 |
| Repozytorium w firmowym OneDrive | Przenieść do prywatnego folderu przed publikacją (tydzień 5) |

## Lista „później” (nie teraz)

Supabase i strona z bazą danych, automatyzacja GitHub Actions, termika pyDMS, model ML na wielu stacjach, platforma sprzedażowa.
