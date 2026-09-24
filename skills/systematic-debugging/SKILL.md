---
name: systematic-debugging
description: Use when a bug, failing test, intermittent failure, or unexpected behavior needs diagnosis and a verified fix. Model policy index - model-policy/registry.json.
---

# Systematic Debugging

## Model adaptation

Load the sibling [model-policy](../model-policy/SKILL.md) once and resolve this skill's entry. Apply its profile and applicable supplements. If unavailable, use small explicit steps and evidence-based verification; do not guess model identity or change permissions.

**Iron Law: NO FIXES WITHOUT ROOT CAUSE INVESTIGATION FIRST.**

调试知识大家都有；这里只约束纪律——模型在时间压力下会跳回"试改一下"。

1. **根因**：读完整错误（堆栈/行号/错误码）；稳定复现；查最近改动（git diff / 新依赖 / 环境差异）；多组件系统在每层边界打日志，跑一次让证据指出断在哪层；深层错误沿调用栈回溯到坏值的来源。没完成这步不许提修复。
2. **对照**：找代码库里相似的工作实现，列出全部差异——别假设"那个无所谓"。
3. **假设**：一次一个具体假设（"X 是根因，因为 Y"），用最小改动验证，一次只改一个变量。失败 → 新假设，不要堆叠修复。不懂就说，别装懂。
4. **修复**：先写复现 bug 的失败测试（见 test-driven-development）→ 单点修根因，不做"顺手"改动 → 验证测试绿、其它测试不破、原症状消失。
5. **3 次无效尝试后重估假设、证据与任务拆分**，不要原样重试。先修复上下文/环境不足，再按 model-policy 判断是否升级；仅在缺少权限或关键决策时询问用户。

紧急事故可以先做可逆缓解，但必须标注 mitigation、回滚方式与后续根因调查，不能声称已修复根因。诊断日志应删去密钥。

**红线**：无证据宣称根因；"试改 X 看看"；一次跑多个改动；跳过复现测试；症状修复。

不要用未经证实的统计断言归因。确认是环境/时序问题后：记录调查过程、加兜底处理（重试/超时/清晰报错）、补监控。
