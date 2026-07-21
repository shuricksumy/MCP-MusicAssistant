import pytest

from music_assistant_mcp import providers as providers_logic
from music_assistant_mcp.providers import ProviderInstance

from fakes import FakeMAClient

STREAMING = [
    {
        "instance_id": "spotify--abc",
        "domain": "spotify",
        "name": "Spotify",
        "type": "music",
        "is_streaming_provider": True,
        "supported_features": ["search", "similar_tracks"],
    },
    {
        "instance_id": "tidal--def",
        "domain": "tidal",
        "name": "Tidal",
        "type": "music",
        "is_streaming_provider": True,
        "supported_features": ["search", "similar_tracks"],
    },
]
LOCAL = [
    {
        "instance_id": "filesystem_smb--ghi",
        "domain": "filesystem_smb",
        "name": "NAS Music",
        "type": "music",
        "is_streaming_provider": False,
        "supported_features": ["search"],
    },
]
NON_MUSIC = [
    {"instance_id": "hass--xyz", "domain": "hass", "name": "Home Assistant", "type": "plugin", "is_streaming_provider": None},
]


async def test_list_providers_filters_to_music_type():
    client = FakeMAClient({"providers": STREAMING + LOCAL + NON_MUSIC})
    result = await providers_logic.list_providers(client)
    assert {p.domain for p in result} == {"spotify", "tidal", "filesystem_smb"}


def _providers():
    return [ProviderInstance.from_raw(p) for p in STREAMING + LOCAL]


def test_resolve_provider_filter_by_source_domain():
    result = providers_logic.resolve_provider_filter(_providers(), "tidal", None)
    assert result == ["tidal--def"]


def test_resolve_provider_filter_by_source_name_substring():
    result = providers_logic.resolve_provider_filter(_providers(), "nas", None)
    assert result == ["filesystem_smb--ghi"]


def test_resolve_provider_filter_source_no_match_raises():
    with pytest.raises(providers_logic.ProviderNotFoundError):
        providers_logic.resolve_provider_filter(_providers(), "nonexistent", None)


def test_resolve_provider_filter_scope_online():
    result = providers_logic.resolve_provider_filter(_providers(), None, "online")
    assert set(result) == {"spotify--abc", "tidal--def"}


def test_resolve_provider_filter_scope_local():
    result = providers_logic.resolve_provider_filter(_providers(), None, "local")
    assert result == ["filesystem_smb--ghi"]


def test_resolve_provider_filter_scope_all_returns_none():
    assert providers_logic.resolve_provider_filter(_providers(), None, "all") is None


def test_resolve_provider_filter_no_scope_no_source_returns_none():
    assert providers_logic.resolve_provider_filter(_providers(), None, None) is None


def test_resolve_provider_filter_invalid_scope_raises():
    with pytest.raises(ValueError):
        providers_logic.resolve_provider_filter(_providers(), None, "bogus")


def test_resolve_provider_filter_source_takes_priority_over_scope():
    result = providers_logic.resolve_provider_filter(_providers(), "spotify", "local")
    assert result == ["spotify--abc"]


def test_resolve_provider_filter_scope_is_case_insensitive():
    result = providers_logic.resolve_provider_filter(_providers(), None, "ONLINE")
    assert set(result) == {"spotify--abc", "tidal--def"}


# --- supports_radio ---


def test_supports_radio_true_for_streaming_artist_no_scope_restriction():
    assert providers_logic.supports_radio(_providers(), "artist", ("spotify--abc",), None)


def test_supports_radio_false_for_local_only_provider():
    assert not providers_logic.supports_radio(
        _providers(), "artist", ("filesystem_smb--ghi",), ["filesystem_smb--ghi"]
    )


def test_supports_radio_false_for_playlist_regardless_of_provider():
    assert not providers_logic.supports_radio(_providers(), "playlist", ("spotify--abc",), None)


def test_supports_radio_respects_allowed_instance_ids_scope():
    # item is backed by both a streaming provider (supports radio) and a local one, but
    # the request was scoped to local only - shouldn't "leak" the streaming capability.
    assert not providers_logic.supports_radio(
        _providers(),
        "artist",
        ("spotify--abc", "filesystem_smb--ghi"),
        ["filesystem_smb--ghi"],
    )


def test_supports_radio_true_when_any_backing_provider_in_scope_supports_it():
    assert providers_logic.supports_radio(
        _providers(),
        "artist",
        ("spotify--abc", "filesystem_smb--ghi"),
        None,
    )
