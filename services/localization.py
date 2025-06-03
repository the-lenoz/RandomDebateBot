# services/localization.py
import json
import os
from typing import Dict, Any
import logging

logger = logging.getLogger(__name__)


class LocalizationService:
    def __init__(self, locales_dir="locales"):
        self.locales_dir = locales_dir
        self.translations: Dict[str, Dict[str, str]] = {}
        self._load_translations()

    def _load_translations(self):
        if not os.path.isdir(self.locales_dir):
            logger.error(f"Locales directory not found: {os.path.abspath(self.locales_dir)}")
            return

        for lang_file in os.listdir(self.locales_dir):
            if lang_file.startswith("messages_") and lang_file.endswith(".json"):
                lang_code = lang_file.replace("messages_", "").replace(".json", "")
                file_path = os.path.join(self.locales_dir, lang_file)
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        self.translations[lang_code] = json.load(f)
                    logger.info(f"Loaded translation file: {file_path} for lang '{lang_code}'")
                except Exception as e:
                    logger.error(f"Error loading translation file {file_path}: {e}")

        if not self.translations:
            logger.warning("No translations were loaded. Check locales directory and file naming.")

    def get_message(self, lang: str, key: str, **kwargs) -> str:
        # Try to get message in the requested language
        if lang in self.translations and key in self.translations[lang]:
            message_template = self.translations[lang][key]
        # Fallback to English if key or lang not found in requested language
        elif "en" in self.translations and key in self.translations["en"]:
            logger.warning(f"Key '{key}' not found for lang '{lang}'. Falling back to 'en'.")
            message_template = self.translations["en"].get(key, f"Untranslated_EN: {key}")
        # Absolute fallback if key not even in English
        else:
            logger.error(f"Key '{key}' not found for lang '{lang}' and no 'en' fallback available.")
            return f"FATAL_MISSING_TRANSLATION: {lang}.{key}"

        try:
            return message_template.format(**kwargs)
        except KeyError as e:
            logger.error(
                f"Missing format key {e} for message {lang}.{key} with template '{message_template}' and args {kwargs}")
            return message_template  # Return unformatted message to avoid crashing