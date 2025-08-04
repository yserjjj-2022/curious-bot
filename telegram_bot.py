# -*- coding: utf-8 -*-

import os
import sys
import logging
from dotenv import load_dotenv

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ApplicationBuilder, ContextTypes, CallbackQueryHandler

from services.storage_service import StorageService

# --- Настройка ---
load_dotenv()
logging.basicConfig(format='%(asctime)s - %(name)s - %(levelname)s - %(message)s', level=logging.INFO)
logger = logging.getLogger(__name__)

# --- Переменные окружения ---
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
WORKFLOW_CHANNEL_ID = os.getenv("WORKFLOW_CHANNEL_ID")
PUBLISH_CHANNEL_ID = os.getenv("PUBLISH_CHANNEL_ID")

if not all([TELEGRAM_BOT_TOKEN, WORKFLOW_CHANNEL_ID, PUBLISH_CHANNEL_ID]):
    logger.error("КРИТИЧЕСКАЯ ОШИБКА: Не все переменные окружения заданы!")
    sys.exit(1)

storage = StorageService()

# --- Конвейеры (остаются без изменений) ---
async def triage_conveyor_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запущен конвейер ОТСЕВА...")
    articles = storage.get_articles_by_status('investigated', limit=5)
    if not articles: return
    for article in articles:
        message_text = (f"<b>[НА ОТСЕВ]</b>\n\n<b>Название:</b> {article.title}\n"
                        f"<b>DOI:</b> {article.doi}\n<b>Тип контента:</b> <code>{article.content_type}</code>")
        keyboard = [[
            InlineKeyboardButton("✅ Принять", callback_data=f"triage_accept_{article.id}"),
            InlineKeyboardButton("❌ Отклонить", callback_data=f"triage_reject_{article.id}"),
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            sent_message = await context.bot.send_message(
                chat_id=WORKFLOW_CHANNEL_ID, text=message_text, parse_mode='HTML',
                reply_markup=reply_markup, disable_web_page_preview=True
            )
            storage.update_moderation_message_id(article.id, sent_message.message_id)
            storage.update_article_status(article.id, 'awaiting_triage')
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи на отсев: {e}", exc_info=True)

async def review_conveyor_job(context: ContextTypes.DEFAULT_TYPE):
    logger.info("Запущен конвейер УТВЕРЖДЕНИЯ...")
    articles = storage.get_articles_by_status('awaiting_review', limit=5)
    if not articles: return
    for article in articles:
        if not article.moderation_message_id:
            logger.warning(f"У статьи {article.id} нет message_id, пропускаю.")
            continue
        message_text = (f"<b>[НА УТВЕРЖДЕНИЕ]</b>\n\n"
                        f"<b>Название:</b> {article.title}\n\n"
                        f"<b>Саммари:</b>\n{article.summary}\n\n<b>Источник:</b> {article.doi}")
        keyboard = [[
            InlineKeyboardButton("🚀 Опубликовать", callback_data=f"publish_approve_{article.id}"),
            InlineKeyboardButton("🗑️ В корзину", callback_data=f"publish_reject_{article.id}"),
        ]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        try:
            await context.bot.edit_message_text(
                chat_id=WORKFLOW_CHANNEL_ID, message_id=article.moderation_message_id,
                text=message_text, parse_mode='HTML', reply_markup=reply_markup,
                disable_web_page_preview=True
            )
            storage.update_article_status(article.id, 'awaiting_publication')
        except Exception as e:
            logger.error(f"Ошибка при отправке статьи на утверждение: {e}", exc_info=True)

# --- Обработчик всех кнопок (финальная, исправленная версия) ---
async def button_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    try:
        parts = query.data.split('_')
        prefix, action, article_id = parts[0], parts[1], "_".join(parts[2:])

        # --- ИСПРАВЛЕНИЕ: Используем правильный атрибут text_html ---
        original_message_html = query.message.text_html

        def get_title_from_message(message_html: str) -> str:
            lines = message_html.split('\n')
            for line in lines:
                if "<b>Название:</b>" in line:
                    return line.strip()
            return "Название не найдено"

        if prefix == "triage":
            if action == "accept":
                article = storage.get_article_by_id(article_id)
                next_status = 'awaiting_parsing' if article.content_type == 'pdf' else 'awaiting_abstract_summary'
                storage.update_article_status(article.id, next_status)
                await query.edit_message_text(text=f"✅ <b>ПРИНЯТО.</b>\nСтатья отправлена на этап: `{next_status}`\n\n{original_message_html}", parse_mode='HTML', reply_markup=None)
            elif action == "reject":
                storage.update_article_status(article_id, 'triage_rejected')
                article_title = get_title_from_message(original_message_html)
                await query.edit_message_text(text=f"❌ <b>ОТКЛОНЕНО.</b>\n{article_title}", parse_mode='HTML', reply_markup=None)
                
        elif prefix == "publish":
            if action == "approve":
                article = storage.get_article_by_id(article_id)
                final_post = (f"<b>{article.title}</b>\n\n{article.summary}\n\n<a href='{article.doi}'>Источник</a>")
                await context.bot.send_message(
                    chat_id=PUBLISH_CHANNEL_ID, text=final_post, parse_mode='HTML',
                    disable_web_page_preview=False
                )
                storage.update_article_status(article_id, 'published')
                await query.edit_message_text(text=f"🚀 <b>ОПУБЛИКОВАНО</b>\n\n{original_message_html}", parse_mode='HTML', reply_markup=None)
                logger.info(f"Статья {article.id} успешно опубликована.")
            elif action == "reject":
                storage.update_article_status(article_id, 'review_rejected')
                article_title = get_title_from_message(original_message_html)
                await query.edit_message_text(text=f"🗑️ <b>ОТПРАВЛЕНО В КОРЗИНУ.</b>\n{article_title}", parse_mode='HTML', reply_markup=None)
    
    except Exception as e:
        logger.error(f"Ошибка в обработчике кнопок: {e}", exc_info=True)


def main():
    logger.info("Запуск Агента-Модератора (Редакционный пульт)...")
    application = ApplicationBuilder().token(TELEGRAM_BOT_TOKEN).build()
    
    job_queue = application.job_queue
    job_queue.run_repeating(triage_conveyor_job, interval=60, first=10)
    job_queue.run_repeating(review_conveyor_job, interval=75, first=20)
    
    application.add_handler(CallbackQueryHandler(button_callback_handler))
    
    application.run_polling()

if __name__ == '__main__':
    main()
