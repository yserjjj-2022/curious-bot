# -*- coding: utf-8 -*-

import os
import pyalex
import re
from typing import List, Dict, Tuple, Optional
from pyalex import invert_abstract

# --- Конфигурация и вспомогательные функции (остаются без изменений) ---
pyalex.config.email = os.getenv('OPENALEX_EMAIL', 'user@example.com')

def _normalize_title(title: str) -> str:
    if not title: return ""
    return re.sub(r'[^a-z0-9]', '', title.lower())

def _clean_title_for_ascii_check(text: str) -> str:
    if not text: return ""
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    text = text.replace('—', '-').replace('–', '-')
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub('<[^<]+?>', '', text)

def _is_likely_english(text: str, threshold: float = 0.003) -> bool:
    if not text: return True
    cleaned_text = _clean_title_for_ascii_check(text)
    if not cleaned_text: return True
    if len(cleaned_text) == 0: return True
    non_ascii_chars = sum(1 for char in cleaned_text if not char.isascii())
    return (non_ascii_chars / len(cleaned_text)) < threshold

def _get_best_content_source(work: Dict) -> Tuple[Optional[str], Optional[str]]:
    best_loc = work.get('best_oa_location')
    if best_loc and best_loc.get('is_oa') and best_loc.get('pdf_url'):
        return 'pdf', best_loc.get('pdf_url')
    for loc in work.get('locations', []):
        if loc.get('is_oa') and loc.get('pdf_url'):
            return 'pdf', loc.get('pdf_url')
    if best_loc and best_loc.get('is_oa') and best_loc.get('landing_page_url'):
        return 'html', best_loc.get('landing_page_url')
    for loc in work.get('locations', []):
        if loc.get('is_oa') and loc.get('landing_page_url'):
            return 'html', loc.get('landing_page_url')
    if work.get('abstract_inverted_index'):
        return 'abstract', None
    return None, None


# --- Основной класс ---
class OpenAlexFetcher:
    def fetch_articles(self, config: Dict) -> List[Dict]:
        all_results_pool = []
        seen_ids = set()
        
        try:
            query = pyalex.Works()
            
            # Применяем базовые фильтры
            if config.get('language'): query = query.filter(language=config['language'])
            if config.get('publication_year'): query = query.filter(publication_year=config['publication_year'])
            document_types = config.get('document_types', ['article', 'book-chapter'])
            if document_types: query = query.filter(type="|".join(document_types))
            
            # --- ИСПРАВЛЕННАЯ, ЛОГИЧЕСКИ ВЕРНАЯ ЛОГИКА ПОИСКА ---
            context_keys = config.get('context_keywords', [])
            aspect_keys = config.get('aspect_keywords', [])

            if not context_keys or not aspect_keys:
                print("   -> ВНИМАНИЕ: В файле отсутствуют context_keywords или aspect_keywords. Поиск невозможен.")
                return []

            # Формируем группу для контекста: ("term1" OR "term2")
            context_search_part = " OR ".join([f'"{phrase}"' for phrase in context_keys])
            
            # Формируем группу для аспекта: ("term3" OR "term4")
            aspect_search_part = " OR ".join([f'"{phrase}"' for phrase in aspect_keys])

            # Собираем финальный запрос: (контекст) AND (аспект)
            final_search_query = f"({context_search_part}) AND ({aspect_search_part})"
            
            # Используем основной метод .search()
            query = query.search(final_search_query)
            # ----------------------------------------------------

            query = query.sort(publication_date="desc")
            
            select_fields = [
                'id', 'display_name', 'publication_year', 'publication_date', 
                'type', 'topics', 'language', 'abstract_inverted_index',
                'best_oa_location', 'locations', 'doi'
            ]
            
            print(f"  -> Выполняю поиск по запросу: {final_search_query}")
            all_results = query.select(select_fields).get(per_page=200)

            for paper in all_results:
                if paper.get('id') not in seen_ids:
                    content_type, content_url = _get_best_content_source(paper)
                    paper['content_type'] = content_type
                    paper['content_url'] = content_url
                    paper['abstract'] = invert_abstract(paper.get('abstract_inverted_index')) if paper.get('abstract_inverted_index') else None
                    all_results_pool.append(paper)
                    seen_ids.add(paper.get('id'))
        except Exception as e:
            print(f"    ...ошибка при выполнении запроса: {e}")
        
        print(f"\nВсего получено {len(all_results_pool)} уникальных статей от API. Начинаю финальную обработку...")

        # Финальная фильтрация и сортировка
        all_results_pool.sort(key=lambda x: x.get('publication_date', '1900-01-01'), reverse=True)
        
        clean_articles = []
        seen_normalized_titles = set()
        fetch_limit = config.get('fetch_limit', 50)

        for paper in all_results_pool:
            if not paper.get('content_type'): continue
            title = paper.get('display_name')
            if not title: continue
            
            target_language = config.get('language')
            if target_language and paper.get('language') and paper.get('language') != target_language: continue
            if target_language == 'en' and not _is_likely_english(title): continue
            
            normalized_title = _normalize_title(title)
            if normalized_title in seen_normalized_titles: continue
            seen_normalized_titles.add(normalized_title)
            
            clean_articles.append(paper)
            if len(clean_articles) >= fetch_limit: break
        
        print(f"   После всех фильтров осталось {len(clean_articles)} чистых статей.")
        return clean_articles
