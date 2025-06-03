# handlers/game_setup.py
from aiogram import Router, F
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from keyboards.reply import (get_role_keyboard, get_team_type_keyboard,
                             get_game_language_keyboard, get_main_menu_keyboard)  # Added main_menu and in_queue
from services.game_logic import GameManager
from services.localization import LocalizationService
from states.user_states import GameSetup
from .common import get_initial_user_lang  # import send_main_menu

game_setup_router = Router()


def _get_game_lang_name_from_code(ls: LocalizationService, game_lang_code: str, ui_lang_code: str) -> str:
    return ls.get_message(ui_lang_code, f"lang_name_{game_lang_code}", default_game_lang_code=game_lang_code.upper())


@game_setup_router.message(GameSetup.choosing_game_language, F.text)
async def game_language_chosen(message: Message, state: FSMContext, ls: LocalizationService, game_manager: GameManager):
    chosen_game_lang_text = message.text
    user_id = message.from_user.id  # Not used directly here, but good practice

    data = await state.get_data()
    ui_lang = data.get("ui_language", game_manager.get_user_ui_lang(user_id, get_initial_user_lang(message, ls)))

    actual_game_lang_code = None
    if chosen_game_lang_text == ls.get_message("en", "lang_en"):
        actual_game_lang_code = "en"
    elif chosen_game_lang_text == ls.get_message("ru", "lang_ru"):
        actual_game_lang_code = "ru"

    if actual_game_lang_code:
        await state.update_data(game_language=actual_game_lang_code)
        await message.answer(ls.get_message(ui_lang, "choose_role"),
                             reply_markup=get_role_keyboard(ls, ui_lang, actual_game_lang_code))
        await state.set_state(GameSetup.choosing_role)
    else:
        await message.reply(ls.get_message(ui_lang, "choose_language_again"),
                            reply_markup=get_game_language_keyboard(ls))  # Re-prompt for game lang


@game_setup_router.message(GameSetup.choosing_role, F.text)
async def role_chosen(message: Message, state: FSMContext, ls: LocalizationService, game_manager: GameManager):
    chosen_role_text = message.text
    data = await state.get_data()
    ui_lang = data.get("ui_language")
    game_lang_code = data.get("game_language")

    user_id = message.from_user.id
    username = message.from_user.username or f"user{user_id}"

    if not ui_lang or not game_lang_code:
        fallback_ui_lang = game_manager.get_user_ui_lang(user_id, get_initial_user_lang(message, ls))
        await message.answer(ls.get_message(fallback_ui_lang, "generic_error") + " (State error)",
                             reply_markup=get_main_menu_keyboard(ls, fallback_ui_lang))
        await state.clear()
        return

    role_player_text = ls.get_message(game_lang_code, "role_player")
    role_judge_text = ls.get_message(game_lang_code, "role_judge")
    game_lang_name = _get_game_lang_name_from_code(ls, game_lang_code, ui_lang)

    if chosen_role_text == role_player_text:
        await state.update_data(role="player")
        await message.answer(ls.get_message(ui_lang, "choose_team_type"),
                             reply_markup=get_team_type_keyboard(ls, ui_lang, game_lang_code))
        await state.set_state(GameSetup.choosing_team_type)
    elif chosen_role_text == role_judge_text:
        await state.update_data(role="judge")
        await message.answer(ls.get_message(ui_lang, "adding_to_judge_queue", game_lang_name=game_lang_name),
                             reply_markup=ReplyKeyboardRemove())  # Temporarily remove while processing
        success = await game_manager.add_judge(user_id, username, game_lang_code, ui_lang)
        if success:
            await state.clear()  # game_manager.add_judge now sends in_queue_keyboard
        else:  # Failed to add (e.g., already in queue), game_manager sent message with in_queue_keyboard
            await state.clear()  # Clear FSM, user is already handled by game_manager
            # Potentially resend main/in_queue if game_manager didn't, but it should.
    else:
        await message.reply(ls.get_message(ui_lang, "choose_role_again", game_lang_name=game_lang_name),
                            reply_markup=get_role_keyboard(ls, ui_lang, game_lang_code))


@game_setup_router.message(GameSetup.choosing_team_type, F.text)
async def team_type_chosen(message: Message, state: FSMContext, ls: LocalizationService, game_manager: GameManager):
    chosen_team_type_text = message.text
    data = await state.get_data()
    ui_lang = data.get("ui_language")
    game_lang_code = data.get("game_language")

    user_id = message.from_user.id
    username = message.from_user.username or f"user{user_id}"

    if not ui_lang or not game_lang_code:
        fallback_ui_lang = game_manager.get_user_ui_lang(user_id, get_initial_user_lang(message, ls))
        await message.answer(ls.get_message(fallback_ui_lang, "generic_error") + " (State error)",
                             reply_markup=get_main_menu_keyboard(ls, fallback_ui_lang))
        await state.clear()
        return

    team_type_single_text = ls.get_message(game_lang_code, "team_type_single")
    team_type_team_text = ls.get_message(game_lang_code, "team_type_team")
    game_lang_name = _get_game_lang_name_from_code(ls, game_lang_code, ui_lang)

    await message.answer(ls.get_message(ui_lang, "processing_request"),
                         reply_markup=ReplyKeyboardRemove())  # Temp remove

    success = False
    if chosen_team_type_text == team_type_single_text:
        success = await game_manager.add_player_single(user_id, username, game_lang_code, ui_lang)
    elif chosen_team_type_text == team_type_team_text:
        success = await game_manager.add_player_team(user_id, username, game_lang_code, ui_lang)
    else:
        await message.reply(ls.get_message(ui_lang, "choose_team_type_again", game_lang_name=game_lang_name),
                            reply_markup=get_team_type_keyboard(ls, ui_lang, game_lang_code))

    if success:
        await state.clear()  # game_manager methods now send in_queue_keyboard
    else:  # Failed to add, game_manager sent message with in_queue_keyboard or main_menu_keyboard
        await state.clear()  # Clear FSM, user handled by game_manager