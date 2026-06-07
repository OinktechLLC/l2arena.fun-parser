#!/usr/bin/env python3
"""
TVArena-Project — поисковый робот для https://tv.l2arena.fun
Использует Playwright (headless Chromium) для обхода JS-защиты и Cloudflare.
Извлекает m3u8-ссылки, включая спрятанные в ?file=... параметрах playerjs.
"""

import re
import time
import random
import logging
import urllib.parse
from datetime import datetime, timezone
from typing import Optional

# ─── Логирование ──────────────────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
log = logging.getLogger("TVArena")

# ─── Константы ────────────────────────────────────────────────────────────────
BASE_URL      = "https://secure-272717.tatnet.app/tv.l2arena.fun"
PLAYLIST_FILE = "playlist.m3u"
PAGE_TIMEOUT  = 30_000   # мс (Playwright)
WAIT_AFTER    = 3        # сек ожидания после загрузки (JS-рендеринг)
NAV_DELAY     = (1.5, 3.0)  # случайная пауза между переходами

# ─── Регулярки ────────────────────────────────────────────────────────────────
RE_M3U8 = re.compile(
    r'https?://[^\s\'"<>()\[\]{}|\\^`]+\.m3u8(?:[?#][^\s\'"<>()\[\]{}|\\^`]*)?',
    re.IGNORECASE,
)
RE_FILE_PARAM = re.compile(r'[?&]file=([^&\s\'"<>]+)', re.IGNORECASE)
RE_STREAM_KEY = re.compile(
    r'(?:source|stream|src|hls(?:Url)?|url|file|playlist|manifest)\s*[=:]\s*["\']'
    r'(https?://[^"\']+\.m3u8[^"\']*)["\']',
    re.IGNORECASE,
)


# ─── Извлечение URL ───────────────────────────────────────────────────────────

def find_m3u8(text: str) -> list[str]:
    found = set()
    found.update(RE_M3U8.findall(text))
    found.update(RE_STREAM_KEY.findall(text))
    for raw in RE_FILE_PARAM.findall(text):
        decoded = urllib.parse.unquote_plus(raw)
        for part in re.split(r'\s+or\s+|\s+', decoded):
            part = part.strip()
            if re.match(r'https?://', part, re.I) and '.m3u8' in part.lower():
                found.add(part)
    return list(found)


def clean_url(url: str) -> str:
    return url.strip().rstrip('\\').split(' ')[0]


# ─── Именование ───────────────────────────────────────────────────────────────

def guess_name(url: str, page_text: str, index: int) -> str:
    # Из пути URL
    try:
        path = urllib.parse.urlparse(url).path
        skip = {'play','tve','hls','live','stream','index','ch','tv','bpk-tv','playlist','chunks'}
        segments = [s for s in path.split('/') if s and s.lower() not in skip]
        for seg in reversed(segments):
            seg = re.sub(r'\.m3u8.*$', '', seg, flags=re.I)
            seg = re.sub(r'[_\-]+', ' ', seg).strip()
            if len(seg) >= 2 and not seg.isdigit():
                return seg.upper()
        host = urllib.parse.urlparse(url).hostname or ''
        host = re.sub(r'^www\.', '', host).split('.')[0]
        if host and len(host) >= 2:
            return host.upper()
    except Exception:
        pass
    return f"Channel {index}"


def clean_name(s: str) -> str:
    s = re.sub(r'\s+', ' ', s).strip()
    s = re.sub(r'[^\w\s\-\.\+\(\)\/]', '', s)
    return s or "Unknown"


# ─── Playwright-парсер ────────────────────────────────────────────────────────

