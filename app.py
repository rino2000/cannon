import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import chain
from pprint import pprint
from threading import Lock
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

Field = List[List[int]]


class Spieler(IntEnum):
    WHITE = 1
    BLACK = 2


class GameState(IntEnum):
    PLACE_SOLDATEN = 0
    MOVE_SOLDATEN = 1


@dataclass
class Room:
    name: str = field(default="test")
    board: Field = field(
        default_factory=lambda: np.zeros(
            (BOARD_SIZE, BOARD_SIZE), dtype=np.uint8
        ).tolist(),
        init=False,
    )
    players: Dict[str, Spieler] = field(
        default_factory=lambda: {}, init=False
    )  # {sid:color}
    gameState: GameState = field(default=GameState.PLACE_SOLDATEN, init=False)
    white_captured: int = field(default=0, init=False)
    black_captured: int = field(default=0, init=False)
    _capture_lock: Lock = field(default_factory=Lock, init=False)

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
        checkX = 0 <= x < BOARD_SIZE
        checkY = 0 <= y < BOARD_SIZE
        return checkX and checkY

    def place_object(self, x: int, y: int, sid: str) -> Optional[Field]:
        spieler = self._get_player(sid)
        return self._check_placement(x, y, spieler)

    def _place_soldier(self, x: int, y: int, spieler: Spieler) -> Field:
        self.board[x][y] = WHITE if spieler == Spieler.WHITE else BLACK
        return self.board

    def _place_town(self, x: int, y: int, spieler: Spieler) -> Field:
        town = TOWN_WHITE if spieler == Spieler.WHITE else TOWN_BLACK
        self.board[x][y] = town
        if self._all_objects_placed():
            self.gameState = GameState.MOVE_SOLDATEN
        return self.board

    def _count_objects(self, spieler: Spieler) -> Tuple[int, int]:
        color = WHITE if spieler == Spieler.WHITE else BLACK
        c = Counter(chain(*self.board))
        soldiers = c[WHITE if color == WHITE else BLACK]
        town = c[TOWN_WHITE if color == WHITE else TOWN_BLACK]
        return (soldiers, town)

    def _all_objects_placed(self) -> bool:
        return all(self._count_objects(s) == (MAX_SOLDIERS, 1) for s in list(Spieler))

    def _white_placed_all(self) -> bool:
        soldiers, towns = self._count_objects(Spieler.WHITE)
        return soldiers == MAX_SOLDIERS and towns == 1

    def _get_player(self, sid: str) -> Optional[Spieler]:
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

    def move_soldier(
        self, startX: int, startY: int, endX: int, endY: int, sid: str
    ) -> Optional[Field]:
        if self.gameState != GameState.MOVE_SOLDATEN:
            print("nicht in move soldaten gamestate")
            return None

        spieler = self._get_player(sid)

        if not (
            self._validate_coordinate(startX, startY)
            and self._validate_coordinate(endX, endY)
        ):
            print(f"Koordinaten sind nicht valide {startX, startY} {endX, endY}")
            return None

        soldier = WHITE if spieler == Spieler.WHITE else BLACK

        if self.board[startX][startY] in [TOWN_BLACK, TOWN_WHITE]:
            print("du darfst die stadt nicht bewegen")
            return None

        if self.board[startX][startY] != soldier:
            print("nicht dein soldat")
            return None

        if self._check_threat(startX, startY, spieler):
            if (endX, endY) in self._all_possible_thread_moves(startX, startY, spieler):
                print(f"thread move {endX, endY} moved")
                self.board[startX][startY] = EMPTY
                self.board[endX][endY] = soldier
                return self.board

        captures = self._check_capture_soldier(startX, startY, spieler)

        if (endX, endY) in captures:
            return self._capture(startX, startY, endX, endY, spieler)

        if self.board[endX][endY] != EMPTY:
            print(f"ziel koordinate {endX, endY} ist nicht frei")
            return None

        direction = 1 if spieler == Spieler.WHITE else -1

        if endX != startX + direction:
            print("soldat darf nur 1 schritt vorraus und diagonal rechts, links")
            return None

        if abs(endY - startY) > 1:
            print("soldat darf nur 1 schritt in allen richtungen")
            return None

        self.board[startX][startY] = EMPTY
        self.board[endX][endY] = soldier
        return self.board

    def _check_capture_soldier(self, x: int, y: int, spieler: Spieler):

        enemy_color = WHITE if spieler == Spieler.BLACK else BLACK
        direction = 1 if spieler == Spieler.WHITE else -1

        fields = [
            (x, y - 1),  # left
            (x, y + 1),  # right
            (x + direction, y),  # above
            (x + direction, y - 1),  # diagonally left
            (x + direction, y + 1),  # diagonally right
        ]

        possible = list(filter(lambda x: self.board[x[0]][x[1]] == enemy_color, fields))
        check = all(map(lambda x: self._validate_coordinate(x[0], x[1]), possible))
        # check = all([self._validate_coordinate(*p) for p in possible])

        return possible if check else ()

    def _capture_soldier(self, spieler: Spieler) -> None:
        with self._capture_lock:
            if spieler == Spieler.WHITE:
                self.white_captured += 1
            else:
                self.black_captured += 1

    def _capture(
        self, startX: int, startY: int, endX: int, endY: int, spieler: Spieler
    ) -> Optional[Field]:
        if not self._validate_coordinate(
            startX, startY
        ) and not self._validate_coordinate(endX, endY):
            print("coordinaten sind nicht valide")
            return None

        soldier = WHITE if spieler == Spieler.WHITE else BLACK

        capturable = self._check_capture_soldier(startX, startY, spieler)

        if (endX, endY) not in capturable:
            print("Kein soldier auf zu capturen")
            return None

        enemy_soldier = WHITE if spieler == Spieler.BLACK else BLACK

        if self.board[endX][endY] == enemy_soldier:
            self._capture_soldier(
                Spieler.WHITE if spieler == Spieler.BLACK else Spieler.BLACK
            )

            self.board[startX][startY] = EMPTY
            self.board[endX][endY] = soldier

            print(f"soldat captured {endX, endY}")
            return self.board

        return self.board

    def _check_threat(self, x: int, y: int, spieler: Spieler) -> bool:
        direction = 1 if spieler == Spieler.WHITE else -1
        opponent = WHITE if spieler == Spieler.BLACK else BLACK

        fields = [
            (x, y - 1),  # left
            (x, y + 1),  # right
            (x + direction, y),  # above
            (x + direction, y - 1),  # diagonally right
            (x + direction, y + 1),  # diagonally left
        ]

        # return any(map(lambda x: self.board[x[0]][x[1]] == opponent, fields))
        return any([self.board[x][y] == opponent for x, y in fields])

    def _check_interception(
        self, x: int, y: int, spieler: Spieler
    ) -> List[Tuple[int, int]]:
        """return List of all interception koordinates that are calculated (endX,endY)"""

        direction = 1 if spieler == Spieler.WHITE else -1

        check_iterception = [
            (x - 1 * direction, y),  # back
            (x - 2 * direction, y),  # back
            (x - 1 * direction, y + 1),  # 1 fields back diagonally right
            (x - 1 * direction, y - 1),  # 1 fields back diagonally left
            (x - 2 * direction, y + 2),  # 1 fields back diagonally right
            (x - 2 * direction, y - 2),  # 1 fields back diagonally left
        ]

        return list(
            filter(
                lambda x: (
                    self.board[x[0]][x[1]] in [WHITE, BLACK, TOWN_BLACK, TOWN_WHITE]
                ),
                check_iterception,
            )
        )

    def _all_possible_thread_moves(
        self, x: int, y: int, spieler: Spieler
    ) -> List[Tuple[int, int]]:
        """Filter all moves that are not intercepted"""

        direction = 1 if spieler == Spieler.WHITE else -1

        possible_moves = [
            (x - 2 * direction, y),  # 2 fields back
            (x - 2 * direction, y + 2),  # 2 fields back diagonally right
            (x - 2 * direction, y - 2),  # 2 fields back diagonally left
        ]

        return list(set(self._check_interception(x, y, spieler)) ^ set(possible_moves))

    def _check_cannon_coordinates(self, endX: int, endY: int, spieler: Spieler):
        direction = 1 if spieler == Spieler.WHITE else -1

        coords = []

        vertical_coords = [
            (endX + 1 * direction, endY),
            (endX + 2 * direction, endY),
            (endX - 1 * direction, endY),
            (endX - 2 * direction, endY),
        ]
        coords.extend(vertical_coords)

        diagonal_coords = [
            (endX + 1 * direction, endY - 1),
            (endX + 2 * direction, endY - 2),
            (endX + 1 * direction, endY + 1),
            (endX + 2 * direction, endY + 2),
            (endX - 1 * direction, endY - 1),
            (endX - 2 * direction, endY - 2),
            (endX - 1 * direction, endY + 1),
            (endX - 2 * direction, endY + 2),
        ]
        coords.extend(diagonal_coords)

        return list(set(filter(lambda c: self._validate_coordinate(*c), coords)))

    def _check_cannon_interception(self, x: int, y: int, spieler: Spieler) -> bool:
        soldier = WHITE if spieler == Spieler.WHITE else BLACK
        opponent = BLACK if spieler == Spieler.WHITE else WHITE

        cannon_coords = self._check_cannon_coordinates(x, y, spieler)
        soldier_coords = [
            coord
            for coord in cannon_coords
            if self.board[coord[0]][coord[1]] == soldier
        ]

        if len(soldier_coords) < 2:
            return False

        for x, y in soldier_coords:
            if self.board[x][y] in [opponent, TOWN_WHITE, TOWN_BLACK]:
                return False

        return True

    def _check_create_cannon(self, endX: int, endY: int, spieler: Spieler) -> bool:
        return self._check_cannon_interception(endX, endY, spieler)

    def _get_all_cannons(self, x: int, y: int, spieler: Spieler):
        direction = 1 if spieler == Spieler.WHITE else -1
        soldier = WHITE if spieler == Spieler.WHITE else BLACK

        all_possible_coords = [
            # 2 druber
            ((x + 1 * direction, y), (x + 2 * direction, y)),
            # 2 drunter
            ((x - 1 * direction, y), (x - 2 * direction, y)),
            # zwischen 2 vertical
            ((x + 1 * direction, y), (x - 1 * direction, y)),
            # 2 digonal rechts boden
            ((x + 1 * direction, y + 1), (x + 2 * direction, y + 2)),
            # 2 digonal rechts spitze
            ((x - 1 * direction, y - 1), (x - 2 * direction, y - 2)),
            # 2 diagonal rechts zwischen
            ((x + 1 * direction, y + 1), (x - 1 * direction, y - 1)),
            # 2 digonal links boden
            ((x + 1 * direction, y - 1), (x + 2 * direction, y - 2)),
            # 2 digonal links spitze
            ((x - 1 * direction, y - 1), (x - 2 * direction, y - 2)),
            # 2 diagonal links zwischen
            ((x + 1 * direction, y - 1), (x - 1 * direction, y - 1)),
        ]

        valide = []

        for first, second in all_possible_coords:
            if self._validate_coordinate(*first) and self._validate_coordinate(*second):
                (xx, yy), (xxx, yyy) = first, second

                if (
                    self.board[x][y] == soldier
                    and self.board[xx][yy] == soldier
                    and self.board[xxx][yyy] == soldier
                ):
                    valide.append((first, second, (x, y)))

        return valide

    def _get_cannon_gun_axis(
        self, coords: List[Tuple[Tuple[int, int]]], spieler: Spieler
    ) -> Tuple[int, int]:
        return (
            min(chain.from_iterable(coords), key=lambda x: x[0])
            if spieler == Spieler.WHITE
            else max(chain.from_iterable(coords), key=lambda x: x[0])
        )

    def _check_cannon_shoot_interception(
        self, x: int, y: int, spieler: Spieler
    ) -> bool:

        direction = 1 if spieler == Spieler.WHITE else -1
        opponent = BLACK if spieler == Spieler.WHITE else WHITE

        interceptions = [
            (x + 3 * direction, y),  # gerade
            (x + 3 * direction, y + 3),  # diagonal rechts
            (x + 3 * direction, y - 3),  # diagonal links
        ]

        return any([self.board[x][y] == opponent for x, y in interceptions])

    def _check_cannon_shoot_validate(self, startX: int, startY: int, spieler: Spieler):

        direction = 1 if spieler == Spieler.WHITE else -1
        possible_targets = [
            (startX + 4 * direction, startY),
            (startX + 5 * direction, startY),
            (startX + 4 * direction, startY + 4),
            (startX + 5 * direction, startY + 5),
            (startX + 4 * direction, startY - 4),
            (startX + 5 * direction, startY - 5),
        ]

        return list(filter(lambda c: self._validate_coordinate(*c), possible_targets))

    def _cannon_shoot(self, startX: int, startY: int, endX: int, endY: int, spieler):

        coords = self._check_cannon_shoot_validate(startX, startY, spieler)
        soldier = WHITE if spieler == Spieler.WHITE else BLACK

        if self._check_cannon_shoot_interception(endX, endY, spieler):
            print("cannon shoot fail, because of interception")
            return None

        x, y = self._get_cannon_gun_axis(
            self._get_all_cannons(startX, startY, spieler), spieler
        )

        if not self.board[x][y] == soldier and not (startX == x and startY == y):
            print(f"cannon shoot axis != {startX, startY}")
            return None

        if (endX, endY) not in coords:
            print("cannon target shooting coord is not in coords")
            return None

        if self.board[endX][endY] in [soldier, TOWN_BLACK, TOWN_WHITE]:
            print("cannon target shoot is not opponent")
            return None

        self._capture_soldier(spieler)
        self.board[endX][endY] = EMPTY
        print(f"cannon shoot success {endX, endY}")
        return self.board


