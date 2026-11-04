# Design-Integrity Guardrails

一套给 Codex、Claude Code 和兼容 Agent 使用的轻量工程约束，目标是让 Agent 完成
**满足验收条件的最小改动**，而不是把每个任务扩展成框架、适配器层和一套新测试基础设施。

## 它解决什么问题

强模型常见的失败不是“代码写错”，而是：

- 事实、需求或外部行为还没确认，就高速做出完整架构；
- 为了不碰正确抽象，增加兼容 API、包装层、fallback、重试或第二条生产路径；
- 用更多测试、配置和文档制造“看起来专业”的完成感；
- 只看局部绿色测试，没有验证真实入口、真实输入和独立 oracle。

没有证据时，`BLOCKED`/`INCOMPLETE` 是合法结果，不需要用 fallback、mock-only 分支或更多文档掩盖。

## 组成

| 部件 | 唯一职责 | 何时触发 |
| --- | --- | --- |
| [`AGENTS.md`](AGENTS.md) | 项目级规则模板：项目事实（含全量测试命令、CI 是否跑全量）、第二条生产路径、测试预算、复审触发 | 每个任务 |
| [`design-integrity-review`](design-integrity-review/SKILL.md) | 在干净上下文里按任务契约（目标、非目标、验收条件）对一个候选改动做一次结构风险审查 | 完成检查点 |
| [`behavioral-acceptance-review`](behavioral-acceptance-review/SKILL.md) | 验证测试/eval 是否独立证明行为；Agent 产品另读 [agent-products](behavioral-acceptance-review/references/agent-products.md)，给出发布结论 | 验收面改变或 Agent 产品发布时 |
| [`review-md`](review-md/SKILL.md) | 起草或更新仓库的 `REVIEW.md`：先扫出候选，只问代码答不出的问题，负责人批准后才保存 | 只在用户点名时 |
| [`scripts/design_integrity.py`](design-integrity-review/scripts/design_integrity.py) | 只回答事实问题：自会话起点以来新增的异常边界、被改动的验收面 | 审查时手动跑；Stop hook 每轮自动跑 |

伴随 Skill 在各自仓库维护，本仓库不再复制：

