import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import chain
from pprint import pprint
from typing import Dict, List, Optional, Tuple

import numpy as np

EMPTY = 0
WHITE = 1  # 👇🏻
BLACK = 2  # 👆🏿
TOWN_WHITE = 3  # 🏠
TOWN_BLACK = 4  # 🏡
MAX_SOLDIERS = 15
MAX_PLAYERS_IN_ROOM = 2
BOARD_SIZE = 10  # 10x10
FIELD_SIZE = BOARD_SIZE + 1  # 11x11 mit Labels


x_legende: List[int] = list(range(BOARD_SIZE))
y_legende: List[chr] = list(map(chr, range(ord("a"), ord("l"))))

Field = List[List[int]]


class Spieler(IntEnum):
    WHITE = 1
    BLACK = 2


class GameState(IntEnum):
    PLACE_SOLDATEN = 0
    MOVE_SOLDATEN = 1


@dataclass
class Room:
    name: str = "test"
    board: Field = field(
        default_factory=lambda: np.zeros(
            (BOARD_SIZE, BOARD_SIZE), dtype=np.uint8
        ).tolist()
    )
    players: Dict[str, Spieler] = field(default_factory=lambda: {})  # {sid:color}
    gameState: GameState = GameState.PLACE_SOLDATEN

    def __post_init__(self):
        rooms[self.name] = self

    def join_room(self, sid: str) -> Optional[Spieler]:
        if self._is_room_full():
            print("room is allready full")
            return None

        if not self.players:
            color = random.choice(list(Spieler))
            self.players |= {sid: color}
            return color

        left = set(Spieler) - set(self.players.values())
        color = left.pop()
        self.players |= {sid: color}
        return color

    def _validate_coordinate(self, x: int, y: int) -> bool:
        checkX = 0 <= x < FIELD_SIZE
        checkY = 0 <= y < FIELD_SIZE
        return checkX and checkY

    def place_object(self, x: int, y: int, sid: str) -> Optional[Field]:
        spieler = self._get_player(sid)
        return self._check_placement(x, y, spieler)

    def _place_soldier(self, x: int, y: int, spieler) -> Field:
        self.board[x][y] = WHITE if spieler == Spieler.WHITE else BLACK
        return self.board

    def _place_town(self, x: int, y: int, spieler: Spieler) -> Field:
        town = TOWN_WHITE if spieler == Spieler.WHITE else TOWN_BLACK
        self.board[x][y] = town
        self.gameState = GameState.MOVE_SOLDATEN if spieler == Spieler.BLACK else None
        return self.board

    def _count_objects(self, spieler: Spieler) -> Tuple[int, int]:
        color = WHITE if spieler == Spieler.WHITE else BLACK
        c = Counter(chain(*self.board))
        soldiers = c[WHITE if color == WHITE else BLACK]
        town = c[TOWN_WHITE if color == WHITE else TOWN_BLACK]
        return (soldiers, town)

    def _all_objects_placed(self) -> bool:
        return all(
            self._count_objects(spieler) == (MAX_SOLDIERS, 1)
            for spieler in list(Spieler)
        )

    def _white_placed_all(self) -> bool:
        soldiers, towns = self._count_objects(Spieler.WHITE)
        return soldiers == MAX_SOLDIERS and towns == 1

    def _get_player(self, sid: str) -> Spieler:
        return self.players.get(sid)

    def _is_room_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS_IN_ROOM

    def _check_placement(self, x: int, y: int, spieler: Spieler) -> Optional[Field]:
        if not self._is_room_full():
            print("warte auf den anderen gegner")
            return None

        if not self._validate_coordinate(x, y):
            print(f"error koordinate {x, y} ist ausserhalb")
            return None

        if self._all_objects_placed():
            print("alle objecte sind geplaced")
            return None

        soldiers, town = self._count_objects(spieler)
        is_white = spieler == Spieler.WHITE

        if spieler == Spieler.BLACK and not self._white_placed_all():
            print("white muss zuerst alle objekte placen")
            return None

        allowed_placement_soldier = (
            (x in range(1, 4)) and (y in range(1, BOARD_SIZE))
            if is_white
            else (x in range(6, BOARD_SIZE - 1)) and (y in range(BOARD_SIZE))
        )

        allowed_placement_town = (
            (x == 0) and (y in range(1, BOARD_SIZE - 1))
            if is_white
            else (x == BOARD_SIZE - 1) and (y in range(1, BOARD_SIZE - 1))
        )

        if soldiers < MAX_SOLDIERS:
            if not allowed_placement_soldier:
                print(f"spieler {spieler} darfst hier nicht soldaten placen {x, y}")
                return None
            return self._place_soldier(x, y, spieler)

        if soldiers == MAX_SOLDIERS and town == 0:
            if not allowed_placement_town:
                print(f"spieler {spieler} darfst hier nicht town placen {x, y}")
                return None
            return self._place_town(x, y, spieler)


rooms: Dict[str, Room] = {}

if __name__ == "__main__":
    r = Room()
    r.join_room("a")
    r.join_room("b")
    rooms[r.name] = r

    white_sid: str = next((k for k, v in r.players.items() if v == Spieler.WHITE))
    black_sid: str = next((k for k, v in r.players.items() if v == Spieler.BLACK))

    w = {"sid": white_sid}
    b = {"sid": black_sid}

    for y in range(1, BOARD_SIZE, 2):
        for x in range(1, 4):
            r.place_object(**w | {"x": x, "y": y})

    r.place_object(**w | {"x": 0, "y": 4})

    for yy in range(0, BOARD_SIZE, 2):
        for xx in range(6, 9):
            r.place_object(**b | {"x": xx, "y": yy})

    r.place_object(**b | {"x": 9, "y": 7})

    print(r._count_objects(Spieler.WHITE), r._count_objects(Spieler.BLACK))

    pprint(r.board)
    print(f"Gamestate == {r.gameState.name}")
    rooms.pop(r.name, None)
