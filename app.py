from enum import Enum
from typing import List, Tuple, TypedDict

import numpy as np
from flask import Flask, jsonify, render_template, request

app = Flask(__name__)

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


class Spieler(Enum):
    WHITE = 0
    BLACK = 1


type Field = List[np.array]
type Koordiante = Tuple[int, int]
type Koordianten = List[Koordiante]
type TownKordinaten = Tuple[int, int]


class Soldaten(TypedDict):
    spieler: Spieler
    coordinate: Koordianten
    town: TownKordinaten


position: Soldaten = {
    "spieler": Spieler.WHITE,
    "coordinate": [(3, 4), (4, 3), (4, 4), (4, 5), (4, 6)],
    "town": (3, 3),
}

position2: Soldaten = {
    "spieler": Spieler.BLACK,
    "coordinate": [(5, 4), (5, 3), (5, 4), (5, 5), (5, 6)],
    "town": (6, 6),
}


def set_soldaten(soldaten: Soldaten, field: Field):
    spieler = soldaten["spieler"]
    coordinated = soldaten["coordinate"]
    town_cord = soldaten["town"]

    place_soldaten(spieler, coordinated, field=field)
    place_town(spieler, town_cord, field)


def place_town(spieler: Spieler, coordinated: TownKordinaten, field: Field) -> Field:
    field[coordinated[0]][coordinated[1]] = (
        town_1 if spieler == Spieler.WHITE else town_2
    )
    return field


def place_soldaten(spieler: Spieler, coordante: Koordiante, field: Field) -> Field:
    for x, y in coordante:
        field[x][y] = soldaten_1[0] if spieler == Spieler.WHITE else soldaten_2[0]
    return field


def initialize_field() -> Field:
    fields: Field = np.zeros((11, 11)).astype(np.int8).tolist()

    for field in range(len(fields) - 1):
        fields[field][0] = x_legende[field]

    fields[-1] = y_legende

    set_soldaten(soldaten=position, field=fields)
    set_soldaten(soldaten=position2, field=fields)

    return fields


@app.route("/")
def hello_world():
    fields = initialize_field()
    return render_template("view.html", data=fields)


@app.post("/start")
def start():
    positions = request.json
    return jsonify(positions)
