from dataclasses import dataclass, field
from enum import IntEnum
from itertools import chain
from pprint import pprint
from typing import Counter, Dict, List, Tuple

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
            (FIELD_SIZE, FIELD_SIZE), dtype=np.uint8
        ).tolist()
    )
    players: Dict[str, Spieler] = field(
        default_factory=lambda: {"testSid": Spieler.WHITE}
    )
    gameState: GameState = GameState.PLACE_SOLDATEN

    def _validate_coordinate(self, x: int, y: int) -> bool:
        checkX = 0 <= x < FIELD_SIZE
        checkY = 0 <= y < FIELD_SIZE
        return checkX and checkY

    def place_object(self, x: int, y: int, sid: str):
        if not self._validate_coordinate(x, y):
            print(f"error koordinate {x, y} ist ausserhalb")
            return None

        spieler = self._get_player(sid)

        soldat = WHITE if spieler == Spieler.WHITE else BLACK

        if self._check_soldier_placement(x, y, spieler):
            self.board[x][y] = soldat
            return self.board

    def _count_objects(self, spieler: Spieler) -> Tuple[int, int]:
        color = WHITE if spieler == Spieler.WHITE else BLACK
        c = Counter(chain(*self.board))
        soldiers = c[WHITE if color == WHITE else BLACK]
        town = c[TOWN_WHITE if color == WHITE else TOWN_BLACK]
        return (soldiers, town)

    def _all_objects_placed(self) -> bool:
        return all(
            self._count_objects(player) == (MAX_SOLDIERS, 1)
            for player in [Spieler.WHITE, Spieler.BLACK]
        )

    def _white_placed_all(self) -> bool:
        soldiers, towns = self._count_objects(Spieler.WHITE)
        return soldiers == MAX_SOLDIERS and towns == 1

    def _get_player(self, sid: str) -> Spieler:
        return self.players.get(sid)

    def _is_room_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS_IN_ROOM

    def _check_soldier_placement(self, x: int, y: int, spieler: Spieler) -> bool:
        if not self._is_room_full():
            print("warte auf den anderen gegner")
            return False

        if not self._white_placed_all():
            print("white soll zu erst alles placen")
            return False

        if self._all_objects_placed():
            print("alle objecte sind geplaced")
            return False

        match spieler:
            case Spieler.WHITE:
                if x == 0 and y in range(FIELD_SIZE) or x in range(4) and y == 0:
                    print(f"white darf nicht placen {x, y}")
                    return False
                else:
                    return True

            case Spieler.BLACK:
                if (
                    x == FIELD_SIZE
                    and y in range(FIELD_SIZE)
                    or y in range(4)
                    and x == FIELD_SIZE
                ):
                    print("black darf nicht placen")
                    return False
                else:
                    return True

            case _:
                print("error case")
                return False


rooms: Room = {}

if __name__ == "__main__":
    r = Room()
    rooms[r.name] = r

    k = {"x": 0, "y": 0, "sid": "testuuid"}

    r.place_object(**k)
    r.place_object(**k | {"x": 1})
    r.place_object(**k | {"y": 2})
    r.place_object(**k | {"y": 2})

    print(r._all_objects_placed())

    pprint(r.board)
