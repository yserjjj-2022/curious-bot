# -*- coding: utf-8 -*-

import os
import sys
import logging
import re
from pathlib import Path

# --- ПУЛЕНЕПРОБИВАЕМЫЙ БЛОК ИНИЦИАЛИЗАЦИИ ---
script_dir = Path(__file__).resolve().parent
# Определяем корень проекта в зависимости от того, где лежит скрипт
project_root = script_dir if script_dir.name == 'curious-bot' else script_dir.parent
sys.path.insert(0, str(project_root))
from dotenv import load_dotenv
dotenv_path = project_root / '.env'
load_dotenv(dotenv_path=dotenv_path)

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, ApplicationBuilder, ContextTypes, CallbackQueryHandler, CommandHandler
from services.storage_service import StorageService

# --- Настройка ---
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger("TelegramBot")

# --- Переменные окружения ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WORKFLOW_CHANNEL_ID = os.getenv("WORKFLOW_CHANNEL_ID")
PUBLISH_CHANNEL_ID = os.getenv("PUBLISH_CHANNEL_ID")
MODERATION_BATCH_SIZE = int(os.getenv("MODERATION_BATCH_SIZE", 10))

storage = StorageService()

# --- КОНВЕЙЕРЫ (ТРИГГЕРЫ) ---

