# main.py
import asyncio
import logging

from aiogram import Bot, Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.enums import ParseMode

from config import BOT_TOKEN
from services.localization import LocalizationService
from services.game_logic import GameManager
from handlers import common_router, game_setup_router

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s.%(funcName)s:%(lineno)d - %(message)s'
)
logger = logging.getLogger(__name__)


async def main():
    if not BOT_TOKEN:
        logger.critical("BOT_TOKEN is not configured. Exiting.")
        return

    bot = Bot(token=BOT_TOKEN)  # Using HTML parse mode for potential future formatting
    storage = MemoryStorage()
    dp = Dispatcher(storage=storage)

    # Initialize services
    # Ensure locales folder is in the same directory as main.py or adjust path in LocalizationService
    ls = LocalizationService(locales_dir="locales")
    if not ls.translations:
        logger.warning(
            "No translations loaded. Bot might not respond with proper text. Check 'locales' folder and file names (messages_en.json, messages_ru.json).")

    game_manager = GameManager(bot=bot, ls=ls)

    # Pass ls and game_manager to handlers via dispatcher context
    dp["ls"] = ls
    dp["game_manager"] = game_manager
    # bot instance is automatically passed if type-hinted in handlers

    # Register routers.
    # Routers with state handlers (like game_setup_router) should ideally be registered
    # before more generic ones if there's any overlap in non-state filters.
    # However, aiogram's FSM handles state-specific handlers with higher priority.
    dp.include_router(game_setup_router)
    dp.include_router(common_router)

    logger.info("Bot starting polling...")
    try:
        # Remove any pending updates
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())
    except Exception as exception:
        logger.critical(f"Critical error during polling: {exception}", exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Bot stopped.")


if __name__ == '__main__':
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        logger.info("Bot execution interrupted by user (Ctrl+C).")
    except Exception as e:
        logger.critical(f"Unhandled exception at top level: {e}", exc_info=True)