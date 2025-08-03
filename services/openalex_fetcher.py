# -*- coding: utf-8 -*-

import os
import pyalex
import re
from typing import List, Dict

# --- Конфигурация ---
from dotenv import load_dotenv
load_dotenv()
# Устанавливаем email для "вежливого" пула запросов OpenAlex
pyalex.config.email = os.getenv('OPENALEX_EMAIL', 'ershovsg@gmail.com')

def _normalize_id(openalex_id):
    """Приводит ID к короткому формату (например, T12345)."""
    if not openalex_id: return None
    return openalex_id.split('/')[-1]

def _normalize_title(title):
    """Приводит название к единому "чистому" формату для надежного сравнения."""
    if not title: return ""
    return re.sub(r'[^a-z0-9]', '', title.lower())

def _clean_title_for_ascii_check(text):
    """Очищает текст от распространенных не-ASCII символов, которые могут присутствовать в английских названиях."""
    if not text: return ""
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    text = text.replace('—', '-').replace('–', '-')
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub('<[^<]+?>', '', text)

def _is_likely_english(text, threshold=0.02):
    """Проверяет, является ли текст, скорее всего, английским, используя пропорциональную эвристику."""
    if not text: return True
    cleaned_text = _clean_title_for_ascii_check(text)
    if len(cleaned_text) == 0: return True
    non_ascii_chars = sum(1 for char in cleaned_text if not char.isascii())
    return (non_ascii_chars / len(cleaned_text)) < threshold

def _chunk_list(lst, n):
    """Разделяет список на чанки размером n."""
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

class OpenAlexFetcher:
    """
    Сервис для получения и первичной обработки статей из OpenAlex.
    Инкапсулирует всю сложную логику взаимодействия с API.
    """
    
    def fetch_articles(self, config: Dict) -> List[Dict]:
        """
        Основной метод. Принимает конфигурацию и возвращает список статей.
        """
        all_results_pool = []
        seen_ids = set()
        total_topics = config.get('topics', [])
        
        # --- 1. Пакетная обработка тем для избежания таймаутов ---
        topic_chunks = list(_chunk_list(total_topics, 7))
        print(f"Разбиваю {len(total_topics)} тем на {len(topic_chunks)} запросов...")

        for i, chunk in enumerate(topic_chunks):
            print(f"  -> Выполняю запрос {i+1}/{len(topic_chunks)}...")
            try:
                query = pyalex.Works()
                
                if config.get('search_in_fields'):
                    for field, search_term in config['search_in_fields'].items():
                        query = query.filter(**{field: search_term})
                if config.get('language'): query = query.filter(language=config.get('language'))
                if config.get('publication_year'): query = query.filter(publication_year=config['publication_year'])
                if config.get('document_types'): query = query.filter(type="|".join(config['document_types']))
                query = query.filter(topics={'id': "|".join(chunk)})
                query = query.sort(publication_date="desc")
                
                # Запрашиваем щедрое кол-во из каждого чанка
                select_fields = ['id', 'display_name', 'publication_year', 'publication_date', 'type', 'topics', 'language']
                chunk_results = query.select(select_fields).get(per_page=50)

                for paper in chunk_results:
                    if paper.get('id') not in seen_ids:
                        all_results_pool.append(paper)
                        seen_ids.add(paper.get('id'))
            except Exception as e:
                print(f"    ...ошибка при обработке чанка {i+1}: {e}")
        
        print(f"\nВсего получено {len(all_results_pool)} уникальных статей от API. Начинаю финальную обработку...")

        # --- 2. Локальная сортировка и фильтрация ---
        all_results_pool.sort(key=lambda x: x.get('publication_date', '1900-01-01'), reverse=True)
        
        clean_articles = []
        seen_normalized_titles = set()
        fetch_limit = config.get('fetch_limit', 50)

        for paper in all_results_pool:
            title = paper.get('display_name')
            if not title: continue
            
            target_language = config.get('language')
            if target_language and paper.get('language') and paper.get('language') != target_language: continue
            if target_language == 'en' and not _is_likely_english(title): continue
            
            normalized_title = _normalize_title(title)
            if normalized_title in seen_normalized_titles: continue
            seen_normalized_titles.add(normalized_title)
            
            clean_articles.append(paper)
            
            if len(clean_articles) >= fetch_limit:
                break
        
        print(f"   После всех фильтров осталось {len(clean_articles)} чистых статей.")
        return clean_articles

