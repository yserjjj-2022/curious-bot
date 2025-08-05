# -*- coding: utf-8 -*-

import os
import sys
import yaml
from pathlib import Path
import json

# --- Блок инициализации ---
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))
from dotenv import load_dotenv
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- Правильные импорты наших сервисов ---
from services.openalex_fetcher import OpenAlexFetcher
from services.storage_service import StorageService

def run_collection_cycle():
    """Основной цикл работы "Агента-Сборщика"."""
    print("=== ЗАПУСК ЦИКЛА СБОРА ДАННЫХ (АГЕНТ-СБОРЩИК) ===")
    
    fetcher = OpenAlexFetcher()
    storage = StorageService()
    print("Сервисы Fetcher и Storage инициализированы.")
    
    source_files = sorted([f for f in os.listdir('sources') if f.endswith('.yaml')])
    print(f"Найдено {len(source_files)} файлов-срезов для обработки.")
    
    for source_file in source_files:
        print(f"\n--- Обрабатываю срез: {source_file} ---")
        try:
            # Загружаем конфигурацию среза
            with open(f"sources/{source_file}", 'r', encoding='utf-8') as f:
                slice_config = yaml.safe_load(f)

            # Извлекаем "человеческое" имя темы из файла
            theme_name_from_file = slice_config.get("theme_name", "Без темы")
            print(f"Тематический срез: '{theme_name_from_file}'")

            # Получаем "сырые" данные от фетчера
            raw_articles = fetcher.fetch_articles(slice_config)
            
            if not raw_articles:
                print("   -> Для данного среза не найдено новых статей, готовых к добавлению.")
                continue

            # Преобразуем "сырые" данные под нашу модель в базе данных
            added_count = 0
            for raw_article in raw_articles:
                article_data_to_store = {
                    'id': raw_article.get('id'),
                    'title': raw_article.get('display_name'),
                    'source_name': 'OpenAlex',
                    'status': 'new',
                    'content_type': raw_article.get('content_type'),
                    'content_url': raw_article.get('content_url'),
                    'doi': raw_article.get('doi'),
                    'year': raw_article.get('publication_year'),
                    'type': raw_article.get('type'),
                    'language': raw_article.get('language'),
                    'original_abstract': raw_article.get('abstract'),
                    # Передаем наш тег (имя темы) в базу
                    'theme_name': theme_name_from_file,
                    # Сохраняем все "сырые" метаданные как строку JSON для будущих нужд
                    'full_metadata': json.dumps(raw_article) 
                }
                
                # Используем правильное имя аргумента `article_data`
                if storage.add_article(article_data=article_data_to_store):
                    added_count += 1
            
            print(f"  ✅ Успешно добавлено {added_count} новых статей в базу по теме '{theme_name_from_file}'.")

        except Exception as e:
            print(f"❌ Ошибка при обработке файла {source_file}: {e}")

    print("\n=== ЦИКЛ СБОРА ДАННЫХ ЗАВЕРШЕН ===")

if __name__ == '__main__':
    run_collection_cycle()
