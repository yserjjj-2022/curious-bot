# agents/summary_agent.py

import os
import sys
from pathlib import Path

# --- Блок инициализации ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
from dotenv import load_dotenv
load_dotenv()

# --- ИЗМЕНЕНИЕ: Импортируем АГРЕССИВНУЮ функцию очистки ---
from services.storage_service import StorageService
from services.summarization_service import AdvancedSummarizer
from services.text_utils import cleanup_summary_text

# --- Настройки из .env ---
SUMMARY_BATCH_SIZE = int(os.getenv("SUMMARY_BATCH_SIZE", 30))

def run_summary_cycle(storage: StorageService):
    """
    Основной цикл агента-суммаризатора.
    """
    print(f"=== ЗАПУСК АГЕНТА-СУММАРИЗАТОРА (v-final-3-step-editor) ===")
    summarizer = AdvancedSummarizer()
    prompt_dir = project_root / 'prompts'
    try:
        with open(prompt_dir / 'summary_abstract_style_prompt.txt', 'r', encoding='utf-8') as f: abstract_prompt = f.read()
        with open(prompt_dir / 'step1_extraction_prompt.txt', 'r', encoding='utf-8') as f: extraction_prompt = f.read()
        with open(prompt_dir / 'step2_synthesis_prompt.txt', 'r', encoding='utf-8') as f: synthesis_prompt = f.read()
        with open(prompt_dir / 'step3_refinement_prompt.txt', 'r', encoding='utf-8') as f: refinement_prompt = f.read()
    except FileNotFoundError as e:
        print(f"КРИТИЧЕСКАЯ ОШИБКА: {e}"); return
    
    statuses_to_find = ['awaiting_full_summary', 'awaiting_abstract_summary']
    articles = storage.get_articles_by_status(statuses_to_find, limit=SUMMARY_BATCH_SIZE)
    if not articles: print("...статей для суммаризации не найдено."); return
    print(f"Найдено {len(articles)} статей для суммаризации...")

    for article in articles:
        print(f"\\n-> Обрабатываю: {article.title[:60]}...")
        storage.update_article_status(article.id, 'summary_in_progress')
        theme = article.theme_name or "Общие финансы"
        summary = None
        
        if article.status == 'awaiting_full_summary' and article.full_text:
            summary = summarizer.summarize_full_text(
                article.full_text, extraction_prompt, synthesis_prompt, refinement_prompt
            )
        elif article.status == 'awaiting_abstract_summary' and article.original_abstract:
            summary = summarizer.summarize_abstract(article.original_abstract, abstract_prompt, theme)
        
        if summary:
            # --- ИЗМЕНЕНИЕ: Используем АГРЕССИВНУЮ функцию очистки ---
            cleaned_summary = cleanup_summary_text(summary)
            print(f"  ✅ Получена выжимка длиной {len(cleaned_summary)} символов.")
            storage.update_article_summary(article.id, cleaned_summary)
            storage.update_article_status(article.id, 'summarized')
        else:
            print("  ❌ Не удалось получить выжимку.")
            storage.update_article_status(article.id, 'summary_failed')
    
    print("\n=== РАБОТА АГЕНТА-СУММАРИЗАТОРА ЗАВЕРШЕНА ===")

if __name__ == "__main__":
    storage_instance = StorageService()
    run_summary_cycle(storage_instance)

