# Reality-First & Design-Integrity Guardrails

一套给 Codex、Claude Code 和兼容 Agent 使用的轻量工程约束，目标是让 Agent 完成
**满足验收条件的最小改动**，而不是把每个任务扩展成框架、适配器层和一套新测试
基础设施。

## 它解决什么问题

强模型常见的失败不是“代码写错”，而是：

- 事实、需求或外部行为还没确认，就高速做出完整架构；
- 为了不碰正确抽象，增加兼容 API、包装层、fallback、重试或第二条生产路径；
- 用更多测试、配置和文档制造“看起来专业”的完成感；
- 只看局部绿色测试，没有验证真实入口、真实输入和独立 oracle；
- 同一任务反复拉起 Agent 或 reviewer，成本超过了问题本身。

这套仓库不试图让模型“更努力”，而是改变它面对的完成条件：先确认方向，再做最小
实现；没有证据时，`BLOCKED`/`INCOMPLETE` 是合法结果。

## 最小结构

| 部件 | 唯一职责 | 何时触发 |
| --- | --- | --- |
| `AGENTS.md` / `CLAUDE.md` | 常驻决策规则、范围和停止出口 | 每个任务 |
| `karpathy-guidelines` | 执行期减法、测试预算和 Agent 分配 | 有设计选择的实现任务 |
| `reality-first-engineering` | 实现前确认事实、未知和方向 | 缺口可能改变方案时 |
| `design-integrity-review` | 冻结候选版本后的结构风险复审 | scanner 命中或显式要求 |
| `behavioral-acceptance-review` | 验证测试/eval 是否独立证明行为 | 验收表面改变时 |
| `evidence-first-testing` | 保留红态并证明测试检测到缺陷 | bug/测试工作时 |
| `integrity_hook.py` | 确定性记录基线并在结束时路由一次复审 | 有新增风险结构时 |
| `project-to-act` | 唯一持久项目事实源 | 长期项目已有/明确采用时 |

不要把这些部件再组合成一个“大审查 Skill”。每层只解决自己的失败模式。
`karpathy-guidelines` 和 `evidence-first-testing` 是可独立安装的伴随 Skill；本仓库
只规定它们在这套流程中的职责，不复制第二份项目账本或测试基础设施。

## 工作协议

```text
用户请求
   │
   ├─ 小且事实已知 ───────────────► 读取代码 → 最小改动 → 相关测试
   │
   └─ 事实/需求/验收缺口可能改变方向
          │
          ▼
     Reality Gate
     goal / non-goals / acceptance / unknowns
     smallest falsifiable probe
          ├─ BLOCKED / INCOMPLETE ─► 报告缺口，停止扩张
          └─ PASS ─────────────────► 最小实现
                                      │
                                      ▼
                           相关现有测试与证据
                                      │
                                      ▼
             只有命中结构风险/验收表面才进行一次复审
```

同一架构决策批次或同一回答中的多次迭代不重复启动 Reality Gate 或 reviewer。新证据
推翻方向时才重新开一个批次。

## 常驻规则的核心

仓库中的 [AGENTS.md](AGENTS.md) 是短版常驻规则，核心只有几件事：

1. 开工前说明目标、非目标、验收条件和未知事实；先读代码、调用方和现有测试。
2. 选择根因所在层，避免为了少改而增加旁路；没有真实 caller、contract、observed
   failure 或安全理由，就不添加新层、fallback、重试或兼容路径。
3. 发现前提错误、范围膨胀或授权不足时停下来上报；不要用漂亮补丁掩盖。
4. 不默认使用多个 Agent；先完成一条内聚路径，再决定是否需要委派。
5. 测试只服务当前验收；相关现有测试优先，新增测试必须证明未覆盖的行为。

## Reality-first engineering

`reality-first-engineering` 是前置的方向门，不是最终代码 review。它要求：

- 将信息分为 `observed`、`measured`、`inferred`、`unknown`；
- 为每个会改变方向的未知定义最小实验、输入、通过/失败条件、停止条件和证据；
- 缺少真实数据、领域负责人、外部系统或独立 oracle 时保持未知；
- 通过后才从证据推导实现计划，失败或未验证则返回 `BLOCKED`/`INCOMPLETE`。

它与 `project-to-act` 不冲突：Reality 负责当前方向判断，`project-to-act` 负责唯一的
持久目标、进度、版本、证据和验收记录。Reality 不创建 `REALITY.md` 或第二套计划。

## 测试和验收边界

测试前先问：

1. 这条测试验证哪条当前验收条件？
2. 没有它，现有测试会漏掉哪个真实回归？
3. 它是否比实现更简单、且能让一个已知坏实现失败？

默认只增加一个主路径和一个关键失败路径。不要为了完整性新增快照矩阵、参数网格、
端到端框架或测试基础设施。涉及 bug 或测试改动时，再使用 `evidence-first-testing`
保留红态/反例。

涉及 `eval`、`benchmark`、`autoresearch`、`harness`、`golden`、`oracle` 或生成产物时，
由 `design-integrity-review` 统一路由到一次 `behavioral-acceptance-review`；实现者
新增的测试只是待审证据，不是唯一 oracle。

