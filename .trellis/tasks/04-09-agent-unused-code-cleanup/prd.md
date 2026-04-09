# Analyze agent module and remove unused code

## Goal

分析 `agent/` 模块的真实运行入口、外部引用与测试动态覆盖情况，识别并清理确认无用的代码，降低维护成本，同时避免破坏 `main.py`、`tools/`、`common/` 和测试依赖的公共契约。

## What I already know

- 用户希望先分析 `agent` 模块，再清除没用代码。
- 用户明确接受跑动态覆盖率检测。
- `agent/` 是后端运行时、契约、提示词和深度研究流程的主要承载目录。
- `main.py`、`common/`、`tools/` 和大量测试直接引用 `agent/` 内模块。

## Assumptions (temporary)

- 先使用 `pytest` 驱动的动态覆盖率作为“运行时未触达”的主要证据。
- “低覆盖”不等于“可删除”；只有同时满足无外部引用、无公共导出契约、动态覆盖为零或近零时，才进入保守删除范围。
- 本轮优先做保守清理，不重构仍有潜在运行价值但暂未覆盖的代码。

## Open Questions

- 是否存在只通过手工流程触达、但当前测试未覆盖的 `agent/` 代码路径。

## Requirements

- 梳理 `agent/` 的主要子模块和外部引用面。
- 跑动态覆盖率，识别未执行模块或未触达代码段。
- 结合仓库搜索确认是否存在真实调用方或公共 API 暴露。
- 仅删除确认无用的代码，避免误删公共契约。
- 对清理结果执行针对性验证。

## Acceptance Criteria

- [ ] 输出 `agent/` 模块的引用与覆盖分析结论。
- [ ] 至少完成一轮动态覆盖率检测并记录关键结果。
- [ ] 删除的代码具备“无引用 + 非公共契约 + 动态未触达”的证据链。
- [ ] 相关测试通过，且未引入导入错误或行为回归。

## Definition of Done (team quality bar)

- 变更范围保持在当前目标内，不做无关重构。
- 对删除项提供足够证据，避免基于猜测删代码。
- 相关测试通过。
- 如发现应补文档或规范，明确记录。

## Out of Scope (explicit)

- 不对 `agent/` 做大规模架构重构。
- 不以纯静态分析结果直接大面积删代码。
- 不清理仅因测试覆盖不足而暂时未命中的潜在运行路径。

## Technical Notes

- 相关规范：
  - `.trellis/spec/backend/directory-structure.md`
  - `.trellis/spec/backend/quality-guidelines.md`
  - `.trellis/spec/backend/tool-runtime-contracts.md`
  - `.trellis/spec/guides/cross-layer-thinking-guide.md`
  - `.trellis/spec/guides/code-reuse-thinking-guide.md`
- 当前已观察到 `main.py`、`common/checkpoint_runtime.py`、`common/session_service.py`、`tools/*`、`tests/*` 对 `agent/` 有广泛引用。
- 后续将把动态覆盖结果和候选删除列表回写到本文件。
