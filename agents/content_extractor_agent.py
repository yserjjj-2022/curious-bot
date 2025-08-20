# agents/content_extractor_agent.py

import sys
import time
import requests
import fitz  # PyMuPDF
from pathlib import Path
from typing import Tuple, Optional
import random
from urllib.parse import urljoin

# --- Блок инициализации ---
project_root = Path(__file__).resolve().parent.parent
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from dotenv import load_dotenv
load_dotenv()

from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
from readability import Document
from services.storage_service import StorageService
# --- ИЗМЕНЕНИЕ: Импортируем ЛЕГКУЮ функцию очистки ---
from services.text_utils import cleanup_extracted_text

# --- Константы ---
MAX_NAVIGATION_HOPS = 3
REQUESTS_TIMEOUT = 30
USER_AGENT = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36'
MIN_PDF_SIZE_BYTES = 10 * 1024

def parse_pdf_from_binary(pdf_data: bytes) -> Tuple[Optional[str], bool]:
    """Извлекает текст из PDF, возвращает (текст, флаг 'только картинки')."""
    try:
        text, is_image_only = "", True
        with fitz.open(stream=pdf_data, filetype="pdf") as doc:
            for page in doc:
                if page.get_text("blocks"): is_image_only = False
                text += page.get_text()
        
        cleaned_text = text.strip()
        if not cleaned_text:
            return None, is_image_only
            
        return cleaned_text, False
    except Exception as e:
        print(f"    -> Ошибка при парсинге PDF: {e}")
        return None, False

def find_best_pdf_link(soup: BeautifulSoup, base_url: str) -> Optional[str]:
    """Ищет лучшую ссылку на PDF, используя многоуровневую стратегию."""
    meta_tag = soup.find('meta', {'name': 'citation_pdf_url'})
    if meta_tag and meta_tag.get('content'):
        print("    -> Найдена надежная ссылка в мета-теге!")
        return meta_tag.get('content')
    
    candidates = []
    for link in soup.find_all('a', href=True):
        href = link.get('href', '')
        if not href or href.startswith('javascript:'): continue
        
        full_url = urljoin(base_url, href)
        link_text = link.get_text(strip=True).lower()
        link_class = ' '.join(link.get('class', [])).lower()
        
        score = 0
        if 'pdf' in link_class: score += 20
        if 'pdf' in link_text: score += 15
        if 'full text' in link_text: score += 10
        if any(kw in full_url for kw in ['.pdf', '/pdf', 'download']): score += 5
        
        negative_keywords = ['copyright', 'form', 'template', 'submission', 'ethics', 'policy', 'author']
        if any(keyword in link_text or keyword in full_url for keyword in negative_keywords):
            score -= 15
        if any(ext in full_url for ext in ['.ris', '.bib']) or 'citation' in link_text:
            score -= 20
        
        if score > 8: candidates.append((score, full_url))
            
    if not candidates: return None
    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]

def run_extraction_cycle(storage: StorageService):
    print("=== ЗАПУСК АГЕНТА-ЭКСТРАКТОРА (v8 - Двухрежимная очистка) ===")
    articles = storage.get_articles_by_status('new', limit=1000)
    
    for i, article in enumerate(articles):
        print(f"\\n[{i+1}/{len(articles)}] Обрабатываю: {article.title[:50]}...")
        storage.update_article_status(article.id, 'extraction_in_progress')
        
        start_url = article.content_url or (f"https://doi.org/{article.doi}" if article.doi else None)
        if not start_url:
            storage.update_article_status(article.id, 'awaiting_abstract_summary'); continue

        urls_to_check = [start_url]
        visited_urls = {start_url}
        pdf_content, source_of_truth_url, last_html_content = None, None, None

        while urls_to_check:
            current_url = urls_to_check.pop(0)
            if len(visited_urls) > 5: print("    -> Превышен лимит переходов."); break
            
            print(f"  -> Проверяю URL: {current_url[:90]}...")
            try:
                head_resp = requests.head(current_url, headers={'User-Agent': USER_AGENT}, timeout=REQUESTS_TIMEOUT, allow_redirects=True)
                content_type = head_resp.headers.get('Content-Type', '').lower()
                
                if 'application/pdf' in content_type:
                    print("    -> Ответ сервера указывает на PDF. Скачиваю напрямую...")
                    get_resp = requests.get(current_url, headers={'User-Agent': USER_AGENT}, timeout=REQUESTS_TIMEOUT)
                    get_resp.raise_for_status()
                    if len(get_resp.content) > MIN_PDF_SIZE_BYTES:
                        pdf_content, source_of_truth_url = get_resp.content, current_url
                    break
                
                elif 'text/html' in content_type:
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        page = browser.new_page()
                        page.goto(current_url, wait_until='domcontentloaded', timeout=60000)
                        last_html_content = page.content()
                        soup = BeautifulSoup(last_html_content, 'html.parser')
                        next_link = find_best_pdf_link(soup, page.url)
                        if next_link and next_link not in visited_urls:
                            urls_to_check.insert(0, next_link)
                            visited_urls.add(next_link)
                        browser.close()
            except Exception as e:
                print(f"    -> Ошибка при проверке URL: {e}")

        if pdf_content:
            print("  -> PDF успешно скачан. Извлекаю текст...")
            full_text, is_image_only = parse_pdf_from_binary(pdf_content)
            
            if full_text:
                # --- ИЗМЕНЕНИЕ: Используем ЛЕГКУЮ функцию очистки ---
                storage.update_article_text(article.id, cleanup_extracted_text(full_text))
                storage.update_article_content(article.id, 'pdf', source_of_truth_url)
                storage.update_article_status(article.id, 'awaiting_full_summary')
                print(f"  ✅ Полный текст (PDF) успешно извлечен.")
            elif is_image_only:
                storage.update_article_status(article.id, 'extraction_failed_pdf_image')
            else:
                storage.update_article_status(article.id, 'extraction_failed_pdf_empty')
        
        elif last_html_content:
            print("  -> PDF не найден. Запускаю План Б: извлечение из HTML.")
            try:
                doc = Document(last_html_content)
                soup = BeautifulSoup(doc.summary(), 'html.parser')
                html_text = soup.get_text(separator='\\n', strip=True)
                if len(html_text) > 1500:
                    # --- ИЗМЕНЕНИЕ: Используем ЛЕГКУЮ функцию очистки ---
                    storage.update_article_text(article.id, cleanup_extracted_text(html_text))
                    storage.update_article_content(article.id, 'html', list(visited_urls)[-1])
                    storage.update_article_status(article.id, 'awaiting_full_summary')
                    print(f"  ✅ Полный текст (HTML) успешно извлечен.")
                else:
                    raise ValueError("Извлеченный HTML слишком короткий.")
            except Exception:
                if article.original_abstract:
                    storage.update_article_status(article.id, 'awaiting_abstract_summary')
                else:
                    storage.update_article_status(article.id, 'extraction_failed')
        else:
            if article.original_abstract:
                storage.update_article_status(article.id, 'awaiting_abstract_summary')
            else:
                storage.update_article_status(article.id, 'extraction_failed')
        
        if i < len(articles) - 1:
            time.sleep(random.uniform(2, 4))
            
    print("\\n=== РАБОТА АГЕНТА-ЭКСТРАКТОРА ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    storage_instance = StorageService()
    run_extraction_cycle(storage_instance)

