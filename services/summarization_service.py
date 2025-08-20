# services/summarization_service.py
import os
from gigachat import GigaChat
from gigachat.models import Chat
from typing import Optional

class AdvancedSummarizer:
    def __init__(self):
        credentials = os.getenv('GIGACHAT_CREDENTIALS')
        if not credentials: raise ValueError("Не найден GIGACHAT_CREDENTIALS")
        self.giga = GigaChat(credentials=credentials, verify_ssl_certs=False)

    def _get_completion(self, prompt: str, temp: float, tokens: int) -> Optional[str]:
        try:
            payload = Chat(messages=[{"role": "user", "content": prompt}], temperature=temp, max_tokens=tokens)
            resp = self.giga.chat(payload)
            return resp.choices[0].message.content.strip() if resp and resp.choices else None
        except Exception as e:
            print(f"❌ Ошибка API: {e}"); return None

    def summarize_abstract(self, abstract: str, template: str, theme: str) -> Optional[str]:
        prompt = template.format(article_text=abstract, theme_name=theme)
        return self._get_completion(prompt, temp=0.6, tokens=500)

    def summarize_full_text(self, text: str, extraction_template: str, synthesis_template: str, theme: str) -> Optional[str]:
        """Конвейер: Сборщик фактов -> Журналист."""
        print("      [Шаг 1/2] Извлечение фактов для журналиста...")
        p1 = extraction_template.format(article_text=text[:20000])
        facts = self._get_completion(p1, temp=0.1, tokens=1000)
        if not facts: 
            print("      -> Ошибка на шаге 1."); return None

        print("      [Шаг 2/2] Написание новостной заметки...")
        p2 = synthesis_template.format(extracted_facts=facts)
        final_summary = self._get_completion(p2, temp=0.7, tokens=800)
        if not final_summary:
            print("      -> Ошибка на шаге 2."); return None
        
        return final_summary
