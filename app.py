from typing import List
from flask import Flask, jsonify, render_template, request
import numpy as np

app = Flask(__name__)

x_legende = list(range(10))
y_legende = list(map(chr, range(ord("a"), ord("k"))))

def initialize_field():
    fields: List[np.array] = np.random.randn(11, 11).astype(np.int8).tolist()
    for field in range(len(fields) -1):
        fields[field][0] = x_legende[field]
    fields[-1] = y_legende
    return fields
    

@app.route("/")
def hello_world():
    fields = initialize_field()
    return render_template("view.html", data=fields)


@app.post("/start")
def start():
    positions = request.json
    return jsonify(positions)
