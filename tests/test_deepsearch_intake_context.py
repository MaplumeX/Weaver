from types import SimpleNamespace

from agent.workflows.agents.clarify import DeepResearchClarifyAgent
from agent.workflows.agents.scope import DeepResearchScopeAgent
from agent.workflows.knowledge_gap import KnowledgeGapAnalyzer


class _CaptureLLM:
    def __init__(self, content: str):
        self.content = content
        self.messages = None

    def invoke(self, messages, config=None):
        self.messages = messages
        return SimpleNamespace(content=self.content)


def test_clarify_agent_prompt_includes_question_answer_history():
    llm = _CaptureLLM(
        """```json
        {
          "needs_clarification": false,
          "question": "",
          "missing_information": [],
          "intake_summary": {
            "research_goal": "Analyze AI chips",
            "background": "",
            "constraints": [],
            "time_range": "Only 2024",
            "source_preferences": [],
            "exclusions": []
          }
        }
        ```"""
    )
    agent = DeepResearchClarifyAgent(llm)

    result = agent.assess_intake(
        "AI chips",
        clarify_answers=["Only 2024"],
        clarify_history=[
            {
                "question": "What time range should the research cover?",
                "answer": "Only 2024",
            }
        ],
    )

    prompt = llm.messages[0].content
    assert "Q: What time range should the research cover?" in prompt
    assert "A: Only 2024" in prompt
    assert result["intake_summary"]["time_range"] == "Only 2024"


def test_scope_agent_prompt_and_fallback_include_clarify_transcript():
    llm = _CaptureLLM(
        """```json
        {
          "research_goal": "Analyze AI chips",
          "research_steps": ["Review the current state of the market."],
          "core_questions": ["What changed in 2024?"],
          "in_scope": ["AI chip market"],
          "out_of_scope": [],
          "constraints": [],
          "source_preferences": [],
          "deliverable_preferences": [],
          "assumptions": []
        }
        ```"""
    )
    agent = DeepResearchScopeAgent(llm)

    result = agent.create_scope(
        "AI chips",
        intake_summary={"research_goal": "Analyze AI chips"},
        clarify_transcript=[
            {
                "question": "Which sources should the research prioritize?",
                "answer": "Use official filings and earnings calls as sources.",
            }
        ],
    )

    prompt = llm.messages[0].content
    assert "Q: Which sources should the research prioritize?" in prompt
    assert "A: Use official filings and earnings calls as sources." in prompt
    assert result["source_preferences"] == ["Use official filings and earnings calls as sources."]


def test_gap_analysis_prompt_avoids_fixed_score_examples():
    llm = _CaptureLLM(
        """```json
        {
          "overall_coverage": 0.42,
          "confidence": 0.63,
          "gaps": [],
          "suggested_queries": [],
          "covered_aspects": ["最新动态"],
          "analysis": "coverage remains partial"
        }
        ```"""
    )
    analyzer = KnowledgeGapAnalyzer(llm)

    result = analyzer.analyze(
        "AI chips",
        executed_queries=["AI chips 2024 annual report"],
        collected_knowledge="Collected evidence about annual filings and roadmap updates.",
    )

    prompt = llm.messages[0].content
    assert '"overall_coverage": 0.65' not in prompt
    assert '"confidence": 0.7' not in prompt
    assert "不是默认值或示例值" in prompt
    assert "必须根据本次输入重新计算" in prompt
    assert result.overall_coverage == 0.42
