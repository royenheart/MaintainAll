# `@maintainall/dsh-plugin-skills-manager`

dsh 插件: 管理 skills 的使用。按 **会话 > 工作区 > 全局** 三个作用域提供
「开启 / 禁用技能」, 作用域之间有覆盖关系 (更近的作用域覆盖更远的)。

## 功能

1. **全局技能设置** — 在 dsh 设置里启用/禁用技能 (写入
   `settings.yaml` 的 `skills-manager` 命名空间); 技能清单跟随**当前会话**发现
   (复用 `skill.list` RPC, 它是 session-addressed);
2. **工作区覆盖** — 每个工作区可覆盖全局设置; 通过工作区三点溢出菜单里的
   「技能管理」选项弹出工作区技能面板。该入口需要 dsh 仓库的 per-workspace 子
   slot `sidebar.workspaces.entry` (见「已知限制」);
3. **会话覆盖** — 已有对话的 session 在上方「轨迹」右侧加「技能」页签, 支持
   Shift 连续多选 / Ctrl 独立多选后批量启用/禁用。

## 技能识别范围

只识别来自 `.agents` 通用目录与 dsh 自身技能目录的技能:

| source | 路径 | 含义 |
|---|---|---|
| `project-dsh` | `<project>/.dsh/skills` | dsh 自身项目目录 |
| `project-agents` | `<project>/.agents/skills` | `.agents` 通用目录 |
| `user-dsh` | `$DSH_HOME/skills` | dsh 自身用户目录 |
| `user-agents` | `~/.agents/skills` | 用户 `.agents` |

其它 agent 的技能目录 (`.claude/skills`、`.codex/skills`、`.cursor/rules` 等)
以及 `bundled`/`runtime`/`custom` 来源 **不识别、不管理**。见
`src/core/skill-filter.ts`。

## 目录结构

```
apps/dsh-plugin-skills-manager/
├── src/
│   ├── index.ts              # host 插件: ctx.skillManager + settings + 强制 provider
│   ├── client.ts             # client 插件: locale + 三个 UI 挂载点
│   ├── core/                 # 纯逻辑 (无 dsh 依赖, 可单测)
│   │   ├── scope.ts          # 作用域覆盖解析
│   │   ├── skill-filter.ts   # 技能识别 / 过滤
│   │   └── settings-schema.ts# settings + 持久化形状
│   └── locales/              # i18n 字典 (zh / en) + 校验
├── tests/                    # node --test 单元测试
├── package.json
└── tsconfig.json
```

## i18n

复用 dsh 自带的 locale 框架 (`@deepseek-ai/dsh-client-locale`): 本插件在
`src/locales/` 里定义 `skills-manager` 命名空间的 `zh` / `en` 两套字典, host
端通过 `ctx.locale.register('skills-manager', dicts)` 注册, UI 端用
`ctx.locale.bind('skills-manager')` 取翻译函数。所有 UI 文案都走这个 API,
双语键集合与占位符对称性由 `tests/i18n.test.ts` 强制。

## 挂载

作为插件集的一员挂在 `maintainall.yml` (见 `stow-configs/dsh/`):

```yaml
- id: skills-manager
  name: '@maintainall/dsh-plugin-skills-manager'
  config: {}
```

host 端默认导出 `SkillManagerService` (提供 `ctx.skillManager`); client 端导出
`./client` 的 `apply`。client **不引入自定义 RPC** (自定义 Typert Remote 需要在
dsh 仓库内跑 codegen), 而是复用两个现成 wire 面:

- **覆盖读写** — `ctx.settingsScope.bind({ namespace: 'skills-manager' })`,
  同一个 namespace 的 `global` / `workspaces` / `sessions` 三块都存进
  `settings.yaml`, 走现成的 settings 传输与修订/冲突处理;
- **技能清单** — `ctx.connection.api.skills.list({ sessionId })` (与
  `/`-触发技能选择器同一个只读目录), 再与 settings 里已有的覆盖名取并集, 保证
  被禁用的技能仍以「禁用」行出现、可重新启用。

## 开发与测试

```bash
cd apps/dsh-plugin-skills-manager
npm test            # node --test tests/*.test.ts (纯逻辑单测, 无需 dsh 运行时)
npm run build       # tsdown 打包 host/client (需要 dsh 仓库的构建环境)
```

## 强制机制

host 注册一个 rank-50 的全局 provider（`src/index.ts`），在 `list(options)` 里
屏蔽「禁用」的技能。关键点：registry 在运行时会把这个 lookup 的 `scope` 原样转发
给 provider（`dsh-tool-skill` 的 catalog 渲染以 `scope: agent` 调用 `snapshot`，
见其源码），而 agent 的 scope key 就是 Agent 本身，`scope.id` 即 session id。因此
provider 用 `sessionIdOf(options)` 取出 session，再调纯函数 `disabledSkillNames`
解析「会话 > 工作区 > 全局」三层，catalog 缓存又按 scope 链隔离——这样三层强制
（禁用/恢复）都生效，无需自定义 RPC。

## 已知限制

- **工作区溢出菜单入口** 需要工作区浏览器声明 per-workspace 子 slot
  (`sidebar.workspaces.entry`); 该 slot 在标准 dsh 构建里不存在。本仓库已把补丁
  应用到 `~/softwares/deepseek-harness` 的 `packages/client/ui-workspace`, 改动如下
  (需要重新构建 dsh 客户端 bundle 并改用源码/重建产物运行才生效; 当前 `npx` 的
  rc.6 不含此 slot):

  1. `contract/slots.ts` — 声明 slot + owner 类型, 并把
     `PropsRenderSlots<'sidebar.workspaces.entry'>` 并进 `WorkspaceBrowserProps`;
  2. `index.ts` — `sidebar.workspaces` 的 `children` 里加该 slot;
  3. `rows/Rows.tsx` — `ProjectRowItem` 加 `onManageSkills` 与「技能管理」菜单项;
  4. `WorkspaceBrowser.tsx` — 加 `skillsTarget` 状态 + 溢出菜单项点击后弹出的
     `<Modal>`, 其中 `renderSlot('sidebar.workspaces.entry', { workspacePath })`;
  5. `locales.ts` — 加 `menu.manageSkills` 键 (zh/en)。

  未打补丁时, 工作区作用域的覆盖仍可通过会话页签或 host 端 `ctx.skillManager`
  管理, 但溢出菜单没有「技能管理」入口。工作区面板的技能发现同样受
  `skill.list` 的 session-addressed 限制: 无对应 session 时只显示「覆盖名 + 按名
  添加」。

- **技能清单只含 user-invocable 项** — `skill.list` 只返回 user-invocable 目录,
  因此 `userInvocable: false` 的「仅模型」技能不会出现在管理列表里; 这类技能
  在标准 profile 里很少 (默认都 user-invocable)。host 侧 `ctx.skillManager.list()`
  仍会按 source 完整识别 `.agents` + dsh 目录, 是权威的管理清单。
- **自定义 RPC 未生成** — 若要给 client 加一个专属的「带 source 的技能清单」
  Remote, 需要在 dsh 仓库内用 Typert codegen; 本插件刻意不依赖它, 直接按
  `maintainall.yml` 里的构建产物路径加载 (无需 npm 发布/安装)。
