import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import batched, chain, compress, filterfalse, starmap
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
    _lock: Lock = field(default_factory=Lock, init=False)

    def __post_init__(self):
        rooms[self.name] = self

    def join_room(self, sid: str) -> Optional[Spieler]:
        if self.room_is_full():
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
        return (0 <= x < BOARD_SIZE) and (0 <= y < BOARD_SIZE)

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
        c = Counter(chain.from_iterable(self.board))
        soldiers = c[WHITE if color == WHITE else BLACK]
        town = c[TOWN_WHITE if color == WHITE else TOWN_BLACK]
        return (soldiers, town)

    def _all_objects_placed(self) -> bool:
        return all(self._count_objects(s) == (MAX_SOLDIERS, 1) for s in list(Spieler))

    def _white_placed_all(self) -> bool:
        return self._count_objects(Spieler.WHITE) == (MAX_SOLDIERS, 1)

    def _get_player(self, sid: str) -> Optional[Spieler]:
        return self.players.get(sid)

    def room_is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS_IN_ROOM

    def _check_placement(self, x: int, y: int, spieler: Spieler) -> Optional[Field]:
        if not self.room_is_full():
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

        if self._check_threat(startX, startY, spieler):
            if (endX, endY) in self._check_interception_thread_move(
                startX, startY, spieler
            ):
                print(f"thread move {endX, endY} moved")
                return self._swap(startX, startY, endX, endY, spieler)

        if (endX, endY) in self._check_capture_soldier(startX, startY, spieler):
            return self.capture_soldier(startX, startY, endX, endY, spieler)

        if self.board[endX][endY] != EMPTY:
            print(f"ziel koordinate {endX, endY} ist nicht frei")
            return None

        if (
            spieler == Spieler.WHITE
            and (startX - endX) == 1
            or spieler == Spieler.BLACK
            and (startX - endX) == -1
        ):
            print(f"soldat: {soldier} darf nicht 1 schritt nachhinten")
            return None

        if abs(endY - startY) > 1 or abs(endX - startX) > 1:
            print("soldat darf nur 1 schritt in allen richtungen")
            return None

        if self.board[startX][startY] in [TOWN_BLACK, TOWN_WHITE]:
            print("du darfst die stadt nicht bewegen")
            return None

        if self.board[startX][startY] != soldier:
            print(f"nicht dein soldat {soldier}")
            return None

        return self._swap(startX, startY, endX, endY, spieler)

    def _check_capture_soldier(
        self, x: int, y: int, spieler: Spieler
    ) -> List[Tuple[int, int]]:
        """Return list of all possible coordinates where opponent is in to capture"""

        opponent = WHITE if spieler == Spieler.BLACK else BLACK
        direction = 1 if spieler == Spieler.WHITE else -1

        coords = [
            (x, y - 1),  # left
            (x, y + 1),  # right
            (x + direction, y),  # above
            (x + direction, y - 1),  # diagonally left
            (x + direction, y + 1),  # diagonally right
        ]

        validate = filter(lambda c: self._validate_coordinate(*c), coords)
        return list(filter(lambda x: self.board[x[0]][x[1]] == opponent, validate))

    def _capture_soldier(self, spieler: Spieler) -> None:
        with self._lock:
            if spieler == Spieler.WHITE:
                self.white_captured += 1
            else:
                self.black_captured += 1

    def capture_soldier(
        self, startX: int, startY: int, endX: int, endY: int, spieler: Spieler
    ) -> Optional[Field]:

        if (endX, endY) not in self._check_capture_soldier(startX, startY, spieler):
            print("Kein soldier zu capturen")
            return None

        opponent = WHITE if spieler == Spieler.BLACK else BLACK

        if self.board[endX][endY] == opponent:
            self._capture_soldier(
                Spieler.WHITE if spieler == Spieler.BLACK else Spieler.BLACK
            )
            print(f"soldat captured {endX, endY}")
            return self._swap(startX, startY, endX, endY, spieler)

        return self.board

    def _check_threat(self, x: int, y: int, spieler: Spieler) -> bool:
        direction = 1 if spieler == Spieler.WHITE else -1
        opponent = WHITE if spieler == Spieler.BLACK else BLACK

        coords = [
            (x, y - 1),  # left
            (x, y + 1),  # right
            (x + 1 * direction, y),  # above
            (x + 1 * direction, y - 1),  # diagonally right
            (x + 1 * direction, y + 1),  # diagonally left
        ]
        valide_coords = filter(lambda c: self._validate_coordinate(*c), coords)
        check_thread = map(lambda x: self.board[x[0]][x[1]] == opponent, valide_coords)
        return any(check_thread)

    def _check_interception_thread_move(
        self, x: int, y: int, spieler: Spieler
    ) -> List[Tuple[int, int]]:
        """Return list of all possible thread moves"""

        direction = 1 if spieler == Spieler.WHITE else -1

        coords = [
            (
                (x - 1 * direction, y),  # back
                (x - 2 * direction, y),
            ),
            (
                (x - 1 * direction, y + 1),  # fields back diagonally right
                (x - 2 * direction, y + 2),
            ),
            (
                (x - 1 * direction, y - 1),  # fields back diagonally left
                (x - 2 * direction, y - 2),
            ),
        ]

        # valide coordinates
        valide_coords = batched(
            map(lambda c: self._validate_coordinate(*c), chain(*coords)), 2
        )

        # filter all tuple coords where False is in
        f = filterfalse(lambda x: False in x, valide_coords)

        interception = [WHITE, BLACK, TOWN_BLACK, TOWN_WHITE]
        all_possible_coords = list(compress(coords, f))
        # check for interception
        for coord in all_possible_coords:
            x, y = coord
            if self.board[x[0]][x[1]] or self.board[y[0]][y[1]] in interception:
                all_possible_coords.remove(coord)

        # return the biggest or smalest coordinate in tuple because the player are only
        # allowed to move 2 fields back and not 1 field
        return (
            list(map(max, all_possible_coords))
            if spieler == Spieler.BLACK
            else list(map(min, all_possible_coords))
        )

    def _check_cannon_coordinates(
        self, endX: int, endY: int, spieler: Spieler
    ) -> List[Tuple[Tuple[int, int], Tuple[int, int]]]:
        """Return all possibles cannon coordinates from a selected cannon coordinate"""

        direction = 1 if spieler == Spieler.WHITE else -1
        coords = []

        vertical = [
            # bottom vertical
            ((endX + 1 * direction, endY), (endX + 2 * direction, endY)),
            # top vertical
            ((endX - 1 * direction, endY), (endX - 2 * direction, endY)),
            # between vertical
            ((endX + 1 * direction, endY), (endX - 1 * direction, endY)),
            # waagerecht zwischen 2
            ((endX, endY - 1), (endX, endY + 1)),
            # waagerecht links 2
            ((endX, endY - 1), (endX, endY - 2)),
            # waagerecht rechts 2
            ((endX, endY + 1), (endX, endY + 2)),
        ]
        coords.extend(vertical)

        diagonally_right = [
            # bottom digonally right up
            ((endX + 1 * direction, endY + 1), (endX + 2 * direction, endY + 2)),
            # top digonally right down
            ((endX - 1 * direction, endY - 1), (endX - 2 * direction, endY - 2)),
            # between digonally right
            ((endX + 1 * direction, endY + 1), (endX - 1 * direction, endY - 1)),
        ]
        coords.extend(diagonally_right)

        diagonally_left = [
            # bottom digonally left up
            ((endX + 1 * direction, endY - 1), (endX + 2 * direction, endY - 2)),
            # top digonally left down
            ((endX - 1 * direction, endY + 1), (endX - 2 * direction, endY + 2)),
            # between left right
            ((endX + 1 * direction, endY - 1), (endX - 1 * direction, endY + 1)),
        ]
        coords.extend(diagonally_left)

        return list(
            batched(
                filter(lambda c: self._validate_coordinate(*c), chain(*coords)),
                2,
            )
        )

    def _get_all_cannons(
        self, x: int, y: int, spieler: Spieler
    ) -> List[Tuple[Tuple[int, int]]]:
        direction = 1 if spieler == Spieler.WHITE else -1
        soldier = WHITE if spieler == Spieler.WHITE else BLACK

        all_possible_coords: List[Tuple[Tuple[int, int], Tuple[int, int]]] = []

        vertical = [
            # 2 druber
            ((x + 1 * direction, y), (x + 2 * direction, y)),
            # 2 drunter
            ((x - 1 * direction, y), (x - 2 * direction, y)),
            # zwischen 2 vertical
            ((x + 1 * direction, y), (x - 1 * direction, y)),
        ]
        all_possible_coords.extend(vertical)

        diagonally_right = [
            # 2 digonal rechts boden
            ((x + 1 * direction, y + 1), (x + 2 * direction, y + 2)),
            # 2 digonal rechts spitze
            ((x - 1 * direction, y - 1), (x - 2 * direction, y - 2)),
            # 2 diagonal rechts zwischen
            ((x + 1 * direction, y + 1), (x - 1 * direction, y - 1)),
            ((x - 1 * direction, y + 1), (x - 2 * direction, y + 2)),
        ]
        all_possible_coords.extend(diagonally_right)

        diagonally_left = [
            # 2 digonal links boden
            ((x + 1 * direction, y - 1), (x + 2 * direction, y - 2)),
            # 2 digonal links spitze
            ((x - 1 * direction, y - 1), (x - 2 * direction, y - 2)),
            # 2 diagonal links zwischen
            ((x + 1 * direction, y - 1), (x - 1 * direction, y + 1)),
        ]
        all_possible_coords.extend(diagonally_left)

        horizontal = [
            # waagerecht rechts
            ((x, y - 1), (x, y - 2)),
            # waagerecht rechts
            ((x, y - 1), (x, y + 1)),
            # waagerecht rechts
            ((x, y + 1), (x, y + 2)),
        ]
        all_possible_coords.extend(horizontal)

        valide = []

        for first, second in all_possible_coords:
            if self._validate_coordinate(*first) and self._validate_coordinate(*second):
                (xx, yy), (xxx, yyy) = first, second

                # check if the selected coord is a soldier and the possible coords around
                if (
                    self.board[x][y] == soldier
                    and self.board[xx][yy] == soldier
                    and self.board[xxx][yyy] == soldier
                ) or (
                    self.board[xx][yy] == soldier and self.board[xxx][yyy] == soldier
                ):
                    valide.append((first, second, (x, y)))

        return valide

    def _get_cannon_gun_axis(
        self, coords: List[Tuple[Tuple[int, int], Tuple[int, int]]], spieler: Spieler
    ) -> Tuple[int, int]:
        coords = list(chain(*coords))
        return (
            min(coords, key=lambda x: x[0])
            if spieler == Spieler.WHITE
            else max(coords, key=lambda x: x[0])
        )

    def _get_cannon_axis(self, coords: List[Tuple[Tuple[int, int], Tuple[int, int]]]):
        return list(map(lambda x: (min(x), max(x)), coords))

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

        check = filter(lambda c: self._validate_coordinate(*c), interceptions)
        interceptions = map(lambda c: self.board[c[0]][c[1]] == opponent, check)
        return any(interceptions)

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
        print(f"cannon shoot capture {endX, endY} ")

        return self.board

    def _check_all_possbible_cannon_moves(
        self, cannons: List[Tuple[Tuple[int, int]]], spieler: Spieler
    ):
        """Return list of all coord pairs after calculate axis swap that are cannons"""

        axis = self._get_cannon_axis(cannons)
        is_white = spieler == Spieler.WHITE
        direction = 1 if is_white else -1

        # (axis coord ,possible coord)
        coords: List[Tuple[Tuple[int, int]], Tuple[int, int]] = []

        for x in axis:
            top, bottom = x
            # vertical
            coords.append(((top), (top[0] - 3 * direction, top[1])))
            coords.append(((bottom), (bottom[0] + 3 * direction, bottom[1])))

            # diagonally left
            coords.append(((top), (top[0] - 3 * direction, top[1] + 3)))
            coords.append(((bottom), (bottom[0] + 3 * direction, bottom[1] - 3)))

            # diagonally right
            coords.append(((top), (top[0] - 3 * direction, top[1] - 3)))
            coords.append(((bottom), (bottom[0] + 3 * direction, bottom[1] + 3)))

            # horizontal
            coords.append(((top), (top[0], top[1] + 3)))
            coords.append(((bottom), (bottom[0], bottom[1] - 3)))

        validate = set(filter(lambda c: self._validate_coordinate(*c[1]), coords))
        cannons = list(map(lambda x: self._check_is_cannon(*x[1], spieler), validate))

        return list(compress(validate, cannons))

    def _swap(self, startX: int, startY: int, endX: int, endY: int, spieler: Spieler):
        soldier = WHITE if spieler == Spieler.WHITE else BLACK
        self.board[startX][startY] = EMPTY
        self.board[endX][endY] = soldier
        print(f"move from {(startX, startY)} -> {(endX, endY)}")
        return self.board

    def _check_is_cannon(
        self, x: int, y: int, spieler: Spieler = Spieler.BLACK
    ) -> bool:
        cannons = self._get_all_cannons(x, y, spieler)
        return any(map(lambda x: len(x) == 3, cannons))

    def move_cannon(
        self, startX: int, startY: int, endX: int, endY: int, spieler: Spieler
    ) -> Optional[Field]:

        cannons = self._get_all_cannons(startX, startY, spieler)

        if not cannons or ((startX, startY) not in chain(*cannons)):
            print(f"{startX, startY} gibt keine cannons")
            return None

        possible_moves = self._check_all_possbible_cannon_moves(cannons, spieler)
        print(f"possible moves {possible_moves}")

        coord = ((startX, startY), (endX, endY))
        moves = list(filter(lambda move: coord == move, possible_moves))

        target_coord = list(starmap(lambda _, target: target, moves))

        if not moves or (coord[1] not in target_coord):
            print(f"Move {coord} nicht moglich zu moven")
            return None

        return self._swap(startX, startY, endX, endY, spieler)


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
    # print(r._check_interception_thread_move(5, 5, Spieler.BLACK))

    # pprint(r.board)
    # print()
    # print(r._check_interception_thread_move(5, 5, Spieler.BLACK))
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
    # r._place_soldier(4, 5, Spieler.BLACK)
    # r._place_soldier(3, 5, Spieler.BLACK)
    # r._place_soldier(5, 5, Spieler.BLACK)
    # r._place_soldier(4, 4, Spieler.WHITE)

    # c = r._check_create_cannon(5, 5, Spieler.BLACK)

    # print(c)

    # r._place_soldier(5, 5, Spieler.BLACK) if c else None
    # l = r._get_all_cannons(5, 5, Spieler.BLACK)

    # print(r._get_cannon_gun_axis(l, Spieler.WHITE))

    # r._place_soldier(2, 5, Spieler.WHITE)
    # r._place_soldier(2, 8, Spieler.WHITE)
    # r._place_soldier(1, 1, Spieler.WHITE)
    # print(r._check_cannon_shoot_interception(5, 5, Spieler.BLACK))
    # print(r._check_cannon_shoot(5, 5, 1, 1, Spieler.BLACK))

    # r._place_soldier(1, 5, Spieler.WHITE)
    # r._place_soldier(0, 5, Spieler.WHITE)
    # r._place_soldier(1, 1, Spieler.WHITE)
    # r._place_soldier(1, 9, Spieler.WHITE)

    # pprint(r.board)
    # print()
    # pprint(r._cannon_shoot(5, 5, 1, 1, Spieler.BLACK))
    # print(r.black_captured, r.white_captured)

    # r.gameState = GameState.MOVE_SOLDATEN
    # pprint(r.place_object(2, 2, white_sid))
    # print()
    # pprint(r.move_soldier(2, 2, 2, 3, white_sid))

    # move shoot
    # r._place_soldier(6, 0, Spieler.BLACK)
    # r._place_soldier(7, 0, Spieler.BLACK)
    # r._place_soldier(8, 0, Spieler.BLACK)
    # r._place_soldier(4, 0, Spieler.WHITE)
    # pprint(r.board)

    # cannons = r._get_all_cannons(6, 0, Spieler.BLACK)
    # cannon_axis = r._get_cannon_gun_axis(cannons, Spieler.BLACK)
    # print(cannon_axis)
    # print(
    #     r._check_cannon_shoot_interception(
    #         cannon_axis[0], cannon_axis[1], Spieler.BLACK
    #     )
    # )
    # pprint(r._cannon_shoot(cannon_axis[0], cannon_axis[1], 4, 0, Spieler.BLACK))

    # cannon move
    # r._place_soldier(6, 0, Spieler.BLACK)
    # r._place_soldier(7, 0, Spieler.BLACK)
    # r._place_soldier(8, 0, Spieler.BLACK)
    # r._place_soldier(5, 0, Spieler.WHITE)

    # [
    #     r.place_object(x, y, white_sid)
    #     for y in range(0, 11)
    #     if y % 2 != 0
    #     for x in range(1, 4)
    # ]
    # r.place_object(0, 4, white_sid)  # town white
    # [
    #     r.place_object(x, y, black_sid)
    #     for y in range(0, 10)
    #     if y % 2 == 0
    #     for x in range(6, 9)
    # ]
    # r.place_object(9, 7, black_sid)  # town black

    # pprint(r.board)

    # pprint(r.move_soldier(6, 0, 5, 0, black_sid))  # move soldier forward black
    # pprint(r.move_soldier(6, 2, 5, 1, black_sid))  # move soldier diagonally left black
    # pprint(r.move_soldier(6, 4, 5, 5, black_sid))  # move soldier diagonally right black
    # pprint(r.move_soldier(5, 5, 6, 5, black_sid))  # move soldier back black
    # print()
    # r._place_soldier(1, 1, Spieler.WHITE)
    # r.move_soldier(1, 1, 2, 1, white_sid)  # move soldier forward white
    # r.move_soldier(2, 1, 3, 2, white_sid)  # move soldier left diagonally white
    # r.move_soldier(3, 2, 4, 1, white_sid)  # move soldier right diagonally white

    # pprint(r.move_soldier(0, 4, 0, 5, white_sid))  # move town white
    # pprint(r.move_soldier(9, 7, 9, 6, black_sid))  # move town black

    # pprint(r.move_soldier(3, 1, 4, 1, white_sid))  # move soldier white

    # r.gameState = GameState.MOVE_SOLDATEN
    # r._place_soldier(1, 1, Spieler.WHITE) # move backwards thread for black
    # r._place_soldier(2, 1, Spieler.BLACK)
    # r._place_soldier(3, 2, Spieler.WHITE)
    # [
    #     r._place_soldier(*x, Spieler.BLACK)
    #     for x in chain.from_iterable(r._check_interception_thread_move(2, 1, Spieler.BLACK))
    # ]

    # r.gameState = GameState.MOVE_SOLDATEN
    # r._place_soldier(5, 5, Spieler.BLACK)  # move backwards thread for white
    # r._place_soldier(4, 5, Spieler.WHITE)
    # r._place_soldier(2, 3, Spieler.BLACK)
    # [
    #     r._place_soldier(*x, Spieler.WHITE)
    #     for x in chain.from_iterable(r._check_interception_thread_move(4, 5, Spieler.WHITE))
    # ]

    # r.gameState = GameState.MOVE_SOLDATEN
    # r._place_soldier(5, 5, Spieler.BLACK)  # check capture soldier white
    # r._place_soldier(4, 5, Spieler.WHITE)

    # pprint(r.move_soldier(5, 5, 4, 5, black_sid))
    # print(r.white_captured, r.black_captured)

    # pprint(r.board)

    # r.gameState = GameState.MOVE_SOLDATEN
    # r._place_soldier(5, 5, Spieler.BLACK)  # check capture soldier black
    # r._place_soldier(4, 5, Spieler.WHITE)

    # pprint(r.move_soldier(4, 5, 5, 5, white_sid))
    # print(r.white_captured, r.black_captured)

    # r.gameState = GameState.MOVE_SOLDATEN
    # r._place_soldier(5, 5, Spieler.BLACK)  # check thread move soldier black 2 back
    # pprint(r.move_soldier(5, 5, 7, 5, black_sid))
    # r._place_soldier(
    #     5, 5, Spieler.BLACK
    # )  # check thread move soldier black 2 back diagonally left
    # pprint(r.move_soldier(5, 5, 7, 3, black_sid))
    # r._place_soldier(
    #     5, 5, Spieler.BLACK
    # )  # check thread move soldier black 2 back diagonally right
    # pprint(r.move_soldier(5, 5, 7, 7, black_sid))
    # r._place_soldier(4, 5, Spieler.WHITE)
    # pprint(r.board)

    # r.gameState = GameState.MOVE_SOLDATEN
    # r._place_soldier(4, 5, Spieler.WHITE)
    # r._place_soldier(5, 5, Spieler.BLACK)
    # pprint(r.move_soldier(4, 5, 2, 5, white_sid)) check thread move soldier white 2 back
    # pprint(r.move_soldier(4, 5, 2, 3, white_sid)) check thread move soldier white 2 right diagonally
    # pprint(r.move_soldier(4, 5, 2, 7, white_sid)) check thread move soldier white 2 left diagonally

    # pprint(r.board)
    # print()

    # """Test create cannon"""
    # r._place_soldier(4, 5, Spieler.BLACK)
    # r._place_soldier(5, 5, Spieler.BLACK)
    # print(r._can_create_cannon(6, 5, Spieler.BLACK))

    """Test cannon shoot"""
    # r._place_soldier(2, 3, Spieler.WHITE)
    # r._place_soldier(3, 3, Spieler.WHITE)
    # r._place_soldier(3, 7, Spieler.WHITE)
    # r._place_soldier(2, 8, Spieler.WHITE)

    # r._place_soldier(5, 3, Spieler.BLACK)
    # r._place_soldier(6, 3, Spieler.BLACK)
    # r._place_soldier(7, 3, Spieler.BLACK)
    # r._place_soldier(6, 4, Spieler.BLACK)
    # r._place_soldier(5, 5, Spieler.BLACK)
    # r._place_soldier(6, 5, Spieler.BLACK)

    # r._place_soldier(1, 3, Spieler.WHITE)
    # r._place_soldier(2, 3, Spieler.WHITE)
    # r._place_soldier(3, 3, Spieler.WHITE)

    # r._place_soldier(2, 4, Spieler.WHITE)
    # r._place_soldier(2, 5, Spieler.WHITE)
    # r._place_soldier(3, 5, Spieler.WHITE)

    # r._place_soldier(5, 3, Spieler.BLACK)
    # r._place_soldier(6, 3, Spieler.BLACK)

    # r._place_soldier(5, 7, Spieler.BLACK)
    # r._place_soldier(6, 8, Spieler.BLACK)

    # all_cannons = r._get_all_cannons(1, 3, Spieler.WHITE)
    # print(all_cannons)
    # cannon_axis = r._get_cannon_gun_axis(all_cannons, Spieler.WHITE)
    # print(cannon_axis)

    # pprint(r.board)
    # pprint(r._cannon_shoot(*cannon_axis, 5, 3, Spieler.WHITE))
    # pprint(r._cannon_shoot(*cannon_axis, 6, 3, Spieler.WHITE))

    # pprint(r._cannon_shoot(*cannon_axis, 5, 7, Spieler.WHITE))
    # pprint(r._cannon_shoot(*cannon_axis, 6, 8, Spieler.WHITE))

    # """Horizontal gerade schwarz"""
    # r._place_soldier(5, 4, Spieler.BLACK)
    # r._place_soldier(6, 4, Spieler.BLACK)
    # r._place_soldier(7, 4, Spieler.BLACK)

    # """Diagonal rechts schwarz"""
    # r._place_soldier(6, 5, Spieler.BLACK)
    # r._place_soldier(7, 4, Spieler.BLACK)
    # r._place_soldier(5, 6, Spieler.BLACK)

    # """Diagonal links schwarz"""
    # r._place_soldier(6, 3, Spieler.BLACK)
    # r._place_soldier(7, 4, Spieler.BLACK)
    # r._place_soldier(5, 2, Spieler.BLACK)

    # """Horzontal gerade weiss"""
    # r._place_soldier(6, 4, Spieler.WHITE)
    # r._place_soldier(5, 4, Spieler.WHITE)
    # r._place_soldier(4, 4, Spieler.WHITE)

    # """Diagonal rechts weiss"""
    # r._place_soldier(5, 3, Spieler.WHITE)
    # r._place_soldier(4, 4, Spieler.WHITE)
    # r._place_soldier(6, 2, Spieler.WHITE)

    # """Diagonal links weiss"""
    # r._place_soldier(3, 3, Spieler.WHITE)
    # r._place_soldier(4, 4, Spieler.WHITE)
    # r._place_soldier(2, 2, Spieler.WHITE)

    r._place_soldier(5, 5, Spieler.BLACK)
    r._place_soldier(6, 5, Spieler.BLACK)
    r._place_soldier(7, 5, Spieler.BLACK)

    r._place_soldier(6, 4, Spieler.BLACK)
    r._place_soldier(5, 3, Spieler.BLACK)
    r._place_soldier(6, 3, Spieler.BLACK)

    pprint(r.board)

    # move_cannon = r.move_cannon(5, 5, 8, 5, Spieler.BLACK) #horizontal down
    # move_cannon = r.move_cannon(7, 5, 4, 5, Spieler.BLACK) #horizontal up
    # move_cannon = r.move_cannon(6, 3, 6, 6, Spieler.BLACK)  # vertical right
    # move_cannon = r.move_cannon(6, 5, 6, 2, Spieler.BLACK)  # vertical left
    # move_cannon = r.move_cannon(7, 5, 4, 2, Spieler.BLACK)  # diagonal left up
    move_cannon = r.move_cannon(5, 3, 8, 6, Spieler.BLACK)  # diagonal right down

    pprint(move_cannon)

    rooms.pop(r.name)
