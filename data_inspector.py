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
    """Приводит ID к короткому формату (C123) из полного URL."""
    if not openalex_id: return None
    return openalex_id.split('/')[-1]

def normalize_title(title):
    """Приводит название к единому формату для надежного сравнения."""
    if not title: return ""
    return re.sub(r'[^a-z0-9]', '', title.lower())

def analyze_source(config: dict):
    """Выполняет анализ одного источника, используя pyalex, собирает статистику и детальные данные."""
    config_name = os.path.basename(config.get('config_path', 'default.yaml'))
    print(f"\n--- Анализирую источник: {config_name} ---")
    try:
        query = pyalex.Works()
        
        # --- Гибкая система фильтрации ---
        if config.get('search_in_fields'):
            for field, search_term in config['search_in_fields'].items():
                query = query.filter(**{field: search_term})
        
        # Отправляем фильтр по языку, даже если он работает не идеально
        if config.get('language'):
            query = query.filter(language=config.get('language'))
        
        if config.get('publication_year'):
            query = query.filter(publication_year=config['publication_year'])
        if config.get('document_types'): 
            query = query.filter(type="|".join(config['document_types']))
        if config.get('topics'): 
            query = query.filter(topics={'id': "|".join(config['topics'])})
        
        query = query.sort(publication_date="desc")
        total_results_available = query.count()
        print(f"✅ Успешный запрос.")
        print(f"   Всего найдено работ по вашим критериям: {total_results_available}")
        
        fetch_limit = config.get('fetch_limit', 50)
        # Обязательно запрашиваем поле 'language' для нашей проверки
        select_fields = ['id', 'display_name', 'publication_year', 'type', 'topics', 'language']
        # Запрашиваем с запасом (в 3 раза больше), чтобы было из чего фильтровать
        full_results = query.select(select_fields).get(per_page=fetch_limit * 3) 
        
        # --- БЛОК ПОСТ-ФИЛЬТРАЦИИ И ДЕДУПЛИКАЦИИ ---
        analyzed_articles = []
        seen_normalized_titles = set()

        for paper in full_results:
            # 1. "Двойной контроль": финальная проверка языка на нашей стороне
            target_language = config.get('language')
            paper_language = paper.get('language')
            if target_language and paper_language != target_language:
                # Этот print сработает, если API вернул статью не на том языке
                print(f"   -> Пост-фильтр: пропуск статьи на языке '{paper_language}'")
                continue

            # 2. Дедупликация по названию
            title = paper.get('display_name')
            if not title: continue
            normalized = normalize_title(title)
            if normalized in seen_normalized_titles:
                print(f"   -> Дубликат: пропуск статьи '{title[:50]}...'")
                continue
            seen_normalized_titles.add(normalized)
            
            # 3. "Пуленепробиваемая" обработка тем
            paper_topics_raw = paper.get('topics', [])
            paper_topics_ids = set()
            if paper_topics_raw:
                for topic_obj in paper_topics_raw:
                    if isinstance(topic_obj, dict) and topic_obj.get('id'):
                        paper_topics_ids.add(normalize_id(topic_obj.get('id')))
            
            analyzed_articles.append({
                'id': paper.get('id'), 'title': title, 'year': paper.get('publication_year'),
                'type': paper.get('type'), 'matched_topics': [t for t in config.get('topics', []) if t in paper_topics_ids]
            })
            # Прерываем, когда набрали нужное количество статей
            if len(analyzed_articles) >= fetch_limit: break
        # ----------------------------------------------------
        
        results_fetched = len(analyzed_articles)
        print(f"   Загружено для анализа (уникальных, на нужном языке): {results_fetched}")
        
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        output_filename = f"debug__{config_name.replace('.yaml', '')}__{timestamp}.json"
        with open(output_filename, 'w', encoding='utf-8') as f:
            json.dump({'analysis_info': {'config_file': config_name, 'timestamp': timestamp, 'total_results_available': total_results_available, 'results_fetched': results_fetched}, 'analyzed_articles': analyzed_articles}, f, indent=2, ensure_ascii=False)
        print(f"📊 Результаты анализа сохранены в файл: {output_filename}")
    except Exception as e:
        print(f"❌ Ошибка во время анализа: {e}")

def main():
    """Основной цикл анализатора. Теперь с надежной централизованной конфигурацией."""
    print("=== ЗАПУСК ОТЛАДОЧНОГО АНАЛИЗАТОРА (v21, финальная) ===")
    
    # 1. Загружаем базовую конфигурацию
    base_config_path = 'sources/_base.yaml'
    try:
        with open(base_config_path, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        print(f"ПРЕДУПРЕЖДЕНИЕ: Базовый файл конфигурации '{base_config_path}' не найден.")
        base_config = {}

    # 2. Находим все файлы-срезы
    source_configs = glob("sources/[!_]*.yaml")
    for config_path in source_configs:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                srez_config = yaml.safe_load(f)

            if srez_config and srez_config.get('enabled'):
                # 3. --- ИСПРАВЛЕННОЕ СЛИЯНИЕ КОНФИГУРАЦИЙ ---
                # Начинаем с копии базы
                final_config = base_config.copy()
                # Обновляем ее уникальными значениями из файла-среза
                final_config.update(srez_config)
                # Отдельно и правильно объединяем списки тем
                final_config['topics'] = list(set(base_config.get('core_topics', []) + srez_config.get('topics', [])))
                # ---------------------------------------------
                
                final_config['config_path'] = config_path
                analyze_source(final_config)
        except Exception as e:
            print(f"Не удалось обработать файл конфигурации {config_path}: {e}")

if __name__ == "__main__":
    main()
