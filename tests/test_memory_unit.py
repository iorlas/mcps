"""Unit tests for memory MCP server (OpenViking wrapper)."""

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from mcps.servers.memory import forget, list_memories, recall, remember


def _mock_response(json_data, status_code=200):
    """Create a mock httpx.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json = MagicMock(return_value=json_data)
    return resp


def _mock_client(**method_responses):
    """Create a mock httpx.AsyncClient with method responses.

    Usage: _mock_client(post=response_data, get=response_data)
    For side_effect, pass an Exception directly.
    """
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    for method, value in method_responses.items():
        if isinstance(value, Exception):
            setattr(client, method, AsyncMock(side_effect=value))
        else:
            setattr(client, method, AsyncMock(return_value=_mock_response(value)))
    return client


@pytest.mark.unit
@pytest.mark.asyncio
class TestRemember:
    async def test_remember_stores_memory(self):
        mock = _mock_client(post={"status": "ok"})
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await remember("We finished Breaking Bad S5")

        assert "stored" in result.lower()
        assert mock.post.call_count >= 1

    async def test_remember_with_custom_user_id(self):
        mock = _mock_client(post={"status": "ok"})
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await remember("Denis prefers 4K", user_id="denis")

        assert "stored" in result.lower()
        calls = mock.post.call_args_list
        resource_call = [c for c in calls if "/api/v1/resources" in str(c)]
        assert len(resource_call) > 0

    async def test_remember_returns_uri(self):
        mock = _mock_client(post={"status": "ok"})
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await remember("TV supports 4K HDR")

        assert "viking://user/memories/household/" in result

    async def test_remember_handles_api_error(self):
        mock = _mock_client(post=Exception("Connection refused"))
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await remember("test")

        assert "unavailable" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
class TestRecall:
    async def test_recall_searches_memories(self):
        search_response = {
            "status": "ok",
            "result": {
                "memories": [
                    {
                        "uri": "viking://user/memories/household/1711234567-abc12345.md",
                        "abstract": "We finished Breaking Bad S5",
                        "score": 0.95,
                        "match_reason": "semantic similarity",
                    }
                ],
                "total": 1,
            },
        }
        mock = _mock_client(post=search_response)
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await recall("Breaking Bad")

        assert "Breaking Bad" in result
        assert "0.95" in result
        call_kwargs = mock.post.call_args
        assert "/api/v1/search/find" in call_kwargs.args[0]

    async def test_recall_with_custom_user_id(self):
        search_response = {"status": "ok", "result": {"memories": [], "total": 0}}
        mock = _mock_client(post=search_response)
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            await recall("anything", user_id="denis")

        call_kwargs = mock.post.call_args
        body = call_kwargs.kwargs["json"]
        assert "viking://user/memories/denis/" in body.get("target_uri", "")

    async def test_recall_empty_results(self):
        search_response = {"status": "ok", "result": {"memories": [], "total": 0}}
        mock = _mock_client(post=search_response)
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await recall("something obscure")

        assert "nothing found" in result.lower()

    async def test_recall_handles_api_error(self):
        mock = _mock_client(post=Exception("Timeout"))
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await recall("anything")

        assert "unavailable" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
class TestListMemories:
    async def test_list_memories_returns_all(self):
        ls_response = {
            "status": "ok",
            "result": [
                {
                    "name": "1711234567-abc12345.md",
                    "uri": "viking://user/memories/household/1711234567-abc12345.md",
                    "modTime": "2026-03-24T12:00:00Z",
                    "isDir": False,
                },
                {
                    "name": "1711234999-def67890.md",
                    "uri": "viking://user/memories/household/1711234999-def67890.md",
                    "modTime": "2026-03-24T13:00:00Z",
                    "isDir": False,
                },
            ],
        }
        mock = _mock_client(get=ls_response)
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await list_memories()

        assert "Memories (2):" in result

    async def test_list_memories_filters_dirs(self):
        ls_response = {
            "status": "ok",
            "result": [
                {"name": "memory.md", "uri": "viking://user/memories/household/memory.md", "isDir": False},
                {"name": ".archive", "uri": "viking://user/memories/household/.archive/", "isDir": True},
            ],
        }
        mock = _mock_client(get=ls_response)
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await list_memories()

        assert "Memories (1):" in result

    async def test_list_memories_empty(self):
        ls_response = {"status": "ok", "result": []}
        mock = _mock_client(get=ls_response)
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await list_memories()

        assert "no memories" in result.lower()

    async def test_list_memories_handles_api_error(self):
        mock = _mock_client(get=Exception("Service unavailable"))
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await list_memories()

        assert "unavailable" in result.lower()


@pytest.mark.unit
@pytest.mark.asyncio
class TestForget:
    async def test_forget_archives_memory(self):
        mv_response = {
            "status": "ok",
            "result": {
                "from": "viking://user/memories/household/1711234567-abc12345.md",
                "to": "viking://user/archive/household/1711234567-abc12345.md",
            },
        }
        mock = _mock_client(post=mv_response)
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await forget("viking://user/memories/household/1711234567-abc12345.md")

        assert "archived" in result.lower()
        call_kwargs = mock.post.call_args
        body = call_kwargs.kwargs["json"]
        assert body["from_uri"] == "viking://user/memories/household/1711234567-abc12345.md"
        assert "viking://user/archive/household/" in body["to_uri"]

    async def test_forget_handles_api_error(self):
        mock = _mock_client(post=Exception("Not found"))
        with patch("mcps.servers.memory.httpx.AsyncClient", return_value=mock):
            result = await forget("viking://user/memories/household/nonexistent.md")

        assert "unavailable" in result.lower()
