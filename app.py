import random
from enum import Enum
from typing import List, Tuple, TypedDict

import numpy as np
from flask import Flask, render_template, request
from flask_socketio import SocketIO, emit, join_room

app = Flask(__name__)

app.config["SECRET_KEY"] = "secret!"
socketio = SocketIO(app, cors_allowed_origins="*", sync_mode="threading")

x_legende: List[int] = list(range(10))
y_legende: List[chr] = list(map(chr, range(ord("a"), ord("l"))))

"""
Spielfeld

0 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
1 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
2 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
3 	0 	0 	0 	0	0 	0 	0 	0 	0 	0
4 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
5 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
6 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
7 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
8 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
9 	0 	0 	0 	0 	0 	0 	0 	0 	0 	0
a 	b 	c 	d 	e 	f 	g 	h 	i 	j 	k
"""

soldaten_1 = ["👇🏻"] * 1
soldaten_2 = ["👆🏿"] * 1
town_1 = "🏠"
town_2 = "🏡"

rooms: dict[str, dict] = {}


class Spieler(Enum):
    WHITE = 0
    BLACK = 1


Field = List[List[np.array]]
Koordiante = Tuple[int, int]
Koordianten = List[Koordiante]
TownKordinaten = Tuple[int, int]

fields: Field = np.zeros((11, 11)).astype(np.int8).tolist()


class Soldaten(TypedDict):
    spieler: Spieler
    coordinate: Koordianten
    town: TownKordinaten


def place_town(spieler: Spieler, coordinated: TownKordinaten, field: Field) -> Field:
    if coordinated is None:
        return
    x, y = coordinated
    field[x][y] = town_1 if spieler == Spieler.WHITE else town_2
    return field


def place_soldaten(spieler: Spieler, coordante: Koordiante, room: str) -> Field:
    x, y = coordante
    field = rooms[room]["field"]
    field[x][y] = soldaten_1[0] if spieler == Spieler.WHITE else soldaten_2[0]
    return field


def check_town_count(fields: Field) -> bool:
    t1, t2 = np.sum(fields == town_1), np.sum(fields == town_2)
    return True if t1 == 1 and t2 == 1 else False


@app.route("/")
def hello_world():
    return render_template("view.html", data=fields)


@socketio.on("join_room")
def join(data):
    room = data["room"]
    sid = request.sid  # Session ID

    # Create room if it doesn't exist
    if room not in rooms:
        rooms[room] = {
            "field": np.zeros((11, 11)).astype(np.uint8).tolist(),
            "players": {},
        }

    players: dict = rooms[room].get("players")

    if len(players) >= 2:
        emit("error", {"message": "Room full!"})
        return

    join_room(room)

    # if first player in a room set color
    if len(players) == 0:
        color = random.choice([0, 1])
        players.update({sid: color})
        emit(
            "joined_room", {"room": rooms[room], "player": sid}, to=sid, broadcast=True
        )
    elif len(players) == 1:
        first_sid_color = list(players.values())[0]
        players.update({sid: 0 if first_sid_color == 1 else 1})
        emit(
            "joined_room", {"room": rooms[room], "player": sid}, to=sid, broadcast=True
        )


@socketio.on("place_soldaten")
def handle_place_soldaten(x, y, player, room):
    print(x, y, player, room)
    field = place_soldaten(spieler=Spieler(player), coordante=(x, y), room=room)
    emit("update_field", field, room=room)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=8000, debug=True)
