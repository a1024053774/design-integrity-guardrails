# Design Integrity Guardrails

面向 Codex、Claude Code 及其他兼容 Agent Skills 的工程完整性约束：一份常驻
`AGENTS.md`、一个聚焦结构风险的 design review skill、一个测试/验收完整性 skill，
以及在任务结束前触发路由的确定性 hook。

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

本仓库把约束分成四个互补部分：

1. **常驻规则**：`AGENTS.md` 定义根因范围、举证责任、比例原则和合法停止出口。
2. **确定性路由**：hook 对本轮新增的异常处理、fallback、疑似旁路 API 和显式验收
   表面做风险标记。
3. **结构复审**：`design-integrity-review` 在冻结候选版本上检查真实调用方、错误
   所有权、架构职责和更简单的修正方式。
4. **行为验收**：`behavioral-acceptance-review` 检查测试、eval、benchmark、
   autoresearch 和生成结果是否有独立输入与 oracle。

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
├── examples/
│   └── acceptance-auditor.toml.example
├── behavioral-acceptance-review/
│   └── SKILL.md
└── tests/
    └── test_design_integrity_gate.py
```

- `AGENTS.md`：可作为全局或项目级工程约定。
- `design-integrity-review/SKILL.md`：一次性、结构范围受限的独立复审和验收路由。
- `behavioral-acceptance-review/SKILL.md`：测试与行为验收的独立性检查单。
- `design_integrity.py`：扫描 Git diff 中新增的风险结构，并输出供复审使用的风险标记。
- `integrity_hook.py`：记录任务基线，在结束时比较新增风险和验收表面，并要求一次复审。
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

### 行为验收路由

为了避免普通单元测试改动触发昂贵的模型复审，hook 只自动识别显式高风险路径：
`autoresearch`、`eval`、`benchmark`、`harness`、`grader`、`golden`、`oracle`
以及带有 `_acceptance`、`_autoresearch`、`_benchmark`、`_eval`、`_golden`、
`_grader`、`_harness`、`_oracle` 后缀的文件名。命中后仍由 `design-integrity-review` 作为统一入口，
一次性路由到 `behavioral-acceptance-review` 和 `acceptance-auditor`；不会再启动第二个
reviewer。其他用户可观察行为可以显式调用该 skill。

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
                              冻结候选版本
                                      │
                                      ▼
                         一次结构或行为验收复审
```

扫描器使用有限的 diff 上下文来识别“已有异常边界中新增的处理体”：上下文只用于
定位边界，不会被当作本轮新增 finding。这样既能捕获把已有 `except/catch/rescue`
改成默认返回或 `pass` 的漏报，也不会因为旧代码本身存在异常处理而重复报警。Ruby
`rescue` 仅匹配高置信度子句和后缀代码形态，普通字符串或散文中的单词不应触发。

基线初始化使用文件锁串行化，避免并行工具调用把新修改覆盖进“旧状态”。基线还会
保存开始时的 Git revision，因此本轮中途提交不会让完成门禁失去证据。

同一回答中的多次编辑或提交只要属于同一计划批次，就合并为一个 review epoch。
hook 使用宿主提供的 `turn_id` 作为回答边界：已确认的批次在下一条用户请求中建立
新的基线并重置预算，未完成的 pending review 则保留，避免通过换 turn 绕过门禁。
只有出现新的风险签名或新的验收路径才会开启下一 epoch；同一范围不会因行号、提交
数量或测试数量变化而重复启动。自动门禁最多处理 2 个 epoch（初审加一次定向复审）；超出后返回
`INCOMPLETE` 提示，不会轮询、关闭后重启或并行创建 reviewer。

## 当前版本结构

本版本不是把“请写好代码”再重复一遍，而是把完成条件拆成互相制约的几层：

~~~text
常驻决策规则
AGENTS.md / CLAUDE.md
        │
        ▼
确定性扫描与生命周期状态
design_integrity.py → integrity_hook.py
        │
        ▼
统一入口（冻结候选版本）
design-integrity-review
        ├── 结构风险
        │     └── 一次有界的 fresh、read-only review
        └── 验收表面
              └── behavioral-acceptance-review
                    └── acceptance-auditor
                        yunpai/gpt-5.6-luna · max · read-only
        │
        ▼
外部行为证据
黑盒输入 / 独立 oracle / CI / 真实公共入口
~~~

