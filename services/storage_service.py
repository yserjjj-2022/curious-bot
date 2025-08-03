# -*- coding: utf-8 -*-

import os
import json
from datetime import datetime
from typing import List, Dict, Optional

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# --- Базовая настройка SQLAlchemy ---
Base = declarative_base()

class Article(Base):
    """
    Обновленная модель данных для статьи. Теперь она включает всю информацию,
    необходимую для многоэтапной модерации и интеллектуальной суммаризации.
    """
    __tablename__ = 'articles'

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    source_name = Column(String)
    
    # --- НОВЫЕ КЛЮЧЕВЫЕ ПОЛЯ ---
    status = Column(String, default='new', nullable=False)
    content_type = Column(String, nullable=True) # 'pdf', 'html' или 'abstract'
    content_url = Column(String, nullable=True) # Ссылка на PDF или HTML-страницу
    
    year = Column(Integer)
    type = Column(String)
    language = Column(String)
    summary = Column(Text, nullable=True) # Наша финальная, утвержденная выжимка
    original_abstract = Column(Text, nullable=True)
    full_metadata = Column(Text) 
    date_added = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Article(id='{self.id}', status='{self.status}', title='{self.title[:30]}...')>"

class StorageService:
    """
    Сервис для работы с хранилищем данных.
    Абстрагирует всю логику работы с БД.
    """
    def __init__(self, db_url: str = 'sqlite:///data/articles.db'):
        os.makedirs(os.path.dirname(db_url.replace('sqlite:///', '')), exist_ok=True)
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine) # Создает таблицу со всеми колонками, если ее нет
        self.Session = sessionmaker(bind=self.engine)

    def add_article(self, article_meta: Dict, content_type: Optional[str], content_url: Optional[str], original_abstract: Optional[str], source_name: str) -> bool:
        """
        Добавляет новую статью в базу со статусом 'new'.
        Возвращает True, если статья была добавлена, и False, если она уже существовала.
        """
        session = self.Session()
        try:
            article_id = article_meta.get('id')
            if not article_id or session.query(Article.id).filter_by(id=article_id).first():
                return False

            new_article = Article(
                id=article_id,
                title=article_meta.get('display_name'),
                source_name=source_name,
                status='new', # Все новые статьи получают этот статус
                content_type=content_type,
                content_url=content_url,
                year=article_meta.get('publication_year'),
                type=article_meta.get('type'),
                language=article_meta.get('language'),
                original_abstract=original_abstract,
                full_metadata=json.dumps(article_meta, ensure_ascii=False)
            )
            session.add(new_article)
            session.commit()
            return True
        finally:
            session.close()

    def update_article_status(self, article_id: str, new_status: str) -> bool:
        """Изменяет статус конкретной статьи."""
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

    def get_articles_by_status(self, status: str, limit: int = 10) -> List[Article]:
        """Возвращает список статей с указанным статусом."""
        session = self.Session()
        try:
            return session.query(Article).filter_by(status=status).order_by(Article.date_added.asc()).limit(limit).all()
        finally:
            session.close()

    # --- НОВЫЙ МЕТОД ДЛЯ ТЕСТИРОВАНИЯ ---
    def get_article_by_id(self, article_id: str) -> Optional[Article]:
        """Находит и возвращает одну статью по ее ID."""
        session = self.Session()
        try:
            return session.query(Article).filter_by(id=article_id).first()
        finally:
            session.close()