# -*- coding: utf-8 -*-

import os
import time
from services.storage_service import StorageService

def run_test():
    """
    Основная функция для тестирования обновленного StorageService.
    Проверяет логику работы со статусами и новыми полями.
    """
    print("=== ЗАПУСК ТЕСТА ДЛЯ ОБНОВЛЕННОГО STORAGE_SERVICE ===")
    
    # Используем отдельную тестовую БД
    test_db_path = 'data/test_articles.db'
    db_url = f'sqlite:///{test_db_path}'
    
    # --- Шаг 0: Очистка перед тестом ---
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
        print(f"Удален старый файл тестовой БД: {test_db_path}")

    # --- Шаг 1: Инициализация ---
    print("\n[ТЕСТ 1] Инициализация сервиса...")
    try:
        storage = StorageService(db_url=db_url)
        print("✅ УСПЕХ: Сервис инициализирован, файл БД создан.")
    except Exception as e:
        print(f"❌ ПРОВАЛ: Ошибка при инициализации сервиса: {e}")
        return

    # --- Шаг 2: Добавление статьи и проверка статуса 'new' ---
    print("\n[ТЕСТ 2] Добавление новой статьи...")
    article_1_meta = {'id': 'W1', 'display_name': 'Article 1'}
    
    was_added = storage.add_article(
        article_meta=article_1_meta,
        content_type='abstract',
        content_url=None,
        original_abstract='Abstract for article 1.',
        source_name='Test Source'
    )
    if not was_added:
        print("❌ ПРОВАЛ: Метод add_article вернул False при добавлении новой статьи.")
        return
    
    # Проверяем, что статья сохранилась с правильным статусом
    saved_article_1 = storage.get_article_by_id('W1')
    if saved_article_1 and saved_article_1.status == 'new':
        print("✅ УСПЕХ: Статья добавлена со статусом 'new'.")
    else:
        status = saved_article_1.status if saved_article_1 else 'None'
        print(f"❌ ПРОВАЛ: Ожидался статус 'new', но получен '{status}'.")
        return

    # --- Шаг 3: Проверка защиты от дубликатов ---
    print("\n[ТЕСТ 3] Попытка повторного добавления той же статьи...")
    was_added_again = storage.add_article(article_1_meta, 'abstract', None, 'Abstract', 'Test')
    if not was_added_again:
        print("✅ УСПЕХ: Защита от дубликатов сработала.")
    else:
        print("❌ ПРОВАЛ: Сервис позволил добавить дубликат.")
        return

    # --- Шаг 4: Обновление статуса статьи ---
    print("\n[ТЕСТ 4] Обновление статуса статьи на 'awaiting_triage'...")
    update_success = storage.update_article_status('W1', 'awaiting_triage')
    if not update_success:
        print("❌ ПРОВАЛ: Метод update_article_status вернул False.")
        return
        
    updated_article_1 = storage.get_article_by_id('W1')
    if updated_article_1 and updated_article_1.status == 'awaiting_triage':
        print("✅ УСПЕХ: Статус статьи успешно обновлен.")
    else:
        status = updated_article_1.status if updated_article_1 else 'None'
        print(f"❌ ПРОВАЛ: Ожидался статус 'awaiting_triage', но получен '{status}'.")
        return

    # --- Шаг 5: Проверка выборки по статусу ---
    print("\n[ТЕСТ 5] Проверка выборки по статусу...")
    # Добавляем еще одну статью, она будет со статусом 'new'
    storage.add_article({'id': 'W2', 'display_name': 'Article 2'}, 'pdf', 'http://a.pdf', 'Abstract 2', 'Test')
    
    new_articles = storage.get_articles_by_status('new', limit=5)
    triage_articles = storage.get_articles_by_status('awaiting_triage', limit=5)

    if len(new_articles) == 1 and new_articles[0].id == 'W2':
        print("✅ УСПЕХ: Корректно найдена 1 статья со статусом 'new'.")
    else:
        print(f"❌ ПРОВАЛ: Найдено {len(new_articles)} статей со статусом 'new', ожидалась 1.")
        return

    if len(triage_articles) == 1 and triage_articles[0].id == 'W1':
        print("✅ УСПЕХ: Корректно найдена 1 статья со статусом 'awaiting_triage'.")
    else:
        print(f"❌ ПРОВАЛ: Найдено {len(triage_articles)} статей со статусом 'awaiting_triage', ожидалась 1.")
        return

    print("\n🎉🎉🎉 Все тесты успешно пройдены! Обновленный StorageService работает корректно. 🎉🎉🎉")

if __name__ == "__main__":
    run_test()
