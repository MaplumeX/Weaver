import json

from common import agents_store


def test_load_agents_migrates_legacy_api_search_tool_names(tmp_path):
    paths = agents_store.AgentsStorePaths(root=tmp_path, file=tmp_path / "agents.json")
    paths.file.write_text(
        json.dumps(
            [
                {
                    "id": "default",
                    "name": "Default",
                    "tools": ["tavily_search", "fallback_search", "browser_search"],
                    "blocked_tools": ["fallback_search"],
                }
            ]
        ),
        encoding="utf-8",
    )

    profiles = agents_store.load_agents(paths)

    assert profiles[0].tools == ["web_search", "browser_search"]
    assert profiles[0].blocked_tools == ["web_search"]

    persisted = json.loads(paths.file.read_text(encoding="utf-8"))
    assert persisted[0]["tools"] == ["web_search", "browser_search"]
    assert persisted[0]["blocked_tools"] == ["web_search"]
