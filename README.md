# Design Integrity Guardrails

面向 Codex、Claude Code 及其他兼容 Agent Skills 的工程完整性约束：一份常驻
`AGENTS.md`、一个独立上下文代码复审 skill，以及在任务结束前触发复审的确定性
hook。

## 解决什么问题

编码 Agent 很容易把“当前测试通过”优化成唯一目标，进而选择短期最容易交付、
长期最难维护的实现：

- 用宽泛 `try/catch`、`except Exception`、空 catch 或默认返回值隐藏失败；
- 为了不修改正确的接口，新增 `V2`、`Safe`、`Compat` 等旁路 API；
- 到处添加没有真实产品契约的 fallback、重试或兼容分支；
- 只修眼前例子，不检查调用方、职责边界和整体架构；
- 在同一上下文里自审，为自己刚写的复杂度补理由。

这些改动通常能通过局部测试，但会增加生产路径、公共接口、状态空间和后续维护
成本。单纯继续往提示词里追加“请注意代码质量”通常不够，因为规则可能被忽略，
skill 可能没有触发，同上下文自审也容易产生动机性推理。

本仓库把约束分成三层：

1. **常驻规则**：`AGENTS.md` 定义根因范围、举证责任、比例原则和合法停止出口。
2. **确定性路由**：hook 对本轮新增的异常处理、fallback 和疑似旁路 API 做风险标记。
3. **独立语义复审**：`design-integrity-review` 在 fresh context 中检查真实调用方、
   错误所有权、架构职责和更简单的修正方式。

扫描命中只是要求复审，不等于代码有错。真正的 finding 必须有可达输入、调用路径、
具体故障或维护成本，以及更简单的修正方案。

## 仓库内容

```text
.
├── AGENTS.md
├── design-integrity-review/
│   ├── SKILL.md
│   └── scripts/
│       ├── design_integrity.py
│       └── integrity_hook.py
└── tests/
    └── test_design_integrity_gate.py
```

- `AGENTS.md`：可作为全局或项目级工程约定。
- `SKILL.md`：独立上下文的证据化复审流程。
- `design_integrity.py`：扫描 Git diff 中新增的风险结构。
- `integrity_hook.py`：记录任务基线，并在结束时要求复审本轮新增风险。
- 测试覆盖脏工作区、提交后隐藏改动、首次提交和并行工具调用等边界。

## 工作方式

```text
首个可能修改代码的工具调用
        │
        ▼
记录 Git 基线 revision + 已存在风险标记
        │
        ▼
Agent 编辑、测试，甚至在授权后提交
        │
        ▼
Stop hook 比较“基线 tree → 当前 HEAD + 当前工作区”
        │
        ├── 没有新增风险标记 ──► 正常结束
        │
        └── 有新增风险标记 ─────► 阻止结束一次
                                      │
                                      ▼
                              fresh-context 语义复审
```

基线初始化使用文件锁串行化，避免并行工具调用把新修改覆盖进“旧状态”。基线还会
保存开始时的 Git revision，因此本轮中途提交不会让完成门禁失去证据。

## 环境要求

- macOS 或 Linux；hook 使用 POSIX `fcntl.flock`。
- Python 3.10 或更高版本。
- Git 工作区。
- Codex CLI/Desktop 或 Claude Code。

## 安装

先克隆仓库：

```bash
git clone https://github.com/a1024053774/design-integrity-guardrails.git
cd design-integrity-guardrails
```

### Codex

将 skill 链接到用户级 skill 目录：

```bash
mkdir -p ~/.agents/skills
ln -s "$PWD/design-integrity-review" ~/.agents/skills/design-integrity-review
```

