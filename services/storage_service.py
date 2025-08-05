# -*- coding: utf-8 -*-

import os
from datetime import datetime, timezone
from typing import List, Union

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime, BigInteger
from sqlalchemy.orm import sessionmaker, declarative_base

Base = declarative_base()

class Article(Base):
    """Финальная модель данных для статьи."""
    __tablename__ = 'articles'

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    source_name = Column(String)
    
    status = Column(String, default='new', nullable=False)
    content_type = Column(String, nullable=True)
    content_url = Column(String, nullable=True)
    doi = Column(String, nullable=True)
    
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
        return f"<Article(id='{self.id}', status='{self.status}', title='{self.title[:20]}...')>"

class StorageService:
    """Финальная версия сервиса для работы с хранилищем."""
    def __init__(self, db_url: str = 'sqlite:///data/articles.db'):
        db_path = db_url.replace('sqlite:///', '')
        os.makedirs(os.path.dirname(db_path), exist_ok=True)
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine)
        self.Session = sessionmaker(bind=self.engine)

    def get_articles_by_status(self, status: Union[str, List[str]], limit: int = 10) -> List[Article]:
        session = self.Session()
        try:
            query = session.query(Article)
            if isinstance(status, list):
                query = query.filter(Article.status.in_(status))
            else:
                query = query.filter_by(status=status)
            return query.order_by(Article.date_added.asc()).limit(limit).all()
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
            
    # --- Остальные методы, которые должны здесь быть ---
    def add_article(self, article_data: dict) -> bool:
        session = self.Session()
        try:
            # Преобразуем 'full_metadata' в строку JSON, если это словарь
            if 'full_metadata' in article_data and isinstance(article_data['full_metadata'], dict):
                import json
                article_data['full_metadata'] = json.dumps(article_data['full_metadata'])
            
            if not session.query(Article).filter_by(id=article_data['id']).first():
                new_article = Article(**article_data)
                session.add(new_article)
                session.commit()
                return True
            return False
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
