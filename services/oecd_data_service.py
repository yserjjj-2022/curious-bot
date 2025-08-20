# services/oecd_data_service.py

import requests
from uuid import uuid4
import yaml
from pathlib import Path

# Предварительная настройка для корректной работы с путем
project_root = Path(__file__).resolve().parent.parent
import sys
if str(project_root) not in sys.path:
    sys.path.append(str(project_root))

from services.storage_service import StorageService, Article

CONFIG_PATH = project_root / "sources" / "oecd_sources.yaml"
OECD_API_BASE_URL = "https://sdmx.oecd.org/public/rest/data/"

class OECDDataService:
    def __init__(self, storage: StorageService):
        self.storage = storage
        self.source_name = "oecd"

    def _load_config(self):
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f)

    def run_ingestion(self):
        """Основной метод для сбора данных из OECD API по YAML-конфигурации."""
        print(f"=== ЗАПУСК СЕРВИСА СБОРА ДАННЫХ: {self.source_name.upper()} ===")
        
        try:
            config = self._load_config()
        except FileNotFoundError:
            print(f"ОШИБКА: Файл конфигурации не найден по пути: {CONFIG_PATH}")
            return 0
        
        total_added = 0
        for dataset in config.get('datasets', []):
            print(f"\n  -> Обработка набора данных: {dataset['name']} ({dataset['id']})")
            
            flow_ref = dataset['flowRef']
            
            # --- ИЗМЕНЕНИЕ: Используем правильные параметры startPeriod и endPeriod ---
            api_params = ["dimensionAtObservation=AllDimensions"]
            start_year = dataset.get('startYear')
            if start_year:
                api_params.append(f"startPeriod={start_year}")
                api_params.append(f"endPeriod={start_year}") # Добавляем для точности
                print(f"    -> Применен фильтр по году: {start_year}")

            params_str = "&".join(api_params)
            api_url = f"{OECD_API_BASE_URL}{flow_ref}/all?{params_str}&format=jsondata"
            
            try:
                print(f"    -> Запрос к API: {api_url}") # Логируем URL для отладки
                response = requests.get(api_url)
                response.raise_for_status()
                data = response.json()
            except requests.exceptions.RequestException as e:
                print(f"    -> Ошибка при запросе к API для {dataset['id']}: {e}")
                continue
            except ValueError:
                print(f"    -> Не удалось декодировать JSON для {dataset['id']}.")
                continue

            added_count = self._parse_and_store_data(data, dataset['id'])
            print(f"    -> Найдено и добавлено {added_count} новых записей.")
            total_added += added_count
            
        print(f"\n=== РАБОТА СЕРВИСА {self.source_name.upper()} ЗАВЕРШЕНА. Всего добавлено: {total_added} ===")
        return total_added

    def _parse_and_store_data(self, data, dataset_id: str) -> int:
        session = self.storage.Session()
        added_count = 0
        
        try:
            observations = data.get('dataSets', [{}])[0].get('observations', {})
            if not observations:
                print("    -> В ответе API не найдено наблюдений (observations). Возможно, данных за указанный период нет.")
                return 0
            
            structure = data.get('structure', {})
            series_dimensions = structure.get('dimensions', {}).get('observation', [])
            
            for key, obs_data in observations.items():
                source_id = f"{dataset_id}_{key}"
                
                existing_article = session.query(Article).filter_by(
                    source_name=self.source_name,
                    source_unique_id=source_id
                ).first()
                
                if existing_article: continue

                title_parts = []
                attributes = obs_data[0].split(':')
                for i, attr_index in enumerate(attributes):
                    dim_info = series_dimensions[i]
                    dim_values = dim_info.get('values', [])
                    if int(attr_index) < len(dim_values):
                        title_parts.append(dim_values[int(attr_index)].get('name', 'N/A'))
                
                title = f"{dataset_id}: {' - '.join(title_parts)}"
                
                new_article = Article(
                    id=str(uuid4()),
                    title=title,
                    status='new_from_source',
                    source_name=self.source_name,
                    source_unique_id=source_id,
                    original_abstract=f"Observation data from OECD. Details: {title}"
                )
                session.add(new_article)
                added_count += 1

            session.commit()
        except Exception as e:
            print(f"    -> Ошибка при парсинге и сохранении данных: {e}")
            session.rollback()
        finally:
            session.close()
            
        return added_count

if __name__ == '__main__':
    storage_service = StorageService()
    service = OECDDataService(storage_service)
    service.run_ingestion()
