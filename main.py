# -*- coding: utf-8 -*-

import sys
import time
import re
import random
from pathlib import Path
from urllib.parse import urljoin

# --- Надежная загрузка .env и настройка импортов ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
from dotenv import load_dotenv
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
# --- ГЛАВНОЕ ИЗМЕНЕНИЕ: Правильный импорт для современных версий ---
from playwright_stealth.stealth import stealth_sync
# ------------------------------------------------------------------
from bs4 import BeautifulSoup
from services.storage_service import StorageService

def find_pdf_link_with_browser(page_url: str) -> str | None:
    """
    Заходит на страницу с помощью "замаскированного" браузера и ищет ссылку на PDF.
    """
    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            # Включаем режим "невидимки"
            stealth_sync(page)
            
            # Увеличиваем таймаут до 60 секунд для "тяжелых" сайтов
            page.goto(page_url, timeout=60000, wait_until='networkidle')
            
            html_content = page.content()
            browser.close()

        soup = BeautifulSoup(html_content, 'html.parser')
        
        pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.I))
        if not pdf_links:
            # Исправляем DeprecationWarning, используя 'string'
            pdf_links = soup.find_all('a', string=re.compile(r'.*(pdf|download|full.?text).*', re.I))

        for link in pdf_links:
            href = link.get('href')
            if href and not href.startswith('javascript:'):
                return urljoin(page_url, href)
                    
        return None
    except PlaywrightTimeoutError:
        print(f"    -> Ошибка: Страница {page_url} не загрузилась за 60 секунд.")
        return None
    except Exception as e:
        print(f"    -> Неожиданная ошибка при работе с Playwright: {e}")
        return None

def run_investigation():
    """
    Основной цикл работы "Агента-Следователя" на движке Playwright в режиме "невидимки".
    """
    print("=== ЗАПУСК АГЕНТА-СЛЕДОВАТЕЛЯ (Движок: Playwright-Stealth) ===")
    storage = StorageService()
    
    articles_to_investigate = storage.get_articles_by_status('new', limit=10)
    upgraded_count = 0
    print(f"Найдено {len(articles_to_investigate)} статей для расследования...")

    for i, article in enumerate(articles_to_investigate):
        url_to_check = article.doi
        
        if not url_to_check or article.content_type == 'pdf':
            print(f"[{i+1}/{len(articles_to_investigate)}] Пропускаю: {article.title[:40]}... (Причина: нет DOI или уже PDF)")
            continue

        print(f"\n[{i+1}/{len(articles_to_investigate)}] Расследую: {article.title[:50]}... (DOI: {url_to_check})")
        
        pdf_link = find_pdf_link_with_browser(url_to_check)
        
        if pdf_link:
            print(f"  ✅ НАЙДЕН PDF: {pdf_link}")
            storage.update_article_content(article.id, 'pdf', pdf_link)
            upgraded_count += 1
        else:
            print("  -> PDF не найден на странице.")

        sleep_time = random.uniform(5, 10)
        print(f"   ...пауза на {sleep_time:.1f} секунд...")
        time.sleep(sleep_time)
            
    print(f"\n=== РАССЛЕДОВАНИЕ ЗАВЕРШЕНО ===")
    print(f"Успешно 'прокачано' до PDF: {upgraded_count} статей.")

if __name__ == "__main__":
    run_investigation()
