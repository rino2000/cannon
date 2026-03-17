import random
from enum import IntEnum
from pprint import pprint
from typing import Dict, List, Tuple

import numpy as np
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)

app.config["SECRET_KEY"] = "secret!"

socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    sync_move="threading",
    logger=True,
    engineio_logger=True,
    ping_timeout=100,
    ping_interval=40,
)

EMPTY = 0  # Empty Koordinate point
WHITE = 1  # 👇🏻
BLACK = 2  # 👆🏿
TOWN_WHITE = 3  # 🏠
TOWN_BLACK = 4  # 🏡
MAX_SOLDIERS = 15
MAX_PLAYERS_IN_ROOM = 2
BOARD_SIZE = 10  # 10x10
FIELD_SIZE = BOARD_SIZE + 1  # 11x11 mit Labels

rooms: Dict[str, Dict] = {}

x_legende: List[int] = list(range(BOARD_SIZE))
y_legende: List[chr] = list(map(chr, range(ord("a"), ord("l"))))


class Spieler(IntEnum):
    WHITE = 1
    BLACK = 2


class GameState(IntEnum):
    PLACE_SOLDATEN = 0
    MOVE_SOLDATEN = 1


Field = List[List[int]]
Koordiante = Tuple[int, int]


def place_town(spieler: Spieler, coordante: Koordiante, room: str) -> Field:
    x, y = coordante
    field: Field = rooms[room].get("field")
    field[x][y] = TOWN_WHITE if spieler == Spieler.WHITE else TOWN_BLACK
    return field


def soldiers_count(player: Spieler, field: Field) -> int:
    return sum(row.count(WHITE if player == Spieler.WHITE else BLACK) for row in field)


def place_soldaten(player: Spieler, coordante: Koordiante, room: str, sid: str):
    field: Field = rooms[room].get("field")
    x, y = coordante

    black_sid: str = [p for p in rooms[room].get("players") if p is not sid][0]

    if field[x][y] != EMPTY:
        emit("info", {"message": "Koordinate is already used"}, to=sid)
        return field

    if white_placed_all(field) and black_placed_all(field):
        emit(
            "info",
            {"message": "Start game", "gameState": GameState.MOVE_SOLDATEN},
            to=room,
            broadcast=True,
        )
        return field

    match player:
        case Spieler.WHITE:
            if white_placed_all(field):
                emit("info", {"message": "Wait for black"}, to=sid)
                return field

            # place soldaten
            field[x][y] = WHITE
            soldiers_count_white: int = soldiers_count(player, field)

            if soldiers_count_white <= MAX_SOLDIERS:
                if soldiers_count_white == MAX_SOLDIERS:
                    emit("info", {"message": "Now place Town"}, to=sid)
                    return field

                emit(
                    "info",
                    {"message": f"Soldaten left {MAX_SOLDIERS - soldiers_count_white}"},
                    to=sid,
                )
                return field
            else:
                field: Field = place_town(player, (x, y), room)
                emit("info", {"message": "Wait for black"}, to=sid)
                emit("info", {"message": "Start placing soldiers"}, to=black_sid)
                return field

        case Spieler.BLACK:
            if not white_placed_all(field):
                emit("info", {"message": "Wait for white"}, to=sid)
                return field

            field[x][y] = BLACK
            soldiers_count_black: int = soldiers_count(player, field)

            if soldiers_count_black <= MAX_SOLDIERS:
                if soldiers_count_black == MAX_SOLDIERS:
                    emit("info", {"message": "Now place Town"}, to=sid)
                    return field

                emit(
                    "info",
                    {"message": f"Soldaten left {MAX_SOLDIERS - soldiers_count_black}"},
                    to=sid,
                )
                return field
            else:
                field: Field = place_town(player, (x, y), room)
                emit("info", {"message": "Start game"}, to=room, broadcast=True)
                return field
        case _:
            emit("info", {"message": "Error"}, to=sid, broadcast=True)


def move_soldat(
    start: Koordiante, ziel: Koordiante, spieler: Spieler, room: str
) -> Field:
    oldX, oldY = start
    newX, newY = ziel
    field: Field = rooms[room].get("field")
    soldat = WHITE if spieler == Spieler.WHITE else BLACK

    field[newX][newY] = soldat
    field[oldX][oldY] = EMPTY

    return field


