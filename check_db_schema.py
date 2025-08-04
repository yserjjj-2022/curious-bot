# -*- coding: utf-8 -*-

import sys
from pathlib import Path
from sqlalchemy import create_engine, inspect

# --- Настраиваем пути, чтобы импортировать нашу модель ---
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

try:
    from services.storage_service import Article
    print("✅ Модель 'Article' из 'storage_service.py' успешно импортирована.")
    
    # Показываем, какие колонки ОЖИДАЕТ наш код
    expected_columns = list(Article.__table__.columns.keys())
    print("\n--- Колонки, которые ОЖИДАЕТ ваш КОД ---")
    print(expected_columns)
    
    if 'moderation_message_id' in expected_columns:
        print("\n[ВЫВОД КОДА]: Ваш Python-код ЗНАЕТ о поле 'moderation_message_id'. Это хорошо.")
    else:
        print("\n[ВЫВОД КОДА]: КРИТИЧЕСКАЯ ОШИБКА! Ваш Python-код НЕ ЗНАЕТ о поле 'moderation_message_id'. Пожалуйста, обновите файл 'storage_service.py'.")

except ImportError:
    print("❌ КРИТИЧЕСКАЯ ОШИБКА: Не удалось импортировать модель 'Article'. Проверьте, что файл 'services/storage_service.py' существует и не содержит ошибок.")
    sys.exit(1)


# --- Теперь смотрим, что на самом деле лежит в файле базы данных ---
db_path = project_root / 'data' / 'articles.db'
print(f"\nПроверяю реальную структуру базы данных в файле: {db_path}")

if not db_path.exists():
    print("\n[ВЫВОД БД]: Файл 'articles.db' не найден. Это значит, что база еще не создана. Запустите сначала main.py.")
    sys.exit(0)

try:
    engine = create_engine(f'sqlite:///{db_path}')
    inspector = inspect(engine)
    
    if 'articles' in inspector.get_table_names():
        actual_columns = [col['name'] for col in inspector.get_columns('articles')]
        print("\n--- Колонки, которые РЕАЛЬНО существуют в ФАЙЛЕ БАЗЫ ДАННЫХ ---")
        print(actual_columns)

        if 'moderation_message_id' in actual_columns:
            print("\n[ВЫВОД БД]: База данных в порядке! Колонка 'moderation_message_id' на месте.")
        else:
            print("\n[ВЫВОД БД]: КРИТИЧЕСКАЯ ОШИБКА! В файле 'articles.db' ОТСУТСТВУЕТ колонка 'moderation_message_id'.")
            print("РЕШЕНИЕ: Удалите файл 'data/articles.db' и перезапустите весь конвейер, начиная с 'main.py'.")
    else:
        print("\n[ВЫВОД БД]: В базе данных нет таблицы 'articles'.")

except Exception as e:
    print(f"\n❌ Произошла ошибка при подключении к базе данных: {e}")