- `reality-first-engineering`、`evidence-first-testing` →
  [reality-evidence-engineering](https://github.com/a1024053774/reality-evidence-engineering)
- 全部目录见 [agent-skills-index](https://github.com/a1024053774/agent-skills-index)

每层只解决自己的失败模式，不要再组合成一个“大审查 Skill”。两个审查 Skill 都会在同类问题再次出现时，给出能拦住它的检查（测试、lint 或依赖规则、脚本、hook）及运行位置；只有无法机器判定时，才给出应写回 `REVIEW.md` 或项目指令的文字规则并说明原因（闭环）。两个审查都只读，由调用方修正已确认的问题。

### 为什么两个审查都用干净上下文

实现者自己审自己，等于自己批改自己的作业：它会沿用写代码时的理由，证明代码是对的。2026-11-03 曾把结构审查改成实现 Agent 收尾自查，理由是“只拿到仓库和候选的 reviewer
会脱离意图挑刺”。真正缺的是意图，不是实现者的上下文，所以现在的做法是：

- 调用方传入目标、非目标和验收条件，不传实现理由；
- 每条 `FAIL` 要附一个能走到被标代码的输入，只靠读代码推出的问题写进 LIMITATIONS，用“may”表述，不能写成事实；
- 不是本次改动引入的问题标 `[pre-existing]`，不阻断本次，单独开票；
- 标出问题的类别并列出全部实例，已经报过的问题不再重复报；
- 报告第一行给状态，第二行先给数量，没有问题就写 `No findings.`。

## 工作协议

```text
用户请求
   │
   ├─ 小且事实已知 ───────────────► 读取代码 → 最小改动 → 覆盖本次改动的测试
   │
   └─ 事实/需求/验收缺口可能改变方向
          │
          ▼
     reality-first-engineering
          ├─ BLOCKED / INCOMPLETE ─► 报告缺口，停止扩张
          ├─ NO_GO ────────────────► 证据否定了方向，报告并换方向
          └─ PASS ─────────────────► 最小实现 → 覆盖本次改动的测试
                                                  │
                    每次 Stop：hook 跑 scanner，新增异常边界或验收面改动各阻断一次
                                                  │
                                                  ▼
                       完成检查点：design-integrity-review（干净上下文，一次）
                       （验收面改变 → behavioral-acceptance-review）
                                                  │
                                                  ▼
                       合入点：全量测试；仓库有 CI 时交给 CI，本地不重复
```

同一回答中的多次迭代不重复审查；新证据推翻方向时才重新开始。修完后最多对改动范围做一次定向复审。复审发现同一条不变式又被新的反例打破时，返回 `needs model`，不再开新一轮复审：先写出不变式，再在小范围内系统地搜索（见 `evidence-first-testing` 的顺序契约）。

## 结构风险扫描

`design_integrity.py` 是定位器，不是 AST linter。它只回答事实问题，不做语义判断。它比较
`--base` 指定的提交和当前工作区（不传时用 `HEAD`），先剔除字符串和注释，再报告：

- 新增的 `catch`/`except`/`rescue` 边界和过宽异常；
- 被吞掉的异常；
- 异常后无证据的默认返回；
- `acceptance_changes`：从基线到现在被改动的验收面文件，以及判定来源（`REVIEW.md` 或目录约定）。

`fallback`、`V2`、`Compat` 等标识符不算行为证据。fallback、兼容路径和并行 API 仍是审查时要核实的设计问题，但要按可达控制流判断，而不是按名字命中。“断言是否被放宽”这类判断也不在 scanner 里做，交给验收复审。

```bash
python3 design-integrity-review/scripts/design_integrity.py --cwd <repo> --base <起点提交> --format json
```

只比较工作区和 `HEAD` 时，会话中途已经提交的改动会从 diff 里消失，所以审查和 hook 都传会话起点的提交。scanner 安静不等于 `PASS`；命中也不等于缺陷。

## REVIEW.md 与验收面冻结

测试分两类：

- **开发测试**：实现过程中 Agent 可以增删改，由 `evidence-first-testing` 约束；
- **验收测试**：实现之前从需求写出，Agent 可以起草，用户确认；实现过程中冻结。Agent
  认为某个验收测试有错时，停下来报告，因为改验收测试等于改需求。

哪些路径是验收面，写在仓库根目录的 `REVIEW.md`：

```markdown
## Acceptance surfaces

- `tests/e2e/**`
- `golden/`
```

- `**` 跨目录，`*` 和 `?` 只在一层目录内匹配；不带通配符或以 `/` 结尾的路径覆盖其下所有文件。
- `REVIEW.md` 本身始终是验收面：删掉一条 glob 也算改需求。
- 没有这一节时，退回目录约定：路径中某一级目录名是 `acceptance`、`autoresearch`、`benchmark(s)`、`eval(s)`、`golden`、`grader(s)`、`harness` 或 `oracle`。
- 这一节存在但为空，表示仓库没有验收面（`REVIEW.md` 自身除外）。

`REVIEW.md` 的其余几节（敏感路径、各区域失败长什么样、跳过的路径）给两个审查 Skill 读。它由代码负责人写；`review-md` 负责起草，只在用户点名时运行。

## 安装

```bash
git clone git@github.com:a1024053774/design-integrity-guardrails.git
cd design-integrity-guardrails
for skill in design-integrity-review behavioral-acceptance-review review-md; do
  ln -sfn "$PWD/$skill" ~/.agents/skills/$skill        # Codex、Cursor、Gemini CLI、Factory 直接读这里
  ln -sfn ~/.agents/skills/$skill ~/.claude/skills/$skill  # Claude Code 只读自己的目录
done
```

`~/.agents/skills` 是中心目录；不要再往 `~/.codex/skills` 或 `~/.cursor/skills` 里放同名链接，否则同一个 Skill 会出现两次。一次维护多个 Skill 时，用
[agent-skills-index 的同步脚本](https://github.com/a1024053774/agent-skills-index)。

[AGENTS.md](AGENTS.md) 是项目级模板，只写项目特有的规则。读够上下文、最小计划、授权边界、测试预算、状态词汇和 Skill 路由这类跨项目默认，放在全局 `~/.codex/AGENTS.md` /
`~/.claude/CLAUDE.md`，模板里不重复，避免同一条规则加载两次、日后写法分叉。

### Acceptance auditor（Codex）

需要把验收复审委派给独立 Agent 时，将
[examples/acceptance-auditor.toml.example](examples/acceptance-auditor.toml.example) 复制到
`~/.codex/agents/acceptance-auditor.toml`，只在本地填入私有模型路由。

## Hook：只调用脚本

检查逻辑只在 `design_integrity.py` 里维护一份，所有 harness 都读同一个脚本；hook 只负责在合适的时机调用它。Stop hook 是
[agent-skills-index/hooks/stop_checks.py](https://github.com/a1024053774/agent-skills-index/tree/main/hooks)，Claude Code 和 Codex 用同一份：

- **SessionStart**：把当前 `HEAD` 记到 `<git-dir>/agent-session-base/<session_id>`。只写一次，恢复会话时保留原来的起点。
- **Stop**：用记下的起点调用 scanner（没有记录时退回 `HEAD`）。新增的异常边界和被改动的验收面各阻断一次，模型要在续跑中改回，或在回复里说明用户要求或批准了这次改动。`stop_hook_active` 为真时不再阻断，避免循环。

Claude Code 在 `~/.claude/settings.json` 的 `SessionStart` 和 `Stop` 下各挂一条
`python3 ~/.claude/hooks/stop_checks.py`。Codex（0.164.0 实测）在 `~/.codex/hooks.json`
里挂同样两个事件；未被信任的 hook 在 `codex exec` 里会被静默跳过，所以装好后要在交互式
Codex 里信任一次，hook 命令改了还要重新信任。

早期版本带一个 `integrity_hook.py`，在 `PreToolUse`/`Stop` 上按 turn 和 review epoch
预算强制复审，用来阻止 Agent 反复拉起、轮询、重启 reviewer。一个真实大型集成实例中旧流程约有 11 次 spawn、60 次 wait，耗时约 23 小时。当前运行时默认不会自行派生 reviewer，那套状态机已经删除，次数规则留在 Skill 里：每个完成检查点审查一次；同一不变式再次被打破时返回
`needs model`。旧实现可在 git 历史中找到。

## 已知边界

- scanner 是正则定位器，可能漏掉未命名的复杂度，也可能命中合法结构。
- 验收面冻结只看路径：改到验收面就阻断，不判断改动是否合理；合理的需求变更由用户确认。
- 没有记录会话起点时（例如 hook 晚于会话开始安装），scanner 退回 `HEAD`，看不到已提交的改动。
- 最终行为仍需项目自己的黑盒测试、CI 或真实入口。
- `BLOCKED`/`INCOMPLETE` 不会被自动重试成 `PASS`。

## 验证

```bash
python3 -m unittest discover -s tests
```

## License

[MIT License](LICENSE)，Copyright © 2026 LuckyE。
