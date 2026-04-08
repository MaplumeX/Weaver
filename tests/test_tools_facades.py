import ast
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]


def _parse_module(relative_path: str) -> ast.Module:
    return ast.parse((REPO_ROOT / relative_path).read_text(encoding="utf-8"))


def _star_import_modules(relative_path: str) -> list[str]:
    tree = _parse_module(relative_path)
    modules: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        if any(alias.name == "*" for alias in node.names):
            modules.append(node.module or "")
    return modules


def _module_all(relative_path: str) -> list[str]:
    tree = _parse_module(relative_path)
    for node in reversed(tree.body):
        if not isinstance(node, ast.Assign):
            continue
        if len(node.targets) != 1:
            continue
        target = node.targets[0]
        if isinstance(target, ast.Name) and target.id == "__all__":
            value = ast.literal_eval(node.value)
            if isinstance(value, list):
                return [str(item) for item in value]
    raise AssertionError(f"__all__ not found in {relative_path}")


def test_root_tools_facade_only_exports_supported_entrypoints():
    assert _star_import_modules("tools/__init__.py") == []
    assert _module_all("tools/__init__.py") == ["execute_python_code", "web_search"]


def test_internal_tool_packages_use_explicit_facades():
    expected_exports = {
        "tools/automation/__init__.py": {
            "ask_human",
            "build_computer_use_tools",
            "build_task_list_tools",
            "safe_bash",
            "str_replace",
        },
        "tools/browser/__init__.py": {
            "BrowserSession",
            "BrowserSearchTool",
            "browser_sessions",
            "build_browser_tools",
        },
        "tools/code/__init__.py": {
            "chart_visualize",
            "create_visualization",
            "execute_python_code",
        },
        "tools/crawl/__init__.py": {
            "CrawlerOptimized",
            "build_crawl_tools",
            "crawl4ai",
            "crawl_url",
            "crawl_urls",
        },
        "tools/io/__init__.py": {
            "ASRService",
            "AVAILABLE_VOICES",
            "ScreenshotService",
            "TTSService",
            "get_asr_service",
            "get_screenshot_service",
            "get_tts_service",
        },
        "tools/planning/__init__.py": {"plan_steps"},
    }

    for relative_path, required_exports in expected_exports.items():
        assert _star_import_modules(relative_path) == []
        exported = set(_module_all(relative_path))
        assert required_exports <= exported
