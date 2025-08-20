# conductor.py

import os
import sys
import time
import logging
import threading
from pathlib import Path
from dotenv import load_dotenv

# --- Инициализация проекта ---
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))
load_dotenv()

from apscheduler.schedulers.blocking import BlockingScheduler

# --- Импортируем наших агентов и сервисы ---
from main import run_collection_cycle
# --- ИЗМЕНЕНИЕ: Импортируем наш новый сервис ---
from services.oecd_data_service import OECDDataService
from agents.content_extractor_agent import run_extraction_cycle
from agents.summary_agent import run_summary_cycle
from telegram_bot import run_telegram_bot

from services.storage_service import StorageService

# --- Настройка ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger("Conductor")

# --- Читаем настройки из .env ---
MODE = os.getenv("MODE", "TRAINING").upper()
FETCH_LIMIT_TRAINING = int(os.getenv("FETCH_LIMIT_TRAINING", 50))
FETCH_LIMIT_INITIAL = int(os.getenv("FETCH_LIMIT_INITIAL", 200))
FETCH_LIMIT_DAILY = int(os.getenv("FETCH_LIMIT_DAILY", 50))

# ==============================================================================
# --- ЛОГИКА ДЛЯ УЧЕБНОГО РЕЖИМА (TRAINING) ---
# ==============================================================================
def run_training_mode():
    """Запускает один полный сквозной прогон для быстрой отладки."""
    logger.info(">>> ЗАПУСК В УЧЕБНОМ РЕЖИМЕ <<<")
    
    storage = StorageService()

    choice = input("Очистить базу данных для нового учебного прогона? (y/n): ").lower()
    if choice == 'y':
        logger.info("Очистка базы данных...")
        db_path = 'data/articles.db'
        if os.path.exists(db_path):
            os.remove(db_path)
        storage = StorageService() # Пересоздаем инстанс и саму БД
        logger.info("База данных очищена.")

    # --- ИЗМЕНЕНИЕ: Добавлен этап сбора данных из OECD ---
    logger.info("--- Этап 1.1: Сбор данных из OECD API ---")
    oecd_service = OECDDataService(storage)
    oecd_service.run_ingestion()
    
    logger.info("--- Этап 1.2: Сбор статей из YAML-источников ---")
    run_collection_cycle(storage, initial_load=False, limit_per_theme=FETCH_LIMIT_TRAINING)
    
    logger.info("--- Этап 2: Извлечение контента ---")
    run_extraction_cycle(storage)

    logger.info("--- Этап 3: Суммаризация ---")
    # run_summary_cycle(storage)
    
    logger.info(">>> УЧЕБНЫЙ ПРОГОН ЗАВЕРШЕН <<<")
    logger.info("Статьи готовы к утверждению. Запустите Telegram-бота отдельно или используйте ручные команды.")

# ==============================================================================
# --- ЛОГИКА ДЛЯ ПОЛНОГО РЕЖИМА (PRODUCTION) ---
# ==============================================================================
def run_production_mode():
    """Запускает систему в боевом, долгоживущем режиме с задачами по расписанию."""
    logger.info(">>> ЗАПУСК В ПОЛНОМ (БОЕВОМ) РЕЖИМЕ <<<")
    storage = StorageService()

    # Проверяем, нужно ли провести первоначальную заливку
    article_count = storage.get_article_count_by_status('new') + storage.get_article_count_by_status('new_from_source')
    if article_count == 0:
        choice = input("База данных пуста. Провести первоначальную 'массовую' заливку? (y/n): ").lower()
        if choice == 'y':
            logger.info("Начинаю первоначальную заливку из OECD...")
            oecd_service = OECDDataService(storage)
            oecd_service.run_ingestion()
            
            logger.info(f"Начинаю первоначальную заливку из YAML с лимитом {FETCH_LIMIT_INITIAL} на тему...")
            run_collection_cycle(storage, initial_load=True, limit_per_theme=FETCH_LIMIT_INITIAL)
            logger.info("Первоначальная заливка завершена.")
    
    scheduler = BlockingScheduler(timezone="Europe/Moscow")
    
    # 1. Ежедневный сбор новых статей из YAML
    scheduler.add_job(run_collection_cycle, 'cron', hour=3, minute=0, args=[StorageService(), False, FETCH_LIMIT_DAILY], name="Daily_YAML_Collection")
    
    # --- ИЗМЕНЕНИЕ: Добавлена новая задача для сбора данных из OECD ---
    # Запускаем его чуть позже, чтобы не было конфликтов
    scheduler.add_job(OECDDataService(StorageService()).run_ingestion, 'cron', hour=4, minute=0, name="Daily_OECD_Ingestion")
    
    # 2. Регулярная обработка накопившихся статей
    scheduler.add_job(run_extraction_cycle, 'interval', minutes=15, args=[StorageService()], name="Extraction_Cycle")
    scheduler.add_job(run_summary_cycle, 'interval', minutes=15, args=[StorageService()], name="Summary_Cycle")
    
    logger.info("Запуск Telegram-бота в фоновом режиме...")
    bot_thread = threading.Thread(target=run_telegram_bot, daemon=True)
    bot_thread.start()
    
    logger.info("Планировщик настроен. Оркестратор переходит в режим ожидания. Нажмите Ctrl+C для выхода.")
    try:
        scheduler.start()
    except (KeyboardInterrupt, SystemExit):
        logger.info("Оркестратор остановлен.")

# ==============================================================================
# --- ГЛАВНАЯ ТОЧКА ВХОДА ---
# ==============================================================================
if __name__ == '__main__':
    os.makedirs('data', exist_ok=True)
    os.makedirs('sources', exist_ok=True)
    
    if MODE == 'TRAINING':
        run_training_mode()
    elif MODE == 'PRODUCTION':
        run_production_mode()
    else:
        logger.error(f"Неизвестный режим работы: {MODE}. Укажите 'TRAINING' или 'PRODUCTION' в .env файле.")
