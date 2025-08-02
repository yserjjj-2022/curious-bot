# -*- coding: utf-8 -*-

import os
import json
import telegram
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Application, CallbackQueryHandler, ContextTypes
from telegram.constants import ParseMode
import pyalex
from dotenv import load_dotenv
import asyncio
import re
import yaml
from glob import glob

# --- Загрузка конфигурации ---
load_dotenv()

# --- Глобальные константы ---
TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN')
TELEGRAM_MOD_CHANNEL_ID = os.getenv('TELEGRAM_MODERATION_CHANNEL_ID')
TELEGRAM_PUB_CHANNEL_ID = os.getenv('TELEGRAM_PUBLIC_CHANNEL_ID')
pyalex.config.email = os.getenv('OPENALEX_EMAIL')

# ===================================================================
# МОДУЛЬ 1: УТИЛИТЫ И ХРАНИЛИЩЕ
# (здесь все без изменений)
# ===================================================================
def reconstruct_abstract(inverted_index: dict) -> str:
    if not inverted_index: return ""
    try:
        max_pos = max(max(positions) for positions in inverted_index.values() if positions)
        abstract_list = [''] * (max_pos + 1); [abstract_list.__setitem__(pos, word) for word, positions in inverted_index.items() for pos in positions]
        return ' '.join(abstract_list)
    except (ValueError, TypeError): return ""

def strip_html_tags(text: str) -> str:
    if not text: return ""
    return re.sub('<[^<]+?>', '', text)

class StateManager:
    def __init__(self, filepath="processed_ids.json"): self.filepath = filepath
    def load_processed_ids(self) -> set:
        if not os.path.exists(self.filepath): return set()
        try:
            with open(self.filepath, 'r', encoding='utf-8') as f: return set(json.load(f))
        except (json.JSONDecodeError, FileNotFoundError): return set()
    def save_processed_ids(self, ids: set):
        with open(self.filepath, 'w', encoding='utf-8') as f: json.dump(list(ids), f, indent=4)

class Translator:
    def translate(self, text: str, target_language: str = "ru") -> str:
        return text

# ===================================================================
# МОДУЛЬ 2: СБОР ДАННЫХ И СУММАРИЗАЦИЯ
# ===================================================================

class Summarizer:
    def summarize(self, paper: dict) -> str:
        print(f"-> [Summarizer] Создаю новость для статьи: '{paper['title'][:30]}...'")
        title = paper['title']
        problem = "Проблема XYZ, изучаемая в статье."
        method = "Использовался метод ABC."
        sample = "Выборка состояла из N участников."
        authors_conclusion = "Авторы пришли к выводу, что..."
        pdf_url = paper['pdf_url']
        summary_text = (f"<b>{title}</b>\n\n<b>Проблема:</b> {problem}\n<b>Метод:</b> {method}\n<b>Выборка:</b> {sample}\n<b>Выводы:</b> {authors_conclusion}\n\n<a href='{pdf_url}'>🔗 Ссылка на PDF</a>")
        return summary_text

class OpenAlexFetcher:
    """
    Конкретный сборщик для OpenAlex.
    Теперь умеет работать и с "concepts", и с "topics", и с "type".
    """
    def fetch(self, config: dict) -> list:
        print(f"--- [OpenAlex] Ищу статьи согласно конфигурации ---")
        try:
            query = pyalex.Works()

            # --- КЛЮЧЕВОЕ ИЗМЕНЕНИЕ ---
            # Фильтр по типу документа. pyalex объединяет несколько типов через '|'.
            if config.get('document_types'):
                query = query.filter(type="|".join(config['document_types']))
            # --- КОНЕЦ ИЗМЕНЕНИЯ ---

            # Фильтрация по Concepts или Topics
            if config.get('primary_concepts'): query = query.filter(concepts={'id': "|".join(config['primary_concepts'])})
            if config.get('primary_topics'): query = query.filter(topics={'id': "|".join(config['primary_topics'])})
            if config.get('domain_concepts'): query = query.filter(concepts={'id': "|".join(config['domain_concepts'])})
            if config.get('domain_topics'): query = query.filter(topics={'id': "|".join(config['domain_topics'])})
            if config.get('exclude_concepts'):
                for concept_id in config['exclude_concepts']: query = query.filter(concepts={'id': f"!{concept_id}"})
            if config.get('exclude_topics'):
                for topic_id in config['exclude_topics']: query = query.filter(topics={'id': f"!{topic_id}"})
            
            # Применяем остальные фильтры и выполняем запрос
            query = query.filter(
                publication_year=f">{config['start_year'] - 1}", is_oa=True, has_pdf_url=True
            ).sort(publication_date="desc").select([
                'id', 'title', 'authorships', 'publication_year', 
                'best_oa_location', 'abstract_inverted_index'
            ])
            
            raw_papers = query.get(per_page=config.get('fetch_limit', 25))
            return [self._normalize(paper) for paper in raw_papers]
            
        except Exception as e:
            print(f"❌ [OpenAlex] Ошибка при запросе к API: {e}")
            return []
            
    def _normalize(self, paper: dict) -> dict:
        return {"id": paper.get('id'), "title": paper.get('title', 'Без названия'), "abstract": reconstruct_abstract(paper.get('abstract_inverted_index')), "authors": [a.get('author', {}).get('display_name') for a in paper.get('authorships', [])], "year": paper.get('publication_year'), "pdf_url": paper.get('best_oa_location', {}).get('pdf_url'), "source_name": "OpenAlex"}

