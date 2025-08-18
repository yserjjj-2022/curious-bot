# agents/content_extractor_agent.py

import sys
import time
import requests
import fitz  # PyMuPDF
from pathlib import Path
import re
from typing import List, Tuple, Optional
import random
from urllib.parse import urljoin

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
MIN_PDF_SIZE_BYTES = 10 * 1024 # Минимальный размер PDF (10 КБ), чтобы не считать его "коротким"

def parse_pdf_from_binary(pdf_data: bytes) -> Optional[str]:
    """Пытается распарсить бинарные данные как PDF. Возвращает текст или None."""
    try:
        text = ""
        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            for page in doc:
                text += page.get_text()
        return text.strip() if text else None
    except Exception:
        return None

def find_best_pdf_link(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Ищет лучшую ссылку на PDF на странице, анализируя ВСЕ атрибуты ссылки."""
    candidates = []
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if not href or href.startswith('javascript:'):
            continue

        link_profile = " ".join([
            link.get_text(strip=True).lower(), href.lower(),
            " ".join(link.get('class', [])).lower(), link.get('id', '').lower()
        ])
        
        score = 0
        if 'pdf' in link_profile: score += 10
        if 'download' in link_profile: score += 8
        if 'full text' in link_profile: score += 3
        if any(ext in href.lower() for ext in ['.ris', '.bib']) or 'citation' in link_profile: score -= 20
        
        if score > 0:
            candidates.append((score, urljoin(base_url, href)))

    if not candidates: return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def run_extraction_cycle(storage: StorageService):
    """Финальная версия: Агент-"Детектив"."""
    print("=== ЗАПУСК АГЕНТА-ЭКСТРАКТОРА КОНТЕНТА (ДЕТЕКТИВ) ===")
    articles_to_process = storage.get_articles_by_status('new', limit=1000)

    if not articles_to_process:
        print("...статей для извлечения контента не найдено."); return

    print(f"Найдено {len(articles_to_process)} статей для обработки.")
    for i, article in enumerate(articles_to_process):
        print(f"\n[{i+1}/{len(articles_to_process)}] Обрабатываю: {article.title[:50]}...")
        storage.update_article_status(article.id, 'extraction_in_progress')
        
        full_text = None
        source_of_truth_url = None
        pdf_is_image_based = False # Флаг для "картиночных" PDF
        
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
                    # --- ИЗМЕНЕНИЕ: Гибкий подход к скачиванию ---
                    # Если URL похож на прямой файл, сначала пытаемся скачать его через requests
                    if any(kw in current_url.lower() for kw in ['download', '.pdf', '/pdf/']):
                        try:
                            response = requests.get(current_url, headers={'User-Agent': USER_AGENT}, timeout=REQUESTS_TIMEOUT)
                            if response.status_code == 200 and len(response.content) > MIN_PDF_SIZE_BYTES:
                                pdf_text = parse_pdf_from_binary(response.content)
                                if pdf_text:
                                    print("    -> Успех! URL оказался прямой ссылкой на текстовый PDF.")
                                    full_text = pdf_text
                                    source_of_truth_url = current_url
                                    break # Квест завершен
                                else:
                                    # PDF скачался, но текста в нем нет -> это "картиночный" PDF
                                    print("    -> Успех! Скачан, предположительно, 'картиночный' PDF.")
                                    full_text = f"Image-based PDF, size: {len(response.content)} bytes."
                                    pdf_is_image_based = True
                                    source_of_truth_url = current_url
                                    break # Квест завершен
                        except requests.RequestException:
                            print("    -> Прямое скачивание не удалось, пробую навигацию...")

                    # Если requests не справился или URL не был похож на файл, используем Playwright
                    page.goto(current_url, timeout=REQUESTS_TIMEOUT*1000, wait_until='domcontentloaded')
                    current_url = page.url
                    if current_url in visited_urls and hop > 0:
                        print("    -> Обнаружен цикл, прекращаю навигацию."); break
                    visited_urls.add(current_url)

                    html_content = page.content()
                    soup = BeautifulSoup(html_content, 'html.parser')
                    best_link = find_best_pdf_link(soup, current_url)
                    
                    if best_link:
                        print(f"    -> Найдена лучшая зацепка: {best_link[:90]}...")
                        current_url = best_link
                    else:
                        print("    -> Дальнейших зацепок не найдено."); break
                except Exception as e:
                    print(f"    -> Ошибка на шаге {hop+1}: {e}"); break
        
        # --- Финальное решение ---
        if full_text:
            if pdf_is_image_based:
                # Если это картиночный PDF, мы не можем его саммаризировать, но сохраняем как успех
                storage.update_article_text(article.id, full_text)
                storage.update_article_content(article.id, 'pdf_image_only', source_of_truth_url)
                storage.update_article_status(article.id, 'image_pdf_extracted')
                print(f"  ✅ 'Картиночный' PDF успешно сохранен. Статус -> image_pdf_extracted")
            else:
                cleaned_text = cleanup_text(full_text)
                if len(cleaned_text) > 1500:
                    storage.update_article_text(article.id, cleaned_text)
                    storage.update_article_content(article.id, 'pdf', source_of_truth_url)
                    storage.update_article_status(article.id, 'awaiting_full_summary')
                    print(f"  ✅ Текстовый PDF успешно извлечен и сохранен. Статус -> awaiting_full_summary")
                else: # Если даже текстовый PDF оказался коротким
                    storage.update_article_status(article.id, 'awaiting_abstract_summary'); print(f"  -> PDF оказался слишком коротким. Статус -> awaiting_abstract_summary")
        elif article.original_abstract:
            storage.update_article_status(article.id, 'awaiting_abstract_summary'); print("  -> Полный текст не найден. Используем аннотацию. Статус -> awaiting_abstract_summary")
        else:
            storage.update_article_status(article.id, 'extraction_failed'); print("  ❌ Не удалось извлечь контент, и нет аннотации. Статус -> extraction_failed")

        if i < len(articles_to_process) - 1:
            sleep_time = random.uniform(2, 5); print(f"   ...пауза на {sleep_time:.1f} сек..."); time.sleep(sleep_time)

    print("\n=== РАБОТА АГЕНТА-ЭКСТРАКТОРА ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    storage_instance = StorageService(); run_extraction_cycle(storage_instance)

