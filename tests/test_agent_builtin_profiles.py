from __future__ import annotations

import json
from pathlib import Path


def _profile_tools() -> dict[str, set[str]]:
    payload = json.loads((Path(__file__).resolve().parents[1] / "data" / "agents.json").read_text())
    return {
        str(item["id"]): {str(tool) for tool in (item.get("tools") or [])}
        for item in payload
        if isinstance(item, dict) and item.get("id")
    }


def _profiles() -> dict[str, dict]:
    payload = json.loads((Path(__file__).resolve().parents[1] / "data" / "agents.json").read_text())
    return {
        str(item["id"]): item
        for item in payload
        if isinstance(item, dict) and item.get("id")
    }


def test_default_profile_keeps_legacy_default_tool_coverage() -> None:
    tools = _profile_tools()["default"]

    assert {
        "tavily_search",
        "fallback_search",
        "crawl_urls",
        "crawl4ai",
        "chart_visualize",
        "create_tasks",
        "view_tasks",
        "update_task",
        "get_next_task",
        "ask_human",
        "str_replace",
        "plan_steps",
        "browser_click",
        "browser_back",
        "browser_extract_text",
        "browser_list_links",
        "browser_screenshot",
        "browser_reset",
    } <= tools


def test_manus_profile_keeps_legacy_full_tool_coverage() -> None:
    tools = _profile_tools()["manus"]

    assert {
        "ask_human",
        "plan_steps",
        "sandbox_delete_file",
        "sandbox_upload_file",
        "sandbox_download_file",
        "sandbox_kill_process",
        "sandbox_list_processes",
        "sandbox_format_cells",
        "sandbox_create_chart",
        "sandbox_add_sheet",
        "sandbox_read_spreadsheet",
        "sandbox_add_formula",
        "sandbox_add_slide",
        "sandbox_add_image_to_slide",
        "sandbox_add_table_to_slide",
        "sandbox_add_shape_to_slide",
        "sandbox_get_presentation_info",
        "sandbox_update_slide",
        "sandbox_delete_slide",
        "outline_to_presentation",
        "refine_presentation_outline",
        "expand_slide_content",
        "apply_presentation_theme",
        "set_slide_background",
        "duplicate_slide",
        "reorder_slides",
        "add_text_box",
        "sandbox_get_image_info",
        "sandbox_resize_image",
        "sandbox_convert_image",
        "sandbox_crop_image",
        "sandbox_read_qr_code",
        "sandbox_compare_images",
        "apply_image_effect",
        "adjust_image",
        "rotate_flip_image",
        "add_watermark",
        "overlay_images",
        "create_thumbnail",
        "computer_move_mouse",
        "computer_press",
        "computer_scroll",
        "computer_screenshot",
        "computer_screen_info",
        "computer_drag",
    } <= tools


def test_builtin_profiles_include_new_role_capability_contract_fields() -> None:
    profiles = _profiles()

    default_profile = profiles["default"]
    manus_profile = profiles["manus"]

    assert default_profile["roles"] == ["default_agent"]
    assert {"search", "browser", "planning", "python"} <= set(default_profile["capabilities"])
    assert default_profile["blocked_capabilities"] == []
    assert default_profile["policy"] == {}

    assert manus_profile["roles"] == ["default_agent"]
    assert {"search", "browser", "shell", "presentation", "computer", "sandbox"} <= set(
        manus_profile["capabilities"]
    )
    assert manus_profile["blocked_capabilities"] == []
    assert manus_profile["policy"] == {}
