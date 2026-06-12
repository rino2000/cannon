from typing import Tuple

import pytest
from flask_socketio import SocketIOTestClient

from app import (
    BLACK,
    EMPTY,
    TOWN_BLACK,
    TOWN_WHITE,
    WHITE,
    GameState,
    Room,
    Spieler,
    app,
    rooms,
    socketio,
)

type sid = str
type clients = Tuple[Tuple[SocketIOTestClient, sid], Tuple[SocketIOTestClient, sid]]
type WhiteBlackClients = Tuple[SocketIOTestClient, sid, SocketIOTestClient, sid]


@pytest.fixture
def two_clients() -> clients:
    client1 = socketio.test_client(app)
    client2 = socketio.test_client(app)

    client1.emit("join_room", "a")
    events1 = client1.get_received()
    client2.emit("join_room", "a")
    events2 = client2.get_received()

    color1 = events1[0]["args"][0]["player"]
    color2 = events2[0]["args"][0]["player"]

    room = rooms["a"]
    sid1 = next(sid for sid, color in room.players.items() if color == color1)
    sid2 = next(sid for sid, color in room.players.items() if color == color2)

    return (client1, sid1), (client2, sid2)


@pytest.fixture(autouse=True)
def clear_rooms() -> None:
    rooms.clear()


def get_white_black_clients(two_clients: clients, room: Room) -> WhiteBlackClients:
    (client1, sid1), (client2, sid2) = two_clients

    if room.players[sid1] == Spieler.WHITE:
        return client1, sid1, client2, sid2
    else:
        return client2, sid2, client1, sid1


