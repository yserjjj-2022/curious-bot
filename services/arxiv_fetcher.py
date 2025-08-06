# agents/arxiv_fetcher.py

import arxiv
from datetime import datetime

class ArxivFetcher:
    """
    Класс для получения статей из arXiv.
    """
    def fetch_articles(self, config: dict) -> list:
        """
        Получает статьи из arXiv по заданным параметрам.
        
        Args:
            config (dict): Словарь с конфигурацией, должен содержать:
                           - 'query': поисковый запрос (например, 'cat:cs.AI AND ti:finance')
                           - 'max_results': максимальное количество результатов
        
        Returns:
            list: Список словарей, где каждый словарь - нормализованная статья.
        """
        search_query = config.get('query')
        max_results = config.get('fetch_limit', 50)
        
        if not search_query:
            print("❌ ArxivFetcher: Поисковый запрос ('query') не указан в конфигурации.")
            return []

        print(f"   [ArxivFetcher] -> Ищу статьи по запросу: '{search_query}', лимит: {max_results}.")
        
        search = arxiv.Search(
            query=search_query,
            max_results=max_results,
            sort_by=arxiv.SortCriterion.SubmittedDate
        )
        
        results = search.results()
        normalized_articles = []
        
        for result in results:
            # Нормализуем данные к нашему внутреннему формату
            normalized_article = {
                'id': result.entry_id,
                'title': result.title,
                'source_name': 'arXiv',
                'content_url': result.pdf_url,
                'doi': result.doi,
                'year': result.published.year,
                'original_abstract': result.summary.replace('\n', ' '),
                'full_metadata': {
                    'authors': [author.name for author in result.authors],
                    'published_date': result.published.isoformat(),
                    'categories': result.categories
                }
            }
            normalized_articles.append(normalized_article)
            
        return normalized_articles

