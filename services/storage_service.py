# -*- coding: utf-8 -*-

import os
import json
from datetime import datetime
from typing import List, Dict

from sqlalchemy import create_engine, Column, String, Integer, Text, DateTime
from sqlalchemy.orm import sessionmaker
from sqlalchemy.ext.declarative import declarative_base

# --- Базовая настройка SQLAlchemy ---
# Определяем "базу" для наших будущих моделей данных
Base = declarative_base()

class Article(Base):
    """
    Модель данных для статьи, которая будет представлена в виде таблицы 'articles' в БД.
    """
    __tablename__ = 'articles'

    id = Column(String, primary_key=True)
    title = Column(String, nullable=False)
    year = Column(Integer)
    type = Column(String)
    language = Column(String)
    summary = Column(Text)
    # Сохраняем "сырые" метаданные на всякий случай
    full_metadata = Column(Text) 
    # Дата добавления в нашу базу, для сортировки
    date_added = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f"<Article(id='{self.id}', title='{self.title[:30]}...')>"

class StorageService:
    """
    Сервис для работы с хранилищем данных.
    Абстрагирует всю логику работы с БД.
    """
    def __init__(self, db_url: str = 'sqlite:///data/articles.db'):
        """
        Инициализирует сервис. Принимает строку подключения к БД.
        Для переезда в облако достаточно будет изменить эту строку.
        """
        # Создаем папку для данных, если ее нет
        os.makedirs(os.path.dirname(db_url.replace('sqlite:///', '')), exist_ok=True)
        
        self.engine = create_engine(db_url)
        Base.metadata.create_all(self.engine) # Создает таблицу, если ее не существует
        self.Session = sessionmaker(bind=self.engine)

    def add_article(self, article_meta: Dict, summary: str) -> bool:
        """
        Добавляет новую статью в базу данных.
        Возвращает True, если статья была добавлена, и False, если она уже существовала.
        """
        session = self.Session()
        try:
            article_id = article_meta.get('id')
            if not article_id:
                return False

            # Проверяем, существует ли уже такая статья
            exists = session.query(Article.id).filter_by(id=article_id).first() is not None
            if exists:
                return False

            # Создаем новый объект статьи для сохранения
            new_article = Article(
                id=article_id,
                title=article_meta.get('display_name'),
                year=article_meta.get('publication_year'),
                type=article_meta.get('type'),
                language=article_meta.get('language'),
                summary=summary,
                full_metadata=json.dumps(article_meta, ensure_ascii=False)
            )
            
            session.add(new_article)
            session.commit()
            return True
        finally:
            session.close()

    def get_latest_articles(self, limit: int = 10) -> List[Dict]:
        """
        Возвращает N последних добавленных статей из базы данных.
        """
        session = self.Session()
        try:
            latest_articles = session.query(Article).order_by(Article.date_added.desc()).limit(limit).all()
            
            # Преобразуем объекты SQLAlchemy в привычные словари
            return [
                {
                    "id": article.id,
                    "title": article.title,
                    "summary": article.summary,
                    "year": article.year,
                    "url": f"https://openalex.org/{article.id}"
                }
                for article in latest_articles
            ]
        finally:
            session.close()
