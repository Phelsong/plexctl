"""Test client module for plexctl."""

import httpx
from plexctl.client import (
    PlexClient,
    PlexHTTPClient,
    _is_xml_content_type,
    _parse_xml_response,
    _xml_to_dict,
)
from plexctl.config import PlexConfig


def test_client_raises_on_missing_token() -> None:
    """Client should raise ValueError when config is missing token."""
    config = PlexConfig(url="http://localhost:32400", token="")
    try:
        PlexClient(config)
        raise AssertionError("Expected ValueError")
    except ValueError as exc:
        assert "PLEX_TOKEN" in str(exc)


def test_client_repr_disconnected() -> None:
    """Client repr should show disconnected state initially."""
    config = PlexConfig(url="http://localhost:32400", token="valid-token")
    client = PlexClient(config)
    assert "disconnected" in repr(client)


def test_client_is_not_connected_initially() -> None:
    """Client should report not connected before accessing server."""
    config = PlexConfig(url="http://localhost:32400", token="valid-token")
    client = PlexClient(config)
    assert not client.is_connected


# --- XML content-type detection ---


def test_is_xml_content_type_detects_text_xml() -> None:
    """Should detect text/xml content type."""
    assert _is_xml_content_type("text/xml") is True


def test_is_xml_content_type_detects_application_xml() -> None:
    """Should detect application/xml content type."""
    assert _is_xml_content_type("application/xml") is True


def test_is_xml_content_type_with_charset() -> None:
    """Should detect XML even with charset suffix."""
    assert _is_xml_content_type("text/xml;charset=utf-8") is True


def test_is_xml_content_type_rejects_json() -> None:
    """Should reject application/json content type."""
    assert _is_xml_content_type("application/json") is False


def test_is_xml_content_type_rejects_empty() -> None:
    """Should reject empty content type."""
    assert _is_xml_content_type("") is False


# --- XML to dict conversion ---


def test_xml_to_dict_simple_attributes() -> None:
    """Should convert XML element attributes to dict keys."""
    import xml.etree.ElementTree as ET

    elem = ET.fromstring('<MediaContainer size="25" friendlyName="Test"/>')
    result = _xml_to_dict(elem)
    assert result["size"] == "25"
    assert result["friendlyName"] == "Test"


def test_xml_to_dict_child_elements() -> None:
    """Should convert child elements as nested dicts."""
    import xml.etree.ElementTree as ET

    elem = ET.fromstring(
        '<MediaContainer size="1">'
        '<Directory count="3" key="library" title="library"/>'
        "</MediaContainer>"
    )
    result = _xml_to_dict(elem)
    assert result["size"] == "1"
    assert result["Directory"]["key"] == "library"
    assert result["Directory"]["count"] == "3"


def test_xml_to_dict_multiple_same_tag_children() -> None:
    """Multiple children with the same tag become a list."""
    import xml.etree.ElementTree as ET

    elem = ET.fromstring("<root><item name='a'/><item name='b'/></root>")
    result = _xml_to_dict(elem)
    assert isinstance(result["item"], list)
    assert len(result["item"]) == 2
    assert result["item"][0]["name"] == "a"
    assert result["item"][1]["name"] == "b"


def test_parse_xml_response_wraps_root_tag() -> None:
    """Should wrap result under the root element's tag name."""
    xml_bytes = (
        b'<?xml version="1.0" encoding="UTF-8"?>\n'
        b'<MediaContainer size="25" friendlyName="TestServer"/>'
    )
    result = _parse_xml_response(xml_bytes)
    assert "MediaContainer" in result
    assert result["MediaContainer"]["size"] == "25"
    assert result["MediaContainer"]["friendlyName"] == "TestServer"


# --- PlexHTTPClient._parse_response ---


def test_parse_response_handles_xml_content_type() -> None:
    """Should parse XML when Content-Type is text/xml."""
    config = PlexConfig(url="http://localhost:32400", token="test")
    client = PlexClient(config)
    http_client = PlexHTTPClient(client)

    xml_body = b'<?xml version="1.0"?><MediaContainer size="1" version="1.0"/>'
    resp = httpx.Response(
        200, content=xml_body, headers={"Content-Type": "text/xml;charset=utf-8"}
    )
    result = http_client._parse_response(resp)

    assert result is not None
    assert "MediaContainer" in result
    assert result["MediaContainer"]["size"] == "1"


def test_parse_response_handles_json_content_type() -> None:
    """Should parse JSON when Content-Type is application/json."""
    config = PlexConfig(url="http://localhost:32400", token="test")
    client = PlexClient(config)
    http_client = PlexHTTPClient(client)

    json_body = b'{"MediaContainer": {"size": 1}}'
    resp = httpx.Response(200, content=json_body, headers={"Content-Type": "application/json"})
    result = http_client._parse_response(resp)

    assert result is not None
    assert result["MediaContainer"]["size"] == 1


def test_parse_response_returns_none_for_204() -> None:
    """Should return None for 204 No Content responses."""
    config = PlexConfig(url="http://localhost:32400", token="test")
    client = PlexClient(config)
    http_client = PlexHTTPClient(client)

    resp = httpx.Response(204)
    result = http_client._parse_response(resp)
    assert result is None
