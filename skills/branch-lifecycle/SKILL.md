---
name: branch-lifecycle
description: Use when starting feature work that needs isolation from the current workspace, or when implementation is complete and the branch needs integration - creates an isolated worktree and handles merge/PR/discard with safe cleanup
---

# Branch Lifecycle

两个阶段：**Setup**（开工前隔离工作区）→ **Finish**（完成后整合）。

## Setup: 隔离工作区

1. **检测现有隔离**：`GIT_DIR=$(git rev-parse --git-dir)` vs `GIT_COMMON=$(git rev-parse --git-common-dir)`。两者不同 → 已在 linked worktree（先排除子模块：`git rev-parse --show-superproject-working-tree` 有输出 = 子模块，按普通仓库处理），直接进基线检查，**不要嵌套创建**。相同 → 普通仓库，询问用户是否建 worktree（已有声明偏好则免问）；拒绝就在原地工作。
2. **创建**：优先平台原生工具（`EnterWorktree`、`/worktree` 等）——手动 `git worktree add` 会造成 harness 看不见的幽灵状态。没有原生工具才回退 git：
   - 目录优先级：用户声明 > 已有 `.worktrees/`（或 `worktrees/`）> 默认 `.worktrees/`
   - 项目内目录创建前必须 `git check-ignore -q .worktrees`，未忽略则先加入 `.gitignore` 并提交（防止误提交 worktree 内容）
   - `git worktree add ".worktrees/<branch>" -b <branch>`；权限错误 → 告知用户并在原地工作
3. **基线检查**：自动装依赖（package.json / Cargo.toml / pyproject.toml / go.mod 对应），跑测试确认干净基线。失败 → 报告并询问，不要带着失败基线开工。

## Finish: 整合

1. **先跑全套测试**。有失败 → 展示并停止，不提供任何选项。
2. **确定基分支**：`git merge-base HEAD main`（或 master），或直接问用户。
3. **给出选项**（detached HEAD 时去掉选项 1，仅 3 个）：
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
   - 路径在 `.worktrees/` 或 `worktrees/` 下 → 我们创建的，负责清理
   - 其它路径 → 宿主环境管理，**不要删**
   - 先 `cd` 到主仓根（绝不在 worktree 内部执行 `git worktree remove`），移除后 `git worktree prune`

## 红线

- 测试没绿就谈收尾；合并后不重跑测试
- 先删分支后删 worktree（`git branch -d` 会失败）
- PR/Keep 路径清理 worktree，或清理非我们创建的 worktree
- Discard 无二次确认；无明确请求就 force-push
