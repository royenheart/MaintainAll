# 三层作用域的操作时序与覆盖设计

> 本文是 skills-manager 插件三层作用域（会话 > 工作区 > 全局）的覆盖率设计：
> 罗列所有操作、执行时序与对应面板/强制执行该呈现的结果，并给出实现方案。

## 1. 模型

三个作用域各持有一张 override 映射（技能名 → enabled）：

    skills-manager:
      global:     { <skill>: bool }              # 全局覆盖
      workspaces: { <path>: { <skill>: bool } }  # 每个工作区一张
      sessions:   { <id>:   { <skill>: bool } }  # 每个会话一张

解析优先级（近处覆盖远处）：

    session  >  workspace  >  global  >  default(enabled)

- **缺省 = 继承**：某作用域里没有某个技能名，就沿用下一层作用域的决策。
- **动态继承**：解析在读取时对「当前 store」进行，不做快照。改低层作用域会立即影响所有没有显式覆盖它的高层作用域。
- **会话 ⇄ 工作区绑定**：一个会话恰好属于一个工作区，绑定关系即「会话的 cwd == 工作区路径」，在会话生命周期内稳定（无需额外状态标识，从 sessions store 可推导）。

## 2. 不变量

1. **最近显式覆盖胜出**：解析结果 = 链上第一个命中该技能名的覆盖，否则 default(enabled)。
2. **高层覆盖不被低层静默改写**：会话对 X 的覆盖，永远压过工作区/全局对 X 的覆盖。
3. **解析与顺序无关**：最终结果只取决于三个映射的当前内容，与「先改哪个、后改哪个」无关；「时序」只影响「何时看到/何时生效」，不影响最终值。
4. **纯函数**：resolveSkillState(store, name, view) 是纯函数，view 必须携带链上所有相关作用域身份。

## 3. 当前缺陷（对应上述不变量）

1. **会话面板的 view 漏了 workspacePath**（主缺陷）。客户端构造 view 时只给了
   sessionId，导致解析链变成 session → global，跳过了工作区层 —— 这正是「改了工作区，
   会话面板却看不到」的原因。强制执行侧（host）用 { workspacePath: cwd, sessionId } 解析，
   本来就是对的；只有客户端显示错。
2. **reset 清空整个字段而非当前实例**。会话面板的「重置」调 unset('sessions')，
   会清空所有会话的覆盖（工作区同理清空所有工作区），而不是只清当前会话/工作区。

## 4. 覆盖矩阵

### 4.1 解析结果（单个技能 X）

对技能 X，三个作用域各「有 / 无」覆盖，共 2³=8 种，解析结果唯一确定：

| session[X] | workspace[X] | global[X] | 有效状态 | 来源(origin) |
|---|---|---|---|---|
| 有 | 有 | 有 | session 值 | session |
| 有 | 有 | 无 | session 值 | session |
| 有 | 无 | 有 | session 值 | session |
| 有 | 无 | 无 | session 值 | session |
| 无 | 有 | 有 | workspace 值 | workspace |
| 无 | 有 | 无 | workspace 值 | workspace |
| 无 | 无 | 有 | global 值 | global |
| 无 | 无 | 无 | enabled | default |

### 4.2 各面板应显示的 view 与结果

| 面板 | view（链） | 对 X 显示 |
|---|---|---|
| 全局设置页 | {} | global 覆盖，否则 default |
| 工作区面板 | { workspacePath } | workspace 覆盖，否则 global，否则 default |
| 会话页签 / 新会话按钮 | { sessionId, workspacePath } | session 覆盖，否则 workspace，否则 global，否则 default |

强制执行（host 侧 model 目录）对会话 S 用 { workspacePath: cwd, sessionId } 解析，与会话面板完全一致 —— 禁用的技能从目录里消失。

### 4.3 执行时序场景

记 S=会话、W=其工作区、G=全局、X=技能。以下按操作先后展开：