- `AGENTS.md` 只负责价值排序、举证责任、比例原则和“正确修复超出范围时停下上报”。
- `design_integrity.py` 只做风险结构识别和验收路径分类，不把命中直接判成缺陷。
- `integrity_hook.py` 记录 Git 基线，按 `turn_id` 管理 review epoch，并把同一回答里的
  多次编辑合并为一个候选版本。
- `design-integrity-review` 是唯一的复审入口：结构风险和行为验收不再各自启动一套
  reviewer。
- `behavioral-acceptance-review` 只判断输入、oracle、公共入口和反例是否独立；没有
  足够证据时必须返回 `INCOMPLETE`，不能用绿色测试猜成 `PASS`。
- `acceptance-auditor` 的模型路由是本机配置，不写入仓库凭据；本地实例固定使用
  `yunpai/gpt-5.6-luna` 和 `max`，不切换官方模型。

这套结构仍然需要项目自己的黑盒 harness、CI 或真实入口测试。reviewer 负责审查证据
是否可信，不负责凭空创造 oracle，也不替代领域验收。

在本次实例里，被验收应用本身也保持单一权威路径：统筹 Agent、管理后台和受控客服
测试共用同一个 FastAPI、SQLite、租户和领域服务；持久会话是唯一会话语义，旧入口只
做委托兼容，不另起一套状态或 mock。工具结果先经过确定性事实映射和安全呈现层，最后
才交给模型生成回答或页面展示。这样 reviewer 检查的是同一条可追踪生产路径，而不是
几个互相独立的演示分支。

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
ln -s "$PWD/behavioral-acceptance-review" ~/.agents/skills/behavioral-acceptance-review
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
ln -s "$PWD/behavioral-acceptance-review" ~/.claude/skills/behavioral-acceptance-review
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

### Acceptance auditor（Codex）

验收 skill 使用一个职责型自定义 Agent，而不是把模型名称写进流程：

```ini
name = "acceptance-auditor"
model = "yunpai/gpt-5.6-luna"
model_reasoning_effort = "max"
sandbox_mode = "read-only"
```

可复制仓库中的 [examples/acceptance-auditor.toml.example](examples/acceptance-auditor.toml.example)
到 `~/.codex/agents/acceptance-auditor.toml`。该文件是本地模型路由配置，不会把公司
API 地址或凭据提交到仓库。主 Agent 在冻结候选版本后委派一次该角色；hook 本身只负责
提示和去重，不直接启动模型。

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
  进入复审，但不替代人的最终判断。结构复审和行为验收共用 review epoch，不会
  为同一候选版本各启动一次。
- 行为验收要求独立输入和 oracle；只有固定样例、绿色测试或实现者解释时，结果应为
  `INCOMPLETE`，而不是 `PASS`。
- hook 只自动路由显式验收目录/文件名；普通单元测试改动仍由 evidence-first testing
  和项目自己的确定性测试覆盖。
- reviewer 必须在稳定的 commit、patch 或只读 worktree 上运行；实现者在复审期间
  不应继续编辑、提交或部署。
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

## 实测案例：yunpai-ecommerce-agent-pr9

本节记录一次真实的多模态统筹 Agent 集成、部署和验收会话。原始导出文件不随本仓库
发布；这里只保留可复核的过程结论，不包含 Cookie、Token、访问链接或其他凭据。它是
流程压力测试，不是模型能力 benchmark：导出会话还包含部署、浏览器和文档工作，所以
总时长不能全部归因于 reviewer。

### 过程规模：旧流程为什么会变重

| 项目 | 导出中观察到的结果 |
| --- | --- |
| 完整导出时间 | 2026-08-28 03:59:40 UTC → 2026-08-29 03:38:23 UTC（约 23 小时 39 分） |
| 主要实现/公网验收阶段 | 截至 2026-08-28 18:19:36 UTC，约 14 小时 20 分 |
| reviewer 编排（粗统计） | 约 11 次 spawn、20 个不同子 Agent 通知、60 次 wait、12 次 close |
| 其他工具记录（粗统计） | 约 958 次 shell、157 次 pytest、231 次 SSH；其中包含部署和排障 |

问题不是 reviewer 完全无效，而是旧流程把结构复审、业务正确性、事实校验、测试
oracle 和公网 QA 混在一起；主 Agent 还会在 reviewer 运行期间继续改版本，于是同一
任务不断出现移动快照、超时、关闭和重新 spawn。

### 首轮发现与修复

初始回归曾达到 `1468 passed, 1 skipped`，但独立结构复审仍确认了 4 个真实可达问题，
其中 3 个直接影响公网安全或可靠性：

