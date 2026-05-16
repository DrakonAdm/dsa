from typing import List
import time
from deep_translator import GoogleTranslator
from deep_translator.exceptions import TranslationNotFound, TooManyRequests

class TranslationService:
    def __init__(self):
        pass

    def translate_list(self, texts: List[str], src_lang: str = 'ru', dest_lang: str = 'en') -> List[str]:
        """
        Переводит список строк.
        :param texts: Список строк для перевода
        :param src_lang: Язык оригинала (например, 'ru' или 'auto')
        :param dest_lang: Язык перевода (например, 'en')
        :return: Список переведённых строк
        """
        if not texts:
            return []

        # Создаём переводчик с нужными языками для текущего вызова
        translator = GoogleTranslator(source=src_lang, target=dest_lang)
        translated = []

        for text in texts:
            try:
                # deep_translator.translate() сразу возвращает строку
                result = translator.translate(text)
                translated.append(result)
                
                # Задержка для снижения риска rate-limit от Google
                time.sleep(0.1)
                
            except (TranslationNotFound, TooManyRequests, Exception) as e:
                print(f"Ошибка перевода '{text}': {e}")
                translated.append(text)  # Возвращаем оригинал при ошибке
                
        return translated

    def translate_split_by_dot(self, text: str, src_lang: str = 'ru', dest_lang: str = 'en') -> List[str]:
        """
        Разбивает строку по точке, переводит каждую часть и возвращает список переводов.
        """
        if not text or not text.strip():
            return []

        parts = [part.strip() for part in text.split('.') if part.strip()]
        return self.translate_list(parts, src_lang, dest_lang)