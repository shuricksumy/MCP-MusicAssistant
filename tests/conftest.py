import os

os.environ.setdefault("MA_SERVER_URL", "http://ma.invalid:8095")

import pytest

from fakes import FakeMAClient


@pytest.fixture
def players_raw():
    return [
        {"player_id": "up1", "display_name": "Living Room", "powered": True, "volume_level": 40},
        {"player_id": "up2", "display_name": "Kitchen Speaker", "powered": False, "volume_level": 20},
        {"player_id": "up3", "display_name": "LedFX Visualizer", "powered": True, "volume_level": 100},
    ]


@pytest.fixture
def fake_client(players_raw):
    return FakeMAClient({"players/all": players_raw})
