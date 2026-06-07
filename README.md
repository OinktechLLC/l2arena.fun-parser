# 📡 TVArena-Project

> **Автономный поисковый робот для сбора IPTV m3u8-каналов с [tv.l2arena.fun](https://tv.l2arena.fun)**  
> Плейлист обновляется каждый день через GitHub Actions. Полный автопилот.

---

## 🔥 Что это

**TVArena-Project** — Python-скрипт + CI/CD пайплайн:

- **Каждый день в 06:00 UTC** заходит на `https://tv.l2arena.fun`
- Запускает **headless Chromium через Playwright** — обходит JS-защиту и Cloudflare
- Перехватывает **сетевые запросы** браузера, ловит m3u8 ещё до рендера страницы
- Декодирует ссылки из `playerjs.html?file=https://url1%20or%20https://url2%20or%20...`
- Формирует готовый **`playlist.m3u`** с нормальными названиями каналов
- Автоматически делает `git commit + git push` — плейлист всегда свежий

---

## 📁 Структура проекта

```
TVArena-Project/
├── scraper.py                   # Основной парсер (Playwright + fallback requests)
├── requirements.txt             # Python-зависимости
├── playlist.m3u                 # Плейлист (авто-генерируется)
├── .github/
│   └── workflows/
│       └── update.yml           # GitHub Actions: cron 06:00 UTC + автокоммит
└── README.md
```

---

## 🚀 Быстрый старт

### 1. Форк / клон

```bash
git clone https://github.com/ВАШ_НИК/TVArena-Project.git
cd TVArena-Project
```

### 2. Установка зависимостей

```bash
pip install -r requirements.txt
playwright install chromium
```

### 3. Запуск вручную

```bash
python scraper.py
```

После выполнения появится / обновится `playlist.m3u`.

---

## 🤖 Автообновление через GitHub Actions

После пуша в репозиторий Actions запускается **сам каждый день**.

### ❗ Обязательно включи права на запись

```
Settings → Actions → General → Workflow permissions
→ [✅] Read and write permissions
→ Save
```

### Ручной запуск (когда хочешь)

```
GitHub → Actions → "TVArena — Обновление плейлиста" → Run workflow → Run workflow
```

---

## 📺 Подключение плейлиста в IPTV-плеер

После первого прогона плейлист доступен по прямой raw-ссылке:

```
https://raw.githubusercontent.com/ВАШ_НИК/TVArena-Project/main/playlist.m3u
```

| Плеер | Платформа | Как добавить |
|---|---|---|
| **TiviMate** | Android TV | Playlist → Add playlist → URL |
| **GSE Smart IPTV** | iOS / Android | Remote playlists → Add URL |
| **OTT Navigator** | Android | Playlist → Network |
| **VLC** | Любая | Медиа → Открыть URL сети |
| **Kodi + PVR IPTV** | Любая | M3U плейлист URL |
| **Jellyfin / Emby** | Любая | M3U URL в Live TV |

---

## ⚙️ Как работает парсер

```
https://tv.l2arena.fun
        │
        ├─ Playwright (headless Chromium)
        │      ├─ Перехват сети: ловит m3u8 до рендера
        │      ├─ JS-рендеринг: ждём networkidle
        │      └─ Анализ HTML после рендера
        │
        ├─ Главная страница
        │      ├─ Прямые .m3u8 в HTML
        │      ├─ m3u8 в <script> тегах
        │      ├─ JS-ключи: source=, hlsUrl=, file=, stream=
        │      └─ ?file=url1%20or%20url2 → decode → split → m3u8
        │
        └─ Все внутренние страницы (глубина 1)
               ├─ playerjs.html?file=... → параметр file=
               ├─ Атрибуты тегов (src, data-src, data-url, ...)
               └─ Inline JS / JSON с m3u8
```

**Стратегии поиска:**
- Перехват XHR/fetch запросов браузером (`page.on("request")`)
- Regex `RE_M3U8` — прямые `.m3u8` URL
- Regex `RE_FILE_PARAM` — декодирование `?file=url1%20or%20url2`
- Regex `RE_STREAM_KEY` — JS-ключи `source:`, `hlsUrl:`, `playlist:` и т.д.
- `BeautifulSoup` — атрибуты тегов
- Fallback на `requests` если Playwright недоступен

---

## 🛠️ Настройка параметров

Все настройки в начале `scraper.py`:

```python
BASE_URL      = "https://tv.l2arena.fun"  # Целевой сайт
PLAYLIST_FILE = "playlist.m3u"            # Имя выходного файла
PAGE_TIMEOUT  = 30_000                    # Таймаут страницы (мс)
WAIT_AFTER    = 3                         # Ожидание JS после загрузки (сек)
NAV_DELAY     = (1.5, 3.0)               # Пауза между страницами (сек)
```

Расписание в `update.yml`:

```yaml
cron: "0 6 * * *"   # Каждый день в 06:00 UTC
```

---

## 📝 Формат плейлиста

```m3u
#EXTM3U x-tvg-url="" tvg-shift=0 cache=500
## TVArena-Project playlist | Обновлено: 2025-06-07 06:00 UTC
## Источник: https://tv.l2arena.fun
## Каналов найдено: 42

#EXTINF:-1 tvg-id="1" tvg-name="RUSSIA 24",RUSSIA 24
https://stream.example.com/live/russia24/index.m3u8

#EXTINF:-1 tvg-id="2" tvg-name="NTV LIVE",NTV LIVE
https://cdn.example.tv/ntv/playlist.m3u8
```

---

## 🔧 Устранение проблем

| Проблема | Решение |
|---|---|
| `playwright: command not found` | `pip install playwright && playwright install chromium` |
| `playlist.m3u` пустой локально | Сайт может требовать VPN или менять структуру |
| Actions не пушит | `Settings → Actions → Workflow permissions → Read and write` |
| Каналы не воспроизводятся | Потоки могут быть временно offline или гео-заблокированы |
| Actions зависает > 30 мин | Увеличь `timeout-minutes` в `update.yml` |

---

## 📄 Лицензия

MIT — используй, форкай, улучшай.

---

*TVArena-Project — автоматически, каждый день, без остановки.*
