# agents/arxiv_fetcher.py

import arxiv
from datetime import datetime

class ArxivFetcher:
    """
    Класс для получения статей из arXiv с фильтрацией по году.
    """
    def fetch_articles(self, config: dict) -> list:
        """
        Получает статьи из arXiv по заданным параметрам.
        
        Args:
            config (dict): Словарь с конфигурацией.
        
        Returns:
            list: Список словарей, где каждый словарь - нормализованная статья.
        """
        search_query = config.get('query')
        max_results = config.get('fetch_limit', 50)
        
        # --- ИЗМЕНЕНИЕ: Получаем параметр для фильтра по году из конфига ---
        # По умолчанию берем статьи за 2 последних года (текущий и прошлый)
        max_age_years = config.get('max_age_years', 2)
        current_year = datetime.now().year
        cutoff_year = current_year - max_age_years
        
        if not search_query:
            print("❌ ArxivFetcher: Поисковый запрос ('query') не указан в конфигурации.")
            return []

        print(f"   [ArxivFetcher] -> Ищу статьи по запросу: '{search_query}', лимит: {max_results}.")
        print(f"   [ArxivFetcher] -> Фильтр: статьи не старше {cutoff_year + 1} года.")
        
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        
        results = search.results()
        normalized_articles = []
        
        for result in results:
            # --- ИЗМЕНЕНИЕ: Добавляем "железный фильтр" по году публикации ---
            article_year = result.published.year
            if article_year <= cutoff_year:
                # Если статья слишком старая, пропускаем ее
                continue
            # ----------------------------------------------------------------
            
            # Нормализуем данные к нашему внутреннему формату
            normalized_article = {
                'id': result.entry_id,
                'title': result.title,
                'source_name': 'arXiv',
                'content_url': result.pdf_url,
                'doi': result.doi,
                'year': article_year, # Используем уже полученный год
                'original_abstract': result.summary.replace('\\n', ' '),
                'full_metadata': {
                    'authors': [author.name for author in result.authors],
                    'published_date': result.published.isoformat(),
                    'categories': result.categories
                }
            }
            normalized_articles.append(normalized_article)
            
        print(f"   [ArxivFetcher] -> Найдено и отфильтровано {len(normalized_articles)} релевантных статей.")
        return normalized_articles
