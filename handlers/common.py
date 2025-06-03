# handlers/common.py
from aiogram import Router, F
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.types import Message, ReplyKeyboardRemove

from keyboards.reply import (get_main_menu_keyboard, get_game_language_keyboard,
                             get_ui_language_keyboard,
                             get_in_queue_keyboard)  # Added get_in_queue_keyboard
from services.game_logic import GameManager
from services.localization import LocalizationService
from states.user_states import GameSetup

common_router = Router()


def get_initial_user_lang(message: Message, ls: LocalizationService) -> str:
    if message.from_user and message.from_user.language_code:
        lang_code = message.from_user.language_code.split('-')[0]
        if lang_code in ls.translations:
            return lang_code
    return 'en'


async def send_main_menu(message: Message, ls: LocalizationService, ui_lang: str, game_manager: GameManager):
    if game_manager.is_user_in_waiting_queue(message.from_user.id):
        await message.answer(
            ls.get_message(ui_lang, "in_queue_menu_prompt"),
            reply_markup=get_in_queue_keyboard(ls, ui_lang)
        )
    else:
        # stats = game_manager.get_waiting_stats() # Not needed for main menu prompt usually
        await message.answer(
            ls.get_message(ui_lang, "main_menu_prompt"),  # A generic main menu prompt
            reply_markup=get_main_menu_keyboard(ls, ui_lang)
        )


@common_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, ls: LocalizationService, game_manager: GameManager):
    await state.clear()
    initial_lang = get_initial_user_lang(message, ls)
    await state.update_data(detected_telegram_lang=initial_lang)

    # Store or update UI lang in game_manager for this user, even before they choose
    # This helps if they use /leave or /online immediately.
    # However, this might be premature if they never complete UI lang selection.
    # For now, rely on FSM state first, then game_manager cache.
    # game_manager.user_involvement.setdefault(message.from_user.id, {}).update({"ui_lang": initial_lang})

    await message.answer(ls.get_message(initial_lang, "start_greeting"))
    await message.answer(
        ls.get_message(initial_lang, "choose_ui_language"),
        reply_markup=get_ui_language_keyboard(ls)
    )
    await state.set_state(GameSetup.choosing_ui_language)


@common_router.message(GameSetup.choosing_ui_language, F.text)
async def ui_language_chosen_handler(message: Message, state: FSMContext, ls: LocalizationService,
                                     game_manager: GameManager):
    chosen_lang_text = message.text
    user_id = message.from_user.id

    selected_ui_lang_code = None
    lang_name_for_confirmation = "English"

    if chosen_lang_text == ls.get_message("en", "lang_en"):
        selected_ui_lang_code = "en"
        lang_name_for_confirmation = ls.get_message("en", "lang_name_en")
    elif chosen_lang_text == ls.get_message("ru", "lang_ru"):
        selected_ui_lang_code = "ru"
        lang_name_for_confirmation = ls.get_message("ru", "lang_name_ru")

    if selected_ui_lang_code:
        await state.update_data(ui_language=selected_ui_lang_code)
        game_manager.user_involvement.setdefault(user_id, {}).update({"ui_lang": selected_ui_lang_code})

        await message.answer(
            ls.get_message(selected_ui_lang_code, "ui_language_chosen", lang_name=lang_name_for_confirmation),
            reply_markup=ReplyKeyboardRemove()  # Remove UI lang choice keyboard specifically
        )
        await state.set_state(None)
        await send_main_menu(message, ls, selected_ui_lang_code, game_manager)  # Show main menu
    else:
        data = await state.get_data()
        fallback_lang = data.get("detected_telegram_lang", "en")
        await message.reply(ls.get_message(fallback_lang, "choose_ui_language"),
                            reply_markup=get_ui_language_keyboard(ls))