1. 全部复合读取失败时，空回答被持久化成“成功完成”；下一轮读取历史会违反非空契约并返回 500。
2. 读取任务异常把内部错误码和字段名直接暴露给 SSE 和最终响应。
3. 会话标题写入/返回没有统一脱敏，手机号等信息可能进入页面。
4. 旧的无状态工作台流接口绕过持久会话契约，形成第二套生产语义。

修复遵循“先红后绿、改根因层”的顺序：

- 失败完成统一映射为 `incomplete`，提供非空的用户安全消息，并禁止空历史进入下一轮；
- 在服务边界产品化异常摘要，SSE 和最终响应共用脱敏出口；标题脱敏放在 API 边界，而不是依赖调用方自觉；
- 保留已有兼容入口，但让它委托同一套持久会话实现并忽略客户端伪造历史，不再维护第二套行为；
- 每一项先用真实调用路径或反例写红灯，再跑定向回归和独立只读复审。

### 后续黑盒验收抓到的漏项

第一次全量变绿并不等于完成。用真实入口、不同输入和持久化记录继续验收后，又发现并
修复了这些跨层问题：

- `no_data` 被当成成功信号、复杂否定句被误判为肯定状态、单步和复合 SSE 状态漂移；
- 模型 objective 作为事实标题的 fallback、跨仓库实体绑定和“其中”等单字误判；
- 带空格的风险等级正则漏匹配、营销字段打平、流量实验数值/方向/区间映射不完整；
- 下一轮没有恢复上一张图片的脱敏视觉观察，模型被历史业务查询带偏；
- 公网工作台历史会话横向滚动容器被内容撑开，右侧会话卡片不可见。

每个漏项都先被真实输入或失败测试复现，再在权威数据/职责所在层修复；没有通过放宽
校验器、增加猜测性 fallback 或复制一套旁路实现来“让测试通过”。

### 验证结果

| 阶段 | 结果 |
| --- | --- |
| 初始整合 | `1468 passed, 1 skipped`，另有 1 个应按增量不变量修正的标签快照失败 |
| 重点 hardening 回归 | 会话/持久化 81 项、多模态/管理页 39 项、M9 合同 18 项（1 项既有跳过）通过 |
| 最终业务版本全量 | `1511 passed, 1 skipped`；`compileall`、`git diff --check`、项目台账校验通过 |
| 最新滚动修复 | 红态定点测试 `1 failed` → 修复后 `20 passed`；相关回归 `79 passed` |
| 真实入口 | `/health`、`/ready` 返回 200；代表性查询达到 `verified_final`；三个页面 console error/warning 为 0 |

CSS 滚动修复只改变布局和对应回归，因此没有把此前的 `1511 passed, 1 skipped` 冒充成该
补丁之后重新跑出的全量结果；README 明确区分全量基线和增量验证。

### 这次实例如何改变本仓库

- 绿色测试是证据，不是 oracle；实现 Agent 新增或修改的测试默认不能单独证明行为正确。
- 结构复审与行为验收分开，但由 `design-integrity-review` 统一路由；同一候选版本只选一条 reviewer 路径。
- reviewer 必须看到冻结快照；快照移动、没有独立输入/oracle 或 reviewer 无响应时报告 `INCOMPLETE`，不靠重试制造 `PASS`。
- 同一回答的多次编辑合并为一个 epoch；每个用户 turn 最多一次初审和一次定向复审。
- 行为验收只在显式 `autoresearch`/`eval`/`benchmark`/`harness` 等表面自动路由，普通单元测试不会触发昂贵的模型审查。

这意味着本版本的目标不是“让 Agent 多审几遍”，而是让它在完成前必须面对一个较小、
稳定、可举证的验收函数；真正的黑盒输入和独立 oracle 仍应由项目 harness、CI 或真实
公共入口提供。

## 为什么不是只写 AGENTS.md

常驻规则负责价值排序，但不能保证每次都被执行。skill 提供完整复审方法，但仍可能
没有被调用。hook 把风险结构变成每个任务真实面对的完成条件；`design-integrity-review`
负责结构路由，`behavioral-acceptance-review` 负责独立输入和 oracle。两类审查共享
review epoch，目标从“让测试变绿”变成“用证据证明这条生产路径确实必要”，同时避免
同一候选版本反复启动 reviewer。

## License

本项目采用 [MIT License](LICENSE)，Copyright © 2026 LuckyE。
