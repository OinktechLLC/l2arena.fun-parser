# TV.L2Arena M3U Scraper

Автоматическое извлечение m3u8-ссылок с https://tv.l2arena.fun и формирование плейлиста `playlist.m3u`.

## Как это работает
- Скрипт `scraper.py` каждую ночь запускается через GitHub Actions.
- Он парсит HTML страницы, ищет ссылки на `.m3u8` и параметр `file=` в `playerjs.html`.
- Все найденные ссылки сохраняются в `playlist.m3u` в формате:
