import pytest
from flask_socketio import SocketIOTestClient

from app import (
    EMPTY,
    GameState,
    Player,
    Room,
    Soldier,
    Town,
    app,
    rooms,
    socketio,
)

type Sid = str
type Clients = tuple[tuple[SocketIOTestClient, Sid], tuple[SocketIOTestClient, Sid]]
type WhiteBlackClients = tuple[SocketIOTestClient, Sid, SocketIOTestClient, Sid]


@pytest.fixture
def two_clients() -> Clients:
    client1 = socketio.test_client(app)
    client2 = socketio.test_client(app)

    client1.emit("join_room", "a")
    events1 = client1.get_received()
    client2.emit("join_room", "a")
    events2 = client2.get_received()

    color1 = events1[0]["args"][0]["player"]
    color2 = events2[0]["args"][0]["player"]

    room = rooms["a"]
    sid1 = next(Sid for Sid, color in room.players.items() if color == color1)
    sid2 = next(Sid for Sid, color in room.players.items() if color == color2)

    return (client1, sid1), (client2, sid2)


@pytest.fixture(autouse=True)
def clear_rooms():
    rooms.clear()


def get_white_black_clients(two_clients: Clients, room: Room) -> WhiteBlackClients:
    (client1, sid1), (client2, sid2) = two_clients

    if room.players[sid1] == Player.WHITE:
        return client1, sid1, client2, sid2
    else:
        return client2, sid2, client1, sid1


