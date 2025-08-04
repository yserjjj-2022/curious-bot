# Файл: agents/summary_agent.py
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
# Мы оставляем ее здесь, чтобы другие агенты могли ее импортировать
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

def run_summary_cycle():
    """Основной цикл работы "Агента-Суммаризатора"."""
    print("=== ЗАПУСК АГЕНТА-СУММАРИЗАТОРА (Финальная версия) ===")
    storage = StorageService()
    giga = GigaService()

    prompt_dir = project_root / 'prompts'
    try:
        with open(prompt_dir / 'summary_news_style_prompt.txt', 'r', encoding='utf-8') as f:
            full_summary_prompt = f.read()
        with open(prompt_dir / 'summary_abstract_style_prompt.txt', 'r', encoding='utf-8') as f:
            abstract_summary_prompt = f.read()
        print("Шаблоны промптов для обоих конвейеров успешно загружены.")
    except FileNotFoundError as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: Не найден файл с промптом: {e}")
        sys.exit(1)
    
    while True:
        print("\nИщу статьи для суммаризации...")
        statuses_to_find = ['awaiting_full_summary', 'awaiting_abstract_summary']
        articles = storage.get_articles_by_status(statuses_to_find, limit=1)
        
        if not articles:
            print("...статей для обработки не найдено. Пауза 60 секунд.")
            time.sleep(60)
            continue

        article = articles[0]
        print(f"\n-> Обрабатываю статью: {article.title[:60]} (Статус: {article.status})")
        
        if article.status == 'awaiting_full_summary':
            prompt_template = full_summary_prompt
            # Просто берем текст, он УЖЕ должен быть очищен Экстрактором
            text_to_process = article.full_text
            print("   Выбран конвейер: Полный текст.")
        else: # awaiting_abstract_summary
            prompt_template = abstract_summary_prompt
            text_to_process = article.original_abstract
            print("   Выбран конвейер: Аннотация.")

        if not text_to_process or len(text_to_process) < 50:
            print("  -> Текст отсутствует или слишком короткий. Пропускаю.")
            storage.update_article_status(article.id, 'summary_failed_no_text')
            continue

        final_prompt = prompt_template.format(article_text=text_to_process[:20000])
        
        print("   Отправляю запрос в GigaChat...")
        summary = giga.get_completion(final_prompt)

        if summary:
            print(f"  ✅ Получена выжимка длиной {len(summary)} символов.")
            storage.update_article_summary(article.id, summary)
            storage.update_article_status(article.id, 'awaiting_review')
            print(f"   -> Выжимка сохранена. Статус изменен на 'awaiting_review'.")
        else:
            print("  -> Не удалось получить выжимку от GigaChat.")
            storage.update_article_status(article.id, 'summary_failed_api_error')
        
        print("\nЦикл суммаризации завершен. Пауза 30 секунд...")
        time.sleep(30)

if __name__ == "__main__":
    run_summary_cycle()
