import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import batched, chain, compress, filterfalse, starmap
from threading import Lock
from typing import Final, Self

import flask_socketio
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


class Player(IntEnum):
    WHITE = 1
    BLACK = 2

    @property
    def direction(self) -> int:
        return 1 if self == Player.WHITE else -1

    @property
    def opponent(self) -> Self:
        return Player.WHITE if self == Player.BLACK else Player.BLACK

    @property
    def opponent_town(self) -> Town:
        return Town.WHITE if self == Player.BLACK else Town.BLACK

    @property
    def town(self) -> Town:
        return Town.WHITE if self == Player.WHITE else Town.BLACK

    @property
    def soldier(self) -> Soldier:
        return Soldier.WHITE if self == Player.WHITE else Soldier.BLACK


class GameState(IntEnum):
    PLACE_SOLDATEN = 0
    MOVE_SOLDATEN = 1
    GAME_OVER = 2
    SURRENDER = 3


@dataclass
class Room:
    name: str = field(default_factory=str, init=True)
    board: Field = field(
        default_factory=lambda: [
            [0 for _ in range(BOARD_SIZE)] for _ in range(BOARD_SIZE)
        ],
        init=False,
    )
    players: dict[str, Player] = field(default_factory=dict, init=False)  # {sid:color}
    gameState: GameState = field(default=GameState.PLACE_SOLDATEN, init=False)
    white_captured: int = field(default=0, init=False)
    black_captured: int = field(default=0, init=False)
    _lock: Lock = field(default_factory=Lock, init=False)
    _turn: Player = field(default=Player.WHITE, init=False)

    def __post_init__(self):
        rooms[self.name] = self

    def join_room(self, sid: str) -> None:
        if self.room_is_full():
            return emit("info", {"message": "Room is already full"}, to=sid)

        if not self.players:
            color: Player = random.choice(list(Player))
        else:
            existing_color: Player = next(iter(self.players.values()))
            color: Player = existing_color.opponent

        self.players[sid] = color

        return emit(
            "joined_room",
            {
                "board": self.board,
                "player": color.value,
                "capture": f"Capture: {0}",
                "turn": f"Turn: {self._turn.name}",
                "message": f"Soldaten left {MAX_SOLDIERS}",
            },
            to=sid,
        )

    def _validate_coordinate(self, x: int, y: int) -> bool:
        return (0 <= x < BOARD_SIZE) and (0 <= y < BOARD_SIZE)

    def place_object(self, x: int, y: int, sid: str) -> None:
        return self._check_placement(x, y, sid)

    def _place_soldier(self, x: int, y: int, player: Player) -> None:
        self.board[x][y] = player.soldier.value

    def _place_town(self, x: int, y: int, player: Player) -> None:
        self.board[x][y] = player.town.value
        if self._all_objects_placed():
            self.gameState = GameState.MOVE_SOLDATEN

    def _count_objects(self, player: Player) -> tuple[int, int]:
        count = Counter(chain(*self.board))
        return (count[player.soldier], count[player.town])

    def _all_objects_placed(self) -> bool:
        return all(self._count_objects(s) == (MAX_SOLDIERS, 1) for s in set(Player))

    def _white_placed_all(self) -> bool:
        return self._count_objects(Player.WHITE) == (MAX_SOLDIERS, 1)

    def _get_player(self, sid: str) -> Player | None:
        if player := self.players.get(sid):
            return player
        else:
            return emit("info", {"message": f"{sid} not in players"}, to=sid)

    def room_is_full(self) -> bool:
        return len(self.players) >= MAX_PLAYERS_IN_ROOM

    def _check_placement(self, x: int, y: int, sid: str) -> None:
        if not self.room_is_full():
            return emit("info", {"message": "warte auf den anderen gegner"}, to=sid)

        if self._all_objects_placed():
            return emit(
                "info", {"message": "Now move soldaten"}, to=sid, broadcast=True
            )

        if self.board[x][y] != EMPTY:
            return emit("info", {"message": f"koord {x, y} ist nicht leer"}, to=sid)

        player: Player = self._get_player(sid)
        soldiers, town = self._count_objects(player)
        is_white: bool = player == Player.WHITE

        if player == Player.BLACK and not self._white_placed_all():
            return emit("info", {"message": "white muss zuerst alles placen"}, to=sid)

        allowed_placement_soldier: bool = (
            (x in range(1, 4)) and (y in range(1, BOARD_SIZE))
            if is_white
            else (x in range(6, BOARD_SIZE - 1)) and (y in range(BOARD_SIZE))
        )

        allowed_placement_town: bool = (
            (x == 0) and (y in range(1, BOARD_SIZE - 1))
            if is_white
            else (x == BOARD_SIZE - 1) and (y in range(1, BOARD_SIZE - 1))
        )

        opponent_sid: str = next(s for s in set(self.players.keys()) if s != sid)

        if soldiers < MAX_SOLDIERS:
            if not allowed_placement_soldier:
                return emit("info", {"message": f"cant place Soldier {x, y}"}, to=sid)

            self._place_soldier(x, y, player)
            remaining = MAX_SOLDIERS - (soldiers + 1)

            emit("info", {"message": f"{remaining} Soldiers left"}, to=sid)
            emit(
                "info",
                {"message": f"{remaining} Soldiers left for {player.name}"},
                to=opponent_sid,
            )
            emit("update_field", self.board, to=sid, broadcast=True)

            if soldiers == MAX_SOLDIERS - 1:
                return emit("info", {"message": "Now place Town"}, to=sid)
        else:
            if (town == 0) and (not allowed_placement_town):
                return emit("info", {"message": f"Cant place Town here {x, y}"}, to=sid)
            elif town == 0 and player == Player.WHITE:
                self._place_town(x, y, player)
                emit("update_field", self.board, to=sid, broadcast=True)
                emit("info", {"message": "Wait for black"}, to=sid)
                emit("info", {"message": "Now place soldiers"}, to=opponent_sid)
                self.switch_turn(player)
                return emit(
                    "info", {"turn": f"Turn: {self._turn.name}"}, broadcast=True
                )
            elif town == 0 and player == Player.BLACK:
                self._place_town(x, y, player)
                emit("update_field", self.board, to=sid, broadcast=True)
                self.gameState = GameState.MOVE_SOLDATEN
                emit("info", {"gameState": self.gameState}, broadcast=True)
                self.switch_turn(player)
                emit("info", {"turn": f"Turn: {self._turn.name}"}, broadcast=True)
                emit("info", {"message": "Wait for White"}, to=sid)
                return emit("info", {"message": "Now Move Soldiers"}, to=opponent_sid)

    def switch_turn(self, player: Player) -> None:
        with self._lock:
            self._turn = player.opponent

    def capture_town(self, startX: int, startY: int, sid: str):
        player: Player = self._get_player(sid)
        with self._lock:
            self.board[startX][startY] = EMPTY
            self.gameState = GameState.GAME_OVER
        return emit(
            "info",
            {
                "message": "Game Over",
                "turn": "",
                "gameState": self.gameState,
                "winner": f"Winner: {player.name}",
            },
            to=sid,
            broadcast=True,
        )

    def move_object(
        self, startX: int, startY: int, endX: int, endY: int, sid: str
    ) -> None:
        if self.gameState == GameState.GAME_OVER:
            return emit("info", {"message": "Game Over"}, to=sid)

        if self.gameState != GameState.MOVE_SOLDATEN:
            return emit("info", {"message": "Nicht in move soldaten gamestate"}, to=sid)

        if not (
            self._validate_coordinate(startX, startY)
            or self._validate_coordinate(endX, endY)
        ):
            return emit(
                "info", {"message": f"Not valide {startX, startY} {endX, endY}"}, to=sid
            )

        player: Player = self._get_player(sid)

        if self._turn != player:
            return emit("info", {"message": "Nicht dein Turn"}, to=sid)

        if self.board[startX][startY] in set(Town):
            return emit("info", {"message": "Städte nicht bewegen"}, to=sid)

        if self.board[endX][endY] == player.soldier:
            return emit("info", {"message": "Feld ist besetzt"}, to=sid)

        if self.board[startX][startY] != player.soldier:
            return emit("info", {"message": "Nicht dein soldat"}, to=sid)

        if self._check_threat(startX, startY, player) and (
            endX,
            endY,
        ) in self._check_interception_thread_move(startX, startY, player):
            emit("info", {"message": f"thread move {endX, endY} moved"}, to=sid)
            return self._swap(startX, startY, endX, endY, sid)

        if (endX, endY) in self._check_capture_town(startX, startY, player):
            return self.capture_town(startX, startY, sid)

        if (endX, endY) in self._check_capture_soldier(startX, startY, player):
            capture: int = self.capture_soldier(startX, startY, endX, endY, sid)
            emit("info", {"capture": f"Capture: {capture}"}, to=sid)
            return emit("info", {"turn": f"Turn: {self._turn.name}"}, broadcast=True)

        if (
            player == Player.WHITE
            and (startX - endX) == 1
            or player == Player.BLACK
            and (startX - endX) == -1
        ):
            return emit(
                "info", {"message": "du darf nicht 1 schritt nachhinten"}, to=sid
            )

        if self._is_cannon(startX, startY, player) and self._is_cannon_axis(
            startX, startY, sid
        ):
            if self._cannon_shoot_intercepted(startX, startY, player):
                return emit("info", {"message": "cannon shoot intercepted"}, to=sid)

            if (endX, endY) in self._check_cannon_shoot_validate(
                startX, startY, player
            ):
                return self.cannon_shoot(startX, startY, endX, endY, sid)
            else:
                return self.move_cannon(startX, startY, endX, endY, sid)

        if abs(endY - startY) > 1 or abs(endX - startX) > 1:
            return emit("info", {"message": "soldat darf nur 1 schritt machen"}, to=sid)

        self._swap(startX, startY, endX, endY, sid)
        return emit("info", {"turn": f"Turn: {self._turn.name}"}, broadcast=True)

    def _is_cannon_axis(self, startX: int, startY: int, sid: str) -> bool:
        player: Player = self._get_player(sid)
        all_cannons = self._get_all_cannons(startX, startY, player)
        axis = self._get_cannon_gun_axis(all_cannons, player)
        return (startX, startY) == axis

    def _check_capture_town(self, x: int, y: int, player: Player) -> list[Coord]:
        coords = zip(
            [x] * 2 + [x + player.direction] * 3,
            [y - 1, y + 1] + list(range(y - 1, y + 2)),
        )
        v = filter(lambda c: self._validate_coordinate(*c), coords)
        return filterfalse(lambda c: self.board[c[0]][c[1]] != player.opponent_town, v)

    def _check_capture_soldier(self, x: int, y: int, player: Player) -> list[Coord]:
        coords = zip(
            [x] * 2 + [x + player.direction] * 3,
            [y - 1, y + 1] + list(range(y - 1, y + 2)),
        )
        v = filter(lambda c: self._validate_coordinate(*c), coords)
        return filterfalse(lambda c: self.board[c[0]][c[1]] != player.opponent, v)

    def _capture_soldier(self, player: Player) -> int:
        with self._lock:
            if player == Player.WHITE:
                self.white_captured += 1
                return self.white_captured
            else:
                self.black_captured += 1
                return self.black_captured

    def capture_soldier(
        self, startX: int, startY: int, endX: int, endY: int, sid: str
    ) -> int:
        player: Player = self._get_player(sid)
        self._swap(startX, startY, endX, endY, sid)
        return self._capture_soldier(player)

    def _check_threat(self, x: int, y: int, player: Player) -> bool:
        xs = [x] * 2 + [x + player.direction] * 3
        ys = [y - 1, y + 1] + list(range(y - 1, y + 2))
        coords = zip(xs, ys)
        valid = filter(lambda c: self._validate_coordinate(*c), coords)
        return any(self.board[c[0]][c[1]] == player.opponent for c in valid)

    def _check_interception_thread_move(
        self, x: int, y: int, player: Player
    ) -> list[Coord]:
        """Return list of all possible thread moves"""

        direction: int = player.direction

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
            if player == Player.BLACK
            else list(map(min, all_possible_coords))
        )

    def _get_all_cannons(self, x: int, y: int, player: Player):
        direction: int = player.direction
        soldier: Soldier = player.soldier.value

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
        self, coords: list[tuple[Coord, Coord]], player: Player
    ) -> Coord:
        coords = list(chain(*coords))
        return (
            min(coords, key=lambda x: x[0])
            if player == Player.WHITE
            else max(coords, key=lambda x: x[0])
        )

    def _get_cannon_axis(self, coords: list[tuple[Coord, Coord]]):
        return [(min(x), max(x)) for x in coords]

    def _cannon_shoot_intercepted(self, x: int, y: int, player: Player) -> bool:
        coords = zip([x + 3 * player.direction] * 3, range(y - 3, y + 3 + 1, 3))
        validate = filter(lambda c: self._validate_coordinate(*c), coords)
        return any(self.board[c[0]][c[1]] in list(Soldier) for c in validate)

    def _check_cannon_shoot_validate(self, startX: int, startY: int, player: Player):
        coords = zip(
            [startX + s * player.direction for s in range(4, 6) for _ in range(3)],
            [startY + off for s in range(4, 6) for off in range(-s, s + 1, s)],
        )
        return filterfalse(lambda c: self._validate_coordinate(*c) == False, coords)

    def cannon_shoot(self, startX: int, startY: int, endX: int, endY: int, sid: str):
        player: Player = self._get_player(sid)

        if self.board[endX][endY] == player.opponent_town:
            return self.capture_town(startX, startY, sid)

        if self.board[endX][endY] in [EMPTY, player.soldier]:
            return emit("info", {"message": "target is invalide"}, to=sid)

        self._capture_soldier(player)
        self.switch_turn(player)
        with self._lock:
            self.board[endX][endY] = EMPTY
        return emit("info", {"message": f"cannon shoot capture {endX, endY}"}, to=sid)

    def _check_all_possbible_cannon_moves(
        self, cannons: list[tuple[Coord]], player: Player
    ):
        """Return list of all coord pairs after calculate axis swap that are cannons"""

        axis = self._get_cannon_axis(cannons)
        direction: int = player.direction

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
        cannons = (self._is_cannon(*x[1], player) for x in validate)

        return list(compress(validate, cannons))

    def _swap(self, startX: int, startY: int, endX: int, endY: int, sid: str) -> None:
        player: Player = self._get_player(sid)
        with self._lock:
            self.board[startX][startY] = EMPTY
            self.board[endX][endY] = player.soldier.value
        return self.switch_turn(player)

    def _is_cannon(self, x: int, y: int, player: Player) -> bool:
        cannons = self._get_all_cannons(x, y, player)
        return any(len(x) == 3 for x in cannons)

    def move_cannon(self, startX: int, startY: int, endX: int, endY: int, sid: str):
        player: Player = self._get_player(sid)
        cannons = self._get_all_cannons(startX, startY, player)

        possible_moves = self._check_all_possbible_cannon_moves(cannons, player)

        coord = ((startX, startY), (endX, endY))
        moves = filterfalse(lambda move: coord != move, possible_moves)

        target_coord = list(starmap(lambda _, target: target, moves))

        if not moves or (coord[1] not in target_coord):
            return emit(
                "info", {"message": f"Move {coord} nicht moglich zu moven"}, to=sid
            )

        return self._swap(startX, startY, endX, endY, sid)

    def surrender(self, player: Player) -> Player:
        self.gameState = GameState.GAME_OVER
        return player.opponent

    def disconnect(self, sid: str) -> None:
        opponent_sid: str = next(s for s in set(self.players.keys()) if s != sid)
        with self._lock:
            self.players.pop(opponent_sid)
        emit("info", {"message": "Opponent disconnected"}, to=opponent_sid)
        return flask_socketio.disconnect()


rooms: dict[str, Room] = {}


@app.get("/")
def hello_world():
    return render_template("view.html")


@socketio.on("join_room")
def join(name: str) -> None:
    sid: str = request.sid  # Session ID

    if name not in rooms:
        rooms[name] = Room(name)

    return rooms[name].join_room(sid)


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
    return emit("update_field", r.board, broadcast=True)


@socketio.on("surrender")
def handle_surrender(player: int, room: str):
    sid: str = request.sid

    if not (r := rooms.get(room)):
        return emit("info", f"No room with this name {room}", to=sid)

    winner: Player = r.surrender(Player(player))
    emit(
        "info",
        {"message": "Game Over", "winner": f"Winner {winner.name}"},
        broadcast=True,
    )
    lock = Lock()
    with lock:
        rooms.pop(r.name)
        del r
    return flask_socketio.disconnect()


@socketio.on("disconnect")
def handle_disconnect(room: str):
    sid: str = request.sid

    if not (r := rooms.get(room)):
        return emit("info", f"No room with this name {room}", to=sid)

    return r.disconnect(sid)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=8000, debug=True)