class TestRoom:
    _room_name = "a"

    def test_two_clients_join_same_room(self, two_clients: clients) -> None:
        (_, sid1), (_, sid2) = two_clients
        assert self._room_name in rooms
        room: Room = rooms[self._room_name]

        assert len(room.players) == 2
        assert room.gameState == GameState.PLACE_SOLDATEN
        assert sid1 in room.players
        assert sid2 in room.players

    def test_white_place_first(self, two_clients: clients):
        room: Room = rooms[self._room_name]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.emit("place_soldaten", 1, 1, self._room_name)

        recv = white_client.get_received()
        update_events = [ev for ev in recv if ev["name"] == "update_field"]
        assert len(update_events) >= 1
        assert room.board[1][1] == Spieler.WHITE

        # balck trys place soldier -> error
        black_client.emit("place_soldaten", 6, 0, self._room_name)
        black_recv = black_client.get_received()
        info_events = [ev for ev in black_recv if ev["name"] == "info"]
        assert any(
            "white muss zuerst alle objekte placen" in str(ev) for ev in info_events
        )
        assert room.board[6][0] == 0

    def test_white_place_all(self, two_clients: clients) -> None:
        room: Room = rooms[self._room_name]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)

        for y in range(1, 10, 2):
            for x in range(1, 4):
                white_client.emit("place_soldaten", x, y, self._room_name)
                white_client.get_received()
                assert room.board[x][y] == WHITE

        white_client.emit("place_soldaten", 0, 4, self._room_name)
        white_client.get_received()
        assert room.board[0][4] == TOWN_WHITE

        # now black can start placing soldiers
        black_msgs = black_client.get_received()
        assert any(
            "Now place soldiers" in str(msg)
            for msg in black_msgs
            if msg["name"] == "info"
        )

    def test_black_place_all(self, two_clients: clients) -> None:
        self.test_white_place_all(two_clients)

        room: Room = rooms[self._room_name]
        _, _, black_client, _ = get_white_black_clients(two_clients, room)

        for y in range(0, 10, 2):
            for x in range(6, 9):
                black_client.emit("place_soldaten", x, y, self._room_name)
                black_client.get_received()
                assert room.board[x][y] == BLACK

        black_client.emit("place_soldaten", 9, 7, self._room_name)
        black_client.get_received()
        assert room.board[9][7] == TOWN_BLACK

    def test_gamestate(self, two_clients: clients) -> None:
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        assert room.gameState == GameState.MOVE_SOLDATEN

    def test_all_objects_placed(self, two_clients: clients) -> None:
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        assert room._all_objects_placed()

    def test_turn_white(self, two_clients: clients) -> None:
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        assert room._turn == Spieler.WHITE

    def test_black_move_first_not_allowed(self, two_clients: clients) -> None:
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        _, _, black_client, _ = get_white_black_clients(two_clients, room)

        startX, startY, endX, endY = 6, 0, 5, 0
        black_client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = black_client.get_received()

        assert recv[0]["args"][0]["message"] == "Nicht dein Turn"
        assert room.board[startX][startY] == BLACK
        assert room.board[endX][endY] == EMPTY

    def test_white_move_tower_not_allowed(self, two_clients: clients) -> None:
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        white_client, _, _, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()

        startX, startY, endX, endY = 0, 4, 0, 5
        white_client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = white_client.get_received()

        assert recv[0]["args"][0]["message"] == "Du darfst die Stadt nicht bewegen"
        assert room.board[startX][startY] == TOWN_WHITE
        assert room.board[endX][endY] == EMPTY

    def test_first_white_move(self, two_clients: clients) -> None:
        self.test_all_objects_placed(two_clients)
        room: Room = rooms[self._room_name]
        white_client, _, _, _ = get_white_black_clients(two_clients, room)

        startX, startY, endX, endY = 3, 1, 4, 1
        white_client.get_received()
        white_client.emit("move_object", startX, startY, endX, endY, room.name)

        assert room.board[startX][startY] == EMPTY
        assert room.board[endX][endY] == WHITE

    def test_black_move_town_not_allowed(self, two_clients: clients) -> None:
        self.test_first_white_move(two_clients)
        room: Room = rooms[self._room_name]
        _, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()  # clear all messages in list

        startX, startY, endX, endY = 9, 7, 9, 8

        black_client.emit("move_object", startX, startY, endX, endY, room.name)
        recv = black_client.get_received()

        assert recv[0]["args"][0]["message"] == "Du darfst die Stadt nicht bewegen"
        assert room.board[startX][startY] == TOWN_BLACK
        assert room.board[endX][endY] == EMPTY

    def test_first_move_black(self, two_clients: clients) -> None:
        self.test_first_white_move(two_clients)
        room: Room = rooms[self._room_name]
        _, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()  # clear all messages in list

        startX, startY, endX, endY = 6, 0, 5, 0

        black_client.emit("move_object", startX, startY, endX, endY, room.name)

        assert room.board[startX][startY] == EMPTY
        assert room.board[endX][endY] == BLACK

    def test_capture_soldier_black(self, two_clients: clients) -> None:
        self.test_first_move_black(two_clients)
        room: Room = rooms[self._room_name]
        white_client, _, _, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()  # clear all messages in list

        startX, startY, endX, endY = 4, 1, 5, 0

        white_client.emit("move_object", startX, startY, endX, endY, room.name)

        assert room.white_captured == 1
        assert room.black_captured == 0
        assert room.board[startX][startY] == EMPTY
        assert room.board[endX][endY] == WHITE
        assert room._turn == Spieler.BLACK

    def test_capture_soldier_white(self, two_clients: clients) -> None:
        self.test_capture_soldier_black(two_clients)
        room: Room = rooms[self._room_name]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()  # clear all messages in list
        white_client.get_received()  # clear all messages in list

        startX, startY, endX, endY = 7, 0, 6, 0

        black_client.emit("move_object", startX, startY, endX, endY, room.name)
        white_client.emit("move_object", 2, 1, 3, 1, room.name)
        black_client.emit("move_object", endX, endY, endX - 1, endY, room.name)

        assert room.white_captured == 1
        assert room.black_captured == 1
        assert room.board[startX][startY] == EMPTY
        assert room.board[endX - 1][endY] == BLACK
        assert room._turn == Spieler.WHITE

    # def test_first_cannon_move_white(self, two_clients: clients) -> None:
    #     self.test_first_move_black(two_clients)
    #     room: Room = rooms[self._room_name]
    #     white_client, _, _, _ = get_white_black_clients(two_clients, room)
    #     white_client.get_received()  # clear all messages in list

    #     startX, startY, endX, endY = 1, 3, 4, 3

    #     white_client.emit("move_object", startX, startY, endX, endY, room.name)

    #     recv = white_client.get_received()
    #     pprint(recv)
    #     pprint(room.board)
