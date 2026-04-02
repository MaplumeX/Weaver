## Import Inventory

This inventory captures the legacy import categories found during the
`reorganize-agent-module` implementation and the replacement entrypoints that
now own those responsibilities.

### Legacy workflow role imports

Use these runtime-owned replacements:

- `agent.workflows.agents.clarify` -> `agent.runtime.deep.roles.clarify`
- `agent.workflows.agents.scope` -> `agent.runtime.deep.roles.scope`
- `agent.workflows.agents.researcher` -> `agent.runtime.deep.roles.researcher`
- `agent.workflows.agents.reporter` -> `agent.runtime.deep.roles.reporter`
- `agent.workflows.agents.coordinator` -> `agent.runtime.deep.roles.coordinator`
- `agent.workflows.agents.planner` -> `agent.runtime.deep.roles.planner`
- `agent.workflows.agents.supervisor` -> `agent.runtime.deep.roles.supervisor`

### Legacy runtime-owned service imports

Use these runtime/shared replacements:

- `agent.workflows.knowledge_gap` -> `agent.runtime.deep.services.knowledge_gap`
- `agent.workflows.claim_verifier` -> `agent.contracts.claim_verifier`
- `agent.workflows.result_aggregator` -> `agent.contracts.result_aggregator`
- `agent.workflows.evidence_extractor` -> `agent.contracts.evidence_extractor`
- `agent.workflows.source_registry` -> `agent.contracts.source_registry`

### Legacy node and graph compatibility imports

Use these explicit runtime or compat replacements:

- `agent.workflows.nodes` -> `agent.runtime.nodes` for runtime callers
- `agent.workflows.nodes` -> `agent.compat.nodes` for temporary compatibility
- `agent.core.graph.create_research_graph` -> `agent.runtime.graph.create_research_graph`

`agent.core.graph.create_checkpointer` remains available as a temporary shim
because tests and existing callers still patch that module directly.

### Stable public surface

Supported public entrypoints after the reorganization:

- `agent`
- `agent.api`
- `agent.contracts.*`
- `agent.runtime.*`

Workflow-owned modules that remain in `agent.workflows.*` stay there because
they still represent workflow-specific behavior rather than runtime-owned deep
research internals. Examples include `agent_factory`, `agent_tools`,
`domain_router`, `parsing_utils`, `quality_assessor`, and `source_url_utils`.