## 结构风险扫描

`design_integrity.py` 是路由器，不是 AST linter。它只报告 Git diff 中新增的高置信度
结构：

- `catch`/`except`/`rescue` 边界和过宽异常；
- 被吞掉的异常；
- 异常后无证据的默认返回；
- 代码形态的 fallback；
- `V2`、`Compat`、`Legacy`、`Safe` 等疑似并行 API。

命中不等于缺陷。`integrity_hook.py` 记录本轮基线，结束时最多请求一次初审和一次
定向复审；它不会自动启动多个 reviewer，也不会把 scanner 安静当成 `PASS`。

## 项目账本与文档

长期项目若已采用 `project-to-act`，继续只使用它的 canonical ledger：

| 信息 | 位置 |
| --- | --- |
| 事实、约束、当前未知 | overview |
| 实验、阻塞、下一步 | progress |
| 由证据改变的路线 | versions |
| 证据、Gate、验收结论 | acceptance |

未配置的一次性项目不因 Skill 加载自动初始化。人只需要一个当前摘要；Agent 需要的
详细记录也必须有来源、状态和最后验证时间。文档过时或重复时合并，不以页数代替事实。

## 安装

先克隆仓库，然后将三个 Skill 链接到 Codex/Claude 的用户目录：

```bash
git clone git@github.com:a1024053774/design-integrity-guardrails.git
cd design-integrity-guardrails

mkdir -p ~/.agents/skills ~/.claude/skills ~/.codex/skills
ln -s "$PWD/reality-first-engineering" ~/.agents/skills/reality-first-engineering
ln -s "$PWD/design-integrity-review" ~/.agents/skills/design-integrity-review
ln -s "$PWD/behavioral-acceptance-review" ~/.agents/skills/behavioral-acceptance-review
ln -s "$PWD/reality-first-engineering" ~/.claude/skills/reality-first-engineering
ln -s "$PWD/design-integrity-review" ~/.claude/skills/design-integrity-review
ln -s "$PWD/behavioral-acceptance-review" ~/.claude/skills/behavioral-acceptance-review
```

将 [AGENTS.md](AGENTS.md) 的规则合并到 `~/.codex/AGENTS.md` 和 `~/.claude/CLAUDE.md`，
不要覆盖已有个人规则。

### Codex/Claude 生命周期门禁

在两个工具的现有 hook 配置中各追加一组 `PreToolUse` 和 `Stop`，命令分别为：

```text
python3 /absolute/path/to/repo/design-integrity-review/scripts/integrity_hook.py --agent codex
python3 /absolute/path/to/repo/design-integrity-review/scripts/integrity_hook.py --agent claude
```

Windows 使用 `py -3`；生命周期锁在 POSIX 使用 `fcntl`，Windows 使用 `msvcrt`。
默认不安装额外的 `UserPromptSubmit` 提示 hook：它只能重复提醒，不能证明 Reality Gate
已经通过，且会增加一条可能互相干扰的触发路径。Reality Gate 由常驻规则按需触发。

### Acceptance auditor（Codex）

需要验收复审时，将 [examples/acceptance-auditor.toml.example](examples/acceptance-auditor.toml.example)
复制到 `~/.codex/agents/acceptance-auditor.toml`，并只在本地填入私有模型路由。公开
模板只固定职责、`max` 推理和只读沙箱：

```ini
model = "<private-model-route>"
model_reasoning_effort = "max"
sandbox_mode = "read-only"
```

hook 只负责路由和去重，不直接启动模型；具体 provider、model、API 地址和凭据只留在
本地未跟踪配置中。

## 本次实例带来的证据

在一个真实大型 Agent 集成实例中，旧流程约有 11 次 spawn、20 个不同
子 Agent 通知、60 次 wait 和 12 次 close，完整过程约 23 小时 39 分。问题不是“审查
不够多”，而是把结构复审、业务验收、事实校验和公网 QA 混在了一起。

本版本因此采用：

- 前置 Reality Gate，而不是完成后才发现方向错误；
- 结构风险和行为验收由一个入口路由，每个候选版本只做一次有界复审；
- 绿色测试只是证据，真实输入、独立 oracle 和真实入口才决定验收；
- 多次迭代不重复拉起 reviewer，快照移动或证据不足时返回 `INCOMPLETE`；
- 文档以一个当前摘要和一个 canonical ledger 为准。

## 已知边界

- Reality Gate 不能凭空创造外部事实；需要真实输入、测量或领域负责人。
- scanner 是正则路由器，可能漏掉未命名的复杂度，也可能要求对合法结构做一次复审。
- lifecycle hook 只处理 Git 工作区；最终行为仍需项目自己的黑盒测试、CI 或真实入口。
- `BLOCKED`/`INCOMPLETE` 不会被自动重试成 `PASS`。

## 验证

```bash
python3 -m unittest discover -s tests
python3 -m compileall -q design-integrity-review reality-first-engineering tests
```

## License

[MIT License](LICENSE)，Copyright © 2026 LuckyE。