def room_is_full(players: Dict[str, int]) -> bool:
    return len(players) >= MAX_PLAYERS_IN_ROOM


def white_placed_all(field: Field):
    soliders_count: bool = sum(row.count(WHITE) for row in field) == MAX_SOLDIERS
    town_count: bool = sum(row.count(TOWN_WHITE) for row in field) == 1
    return soliders_count and town_count


def black_placed_all(field: Field) -> bool:
    soliders_count: bool = sum(row.count(BLACK) for row in field) == MAX_SOLDIERS
    town_count: bool = sum(row.count(TOWN_BLACK) for row in field) == 1
    return soliders_count and town_count


def placement_complete(room: str) -> bool:
    field: Field = rooms[room].get("field")
    white_done = white_placed_all(field)
    black_done = black_placed_all(field)
    return white_done and black_done


def can_capture_side(
    koordiante: Koordiante, spieler: Spieler, field: Field
) -> Tuple[bool, bool]:
    x, y = koordiante

    left_ok = y - 1 >= 0
    right_ok = y + 1 < 10

    can_left = False
    can_right = False

    if left_ok:
        left_piece = field[x][y - 1]
        is_other = (
            False if left_piece == (WHITE if spieler == WHITE else BLACK) else True
        )
        can_left = (
            True if left_piece is not (TOWN_BLACK or TOWN_WHITE) and is_other else False
        )

    if right_ok:
        right_piece = field[x][y + 1]
        is_other = (
            False if right_piece == (WHITE if spieler == WHITE else BLACK) else True
        )
        can_right = True if right_piece is not (TOWN_BLACK or TOWN_WHITE) else False
    return can_left, can_right


def create_player(sid: str, room: str) -> None:
    players: Dict[str, int] = rooms[room].get("players")

    data = {"room": rooms[room], "player": sid, "soldiers_left": MAX_SOLDIERS}

    if room_is_full(players):
        emit("error", {"message": "Room is full!"}, to=sid)
        return

    if len(players) == 0:
        color = random.choice([WHITE, BLACK])
        players |= {sid: color}
        emit("joined_room", data, to=sid)
        emit("info", {"message": f"Soldaten left {MAX_SOLDIERS}"}, to=sid)
    elif len(players) == 1:
        first_sid_color = list(rooms[room].get("players").values())[0]
        players |= {sid: BLACK if first_sid_color == WHITE else WHITE}
        emit("joined_room", data, to=sid)
        emit("info", {"message": f"Soldaten left {MAX_SOLDIERS}"}, to=sid)


@app.route("/")
def hello_world():
    return render_template(
        "view.html", data=np.zeros((FIELD_SIZE, FIELD_SIZE), dtype=np.uint8)
    )


@socketio.on("join_room")
def join(data):
    room: str = data.get("room")
    sid: str = request.sid  # Session ID

    if not room:
        emit("error", {"message": "Room name required"}, to=sid)
        return

    if room not in rooms:
        rooms[room] = {
            "field": np.zeros((FIELD_SIZE, FIELD_SIZE), dtype=np.uint8).tolist(),
            "players": {},  # {sid: color}
        }

    create_player(sid=sid, room=room)
    join_room(room)


@socketio.on("place_soldaten")
def handle_place_soldaten(x: int, y: int, room: str):
    sid: str = request.sid
    players: Dict[str, int] = rooms[room].get("players")
    player: str = rooms[room].get("players")[sid]

    if placement_complete(room):
        emit(
            "info",
            {"message": "Start game", "gameState": GameState.MOVE_SOLDATEN},
            to=room,
            broadcast=True,
        )
        return

    if not room_is_full(players):
        emit("info", {"message": "Wait for second player "}, to=sid)
        return

    field: Field = place_soldaten(player, coordante=(x, y), room=room, sid=sid)

    emit("update_field", field, room=room)


@socketio.on("move_soldaten")
def handle_move_soldaten(
    startX: int, startY: int, zielX: int, zielY: int, spieler: Spieler, room: str
):
    field: Field = move_soldat(
        start=(startX, startY), ziel=(zielX, zielY), spieler=spieler, room=room
    )
    emit("update_field", field, to=request.sid, broadcast=True)


