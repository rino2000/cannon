import random
from collections import Counter
from dataclasses import dataclass, field
from enum import IntEnum
from itertools import chain, compress, filterfalse, starmap
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

    def _soldier_not_allowed_moves(self, x: int, y: int, player: Player) -> list[Coord]:
        direction: int = player.direction
        coords = [
            (x, y - 1),
            (x, y + 1),
            (x - 1 * direction, y),
            (x - 1 * direction, y - 1),
            (x - 1 * direction, y + 1),
        ]
        return filterfalse(lambda c: self._validate_coordinate(*c) == False, coords)

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
            return emit("info", {"message": "Move Coord nicht valide"}, to=sid)

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

        if (endX, endY) in self._soldier_not_allowed_moves(startX, startY, player):
            return emit("info", {"message": "Soldier cant move there"}, to=sid)

        self._swap(startX, startY, endX, endY, sid)
        return emit("info", {"turn": f"Turn: {self._turn.name}"}, broadcast=True)

    def _is_cannon_axis(self, startX: int, startY: int, sid: str) -> bool:
        player: Player = self._get_player(sid)
        all_cannons = self._get_all_cannons(startX, startY, player)
        axis: list[Coord] = self._get_cannon_gun_axis(all_cannons, player)
        return any(((startX, startY) == axis) for axis in axis)

    def _check_capture_town(self, x: int, y: int, player: Player) -> list[Coord]:
        xs = [x] * 2 + [x + player.direction] * 3
        ys = [y - 1, y + 1] + list(range(y - 1, y + 2))
        v = filter(lambda c: self._validate_coordinate(*c), zip(xs, ys))
        return filterfalse(lambda c: self.board[c[0]][c[1]] != player.opponent_town, v)

    def _check_capture_soldier(self, x: int, y: int, player: Player) -> list[Coord]:
        xs = [x] * 2 + [x + player.direction] * 3
        ys = [y - 1, y + 1] + list(range(y - 1, y + 2))
        v = filter(lambda c: self._validate_coordinate(*c), zip(xs, ys))
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
        valid = filter(lambda c: self._validate_coordinate(*c), zip(xs, ys))
        return any(self.board[c[0]][c[1]] == player.opponent for c in valid)

    def _check_interception_thread_move(
        self, x: int, y: int, player: Player
    ) -> list[Coord]:
        offsets = [((-1, 0), (-2, 0)), ((-1, 1), (-2, 2)), ((-1, -1), (-2, -2))]

        interceptions = list(Soldier) + list(Town)
        valid = [
            (first, second)
            for (dx1, dy1), (dx2, dy2) in offsets
            for first, second in [
                (
                    (x + dx1 * player.direction, y + dy1),
                    (x + dx2 * player.direction, y + dy2),
                )
            ]
            if self._validate_coordinate(*first)
            and self._validate_coordinate(*second)
            and self.board[first[0]][first[1]] not in interceptions
            and self.board[second[0]][second[1]] not in interceptions
        ]

        # Return the max or min of each pair depending on player
        return [max(pair) if player == Player.BLACK else min(pair) for pair in valid]

    def _get_all_cannons(self, x: int, y: int, player: Player):
        soldier = player.soldier.value

        # All offset-pairs: ( (dx1,dy1), (dx2,dy2) )
        offsets = [
            ((1, 0), (2, 0)),
            ((-1, 0), (-2, 0)),
            ((1, 0), (-1, 0)),  # vertical
            ((1, 1), (2, 2)),
            ((-1, -1), (-2, -2)),
            ((1, 1), (-1, -1)),
            ((-1, 1), (-2, 2)),  # diag right
            ((1, -1), (2, -2)),
            ((-1, -1), (-2, -2)),
            ((1, -1), (-1, 1)),  # diag left
            ((0, -1), (0, -2)),
            ((0, -1), (0, 1)),
            ((0, 1), (0, 2)),  # horizontal
        ]

        # Generate all candidate pairs, validate, and check if both are soldiers
        result = []
        for (dx1, dy1), (dx2, dy2) in offsets:
            first = (x + dx1 * player.direction, y + dy1)
            second = (x + dx2 * player.direction, y + dy2)
            if (
                self._validate_coordinate(*first)
                and self._validate_coordinate(*second)
                and self.board[first[0]][first[1]] == soldier
                and self.board[second[0]][second[1]] == soldier
            ):
                result.append((first, second, (x, y)))
        return result

    def _get_cannon_gun_axis(
        self, coords: list[tuple[Coord, Coord]], player: Player
    ) -> list[Coord]:
        """Return List of all cannon gun axis available"""
        return [(min if player == Player.WHITE else max)(coord) for coord in coords]

    def _get_cannon_axis(self, coords: list[tuple[Coord, Coord]]):
        return [(min(x), max(x)) for x in coords]

    def _cannon_shoot_intercepted(self, x: int, y: int, player: Player) -> bool:
        coords = zip([x + 3 * player.direction] * 3, range(y - 3, y + 3 + 1, 3))
        validate = filter(lambda c: self._validate_coordinate(*c), coords)
        return any(self.board[c[0]][c[1]] in list(Soldier) for c in validate)

    def _check_cannon_shoot_validate(self, startX: int, startY: int, player: Player):
        xs = [startX + s * player.direction for s in range(4, 6)] * 3
        ys = [startY + off for s in range(4, 6) for off in range(-s, s + 1, s)]
        return list(filter(lambda c: self._validate_coordinate(*c), zip(xs, ys)))

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

    def _check_all_possbible_cannon_moves(self, cannons, player: Player):
        d = player.direction
        axis = self._get_cannon_axis(cannons)

        # (axis coord, possible coord)
        all_moves = chain.from_iterable(
            (
                (top, (top[0] - 3 * d, top[1])),
                (top, (top[0] + 3 * d, bottom[1])),
                (top, (top[0] - 3 * d, top[1] + 3)),
                (top, (top[0] + 3 * d, top[1] + 3)),
                (top, (top[0] - 3 * d, top[1] - 3)),
                (top, (top[0] + 3 * d, top[1] - 3)),
                (top, (top[0], top[1] + 3)),
                (bottom, (bottom[0] + 3 * d, bottom[1])),
                (bottom, (bottom[0] - 3 * d, bottom[1])),
                (bottom, (bottom[0] + 3 * d, bottom[1] - 3)),
                (bottom, (bottom[0] - 3 * d, bottom[1] - 3)),
                (bottom, (bottom[0] + 3 * d, bottom[1] + 3)),
                (bottom, (bottom[0] - 3 * d, bottom[1] + 3)),
                (bottom, (bottom[0], bottom[1] - 3)),
            )
            for top, bottom in axis
        )

        valid = set(filter(lambda c: self._validate_coordinate(*c[1]), all_moves))
        return list(compress(valid, (self._is_cannon(*p[1], player) for p in valid)))

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
