import json
import time
from pathlib import Path
from datetime import datetime

from endstone.plugin import Plugin
from endstone.command import CommandSender
from endstone import Player
from endstone.event import event_handler, PlayerJoinEvent, PlayerQuitEvent, PlayerChatEvent


class GroupChatPlugin(Plugin):
    api_version = "0.5"

    # ========== РАНГИ ==========
    ranks = {
        "stuff": {
            "display": "§d§lSTUFF",
            "name_color": "§d§l",
            "chat_format": "§8§l[§d§lSTUFF§8§l] §d§l{name} §8§l» §f{msg}",
            "permissions": ["groupchat.stuff", "groupchat.admin", "groupchat.helper", "groupchat.modern", "groupchat.chat"],
            "menu_perms": ["players", "ranks", "setrank", "delrank", "color", "prefix", "invsee", "clear_prefix", "trash", "settings"]
        },
        "admin": {
            "display": "§c§lAdmin",
            "name_color": "§c§l",
            "chat_format": "§8§l[§c§lAdmin§8§l] §c§l{name} §8§l» §f{msg}",
            "permissions": ["groupchat.admin", "groupchat.helper", "groupchat.modern", "groupchat.chat"],
            "menu_perms": ["players", "ranks", "color", "prefix", "invsee", "clear_prefix", "trash", "settings"]
        },
        "helper": {
            "display": "§a§lHelper",
            "name_color": "§a§l",
            "chat_format": "§8§l[§a§lHelper§8§l] §a§l{name} §8§l» §f{msg}",
            "permissions": ["groupchat.helper", "groupchat.modern", "groupchat.chat"],
            "menu_perms": ["players", "ranks", "color", "prefix", "clear_prefix", "trash", "settings"]
        },
        "builder": {
            "display": "§e§lBuilder",
            "name_color": "§e§l",
            "chat_format": "§8§l[§e§lBuilder§8§l] §e§l{name} §8§l» §f{msg}",
            "permissions": ["groupchat.modern", "groupchat.chat", "worldedit.*"],
            "menu_perms": ["players", "ranks", "color", "prefix", "clear_prefix", "trash", "settings"]
        },
        "moder": {
            "display": "§b§lModer",
            "name_color": "§b§l",
            "chat_format": "§8§l[§b§lModer§8§l] §b§l{name} §8§l» §f{msg}",
            "permissions": ["groupchat.modern", "groupchat.chat"],
            "menu_perms": ["players", "ranks", "trash", "settings"]
        },
        "player": {
            "display": "§7Игрок",
            "name_color": "§7",
            "chat_format": "§8[§7Игрок§8] §7{name} §8» §f{msg}",
            "permissions": ["groupchat.chat"],
            "menu_perms": ["players", "ranks", "trash", "settings"]
        },
    }

    COLORS = {
        "red": "§c", "green": "§a", "blue": "§9", "gold": "§6",
        "yellow": "§e", "aqua": "§b", "pink": "§d", "white": "§f",
        "gray": "§7", "dark_red": "§4", "dark_green": "§2",
        "dark_blue": "§1", "black": "§0"
    }

    RANK_HIERARCHY = ["stuff", "admin", "helper", "builder", "moder", "player"]

    def on_enable(self):
        self.logger.info("GroupChat core enabled!")
        self.player_ranks = {}
        self.player_data = {}
        self.known_players = {}
        self.data_path = Path(self.data_folder)
        self.data_path.mkdir(exist_ok=True)

        # Загрузка данных
        self.ranks_file = self.data_path / "ranks.json"
        if self.ranks_file.exists():
            self.player_ranks = json.loads(self.ranks_file.read_text("utf-8"))

        self.player_file = self.data_path / "players.json"
        if self.player_file.exists():
            self.player_data = json.loads(self.player_file.read_text("utf-8"))

        self.players_list_file = self.data_path / "known_players.json"
        if self.players_list_file.exists():
            data = json.loads(self.players_list_file.read_text("utf-8"))
            self.known_players = {name: {"first_join": "неизвестно", "last_join": "неизвестно"} for name in data} if isinstance(data, list) else data

        self.register_events(self)
        self._schedule_announce()

        self.restart_file = self.data_path / "restart.json"
        if self.restart_file.exists():
            self._last_restart = json.loads(self.restart_file.read_text("utf-8")).get("time", "неизвестно")
            self.restart_file.unlink()
        else:
            self._last_restart = None

    def _save(self):
        self.ranks_file.write_text(json.dumps(self.player_ranks, ensure_ascii=False, indent=2), "utf-8")
        self.player_file.write_text(json.dumps(self.player_data, ensure_ascii=False, indent=2), "utf-8")
        self.players_list_file.write_text(json.dumps(self.known_players, ensure_ascii=False, indent=2), "utf-8")

    def on_disable(self):
        self.restart_file.write_text(json.dumps({"time": datetime.now().strftime("%H:%M")}, ensure_ascii=False), "utf-8")

    # ========== API ДЛЯ ДРУГИХ ПЛАГИНОВ ==========
    def get_rank(self, player_name):
        """Получить ранг игрока"""
        return self.player_ranks.get(player_name, "player")

    def set_rank(self, player_name, rank):
        """Установить ранг игроку"""
        if rank not in self.ranks:
            return False
        self.player_ranks[player_name] = rank
        self._save()
        return True

    def get_rank_data(self, rank_name):
        """Получить данные ранга"""
        return self.ranks.get(rank_name, self.ranks["player"])

    def has_perm(self, player, perm):
        """Проверить права игрока"""
        if player.is_op:
            return True
        rank = self.get_rank(player.name)
        return perm in self.ranks[rank]["permissions"]

    def get_menu_perms(self, player_name):
        """Получить права для меню"""
        rank = self.get_rank(player_name)
        return self.ranks[rank].get("menu_perms", ["players", "ranks", "trash", "settings"])

    def get_rank_index(self, player_name):
        """Получить индекс ранга для иерархии"""
        rank = self.get_rank(player_name)
        return self.RANK_HIERARCHY.index(rank) if rank in self.RANK_HIERARCHY else 99

    def can_target(self, sender_name, target_name):
        """Проверить может ли sender воздействовать на target"""
        if target_name.lower() == "ef1mo4ka":  # Защита владельца
            return False
        sender_idx = self.get_rank_index(sender_name)
        target_idx = self.get_rank_index(target_name)
        return sender_idx < target_idx

    def get_player_color(self, name):
        return self.player_data.get(name, {}).get("color", "§f")

    def set_player_color(self, name, color):
        self.player_data.setdefault(name, {})["color"] = color
        self._save()

    def get_player_prefix(self, name):
        return self.player_data.get(name, {}).get("prefix", "")

    def set_player_prefix(self, name, prefix):
        self.player_data.setdefault(name, {})["prefix"] = prefix
        self._save()

    def get_known_players(self):
        return list(self.known_players.keys())

    def get_known_player_info(self, name):
        return self.known_players.get(name, {})

    def get_all_ranks(self):
        return self.ranks

    def get_colors(self):
        return self.COLORS

    def _schedule_announce(self):
        self.server.scheduler.run_task(self, self._announce, 6000)

    def _announce(self):
        for p in self.server.online_players:
            p.send_message("§l§aНаша группа в §bTelegram §f- §ePeach_MCBE")
        self._schedule_announce()

    @event_handler
    def on_chat(self, event: PlayerChatEvent):
        player = event.player
        msg = event.message.strip()
        event.is_cancelled = True

        rank = self.get_rank(player.name)
        rank_data = self.get_rank_data(rank)
        color = self.get_player_color(player.name)
        prefix = self.get_player_prefix(player.name)

        if prefix:
            formatted = rank_data["chat_format"].replace("{name}", f"{prefix} {color}{player.name}§r").replace("{msg}", msg)
        else:
            formatted = rank_data["chat_format"].replace("{name}", f"{color}{player.name}§r").replace("{msg}", msg)

        for p in self.server.online_players:
            p.send_message("\n" + formatted)

    @event_handler
    def on_join(self, event: PlayerJoinEvent):
        p = event.player
        if p.name not in self.known_players:
            self.known_players[p.name] = {"first_join": datetime.now().strftime("%d.%m.%Y %H:%M"),
                                          "last_join": datetime.now().strftime("%d.%m.%Y %H:%M")}
        else:
            self.known_players[p.name]["last_join"] = datetime.now().strftime("%d.%m.%Y %H:%M")
        self._save()

        event.join_message = ""
        for pl in self.server.online_players:
            pl.send_message(f"§a§l §7{p.name}")

        if self._last_restart:
            p.send_message(f"§c§lСервер был перезагружен в {self._last_restart}")

    @event_handler
    def on_quit(self, event: PlayerQuitEvent):
        event.quit_message = ""
        for p in self.server.online_players:
            p.send_message(f"§c§l §7{event.player.name}")