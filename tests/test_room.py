import pytest

from app import BLACK, BOARD_SIZE, MAX_PLAYERS_IN_ROOM, WHITE, GameState, Room, Spieler


@pytest.fixture
def room():
    r = Room()
    r.join_room("1")
    r.join_room("2")
    return r


def white_sid(room) -> str:
    return next((k for k, v in room.players.items() if v == Spieler.WHITE))


def black_sid(room) -> str:
    return next((k for k, v in room.players.items() if v == Spieler.BLACK))


class TestRoom:
    def test_create_default_name(self, room: Room):
        assert room.name == "test"

    def test_create_with_name(self):
        assert Room("abc").name == "abc"

    def test_field_size(self, room: Room):
        assert len(room.board) == BOARD_SIZE and isinstance(room.board, list)

    def test_game_state(self, room: Room):
        assert room.gameState == GameState.PLACE_SOLDATEN

    def test_room_is_full(self, room: Room):
        assert room.room_is_full()

    def test_two_players_in_room(self, room: Room):
        assert len(room.players) == MAX_PLAYERS_IN_ROOM

    def test_white_placed_all(self, room: Room):
        [
            room.place_object(x, y, white_sid(room))
            for y in range(0, 11)
            if y % 2 != 0
            for x in range(1, 4)
        ]
        room.place_object(0, 4, white_sid(room))  # town white
        assert room._white_placed_all()

    def test_black_place_first(self, room: Room):
        error = room.place_object(6, 0, black_sid(room))
        assert error is None, "value was odd, should be even"

    def test_black_place_all(self, room: Room):
        self.test_white_placed_all(room)
        room.place_object(6, 0, black_sid(room))
        [
            room.place_object(x, y, black_sid(room))
            for y in range(0, 10)
            if y % 2 == 0
            for x in range(6, 9)
        ]
        room.place_object(9, 7, black_sid(room))  # town black
        assert room._all_objects_placed()

    def test_game_state_is_move_soldiers(self, room: Room):
        self.test_black_place_all(room)
        assert room.gameState == GameState.MOVE_SOLDATEN

    def test_white_move_soldier(self, room: Room):
        self.test_black_place_all(room)
        data = {"startX": 3, "startY": 1, "endX": 4, "endY": 1, "sid": white_sid(room)}
        room.move_soldier(**data)
        assert room.board[data.get("endX")][data.get("endY")] == WHITE

    def test_black_move_soldier(self, room: Room):
        self.test_white_move_soldier(room)
        data = {"startX": 6, "startY": 0, "endX": 5, "endY": 0, "sid": black_sid(room)}
        room.move_soldier(**data)
        assert room.board[data.get("endX")][data.get("endY")] == BLACK
