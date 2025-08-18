# agents/content_extractor_agent.py

import sys
import time
import requests
import fitz  # PyMuPDF
from pathlib import Path
import re
from typing import List, Tuple, Optional
import random
from urllib.parse import urljoin, unquote

# --- Блок инициализации ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from readability import Document
from services.storage_service import StorageService
from agents.summary_agent import cleanup_text

# --- Константы ---
MAX_NAVIGATION_HOPS = 3
REQUESTS_TIMEOUT = 30
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
MIN_PDF_SIZE_BYTES = 10 * 1024 # 10 КБ

def parse_pdf_from_binary(pdf_data: bytes) -> Tuple[Optional[str], bool]:
    try:
        text, is_image_only = "", True
        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            for page in doc:
                if page.get_text("blocks"): is_image_only = False
                text += page.get_text()
        if not text.strip() and not is_image_only: return (None, False)
        if not text.strip() and is_image_only: return (None, True)
        return (text.strip(), False)
    except Exception:
        return (None, False)

# --- ИЗМЕНЕНИЕ: Полностью переработанная функция поиска ---
def find_best_pdf_link(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """
    Ищет лучшую ссылку на PDF, используя многоуровневую стратегию:
    1. Ищет прямую ссылку в мета-тегах.
    2. Если не находит, ищет лучшую видимую ссылку на странице.
    """
    # Стратегия 1: Поиск в мета-тегах (самый надежный способ)
    meta_tag = soup.find('meta', {'name': 'citation_pdf_url'})
    if meta_tag and meta_tag.get('content'):
        print("    -> Найдена надежная ссылка в мета-теге citation_pdf_url!")
        return meta_tag.get('content')

    # Стратегия 2: Анализ видимых ссылок (старая логика)
    candidates = []
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if not href or href.startswith('javascript:'): continue

        full_url = urljoin(base_url, href)
        decoded_url = unquote(full_url).lower()
        link_text = link.get_text(strip=True).lower()
        
        score = 0
        if 'pdf' in link_text or '.pdf' in decoded_url or '/pdf' in decoded_url: score += 10
        if 'download' in link_text or 'download' in decoded_url: score += 5
        if 'full text' in link_text: score += 3
        
        # Улучшенное правило: добавляем очки, если класс содержит 'pdf'
        link_class = ' '.join(link.get('class', [])).lower()
        if 'pdf' in link_class:
            score += 15
        
        negative_keywords = ['copyright', 'form', 'template', 'submission', 'ethics', 'policy']
        if any(keyword in link_text or keyword in decoded_url for keyword in negative_keywords):
            score -= 15
        
        if any(ext in decoded_url for ext in ['.ris', '.bib', '.enw']) or 'citation' in link_text:
            score -= 20
        
        if score > 5:
            candidates.append((score, full_url))

    if not candidates: return None
    candidates.sort(key=lambda x: x, reverse=True)
    return candidates[0][1] if candidates else None

def is_likely_reference_list(text: str) -> bool:
    if not text: return False
    text_lower = text.lower()
    if text_lower.strip().startswith(("references", "bibliography", "литература")): return True
    doi_count = text_lower.count("doi.org")
    if doi_count > 10: return True
    return False

def run_extraction_cycle(storage: StorageService):
    """Финальная версия: Агент, который "читает между строк"."""
    print("=== ЗАПУСК АГЕНТА-ЭКСТРАКТОРА (v4 - с поиском в мета-тегах) ===")
    articles_to_process = storage.get_articles_by_status('new', limit=1000)

    if not articles_to_process:
        print("...статей для извлечения контента не найдено."); return

    print(f"Найдено {len(articles_to_process)} статей для обработки.")
    for i, article in enumerate(articles_to_process):
        print(f"\n[{i+1}/{len(articles_to_process)}] Обрабатываю: {article.title[:50]}...")
        storage.update_article_status(article.id, 'extraction_in_progress')
        
        full_text, source_of_truth_url, pdf_is_image_based = None, None, False
        last_visited_html = None
        
        start_url = article.content_url or (f"https://doi.org/{article.doi}" if article.doi else None)
        if not start_url:
            storage.update_article_status(article.id, 'awaiting_abstract_summary'); continue
        
        current_url = start_url
        visited_urls = {current_url}
        
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            for hop in range(MAX_NAVIGATION_HOPS):
                print(f"  [Шаг {hop+1}] Анализирую: {current_url[:90]}...")
                try:
                    if any(kw in current_url.lower() for kw in ['download', '.pdf']):
                        response = requests.get(current_url, headers={'User-Agent': USER_AGENT}, timeout=REQUESTS_TIMEOUT)
                        if response.status_code == 200 and len(response.content) > MIN_PDF_SIZE_BYTES:
                            pdf_text, is_image_pdf = parse_pdf_from_binary(response.content)
                            if pdf_text:
                                full_text, pdf_is_image_based = pdf_text, False
                            elif is_image_pdf:
                                full_text, pdf_is_image_based = f"Image-based PDF, size: {len(response.content)} bytes.", True
                            else:
                                print("    -> Обнаружен PDF с проблемой кодировки текста. Текст не извлечен.")
                                full_text = None
                            source_of_truth_url = current_url
                            break
                        else:
                            print("    -> Не удалось скачать PDF через requests. Прекращаю попытки для этого URL.")
                            break
                    
                    page.goto(current_url, timeout=REQUESTS_TIMEOUT*1000, wait_until='domcontentloaded')
                    last_visited_html = page.content()
                    current_url = page.url
                    if current_url in visited_urls and hop > 0:
                        print("    -> Обнаружен цикл, прекращаю навигацию."); break
                    visited_urls.add(current_url)

                    soup = BeautifulSoup(last_visited_html, 'html.parser')
                    best_link = find_best_pdf_link(soup, current_url)
                    
                    if best_link:
                        print(f"    -> Найдена лучшая зацепка: {best_link[:90]}...")
                        current_url = best_link
                    else:
                        print("    -> Дальнейших зацепок не найдено.")
                        break
                except Exception as e:
                    print(f"    -> Ошибка на шаге {hop+1}: {e}"); break
        
        if not full_text and last_visited_html:
            print("  -> Поиск PDF не удался. Запускаю План Б: извлечение текста из HTML.")
            try:
                doc = Document(last_visited_html)
                html_article_text = doc.summary()
                soup = BeautifulSoup(html_article_text, 'html.parser')
                final_html_text = soup.get_text(separator='\n', strip=True)
                
                if not is_likely_reference_list(final_html_text) and len(final_html_text) > 1500:
                    full_text = final_html_text; source_of_truth_url = current_url
                    print("    -> Успех! Извлечен полный текст из HTML.")
            except Exception as e:
                print(f"    -> Ошибка при извлечении текста из HTML: {e}")

        if full_text:
            if pdf_is_image_based:
                storage.update_article_text(article.id, full_text); storage.update_article_content(article.id, 'pdf_image_only', source_of_truth_url); storage.update_article_status(article.id, 'image_pdf_extracted')
                print(f"  ✅ 'Картиночный' PDF успешно сохранен. Статус -> image_pdf_extracted")
            else:
                content_type = 'html' if source_of_truth_url == current_url else 'pdf'
                cleaned_text = cleanup_text(full_text)
                if len(cleaned_text) > 1500:
                    storage.update_article_text(article.id, cleaned_text); storage.update_article_content(article.id, content_type, source_of_truth_url); storage.update_article_status(article.id, 'awaiting_full_summary')
                    print(f"  ✅ Полный текст ({content_type}) успешно извлечен и сохранен. Статус -> awaiting_full_summary")
                else:
                    storage.update_article_status(article.id, 'awaiting_abstract_summary'); print(f"  -> Извлеченный текст ({content_type}) оказался слишком коротким. Статус -> awaiting_abstract_summary")
        elif article.original_abstract:
            storage.update_article_status(article.id, 'awaiting_abstract_summary'); print("  -> Полный текст не найден. Используем аннотацию. Статус -> awaiting_abstract_summary")
        else:
            storage.update_article_status(article.id, 'extraction_failed'); print("  ❌ Не удалось извлечь контент, и нет аннотации. Статус -> extraction_failed")

        if i < len(articles_to_process) - 1:
            sleep_time = random.uniform(2, 5); print(f"   ...пауза на {sleep_time:.1f} сек..."); time.sleep(sleep_time)

    print("\n=== РАБОТА АГЕНТА-ЭКСТРАКТОРА ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    storage_instance = StorageService(); run_extraction_cycle(storage_instance)
