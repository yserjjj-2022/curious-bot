# get_domain_topics.py
import requests
import argparse
import time
import openpyxl
import json
from dotenv import load_dotenv
import os

# Загружаем email из .env для "вежливого" пула запросов
load_dotenv()
OPENALEX_EMAIL = os.getenv('OPENALEX_EMAIL', 'user@example.com')

def save_topics_to_excel(topics, filename):
    """Сохраняет иерархический список топиков в Excel."""
    try:
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Topics List"
        
        headers = ["ID Темы", "Название Темы", "ID Подраздела", "Название Подраздела", "ID Раздела", "Название Раздела"]
        ws.append(headers)

        for topic in topics:
            ws.append([
                topic.get('id').split('/')[-1], # Короткий ID
                topic.get('display_name'),
                topic.get('subfield', {}).get('id', '').split('/')[-1],
                topic.get('subfield', {}).get('display_name'),
                topic.get('field', {}).get('id', '').split('/')[-1],
                topic.get('field', {}).get('display_name')
            ])

        # Автонастройка ширины колонок
        for col in ws.columns:
            max_length = 0
            column_letter = col[0].column_letter
            for cell in col:
                try:
                    if len(str(cell.value)) > max_length:
                        max_length = len(str(cell.value))
                except: pass
            adjusted_width = (max_length + 2)
            ws.column_dimensions[column_letter].width = min(adjusted_width, 60)

        wb.save(filename)
        print(f"\n✅ Успешно сохранено {len(topics)} топиков в файл: {filename}")
    except Exception as e:
        print(f"❌ Ошибка при сохранении в Excel: {e}")

def fetch_and_filter_all_topics(target_domain_shorthand):
    """
    Выгружает ВСЕ топики и фильтрует их по ID домена на стороне клиента.
    """
    all_topics_from_api = []
    page = 1
    
    print("Применяю обходной путь: выгружаю все топики для локальной фильтрации.")
    
    while True:
        print(f"Загружаю страницу {page} ВСЕХ топиков...")
        
        params = {'per-page': 200, 'page': page, 'mailto': OPENALEX_EMAIL}
        
        try:
            response = requests.get("https://api.openalex.org/topics", params=params)
            response.raise_for_status()
            data = response.json()
            results = data.get('results', [])
            if not results:
                print("Больше страниц нет. Завершаю загрузку.")
                break
            all_topics_from_api.extend(results)
            page += 1
            time.sleep(0.1)
        except Exception as e:
            print(f"❌ Ошибка API на странице {page}: {e}")
            break

    print(f"\nЗагружено всего {len(all_topics_from_api)} топиков.")
    
    # --- КЛЮЧЕВОЕ ИСПРАВЛЕНИЕ ---
    # Извлекаем число из 'D2' -> '2' и строим правильный URL
    domain_number = target_domain_shorthand.replace('D', '')
    full_target_domain_id = f"https://openalex.org/domains/{domain_number}"
    print(f"Начинаю фильтрацию. Целевой ID домена: {full_target_domain_id}")
    # -----------------------------

    filtered_topics = []
    for topic in all_topics_from_api:
        domain_info = topic.get('domain')
        if domain_info and domain_info.get('id') == full_target_domain_id:
            filtered_topics.append(topic)
            
    print(f"Фильтрация завершена. Найдено {len(filtered_topics)} топиков в указанном домене.")
    return filtered_topics

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Скрипт для выгрузки всех топиков OpenAlex из указанного домена (с локальной фильтрацией).")
    parser.add_argument("domain_id", type=str, help="Короткий ID домена (например, 'D2' или просто '2' для Social Sciences).")
    parser.add_argument("--output", type=str, default="domain_topics.xlsx", help="Имя выходного файла Excel.")
    
    args = parser.parse_args()

    print(f"=== Начинаю выгрузку топиков из домена: {args.domain_id} ===")
    topics_list = fetch_and_filter_all_topics(args.domain_id)
    
    if topics_list:
        save_topics_to_excel(topics_list, args.output)
    else:
        print("Не удалось найти топики для указанного домена.")
