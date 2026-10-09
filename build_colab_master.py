"""
Generator notatnika notebooks/AgriWatch_Monitor.ipynb (monitoring jednej winnicy).
Poprzednia wersja (notatnik AgriScreen v2.5): legacy/build_colab_master_v1.py.
"""
import json
import os

CELLS = [
    ("md", """# AgriWatch Monitor — anomalie suszy dla winnicy (Condom, Gers)
Otwieraj z GitHub (Plik → Otwórz → GitHub). Środowisko z **GPU** (dla SEN2SR). Potem `Uruchom wszystko`.

Łańcuch: Sentinel-2 (rastry, jak w v1) → SEN2SR 2,5 m z kontrolą → indeksy winnicy → anomalie (ERA5-Land SMA, SPI, NDVI)
→ status dekadowy wg logiki EDO CDI → walidacja na ISMN Condom → biuletyn i **dashboard winnicy**.
Wyniki: `MyDrive/GeoWorldLook/agriwatch/data/05_Final_Outputs/agriwatch/` i tabele `data/registry/gwl_*.csv`."""),
    ("md", "## 1. Dysk Google i kod z GitHub"),
    ("code", """import os, sys
try:
    from google.colab import drive
    drive.mount('/content/drive')
    IN_COLAB = True
except Exception:
    IN_COLAB = False

REPO_URL = 'https://github.com/geoworldlook/1_geoworldlook-agriscreen.git'
PROJECT_DIR = '/content/drive/MyDrive/GeoWorldLook/agriwatch'
if IN_COLAB:
    if not os.path.exists(os.path.join(PROJECT_DIR, '.git')):
        os.makedirs(os.path.dirname(PROJECT_DIR), exist_ok=True)
        !git clone {REPO_URL} "{PROJECT_DIR}"
    # Lokalne zmiany w kodzie (np. zapisany notatnik) blokowały `pull --ff-only` i kod zostawał stary:
    # odkładamy je do stash (do odzyskania: git stash list / git stash pop), potem pull.
    !git -C "{PROJECT_DIR}" stash push -q -m "colab-autostash" || true
    !git -C "{PROJECT_DIR}" pull --ff-only
    !git -C "{PROJECT_DIR}" log -1 --format="Kod: %h %ci %s"
    if os.popen(f'git -C "{PROJECT_DIR}" rev-parse HEAD').read() != os.popen(f'git -C "{PROJECT_DIR}" rev-parse origin/main').read():
        print('[UWAGA] Kod na Dysku różni się od origin/main — wyniki będą z innej wersji kodu.')
else:
    PROJECT_DIR = os.path.abspath('..') if os.path.basename(os.getcwd()) == 'notebooks' else os.path.abspath('.')
os.chdir(PROJECT_DIR)
if PROJECT_DIR not in sys.path:
    sys.path.insert(0, PROJECT_DIR)
import importlib
sys.modules.setdefault('imp', importlib)
try:
    %load_ext autoreload
    %autoreload 2
except Exception as e:
    print(f'[INFO] autoreload pominięty ({e})')
print('Projekt:', PROJECT_DIR)"""),
    ("md", "## 2. Środowisko: pakiety, GEE, rejestr, konfiguracja"),
    ("code", """from step_05_colab_run import (setup_runtime, monitor_config, run_task, run_history, registry_summary,
                               task_ingest_s2, task_ingest_era5, task_scene_stats, task_anomalies,
                               task_validate, task_weather, task_bulletin, task_dashboard, task_summary)
from step_06_dashboard import show_dashboard
rt = setup_runtime(PROJECT_DIR, gee_project='ee-geoworldlook', pull=False)
cfg = monitor_config(rt)   # zmiany: monitor_config(rt, {'VINEYARDS': {'VINEYARD_06': 6, 'VINEYARD_07': 7}})"""),
    ("md", "## 3. Dane: rastry Sentinel-2 (przyrostowo) i ERA5-Land 1991 → dziś"),
    ("code", """run_task(rt, 'ingest_s2', task_ingest_s2, rt, cfg)
run_task(rt, 'ingest_era5', task_ingest_era5, rt, cfg)"""),
    ("md", "## 4. Indeksy winnicy i stacji: 10 m oraz SEN2SR 2,5 m (kontrola H-SR0/H-SR1, bez zastępstwa interpolacją)"),
    ("code", "run_task(rt, 'scene_stats', task_scene_stats, rt, cfg)"),
    ("md", """## 5. Anomalie, status, walidacja, przymrozki i upały, biuletyn
`weather`: dane dobowe Météo-France (Gers, Lot-et-Garonne) i ERA5-Land w punktach najbliższych stacji — walidacja
Tmin, Tmax, opadu i SPI oraz kalibracja progów przymrozku i upału. Pierwsze uruchomienie pobiera ERA5 dla stacji
(kilka minut), kolejne korzystają z cache."""),
    ("code", """run_task(rt, 'anomalies', task_anomalies, rt, cfg)
run_task(rt, 'validate', task_validate, rt, cfg)
run_task(rt, 'weather', task_weather, rt, cfg)
run_task(rt, 'bulletin', task_bulletin, rt, cfg)"""),
    ("md", """## 6. Dashboard winnicy
Mapa NDVI na zdjęciu satelitarnym (wybór daty), status, ryzyko suszy, przyczyny, pogoda i prognoza, wiarygodność.
Plik: `data/05_Final_Outputs/agriwatch/dashboard.html` (można otworzyć w przeglądarce z Dysku)."""),
    ("code", """run_task(rt, 'dashboard', task_dashboard, rt, cfg)
p = os.path.join(cfg['OUTPUT_DIR'], 'dashboard.html')
if os.path.exists(p):
    show_dashboard(p)
else:
    print('Dashboard nie powstał — sprawdź komunikat zadania powyżej.')"""),
    ("md", """## 7. Raport z uruchomienia (do analizy)
`run_summary.md` — wersje, konfiguracja, pokrycie danych, kontrola SR, status per rok, walidacja, błędy.
**Po każdym większym uruchomieniu prześlij ten plik** (albo wklej jego treść) — na nim opieramy wnioski."""),
    ("code", """run_task(rt, 'summary', task_summary, rt, cfg)
print(open(os.path.join(cfg['OUTPUT_DIR'], 'run_summary.md'), encoding='utf-8').read())"""),
    ("md", "## 8. Rejestr i historia uruchomień"),
    ("code", """display(registry_summary(rt))
display(run_history(rt, n=10))"""),
]


def create_monitor_notebook(path="notebooks/AgriWatch_Monitor.ipynb"):
    nb = {"cells": [], "nbformat": 4, "nbformat_minor": 0,
          "metadata": {"colab": {"name": "AgriWatch_Monitor.ipynb", "provenance": []}, "accelerator": "GPU",
                       "language_info": {"name": "python"}}}
    for kind, text in CELLS:
        src = [line + "\n" for line in text.strip().split("\n")]
        if kind == "md":
            nb["cells"].append({"cell_type": "markdown", "metadata": {}, "source": src})
        else:
            nb["cells"].append({"cell_type": "code", "execution_count": None, "metadata": {}, "outputs": [],
                                "source": src})
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(nb, f, indent=2, ensure_ascii=False)
    print(f"Wygenerowano: {path}")


if __name__ == "__main__":
    create_monitor_notebook()
