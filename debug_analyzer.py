# -*- coding: utf-8 -*-

import os
import json
import yaml
import pyalex
import re
from glob import glob
from datetime import datetime

# --- Конфигурация ---
from dotenv import load_dotenv
load_dotenv()
pyalex.config.email = os.getenv('OPENALEX_EMAIL', 'user@example.com')

def normalize_id(openalex_id):
    if not openalex_id: return None
    return openalex_id.split('/')[-1]

def normalize_title(title):
    if not title: return ""
    return re.sub(r'[^a-z0-9]', '', title.lower())

def clean_title_for_ascii_check(text):
    if not text: return ""
    text = text.replace('“', '"').replace('”', '"').replace('‘', "'").replace('’', "'")
    text = text.replace('—', '-').replace('–', '-')
    text = re.sub(r'\s+', ' ', text).strip()
    return re.sub('<[^<]+?>', '', text)

def is_likely_english(text, threshold=0.003):
    if not text: return True
    cleaned_text = clean_title_for_ascii_check(text)
    if len(cleaned_text) == 0: return True
    non_ascii_chars = sum(1 for char in cleaned_text if not char.isascii())
    return (non_ascii_chars / len(cleaned_text)) < threshold

def chunk_list(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i + n]

def analyze_source(config: dict):
    config_name = os.path.basename(config.get('config_path', 'default.yaml'))
    print(f"\n--- Анализирую источник: {config_name} ---")
    try:
        all_results_pool = []
        seen_ids = set()
        total_topics = config.get('topics', [])
        total_available_estimate = 0
        
        # --- НОВАЯ ЛОГИКА: Пакетная обработка тем ---
        topic_chunks = list(chunk_list(total_topics, 7))
        print(f"Разбиваю {len(total_topics)} тем на {len(topic_chunks)} запросов...")

        for i, chunk in enumerate(topic_chunks):
            print(f"  -> Выполняю запрос {i+1}/{len(topic_chunks)} для {len(chunk)} тем...")
            query = pyalex.Works()
            
            if config.get('search_in_fields'):
                for field, search_term in config['search_in_fields'].items():
                    query = query.filter(**{field: search_term})
            if config.get('language'): query = query.filter(language=config.get('language'))
            if config.get('publication_year'): query = query.filter(publication_year=config['publication_year'])
            if config.get('document_types'): query = query.filter(type="|".join(config['document_types']))
            query = query.filter(topics={'id': "|".join(chunk)})
            query = query.sort(publication_date="desc")
            
            # --- НОВОЕ: Считаем количество для каждого чанка ---
            try:
                chunk_count = query.count()
                print(f"    ...найдено {chunk_count} работ.")
                total_available_estimate += chunk_count
            except Exception as count_e:
                print(f"    ...не удалось посчитать работы для этого чанка: {count_e}")
            # ---------------------------------------------------

            select_fields = ['id', 'display_name', 'publication_year', 'publication_date', 'type', 'topics', 'language']
            chunk_results = query.select(select_fields).get(per_page=50) # Запрашиваем щедрое кол-во из каждого

            for paper in chunk_results:
                if paper.get('id') not in seen_ids:
                    all_results_pool.append(paper)
                    seen_ids.add(paper.get('id'))
        
        print(f"\n✅ Все запросы выполнены.")
        print(f"   Примерная оценка общего числа доступных работ (сумма по чанкам): ~{total_available_estimate}")
        print(f"   Всего получено {len(all_results_pool)} уникальных статей от API. Начинаю сортировку и финальную обработку...")

        # --- Локальная сортировка и фильтрация ---
        all_results_pool.sort(key=lambda x: x.get('publication_date', '1900-01-01'), reverse=True)
        
        analyzed_articles = []
        seen_normalized_titles = set()
        fetch_limit = config.get('fetch_limit', 50)

        for paper in all_results_pool:
            title = paper.get('display_name')
            if not title: continue
            
            target_language = config.get('language')
            if target_language and paper.get('language') and paper.get('language') != target_language: continue
            if target_language == 'en' and not is_likely_english(title): continue
            
            normalized = normalize_title(title)
            if normalized in seen_normalized_titles: continue
            seen_normalized_titles.add(normalized)
            
            paper_topics_raw = paper.get('topics', [])
            paper_topics_ids = {normalize_id(t['id']) for t in paper_topics_raw if t and t.get('id')}
            
            analyzed_articles.append({
                'id': paper.get('id'), 'title': title, 'year': paper.get('publication_year'),
                'type': paper.get('type'), 'matched_topics': [t for t in total_topics if t in paper_topics_ids]
            })
            if len(analyzed_articles) >= fetch_limit: break
        
        results_fetched = len(analyzed_articles)
        print(f"   Загружено для анализа (финальных, уникальных, на нужном языке): {results_fetched}")
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_filename = f"debug__{config_name.replace('.yaml', '')}__{timestamp}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump({'analysis_info': {'config_file': config_name, 'timestamp': timestamp, 'total_available_estimate': f"~{total_available_estimate}", 'total_fetched_from_api': len(all_results_pool), 'final_results_count': results_fetched}, 'analyzed_articles': analyzed_articles}, f, indent=2, ensure_ascii=False)
        print(f"📊 Результаты анализа сохранены в файл: {output_filename}")

    except Exception as e:
        print(f"❌ Ошибка во время анализа: {e}")
        import traceback
        traceback.print_exc()

def main():
    print("=== ЗАПУСК ОТЛАДОЧНОГО АНАЛИЗАТОРА (v29, с надежной пакетной обработкой) ===")
    base_config_path = 'sources/_base.yaml'
    try:
        with open(base_config_path, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f) or {}
    except FileNotFoundError: base_config = {}
    
    source_configs = glob("sources/[!_]*.yaml")
    for config_path in source_configs:
        try:
            with open(config_path, 'r', encoding='utf-8') as f: srez_config = yaml.safe_load(f)
            if srez_config and srez_config.get('enabled'):
                final_config = {**base_config, **srez_config}
                final_config['topics'] = list(set(base_config.get('core_topics', []) + srez_config.get('topics', [])))
                final_config['config_path'] = config_path
                analyze_source(final_config)
        except Exception as e: print(f"Не удалось обработать файл конфигурации {config_path}: {e}")

if __name__ == "__main__":
    main()