async def trigger_triage_conveyor(app: Application):
    """Отправляет статьи на ОТСЕВ в РАБОЧИЙ канал."""
    logger.info("Запущен конвейер ОТСЕВА по триггеру...")
    articles = storage.get_articles_by_status('investigated', limit=MODERATION_BATCH_SIZE, random_order=True)
    if not articles:
        logger.info("...статей на отсев не найдено.")
        return
    
    logger.info(f"Отправка {len(articles)} статей на отсев...")
    for article in articles:
        message_text = (
            f"<b>[НА ОТСЕВ]</b>\n\n"
            f"<b>Название:</b> {article.title}\n"
            f"<b>DOI:</b> {article.doi}\n"
            f"<b>Тип контента:</b> <code>{article.content_type}</code>"
        )
        keyboard = [[
            InlineKeyboardButton("✅ Принять", callback_data=f"triage_accept_{article.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"triage_reject_{article.id}"),
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            sent_message = await app.bot.send_message(
                chat_id=WORKFLOW_CHANNEL_ID, 
                text=message_text, 
                parse_mode='HTML',
                reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            storage.update_moderation_message_id(article.id, sent_message.message_id)
            storage.update_article_status(article.id, 'awaiting_triage')
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи на отсев {article.id}: {e}", exc_info=True)

async def trigger_review_conveyor(app: Application):
    """Отправляет статьи на УТВЕРЖДЕНИЕ в РАБОЧИЙ канал."""
    logger.info("Запущен конвейер УТВЕРЖДЕНИЯ по триггеру...")
    articles = storage.get_articles_by_status('awaiting_review', limit=MODERATION_BATCH_SIZE, random_order=True)
    if not articles:
        logger.info("...статей на утверждение не найдено.")
        return
    
    logger.info(f"Отправка {len(articles)} статей на утверждение...")
    for article in articles:
        if not article.moderation_message_id:
            logger.warning(f"У статьи {article.id} нет moderation_message_id, пропускаю.")
            continue
        
        theme_line = f"<b>Тема:</b> {article.theme_name}\n\n" if article.theme_name else ""
        message_text = (
            f"<b>[НА УТВЕРЖДЕНИЕ]</b>\n\n"
            f"{theme_line}"
            f"<b>Название:</b> {article.title}\n\n"
            f"<b>Саммари:</b>\n{article.summary}\n\n"
            f"<b>Источник:</b> {article.doi}"
        )
        keyboard = [[
            InlineKeyboardButton("🚀 Опубликовать", callback_data=f"publish_approve_{article.id}"),
            InlineKeyboardButton("🗑️ В корзину", callback_data=f"publish_reject_{article.id}"),
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await app.bot.edit_message_text(
                chat_id=WORKFLOW_CHANNEL_ID, message_id=article.moderation_message_id,
                text=message_text, parse_mode='HTML', reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            storage.update_article_status(article.id, 'awaiting_publication')
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи на утверждение {article.id}: {e}", exc_info=True)

# --- ОБРАБОТЧИКИ КОМАНД И КНОПОК ---

async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    welcome_message = "Привет, Редактор! Выберите действие:"
    keyboard = [[
        InlineKeyboardButton("✅ Запросить на ОТСЕВ", callback_data="manual_triage"),
        InlineKeyboardButton("🚀 Запросить на УТВЕРЖДЕНИЕ", callback_data="manual_review"),
    ],[
        InlineKeyboardButton("📊 Статус конвейеров", callback_data="show_pipeline_status"),
    ]]
    reply_markup = InlineKeyboardMarkup(keyboard)
    await context.bot.send_message(chat_id=update.effective_chat.id, text=welcome_message, reply_markup=reply_markup)

async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        data = query.data
        if data == "manual_triage":
            await trigger_triage_conveyor(context.application)
            await query.edit_message_text(text="✅ Запрошены статьи на ОТСЕВ. Проверьте рабочий канал.")
        elif data == "manual_review":
            await trigger_review_conveyor(context.application)
            await query.edit_message_text(text="🚀 Запрошены статьи на УТВЕРЖДЕНИЕ. Проверьте рабочий канал.")
        elif data == "show_pipeline_status":
            status_message = "📊 *СТАТУС КОНВЕЙЕРОВ*\n\n"
            all_statuses = ['new', 'investigated', 'awaiting_triage', 'triage_rejected',
                            'awaiting_parsing', 'awaiting_abstract_summary', 'extraction_failed',
                            'awaiting_review', 'awaiting_publication', 'review_rejected', 'published']
            for status in all_statuses:
                count = storage.get_article_count_by_status(status)
                status_message += f"• `{status}`: {count} статей\n"
            await query.edit_message_text(text=status_message, parse_mode='Markdown')
        else:
            parts = data.split('_')
            prefix, action, article_id = parts[0], parts[1], "_".join(parts[2:])

            if prefix == "triage":
                if action == "accept":
                    article = storage.get_article_by_id(article_id)
                    if not article: return
                    next_status = 'awaiting_parsing' if article.content_type == 'pdf' else 'awaiting_abstract_summary'
                    storage.update_article_status(article.id, next_status)
                    await query.edit_message_text(text=f"✅ <b>ПРИНЯТО.</b>\nСтатья отправлена на этап: `{next_status}`", parse_mode='HTML')
                elif action == "reject":
                    storage.update_article_status(article_id, 'triage_rejected')
                    await query.edit_message_text(text="❌ <b>ОТКЛОНЕНО.</b>", parse_mode='HTML')
                    
            elif prefix == "publish":
                article = storage.get_article_by_id(article_id)
                if not article: return
                if action == "approve":
                    hashtag = f"#{re.sub(r'[^a-zA-Z0-9а-яА-Я_]', '', article.theme_name.replace(' ', '_'))}" if article.theme_name else ""
                    final_post = (f"{hashtag}\n\n" if hashtag else "") + \
                                 f"<b>{article.title}</b>\n\n" + \
                                 f"{article.summary}\n\n" + \
                                 f"<a href='{article.doi}'>Источник</a>"
                    await context.bot.send_message(chat_id=PUBLISH_CHANNEL_ID, text=final_post, parse_mode='HTML', disable_web_page_preview=False)
                    storage.update_article_status(article.id, 'published')
                    await query.edit_message_text(text=f"🚀 <b>ОПУБЛИКОВАНО</b>", parse_mode='HTML')
                elif action == "reject":
                    storage.update_article_status(article_id, 'review_rejected')
                    await query.edit_message_text(text="🗑️ <b>ОТПРАВЛЕНО В КОРЗИНУ.</b>", parse_mode='HTML')
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}", exc_info=True)

# --- ГЛАВНАЯ ФУНКЦИЯ ЗАПУСКА ---
def run_telegram_bot():
    logger.info("Запуск Telegram-бота...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CommandHandler(["start", "menu"], start_command))
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    logger.info("Бот запущен и готов к работе.")
    application.run_polling()

if __name__ == '__main__':
    run_telegram_bot()
