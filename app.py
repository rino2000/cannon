import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import batched, chain, compress, filterfalse, starmap
from threading import Lock
from typing import Dict, List, Optional, Tuple

import numpy as np
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit

app = Flask(__name__)

app.config["SECRET_KEY"] = "secret!"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    sync_move="threading",
    logger=True,
    engineio_logger=True,
    ping_timeout=10000,
    ping_interval=10000,
)

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
    name: str = field(default_factory=str, init=True)
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
    _turn: Spieler = field(default=Spieler.WHITE, init=False)

    def __post_init__(self):
        rooms[self.name] = self

    def join_room(self, sid: str) -> None:
        if self.room_is_full():
            emit("info", {"message": "Room is already full"}, to=sid)
            return None

        if not self.players:
            color = random.choice(list(Spieler))
            self.players |= {sid: color}
            capture: int = (
                self.black_captured if color == Spieler.BLACK else self.white_captured
            )
            emit(
                "joined_room",
                {
                    "board": self.board,
                    "player": color.value,
                    "capture": capture,
                    "turn": self._turn.value,
                    "message": f"Soldaten left {MAX_SOLDIERS}",
                },
                to=sid,
            )
            return None

        left = set(Spieler) - set(self.players.values())
        color = left.pop()
        self.players |= {sid: color}
        capture: int = (
            self.black_captured if color == Spieler.BLACK else self.white_captured
        )
        emit(
            "joined_room",
            {
                "board": self.board,
                "player": color.value,
                "capture": capture,
                "turn": self._turn.value,
                "message": f"Soldaten left {MAX_SOLDIERS}",
            },
            to=sid,
        )
        return None

    def _validate_coordinate(self, x: int, y: int) -> bool:
        return (0 <= x < BOARD_SIZE) and (0 <= y < BOARD_SIZE)

    def place_object(self, x: int, y: int, sid: str) -> None:
        self._check_placement(x, y, sid)

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
        return self._count_objects(Spieler.WHITE) == (MAX_SOLDIERS, 1)

    def _get_player(self, sid: str) -> Optional[Spieler]:
        if player := self.players.get(sid):
            return player
        else:
            emit("info", {"message": f"{sid} not in players"}, to=sid)

    def room_is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS_IN_ROOM

    def _coord_is_empty(self, x: int, y: int) -> bool:
        return self.board[x][y] == EMPTY

    def _check_placement(self, x: int, y: int, sid: str) -> None:
        if not self.room_is_full():
            emit("info", {"message": "warte auf den anderen gegner"}, to=sid)
            return None

        if self._all_objects_placed():
            emit("info", {"message": "Now move soldaten"}, to=sid)
            return None

        if not self._coord_is_empty(x, y):
            emit("info", {"message": f"Koordinate {x, y} ist nicht leer"}, to=sid)
            return None

        spieler: Spieler = self._get_player(sid)
        soldiers, town = self._count_objects(spieler)
        is_white: bool = spieler == Spieler.WHITE

        if spieler == Spieler.BLACK and not self._white_placed_all():
            emit("info", {"message": "white muss zuerst alle objekte placen"}, to=sid)
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

        opponent_sid: str = next(s for s in set(self.players.keys()) if s != sid)

        if soldiers < MAX_SOLDIERS:
            if not allowed_placement_soldier:
                emit("info", {"message": f"Soldier cant place here {x, y}"}, to=sid)
                return None

            self._place_soldier(x, y, spieler)
            remaining = MAX_SOLDIERS - (soldiers + 1)

            emit("info", {"message": f"{remaining} Soldiers left"}, to=sid)
            emit(
                "info",
                {"message": f"{remaining} Soldiers left for {spieler.name}"},
                to=opponent_sid,
            )
            emit("update_field", self.board, to=sid, broadcast=True)

            if soldiers == MAX_SOLDIERS - 1:
                emit("info", {"message": "Now place Town"}, to=sid)
                return None
            return None
        else:
            if (town == 0) and (not allowed_placement_town):
                emit("info", {"message": f"Cant place Town here {x, y}"}, to=sid)
                return None
            elif town == 0 and spieler == Spieler.WHITE:
                self._place_town(x, y, spieler)
                emit("update_field", self.board, to=sid, broadcast=True)
                emit("info", {"message": "Wait for black"}, to=sid)
                emit("info", {"message": "Now place soldiers"}, to=opponent_sid)
                self.switch_turn(spieler)
                emit("info", {"turn": self._turn.value}, broadcast=True)
                return None
            elif town == 0 and spieler == Spieler.BLACK:
                self._place_town(x, y, spieler)
                emit("update_field", self.board, to=sid, broadcast=True)
                self.gameState = GameState.MOVE_SOLDATEN
                emit("info", {"gameState": self.gameState}, broadcast=True)
                self.switch_turn(spieler)
                emit("info", {"turn": self._turn.value}, broadcast=True)
                emit("info", {"message": "Wait for White"}, to=sid)
                emit("info", {"message": "Now Move Soldiers"}, to=opponent_sid)
                return None

    def switch_turn(self, spieler: Spieler) -> None:
        opponent: Spieler = next(s for s in set(Spieler) if s != spieler)
        self._turn = opponent

    def move_object(
        self, startX: int, startY: int, endX: int, endY: int, sid: str
    ) -> None:

        if self.gameState != GameState.MOVE_SOLDATEN:
            emit("info", {"message": "Nicht in move soldaten gamestate"}, to=sid)
            return None

        spieler: Spieler = self._get_player(sid)

        if self._turn != spieler:
            emit("info", {"message": "Nicht dein Turn"}, to=sid)
            return None

        if (self.board[startX][startY] == TOWN_BLACK) or (
            self.board[startX][startY] == TOWN_WHITE
        ):
            emit("info", {"message": "Du darfst die Stadt nicht bewegen"}, to=sid)
            return None

        soldier = WHITE if spieler == Spieler.WHITE else BLACK

        if self.board[startX][startY] != soldier:
            emit("info", {"message": f"Nicht dein soldat {soldier}"}, to=sid)
            return None

        if not (
            self._validate_coordinate(startX, startY)
            and self._validate_coordinate(endX, endY)
        ):
            emit(
                "info",
                {"message": f"Nicht valide {startX, startY} {endX, endY}"},
                to=sid,
            )
            return None

        if self._check_threat(startX, startY, spieler):
            if (endX, endY) in self._check_interception_thread_move(
                startX, startY, spieler
            ):
                emit("info", {"message": f"thread move {endX, endY} moved"}, to=sid)
                self._swap(startX, startY, endX, endY, sid)

        if (endX, endY) in self._check_capture_soldier(startX, startY, spieler):
            capture: int = self.capture_soldier(startX, startY, endX, endY, sid)
            emit("info", {"capture": capture}, to=sid)
            emit("info", {"turn": self._turn.value}, broadcast=True)
            return None

        if (
            spieler == Spieler.WHITE
            and (startX - endX) == 1
            or spieler == Spieler.BLACK
            and (startX - endX) == -1
        ):
            emit(
                "info",
                {"message": f"soldat: {soldier} darf nicht 1 schritt nachhinten"},
                to=sid,
            )
            return None

        if abs(endY - startY) > 1 or abs(endX - startX) > 1:
            emit(
                "info",
                {"message": "soldat darf nur 1 schritt in allen richtungen"},
                to=sid,
            )
            return None

        if self._is_cannon(startX, startY, spieler):
            return self.move_cannon(startX, startY, endX, endY, sid)

        self._swap(startX, startY, endX, endY, sid)
        emit("info", {"turn": self._turn.value}, broadcast=True)

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

    def _capture_soldier(self, spieler: Spieler) -> int:
        with self._lock:
            if spieler == Spieler.WHITE:
                self.white_captured += 1
                return self.white_captured
            else:
                self.black_captured += 1
                return self.black_captured

    def capture_soldier(
        self, startX: int, startY: int, endX: int, endY: int, sid: str
    ) -> int:
        player: Spieler = self._get_player(sid)
        # opponent_soldir = WHITE if player == Spieler.BLACK else BLACK

        # if self.board[endX][endY] == opponent_soldir:
        # capture: int = self._capture_soldier(player)
        self._swap(startX, startY, endX, endY, sid)
        return self._capture_soldier(player)

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
            filter(lambda c: self._validate_coordinate(*c), chain(*coords)), 2
        )

        f = filterfalse(lambda x: len(x) < 2, valide_coords)

        interceptions = [WHITE, BLACK, TOWN_BLACK, TOWN_WHITE]
        all_possible_coords = list(compress(valide_coords, f))

        # check for interception
        for coord in all_possible_coords:
            x, y = coord
            if (self.board[x[0]][x[1]] in interceptions) or (
                self.board[y[0]][y[1]] in interceptions
            ):
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
        direction = 1 if spieler == Spieler.WHITE else -1

        # (axis coord ,possible coord)
        coords: List[Tuple[Tuple[int, int]], Tuple[int, int]] = []

        for x in axis:
            top, bottom = x
            # vertical
            coords.append(((top), (top[0] - 3 * direction, top[1])))
            coords.append(((top), (top[0] + 3 * direction, bottom[1])))
            coords.append(((bottom), (bottom[0] + 3 * direction, bottom[1])))
            coords.append(((bottom), (bottom[0] - 3 * direction, bottom[1])))

            # diagonally left
            coords.append(((top), (top[0] - 3 * direction, top[1] + 3)))
            coords.append(((top), (top[0] + 3 * direction, top[1] + 3)))
            coords.append(((bottom), (bottom[0] + 3 * direction, bottom[1] - 3)))
            coords.append(((bottom), (bottom[0] - 3 * direction, bottom[1] - 3)))

            # diagonally right
            coords.append(((top), (top[0] - 3 * direction, top[1] - 3)))
            coords.append(((top), (top[0] + 3 * direction, top[1] - 3)))
            coords.append(((bottom), (bottom[0] + 3 * direction, bottom[1] + 3)))
            coords.append(((bottom), (bottom[0] - 3 * direction, bottom[1] + 3)))

            # horizontal
            coords.append(((top), (top[0], top[1] + 3)))
            coords.append(((bottom), (bottom[0], bottom[1] - 3)))

        validate = set(filter(lambda c: self._validate_coordinate(*c[1]), coords))
        cannons = list(map(lambda x: self._is_cannon(*x[1], spieler), validate))

        return list(compress(validate, cannons))

    def _swap(self, startX: int, startY: int, endX: int, endY: int, sid: str) -> None:
        spieler: Spieler = self._get_player(sid)
        soldier = WHITE if spieler == Spieler.WHITE else BLACK

        self.board[startX][startY] = EMPTY
        self.board[endX][endY] = soldier
        return self.switch_turn(spieler)

    def _is_cannon(self, x: int, y: int, spieler: Spieler) -> bool:
        cannons = self._get_all_cannons(x, y, spieler)
        return any(map(lambda x: len(x) == 3, cannons))

    def move_cannon(self, startX: int, startY: int, endX: int, endY: int, sid: str):

        spieler: Spieler = self._get_player(sid)
        cannons = self._get_all_cannons(startX, startY, spieler)

        # if endX, endY != gun axis then move soldier
        if (startX, startY) != self._get_cannon_gun_axis(cannons, spieler):
            return self._swap(startX, startY, endX, endY, sid)

        if not cannons or ((startX, startY) not in chain(*cannons)):
            emit("info", {"message": f"{startX, startY} gibt keine cannons"}, to=sid)
            return None

        possible_moves = self._check_all_possbible_cannon_moves(cannons, spieler)

        coord = ((startX, startY), (endX, endY))
        moves = list(filter(lambda move: coord == move, possible_moves))

        target_coord = list(starmap(lambda _, target: target, moves))

        if not moves or (coord[1] not in target_coord):
            emit("info", {"message": f"Move {coord} nicht moglich zu moven"}, to=sid)
            return None

        self._swap(startX, startY, endX, endY, sid)


rooms: Dict[str, Room] = {}


@app.get("/")
def hello_world():
    return render_template(
        "view.html", data=np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=np.uint8)
    )


@socketio.on("join_room")
def join(name: str):
    sid: str = request.sid  # Session ID

    if name not in rooms:
        rooms[name] = Room(name)

    room = rooms[name]
    room.join_room(sid)
    # join_room(room=name)


@socketio.on("place_soldaten")
def handle_place_soldaten(x: int, y: int, room: str):
    sid: str = request.sid
    r: Room = rooms[room]

    if not r:
        emit("info", f"No room with this name {room}", to=sid)

    r.place_object(x, y, sid)
    emit("update_field", r.board, broadcast=True)


@socketio.on("move_object")
def handle_move_object(startX: int, startY: int, zielX: int, zielY: int, room: str):
    sid: str = request.sid
    r: Room = rooms[room]

    if not r:
        emit("info", f"No room with this name {room}", to=sid)

    r.move_object(startX, startY, zielX, zielY, sid)
    emit("update_field", r.board, to=room, broadcast=True)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=8000, debug=True)