将 `AGENTS.md` 中需要的规则合并到 `~/.codex/AGENTS.md`，或者把本仓库的
`AGENTS.md` 放到目标项目根目录。不要无条件覆盖已有的个人或项目规则。Codex 的
加载与覆盖顺序见 [OpenAI Docs: AGENTS.md](https://learn.chatgpt.com/docs/agent-configuration/agents-md)。

在 `~/.codex/hooks.json` 的现有 `hooks` 对象中追加以下 matcher group，并把
`/absolute/path/to/repo` 替换为真实路径：

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash|apply_patch|Edit|Write",
      "hooks": [
        {
          "type": "command",
          "command": "python3 /absolute/path/to/repo/design-integrity-review/scripts/integrity_hook.py --agent codex",
          "timeout": 10
        }
      ]
    }
  ],
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "python3 /absolute/path/to/repo/design-integrity-review/scripts/integrity_hook.py --agent codex",
          "timeout": 10
        }
      ]
    }
  ]
}
```

这是追加片段，不是完整配置文件。保留已有 hooks。重新启动 Codex 后运行 `/hooks`，
逐条检查并信任新命令。Codex hook 格式见
[OpenAI Docs: Hooks](https://learn.chatgpt.com/docs/hooks)。

### Claude Code

链接 skill：

```bash
mkdir -p ~/.claude/skills
ln -s "$PWD/design-integrity-review" ~/.claude/skills/design-integrity-review
```

如果没有 `~/.claude/CLAUDE.md`，可以直接链接同一份规则：

```bash
ln -s "$PWD/AGENTS.md" ~/.claude/CLAUDE.md
```

如果已经有 `CLAUDE.md`，请手动合并规则，避免覆盖已有配置。

在 `~/.claude/settings.json` 的现有 `hooks` 对象中追加：

```json
{
  "PreToolUse": [
    {
      "matcher": "Bash|Edit|Write|MultiEdit|NotebookEdit",
      "hooks": [
        {
          "type": "command",
          "command": "python3 /absolute/path/to/repo/design-integrity-review/scripts/integrity_hook.py --agent claude",
          "timeout": 10
        }
      ]
    }
  ],
  "Stop": [
    {
      "hooks": [
        {
          "type": "command",
          "command": "python3 /absolute/path/to/repo/design-integrity-review/scripts/integrity_hook.py --agent claude",
          "timeout": 10
        }
      ]
    }
  ]
}
```

同样需要合并，而不是替换整个 `settings.json`。Claude Code 的 skill 与 hook 文档：

- [Skills](https://code.claude.com/docs/en/skills)
- [Hooks](https://code.claude.com/docs/en/hooks-guide)
- [CLAUDE.md](https://code.claude.com/docs/en/memory)

## 复审判据

对每个新增 catch/except、fallback、兼容路径、重复 API 或特殊分支，复审者需要回答：

1. **可达性**：哪个真实调用方、输入、契约或已观察失败需要它？
2. **所有权**：当前层是否真正拥有恢复、降级、清理或错误翻译职责？
3. **架构**：为什么现有抽象不能承载正确行为？修改根因层是否更清晰？
4. **比例**：修改是否限制在根因范围内，没有顺手重构或把小 bug 扩成大工程？

注释和实现者自己的解释不能单独作为证据。

## 运行测试

```bash
python3 -m unittest tests/test_design_integrity_gate.py
```

## 已知边界

- 确定性门禁目前只处理 Git 工作区。
- 扫描器是正则驱动的风险路由器，不是 AST linter，也不直接判定代码错误。
- fresh-context 复审仍需要模型进行语义判断；hook 会显式中断一次完成流程并要求
  进入复审，但不替代人的最终判断。
- 当前 hook 使用 POSIX 文件锁，Windows 尚未支持。
- 本仓库不会因为看到 `catch` 或 `fallback` 就要求删除它；有真实契约和恢复所有权
  的路径应当保留。

## 为什么不是只写 AGENTS.md

常驻规则负责价值排序，但不能保证每次都被执行。skill 提供完整复审方法，但仍可能
没有被调用。hook 把风险结构变成每个任务真实面对的完成条件，而独立上下文复审负责
避免实现者为自己的方案补理由。三层结合后，目标从“让测试变绿”变成“用证据证明这条
生产路径确实必要”。

## License

本项目采用 [MIT License](LICENSE)，Copyright © 2026 LuckyE。
