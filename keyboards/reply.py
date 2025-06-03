# keyboards/reply.py
from aiogram.types import ReplyKeyboardMarkup
from aiogram.utils.keyboard import ReplyKeyboardBuilder

from services.localization import LocalizationService

def get_ui_language_keyboard(ls: LocalizationService) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=ls.get_message("en", "lang_en"))
    builder.button(text=ls.get_message("ru", "lang_ru"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def get_main_menu_keyboard(ls: LocalizationService, ui_lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=ls.get_message(ui_lang, "play_button"))
    builder.button(text=ls.get_message(ui_lang, "stats_button"))
    builder.adjust(1) # Play on top, Stats below it
    return builder.as_markup(resize_keyboard=True) # Persistent menu

def get_in_queue_keyboard(ls: LocalizationService, ui_lang: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=ls.get_message(ui_lang, "leave_queue_button"))
    builder.button(text=ls.get_message(ui_lang, "stats_button")) # Can still view stats while in queue
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True) # Persistent while in queue

# This keyboard is now less used, main menu is preferred after "Not now"
def get_after_decline_keyboard(ls: LocalizationService, ui_lang: str) -> ReplyKeyboardMarkup:
    return get_main_menu_keyboard(ls, ui_lang) # Show main menu after declining

# These keyboards are for specific steps and should be one-time
def get_game_language_keyboard(ls: LocalizationService) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=ls.get_message("en", "lang_en"))
    builder.button(text=ls.get_message("ru", "lang_ru"))
    builder.adjust(2)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def get_role_keyboard(ls: LocalizationService, ui_lang: str, game_lang_for_buttons: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=ls.get_message(game_lang_for_buttons, "role_player"))
    builder.button(text=ls.get_message(game_lang_for_buttons, "role_judge"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

def get_team_type_keyboard(ls: LocalizationService, ui_lang: str, game_lang_for_buttons: str) -> ReplyKeyboardMarkup:
    builder = ReplyKeyboardBuilder()
    builder.button(text=ls.get_message(game_lang_for_buttons, "team_type_single"))
    builder.button(text=ls.get_message(game_lang_for_buttons, "team_type_team"))
    builder.adjust(1)
    return builder.as_markup(resize_keyboard=True, one_time_keyboard=True)

# Replaces get_play_now_keyboard, as "Play" is part of main menu
# If a specific "Play/Not Now" prompt is absolutely needed distinct from main menu,
# you can re-introduce a variant of get_play_now_keyboard.
# For now, assuming main menu covers the "Play" initiation.