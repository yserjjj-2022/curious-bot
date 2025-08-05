# -*- coding: utf-8 -*-

import sys
import time
import requests
import fitz
from pathlib import Path
from readability import Document
from bs4 import BeautifulSoup

# --- Блок инициализации ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
from dotenv import load_dotenv
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- Импорты наших модулей ---
from playwright.sync_api import sync_playwright
from services.storage_service import StorageService
from agents.summary_agent import cleanup_text

# ... (parse_pdf_from_url и parse_html_from_url остаются без изменений) ...
def parse_pdf_from_url(pdf_url: str) -> str | None:
    """Скачивает и парсит PDF по прямой ссылке."""
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(pdf_url, headers=headers, timeout=30, stream=True)
        response.raise_for_status()
        if 'application/pdf' not in response.headers.get('Content-Type', ''):
            print(f"    -> Ссылка {pdf_url[:70]}... не является PDF.")
            return None
        pdf_data = response.content
        text = ""
        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text.strip()
    except Exception as e:
        print(f"    -> Ошибка при обработке PDF по ссылке {pdf_url[:70]}...: {e}")
        return None

def parse_html_from_url(page_url: str, original_abstract: str = None) -> str | None:
    """Заходит на страницу, извлекает текст и проверяет его на адекватность."""
    with sync_playwright() as p:
        browser = None
        try:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(page_url, timeout=60000, wait_until='domcontentloaded')
            time.sleep(3)
            html_content = page.content()
            
            doc = Document(html_content)
            extracted_html = doc.summary()
            soup = BeautifulSoup(extracted_html, 'html.parser')
            extracted_text = soup.get_text(separator='\n', strip=True)

            if original_abstract and original_abstract[:100] not in extracted_text:
                print("    -> ВНИМАНИЕ: Извлеченный HTML не содержит аннотации. Считаем его невалидным.")
                return None
            
            return extracted_text
        except Exception as e:
            print(f"    -> Неожиданная ошибка при парсинге HTML со страницы {page_url[:70]}...: {e}")
            return None
        finally:
            if browser:
                browser.close()

def run_extraction_cycle():
    """Основной цикл работы "Агента-Экстрактора" (с приоритетом для .pdf)."""
    print("=== ЗАПУСК АГЕНТА-ЭКСТРАКТОРА КОНТЕНТА (Финальная версия с приоритетом) ===")
    storage = StorageService()
    
    while True:
        print("\nИщу статьи для извлечения контента...")
        articles_to_process = storage.get_articles_by_status(['awaiting_parsing', 'awaiting_summary'], limit=5)
        
        if not articles_to_process:
            print("...статей для обработки не найдено. Пауза 60 секунд.")
            time.sleep(60)
            continue

        for article in articles_to_process:
            print(f"\n-> Обрабатываю статью: {article.title[:50]}...")
            raw_text = None
            source_type = None

            # --- Новая, улучшенная стратегия с приоритетом для .pdf ---
            
            # 1. Приоритетная попытка: Скачивание PDF, если ссылка выглядит как PDF
            if article.content_url and article.content_url.lower().endswith('.pdf'):
                print("   Попытка №1 (Приоритетная): Обнаружена прямая ссылка на PDF...")
                raw_text = parse_pdf_from_url(article.content_url)
                if raw_text: source_type = 'direct_pdf'

            # 2. Попытка извлечь HTML со страницы content_url (если приоритетная не сработала)
            if not raw_text and article.content_url:
                print(f"   Попытка №2: Извлечение HTML со страницы content_url...")
                raw_text = parse_html_from_url(article.content_url, article.original_abstract)
                if raw_text: source_type = 'content_url_html'

            # 3. Попытка извлечь HTML со страницы DOI (последний шанс)
            if not raw_text and article.doi and article.doi != article.content_url:
                print(f"   Попытка №3: Извлечение HTML со страницы DOI...")
                raw_text = parse_html_from_url(article.doi, article.original_abstract)
                if raw_text: source_type = 'doi_html'

            # --- Финальное принятие решения (логика остается без изменений) ---
            if raw_text:
                print(f"   Извлечен 'грязный' текст ({len(raw_text)} симв.). Начинаю очистку...")
                cleaned_text = cleanup_text(raw_text)
                print(f"   Длина 'чистого' текста: {len(cleaned_text)} симв.")

                if len(cleaned_text) > 2500:
                    print(f"  ✅ Текст признан полным (источник: {source_type}).")
                    storage.update_article_text(article.id, cleaned_text)
                    storage.update_article_status(article.id, 'awaiting_full_summary')
                    print(f"   -> Статус изменен на 'awaiting_full_summary'.")
                else:
                    print("  -> 'Чистый' текст слишком короткий. Будем использовать аннотацию.")
                    storage.update_article_status(article.id, 'awaiting_abstract_summary')
                    print(f"   -> Статус изменен на 'awaiting_abstract_summary'.")
            
            elif article.original_abstract:
                print("  -> Текст извлечь не удалось. Используем аннотацию.")
                storage.update_article_status(article.id, 'awaiting_abstract_summary')
                print(f"   -> Статус изменен на 'awaiting_abstract_summary'.")
            else:
                print("  -> Не удалось извлечь контент.")
                storage.update_article_status(article.id, 'extraction_failed')
                print(f"   -> Статус изменен на 'extraction_failed'.")
        
        print("\nЦикл экстракции завершен. Небольшая пауза...")
        time.sleep(10)

if __name__ == "__main__":
    run_extraction_cycle()