class TestRoom:
    _room_name = "a"

    def test_two_clients_join_same_room(self, two_clients: Clients):
        (_, sid1), (_, sid2) = two_clients
        assert self._room_name in rooms
        room: Room = rooms[self._room_name]

        assert room._turn == Player.WHITE
        assert len(room.players) == 2
        assert room.gameState == GameState.PLACE_SOLDATEN
        assert sid1 in room.players
        assert sid2 in room.players

    def test_white_place_first(self, two_clients: Clients):
        room: Room = rooms[self._room_name]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.emit("place_soldaten", 1, 1, self._room_name)

        recv = white_client.get_received()
        update_events = [ev for ev in recv if ev["name"] == "update_field"]
        assert len(update_events) >= 1
        assert room.board[1][1] == Soldier.WHITE

        # balck trys place soldier -> error
        black_client.emit("place_soldaten", 6, 0, self._room_name)
        black_recv = black_client.get_received()
        info_events = [ev for ev in black_recv if ev["name"] == "info"]
        assert any("white muss zuerst alles placen" in str(ev) for ev in info_events)
        assert room.board[6][0] == 0

    def test_white_place_all(self, two_clients: Clients):
        room: Room = rooms[self._room_name]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)

        for y in range(1, 10, 2):
            for x in range(1, 4):
                white_client.emit("place_soldaten", x, y, self._room_name)
                white_client.get_received()
                assert room.board[x][y] == Soldier.WHITE

        white_client.emit("place_soldaten", 0, 4, self._room_name)
        white_client.get_received()
        assert room.board[0][4] == Town.WHITE

        # now black can start placing soldiers
        black_msgs = black_client.get_received()
        assert any(
            "Now place soldiers" in str(msg)
            for msg in black_msgs
            if msg["name"] == "info"
        )

    def test_black_place_all(self, two_clients: Clients):
        self.test_white_place_all(two_clients)

        room: Room = rooms[self._room_name]
        _, _, black_client, _ = get_white_black_clients(two_clients, room)

        for y in range(0, 10, 2):
            for x in range(6, 9):
                black_client.emit("place_soldaten", x, y, self._room_name)
                black_client.get_received()
                assert room.board[x][y] == Soldier.BLACK

        black_client.emit("place_soldaten", 9, 7, self._room_name)
        black_client.get_received()
        assert room.board[9][7] == Town.BLACK

    def test_gamestate(self, two_clients: Clients):
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        assert room.gameState == GameState.MOVE_SOLDATEN

    def test_all_objects_placed(self, two_clients: Clients):
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        assert room._all_objects_placed()

    def test_first_turn_is_white(self, two_clients: Clients):
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        assert room._turn == Player.WHITE

    def test_black_move_first_not_allowed(self, two_clients: Clients):
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        _, _, black_client, _ = get_white_black_clients(two_clients, room)

        startX, startY, endX, endY = 6, 0, 5, 0
        black_client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = black_client.get_received()

        assert recv[0]["args"][0]["message"] == "Nicht dein Turn"
        assert room.board[startX][startY] == Soldier.BLACK
        assert room.board[endX][endY] == EMPTY

    def test_first_white_move(self, two_clients: Clients):
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        white_client, _, _, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()

        startX, startY, endX, endY = 3, 1, 4, 1
        white_client.emit("move_object", startX, startY, endX, endY, room.name)

        assert room.board[startX][startY] == EMPTY
        assert room.board[endX][endY] == Soldier.WHITE
        assert room._turn == Player.BLACK

    def test_first_move_black(self, two_clients: Clients):
        self.test_first_white_move(two_clients)
        room: Room = rooms[self._room_name]
        _, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()

        startX, startY, endX, endY = 6, 0, 5, 0

        black_client.emit("move_object", startX, startY, endX, endY, room.name)

        assert room.board[startX][startY] == EMPTY
        assert room.board[endX][endY] == Soldier.BLACK
        assert room._turn == Player.WHITE

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [
            (8, 3, 8, 4, Player.BLACK),
            (2, 5, 4, 4, Player.WHITE),
        ],
    )
    def test_cannon_move_not_allowed(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room._turn = player
        room.gameState = GameState.MOVE_SOLDATEN
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()

        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 1, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 1, 1, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 2, 0, 2, 0, 0, 0, 0, 0, 0],
            [0, 2, 2, 2, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 2, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()

        assert (
            recv[0]["args"][0]["message"]
            == f"Move (({startX}, {startY}), ({endX}, {endY})) nicht moglich zu moven"
        )
        assert (
            room.board[startX][startY] == Soldier.WHITE
            if player == Player.WHITE
            else Soldier.BLACK
        )
        assert room.board[endX][endY] == EMPTY
        assert room._turn == player

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [(0, 4, 0, 5, Player.WHITE), (9, 7, 9, 8, Player.BLACK)],
    )
    def test_move_tower_fail(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: str,
        two_clients: Clients,
    ):
        self.test_black_place_all(two_clients)
        room: Room = rooms[self._room_name]
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()

        assert recv[0]["args"][0]["message"] == "Städte nicht bewegen"
        assert (
            room.board[startX][startY] == Town.WHITE
            if player == Player.WHITE
            else Town.BLACK
        )
        assert room.board[endX][endY] == EMPTY
        assert room._turn == player

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [(-23, 100, 13, -13, Player.WHITE), (11, 23, 203, 20, Player.BLACK)],
    )
    def test_move_coord_invalide(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()
        white_client.get_received()

        client = white_client if player == Player.WHITE else black_client

        client.emit("move_object", startX, startY, endX, endY, room.name)
        recv = client.get_received()

        assert recv[0]["args"][0]["message"] == "Move Coord nicht valide"
        assert room._turn == player

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [(1, 3, 0, 4, Player.BLACK), (8, 7, 9, 7, Player.WHITE)],
    )
    def test_soldier_capture_town(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room._turn = player
        room.gameState = GameState.MOVE_SOLDATEN
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 2, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()
        white_client.get_received()

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()

        assert recv[0]["args"][0]["message"] == "Game Over"
        assert recv[0]["args"][0]["winner"] == f"Winner: {player.name}"
        assert room.gameState == GameState.GAME_OVER
        assert room.board[startX][startY] == EMPTY
        assert room.black_captured == 0
        assert room.white_captured == 0
        assert room._turn == player

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [(5, 7, 9, 7, Player.WHITE), (5, 5, 0, 5, Player.BLACK)],
    )
    def test_cannon_shoot_capture_town(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room._turn = player
        room.gameState = GameState.MOVE_SOLDATEN
        room.board = [
            [0, 0, 0, 0, 0, 3, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 1, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()

        assert recv[0]["args"][0]["message"] == "Game Over"
        assert room.gameState == GameState.GAME_OVER
        assert room.black_captured == 0
        assert room.white_captured == 0
        assert room._turn == player

    @pytest.mark.parametrize("player", [(Player.BLACK), (Player.WHITE)])
    def test_client_surrender(self, player: Player, two_clients: Clients):
        room: Room = rooms[self._room_name]
        room._turn = player

        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()
        white_client.get_received()

        client = white_client if player == Player.WHITE else black_client
        client.emit("surrender", room._turn, room.name)

        assert client.is_connected() == False
        assert room.gameState == GameState.GAME_OVER
        assert room._turn == player

    @pytest.mark.parametrize("player", [(Player.WHITE), (Player.BLACK)])
    def test_client_disconnect(self, player: Player, two_clients: Clients):
        room: Room = rooms[self._room_name]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()

        client = white_client if player == Player.WHITE else black_client
        client.emit("disconnect", room.name)
        opponent_client = black_client if player == Player.WHITE else white_client

        recv = opponent_client.get_received()

        assert recv[0]["args"][0]["message"] == "Opponent disconnected"
        assert black_client.is_connected() == False if player == Player.BLACK else True
        assert white_client.is_connected() == False if player == Player.WHITE else True
        assert len(room.players) == 1

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [(3, 1, 4, 2, Player.WHITE), (6, 5, 5, 6, Player.BLACK)],
    )
    def test_soldier_move_occupied_field(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 2, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()

        assert recv[0]["args"][0]["message"] == "Feld ist besetzt"
        assert (
            room.board[startX][startY] == Soldier.WHITE
            if player == Player.WHITE
            else Soldier.BLACK
        )
        assert (
            room.board[endX][endY] == Soldier.WHITE
            if player == Player.WHITE
            else Soldier.BLACK
        )
        assert room._turn == player
        assert room.black_captured == 0
        assert room.white_captured == 0

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [(4, 2, 9, 7, Player.WHITE), (5, 9, 0, 4, Player.BLACK)],
    )
    def test_cannon_shoot_center_axis(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room._turn = player
        room.gameState = GameState.MOVE_SOLDATEN
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 2, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 2, 0],
            [0, 0, 0, 1, 0, 0, 0, 0, 0, 2],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 2],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 2],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()

        assert recv[0]["args"][0]["message"] == "Game Over"
        assert room.board[startX][startY] == EMPTY
        assert (
            room.board[endX][endY] == Town.BLACK
            if player == Player.WHITE
            else Town.WHITE
        )
        assert room._turn == player
        assert room.black_captured == 0
        assert room.white_captured == 0

    def test_game_over_message_in_both_players(self, two_clients: Clients):
        self.test_first_white_move(two_clients)
        room: Room = rooms[self._room_name]
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 2, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 1, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        startX, startY, endX, endY = 1, 3, 0, 4
        black_client.emit("move_object", startX, startY, endX, endY, room.name)

        white_recv = white_client.get_received()
        black_recv = black_client.get_received()

        assert black_recv[0]["args"][0]["message"] == "Game Over"
        assert black_recv[0]["args"][0]["winner"] == f"Winner: {Player.BLACK.name}"

        assert white_recv[0]["args"][0]["message"] == "Game Over"
        assert white_recv[0]["args"][0]["winner"] == f"Winner: {Player.BLACK.name}"

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [
            (6, 4, 7, 3, Player.BLACK),
            (6, 4, 7, 4, Player.BLACK),
            (6, 4, 7, 5, Player.BLACK),
            (6, 4, 6, 3, Player.BLACK),
            (6, 4, 6, 5, Player.BLACK),
            (3, 4, 2, 3, Player.WHITE),
            (3, 4, 2, 5, Player.WHITE),
            (3, 4, 2, 4, Player.WHITE),
            (3, 4, 3, 3, Player.WHITE),
            (3, 4, 3, 5, Player.WHITE),
        ],
    )
    def test_soldier_moves_not_allowed(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 2, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()
        assert recv[0]["args"][0]["message"] == "Soldier cant move there"

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [
            (6, 5, 3, 5, Player.BLACK),
            (4, 5, 7, 5, Player.BLACK),
            (4, 3, 7, 6, Player.BLACK),
            (6, 5, 3, 2, Player.BLACK),
            (5, 3, 5, 6, Player.BLACK),
            (5, 5, 5, 2, Player.BLACK),
            (6, 5, 3, 5, Player.WHITE),
            (4, 5, 7, 5, Player.WHITE),
            (4, 3, 7, 6, Player.WHITE),
            (6, 5, 3, 2, Player.WHITE),
            (5, 3, 5, 6, Player.WHITE),
            (5, 5, 5, 2, Player.WHITE),
        ],
    )
    def test_all_cannon_moves(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board[startX][startY] = (
            Soldier.BLACK if player == Player.BLACK else Soldier.WHITE
        )
        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()
        assert recv[0]["args"][0]["turn"] == f"Turn: {player.opponent.name}"
        assert room._turn == player.opponent

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [
            (4, 5, 6, 5, Player.BLACK),
            (4, 5, 6, 3, Player.BLACK),
            (4, 5, 6, 7, Player.BLACK),
            (6, 2, 4, 2, Player.WHITE),
            (6, 2, 4, 0, Player.WHITE),
            (6, 2, 4, 4, Player.WHITE),
        ],
    )
    def test_all_soldier_thread_moves(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 0, 0, 0, 0, 0, 0, 0],
            [0, 2, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()
        assert recv[0]["args"][0]["message"] == f"thread move ({endX}, {endY}) moved"
        assert room._turn == player.opponent

    @pytest.mark.parametrize(
        "startX,startY,endX,endY",
        [(8, 4, 3, 4), (8, 4, 4, 8), (8, 4, 3, 9), (8, 6, 3, 1), (8, 6, 4, 2)],
    )
    def test_cannons_shoot_black(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = Player.BLACK
        _, _, black_client, _ = get_white_black_clients(two_clients, room)
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 1, 0, 0, 1, 0, 0, 0, 0, 1],
            [0, 0, 1, 0, 0, 0, 0, 0, 1, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 2, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 2, 2, 0, 0, 0, 0],
            [0, 0, 0, 0, 2, 0, 2, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        black_client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = black_client.get_received()
        assert recv[1]["args"][0]["message"] == f"cannon shoot capture ({endX}, {endY})"
        assert room._turn == Player.WHITE
        assert room.black_captured == 1
        assert room.white_captured == 0

    @pytest.mark.parametrize(
        "startX,startY,endX,endY",
        [(1, 4, 6, 4), (1, 4, 5, 8), (1, 4, 6, 9), (1, 6, 5, 2), (1, 6, 6, 1)],
    )
    def test_cannon_shoot_white(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = Player.WHITE
        white_client, _, _, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 1, 1, 0, 0, 0, 0],
            [0, 0, 0, 0, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 2, 0, 0, 0, 0, 0, 2, 0],
            [0, 2, 0, 0, 2, 0, 0, 0, 0, 2],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        white_client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = white_client.get_received()
        assert recv[1]["args"][0]["message"] == f"cannon shoot capture ({endX}, {endY})"
        assert room.white_captured == 1
        assert room.black_captured == 0
        assert room._turn == Player.BLACK

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [
            (8, 6, 3, 6, Player.BLACK),
            (1, 0, 5, 0, Player.WHITE),
        ],
    )
    def test_cannon_shoot_intercepted(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [2, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 1, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 2, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 2, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 2, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()
        assert recv[0]["args"][0]["message"] == "cannon shoot intercepted"
        assert room._turn == player
        assert room.black_captured == 0
        assert room.white_captured == 0

    @pytest.mark.parametrize(
        "startX,startY,endX,endY,player",
        [
            (6, 3, 6, 2, Player.BLACK),
            (6, 3, 6, 4, Player.BLACK),
            (6, 3, 5, 2, Player.BLACK),
            (6, 3, 5, 3, Player.BLACK),
            (6, 3, 5, 4, Player.BLACK),
            (2, 6, 2, 5, Player.WHITE),
            (2, 6, 3, 5, Player.WHITE),
            (2, 6, 3, 6, Player.WHITE),
            (2, 6, 3, 7, Player.WHITE),
            (2, 6, 2, 7, Player.WHITE),
        ],
    )
    def test_soldier_capture(
        self,
        startX: int,
        startY: int,
        endX: int,
        endY: int,
        player: Player,
        two_clients: Clients,
    ):
        room: Room = rooms[self._room_name]
        room.gameState = GameState.MOVE_SOLDATEN
        room._turn = player
        white_client, _, black_client, _ = get_white_black_clients(two_clients, room)
        white_client.get_received()
        black_client.get_received()
        room.board = [
            [0, 0, 0, 0, 3, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 2, 1, 2, 0, 0],
            [0, 0, 0, 0, 0, 2, 2, 2, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 1, 1, 1, 0, 0, 0, 0, 0],
            [0, 0, 1, 2, 1, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
            [0, 0, 0, 0, 0, 0, 0, 4, 0, 0],
        ]

        client = white_client if player == Player.WHITE else black_client
        client.emit("move_object", startX, startY, endX, endY, room.name)

        recv = client.get_received()

        assert recv[0]["args"][0]["capture"] == "Capture: 1"
        assert recv[1]["args"][0]["turn"] == f"Turn: {player.opponent.name}"
        assert room._turn == player.opponent
        assert room.black_captured == 0 if player == player.opponent else 1
        assert room.black_captured == 0 if player == player.opponent else 1
