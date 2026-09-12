# Agent 验收操作模板

这些模板只提供记录结构，不替项目决定适用性、阈值或发布范围。先完成 [SKILL.md 的适用性画像](../SKILL.md)，再复制核心字段并按 `yes` 的能力轴加入扩展。没有启用的能力要写 `N/A` 及理由，适用但尚未验证的字段保持缺失并标为 `INCOMPLETE`；不要用空白、`TO_FILL` 或 `null` 伪装成证据。

## 证据目录

```text
<evidence-root>/
  manifest.yaml                 # 候选、协议、环境和适用性画像
  plan.md                       # 目标、非目标、门槛、未知和停止条件
  applicability.yaml            # 每个能力轴的 yes/no/N/A 理由
  cases/                        # 用例卡、输入和独立 oracle 引用
  tracks/                       # 并行轨道回执（如有）
  raw/                          # 原始请求、响应、事件、命令输出和退出码
  trials/                       # 每次 live trial 的结构化记录
  defects/                      # 红态、修复、复测和变异记录
  reviews/                      # fresh-context 只读复核回执
  states/                       # 项目声明的权威状态读回（若有）
  digests/                      # 生产者停止写入后计算的摘要
  verdict.md                    # 用例、能力、发布三层结论
```

目录一旦封存，任何新增文件或修改都要重新计算摘要并把旧摘要标为 `SUPERSEDED`；不要覆盖原始红证据。

## 适用性画像

```yaml
profile_version: 1
axes:
  orchestration_state:
    status: yes | no
    reason: ""
  streaming_async:
    status: yes | no
    reason: ""
  retrieval_knowledge:
    status: yes | no
    reason: ""
  identity_scope:
    status: yes | no
    reason: ""
  user_interface:
    status: yes | no
    reason: ""
  files_media:
    status: yes | no
    reason: ""
  external_side_effects:
    status: yes | no
    reason: ""
  operations_deployment:
    status: yes | no
    reason: ""
delivery:
  must_ship_now: []
  deferred:
    - capability: ""
      owner: ""
      review_or_unblock: ""
  out_of_scope: []
```

`status: no` 只表示该能力在本轮没有承诺；如果能力存在但没有足够证据，保留 `status: yes`，在用例或能力状态中记 `INCOMPLETE`。

## manifest.yaml

```yaml
run_id: ""
created_at_utc: ""
delivery_profile: internal | preproduction | production_canary | production
product:
  candidate_digest: ""
  source_or_build: ""
  skill_digest: ""
  protocol_digest: ""
  dataset_digest: ""
runtime:
  executor: ""
  model_provider: ""
  model: ""
  dependency_lock_digest: ""
  process_or_job_id: ""       # 若有
  listen_or_entrypoint: ""    # 若有
  health_check: ""             # 若有
inputs:
  identity_or_test_principal: ""
  data_scope: ""
  seed: ""
  time_window_utc: ""
boundaries:
  allowed_services: []
  allowed_write_targets: []
  credential_source: "redacted reference"
  budget: ""
  stop_thresholds: []
  cleanup: ""
applicability_ref: "applicability.yaml"
```

仅记录验收需要的白名单和摘要；不要把密钥、隐藏推理或不必要的个人资料放进 manifest。进程、监听地址和健康检查只在项目确实有服务入口时填写。

## 用例卡（cases/<case-id>.md）

```markdown
# <case-id> <短标题>

- 能力：
- 适用轴：
- 目标层级：L0/L1/L2/L3/L4/L5
- 前置状态：身份、权限、数据、配置、依赖、时间和外部对象
- 精确输入：固定输入或输入文件摘要；不要从实际答案生成 expected
- 真实入口：网页、API、CLI、批处理、事件或其他已声明入口
- 允许行为：
- 禁止行为：
- 预期后置状态：仅写项目实际声明的状态来源；没有则写 N/A
- 独立 oracle：人工真值、公开合同、协议 schema、状态不变量、权限矩阵或外部只读记录
- 后置核对：用户结果、持久化、来源、事件、工具动作、界面和清理（按适用性选择）
- 证据路径：原始请求/响应、日志、状态读回、截图或命令输出
- 失败语义：产品违约 / 无效夹具 / 环境阻断 / 证据不足 / 未执行
- 退出条件：
- 清理：
- 结果：PASS | FAIL | BLOCKED | INCOMPLETE | NOT_RUN | N/A
- 缺陷 ID：
```

## 并行轨道回执（tracks/<track-id>.yaml）

```yaml
track_id: ""
authorized_by: ""
scope: []
write_boundary: read_only | isolated_copy | named_external_sandbox
candidate_digest: ""
data_and_port_boundary: ""
entrypoint: ""
executor: ""
start_utc: ""
stop_condition: ""
timeout:
  seconds: 0
  observed_status: running | completed | needs_attention | unknown
  follow_up_evidence: ""
quiescent_at_utc: ""
evidence_digest: ""
supersedes: ""
result: PASS | FAIL | BLOCKED | INCOMPLETE | NOT_RUN
```

