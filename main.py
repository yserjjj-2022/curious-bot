# -*- coding: utf-8 -*-

import os
import yaml
from glob import glob
import time

# Импортируем наши новые, профессиональные сервисы
from services.openalex_fetcher import OpenAlexFetcher
from services.storage_service import StorageService

def run_main_cycle():
    """
    Основной рабочий цикл приложения.
    Загружает конфигурации, получает данные и сохраняет их в базу.
    """
    print("=== ЗАПУСК ОСНОВНОГО ЦИКЛА СБОРА ДАННЫХ ===")
    
    # 1. Инициализация сервисов
    # Создаем по одному экземпляру каждого сервиса, которые будем переиспользовать
    fetcher = OpenAlexFetcher()
    storage = StorageService(db_url='sqlite:///data/articles.db') # Используем рабочую БД
    print("Сервисы Fetcher и Storage инициализированы.")

    # 2. Загрузка конфигураций
    base_config_path = 'sources/_base.yaml'
    try:
        with open(base_config_path, 'r', encoding='utf-8') as f:
            base_config = yaml.safe_load(f) or {}
    except FileNotFoundError:
        base_config = {}
    
    source_configs = glob("sources/[!_]*.yaml")
    print(f"Найдено {len(source_configs)} файлов-срезов для обработки.")

    # 3. Основной цикл по файлам-конфигурациям
    for config_path in source_configs:
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                srez_config = yaml.safe_load(f)

            if not (srez_config and srez_config.get('enabled')):
                continue # Пропускаем отключенные файлы

            # Объединяем базовую и конкретную конфигурации
            final_config = {**base_config, **srez_config}
            final_config['topics'] = list(set(base_config.get('core_topics', []) + srez_config.get('topics', [])))
            
            config_name = os.path.basename(config_path)
            print(f"\n--- Обрабатываю источник: {config_name} ---")

            # 4. Получение статей через Fetcher
            articles_to_process = fetcher.fetch_articles(final_config)
            
            if not articles_to_process:
                print("   -> Новых статей для этого источника не найдено.")
                continue

            # 5. Сохранение статей через Storage
            newly_added_count = 0
            for article_meta in articles_to_process:
                # ВАЖНО: Пока у нас нет сервиса суммаризации, мы используем заглушку.
                # В будущем здесь будет вызов SummarizationService.
                summary_placeholder = "Summary will be generated later."
                
                was_added = storage.add_article(article_meta, summary_placeholder)
                if was_added:
                    newly_added_count += 1
            
            print(f"   -> Успешно добавлено {newly_added_count} новых статей в базу данных.")

        except Exception as e:
            print(f"❌ Ошибка при обработке файла {config_path}: {e}")
    
    print("\n=== ОСНОВНОЙ ЦИКЛ СБОРА ДАННЫХ ЗАВЕРШЕН ===")

if __name__ == "__main__":
    run_main_cycle()