@socketio.on("disconnect")
def handle_disconnect():
    sid: str = request.sid
    emit("info", {"message": "Disconnect"}, to=sid)
    print("Client disconnected")


def get_soldat_and_direction(player: Spieler):
    soldat = WHITE if player == Spieler.WHITE else BLACK
    direction = 1 if player == Spieler.WHITE else -1
    return soldat, direction


def is_coordinate_valide(start: Koordiante, end: Koordiante) -> bool:
    oldX, oldY = start
    newX, newY = end
    start_is_valide = (0 <= oldX < FIELD_SIZE) and (0 <= oldY < FIELD_SIZE)
    end_is_valide = (0 <= newX < FIELD_SIZE) and (0 <= newY < FIELD_SIZE)
    return start_is_valide and end_is_valide


def move_forward(start: Koordiante, end: Koordiante, spieler: Spieler, field: Field):
    if not is_coordinate_valide(start, end):
        print("coordiantye sind falsch")
        return None

    soldat, direction = get_soldat_and_direction(spieler)

    oldX, oldY = start
    newX, newY = end

    if field[oldX][oldY] != soldat:
        print("Nicht der eigenee Soldat")
        return None

    if (newX - oldX) != direction or (newY - oldY) > 1:
        print("Invalid move direction")
        return None

    if field[newX][newY] != EMPTY:
        print("Target coord is not empty")
        return None

    field[oldX][oldY] = EMPTY
    field[newX][newY] = soldat

    return field


def move_diagonally(start: Koordiante, end: Koordiante, spieler: Spieler, field: Field):
    if not is_coordinate_valide(start, end):
        print("invalid koordinatae")
        return None

    oldX, oldY = start
    newX, newY = end
    soldat, direction = get_soldat_and_direction(spieler)
    opposite_soldat = BLACK if soldat == WHITE else WHITE

    if field[oldX][oldY] != soldat:
        print("nicht dein soldat")
        return None

    dx = newX - oldX

    if not (dx == direction):
        print("invalider direction")
        return None

    if field[newX][newY] != EMPTY:
        print("zielkoordinate ist nicht leer")
        return None

    if field[newX][newY] == opposite_soldat:
        print(f"captures soldat {'BLACK' if opposite_soldat == BLACK else 'WHITE'}")

    field[oldX][oldY] = EMPTY
    field[newX][newY] = soldat

    return field


def t() -> None:
    # from collections import Counter
    # c = Counter(chain(*field))[Spieler.WHITE]
    # print(c)
    room = "test"

    rooms[room] = {
        "field": np.zeros((FIELD_SIZE, FIELD_SIZE), dtype=np.uint8).tolist(),
        "players": {"white": Spieler.WHITE, "black": Spieler.BLACK},  # {sid: color}
    }

    field = rooms["test"].get("field")

    # x, y, placed_soldiers = 0, 0, 0
    # while placed_soldiers < MAX_SOLDIERS:
    #     field[x][y] = WHITE
    #     y += 1
    #     if y >= 10:
    #         y = 0
    #         x += 1
    #     placed_soldiers += 1

    # field[x][y] = TOWN_WHITE

    # x, y, placed_soldiers = 2, 2, 0
    # while placed_soldiers < MAX_SOLDIERS:
    #     field[x][y] = BLACK
    #     y += 1
    #     if y >= 10:
    #         y = 0
    #         x += 1
    #     placed_soldiers += 1

    # field[x][y] = TOWN_BLACK

    field[0][0] = WHITE
    field[0][1] = WHITE
    field[1][1] = BLACK

    pprint(field)
    print("")
    start = (0, 0)
    end = (1, 1)

    # move_soldat(start, end, Spieler.WHITE, room)
    # move_diagonally(start, end, Spieler.WHITE, field)
    # move_diagonally((2, 9), (1, 10), Spieler.BLACK, field)
    # move_forward(whiteSoldier, newWhiteSoldier, Spieler.WHITE, field)

    pprint(field)


if __name__ == "__main__":
    t()
    # socketio.run(app, host="127.0.0.1", port=8000, debug=True)
