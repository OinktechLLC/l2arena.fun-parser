import re
import requests
from bs4 import BeautifulSoup
from urllib.parse import urlparse, urljoin, unquote
from datetime import datetime
import logging

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

BASE_URL = "https://tv.l2arena.fun/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
}

def get_page_html(url):
    try:
        resp = requests.get(url, headers=HEADERS, timeout=15)
        resp.raise_for_status()
        return resp.text
    except Exception as e:
        logging.error(f"Failed to fetch {url}: {e}")
        return None

def extract_m3u8_links(html, base_url):
    soup = BeautifulSoup(html, 'lxml')
    links = set()

    # 1. Ищем playerjs.html?file=...
    for tag in soup.find_all(['a', 'iframe', 'script'], src=True, href=True):
        attr = tag.get('src') or tag.get('href')
        if not attr:
            continue
        full_url = urljoin(base_url, attr)
        # playerjs.html?file=...
        if 'playerjs.html' in full_url:
            match = re.search(r'[?&]file=([^&]+)', full_url)
            if match:
                encoded_url = match.group(1)
                decoded = unquote(encoded_url)
                if '.m3u8' in decoded:
                    links.add(decoded)
        # прямые m3u8
        elif '.m3u8' in full_url:
            links.add(full_url)

    # 2. Ищем внутри <script> переменные, содержащие m3u8
    for script in soup.find_all('script'):
        if script.string:
            # паттерн: 'http...m3u8' или "http...m3u8"
            found = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', script.string)
            for url in found:
                links.add(url)
            # паттерн с file=
            found2 = re.findall(r'file:\s*[\'"]([^\'"]+\.m3u8[^\'"]*)[\'"]', script.string)
            for url in found2:
                links.add(url)

    # 3. Можно добавить дополнительные правила (например, из iframe src с m3u8)
    return list(links)

def get_channel_name(url, soup, fallback_idx):
    # Попытаться найти название из окружающего текста (упрощённо)
    # Здесь можно расширить логику: например, взять title страницы или текст ближайшего родителя
    # Для демонстрации – используем домен и путь
    parsed = urlparse(url)
    path = parsed.path.rstrip('/')
    name = path.split('/')[-1].replace('.m3u8', '').replace('index', '')
    if not name or len(name) < 2:
        name = f"Channel_{fallback_idx}"
    # Очистка
    name = re.sub(r'[^\w\s\-]', '', name).strip()
    return name if name else f"Channel_{fallback_idx}"

def generate_m3u(links, soup):
    m3u_lines = ["#EXTM3U"]
    for idx, url in enumerate(links, 1):
        if not url.startswith('http'):
            url = urljoin(BASE_URL, url)
        name = get_channel_name(url, soup, idx)
        m3u_lines.append(f'#EXTINF:-1,{name}')
        m3u_lines.append(url)
    return "\n".join(m3u_lines)

def main():
    logging.info("Start scraping tv.l2arena.fun")
    html = get_page_html(BASE_URL)
    if not html:
        return

    soup = BeautifulSoup(html, 'lxml')
    links = extract_m3u8_links(html, BASE_URL)

    if not links:
        # Fallback: попробовать найти ссылки через регулярку по всему HTML
        all_m3u8 = re.findall(r'https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*', html)
        links = list(set(all_m3u8))

    logging.info(f"Found {len(links)} unique m3u8 links")

    m3u_content = generate_m3u(links, soup)

    with open("playlist.m3u", "w", encoding="utf-8") as f:
        f.write(m3u_content)

    logging.info("playlist.m3u saved")

if __name__ == "__main__":
    main()