class FetcherService:
    # ... (код этого класса не меняется)
    def __init__(self): self.fetchers = {"openalex": OpenAlexFetcher()}
    def run(self) -> list:
        print("\n=== ЗАПУСК СЕРВИСА СБОРА ДАННЫХ ==="); all_new_papers = []
        for config_path in glob("sources/*.yaml"):
            with open(config_path, 'r', encoding='utf-8') as f: config = yaml.safe_load(f)
            if not config.get('enabled'): continue
            fetcher_type = config.get('fetcher_type')
            if fetcher_type in self.fetchers: all_new_papers.extend(self.fetchers[fetcher_type].fetch(config))
        print(f"Сбор данных завершен. Всего найдено: {len(all_new_papers)} статей.")
        return all_new_papers

# ===================================================================
# МОДУЛЬ 3: ЛОГИКА БОТА
# (здесь все без изменений)
# ===================================================================

async def send_for_triage(context: ContextTypes.DEFAULT_TYPE):
    fetcher_service = FetcherService()
    state_manager = StateManager()
    all_papers = await asyncio.to_thread(fetcher_service.run)
    processed_ids = state_manager.load_processed_ids()
    print(f"Загружено {len(processed_ids)} ранее обработанных ID.")
    if 'papers_in_progress' not in context.bot_data: context.bot_data['papers_in_progress'] = {}
    new_papers_found = 0
    for paper in sorted(all_papers, key=lambda p: p.get('year', 0)):
        if paper['id'] in processed_ids or not paper.get('pdf_url'): continue
        context.bot_data['papers_in_progress'][paper['id']] = paper
        keyboard = [[InlineKeyboardButton("👍 В работу", callback_data=f"triage_accept_{paper['id']}"), InlineKeyboardButton("👎 Отклонить", callback_data=f"triage_reject_{paper['id']}")]]
        reply_markup = InlineKeyboardMarkup(keyboard)
        message_text = f"<b>{paper['title']}</b>\n\n<i>{strip_html_tags(paper['abstract'])[:700]}...</i>\n\n<a href='{paper['pdf_url']}'>🔗 PDF</a>"
        await context.bot.send_message(chat_id=TELEGRAM_MOD_CHANNEL_ID, text=message_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
        processed_ids.add(paper['id'])
        new_papers_found += 1
        await asyncio.sleep(2)
    state_manager.save_processed_ids(processed_ids)
    print(f"Отправлено на модерацию: {new_papers_found} статей.")

async def moderation_callback_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    stage, action, paper_id = query.data.split("_", 2)
    original_message = query.message
    if stage == "triage":
        await original_message.delete()
        if action == "accept":
            paper_data = context.bot_data['papers_in_progress'].get(paper_id)
            if not paper_data: return
            summarizer = Summarizer()
            summary_text = summarizer.summarize(paper_data)
            keyboard = [[InlineKeyboardButton("✅ Опубликовать", callback_data=f"publish_accept_{paper_id}"), InlineKeyboardButton("✏️ Отклонить", callback_data=f"publish_reject_{paper_id}")]]
            reply_markup = InlineKeyboardMarkup(keyboard)
            await context.bot.send_message(chat_id=TELEGRAM_MOD_CHANNEL_ID, text=summary_text, parse_mode=ParseMode.HTML, reply_markup=reply_markup)
    elif stage == "publish":
        await original_message.delete()
        if action == "accept":
            await context.bot.send_message(chat_id=TELEGRAM_PUB_CHANNEL_ID, text=original_message.text_html, parse_mode=ParseMode.HTML)
            print(f"✅ Новость {paper_id} опубликована.")
            if paper_id in context.bot_data['papers_in_progress']:
                del context.bot_data['papers_in_progress'][paper_id]

# ===================================================================
# ГЛАВНЫЙ ЗАПУСК
# (здесь все без изменений)
# ===================================================================
def main():
    if not all([TELEGRAM_BOT_TOKEN, TELEGRAM_MOD_CHANNEL_ID, TELEGRAM_PUB_CHANNEL_ID]):
        print("❌ Ошибка: Не все необходимые переменные окружения заданы. Проверьте .env файл.")
        return
    application = Application.builder().token(TELEGRAM_BOT_TOKEN).build()
    application.add_handler(CallbackQueryHandler(moderation_callback_handler))
    job_queue = application.job_queue
    job_queue.run_repeating(send_for_triage, interval=14400, first=10)
    print("🚀 Бот запущен в автоматическом режиме. Первая проверка начнется через 10 секунд...")
    application.run_polling()

if __name__ == "__main__":
    main()
