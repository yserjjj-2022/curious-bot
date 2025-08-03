# -*- coding: utf-8 -*-

import os
import time
from services.storage_service import StorageService

def run_test():
    """
    Основная функция для тестирования StorageService.
    """
    print("=== ЗАПУСК ТЕСТА ДЛЯ STORAGE_SERVICE ===")
    
    # Используем отдельную тестовую БД, чтобы не засорять рабочую
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
        if os.path.exists(test_db_path):
            print("✅ УСПЕХ: Файл базы данных успешно создан.")
        else:
            print("❌ ПРОВАЛ: Файл базы данных не был создан.")
            return
    except Exception as e:
        print(f"❌ ПРОВАЛ: Ошибка при инициализации сервиса: {e}")
        return

    # --- Шаг 2: Добавление первой статьи ---
    print("\n[ТЕСТ 2] Добавление новой статьи...")
    article_1_meta = {
        'id': 'W12345', 'display_name': 'First Test Article', 'publication_year': 2025,
        'type': 'article', 'language': 'en'
    }
    summary_1 = "Summary for the first article."
    
    is_added_1 = storage.add_article(article_1_meta, summary_1)
    if is_added_1:
        print("✅ УСПЕХ: Первая статья успешно добавлена (метод вернул True).")
    else:
        print("❌ ПРОВАЛ: Метод add_article вернул False при добавлении новой статьи.")
        return
        
    # --- Шаг 3: Проверка защиты от дубликатов ---
    print("\n[ТЕСТ 3] Попытка повторного добавления той же статьи...")
    is_added_again = storage.add_article(article_1_meta, summary_1)
    if not is_added_again:
        print("✅ УСПЕХ: Защита от дубликатов сработала (метод вернул False).")
    else:
        print("❌ ПРОВАЛ: Сервис позволил добавить дубликат статьи.")
        return

    # --- Шаг 4: Добавление второй статьи и получение списка ---
    print("\n[ТЕСТ 4] Добавление второй статьи и получение списка...")
    # Небольшая задержка, чтобы даты добавления гарантированно отличались
    time.sleep(1) 
    
    article_2_meta = {
        'id': 'W67890', 'display_name': 'Second Test Article', 'publication_year': 2024,
        'type': 'report', 'language': 'en'
    }
    summary_2 = "Summary for the second article."
    storage.add_article(article_2_meta, summary_2)
    
    latest_articles = storage.get_latest_articles(limit=5)
    
    if len(latest_articles) == 2:
        print("✅ УСПЕХ: Получено правильное количество статей (2).")
    else:
        print(f"❌ ПРОВАЛ: Получено {len(latest_articles)} статей, ожидалось 2.")
        return
        
    if latest_articles[0]['id'] == 'W67890':
        print("✅ УСПЕХ: Статьи отсортированы правильно (вторая статья идет первой).")
    else:
        print("❌ ПРОВАЛ: Неправильная сортировка статей.")
        print("   Ожидалось, что первой будет W67890, но получено:", latest_articles[0]['id'])
        return

    print("\n🎉🎉🎉 Все тесты успешно пройдены! StorageService работает корректно. 🎉🎉🎉")

if __name__ == "__main__":
    run_test()