- **A. 建会话（未改）→ 改工作区 → 开会话面板**
  - 期望：会话面板反映 W[X]（动态继承）。当前为缺陷 1（显示 default）。
- **B1. 建会话 → 改会话 → 改工作区 → 重开会话面板**
  - 期望：X 仍显示 S[X]（会话覆盖不被工作区覆盖）；对未在会话覆盖的技能 Y 显示 W[Y]。
  - 当前：S[X] 正确，但 Y 会错误显示 default（缺陷 1）。
- **B2a. 建会话 → 直接对话（未改会话）→ 改工作区 → 下一步 agent**
  - 期望：会话对 X 的强制执行随工作区变化（动态）。host 在 invalidate() 后下一步重新解析，
    X 被禁用/启用。当前：host 已正确（因 host 用全链），无需改。
- **B2b. 建会话 → 改会话 → 对话 → 改工作区 → 下一步 agent**
  - 期望：X 走 S[X]（会话覆盖胜出）；未覆盖的 Y 走 W[Y]（动态）。host 已正确。
- **C. 改全局 → 开会话/工作区面板**
  - 期望：无 W/S 覆盖的技能显示 G[X]（动态）。会话面板因缺陷 1 仍能显示 G[X]
    （链是 session→global），但工作区覆盖会丢失 —— 见 4.2。
- **D. 改工作区 → 建会话 → 开会话面板**
  - 期望：会话面板显示 W[X]（建会话时继承工作区）。当前为缺陷 1（显示 default）。
- **E. reset 操作**
  - 全局 reset：清空 global（唯一实例，正确）。
  - 工作区 reset：只清 workspaces[W]，不影响其它工作区（缺陷 2）。
  - 会话 reset：只清 sessions[S]，不影响其它会话（缺陷 2）。

> 结论：所有「时序」都归结为「当前 store + 正确 view 的纯解析」。唯一需要的改动是
> 补齐会话面板的 workspacePath + 修 reset 的实例语义，不需要任何快照/时间戳/绑定标记。

## 5. 边界情况

| 情况 | 处理 |
|---|---|
| 会话无 cwd（游离会话 / cwd 未就绪） | workspacePath=undefined，链退化为 session→global，工作区层不生效（正确）。 |
| 会话 cwd 与工作区 key 规范化不一致（尾斜杠/符号链接） | 需保证会话面板用「与工作区 key 相同的字符串」查 workspaces。两者都来自同一 cwd，理论一致；若不一致，以工作区 key 为准做规范化。 |
| 空 store | 全部 default(enabled)。 |
| 会话尚未进入 sessions store（竞态） | 先按 workspacePath=undefined 渲染，store 更新后重渲染补上工作区层。 |
| 全局页的 view={} | 全局页只编辑全局覆盖，不应显示会话/工作区覆盖（当前正确）。 |

## 6. 设计决策：动态继承，不做快照

- 工作区覆盖 = 「该工作区下所有会话的默认值」，会话只覆盖它显式设置的部分。
- 因此 B2（已开始对话的会话在改工作区后）同样被覆盖修改（动态），这是符合直觉的：
  用户「对工作区」禁用了 X，自然期望该工作区里正在进行的会话也不再使用 X。
- 需要「会话锁定创建时快照」的诉求才会引入快照标记；本设计不需要，保持最小状态。

## 7. 实施计划

1. **客户端补 workspacePath**：扩展 SessionsFace 暴露 byId；会话面板从
   sessions.list.getSnapshot().byId[sessionId]?.cwd 取工作区路径，构造
   view = { sessionId, workspacePath }；订阅 sessions store 以便 cwd 就绪后重渲染。
2. **修 reset**：新增纯函数 resetScopeInSection(section, scopeKind, scopeKey) 返回
   { field, value }（global 清空；workspace/session 删除对应 key 条目），reset 改走
   set(field, value) 而非 unset(field)。
3. **单测**：为 resetScopeInSection 与会话链 session→workspace→global 补用例。
4. **不改 host**：强制执行已是全链解析，无需改动。
