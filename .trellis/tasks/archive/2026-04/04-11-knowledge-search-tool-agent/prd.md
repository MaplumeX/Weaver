# Add Knowledge Search Tool For Tool Agents

## Goal
Provide ordinary tool agents with a first-class `knowledge_search` capability backed by the existing knowledge-file RAG pipeline, while enforcing user-scoped access to uploaded knowledge files.

## Requirements
- Add ownership/scope fields to knowledge file records and keep file operations scoped to the current owner.
- Extend knowledge retrieval so search only returns chunks visible to the current owner.
- Add a dedicated `knowledge_search` tool for tool agents instead of reviving the removed `rag_search` name.
- Register the tool through the existing tool capability/runtime pipeline with a separate `knowledge` capability.
- Update knowledge-file API routes to resolve the effective owner from request context before listing, uploading, downloading, reindexing, or deleting files.
- Add prompt guidance so agents use `knowledge_search` for uploaded/private/internal documents.

## Acceptance Criteria
- [ ] Knowledge file persistence records owner metadata and no longer behaves like a global shared pool by default.
- [ ] `KnowledgeService.search()` accepts scope input and only returns hits for visible files.
- [ ] Tool agents can receive `knowledge_search` through the tool registry/capability system.
- [ ] `search` capability alone does not implicitly grant `knowledge_search`.
- [ ] Knowledge API routes respect owner scoping for list/upload/download/reindex/delete flows.
- [ ] Regression tests cover the scoped service behavior, tool capability expansion, and API owner enforcement.

## Technical Notes
- Reuse the existing Milvus-backed knowledge search result payload shape where possible.
- Keep the tool explicit and separate from `web_search`.
- Follow existing JSON-file persistence patterns rather than introducing a new DB layer.
