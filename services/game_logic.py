# services/game_logic.py
import asyncio
import datetime
import logging
from typing import List, Tuple, Dict, Optional, Any
import pytz

from aiogram import Bot
from aiogram.fsm.context import FSMContext  # Keep for type hinting if methods called from handlers
from aiogram.exceptions import TelegramAPIError
from aiogram.types import ReplyKeyboardRemove  # For removing keyboards when room is ready

from google_integration.meet import create_google_meet_event
from services.localization import LocalizationService
from config import GOOGLE_API_CREDENTIALS_PATH
from keyboards.reply import get_in_queue_keyboard, get_main_menu_keyboard  # Import new keyboards

logger = logging.getLogger(__name__)

UserTuple = Tuple[int, str]
TeamTuple = Tuple[UserTuple, UserTuple]


class GameManager:
    def __init__(self, bot: Bot, ls: LocalizationService):
        self.bot = bot
        self.ls = ls
        self.waiting_single_players: Dict[str, List[UserTuple]] = {"en": [], "ru": []}
        self.waiting_team_first_player: Dict[str, Optional[UserTuple]] = {"en": None, "ru": None}
        self.waiting_formed_teams: Dict[str, List[TeamTuple]] = {"en": [], "ru": []}
        self.waiting_judges: Dict[str, List[UserTuple]] = {"en": [], "ru": []}
        self.active_rooms: List[Dict[str, Any]] = []
        self.user_involvement: Dict[int, Dict[str, Any]] = {}
        self.MAX_PLAYERS_PER_TEAM = 2
        self.TEAMS_PER_ROOM = 4
        self.PLAYERS_PER_ROOM = self.TEAMS_PER_ROOM * self.MAX_PLAYERS_PER_TEAM
        self.JUDGES_PER_ROOM = 1
        self.MEET_DURATION_HOURS = 2.5
        self.TIME_ZONE = 'Europe/Rome'

    def _get_user_info(self, user_id: int, username: Optional[str]) -> UserTuple:
        return (user_id, username if username else f"user{user_id}")

    def _get_game_lang_name(self, game_lang_code: str, ui_lang_code: str) -> str:
        # Use a default if the specific lang_name key isn't found, to prevent crashes
        return self.ls.get_message(ui_lang_code, f"lang_name_{game_lang_code}",
                                   default_game_lang_code=game_lang_code.upper())

    def is_user_occupied(self, user_id: int) -> bool:
        involvement = self.user_involvement.get(user_id)
        if involvement and involvement.get("status") not in [None, "left"]:
            return True
        return False

    def is_user_in_waiting_queue(self, user_id: int) -> bool:
        involvement = self.user_involvement.get(user_id)
        if involvement:
            status = involvement.get("status")
            return status in ["waiting_single", "waiting_team_partner", "waiting_as_team", "waiting_judge"]
        return False

    def get_user_ui_lang(self, user_id: int, default_lang: str = 'en') -> str:
        return self.user_involvement.get(user_id, {}).get("ui_lang", default_lang)

    async def _safe_send_message(self, user_id: int, text: str, **kwargs):
        try:
            await self.bot.send_message(user_id, text, **kwargs)
        except TelegramAPIError as e:
            logger.error(f"Failed to send message to user {user_id}: {e}")
            if "bot was blocked" in str(e).lower() or "user is deactivated" in str(
                    e).lower() or "chat not found" in str(e).lower():
                logger.warning(f"User {user_id} blocked/deactivated/not found. Removing from queues.")
                await self.remove_user_from_queues(user_id, called_from_send_error=True)

    async def add_player_single(self, user_id: int, username: Optional[str], game_lang: str, ui_lang: str):
        if self.is_user_occupied(user_id):  # is_user_occupied also checks for game, but here we focus on queue
            await self._safe_send_message(user_id, self.ls.get_message(ui_lang, "already_in_queue"),
                                          reply_markup=get_in_queue_keyboard(self.ls, ui_lang))
            return False

        user_info = self._get_user_info(user_id, username)
        self.waiting_single_players[game_lang].append(user_info)
        self.user_involvement[user_id] = {"game_lang": game_lang, "role": "player", "status": "waiting_single",
                                          "ui_lang": ui_lang}
        logger.info(f"User {user_id} (@{username}) added as single player [{game_lang}], UI lang [{ui_lang}].")

        await self._notify_player_wait_status_and_set_keyboard(user_id, game_lang, ui_lang)
        asyncio.create_task(self.try_matchmake(game_lang))
        return True

    async def add_player_team(self, user_id: int, username: Optional[str], game_lang: str, ui_lang: str):
        if self.is_user_occupied(user_id):
            await self._safe_send_message(user_id, self.ls.get_message(ui_lang, "already_in_queue"),
                                          reply_markup=get_in_queue_keyboard(self.ls, ui_lang))
            return False

        current_user_info = self._get_user_info(user_id, username)
        first_player_info = self.waiting_team_first_player[game_lang]

        if first_player_info:
            if first_player_info[0] == user_id:
                await self._safe_send_message(user_id, "You cannot be your own teammate.",
                                              reply_markup=get_main_menu_keyboard(self.ls, ui_lang))  # TODO: Localize
                return False

            teammate_id, teammate_username = first_player_info
            new_team: TeamTuple = (first_player_info, current_user_info)
            self.waiting_formed_teams[game_lang].append(new_team)
            self.waiting_team_first_player[game_lang] = None

            teammate_ui_lang = self.get_user_ui_lang(teammate_id, game_lang)
            self.user_involvement[teammate_id].update({"status": "waiting_as_team"})
            self.user_involvement[user_id] = {"game_lang": game_lang, "role": "player", "status": "waiting_as_team",
                                              "ui_lang": ui_lang}
            logger.info(f"Team formed for game lang {game_lang}: {new_team}")

            game_lang_name_teammate = self._get_game_lang_name(game_lang, teammate_ui_lang)
            game_lang_name_user = self._get_game_lang_name(game_lang, ui_lang)

            await self._safe_send_message(teammate_id,
                                          self.ls.get_message(teammate_ui_lang, "team_complete_waiting_room",
                                                              game_lang_name=game_lang_name_teammate),
                                          reply_markup=get_in_queue_keyboard(self.ls, teammate_ui_lang))
            await self._safe_send_message(user_id, self.ls.get_message(ui_lang, "team_complete_waiting_room",
                                                                       game_lang_name=game_lang_name_user),
                                          reply_markup=get_in_queue_keyboard(self.ls, ui_lang))

            # Redundant wait status message if team_complete is sent, but keep for consistency if needed
            # await self._notify_player_wait_status_and_set_keyboard(teammate_id, game_lang, teammate_ui_lang)
            # await self._notify_player_wait_status_and_set_keyboard(user_id, game_lang, ui_lang)

            asyncio.create_task(self.try_matchmake(game_lang))
            return True
        else:
            self.waiting_team_first_player[game_lang] = current_user_info
            self.user_involvement[user_id] = {"game_lang": game_lang, "role": "player",
                                              "status": "waiting_team_partner", "ui_lang": ui_lang}
            logger.info(
                f"User {user_id} (@{username}) is first player of a team [{game_lang}], UI lang [{ui_lang}]. Waiting for partner.")
            game_lang_name = self._get_game_lang_name(game_lang, ui_lang)
            await self._safe_send_message(user_id, self.ls.get_message(ui_lang, "waiting_for_teammate",
                                                                       game_lang_name=game_lang_name),
                                          reply_markup=get_in_queue_keyboard(self.ls, ui_lang))
            return True

    async def add_judge(self, user_id: int, username: Optional[str], game_lang: str, ui_lang: str):
        if self.is_user_occupied(user_id):
            await self._safe_send_message(user_id, self.ls.get_message(ui_lang, "already_in_queue"),
                                          reply_markup=get_in_queue_keyboard(self.ls, ui_lang))
            return False

        user_info = self._get_user_info(user_id, username)
        self.waiting_judges[game_lang].append(user_info)
        self.user_involvement[user_id] = {"game_lang": game_lang, "role": "judge", "status": "waiting_judge",
                                          "ui_lang": ui_lang}
        logger.info(f"User {user_id} (@{username}) added as judge [{game_lang}], UI lang [{ui_lang}].")
        game_lang_name = self._get_game_lang_name(game_lang, ui_lang)
        await self._safe_send_message(user_id,
                                      self.ls.get_message(ui_lang, "waiting_for_judge", game_lang_name=game_lang_name),
                                      reply_markup=get_in_queue_keyboard(self.ls, ui_lang))
        asyncio.create_task(self.try_matchmake(game_lang))
        return True

    async def _notify_player_wait_status_and_set_keyboard(self, user_id: int, game_lang: str, ui_lang: str):
        current_players_in_queue = len(self.waiting_single_players[game_lang]) + \
                                   (1 if self.waiting_team_first_player[game_lang] else 0) + \
                                   len(self.waiting_formed_teams[game_lang]) * self.MAX_PLAYERS_PER_TEAM

        game_lang_name = self._get_game_lang_name(game_lang, ui_lang)
        await self._safe_send_message(user_id, self.ls.get_message(ui_lang, "waiting_for_players",
                                                                   current_players=current_players_in_queue,
                                                                   total_players=self.PLAYERS_PER_ROOM,
                                                                   game_lang_name=game_lang_name),
                                      reply_markup=get_in_queue_keyboard(self.ls, ui_lang))

    def get_waiting_stats(self) -> Dict[str, Any]:
        stats = {
            "rooms_count": len(self.active_rooms),
            "en_single_players": len(self.waiting_single_players["en"]),
            "en_half_teams": 1 if self.waiting_team_first_player["en"] else 0,
            "en_formed_teams": len(self.waiting_formed_teams["en"]),
            "en_formed_teams_players": len(self.waiting_formed_teams["en"]) * self.MAX_PLAYERS_PER_TEAM,
            "en_judges": len(self.waiting_judges["en"]),
            "ru_single_players": len(self.waiting_single_players["ru"]),
            "ru_half_teams": 1 if self.waiting_team_first_player["ru"] else 0,
            "ru_formed_teams": len(self.waiting_formed_teams["ru"]),
            "ru_formed_teams_players": len(self.waiting_formed_teams["ru"]) * self.MAX_PLAYERS_PER_TEAM,
            "ru_judges": len(self.waiting_judges["ru"]),
        }
        total_players_waiting_en = stats["en_single_players"] + stats["en_half_teams"] + stats[
            "en_formed_teams_players"]
        total_players_waiting_ru = stats["ru_single_players"] + stats["ru_half_teams"] + stats[
            "ru_formed_teams_players"]
        stats["total_players_waiting"] = total_players_waiting_en + total_players_waiting_ru
        return stats

    async def try_matchmake(self, game_lang: str):
        logger.info(f"Attempting matchmaking for game language: {game_lang}")

        single_players_pool = self.waiting_single_players[game_lang]
        while len(single_players_pool) >= self.MAX_PLAYERS_PER_TEAM:
            p1_info = single_players_pool.pop(0)
            p2_info = single_players_pool.pop(0)
            new_team: TeamTuple = (p1_info, p2_info)
            self.waiting_formed_teams[game_lang].append(new_team)
            logger.info(f"Formed new team from singles [{game_lang}]: {p1_info[0]} and {p2_info[0]}")

            p1_ui_lang = self.get_user_ui_lang(p1_info[0], game_lang)
            p2_ui_lang = self.get_user_ui_lang(p2_info[0], game_lang)

            self.user_involvement[p1_info[0]]["status"] = "waiting_as_team"
            self.user_involvement[p2_info[0]]["status"] = "waiting_as_team"

            game_lang_name_p1 = self._get_game_lang_name(game_lang, p1_ui_lang)
            game_lang_name_p2 = self._get_game_lang_name(game_lang, p2_ui_lang)

            await self._safe_send_message(p1_info[0],
                                          self.ls.get_message(p1_ui_lang, "paired_with_teammate_notification",
                                                              teammate_username=p2_info[1],
                                                              game_lang_name=game_lang_name_p1),
                                          reply_markup=get_in_queue_keyboard(self.ls, p1_ui_lang))
            await self._safe_send_message(p2_info[0],
                                          self.ls.get_message(p2_ui_lang, "paired_with_teammate_notification",
                                                              teammate_username=p1_info[1],
                                                              game_lang_name=game_lang_name_p2),
                                          reply_markup=get_in_queue_keyboard(self.ls, p2_ui_lang))

            # await self._notify_player_wait_status_and_set_keyboard(p1_info[0], game_lang, p1_ui_lang)
            # await self._notify_player_wait_status_and_set_keyboard(p2_info[0], game_lang, p2_ui_lang)

        available_teams = self.waiting_formed_teams[game_lang]
        available_judges = self.waiting_judges[game_lang]
        logger.info(f"[{game_lang}] Available for room: {len(available_teams)} teams, {len(available_judges)} judges.")

        if len(available_teams) >= self.TEAMS_PER_ROOM and \
                len(available_judges) >= self.JUDGES_PER_ROOM:

            logger.info(f"Sufficient participants to form a room for game language [{game_lang}]")
            selected_teams = [available_teams.pop(0) for _ in range(self.TEAMS_PER_ROOM)]
            selected_judge = available_judges.pop(0)

            try:
                tz = pytz.timezone(self.TIME_ZONE)
            except pytz.UnknownTimeZoneError:
                logger.warning(f"Timezone '{self.TIME_ZONE}' not found, using UTC.")
                tz = pytz.utc
            start_time = datetime.datetime.now(tz)
            end_time = start_time + datetime.timedelta(hours=self.MEET_DURATION_HOURS)

            summary = f"Debate Game Room ({game_lang.upper()})"
            description = f"Debate game. Language: {game_lang.upper()}."

            created_event = create_google_meet_event(
                api_credentials_path=GOOGLE_API_CREDENTIALS_PATH, summary=summary, description=description,
                start_time=start_time, end_time=end_time, time_zone=str(tz), attendees=None
            )

            if created_event and created_event.get('conferenceData', {}).get('entryPoints', [{}])[0].get('uri'):
                meet_link = created_event['conferenceData']['entryPoints'][0]['uri']
                event_id = created_event['id']
                room_id = f"room_{game_lang}_{event_id[:8]}"

                new_room = {"id": room_id, "language": game_lang, "judge": selected_judge,
                            "teams": selected_teams, "meet_link": meet_link,
                            "created_at": datetime.datetime.utcnow()}
                self.active_rooms.append(new_room)

                judge_id, _ = selected_judge
                judge_ui_lang = self.get_user_ui_lang(judge_id, game_lang)
                game_lang_name_judge = self._get_game_lang_name(game_lang, judge_ui_lang)
                await self._safe_send_message(judge_id,
                                              self.ls.get_message(judge_ui_lang, "room_ready_title") + "\n" + \
                                              self.ls.get_message(judge_ui_lang, "room_ready_judge_notification",
                                                                  meet_link=meet_link,
                                                                  game_lang_name=game_lang_name_judge),
                                              reply_markup=ReplyKeyboardRemove()  # Remove queue keyboard, game started
                                              )
                self.user_involvement[judge_id]["status"] = f"in_game_{room_id}"

                for team_idx, team in enumerate(selected_teams):
                    (p1_id, p1_username), (p2_id, p2_username) = team
                    p1_ui_lang = self.get_user_ui_lang(p1_id, game_lang)
                    p2_ui_lang = self.get_user_ui_lang(p2_id, game_lang)

                    game_lang_name_p1 = self._get_game_lang_name(game_lang, p1_ui_lang)
                    game_lang_name_p2 = self._get_game_lang_name(game_lang, p2_ui_lang)

                    await self._safe_send_message(p1_id,
                                                  self.ls.get_message(p1_ui_lang, "room_ready_title") + "\n" + \
                                                  self.ls.get_message(p1_ui_lang, "room_ready_player_notification",
                                                                      teammate_username=p2_username,
                                                                      meet_link=meet_link,
                                                                      game_lang_name=game_lang_name_p1),
                                                  reply_markup=ReplyKeyboardRemove()
                                                  )
                    self.user_involvement[p1_id]["status"] = f"in_game_{room_id}"

                    await self._safe_send_message(p2_id,
                                                  self.ls.get_message(p2_ui_lang, "room_ready_title") + "\n" + \
                                                  self.ls.get_message(p2_ui_lang, "room_ready_player_notification",
                                                                      teammate_username=p1_username,
                                                                      meet_link=meet_link,
                                                                      game_lang_name=game_lang_name_p2),
                                                  reply_markup=ReplyKeyboardRemove()
                                                  )
                    self.user_involvement[p2_id]["status"] = f"in_game_{room_id}"
                logger.info(f"Room {room_id} formed and participants notified.")
                asyncio.create_task(self.try_matchmake(game_lang))
            else:
                logger.error(f"Failed to create Google Meet link for room [{game_lang}]. Reverting selections.")
                self.waiting_formed_teams[game_lang] = selected_teams + self.waiting_formed_teams[game_lang]
                self.waiting_judges[game_lang] = [selected_judge] + self.waiting_judges[game_lang]

                all_failed_participants_ids = [selected_judge[0]] + [p[0] for team in selected_teams for p in team]
                for p_id in all_failed_participants_ids:
                    p_ui_lang = self.get_user_ui_lang(p_id, game_lang)
                    await self._safe_send_message(p_id, self.ls.get_message(p_ui_lang, "error_google_meet"),
                                                  reply_markup=get_in_queue_keyboard(self.ls,
                                                                                     p_ui_lang))  # Stay in queue
        else:
            logger.info(f"Not enough participants to form a room for [{game_lang}]. Waiting.")

    async def remove_user_from_queues(self, user_id: int, called_from_send_error: bool = False) -> bool:
        involvement = self.user_involvement.get(user_id)  # Get current involvement first
        if not involvement:
            if not called_from_send_error:
                # If user isn't in involvement, means they are not in any queue or game.
                # Need a way to get their preferred UI lang if possible, or default.
                # For now, let's assume a default if we can't get it.
                # This case is rare if user interacts normally.
                await self._safe_send_message(user_id, self.ls.get_message('en', "not_in_any_queue"),
                                              reply_markup=get_main_menu_keyboard(self.ls, 'en'))
            logger.info(f"User {user_id} not found in involvement cache. Cannot remove from queues.")
            return False

        # Pop from involvement after getting details, to signify they are being processed for removal
        self.user_involvement.pop(user_id, None)

        game_lang = involvement.get("game_lang")
        status = involvement.get("status")
        leaving_user_ui_lang = involvement.get("ui_lang", "en")
        leaver_username = self._get_user_info(user_id, None)[1]

        logger.info(
            f"Attempting to remove user {user_id} (@{leaver_username}) from queues. Status: {status}, Game Lang: {game_lang}, UI Lang: {leaving_user_ui_lang}")

        removed_flag = False
        teammate_to_notify_info = None

        if str(status).startswith("in_game_"):
            logger.info(f"User {user_id} is in an active game ({status}). Cannot leave queue this way.")
            self.user_involvement[user_id] = involvement  # Put back, as they are still in game
            if not called_from_send_error:
                await self._safe_send_message(user_id, self.ls.get_message(leaving_user_ui_lang, "already_in_queue"),
                                              reply_markup=ReplyKeyboardRemove())  # Game started, no queue keyboard
            return False

        if game_lang:
            if status == "waiting_single":
                self.waiting_single_players[game_lang] = [u for u in self.waiting_single_players[game_lang] if
                                                          u[0] != user_id]
                removed_flag = True
            elif status == "waiting_team_partner":
                if self.waiting_team_first_player[game_lang] and self.waiting_team_first_player[game_lang][
                    0] == user_id:
                    self.waiting_team_first_player[game_lang] = None
                    removed_flag = True
            elif status == "waiting_as_team":
                team_to_remove_idx = -1
                teammate_info_tuple = None
                for i, team_tuple_iter in enumerate(self.waiting_formed_teams[game_lang]):
                    p1_info, p2_info = team_tuple_iter
                    if user_id == p1_info[0]:
                        team_to_remove_idx = i
                        teammate_info_tuple = p2_info
                        break
                    elif user_id == p2_info[0]:
                        team_to_remove_idx = i
                        teammate_info_tuple = p1_info
                        break

                if team_to_remove_idx != -1:
                    self.waiting_formed_teams[game_lang].pop(team_to_remove_idx)
                    removed_flag = True
                    if teammate_info_tuple:
                        teammate_id, teammate_username_val = teammate_info_tuple
                        if teammate_id in self.user_involvement:
                            self.user_involvement[teammate_id]["status"] = "waiting_single"
                            self.waiting_single_players[game_lang].append(teammate_info_tuple)
                            teammate_ui_lang = self.user_involvement[teammate_id].get("ui_lang", game_lang)
                            teammate_to_notify_info = (teammate_id, teammate_username_val, teammate_ui_lang)
                            logger.info(f"Teammate {teammate_id} of {user_id} moved to single queue for {game_lang}.")
                        else:
                            logger.info(f"Teammate {teammate_id} of {user_id} not in involvement, no action for them.")
            elif status == "waiting_judge":
                self.waiting_judges[game_lang] = [u for u in self.waiting_judges[game_lang] if u[0] != user_id]
                removed_flag = True

        main_menu_for_leaver = get_main_menu_keyboard(self.ls, leaving_user_ui_lang)

        if removed_flag:
            logger.info(f"User {user_id} successfully removed from specific queue.")
            if not called_from_send_error:
                await self._safe_send_message(user_id,
                                              self.ls.get_message(leaving_user_ui_lang, "successfully_left_queue"),
                                              reply_markup=main_menu_for_leaver)

            if teammate_to_notify_info:
                tid, t_user, t_ui_lang = teammate_to_notify_info
                game_lang_name_for_teammate = self._get_game_lang_name(game_lang, t_ui_lang)
                await self._safe_send_message(tid, self.ls.get_message(t_ui_lang, "teammate_left_notification",
                                                                       leaver_username=leaver_username,
                                                                       game_lang_name=game_lang_name_for_teammate),
                                              reply_markup=get_in_queue_keyboard(self.ls,
                                                                                 t_ui_lang))  # Teammate gets in-queue kbd
                # await self._notify_player_wait_status_and_set_keyboard(tid, game_lang, t_ui_lang) # Covered by above

            if game_lang:
                asyncio.create_task(self.try_matchmake(game_lang))
        else:  # Not removed from a specific queue (e.g. only chose UI lang, or was in game)
            if not str(status).startswith("in_game_"):  # If not in game
                logger.warning(
                    f"User {user_id} was in involvement but not found in an expected queue. Status: '{status}', GameLang: '{game_lang}'.")
                if not called_from_send_error:
                    await self._safe_send_message(user_id,
                                                  self.ls.get_message(leaving_user_ui_lang, "not_in_any_queue"),
                                                  reply_markup=main_menu_for_leaver)
        return removed_flag