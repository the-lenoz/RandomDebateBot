# handlers/__init__.py
from .common import common_router
from .game_setup import game_setup_router

__all__ = ["common_router", "game_setup_router"]