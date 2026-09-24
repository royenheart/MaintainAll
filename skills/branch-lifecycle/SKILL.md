---
name: branch-lifecycle
description: Use when isolating development in a branch/worktree or delivering, retaining, merging, or discarding completed changes. Model policy index - model-policy/registry.json.
---

# Branch Lifecycle

## Model adaptation

Load the sibling [model-policy](../model-policy/SKILL.md) once and resolve this skill's entry. Apply its profile and applicable supplements. If unavailable, use small explicit steps and evidence-based verification; do not guess model identity or change permissions.

两个阶段：**Setup**（开工前隔离工作区）→ **Finish**（完成后整合）。

## Setup: 隔离工作区

1. **检测现有隔离**：`GIT_DIR=$(git rev-parse --git-dir)` vs `GIT_COMMON=$(git rev-parse --git-common-dir)`。两者不同 → 已在 linked worktree（先排除子模块：`git rev-parse --show-superproject-working-tree` 有输出 = 子模块，按普通仓库处理），直接进基线检查，**不要嵌套创建**。相同 → 普通仓库；按用户指定方式或合理的独立分支/worktree 隔离。已要求开 PR 无需再次询问常规分支操作。先检查 git status，保留用户改动。
2. **创建**：优先平台原生工具（`EnterWorktree`、`/worktree` 等）——手动 `git worktree add` 会造成 harness 看不见的幽灵状态。没有原生工具才回退 git：
   - 目录优先级：用户声明 > 已有 `.worktrees/`（或 `worktrees/`）> 默认 `.worktrees/`
   - 项目内目录创建前必须 `git check-ignore -q .worktrees`，未忽略时优先使用仓库外任务目录，避免无关的 ignore 提交
   - `git worktree add ".worktrees/<branch>" -b <branch>`；权限错误 → 告知用户并在原地工作
3. **基线检查**：检查依赖和安装脚本，使用可用环境运行相关基线。区分已有失败、环境阻塞与新回归；记录限制后继续可独立完成的工作。

## Finish: 整合

1. **检查完整 diff 并运行与改动风险匹配的验证**。修复新引入的失败；无法运行或已有失败须在交付中准确说明，必要时开 draft PR。
2. **确定基分支**：读取用户指定目标或 remote 默认分支，记录其 SHA，不硬编码 main/master。
3. **执行已授权的交付方式；仅在未指定时给出选项**（detached HEAD 时去掉选项 1，仅 3 个）：
   ```
   Implementation complete. What would you like to do?
   1. Merge back to <base-branch> locally
   2. Push and create a Pull Request
   3. Keep the branch as-is (I'll handle it later)
   4. Discard this work
   ```
4. **执行**：
   - **Merge**：到主仓根 `git checkout <base> && git pull && git merge <branch>` → 合并结果上重跑测试 → 清理 worktree → `git branch -d <branch>`
   - **PR**：`git push -u origin <branch>` + `gh pr create`。**不清理 worktree**——PR 迭代还要用
   - **Keep**：报告分支与 worktree 路径，不清理
   - **Discard**：先展示将删除的内容（分支、提交列表、worktree 路径），等用户输入 `discard` 确认 → 清理 worktree → `git branch -D <branch>`
5. **worktree 清理归属规则**（仅 Merge/Discard 时）：
   - 仅清理本任务记录为自己创建的资源；目录名字不能证明归属
   - 其它路径 → 宿主环境管理，**不要删**
   - 先 `cd` 到主仓根（绝不在 worktree 内部执行 `git worktree remove`），移除后 `git worktree prune`

## 红线

- 未验证就宣称通过；隐瞒失败或验证限制；合并后不检查受影响行为
- 先删分支后删 worktree（`git branch -d` 会失败）
- PR/Keep 路径清理 worktree，或清理非我们创建的 worktree
- Discard 无二次确认；无明确请求就 force-push
