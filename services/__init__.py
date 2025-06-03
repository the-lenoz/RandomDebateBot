# services/__init__.py
from .localization import LocalizationService
from .game_logic import GameManager

__all__ = ["LocalizationService", "GameManager"]