# 模型分级与技能适配

检索日期：2026-09-24。规范数据唯一入口是 `registry.json`；本页解释方法，不另存模型排名表。

## 触发、适配、调度的边界

支持 Agent Skills 的宿主通常先索引 name/description，再按任务或显式调用加载正文。
description 中的 `model-policy/registry.json` 是发现入口，不是标准规定的自动模型调度语法。
技能正文明确加载 companion；真正切换模型/effort 需要宿主能力。官方机制见
[OpenAI Skills](https://developers.openai.com/plugins/concepts/skills)。

本次覆盖 `skills/` 的十个开发技能；`.agents/skills/` 是 MaintainAll AIOps 领域技能，
`deploy/compute-use/skills/` 是另一部署资产，均不混入开发技能索引。
现有 TUI loader 没有自动执行本策略，本 PR 不改变模型配置或运行时权限。

## 身份与阶梯

评价单位是模型版本 × 提供商/endpoint × 原生推理配置 × 任务方向。
正式实验还必须固定 prompt/skill Git SHA、harness、工具权限、上下文长度、采样参数、
token/time budget；开源模型另记权重与 tokenizer revision、量化、推理引擎和硬件。

- `U`：未评估/身份不明/过期；不是低智力判断，使用 scaffolded 指导。
- `T1`：边界明确的局部任务，需要显式输入输出和中间检查。
- `T2`：多步骤实现/集成，按组件边界验证。
- `T3`：复杂诊断/架构/审查，比较假设并检查独立证据。

阶梯是 MaintainAll 的工程策略，不是人的 IQ，也不是厂商市场分级。
总参数与每 token 激活参数分开记录；闭源未知值用 null，不根据价格、品牌或输出风格猜测。
硬件/量化可以改变延迟与质量，不能将参数大小直接映射到阶梯。

原生配置不能通用化：OpenAI 的 effort、Qwen 的 enable_thinking、其它厂商的 thinking
开关/预算不是同一尺度。缺少配置时保持 U；不能用高 effort 的成绩证明 low 也同样可靠。
[OpenAI reasoning](https://developers.openai.com/api/docs/guides/reasoning) 明确说明支持值与默认值依模型而异。

## 初始索引的证据状态

当前六个模型、十个配置行是**暂定候选/未评估记录**，不是完整的实测排行榜。
保留当前 OpenAI Sol、仓库使用的 DeepSeek、不同规模的 Qwen，以及 GPT-5.4 历史锚点。
各模型的具体配置、任务阶梯、参数规模、理由和来源都在 JSON 中。
高 effort 的候选阶梯是待检验假设，不能解释为已证明提升。

只导入了能明确读到的两条 AA 原始 composite 观察，不将其直接算作代码/审查/工具能力。
没有捕获到的样本量、置信区间和局部指标用 null，未跑本地模型调用或付费评测。
`observed_at` 是读取榜单快照的时间；`measured_at` 是原始评测运行日期，未公开时为 null。
读取新快照不代表刚重新评测，未知实测时间的记录不能获得已校准资格。
Qwen 对比页没有可可靠提取的任务分数；社区资料本轮核实了 Arena 的方法，但没有导入
可归因到这些精确配置的社区观测。因此相应数组为空，禁止标成 calibrated。

发现一个实际的版本风险：DeepSeek 文档说明 `deepseek-v4-flash` 已变为 V4.1 Flash 的旧别名。
resolver 不自动把旧名映射到新名，调用者必须确认实际版本。
DeepSeek thinking 配置页本轮读取失败，不能据此猜造 API 参数；AA 的 max 标签仅是评测配置名。
[DeepSeek 模型说明](https://api-docs.deepseek.com/quick_start/pricing/)。

## 多来源、多任务评价矩阵

下列是应采集的独立证据渠道，登记来源不等于已取得某个模型的成绩。

| 方向 | 优先证据 | 不能直接外推的内容 |
|---|---|---|
| 局部编程/测试 | [LiveCodeBench](https://livecodebench.github.io/) + 本地行为测试 | 竞赛题不代表仓库维护能力 |
| 仓库修复/调试 | [SWE-bench](https://www.swebench.com/index.html) + 本地故障样本 | Verified/Pro/不同 agent、预算、子集不混排 |
| 终端/多步执行 | [Terminal-Bench](https://www.tbench.ai/) + 沙箱任务 | 分数属于模型与 agent 组合 |
| 工具/结构化输出 | [BFCL](https://gorilla.cs.berkeley.edu/leaderboard) + schema/失败恢复测试 | 原生 function calling 与 prompt 模拟分开 |
| 推理/指令/长文档 | [LiveBench](https://github.com/LiveBench/LiveBench) + [AA 方法](https://artificialanalysis.ai/methodology/intelligence-benchmarking) | 同一底层 benchmark 的转载不算独立证据 |
| 真实使用体验 | [Arena 方法](https://arena.ai/blog/arena-rank) + 有原始 trace 的社区报告 | 偏好、表达和流畅度不等于可执行正确性 |
| 技能适配本身 | 自有保留集的无技能/基础技能/适配技能配对实验 | 不能用同一批调提示词的样本宣称泛化 |

“审查能力”没有简单可靠的统一外部指标，须加入已知缺陷与无缺陷样本，衡量发现率、
误报率、严重性和可复现性；架构任务使用预先定义 rubric 与独立人工复核。

## 晋级、冲突与过期

这是未来校准的准入规范；v1 helper 仅做静态查表，不运行评分服务：

1. 每个任务方向收集至少两个独立评测组织的相关结果；官方模型卡用于参数/能力契约，
   不充当第二份独立性能证据。记录原始分数、方向、单位、任务集版本、配置、时间和运行方式。
2. 同一 benchmark 的不同配置/版本分组保留，绝不平均 Elo、pass rate 和 composite index。
   如果要合成，先固定参考 cohort 与时间窗，在可比组内归一化，再公开任务权重与缺失覆盖率。
   默认保留任务能力向量及质量/成本/延迟 Pareto 比较；缺失项不是零，也不重分配成虚高分。
3. 本地每方向至少 30 个独立用例、每例 3 次；按用例聚类计算 95% 区间，不能把重复调用当
   独立样本。难例不足则维持 provisional；阈值是项目策略，须用基线校准，不是假称行业标准。
4. T1/T2/T3 分别对应有界、多组件、复杂判断难度集。候选需要在目标难度集达到预注册的
   成功率/误报率/成本/延迟门槛，且关键破坏性失败为零；不能仅通过简单题就升 T3。
5. 社区证据保存链接/日期、原始 prompt、环境、版本、样本数、可复现 trace、正反反馈。
   去重转帖、标记赞助与选择偏差；匿名情绪仅作为调查线索。偏好分不覆盖客观正确性。
6. 外部榜单、社区反馈、本地结果冲突时保留冲突并扩大配对验证；默认采用更保守的执行方式。
   先查模型漂移、工具与预算差异。不得挑最高分，也不得把训练污染风险当已证实污染。
7. 当前记录、来源访问、关联观察快照或已知实测日期超过 JSON 中的 45 天复核期，
   或日期在未来，resolver 回落到 U。
   模型别名漂移或运行环境变更需要立即复核，不等待过期。
8. 晋级通过审阅的 PR 更新唯一索引并记录理由、原始结果和回滚版本。v1 validator 明确拒绝
   calibrated 状态，未来服务接入时需一起实现并审查证据校验，不能只改状态字符串。

## 模型差异如何影响技能

通用技能保持一个核心版本，差异来自 JSON 的 profile、supplements 和 additional_skills。
scaffolded 增加显式契约、单步实验和计划辅助；standard 按组件推进；analytical 强调假设比较。
所有配置都保留验证与证据记录。新模型特有修补应附上复现样本和失效条件，避免永久堆提示词。
模型能力不足时先缩小任务/补上下文，再请求宿主支持的升级；工具/权限问题不能靠升级模型解决。

`additional_skills` 是按阶段使用的依赖，不是无条件递归执行；每个任务记录已加载集合。
`--risk high` 始终增加风险审查，强模型不能跳过权限、数据保护或测试。

## 使用与分发

从仓库根目录运行：

```bash
python3 skills/model-policy/scripts/resolve.py --validate
python3 skills/model-policy/scripts/resolve.py --model gpt-6-sol --variant medium --skill systematic-debugging
python3 skills/model-policy/scripts/resolve.py --model Qwen/Qwen3-8B --variant non-thinking --skill dsh-plugin-development --risk high
python3 skills/model-policy/scripts/resolve.py --skill writing-skills
python3 -m unittest discover -s tests -p 'test_model_policy.py' -v
```

`--as-of YYYY-MM-DD` 仅用于重放历史策略，不能用来绕过当前证据过期。
`--task review` 可以给审查角色显式选择方向；不要为了提高阶梯改成无关方向。
CLI 使用脚本位置定位索引，与当前工作目录无关；只需要 Python 3.11+ 标准库，无 API Key。

分发时复制 `model-policy/` 与所选开发技能为同级目录，还要包含 JSON 引用的
`writing-plans/`、`verification-before-completion/`；如果使用子代理模板则保留整个对应目录。
例如安装到宿主支持的 `.agents/skills/` 时维持这些兄弟目录结构。
只复制单个 SKILL.md 会丢失共享策略；缺少 companion 时正文规定保守降级，不自动联网安装。
不要将本仓库开发技能静默安装进 AIOps 的 `.agents/skills/` 或更改其 loader 配置。

运行静态测试只能证明索引/回退/引用行为，不能证明模型排序与提示词效果。
