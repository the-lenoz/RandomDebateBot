# keyboards/__init__.py
from .reply import (
    get_ui_language_keyboard,
    get_main_menu_keyboard,    # Added
    get_in_queue_keyboard,     # Added
    # get_play_now_keyboard,   # Removed, replaced by main_menu
    get_game_language_keyboard,
    get_role_keyboard,
    get_team_type_keyboard,
    get_after_decline_keyboard # Now returns main_menu
)

__all__ = [
    "get_ui_language_keyboard",
    "get_main_menu_keyboard",    # Added
    "get_in_queue_keyboard",     # Added
    "get_game_language_keyboard",
    "get_role_keyboard",
    "get_team_type_keyboard",
    "get_after_decline_keyboard"
]