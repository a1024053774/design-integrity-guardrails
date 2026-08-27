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
- `design_integrity.py`：扫描 Git diff 中新增的风险结构，并输出供复审使用的风险标记。
- `integrity_hook.py`：记录任务基线，在结束时比较本轮新增风险标记，并要求进行复审。
- 测试覆盖脏工作区、提交后隐藏改动、首次提交和并行工具调用等边界。

## 扫描哪些风险结构

`design_integrity.py` 是一个正则驱动的路由器，不是 AST linter。它只扫描可识别的
源文件 Git diff，并且只把新增行报告为风险标记；未改变的上下文只用于定位已有的
异常边界。当前标记包括：

| 标记 | 识别的结构 | 目的 |
| --- | --- | --- |
| `exception-boundary` | 带 body 的 `catch`、Python `except`/`except*`、Ruby `rescue`，以及 Promise `.catch(...)` 调用 | 要求复审错误处理是否有真实输入、调用方和恢复所有权 |
| `broad-exception` | Python `except:`、`except Exception`、`except BaseException`，也覆盖 `except*` 变体 | 防止用过宽异常范围隐藏根因 |
| `swallowed-exception` | 空 `catch`、内联 `except: pass`，或在已有异常边界中新增 `pass` | 防止异常被静默吞掉 |
| `default-after-catch` | 异常处理体中新增 `return None`、`null`、`nil`、布尔值、`0`、空字符串、空数组或空对象 | 防止用无证据的默认值掩盖失败 |
| `fallback-marker` | 代码形态中的 `fallback` 标识符：调用、属性、下标、赋值或关键字参数 | 复审是否存在没有契约依据的降级路径 |
| `parallel-api-name` | `def`、`function`、`class`、`func`、Rust `fn`、Kotlin `fun` 声明中带有 `V2`、`New`、`Safe`、`Compat`、`Legacy` 等旁路命名 | 防止为避免修改正确抽象而新增重复公共 API |

这些标记只是“需要看一眼”的路由信号，不等于代码一定错误。有真实契约、可达失败
和正确职责归属的异常处理或 fallback 可以保留。反过来，重试、任意特殊分支、无
关键字的方法重命名等不一定会被 scanner 命中，仍由 `design-integrity-review` 的
语义复审负责。

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

扫描器使用有限的 diff 上下文来识别“已有异常边界中新增的处理体”：上下文只用于
定位边界，不会被当作本轮新增 finding。这样既能捕获把已有 `except/catch/rescue`
改成默认返回或 `pass` 的漏报，也不会因为旧代码本身存在异常处理而重复报警。Ruby
`rescue` 仅匹配高置信度子句和后缀代码形态，普通字符串或散文中的单词不应触发。

基线初始化使用文件锁串行化，避免并行工具调用把新修改覆盖进“旧状态”。基线还会
保存开始时的 Git revision，因此本轮中途提交不会让完成门禁失去证据。

## 环境要求

### Scanner

- macOS、Linux 或 Windows。
- Python 3.10 或更高版本。
- Git 工作区。

只运行 `design_integrity.py` 时，Windows 原生环境可以使用 Python 和 Git；例如：

```powershell
py -3 design-integrity-review/scripts/design_integrity.py --cwd . --format text
```

### Lifecycle hook

- Codex CLI/Desktop 或 Claude Code。
- macOS 或 Linux；当前 hook 使用 POSIX `fcntl.flock`，Windows 原生环境暂不支持。

Windows 用户如果需要完整的 `PreToolUse`/`Stop` 门禁，请在 WSL2 或 Linux CI 中运行
hook；也可以在 Windows 原生环境只运行 scanner，待后续加入 Windows 文件锁实现后再
接入生命周期 hook。不要直接把当前 `integrity_hook.py` 配置到 Windows 原生 Python，
因为模块导入阶段就会依赖不可用的 `fcntl`。

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
- 生命周期 hook 使用 POSIX 文件锁，Windows 原生尚未支持；Windows 可单独运行 scanner。
- 本仓库不会因为看到 `catch` 或 `fallback` 就要求删除它；有真实契约和恢复所有权
  的路径应当保留。
- 正则只匹配高置信度代码形态；行首 `*` 的解引用赋值会被当作注释跳过。
- 字符串字面量里的代码形态（如 `"fallback()"`）仍可能触发。
- Java/C# 等无关键字的方法定义不在 parallel-api 检测范围内。
- fallback 识别要求代码形态后缀（调用/属性/下标/赋值）；纯值位置引用（如
  `?? fallbackValue`、实参、对象键）不触发，属有意的精度取舍。
- 对已有 `catch/except/rescue` 处理体的新增 `pass` 或默认返回会触发复审；异常边界
  本身未新增时，依赖 diff 的有限上下文定位。超出上下文窗口的复杂跨行结构可能需要
  语义复审补充判断。
- Ruby `rescue` 只接受高置信度形式；非标准 DSL 或跨多行的 rescue 写法可能需要
  语义复审补充判断。
- hook 的 state 文件超过 48 小时会自动清理。

## 为什么不是只写 AGENTS.md

常驻规则负责价值排序，但不能保证每次都被执行。skill 提供完整复审方法，但仍可能
没有被调用。hook 把风险结构变成每个任务真实面对的完成条件，而独立上下文复审负责
避免实现者为自己的方案补理由。三层结合后，目标从“让测试变绿”变成“用证据证明这条
生产路径确实必要”。

## License

本项目采用 [MIT License](LICENSE)，Copyright © 2026 LuckyE。
