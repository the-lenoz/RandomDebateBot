# states/user_states.py
from aiogram.fsm.state import State, StatesGroup

class GameSetup(StatesGroup):
    choosing_ui_language = State() # New state for UI language
    choosing_game_language = State() # Renamed for clarity
    choosing_role = State()
    choosing_team_type = State()