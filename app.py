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


def set_soldaten(soldaten: Soldaten, field: Field):
    spieler = soldaten["spieler"]
    coordinated = soldaten["coordinate"]
    town_cord = soldaten.get("town")

    place_soldaten(spieler, coordinated, field=field)
    place_town(spieler, town_cord, field)


def place_town(spieler: Spieler, coordinated: TownKordinaten, field: Field) -> Field:
    if coordinated is None:
        return
    x, y = coordinated
    field[x][y] = town_1 if spieler == Spieler.WHITE else town_2
    return field


def place_soldaten(spieler: Spieler, coordante: Koordiante, field: Field) -> Field:
    for x, y in coordante:
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
            "players": [],
            "colors": {},
        }

    players = rooms[room]["players"]

    # Check if room has space
    if len(players) >= 2:
        emit("error", {"message": "Room full!"})
        return

    # add player to room
    join_room(room)
    players.append(sid)

    # if first player in a room set color
    if len(players) == 1:
        color = random.choice([0, 1])
        rooms[room]["colors"][sid] = color

        emit("joined_room", {"room": rooms[room], "player": sid})
        print(rooms)
    elif len(players) == 2:
        first_sid = players[0]
        first_color = rooms[room]["colors"][first_sid]
        rooms[room]["colors"][sid] = 1 - first_color

        emit("joined_room", {"room": rooms[room], "player": sid}, to=sid)
        print(rooms)


@socketio.on("place_soldaten")
def handle_place_soldaten(data):
    spieler = Spieler(data["spieler"])
    koordinaten = [tuple(coord) for coord in data["coordinate"]]
    town = tuple(data["town"])
    soldaten: Soldaten = {"spieler": spieler, "coordinate": koordinaten, "town": town}

    set_soldaten(soldaten, fields)

    emit("update_field", fields, broadcast=True)


if __name__ == "__main__":
    socketio.run(app, host="127.0.0.1", port=8000, debug=True)