async def start_game_setup_flow(message: Message, state: FSMContext, ls: LocalizationService,
                                game_manager: GameManager):
    user_id = message.from_user.id
    data = await state.get_data()
    ui_lang = data.get("ui_language", game_manager.get_user_ui_lang(user_id, get_initial_user_lang(message, ls)))

    current_state_val = await state.get_state()
    if current_state_val not in [None, GameSetup.choosing_ui_language.state]:
        if current_state_val != GameSetup.choosing_ui_language.state:
            await message.answer(ls.get_message(ui_lang, "command_in_progress"),
                                 reply_markup=get_in_queue_keyboard(ls,
                                                                    ui_lang) if game_manager.is_user_in_waiting_queue(
                                     user_id) else ReplyKeyboardRemove())
            return

    if game_manager.is_user_occupied(user_id):  # Checks both queue and game
        await message.answer(ls.get_message(ui_lang, "already_in_queue"),
                             reply_markup=get_in_queue_keyboard(ls, ui_lang) if game_manager.is_user_in_waiting_queue(
                                 user_id) else ReplyKeyboardRemove())
        return

    if not data.get("ui_language"):
        initial_lang = data.get("detected_telegram_lang", get_initial_user_lang(message, ls))
        await message.answer(
            ls.get_message(initial_lang, "choose_ui_language"),
            reply_markup=get_ui_language_keyboard(ls)
        )
        await state.set_state(GameSetup.choosing_ui_language)
        return

    await message.answer(ls.get_message(ui_lang, "choose_language"),
                         reply_markup=get_game_language_keyboard(ls))
    await state.set_state(GameSetup.choosing_game_language)


@common_router.message(Command("play"))  # Handles /play command directly
async def cmd_play_command(message: Message, state: FSMContext, ls: LocalizationService, game_manager: GameManager):
    await start_game_setup_flow(message, state, ls, game_manager)


@common_router.message(Command("online"))
async def cmd_online(message: Message, state: FSMContext, ls: LocalizationService, game_manager: GameManager):
    data = await state.get_data()
    ui_lang = data.get("ui_language",
                       game_manager.get_user_ui_lang(message.from_user.id, get_initial_user_lang(message, ls)))
    stats_data = game_manager.get_waiting_stats()

    await message.answer(ls.get_message(ui_lang, "online_stats", **stats_data))
    # Do not remove main menu, just send stats above it.
    # If a specific menu was active due to FSM, it might be an issue, but for /online, assume general context.
    # If user is in queue, their in_queue_keyboard should persist. If not, main_menu should.
    # ReplyKeyboardRemove() is NOT called here.


@common_router.message(Command("leave"))
async def cmd_leave_command(message: Message, state: FSMContext, ls: LocalizationService, game_manager: GameManager):
    user_id = message.from_user.id
    await state.clear()  # Clear FSM state regardless of queue status first

    fsm_data = await state.get_data()  # FSM data is now empty
    ui_lang = game_manager.get_user_ui_lang(user_id, get_initial_user_lang(message, ls))  # Get from GM or default

    await game_manager.remove_user_from_queues(user_id)
    # remove_user_from_queues handles sending "successfully_left_queue" or "not_in_any_queue"
    # and sets the main_menu_keyboard. So, no extra message here needed typically.
    # If FSM was active, a "process cancelled" could be added, but remove_user already shows success.


# Handler for main menu buttons and other text when no specific game setup FSM state is active.
@common_router.message(F.text, StateFilter(None))
async def handle_main_menu_buttons(message: Message, state: FSMContext, ls: LocalizationService,
                                   game_manager: GameManager):
    user_id = message.from_user.id
    data = await state.get_data()
    ui_lang = data.get("ui_language", game_manager.get_user_ui_lang(user_id, get_initial_user_lang(message, ls)))

    # Check against localized button texts
    play_button_text = ls.get_message(ui_lang, "play_button")
    stats_button_text = ls.get_message(ui_lang, "stats_button")
    leave_queue_button_text = ls.get_message(ui_lang, "leave_queue_button")
    # "Not now" is less relevant if we always show main menu
    # not_now_button_text_current_ui = ls.get_message(ui_lang, "not_now_button")

    if message.text == play_button_text:
        await start_game_setup_flow(message, state, ls, game_manager)
    elif message.text == stats_button_text:
        await cmd_online(message, state, ls, game_manager)  # Call existing stats handler
    elif message.text == leave_queue_button_text:
        await cmd_leave_command(message, state, ls, game_manager)  # Call existing leave handler
    # elif message.text == not_now_button_text_current_ui:
    #     await message.answer(
    #         ls.get_message(ui_lang, "not_now_response"),
    #         reply_markup=get_main_menu_keyboard(ls, ui_lang) # Show main menu
    #     )
    else:
        # Unknown command when no state, show main menu
        await send_main_menu(message, ls, ui_lang, game_manager)