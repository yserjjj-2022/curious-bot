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

# --- Используем Playwright ---
from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeoutError
from bs4 import BeautifulSoup
from services.storage_service import StorageService

def find_pdf_link_with_browser(page_url: str) -> str | None:
    """
    Заходит на страницу, используя Playwright, и ищет ссылку на PDF.
    """
    with sync_playwright() as p:
        browser = None
        try:
            launch_args = ['--disable-blink-features=AutomationControlled']
            browser = p.chromium.launch(headless=True, args=launch_args)
            
            context = browser.new_context(
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
            )
            page = context.new_page()
            
            page.goto(page_url, timeout=60000, wait_until='domcontentloaded')
            time.sleep(5) 
            html_content = page.content()

            soup = BeautifulSoup(html_content, 'html.parser')
            
            # Ищем ссылки, которые явно ведут на .pdf
            pdf_links = soup.find_all('a', href=re.compile(r'\.pdf$', re.I))
            if not pdf_links:
                # Если не нашли, ищем по тексту ссылки
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

# --- НОВАЯ ГЛАВНАЯ ФУНКЦИЯ ДЛЯ ОРКЕСТРАТОРА ---
def run_investigation_cycle(storage: StorageService):
    """
    Запускается "Дирижером", обрабатывает ВСЕ доступные статьи со статусом 'new'
    и завершает свою работу.
    """
    print("=== ЗАПУСК АГЕНТА-РАССЛЕДОВАТЕЛЯ ===")
    # storage = StorageService()
    
    # Берем все статьи 'new' за один раз
    articles_to_investigate = storage.get_articles_by_status('new', limit=1000)
    
    if not articles_to_investigate:
        print("...статей для расследования не найдено.")
        print("=== РАБОТА АГЕНТА-РАССЛЕДОВАТЕЛЯ ЗАВЕРШЕНА ===")
        return

    print(f"Найдено {len(articles_to_investigate)} новых статей для расследования. Начинаю обработку...")
    upgraded_count = 0
    
    for i, article in enumerate(articles_to_investigate):
        print(f"\n[{i+1}/{len(articles_to_investigate)}] Расследую: {article.title[:50]}...")
        
        url_to_check = article.doi
        new_status = 'investigated' # По умолчанию считаем, что расследование прошло
        
        if not url_to_check:
            print("  -> Пропускаю: нет DOI для проверки.")
            # Статус 'investigated' все равно ставим, чтобы статья пошла дальше по конвейеру
            # и обработалась на основе аннотации.
        else:
            print(f"   Проверяю DOI: {url_to_check}")
            pdf_link = find_pdf_link_with_browser(url_to_check)
            
            if pdf_link:
                print(f"  ✅ НАЙДЕН PDF: {pdf_link[:80]}...")
                storage.update_article_content(article.id, 'pdf', pdf_link)
                upgraded_count += 1
            else:
                print("  -> PDF не найден на странице DOI.")

        storage.update_article_status(article.id, new_status)
        print(f"   -> Статья обработана. Новый статус: '{new_status}'.")

        sleep_time = random.uniform(3, 7)
        print(f"   ...пауза на {sleep_time:.1f} секунд...")
        time.sleep(sleep_time)
            
    print(f"\n=== РАССЛЕДОВАНИЕ ЗАВЕРШЕНО ===")
    print(f"Всего обработано статей: {len(articles_to_investigate)}")
    print(f"Из них найдена прямая ссылка на PDF: {upgraded_count}")


if __name__ == "__main__":
    # Для ручного запуска создаем собственный экземпляр StorageService
    print("--- Запуск Расследователя в режиме ручной отладки ---")
    storage_instance = StorageService()
    run_investigation_cycle(storage_instance)