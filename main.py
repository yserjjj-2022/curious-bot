# main.py (полностью обновленная версия)

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

# --- ИЗМЕНЕНО: Импортируем оба наших фетчера ---
from services.openalex_fetcher import OpenAlexFetcher
from services.arxiv_fetcher import ArxivFetcher # <-- НОВЫЙ ИМПОРТ
from services.storage_service import StorageService

def run_collection_cycle(storage: StorageService, initial_load: bool = False, limit_per_theme: int = 50):
    """
    Основной цикл работы "Агента-Сборщика".
    Теперь может работать с разными источниками (OpenAlex, arXiv).
    """
    print("=== ЗАПУСК ЦИКЛА СБОРА ДАННЫХ (АГЕНТ-СБОРЩИК) ===")
    
    # --- ИЗМЕНЕНО: Создаем экземпляры всех доступных фетчеров ---
    fetchers = {
        'openalex': OpenAlexFetcher(),
        'arxiv': ArxivFetcher()
    }
    print("Сервисы Fetcher и Storage инициализированы.")
    
    source_files = sorted([f for f in os.listdir('sources') if f.endswith('.yaml')])
    print(f"Найдено {len(source_files)} файлов-срезов для обработки.")
    
    for source_file in source_files:
        print(f"\n--- Обрабатываю срез: {source_file} ---")
        try:
            with open(f"sources/{source_file}", 'r', encoding='utf-8') as f:
                slice_config = yaml.safe_load(f)

            # --- ИЗМЕНЕНО: Определяем, какой фетчер использовать ---
            source_type = slice_config.get('source_type', 'openalex').lower()
            fetcher = fetchers.get(source_type)
            
            if not fetcher:
                print(f"   ❌ Неизвестный тип источника '{source_type}'. Пропускаю.")
                continue

            slice_config['fetch_limit'] = limit_per_theme
            
            # Логика для первоначальной заливки (применима только к OpenAlex)
            if initial_load and source_type == 'openalex':
                slice_config['publication_year'] = '>=2025'
                print(f"   [Режим первоначальной заливки] -> Ищем статьи с 2025 года.")

            theme_name_from_file = slice_config.get("theme_name", "Без темы")
            print(f"Тематический срез: '{theme_name_from_file}' (Источник: {source_type.upper()})")

            # Получаем "сырые" данные от выбранного фетчера
            raw_articles = fetcher.fetch_articles(slice_config)
            
            if not raw_articles:
                print("   -> Для данного среза не найдено новых статей, готовых к добавлению.")
                continue

            added_count = 0
            enriched_count = 0
            for raw_article in raw_articles:
                # --- ИЗМЕНЕНО: Адаптируем маппинг данных ---
                # Теперь `add_article` сама разберется, что делать
                result = storage.add_article(article_data=raw_article, theme_name=theme_name_from_file)
                if result == "added":
                    added_count += 1
                elif result == "enriched":
                    enriched_count += 1
            
            print(f"  ✅ По теме '{theme_name_from_file}': добавлено {added_count} новых статей, обогащено {enriched_count}.")

        except Exception as e:
            print(f"❌ Ошибка при обработке файла {source_file}: {e}")

    print("\n=== ЦИКЛ СБОРА ДАННЫХ ЗАВЕРШЕН ===")


if __name__ == '__main__':
    print("--- Запуск Сборщика в режиме ручной отладки ---")
    storage_instance = StorageService()
    run_collection_cycle(storage_instance, initial_load=False, limit_per_theme=10)
