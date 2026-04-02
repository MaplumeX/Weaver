from agent.runtime.deep.roles.supervisor import ResearchSupervisor, SupervisorAction


class _NeverInvokeLLM:
    def invoke(self, _messages, config=None):
        raise AssertionError("LLM should not be called when quality guardrails decide action")


def test_supervisor_prefers_replan_for_low_quality_signals():
    supervisor = ResearchSupervisor(_NeverInvokeLLM())

    decision = supervisor.decide_next_action(
        topic="AI chips",
        num_queries=4,
        num_sources=8,
        num_summaries=2,
        current_epoch=1,
        max_epochs=4,
        quality_score=0.42,
        quality_gap_count=3,
        citation_accuracy=0.3,
    )

    assert decision.action == SupervisorAction.REPLAN


def test_supervisor_allows_report_for_high_quality_signals():
    supervisor = ResearchSupervisor(_NeverInvokeLLM())

    decision = supervisor.decide_next_action(
        topic="AI chips",
        num_queries=4,
        num_sources=12,
        num_summaries=3,
        current_epoch=1,
        max_epochs=4,
        quality_score=0.91,
        quality_gap_count=0,
        citation_accuracy=0.86,
    )

    assert decision.action == SupervisorAction.REPORT


def test_supervisor_prefers_plan_before_any_queries():
    supervisor = ResearchSupervisor(_NeverInvokeLLM())

    decision = supervisor.decide_next_action(
        topic="Summarize AI chip market",
        num_queries=0,
        num_sources=0,
        num_summaries=0,
        current_epoch=0,
        max_epochs=3,
    )

    assert decision.action == SupervisorAction.PLAN


def test_supervisor_honors_epoch_limit_before_dispatching_ready_tasks():
    supervisor = ResearchSupervisor(_NeverInvokeLLM())

    decision = supervisor.decide_next_action(
        topic="AI chips",
        num_queries=3,
        num_sources=8,
        num_summaries=2,
        current_epoch=3,
        max_epochs=3,
        ready_task_count=2,
        request_ids=["req-1"],
    )

    assert decision.action == SupervisorAction.REPORT
    assert decision.reasoning == "已达到最大研究轮次，停止继续派发研究任务"
    assert decision.request_ids == ["req-1"]


def test_supervisor_honors_epoch_limit_before_retrying_branch():
    supervisor = ResearchSupervisor(_NeverInvokeLLM())

    decision = supervisor.decide_next_action(
        topic="AI chips",
        num_queries=3,
        num_sources=8,
        num_summaries=2,
        current_epoch=4,
        max_epochs=3,
        retry_task_ids=["task-1"],
        request_ids=["req-1"],
    )

    assert decision.action == SupervisorAction.REPORT
    assert decision.reasoning == "已达到最大研究轮次，停止继续派发研究任务"
    assert decision.retry_task_ids == []
