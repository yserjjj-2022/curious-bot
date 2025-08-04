# -*- coding: utf-8 -*-

import os
from gigachat import GigaChat
from gigachat.models import Chat
from typing import Optional

class GigaService:
    """
    Сервис-обертка для удобной работы с API GigaChat.
    Инкапсулирует в себе всю логику аутентификации и отправки запросов.
    """
    def __init__(self):
        """
        Инициализирует клиент GigaChat, подтягивая креды из .env файла.
        """
        credentials = os.getenv('GIGACHAT_CREDENTIALS')
        if not credentials:
            raise ValueError("КРИТИЧЕСКАЯ ОШИБКА: Не найден GIGACHAT_CREDENTIALS в переменных окружения!")
        
        try:
            # verify_ssl_certs=False нужно для работы на некоторых системах, где есть проблемы с сертификатами
            self.giga = GigaChat(credentials=credentials, verify_ssl_certs=False)
        except Exception as e:
            raise ConnectionError(f"Не удалось подключиться к GigaChat. Проверьте креды и сетевое соединение. Ошибка: {e}")

    def get_completion(self, prompt: str, temperature: float = 0.7, max_tokens: int = 1024) -> Optional[str]:
        """
        Отправляет промпт в GigaChat и возвращает ответ модели.
        """
        if not prompt:
            return None

        try:
            payload = Chat(
                messages=[
                    {"role": "user", "content": prompt},
                ],
                temperature=temperature,
                max_tokens=max_tokens,
            )
            response = self.giga.chat(payload)
            
            if response.choices and response.choices[0].message.content:
                return response.choices[0].message.content.strip()
            return None

        except Exception as e:
            print(f"❌ Ошибка при обращении к GigaChat API: {e}")
            return None