共享写入、外部对象和同一端口必须串行或明确隔离。超时只表示观察窗口结束；要查询同一句柄并确认状态，不能因超时自动重启、关闭或重复派发。

## trial.json

以下是跨架构的最小字段；原始响应、事件和退出码先落盘，再解析摘要。

```json
{
  "run_id": "",
  "case_id": "",
  "trial_id": "",
  "status": "PASS|FAIL|BLOCKED|INCOMPLETE|NOT_RUN|N/A",
  "delivery_profile": "internal|preproduction|production_canary|production",
  "environment": {"candidate_digest": "", "protocol_digest": "", "dataset_digest": "", "executor": ""},
  "request": {"input_digest": "", "entrypoint": "", "identity_ref": "", "scope_ref": ""},
  "oracle": {"source": "", "version": "", "digest": ""},
  "raw_evidence_digest": "",
  "fixture_validated": true,
  "input_changed": true,
  "control_or_counterfactual": {"kind": "", "reference": ""},
  "hard_boundary": {"violations": [], "authorized": true},
  "task_result": {"success": false, "first_completion": false, "consistent": false},
  "post_state": {"observed": "", "authority_ref": "", "readback_digest": ""},
  "timing_ms": 0,
  "retries": 0,
  "cost_status": "measured|estimated|unknown|N/A",
  "human_review": "",
  "defect_ids": [],
  "evidence_paths": []
}
```

`oracle.source` 必须指向被测实现之外的事实。`fixture_validated: false`、缺失读回或输入未真正影响执行时，不能把结构化输出记作产品通过。

## 按适用性加入的 trial 扩展

这些组是可选的示例，只有画像为 `yes` 才加入；整组不适用时省略并在画像写理由。

```json
{
  "extensions": {
    "orchestration_state": {"steps": [], "transitions": [], "replay_key": "", "recovery": ""},
    "streaming_async": {"events": [], "ordering": "", "termination": "", "reconnect": ""},
    "retrieval_knowledge": {"source_refs": [], "version_refs": [], "scope": "", "retrieval_result": ""},
    "identity_scope": {"principal_ref": "", "authorization_decision": "", "isolation_check": "", "revocation": ""},
    "user_interface": {"journey_steps": [], "visible_state": "", "backend_state_ref": ""},
    "files_media": {"media_type": "", "source_digest": "", "parser": "", "content_check": "", "failure_class": ""},
    "external_side_effects": {"action": "", "target_ref": "", "idempotency_key": "", "authority_readback": "", "delivery_state": ""},
    "operations_deployment": {"environment": "", "alerts": [], "recovery": "", "rollback": ""}
  }
}
```

字段名只是稳定的记录组名，不要求项目拥有同名 API 或数据库列。项目可以在组内使用自己的字段，但必须保留入口、独立 oracle、后置核对和失败语义。

## 缺陷与反事实记录（defects/<id>.md）

```markdown
# <defect-id> <标题>

- 触发用例与入口：
- 候选摘要 / 环境摘要：
- 最小输入与前置状态：
- 独立 oracle：
- 修复前红态：命令、退出码、原始证据路径和 digest
- 根因层：产品 / 测试 / 夹具 / 环境 / 证据流程
- 单根因变异或父版本反事实：
- 最小修复：
- 同入口同 oracle 复测：
- 受影响的最小回归：
- 未恢复的反事实或缺口：
- 结果：PASS | FAIL | INCOMPLETE | BLOCKED
```

如果修复先于红态，明确写“修复后通过但回归证明不完整”，不要删除历史失败或把变异失败冒充原始产品红态。

## 最终判定（verdict.md）

```markdown
# Agent 验收判定 <run_id>

## 范围
- must_ship_now：
- deferred（owner / review_or_unblock）：
- out_of_scope：
- 交付层级与环境：

## 用例结果
| case_id | status | layer | evidence | defect |
| --- | --- | --- | --- | --- |

## 能力状态
| capability | complete / named_slice / not_delivered | supporting_cases | gaps |
| --- | --- | --- | --- |

## 独立复核
- verifier_context：fresh / not_fresh
- read_only：yes / no
- review_receipt：
- receipt_digest：

## 发布决定
- decision：LIMITED_GO / FULL_GO / NO_GO / INCOMPLETE
- blocking P0/P1：
- applicable gates passed：
- N/A gates and reasons：
- unresolved unknowns：
- rollback / stop condition：
- next smallest verification：
```

`N/A` 只用于适用性画像确认的能力；适用但未测、证据过期、反事实缺失或只完成命名切片都不能写成 `N/A`。发布门禁只检查本轮承诺范围和适用门禁；没有外部写入、权威记录、流式或 UI 的项目不要人为添加对应条件。
