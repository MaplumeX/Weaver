# Fix deep research citation rendering

## Goal
修复 deep research 最终报告在聊天对话中的引用显示问题，让报告中的引用稳定显示为 `[1]` 这类编号形式，并保持消息区与 Artifacts 面板行为一致。

## Requirements
- 识别 deep research 报告生成到前端渲染链路中的引用格式失配点。
- 统一处理常见引用变体，避免只有理想格式才能正确渲染。
- 消息区与 Artifacts 面板使用一致的 citation 渲染逻辑。
- 为修复补充回归测试。

## Acceptance Criteria
- [ ] deep research 报告中的引用在聊天消息中正确显示为 `[1]` 形式。
- [ ] 兼容标准 `[1]` 之外的常见 citation 变体，并被规范化后正确渲染。
- [ ] Artifacts 面板与聊天消息区的引用展示一致。
- [ ] 相关后端/前端回归测试通过。

## Technical Notes
- 该问题跨越 deep research reporter 规范化逻辑与 web markdown 渲染逻辑。
- 优先做小范围、可验证的标准化修复，避免改动 deep research 主流程。
