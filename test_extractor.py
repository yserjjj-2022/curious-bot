# test_extractor.py

import os
import sys
import time
import threading
import psutil
from pathlib import Path
from uuid import uuid4

# --- Инициализация проекта ---
project_root = Path(__file__).resolve().parent
sys.path.append(str(project_root))

from services.storage_service import StorageService, Article
from agents.content_extractor_agent import run_extraction_cycle

# ==============================================================================
# --- ВАШ ТЕСТОВЫЙ ПОЛИГОН ---
# ==============================================================================
TEST_URLS = [
    "https://doi.org/10.38035/dijefa.v6i4.4838",
    "https://doi.org/10.47747/fmiic.vi2.2963",
    "https://www.paradigmpress.org/le/article/view/1673",
    "https://doi.org/10.54254/2754-1169/2025.bl24328",
    "https://doi.org/10.25136/2409-7144.2025.5.74546",
    "https://doi.org/10.3389/frbhe.2025.1379577",
    "https://doi.org/10.52783/jier.v5i1.2004"
]
# ==============================================================================

# --- ИЗМЕНЕНИЕ: Добавлен класс для мониторинга ресурсов ---
class ResourceMonitor:
    def __init__(self, interval=0.5):
        self._interval = interval
        self._process = psutil.Process(os.getpid())
        self._thread = None
        self._running = False
        self.cpu_usage = []
        self.memory_usage = []

    def _monitor(self):
        """Функция, которая будет работать в фоновом потоке."""
        while self._running:
            self.cpu_usage.append(self._process.cpu_percent())
            # Сохраняем использование памяти в мегабайтах
            self.memory_usage.append(self._process.memory_info().rss / (1024 * 1024))
            time.sleep(self._interval)

    def start(self):
        """Запускает мониторинг."""
        if self._thread is None:
            self._running = True
            self._thread = threading.Thread(target=self._monitor)
            self._thread.start()

    def stop(self):
        """Останавливает мониторинг и возвращает результаты."""
        if self._thread is not None:
            self._running = False
            self._thread.join()
            
            # Вычисляем и возвращаем итоговые метрики
            avg_cpu = sum(self.cpu_usage) / len(self.cpu_usage) if self.cpu_usage else 0
            max_mem = max(self.memory_usage) if self.memory_usage else 0
            
            return avg_cpu, max_mem

def prepare_test_db(urls):
    """Готовит и заполняет временную базу данных."""
    test_db_path = 'data/test_articles.db'
    test_db_url = f'sqlite:///{test_db_path}'
    if os.path.exists(test_db_path):
        os.remove(test_db_path)
    
    storage = StorageService(db_url=test_db_url)
    session = storage.Session()
    
    for i, url in enumerate(urls):
        is_doi = "doi.org" in url
        mock_article = Article(
            id=str(uuid4()),
            title=f"Тестовая статья #{i+1} ({url[:30]}...)",
            status='new',
            doi=url if is_doi else None,
            content_url=url if not is_doi else None
        )
        session.add(mock_article)
        
    session.commit()
    session.close()
    return storage

# --- ИЗМЕНЕНИЕ: Основная функция обернута в профилировщик ---
def run_test_with_profiling():
    """
    Основная функция тестового прогона с замером ресурсов.
    """
    print("===== ЗАПУСК ТЕСТОВОГО СТЕНДА ДЛЯ ЭКСТРАКТОРА =====")
    
    # 1. Подготовка
    print(f"-> Подготовка тестовой базы для {len(TEST_URLS)} URL...")
    storage = prepare_test_db(TEST_URLS)
    print("-> Тестовая база готова.")
    
    # 2. Запуск мониторинга и основного кода
    monitor = ResourceMonitor()
    
    start_time = time.time()
    monitor.start()
    
    print("\n===== ЗАПУСК ЦИКЛА ЭКСТРАКЦИИ В ТЕСТОВОМ РЕЖИМЕ =====")
    run_extraction_cycle(storage)
    print("===== ЦИКЛ ЭКСТРАКЦИИ ЗАВЕРШЕН =====")
    
    avg_cpu, max_mem = monitor.stop()
    end_time = time.time()
    
    # 3. Вывод результатов
    total_time = end_time - start_time
    time_per_article = total_time / len(TEST_URLS) if TEST_URLS else 0
    
    print("\n" + "="*30)
    print("    ОТЧЕТ О РЕСУРСОЕМКОСТИ")
    print("="*30)
    print(f"  Всего обработано URL: {len(TEST_URLS)}")
    print(f"  Общее время выполнения: {total_time:.2f} сек.")
    print(f"  Среднее время на статью: {time_per_article:.2f} сек.")
    print(f"  Средняя загрузка ЦП: {avg_cpu:.2f}%")
    print(f"  Пиковое потребление памяти: {max_mem:.2f} МБ")
    print("="*30)
    print(f"\nВы можете изучить результаты в файле базы данных: data/test_articles.db")

if __name__ == "__main__":
    run_test_with_profiling()
