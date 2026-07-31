---
name: systematic-debugging
description: Use when encountering any bug, test failure, or unexpected behavior, before proposing fixes
---

# Systematic Debugging

**Iron Law: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

调试知识大家都有；这里只约束纪律——模型在时间压力下会跳回"试改一下"。

1. **根因**：读完整错误（堆栈/行号/错误码）；稳定复现；查最近改动（git diff / 新依赖 / 环境差异）；多组件系统在每层边界打日志，跑一次让证据指出断在哪层；深层错误沿调用栈回溯到坏值的来源。没完成这步不许提修复。
2. **对照**：找代码库里相似的工作实现，列出全部差异——别假设"那个无所谓"。
3. **假设**：一次一个具体假设（"X 是根因，因为 Y"），用最小改动验证，一次只改一个变量。失败 → 新假设，不要堆叠修复。不懂就说，别装懂。
4. **修复**：先写复现 bug 的失败测试（见 test-driven-development）→ 单点修根因，不做"顺手"改动 → 验证测试绿、其它测试不破、原症状消失。
5. **3 次修复失败 → STOP，质疑架构**：每次修复都在别处暴露新问题、或修复需要大规模重构 = 模式错了，不是补丁错了。和用户讨论后再试第 4 次。

**红线**：先修后查；"试改 X 看看"；一次跑多个改动；跳过复现测试；症状修复。

95% 的"查不到根因"是调查不完整。确认是环境/时序问题后：记录调查过程、加兜底处理（重试/超时/清晰报错）、补监控。
