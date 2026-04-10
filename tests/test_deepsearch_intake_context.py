from types import SimpleNamespace

from agent.deep_research.agents.clarify import DeepResearchClarifyAgent
from agent.deep_research.agents.scope import DeepResearchScopeAgent


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
          "status": "ready_for_scope",
          "follow_up_question": "",
          "blocking_slot": "none",
          "resolved_slots": {
            "goal": "Analyze AI chips",
            "time_range": "Only 2024",
            "source_preferences": [],
            "constraints": [],
            "exclusions": [],
            "deliverable_preferences": []
          },
          "unresolved_slots": [],
          "asked_slots": ["time_range"]
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
    assert result["resolved_slots"]["time_range"] == "Only 2024"


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
        clarification_state={
            "resolved_slots": {
                "goal": "Analyze AI chips",
                "time_range": "",
                "source_preferences": [],
                "constraints": [],
                "exclusions": [],
                "deliverable_preferences": [],
            },
            "unresolved_slots": [],
        },
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


def test_scope_agent_turns_unresolved_slots_into_assumptions():
    llm = _CaptureLLM("{}")
    agent = DeepResearchScopeAgent(llm)

    result = agent.create_scope(
        "AI chips",
        clarification_state={
            "resolved_slots": {
                "goal": "Analyze AI chips",
                "time_range": "",
                "source_preferences": [],
                "constraints": [],
                "exclusions": [],
                "deliverable_preferences": [],
            },
            "unresolved_slots": ["time_range", "source_preferences"],
        },
    )

    assert "Clarification still needed for time_range." in result["assumptions"]
    assert "Clarification still needed for source_preferences." in result["assumptions"]
