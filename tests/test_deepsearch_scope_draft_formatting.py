from agent.runtime.deep.multi_agent.graph import _format_scope_draft_markdown
from agent.runtime.deep.multi_agent.schema import ScopeDraft


def test_scope_draft_markdown_prefers_research_steps_over_structured_sections():
    draft = ScopeDraft(
        id="scope_test",
        version=1,
        topic="北京这周天气",
        research_goal="分析北京本周天气走势及出行影响",
        research_steps=[
            "搜索北京在本周的最新天气预报。",
            "提取逐日温度、降水、风力和天气现象。",
            "结合空气质量预测, 评估对户外活动和出行的影响.",
        ],
        core_questions=["这周气温怎么变化?"],
        in_scope=["逐日天气"],
        out_of_scope=["长期气候趋势"],
    )

    markdown = _format_scope_draft_markdown(draft)

    assert "# 研究计划草案 v1" in markdown
    assert "1. 搜索北京在本周的最新天气预报。" in markdown
    assert "2. 提取逐日温度、降水、风力和天气现象。" in markdown
    assert "## Core Questions" not in markdown
    assert "## In Scope" not in markdown


def test_scope_draft_markdown_falls_back_to_generated_steps_when_missing_research_steps():
    draft = ScopeDraft(
        id="scope_test",
        version=1,
        topic="北京这周天气",
        research_goal="分析北京本周天气走势及出行影响",
        core_questions=["本周每天的气温和降水如何变化?", "哪些天气因素会影响日常出行?"],
        in_scope=["逐日天气预报", "空气质量与雾霾风险"],
        source_preferences=["官方气象数据", "AQI 预报"],
    )

    markdown = _format_scope_draft_markdown(draft)

    assert "1. " in markdown
    assert "逐日天气预报" in markdown
    assert "本周每天的气温和降水如何变化?" in markdown
    assert "最后整合证据" in markdown
