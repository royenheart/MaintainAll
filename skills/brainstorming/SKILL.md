---
name: brainstorming
description: Use when a feature or behavior change needs design decisions, requirements clarification, or comparison of approaches. Model policy index - model-policy/registry.json.
---

# Brainstorming Ideas Into Designs

## Model adaptation

Load the sibling [model-policy](../model-policy/SKILL.md) once and resolve this skill's entry. Apply its profile and applicable supplements. If unavailable, use small explicit steps and evidence-based verification; do not guess model identity or change permissions.

先检查会话中已有的目标、约束和授权。用户明确要求实现并开 PR 时，常规实现选择已获授权，不重复索取设计批准。仅在关键需求不明、选择会显著改变范围/成本，或行动超出授权时提问。小改动用几句设计即可。

1. **看上下文**（文件 / 文档 / 近期提交）。多子系统请求先分解成子项目，逐个走本流程。
2. **识别仍缺少的关键上下文**，仅对会改变方案的问题逐个澄清，聚焦目的、约束、成功标准。
3. **给 2-3 个方案**及权衡，先说推荐和理由。
4. **呈现必要设计**（接口 / 数据流 / 失败行为 / 验收标准），只有影响方案的未知项需要澄清；其余独立工作继续。
5. **需要长期记录或用户要求时写 spec** 到 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` 并提交（用户偏好优先）。
6. **自审**（内联修正即可，不再评审）：有占位符（TBD/TODO/含糊需求）？各节互相矛盾？范围够不够一个计划？低风险假设明确记录；重大歧义先澄清，不擅自写成用户要求。
7. **按已有授权推进**：复杂任务用 writing-plans 分解；简单任务直接实现。保留用户明确要求的审阅环节。

设计原则：单元职责单一、接口清晰、可独立理解测试；现有代码库遵循既有模式，只做服务于当前目标的改进；YAGNI 无情删功能。
