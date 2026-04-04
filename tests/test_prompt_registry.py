from agent.prompts import PromptManager


def test_prompt_manager_registry_exposes_runtime_prompts():
    manager = PromptManager(prompt_style="enhanced")

    prompt_ids = set(manager.registry.ids())

    assert "planning.plan" in prompt_ids
    assert "deep.scope" in prompt_ids
    assert "review.evaluate" in prompt_ids
    assert "Deep Research scope agent" in manager.render("deep.scope")


def test_prompt_manager_custom_override_applies_to_runtime_prompt():
    manager = PromptManager(prompt_style="enhanced")
    manager.set_custom_prompt("deep.scope", "custom scope prompt")

    assert manager.render("deep.scope") == "custom scope prompt"
    assert manager.get_direct_answer_prompt()
