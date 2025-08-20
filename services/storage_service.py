# services/storage_service.py

import os
from datetime import datetime, timezone
from typing import List, Union
import json
import re

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, BigInteger, func
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

def normalize_title(title: str) -> str:
    """Приводит название к нижнему регистру и убирает не-буквенно-цифровые символы."""
    if not title:
        return ""
    return re.sub(r'\W+', '', title).lower()

class Article(Base):
    __tablename__ = 'articles'
    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    normalized_title = Column(String, index=True)
    source_name = Column(String, index=True) # Добавил индекс для ускорения поиска
    
    # --- ИЗМЕНЕНИЕ: Добавляем новое ключевое поле ---
    source_unique_id = Column(String, index=True) # Уникальный ID из источника
    
    status = Column(String, default='new', nullable=False, index=True) # Добавил индекс
    content_type = Column(String, nullable=True)
    content_url = Column(String, nullable=True)
    doi = Column(String, nullable=True, index=True) # Добавил индекс
    year = Column(Integer)
    type = Column(String)
    language = Column(String)
    summary = Column(Text, nullable=True)
    original_abstract = Column(Text, nullable=True)
    full_text = Column(Text, nullable=True)
    full_metadata = Column(Text)
    theme_name = Column(String, nullable=True)
    moderation_message_id = Column(BigInteger, nullable=True)
    date_added = Column(DateTime, default=lambda: datetime.now(timezone.utc))

    def __repr__(self):
        return f"<Article(id='{self.id}', title='{self.title[:30]}...', status='{self.status}')>"

class StorageService:
    def __init__(self, db_url: str = 'sqlite:///data/articles.db'):
        db_path = db_url.replace('sqlite:///', '')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def add_article(self, article_data: dict, theme_name: str) -> str | None:
        """
        Добавляет или обогащает статью. Приоритет проверки на дубликаты:
        1. По (source_name, source_unique_id)
        2. По DOI
        3. По нормализованному заголовку
        """
        session = self.Session()
        try:
            new_title = article_data.get('title')
            if not new_title: return "skipped_no_title"

            # --- ИЗМЕНЕНИЕ: Улучшенная логика поиска дубликатов ---
            existing_article = None
            source_name = article_data.get('source_name')
            source_unique_id = article_data.get('source_unique_id')
            new_doi = article_data.get('doi')
            norm_title = normalize_title(new_title)

            # 1. Лучший способ: по ID из источника
            if source_name and source_unique_id:
                existing_article = session.query(Article).filter_by(
                    source_name=source_name, 
                    source_unique_id=source_unique_id
                ).first()

            # 2. Второй по надежности: по DOI
            if not existing_article and new_doi:
                existing_article = session.query(Article).filter_by(doi=new_doi).first()

            # 3. Наименее надежный: по заголовку
            if not existing_article:
                existing_article = session.query(Article).filter_by(normalized_title=norm_title).first()

            if existing_article:
                # --- ЛОГИКА ОБОГАЩЕНИЯ ---
                is_enriched = False
                if not existing_article.content_url and article_data.get('content_url'):
                    existing_article.content_url = article_data.get('content_url')
                    is_enriched = True
                
                existing_abstract = existing_article.original_abstract or ""
                new_abstract = article_data.get('original_abstract') or ""
                if len(new_abstract) > len(existing_abstract):
                    existing_article.original_abstract = new_abstract
                    is_enriched = True
                
                if not existing_article.doi and new_doi:
                    existing_article.doi = new_doi
                    is_enriched = True
                
                # Добавляем ID источника, если его не было
                if not existing_article.source_unique_id and source_unique_id:
                    existing_article.source_unique_id = source_unique_id
                    is_enriched = True
                
                if is_enriched:
                    session.commit()
                    return "enriched"
                else:
                    return "skipped_duplicate"
            
            # --- Дубликатов нет. Создаем новую статью. ---
            new_article = Article(
                id=article_data.get('id'),
                title=new_title,
                normalized_title=norm_title,
                source_name=source_name,
                source_unique_id=source_unique_id, # Сохраняем ID источника
                status='new',
                content_url=article_data.get('content_url'),
                doi=new_doi,
                year=article_data.get('year'),
                language=article_data.get('language'),
                original_abstract=article_data.get('original_abstract'),
                theme_name=theme_name,
                full_metadata=json.dumps(article_data.get('full_metadata', {}))
            )
            session.add(new_article)
            session.commit()
            return "added"

        except Exception as e:
            session.rollback()
            # Для отладки полезно видеть ошибку
            print(f"ERROR in add_article: {e}")
            raise
        finally:
            session.close()

    # --- Остальные методы без изменений ---
    def get_articles_by_status(self, status: Union[str, List[str]], limit: int = 10, random_order: bool = False) -> List[Article]:
        session = self.Session()
        try:
            query = session.query(Article)
            if isinstance(status, list):
                query = query.filter(Article.status.in_(status))
            else:
                query = query.filter_by(status=status)
            
            if random_order:
                query = query.order_by(func.random())
            else:
                query = query.order_by(Article.date_added.asc())
                
            return query.limit(limit).all()
        finally:
            session.close()

    def get_article_count_by_status(self, status: str) -> int:
        session = self.Session()
        try:
            return session.query(Article).filter_by(status=status).count()
        finally:
            session.close()

    def get_article_by_id(self, article_id: str) -> Article | None:
        session = self.Session()
        try:
            return session.query(Article).filter_by(id=article_id).first()
        finally:
            session.close()

    def update_article_status(self, article_id: str, new_status: str) -> bool:
        session = self.Session()
        try:
            article = session.query(Article).filter_by(id=article_id).first()
            if article:
                article.status = new_status
                session.commit()
                return True
            return False
        finally:
            session.close()

    def update_article_content(self, article_id: str, content_type: str, content_url: str) -> bool:
        session = self.Session()
        try:
            article = session.query(Article).filter_by(id=article_id).first()
            if article:
                article.content_type = content_type
                article.content_url = content_url
                session.commit()
                return True
            return False
        finally:
            session.close()

    def update_article_text(self, article_id: str, text: str) -> bool:
        session = self.Session()
        try:
            article = session.query(Article).filter_by(id=article_id).first()
            if article:
                article.full_text = text
                session.commit()
                return True
            return False
        finally:
            session.close()

    def update_article_summary(self, article_id: str, summary: str) -> bool:
        session = self.Session()
        try:
            article = session.query(Article).filter_by(id=article_id).first()
            if article:
                article.summary = summary
                session.commit()
                return True
            return False
        finally:
            session.close()

    def update_moderation_message_id(self, article_id: str, message_id: int) -> bool:
        session = self.Session()
        try:
            article = session.query(Article).filter_by(id=article_id).first()
            if article:
                article.moderation_message_id = message_id
                session.commit()
                return True
            return False
        finally:
            session.close()

if __name__ == '__main__':
    # Эта часть нужна для инициализации/пересоздания БД
    print("Инициализация базы данных...")
    storage = StorageService()
    print("База данных готова к работе.")
