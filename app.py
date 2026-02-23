import pprint
import random
from enum import Enum
from typing import List, Tuple

import numpy as np
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)

app.config["SECRET_KEY"] = "secret!"
socketio = SocketIO(app, cors_allowed_origins="*", sync_mode="threading")

x_legende: List[int] = list(range(10))
y_legende: List[chr] = list(map(chr, range(ord("a"), ord("l"))))

WHITE = 1  # 👇🏻
BLACK = 2  # 👆🏿
TOWN_WHITE = 3  # 🏠
TOWN_BLACK = 4  # 🏡
MAX_SOLDIERS = 15
MAX_PLAYERS_IN_ROOM = 2

rooms: dict[str, dict] = {}


class Spieler(Enum):
    WHITE = 1
    BLACK = 2


Field = List[List[int]]
Koordiante = Tuple[int, int]


def place_town(spieler: Spieler, coordante: Koordiante, room: str) -> Field:
    x, y = coordante
    field: Field = rooms[room].get("field")
    field[x][y] = TOWN_WHITE if spieler == WHITE else TOWN_BLACK
    return field


def place_soldaten(player: Spieler, coordante: Koordiante, room: str, sid: str):
    field: Field = rooms[room].get("field")

    white_placed_all_soliders: bool = (
        True if sum(row.count(WHITE) for row in field) == MAX_SOLDIERS else False
    )

    black_placed_all_soldirs: bool = (
        True if sum(row.count(BLACK) for row in field) == MAX_SOLDIERS else False
    )

    soldiers_count_black: int = sum(row.count(BLACK) for row in field)
    soldiers_count_white: int = sum(row.count(WHITE) for row in field)

    x, y = coordante

    # wenn white and black alle soldaten placed haben info message
    if white_placed_all_soliders and black_placed_all_soldirs:
        emit("info", {"message": "Max soldiers placed"}, room=room, broadcast=True)
        return field

    # wenn auf dem coord schon ein soldat geplaced ist dann info
    if field[x][y] != 0:
        emit("info", {"message": "Soldat is already placed"}, to=sid)
        return field

    if player == BLACK and not white_placed_all_soliders:
        emit("info", {"message": "Wait until White placed all 15 soldiers!"}, to=sid)
        return field
    elif player == BLACK and white_placed_all_soliders:
        emit(
            "info",
            {
                "message": f"You have {MAX_SOLDIERS - soldiers_count_black} Soldaten left to place"
            },
            to=sid,
        )
        field[x][y] = BLACK
        return field
    elif player == WHITE and white_placed_all_soliders:
        return field
    elif player == WHITE:
        emit(
            "info",
            {
                "message": f"You have {MAX_SOLDIERS - soldiers_count_white} Soldaten left to place"
            },
            to=sid,
        )
        field[x][y] = WHITE
        return field


def room_is_full(players: dict[str, int]) -> bool:
    return True if len(players) >= MAX_PLAYERS_IN_ROOM else False


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
    elif len(players) == 1:
        first_sid_color = list(rooms[room].get("players").values())[0]
        players |= {sid: BLACK if first_sid_color == WHITE else WHITE}
        emit("joined_room", data, to=sid)


@app.route("/")
def hello_world():
    return render_template("view.html", data=np.zeros((11, 11), dtype=object))


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
    pprint.pprint(rooms[room]["field"])
    emit("update_field", field, room=room)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=8000, debug=True)
