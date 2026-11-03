# Design-Integrity Guardrails

一套给 Codex、Claude Code 和兼容 Agent 使用的轻量工程约束，目标是让 Agent 完成
**满足验收条件的最小改动**，而不是把每个任务扩展成框架、适配器层和一套新测试
基础设施。

## 它解决什么问题

强模型常见的失败不是“代码写错”，而是：

- 事实、需求或外部行为还没确认，就高速做出完整架构；
- 为了不碰正确抽象，增加兼容 API、包装层、fallback、重试或第二条生产路径；
- 用更多测试、配置和文档制造“看起来专业”的完成感；
- 只看局部绿色测试，没有验证真实入口、真实输入和独立 oracle。

没有证据时，`BLOCKED`/`INCOMPLETE` 是合法结果，不需要用 fallback、mock-only 分支或
更多文档掩盖。

## 组成

| 部件 | 唯一职责 | 何时触发 |
| --- | --- | --- |
| [`AGENTS.md`](AGENTS.md) | 项目级规则模板：项目事实、第二条生产路径、测试预算、复审触发 | 每个任务 |
| [`design-integrity-review`](design-integrity-review/SKILL.md) | 实现 Agent 收尾时对自己改动的一次结构风险自查，不另起 reviewer | 完成检查点，或显式要求 |
| [`behavioral-acceptance-review`](behavioral-acceptance-review/SKILL.md) | 验证测试/eval 是否独立证明行为；Agent 产品另读 [agent-products](behavioral-acceptance-review/references/agent-products.md)，给出发布结论 | 验收表面改变或 Agent 产品发布时 |

伴随 Skill 在各自仓库维护，本仓库不再复制：

- `reality-first-engineering`、`evidence-first-testing` →
  [reality-evidence-engineering](https://github.com/a1024053774/reality-evidence-engineering)
- 全部目录见 [agent-skills-index](https://github.com/a1024053774/agent-skills-index)

每层只解决自己的失败模式，不要再组合成一个“大审查 Skill”。两个 Skill 都会在同类问题再次出现时，给出能拦住它的检查（测试、lint 或依赖规则、脚本、hook）及运行位置；只有无法机器判定时，才给出应写回项目指令的文字规则并说明原因（闭环）。行为验收复审保持只读；结构自查由实现 Agent 直接修正已确认的问题。

只有行为验收用独立上下文：它的价值在于不继承实现者的 oracle，每条 `FAIL` 都要附实际跑过的反例。结构问题的可达性和归属要结合任务的目标与非目标判断，交给只拿到仓库和候选的 reviewer，容易变成脱离意图的挑刺，所以改成实现 Agent 自查。

## 工作协议

```text
用户请求
   │
   ├─ 小且事实已知 ───────────────► 读取代码 → 最小改动 → 相关测试
   │
   └─ 事实/需求/验收缺口可能改变方向
          │
          ▼
     reality-first-engineering
          ├─ BLOCKED / INCOMPLETE ─► 报告缺口，停止扩张
          └─ PASS ─────────────────► 最小实现 → 相关现有测试与证据
                                                  │
                                                  ▼
                       完成检查点：design-integrity-review 自查一次
                       （验收表面改变 → behavioral-acceptance-review 独立复审）
```

同一回答中的多次迭代不重复自查或复审；新证据推翻方向时才重新开始。复审发现同一条不变式
又被新的反例打破时，返回 `needs model`，不再开新一轮复审：先写出不变式，再在小范围内系统地
搜索（见 `evidence-first-testing` 的顺序契约）。

## 结构风险扫描

`design_integrity.py` 是定位器，不是 AST linter。它只报告 Git 工作区 diff 中新增的
高置信度语法结构，并先剔除字符串和注释：

- `catch`/`except`/`rescue` 边界和过宽异常；
- 被吞掉的异常；
- 异常后无证据的默认返回。

`fallback`、`V2`、`Compat` 等标识符不算行为证据。fallback、兼容路径和并行 API 仍是
自查时要核实的设计问题，但要按可达控制流判断，而不是按名字命中。scanner 只比较工作区和
`HEAD`，看不到已经提交的改动，所以要在提交前运行。

```bash
python3 design-integrity-review/scripts/design_integrity.py --cwd <repo> --format json
```

scanner 安静不等于 `PASS`；命中也不等于缺陷。

## 安装

```bash
git clone git@github.com:a1024053774/design-integrity-guardrails.git
cd design-integrity-guardrails
for skill in design-integrity-review behavioral-acceptance-review; do
  ln -sfn "$PWD/$skill" ~/.agents/skills/$skill        # Codex、Cursor、Gemini CLI、Factory 直接读这里
  ln -sfn ~/.agents/skills/$skill ~/.claude/skills/$skill  # Claude Code 只读自己的目录
done
```

`~/.agents/skills` 是中心目录；不要再往 `~/.codex/skills` 或 `~/.cursor/skills` 里放同名链接，
否则同一个 Skill 会出现两次。一次维护多个 Skill 时，用
[agent-skills-index 的同步脚本](https://github.com/a1024053774/agent-skills-index)。

[AGENTS.md](AGENTS.md) 是项目级模板，只写项目特有的规则。读够上下文、最小计划、授权边界、
测试预算、状态词汇和 Skill 路由这类跨项目默认，放在全局 `~/.codex/AGENTS.md` /
`~/.claude/CLAUDE.md`，模板里不重复，避免同一条规则加载两次、日后写法分叉。

### Acceptance auditor（Codex）

需要把验收复审委派给独立 Agent 时，将
[examples/acceptance-auditor.toml.example](examples/acceptance-auditor.toml.example) 复制到
`~/.codex/agents/acceptance-auditor.toml`，只在本地填入私有模型路由。

## 为什么没有 lifecycle hook

早期版本带一个 `integrity_hook.py`，在 `PreToolUse`/`Stop` 上记录基线、按 turn 和
review epoch 预算强制复审，用来阻止 Agent 反复拉起、轮询、重启 reviewer。一个真实
大型集成实例中旧流程约有 11 次 spawn、60 次 wait，耗时约 23 小时。

当前模型和 Agent 运行时默认不会自行派生 reviewer，而改成 advisory 模式后 hook 只写
状态文件、没有任何调用方消费。因此移除了 hook 及其状态机，只在 Skill 里保留次数规则：
结构自查每个完成检查点一次；行为验收复审在同一不变式再次被打破时返回 `needs model`，
不再继续找反例。旧实现可在 git 历史中找到。

## 已知边界

- scanner 是正则定位器，可能漏掉未命名的复杂度，也可能命中合法结构。
- 最终行为仍需项目自己的黑盒测试、CI 或真实入口。
- `BLOCKED`/`INCOMPLETE` 不会被自动重试成 `PASS`。

## 验证

```bash
python3 -m unittest discover -s tests
```

## License

[MIT License](LICENSE)，Copyright © 2026 LuckyE。