rooms: Dict[str, Room] = {}

if __name__ == "__main__":
    r = Room()
    r.join_room("a")
    r.join_room("b")
    rooms[r.name] = r

    white_sid: str = next((k for k, v in r.players.items() if v == Spieler.WHITE))
    black_sid: str = next((k for k, v in r.players.items() if v == Spieler.BLACK))

    # w = {"sid": white_sid}
    # b = {"sid": black_sid}

    # for y in range(1, BOARD_SIZE, 2):
    #     for x in range(1, 4):
    #         r.place_object(**w | {"x": x, "y": y})

    # r.place_object(**w | {"x": 0, "y": 4})

    # for yy in range(0, BOARD_SIZE, 2):
    #     for xx in range(6, 9):
    #         r.place_object(**b | {"x": xx, "y": yy})

    # r.place_object(**b | {"x": 9, "y": 7})

    # print(r._count_objects(Spieler.WHITE), r._count_objects(Spieler.BLACK))
    # pprint(r.board)
    # print()

    # allowed white
    # r.move_soldier(1, 1, 2, 2, white_sid)  # diagonal rechts
    # r.move_soldier(1, 1, 2, 0, white_sid)  # diagonal links
    # r.move_soldier(3, 1, 4, 1, white_sid)  # gerade aus

    # error moves
    # r.move_soldier(3, 1, 5, 1, white_sid)  # mehr als 1+ gerade aus
    # r.move_soldier(1, 1, 1, 0, white_sid)  # links
    # r.move_soldier(1, 1, 1, 2, white_sid)  # rechts
    # r.move_soldier(0, 4, 0, 5, white_sid)  # versucht stadt moven
    # r.move_soldier(1, 1, 0, 1, white_sid)  # 1 hinten

    # allowed black
    # r.move_soldier(6, 0, 5, 1, black_sid)  # diagonal rechts
    # r.move_soldier(6, 2, 5, 1, black_sid)  # diagonal links
    # r.move_soldier(6, 0, 5, 0, black_sid)  # gerade aus

    # error moves
    # r.move_soldier(6, 0, 4, 0, black_sid)  # mehr als 1+ gerade aus
    # r.move_soldier(6, 2, 6, 1, black_sid)  # links
    # r.move_soldier(6, 0, 6, 1, black_sid)  # rechts
    # r.move_soldier(9, 7, 9, 10, black_sid)  # versucht stadt moven
    # r.move_soldier(8, 0, 9, 0, black_sid)  # 1 hinten

    # capture
    # black_coord = {"x": 4, "y": 1, "spieler": Spieler.BLACK}
    # r._place_soldier(**black_coord)  # place black

    # r._place_soldier(3, 0, Spieler.WHITE)  # diagonally left
    # r._place_soldier(3, 2, Spieler.WHITE)  # diagonally right
    # r._place_soldier(4, 2, Spieler.WHITE)  # right
    # r._place_soldier(4, 0, Spieler.WHITE)  # left

    # pprint(r.board)

    # print(r._check_capture_soldier(**black_coord))

    # pprint(r.move_soldier(4, 1, 3, 1, black_sid))

    # print(r.black_captured, r.white_captured)

    # interception logic
    # print(r._check_threat(5, 1, Spieler.BLACK))  # false thread
    # print(r._check_threat(4, 1, Spieler.BLACK))  # true thread

    # thread logic
    # r._place_soldier(4, 5, Spieler.WHITE)
    # r._place_soldier(5, 5, Spieler.BLACK)
    # r._place_soldier(7, 5, Spieler.WHITE)
    # print(r._check_interception(5, 5, Spieler.BLACK))

    # pprint(r.board)
    # print()
    # print(r._check_interception(5, 5, Spieler.BLACK))
    # print(r._all_possible_thread_moves(5, 5, Spieler.BLACK))
    # r.gameState = GameState.MOVE_SOLDATEN
    # pprint(r.move_soldier(5, 5, 7, 7, black_sid)) #thread move right diagonally
    # pprint(r.move_soldier(5, 5, 7, 3, black_sid))  # thread move left diagonally
    # pprint(r.move_soldier(5, 5, 7, 5, black_sid))  # thread move down

    # [r._place_soldier(x, 0, Spieler.BLACK) for x in range(7, 9)]
    # r._place_soldier(5, 5, Spieler.BLACK)
    # r._place_soldier(6, 5, Spieler.BLACK)
    # r._place_soldier(6, 5, Spieler.BLACK)
    # r._place_soldier(7, 4, Spieler.BLACK)

    # r.board = np.arange(100).reshape(10, 10).tolist()
    # r._place_soldier(5, 5, Spieler.BLACK)
    # r._place_soldier(5, 5, Spieler.BLACK)
    r._place_soldier(4, 5, Spieler.BLACK)
    r._place_soldier(3, 5, Spieler.BLACK)
    r._place_soldier(5, 5, Spieler.BLACK)
    # r._place_soldier(4, 4, Spieler.WHITE)

    # c = r._check_create_cannon(5, 5, Spieler.BLACK)

    # print(c)

    # r._place_soldier(5, 5, Spieler.BLACK) if c else None
    l = r._get_all_cannons(5, 5, Spieler.BLACK)

    # print(r._get_cannon_gun_axis(l, Spieler.WHITE))

    # r._place_soldier(2, 5, Spieler.WHITE)
    # r._place_soldier(2, 8, Spieler.WHITE)
    # r._place_soldier(1, 1, Spieler.WHITE)
    # print(r._check_cannon_shoot_interception(5, 5, Spieler.BLACK))
    # print(r._check_cannon_shoot(5, 5, 1, 1, Spieler.BLACK))

    r._place_soldier(1, 5, Spieler.WHITE)
    r._place_soldier(0, 5, Spieler.WHITE)
    r._place_soldier(1, 1, Spieler.WHITE)
    r._place_soldier(1, 9, Spieler.WHITE)

    pprint(r.board)
    pprint(r._cannon_shoot(5, 5, 1, 1, Spieler.BLACK))

    rooms.pop(r.name, None)
