import random
from enum import IntEnum
from typing import List, Tuple

import numpy as np
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)

app.config["SECRET_KEY"] = "secret!"
socketio = SocketIO(app, cors_allowed_origins="*", sync_mode="threading")

x_legende: List[int] = list(range(10))
y_legende: List[chr] = list(map(chr, range(ord("a"), ord("l"))))

EMPTY = 0  # Empty Koordinate point
WHITE = 1  # 👇🏻
BLACK = 2  # 👆🏿
TOWN_WHITE = 3  # 🏠
TOWN_BLACK = 4  # 🏡
MAX_SOLDIERS = 15
MAX_PLAYERS_IN_ROOM = 2

rooms: dict[str, dict] = {}


class Spieler(IntEnum):
    WHITE = 1
    BLACK = 2


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

    if field[x][y] != EMPTY:
        emit("info", {"message": "Koordinate is already used"}, to=sid)
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
                return field

        case Spieler.BLACK:
            if black_placed_all(field):
                emit("info", {"message": "Start game"})
                return field

            if not white_placed_all(field):
                emit("info", {"message": "Wait for white"})
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
                emit("info", {"message": "Game start"}, to=sid, broadcast=True)
                return field
        case _:
            emit("info", {"message": "Error"}, to=sid, broadcast=True)


def room_is_full(players: dict[str, int]) -> bool:
    return len(players) >= MAX_PLAYERS_IN_ROOM


def white_placed_all(field: Field):
    soliders_count: bool = sum(row.count(WHITE) for row in field) == MAX_SOLDIERS
    town_count: bool = sum(row.count(TOWN_WHITE) for row in field) == 1
    return soliders_count and town_count


def black_placed_all(field: Field) -> bool:
    soliders_count: bool = sum(row.count(BLACK) for row in field) == MAX_SOLDIERS
    town_count: bool = sum(row.count(TOWN_BLACK) for row in field) == 1
    return soliders_count and town_count


def create_player(sid: str, room: str) -> None:
    players: dict[str, int] = rooms[room].get("players")

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
    return render_template("view.html", data=np.zeros((11, 11), dtype=np.uint8))


@socketio.on("join_room")
def join(data):
    room: str = data.get("room")
    sid: str = request.sid  # Session ID

    if not room:
        emit("error", {"message": "Room name required"}, to=sid)
        return

    # Create room if it doesn't exist
    if room not in rooms:
        rooms[room] = {
            "field": np.zeros((11, 11), dtype=object).tolist(),
            "players": {},  # {sid: color}
        }

    create_player(sid=sid, room=room)
    join_room(room)


@socketio.on("place_soldaten")
def handle_place_soldaten(x: int, y: int, room: str):
    sid: str = request.sid
    player: int = rooms[room].get("players")[sid]
    field: Field = place_soldaten(player, coordante=(x, y), room=room, sid=sid)
    emit("update_field", field, room=room)


@socketio.on("place_town")
def handle_place_town(x, y, player, room):
    field: Field = place_town(spieler=player, coordante=(x, y), room=room)
    emit("update_field", field, room=room)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=8000, debug=True)
