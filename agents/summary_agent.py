# -*- coding: utf-8 -*-

import os
import sys
import time
import re
from pathlib import Path

# --- Блок инициализации ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
from dotenv import load_dotenv
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)

# --- Импорты наших модулей ---
from services.storage_service import StorageService
from services.giga_service import GigaService

# --- УТИЛИТАРНАЯ ФУНКЦИЯ ---
def cleanup_text(text: str) -> str:
    """Отсекает "хвост" из ссылок и прочего мусора."""
    if not text:
        return ""
    stop_words = [
        'References', 'Bibliography', 'Data availability statement',
        'Ethics statement', 'Author contributions', 'Funding',
        'Conflict of interest', 'Supplementary material', 'Publisher’s note'
    ]
    pattern = re.compile(r'\b(' + '|'.join(stop_words) + r')\b', re.IGNORECASE)
    match = pattern.search(text)
    
    if match:
        return text[:match.start()]
    return text

# --- НОВАЯ ГЛАВНАЯ ФУНКЦИЯ ДЛЯ ОРКЕСТРАТОРА ---
def run_summary_cycle(storage: StorageService):
    """
    Запускается "Дирижером", обрабатывает ВСЕ статьи, ожидающие суммаризации,
    и завершает свою работу.
    """
    print("=== ЗАПУСК АГЕНТА-СУММАРИЗАТОРА ===")
    # storage = StorageService()
    giga = GigaService()

    # Загружаем шаблоны промптов
    prompt_dir = project_root / 'prompts'
    try:
        with open(prompt_dir / 'summary_news_style_prompt.txt', 'r', encoding='utf-8') as f:
            full_summary_prompt = f.read()
        with open(prompt_dir / 'summary_abstract_style_prompt.txt', 'r', encoding='utf-8') as f:
            abstract_summary_prompt = f.read()
    except FileNotFoundError as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Не найден файл с промптом: {e}")
        return
    
    statuses_to_find = ['awaiting_full_summary', 'awaiting_abstract_summary']
    articles_to_process = storage.get_articles_by_status(statuses_to_find, limit=1000)
        
    if not articles_to_process:
        print("...статей для суммаризации не найдено.")
        print("=== РАБОТА АГЕНТА-СУММАРИЗАТОРА ЗАВЕРШЕНА ===")
        return

    print(f"Найдено {len(articles_to_process)} статей для суммаризации. Начинаю обработку...")

    for article in articles_to_process:
        print(f"\n-> Обрабатываю статью: {article.title[:60]}... (Статус: {article.status})")
        
        theme = article.theme_name or "Общие финансы"
        
        if article.status == 'awaiting_full_summary':
            prompt_template = full_summary_prompt
            text_to_process = article.full_text
        else: # awaiting_abstract_summary
            prompt_template = abstract_summary_prompt
            text_to_process = article.original_abstract

        if not text_to_process or len(text_to_process) < 50:
            print("  -> Текст отсутствует или слишком короткий. Пропускаю.")
            storage.update_article_status(article.id, 'summary_failed_no_text')
            continue
        
        final_prompt = prompt_template.format(
            article_text=text_to_process[:20000],
            theme_name=theme 
        )
        
        print(f"   Отправляю промпт в GigaChat (Тема: '{theme}')...")
        summary = giga.get_completion(final_prompt)

        if summary:
            print(f"  ✅ Получена выжимка длиной {len(summary)} символов.")
            storage.update_article_summary(article.id, summary)
            storage.update_article_status(article.id, 'awaiting_review')
            print(f"   -> Выжимка сохранена. Статус изменен на 'awaiting_review'.")
        else:
            print("  -> Не удалось получить выжимку от GigaChat.")
            storage.update_article_status(article.id, 'summary_failed_api_error')
    
    print(f"\nОбработано {len(articles_to_process)} статей.")
    print("=== РАБОТА АГЕНТА-СУММАРИЗАТОРА ЗАВЕРШЕНА ===")


if __name__ == "__main__":
    # Для ручного запуска создаем собственный экземпляр StorageService
    print("--- Запуск Суммаризатора в режиме ручной отладки ---")
    storage_instance = StorageService()
    run_summary_cycle(storage_instance)
