# Файл: agents/investigator_agent.py
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

# --- Используем ТОЛЬКО официальный Playwright ---
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from services.storage_service import StorageService

def find_pdf_link_with_browser(page_url: str) -> str | None:
    """
    Заходит на страницу, используя стандартный Playwright с аргументами для маскировки.
    """
    with sync_playwright() as p:
        browser = None
        try:
            launch_args = [
                '--disable-blink-features=AutomationControlled',
                '--start-maximized',
            ]
            browser = p.chromium.launch(headless=True, args=launch_args)
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
                viewport={'width': 1920, 'height': 1080},
            )
            page = context.new_page()
            
            page.goto(page_url, timeout=60000, wait_until='domcontentloaded')
            time.sleep(5) 
            html_content = page.content()

            soup = BeautifulSoup(html_content, 'html.parser')
            
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf', re.I))
            if not pdf_links:
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
        finally:
            if browser:
                browser.close()

def run_investigation():
    """
    Основной цикл работы "Агента-Следователя", который теперь
    ПРАВИЛЬНО меняет статус статьи с 'new' на 'investigated'.
    """
    print("=== ЗАПУСК АГЕНТА-СЛЕДОВАТЕЛЯ (Финальная, синхронизированная версия) ===")
    storage = StorageService()
    
    articles_to_investigate = storage.get_articles_by_status('new', limit=10)
    upgraded_count = 0
    processed_count = 0
    print(f"Найдено {len(articles_to_investigate)} новых статей для расследования...")

    for i, article in enumerate(articles_to_investigate):
        url_to_check = article.doi
        new_status = 'investigated'
        
        if not url_to_check:
            print(f"[{i+1}/{len(articles_to_investigate)}] Пропускаю: {article.title[:40]}... (Причина: нет DOI)")
            new_status = 'investigated_no_link'
        else:
            print(f"\n[{i+1}/{len(articles_to_investigate)}] Расследую: {article.title[:50]}... (DOI: {url_to_check})")
            
            pdf_link = find_pdf_link_with_browser(url_to_check)
            
            if pdf_link:
                print(f"  ✅ НАЙДЕН PDF: {pdf_link}")
                storage.update_article_content(article.id, 'pdf', pdf_link)
                upgraded_count += 1
            else:
                print("  -> PDF не найден на странице.")

        storage.update_article_status(article.id, new_status)
        processed_count += 1
        print(f"   -> Статья {article.id} обработана. Новый статус: '{new_status}'.")

        sleep_time = random.uniform(5, 10)
        print(f"   ...пауза на {sleep_time:.1f} секунд...")
        time.sleep(sleep_time)
            
    print(f"\n=== РАССЛЕДОВАНИЕ ЗАВЕРШЕНО ===")
    print(f"Всего обработано статей: {processed_count}")
    print(f"Из них 'прокачано' до PDF: {upgraded_count}")

if __name__ == "__main__":
    run_investigation()
