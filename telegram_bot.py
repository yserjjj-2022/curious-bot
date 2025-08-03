# telegram_bot.py
# -*- coding: utf-8 -*-

import os
import logging
from pathlib import Path
from dotenv import load_dotenv
from telegram import Update
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler

from services.storage_service import StorageService

# Надежная загрузка .env файла
env_path = Path(__file__).resolve().parent / '.env'
load_dotenv(dotenv_path=env_path)
print(f"Загрузка переменных окружения из: {env_path}")

# Настройка логирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)

# --- Обработчики команд ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет приветственное сообщение при команде /start."""
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text="Привет! Я Curious Bot. Используйте команду /get_latest N, чтобы получить последние N статей."
    )

async def get_latest(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Отправляет N последних статей из базы данных."""
    try:
        # --- ИСПРАВЛЕНИЕ: Правильная обработка аргументов ---
        # Проверяем, есть ли аргументы, и берем первый, если он существует.
        # Иначе используем значение по умолчанию (5).
        if context.args and len(context.args) > 0:
            limit = int(context.args[0])
        else:
            limit = 5
        # ----------------------------------------------------

        # Проверяем, что число находится в разумных пределах
        if not (1 <= limit <= 20):
            await context.bot.send_message(chat_id=update.effective_chat.id, text="Пожалуйста, укажите число от 1 до 20.")
            return

        storage = StorageService()
        articles = storage.get_latest_articles(limit=limit)

        if not articles:
            await context.bot.send_message(chat_id=update.effective_chat.id, text="В базе данных пока нет статей.")
            return

        # Формируем и отправляем сообщение для каждой статьи
        for article in articles:
            text_to_show = article.get('original_abstract') or article.get('summary', '')
            
            if text_to_show and len(text_to_show) > 800:
                 text_to_show = text_to_show[:800] + "..."

            source_display = article.get('source_name', 'Неизвестный источник')
            channel_signature = f"Источник: {source_display} | ✒️ *Curious Bot*"

            message_text = (
                f"*{article['title']}* ({article['year']})\n\n"
                f"{text_to_show}\n\n"
                f"[Читать полностью]({article['url']})\n\n"
                f"_{channel_signature}_"
            )
            await context.bot.send_message(
                chat_id=update.effective_chat.id,
                text=message_text,
                parse_mode='Markdown'
            )

    except (IndexError, ValueError):
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Использование: /get_latest <число_статей>")
    except Exception as e:
        logging.error(f"Ошибка при обработке /get_latest: {e}")
        await context.bot.send_message(chat_id=update.effective_chat.id, text="Произошла ошибка при получении статей.")


if __name__ == '__main__':
    TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
    if not TOKEN:
        raise ValueError("Не найден TELEGRAM_BOT_TOKEN! Проверьте, что файл .env существует и путь к нему верен.")

    application = ApplicationBuilder().token(TOKEN).build()
    
    start_handler = CommandHandler('start', start)
    get_latest_handler = CommandHandler('get_latest', get_latest)
    
    application.add_handler(start_handler)
    application.add_handler(get_latest_handler)
    
    print("Бот запущен и готов к работе...")
    application.run_polling()
