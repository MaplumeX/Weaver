from agent.prompting.prompt_manager import PromptManager


def test_prompt_manager_registry_exposes_runtime_prompts():
    manager = PromptManager(prompt_style="enhanced")

    prompt_ids = set(manager.registry.ids())

    assert "planning.plan" in prompt_ids
    assert "deep.scope" in prompt_ids
    assert "review.evaluate" in prompt_ids
    assert "deep.plan" not in prompt_ids
    assert "deep.plan.refine" not in prompt_ids
    assert "deep.supervisor.decision" not in prompt_ids
    assert "deep.researcher.select_urls" not in prompt_ids
    assert "deep.researcher.summarize" not in prompt_ids
    assert "deep.researcher.gap_analysis" not in prompt_ids
    assert "deep.researcher.query_refine" not in prompt_ids
    assert "deep.researcher.counterevidence" not in prompt_ids
    assert "deep.researcher.claim_grounding" not in prompt_ids
    assert "deep.researcher.evidence_synthesis" not in prompt_ids
    assert "deep.reporter" not in prompt_ids
    assert "deep.reporter.refine" not in prompt_ids
    assert "deep.reporter.executive_summary" not in prompt_ids
    assert "Deep Research scope agent" in manager.render("deep.scope")


def test_prompt_manager_custom_override_applies_to_runtime_prompt():
    manager = PromptManager(prompt_style="enhanced")
    manager.registry.set_override("deep.scope", "custom scope prompt")

    assert manager.render("deep.scope") == "custom scope prompt"
    assert manager.render("direct_answer")
