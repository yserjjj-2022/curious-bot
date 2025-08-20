# services/text_utils.py

import re

# --- Легкая очистка остается без изменений ---
def cleanup_extracted_text(text: str) -> str:
    """
    Легкая очистка для текста, полученного из PDF/HTML.
    Главная задача - отрезать "хвост".
    """
    if not text:
        return ""

    lines = text.splitlines()
    cut_off_index = -1
    
    stop_words_lower = [
        'references', 'bibliography', 'data availability statement', 'ethics statement', 
        'author contributions', 'funding', 'conflict of interest', 'supplementary material', 
        'publisher’s note', 'acknowledgement', 'acknowledgements', 'literaturverzeichnis', 
        'bibliographie', 'referencias', 'bibliografia', 'daftar pustaka', 'список литературы', 
        'список источников', 'источники', 'literature cited', 'works cited'
    ]

    for i, line in enumerate(lines):
        if line.strip().lower() in stop_words_lower:
            cut_off_index = i
            break

    if cut_off_index != -1:
        lines = lines[:cut_off_index]
        
    clean_text = "\n".join(lines)
    
    lines = (line.strip() for line in clean_text.splitlines())
    return "\n".join(line for line in lines if line)


# --- ИЗМЕНЕНИЕ: Ультимативная, безопасная "тяжелая" очистка ---
def cleanup_summary_text(text: str) -> str:
    """
    Безопасная очистка для текста, полученного от GigaChat.
    Удаляет ТОЛЬКО Markdown, не трогая другие символы.
    """
    if not text:
        return ""
    
    # 1. Механически удаляем жирный шрифт
    clean_text = text.replace('**', '')
    
    # 2. Механически удаляем строки, похожие на заголовки или разделители
    lines = clean_text.splitlines()
    cleaned_lines = []
    for line in lines:
        stripped_line = line.strip()
        if stripped_line.startswith(('#', '---')):
            continue
        cleaned_lines.append(line)
    clean_text = "\n".join(cleaned_lines)
    
    # 3. Финальная очистка пустых строк
    lines = (line.strip() for line in clean_text.splitlines())
    return "\n".join(line for line in lines if line)

