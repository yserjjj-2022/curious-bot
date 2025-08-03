# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from dotenv import load_dotenv

# --- Надежная загрузка .env и настройка импортов ---
project_root = Path(__file__).resolve().parent.parent
sys.path.append(str(project_root))
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)
print(f"Загрузка переменных окружения из: {dotenv_path}")

# Импортируем наш сервис
from services.summarization_service import GigaChatSummarizer

SAMPLE_ABSTRACT = """
This study investigates the impact of personalized financial advice, delivered through a mobile application, on the saving behavior of young adults in Germany. We conducted a randomized controlled trial (RCT) with a sample of 1,500 individuals aged 18-25. The treatment group received AI-driven nudges and personalized saving goals, while the control group used a standard budgeting app. Our findings indicate that personalized interventions significantly increased the average monthly savings rate by 15% compared to the control group. Furthermore, we observe that the effect is most pronounced among individuals with lower initial financial literacy. The results suggest that technology-driven behavioral interventions can be a powerful tool for improving financial capability among the youth.
"""

def run_test():
    """Основная функция для тестирования GigaChatSummarizer."""
    print("=== ЗАПУСК ТЕСТА ДЛЯ GIGACHAT SUMMARIZER (КАЧЕСТВЕННЫЙ ВЫВОД) ===")
    
    try:
        summarizer = GigaChatSummarizer()
        print("✅ Сервис успешно инициализирован.")
    except Exception as e:
        print(f"❌ ПРОВАЛ: {e}")
        return

    print("\n--- Оригинальная аннотация (на английском) ---")
    print(SAMPLE_ABSTRACT)
    
    print("\n--- Запрос на стилизованную суммаризацию ---")
    summary = summarizer.summarize_abstract(SAMPLE_ABSTRACT)

    if summary:
        print("\n✅ УСПЕХ: Получена выжимка:")
        print("=" * 40)
        print(summary)
        print("=" * 40)
    else:
        print("\n❌ ПРОВАЛ: Выжимка не была получена. Проверьте лог на наличие ошибок API.")

    print("\n=== ТЕСТ ЗАВЕРШЕН ===")

if __name__ == "__main__":
    run_test()