def run_playwright(channels: dict[str, str]):
    """
    Основной парсер на базе Playwright.
    Перехватывает сетевые запросы (включая XHR/fetch с m3u8),
    а также анализирует HTML после JS-рендеринга.
    """
    try:
        from playwright.sync_api import sync_playwright, TimeoutError as PWTimeout
    except ImportError:
        log.error("Playwright не установлен. Установи: pip install playwright && playwright install chromium")
        return

    intercepted: set[str] = set()

    def on_request(request):
        url = request.url
        if '.m3u8' in url.lower():
            intercepted.add(url)
            log.info(f"  [сеть] m3u8 перехвачен: {url}")

    def on_response(response):
        url = response.url
        if '.m3u8' in url.lower():
            intercepted.add(url)

    with sync_playwright() as pw:
        browser = pw.chromium.launch(
            headless=True,
            args=[
                '--no-sandbox',
                '--disable-setuid-sandbox',
                '--disable-blink-features=AutomationControlled',
                '--disable-dev-shm-usage',
                '--lang=ru-RU',
            ],
        )
        context = browser.new_context(
            viewport={"width": 1366, "height": 768},
            locale="ru-RU",
            timezone_id="Europe/Moscow",
            user_agent=(
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            extra_http_headers={
                "Accept-Language": "ru-RU,ru;q=0.9,en-US;q=0.8",
                "DNT": "1",
            },
        )
        page = context.new_page()
        page.on("request", on_request)
        page.on("response", on_response)

        # ── Загружаем главную страницу ────────────────────────────────────────
        log.info(f"Playwright → {BASE_URL}")
        try:
            page.goto(BASE_URL, timeout=PAGE_TIMEOUT, wait_until="networkidle")
        except PWTimeout:
            log.warning("Таймаут networkidle — пробуем domcontentloaded")
            try:
                page.goto(BASE_URL, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
            except Exception as e:
                log.error(f"Не удалось загрузить главную: {e}")
                browser.close()
                return

        time.sleep(WAIT_AFTER)
        _process_page(page, channels, "главная")

        # ── Собираем ссылки на каналы ─────────────────────────────────────────
        links = _collect_links(page)
        log.info(f"Внутренних ссылок: {len(links)}")

        visited = {BASE_URL}
        for link in links:
            if link in visited:
                continue
            visited.add(link)

            # playerjs: разбираем file= из URL
            if 'playerjs' in link.lower() or 'file=' in link:
                for u in find_m3u8(link):
                    u = clean_url(u)
                    if u not in channels:
                        channels[u] = guess_name(u, '', len(channels) + 1)
                        log.info(f"  + [url-param] {channels[u]}: {u}")

            # Переходим на страницу
            log.info(f"Playwright → {link[:80]}")
            try:
                page.goto(link, timeout=PAGE_TIMEOUT, wait_until="networkidle")
            except PWTimeout:
                try:
                    page.goto(link, timeout=PAGE_TIMEOUT, wait_until="domcontentloaded")
                except Exception as e:
                    log.warning(f"Пропускаем {link}: {e}")
                    continue
            except Exception as e:
                log.warning(f"Ошибка {link}: {e}")
                continue

            time.sleep(random.uniform(*NAV_DELAY))
            _process_page(page, channels, link[:60])

        # ── Добавляем перехваченные сетевые запросы ───────────────────────────
        for url in intercepted:
            url = clean_url(url)
            if url not in channels:
                channels[url] = guess_name(url, '', len(channels) + 1)
                log.info(f"  + [network] {channels[url]}: {url}")

        browser.close()


def _process_page(page, channels: dict[str, str], label: str):
    """Извлечь m3u8 из текущей страницы (HTML + JS-контент)."""
    added = 0
    try:
        html = page.content()
    except Exception:
        return

    for url in find_m3u8(html):
        url = clean_url(url)
        if url and url not in channels:
            name = guess_name(url, html, len(channels) + 1)
            channels[url] = name
            log.info(f"  + [{label}] {name}: {url}")
            added += 1

    if added:
        log.info(f"  Страница [{label}]: +{added} каналов | итого: {len(channels)}")


def _collect_links(page) -> list[str]:
    """Собрать все внутренние ссылки с текущей страницы."""
    try:
        hrefs = page.evaluate("""
            () => {
                const links = new Set();
                document.querySelectorAll('a[href], [data-src], [data-url], [data-stream]').forEach(el => {
                    const h = el.href || el.dataset.src || el.dataset.url || el.dataset.stream || '';
                    if (h) links.add(h);
                });
                return Array.from(links);
            }
        """)
    except Exception:
        return []

    result = []
    for href in hrefs:
        if not href or href.startswith(('javascript:', 'mailto:', '#')):
            continue
        if BASE_URL in href or 'l2arena' in href:
            result.append(href)
    return result


# ─── Fallback: requests (если Playwright недоступен) ─────────────────────────

def run_requests_fallback(channels: dict[str, str]):
    """Простой HTTP-парсер как запасной вариант."""
    import requests
    from bs4 import BeautifulSoup

    log.info("Запускаем fallback-парсер (requests + BeautifulSoup)")

    session = requests.Session()
    session.headers.update({
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
        "Accept-Language": "ru-RU,ru;q=0.9",
        "Referer": BASE_URL,
    })

    try:
        resp = session.get(BASE_URL, timeout=25)
        if resp.ok:
            html = resp.text
            soup = BeautifulSoup(html, 'html.parser')
            for url in find_m3u8(html):
                url = clean_url(url)
                if url and url not in channels:
                    channels[url] = guess_name(url, html, len(channels) + 1)
                    log.info(f"  + [fallback] {channels[url]}: {url}")
            # Атрибуты тегов
            for tag in soup.find_all(True):
                for attr in tag.attrs.values():
                    if isinstance(attr, str):
                        for url in find_m3u8(attr):
                            url = clean_url(url)
                            if url and url not in channels:
                                channels[url] = guess_name(url, '', len(channels) + 1)
                                log.info(f"  + [attr fallback] {channels[url]}: {url}")
        else:
            log.warning(f"Fallback: HTTP {resp.status_code}")
    except Exception as e:
        log.error(f"Fallback ошибка: {e}")


# ─── Плейлист ─────────────────────────────────────────────────────────────────

def build_playlist(channels: dict[str, str]) -> str:
    now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        '#EXTM3U x-tvg-url="" tvg-shift=0 cache=500',
        f'## TVArena-Project playlist | Обновлено: {now}',
        f'## Источник: {BASE_URL}',
        f'## Каналов найдено: {len(channels)}',
        '',
    ]
    for idx, (url, name) in enumerate(channels.items(), start=1):
        name = clean_name(name) or f"Channel {idx}"
        lines.append(f'#EXTINF:-1 tvg-id="{idx}" tvg-name="{name}",{name}')
        lines.append(url)
        lines.append('')
    return '\n'.join(lines)


def save_playlist(text: str, path: str = PLAYLIST_FILE):
    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
    log.info(f"Плейлист сохранён → {path} | {text.count('#EXTINF')} каналов")


# ─── Main ─────────────────────────────────────────────────────────────────────

def main():
    log.info("=" * 60)
    log.info("TVArena-Project Scraper — старт")
    log.info(f"Цель: {BASE_URL}")
    log.info("=" * 60)

    channels: dict[str, str] = {}

    # Основной движок — Playwright
    try:
        from playwright.sync_api import sync_playwright  # noqa: F401
        run_playwright(channels)
    except ImportError:
        log.warning("Playwright не найден — используем requests-fallback")
        run_requests_fallback(channels)

    log.info(f"Итого уникальных m3u8: {len(channels)}")
    if not channels:
        log.warning("Каналы не найдены.")
        log.warning("Если запускаешь локально — убедись что Playwright установлен:")
        log.warning("  pip install playwright && playwright install chromium")

    playlist = build_playlist(channels)
    save_playlist(playlist)

    log.info("=" * 60)
    log.info("Готово!")
    log.info("=" * 60)


if __name__ == "__main__":
    main()
