import pytest

from app import BOARD_SIZE, GameState, Room


@pytest.fixture
def room():
    return Room()


class TestRoom:
    def test_create_default_name(self, room: Room):
        assert room.name == "test"

    def test_create_with_name(self):
        s = "abc"
        assert Room(s).name == s

    def test_field_size(self, room: Room):
        assert len(room.board) == BOARD_SIZE and isinstance(room.board, list)

    def test_game_state(self, room: Room):
        assert room.gameState == GameState.PLACE_SOLDATEN

    def test_players_empty(self, room: Room):
        assert len(room.players) == 0

    def test_add_player(self, room: Room):
        room.join_room(room.name)
        assert len(room.players) == 1
