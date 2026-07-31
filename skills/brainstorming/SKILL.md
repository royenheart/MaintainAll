---
name: brainstorming
description: You MUST use this before any creative work - creating features, building components, adding functionality, or modifying behavior. Explores user intent, requirements and design before implementation.
---

# Brainstorming Ideas Into Designs

<HARD-GATE>
Do NOT write code or scaffold until you have presented a design and the user has approved it. Every project, however simple — the design can be a few sentences, but approval is required.
</HARD-GATE>

1. **看上下文**（文件 / 文档 / 近期提交）。多子系统请求先分解成子项目，逐个走本流程。
2. **逐个问澄清问题**（偏好选择题），聚焦目的、约束、成功标准。不要一次抛一堆。
3. **给 2-3 个方案**及权衡，先说推荐和理由。
4. **分节呈现设计**（架构 / 组件 / 数据流 / 错误处理 / 测试），每节确认；讲不通就回头澄清。
5. **写 spec** 到 `docs/superpowers/specs/YYYY-MM-DD-<topic>-design.md` 并提交（用户偏好优先）。
6. **自审**（内联修正即可，不再评审）：有占位符（TBD/TODO/含糊需求）？各节互相矛盾？范围够不够一个计划？任何需求有歧义 → 挑一种解释写死。
7. **用户审阅 spec**，批准后调用 writing-plans——那是唯一的下一个技能。

设计原则：单元职责单一、接口清晰、可独立理解测试；现有代码库遵循既有模式，只做服务于当前目标的改进；YAGNI 无情删功能。
