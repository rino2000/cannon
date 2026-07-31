import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import batched, chain, compress, filterfalse, starmap
from threading import Lock
from typing import Final, Self

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

EMPTY: Final = 0
MAX_SOLDIERS: Final = 15
MAX_PLAYERS_IN_ROOM: Final = 2
BOARD_SIZE: Final = 10  # 10x10

type Field = list[list[int]]
type Coord = tuple[int, int]


class Town(IntEnum):
    WHITE = 3  # 🏠
    BLACK = 4  # 🏡


class Soldier(IntEnum):
    WHITE = 1  # 👇🏻
    BLACK = 2  # 👆🏿


class Spieler(IntEnum):
    WHITE = 1
    BLACK = 2

    @property
    def direction(self) -> int:
        return 1 if self == Spieler.WHITE else -1

    @property
    def opponent(self) -> Self:
        return Spieler.WHITE if self == Spieler.BLACK else Spieler.BLACK


class GameState(IntEnum):
    PLACE_SOLDATEN = 0
    MOVE_SOLDATEN = 1
    GAME_OVER = 2
    SURRENDER = 3


@dataclass
class Room:
    name: str = field(default_factory=str, init=True)
    board: Field = field(
        default_factory=lambda: np.zeros(
            (BOARD_SIZE, BOARD_SIZE), dtype=np.uint8
        ).tolist(),
        init=False,
    )
    players: dict[str, Spieler] = field(default_factory=dict, init=False)  # {sid:color}
    gameState: GameState = field(default=GameState.PLACE_SOLDATEN, init=False)
    white_captured: int = field(default=0, init=False)
    black_captured: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    _turn: Spieler = field(default=Spieler.WHITE, init=False)

    def __post_init__(self):
        rooms[self.name] = self

    def join_room(self, sid: str) -> None:
        if self.room_is_full():
            return emit("info", {"message": "Room is already full"}, to=sid)

        if not self.players:
            color = random.choice(list(Spieler))
            self.players |= {sid: color}
            capture: int = (
                self.black_captured if color == Spieler.BLACK else self.white_captured
            )
            return emit(
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

        left = set(Spieler) - set(self.players.values())
        color = left.pop()
        self.players |= {sid: color}
        capture: int = (
            self.black_captured if color == Spieler.BLACK else self.white_captured
        )
        return emit(
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

    def _validate_coordinate(self, x: int, y: int) -> bool:
        return (0 <= x < BOARD_SIZE) and (0 <= y < BOARD_SIZE)

    def place_object(self, x: int, y: int, sid: str) -> None:
        return self._check_placement(x, y, sid)

    def _place_soldier(self, x: int, y: int, spieler: Spieler) -> None:
        self.board[x][y] = Soldier.WHITE if spieler == Spieler.WHITE else Soldier.BLACK

    def _place_town(self, x: int, y: int, spieler: Spieler) -> None:
        town = Town.WHITE if spieler == Spieler.WHITE else Town.BLACK
        self.board[x][y] = town
        if self._all_objects_placed():
            self.gameState = GameState.MOVE_SOLDATEN

    def _count_objects(self, spieler: Spieler) -> tuple[int, int]:
        color = Soldier.WHITE if spieler == Spieler.WHITE else Soldier.BLACK
        c = Counter(chain(*self.board))
        soldiers = c[Soldier.WHITE if color == Soldier.WHITE else Soldier.BLACK]
        town = c[Town.WHITE if color == Soldier.WHITE else Town.BLACK]
        return (soldiers, town)

    def _all_objects_placed(self) -> bool:
        return all(self._count_objects(s) == (MAX_SOLDIERS, 1) for s in set(Spieler))

    def _white_placed_all(self) -> bool:
        return self._count_objects(Spieler.WHITE) == (MAX_SOLDIERS, 1)

    def _get_player(self, sid: str) -> Spieler | None:
        if player := self.players.get(sid):
            return player
        else:
            return emit("info", {"message": f"{sid} not in players"}, to=sid)

    def room_is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS_IN_ROOM

    def _coord_is_empty(self, x: int, y: int) -> bool:
        return self.board[x][y] == EMPTY

    def _check_placement(self, x: int, y: int, sid: str) -> None:
        if not self.room_is_full():
            return emit("info", {"message": "warte auf den anderen gegner"}, to=sid)

        if self._all_objects_placed():
            return emit("info", {"message": "Now move soldaten"}, to=sid)

        if not self._coord_is_empty(x, y):
            return emit("info", {"message": f"koord {x, y} ist nicht leer"}, to=sid)

        spieler: Spieler = self._get_player(sid)
        soldiers, town = self._count_objects(spieler)
        is_white: bool = spieler == Spieler.WHITE

        if spieler == Spieler.BLACK and not self._white_placed_all():
            return emit("info", {"message": "white muss zuerst alles placen"}, to=sid)

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
                return emit("info", {"message": f"cant place Soldier {x, y}"}, to=sid)

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
                return emit("info", {"message": "Now place Town"}, to=sid)
        else:
            if (town == 0) and (not allowed_placement_town):
                return emit("info", {"message": f"Cant place Town here {x, y}"}, to=sid)
            elif town == 0 and spieler == Spieler.WHITE:
                self._place_town(x, y, spieler)
                emit("update_field", self.board, to=sid, broadcast=True)
                emit("info", {"message": "Wait for black"}, to=sid)
                emit("info", {"message": "Now place soldiers"}, to=opponent_sid)
                self.switch_turn(spieler)
                return emit("info", {"turn": self._turn.value}, broadcast=True)
            elif town == 0 and spieler == Spieler.BLACK:
                self._place_town(x, y, spieler)
                emit("update_field", self.board, to=sid, broadcast=True)
                self.gameState = GameState.MOVE_SOLDATEN
                emit("info", {"gameState": self.gameState}, broadcast=True)
                self.switch_turn(spieler)
                emit("info", {"turn": self._turn.value}, broadcast=True)
                emit("info", {"message": "Wait for White"}, to=sid)
                return emit("info", {"message": "Now Move Soldiers"}, to=opponent_sid)

    def switch_turn(self, spieler: Spieler) -> None:
        with self._lock:
            self._turn = spieler.opponent

    def move_object(
        self, startX: int, startY: int, endX: int, endY: int, sid: str
    ) -> None:

        if self.gameState != GameState.MOVE_SOLDATEN:
            return emit("info", {"message": "Nicht in move soldaten gamestate"}, to=sid)

        if not (
            self._validate_coordinate(startX, startY)
            and self._validate_coordinate(endX, endY)
        ):
            return emit(
                "info",
                {"message": f"Nicht valide {startX, startY} {endX, endY}"},
                to=sid,
            )

        spieler: Spieler = self._get_player(sid)

        if self._turn != spieler:
            return emit("info", {"message": "Nicht dein Turn"}, to=sid)

        if self.board[startX][startY] in set(Town):
            return emit(
                "info", {"message": "Du darfst die Stadt nicht bewegen"}, to=sid
            )

        soldier = Soldier.WHITE if spieler == Spieler.WHITE else Soldier.BLACK

        if self.board[startX][startY] != soldier:
            return emit("info", {"message": "Nicht dein soldat"}, to=sid)

        if self._check_threat(startX, startY, spieler) and (
            endX,
            endY,
        ) in self._check_interception_thread_move(startX, startY, spieler):
            emit("info", {"message": f"thread move {endX, endY} moved"}, to=sid)
            return self._swap(startX, startY, endX, endY, sid)

        if (endX, endY) in self._check_capture_soldier(startX, startY, spieler):
            capture: int = self.capture_soldier(startX, startY, endX, endY, sid)
            emit("info", {"capture": capture}, to=sid)
            return emit("info", {"turn": self._turn.name}, broadcast=True)

        if (
            spieler == Spieler.WHITE
            and (startX - endX) == 1
            or spieler == Spieler.BLACK
            and (startX - endX) == -1
        ):
            return emit(
                "info", {"message": "du darf nicht 1 schritt nachhinten"}, to=sid
            )

        if self._is_cannon(startX, startY, spieler) and self._is_cannon_axis(
            startX, startY, sid
        ):
            if self._cannon_shoot_intercepted(startX, startY, spieler):
                return emit("info", {"message": "cannon shoot intercepted"}, to=sid)

            if (endX, endY) in self._check_cannon_shoot_validate(
                startX, startY, spieler
            ):
                return self.cannon_shoot(endX, endY, sid)
            else:
                return self.move_cannon(startX, startY, endX, endY, sid)

        if abs(endY - startY) > 1 or abs(endX - startX) > 1:
            return emit("info", {"message": "soldat darf nur 1 schritt machen"}, to=sid)

        self._swap(startX, startY, endX, endY, sid)
        return emit("info", {"turn": self._turn.name}, broadcast=True)

    def _is_cannon_axis(self, startX: int, startY: int, sid: str) -> bool:
        spieler: Spieler = self._get_player(sid)
        all_cannons = self._get_all_cannons(startX, startY, spieler)
        axis = self._get_cannon_gun_axis(all_cannons, spieler)
        return (startX, startY) == axis

    def _check_capture_soldier(self, x: int, y: int, spieler: Spieler) -> list[Coord]:
        direction: int = spieler.direction

        coords = [
            (x, y - 1),  # left
            (x, y + 1),  # right
            (x + direction, y),  # above
            (x + direction, y - 1),  # diagonally left
            (x + direction, y + 1),  # diagonally right
        ]
        val = filter(lambda c: self._validate_coordinate(*c), coords)
        return filterfalse(lambda x: self.board[x[0]][x[1]] != spieler.opponent, val)

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
        self._swap(startX, startY, endX, endY, sid)
        return self._capture_soldier(player)

    def _check_threat(self, x: int, y: int, spieler: Spieler) -> bool:
        direction: int = spieler.direction
        coords = [
            (x, y - 1),  # left
            (x, y + 1),  # right
            (x + 1 * direction, y),  # above
            (x + 1 * direction, y - 1),  # diagonally left
            (x + 1 * direction, y + 1),  # diagonally right
        ]
        validate = filter(lambda c: self._validate_coordinate(*c), coords)
        return any(self.board[x[0]][x[1]] == spieler.opponent for x in validate)

    def _check_interception_thread_move(
        self, x: int, y: int, spieler: Spieler
    ) -> list[Coord]:
        """Return list of all possible thread moves"""

        direction: int = spieler.direction

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

        interceptions = list(Soldier) + list(Town)
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
    ) -> list[tuple[Coord, Coord]]:
        """Return all possibles cannon coordinates from a selected cannon coordinate"""

        direction: int = spieler.direction
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

    def _get_all_cannons(self, x: int, y: int, spieler: Spieler):
        direction: int = spieler.direction
        soldier = Soldier.WHITE if spieler == Spieler.WHITE else Soldier.BLACK

        all_possible_coords: list[tuple[Coord, Coord]] = []

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
        self, coords: list[tuple[Coord, Coord]], spieler: Spieler
    ) -> Coord:
        coords = list(chain(*coords))
        return (
            min(coords, key=lambda x: x[0])
            if spieler == Spieler.WHITE
            else max(coords, key=lambda x: x[0])
        )

    def _get_cannon_axis(self, coords: list[tuple[Coord, Coord]]):
        return [(min(x), max(x)) for x in coords]

    def _cannon_shoot_intercepted(self, x: int, y: int, spieler: Spieler) -> bool:
        direction: int = spieler.direction
        coords = [
            (x + 3 * direction, y),  # gerade
            (x + 3 * direction, y + 3),  # diagonal rechts
            (x + 3 * direction, y - 3),  # diagonal links
        ]
        valide = filter(lambda c: self._validate_coordinate(*c), coords)
        return any(self.board[c[0]][c[1]] in list(Soldier) for c in valide)

    def _check_cannon_shoot_validate(self, startX: int, startY: int, spieler: Spieler):
        direction: int = spieler.direction
        coords = [
            (startX + 4 * direction, startY),
            (startX + 5 * direction, startY),
            (startX + 4 * direction, startY + 4),
            (startX + 5 * direction, startY + 5),
            (startX + 4 * direction, startY - 4),
            (startX + 5 * direction, startY - 5),
        ]
        return filterfalse(lambda c: self._validate_coordinate(*c) == False, coords)

    def cannon_shoot(self, endX: int, endY: int, sid: str):
        player: Spieler = self._get_player(sid)
        soldier: Soldier = Soldier.WHITE if player == Spieler.WHITE else Soldier.BLACK

        if self.board[endX][endY] in (list(Town) + [EMPTY, soldier]):
            return emit("info", {"message": "target is invalide"}, to=sid)

        self._capture_soldier(player)
        self.switch_turn(player)
        with self._lock:
            self.board[endX][endY] = EMPTY
        return emit("info", {"message": f"cannon shoot capture {endX, endY}"}, to=sid)

    def _check_all_possbible_cannon_moves(
        self, cannons: list[tuple[Coord]], spieler: Spieler
    ):
        """Return list of all coord pairs after calculate axis swap that are cannons"""

        axis = self._get_cannon_axis(cannons)
        direction: int = spieler.direction

        # (axis coord ,possible coord)
        coords: list[tuple[Coord], tuple[Coord]] = []

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
        cannons = (self._is_cannon(*x[1], spieler) for x in validate)

        return list(compress(validate, cannons))

    def _swap(self, startX: int, startY: int, endX: int, endY: int, sid: str) -> None:
        spieler: Spieler = self._get_player(sid)
        soldier: Soldier = Soldier.WHITE if spieler == Spieler.WHITE else Soldier.BLACK

        with self._lock:
            self.board[startX][startY] = EMPTY
            self.board[endX][endY] = soldier
        return self.switch_turn(spieler)

    def _is_cannon(self, x: int, y: int, spieler: Spieler) -> bool:
        cannons = self._get_all_cannons(x, y, spieler)
        return any(len(x) == 3 for x in cannons)

    def move_cannon(self, startX: int, startY: int, endX: int, endY: int, sid: str):
        spieler: Spieler = self._get_player(sid)
        cannons = self._get_all_cannons(startX, startY, spieler)

        # if endX, endY != gun axis then move soldier
        # if (startX, startY) != self._get_cannon_gun_axis(cannons, spieler):
        #     return self._swap(startX, startY, endX, endY, sid)

        # if not cannons or ((startX, startY) not in chain(*cannons)):
        #     return emit(
        #         "info", {"message": f"{startX, startY} gibt keine cannons"}, to=sid
        #     )

        possible_moves = self._check_all_possbible_cannon_moves(cannons, spieler)

        coord = ((startX, startY), (endX, endY))
        moves = filterfalse(lambda move: coord != move, possible_moves)

        target_coord = list(starmap(lambda _, target: target, moves))

        if not moves or (coord[1] not in target_coord):
            return emit(
                "info", {"message": f"Move {coord} nicht moglich zu moven"}, to=sid
            )

        return self._swap(startX, startY, endX, endY, sid)


rooms: dict[str, Room] = {}


@app.get("/")
def hello_world():
    board = np.zeros((BOARD_SIZE, BOARD_SIZE), dtype=np.uint8)
    return render_template("view.html", data=board)


@socketio.on("join_room")
def join(name: str) -> None:
    sid: str = request.sid  # Session ID

    if name not in rooms:
        rooms[name] = Room(name)

    return rooms[name].join_room(sid)
    # join_room(room=name)


@socketio.on("place_soldaten")
def handle_place_soldaten(x: int, y: int, room: str) -> None:
    sid: str = request.sid

    if not (r := rooms.get(room)):
        return emit("info", f"No room with this name {room}", to=sid)

    r.place_object(x, y, sid)
    return emit("update_field", r.board, broadcast=True)


@socketio.on("move_object")
def handle_move_object(startX: int, startY: int, endX: int, endY: int, room: str):
    sid: str = request.sid

    if not (r := rooms.get(room)):
        return emit("info", f"No room with this name {room}", to=sid)

    r.move_object(startX, startY, endX, endY, sid)
    return emit("update_field", r.board, to=room, broadcast=True)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=8000, debug=True)
