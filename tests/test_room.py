from app import BOARD_SIZE, GameState, Room


class TestRoom:
    def test_create_default_name(self):
        r = Room()
        assert r.name == "test"

    def test_create_with_name(self):
        r = Room("abc")
        assert r.name == "abc"

    def test_field_size(self):
        r = Room()
        assert len(r.board) == BOARD_SIZE and isinstance(r.board, list)

    def test_game_state(self):
        assert Room().gameState == GameState.PLACE_SOLDATEN

    def test_players_empty(self):
        assert len(Room().players) == 0
