# Agent 验收测试：操作模板

这些模板是可复制的起点，不是通过标准。空白、`NOT_RUN`、`TO_FILL` 和 `null` 都表示尚未证明；不要用默认值填成 PASS。每次运行使用新的目录，保留失败、重试、变异和清理记录，不覆盖旧跑次。

## 推荐证据目录

```text
evidence/<RUN-ID>/
├── manifest.json                 # 候选、环境、数据、预算、层级和时间
├── plan.md                       # 范围、非目标、轨道、停止条件
├── cases/CASE-001.md             # 一用例一张卡
├── workers/<track>/report.md     # 并行执行者回执
├── trials/<CASE-ID>-<N>.json     # live/mock trial 结构化记录
├── raw/                          # 脱敏日志、请求/响应、SSE、节点/工具事件
├── states/                       # 数据库、文件、业务账本前后状态摘要
├── mutations/<name>/             # 变异差异、红态和恢复结果
├── defects/<DEFECT-ID>/          # 最小复现、修复前后证据
└── verdict.md                    # 汇总、限制、放行/拒绝决定
```

## 证据封存与收口

1. 把临时脚本、重试输出和未定稿文件写到证据目录外的 scratch 位置；不要让正在运行的生产者直接覆盖 `raw/`、`states/` 或红态文件。
2. 停止或确认所有测试进程、子代理和审查句柄已经不再写入；收集退出码、清理结果和外部副作用。
3. 写完最终结果、审查回执和清理记录后，按“相对路径 + 文件字节”计算 evidence digest；同时保存候选、技能、协议和审查摘要。
4. 计算摘要后只读复查目录的文件列表、摘要和修改时间。若又写入文件，旧摘要标记为 `SUPERSEDED`，重新计算并重新冻结，不能覆盖旧红证据。
5. 关闭前检查每条主张绑定了当前候选、用例、层级、原始证据和限制；不要把“摘要脚本退出 0”或“报告生成成功”当作产品通过。

## 冻结清单（manifest）

```text
run_id / owner / independent_reviewer / truth_owner:
started_at / timezone:
delivery_profile (LIMITED_INTERNAL | PREPROD | PRODUCTION):
must_ship_now / deferred / out_of_scope:
scope / non_goals / delivery_claims:
candidate_commit / dirty_diff_digest / untracked_source_digest:
skill_digest / review_digest / protocol_digest:
build_or_image_id / runtime_pid / listen_address / health_check:
database_schema / isolated_data_dir / browser_os:
model_configured / model_reported / provider / time_window:
prompt_skill_hook_tool_digest:
embedding_provider / model / dimension / index_version:
parser_ocr_dependency_digest:
dataset_version / truth_matrix_version / seed:
environment_levels / allowed_services / budget / stop_threshold:
missing_inputs / owner / unblock_condition:
```

## 用例卡

```text
case_id / title / source (bug|requirement|risk|incident):
priority / environment_level / capability_claim:
candidate_digest / run_id / trial_id:

Preconditions:
- identity, role, tenant/project/resource, session state:
- knowledge/files/model/tools/external ledger state:
- feature flags, limits, known restrictions:

Input:
- exact user text and request parameters:
- image/file digest and non-trusted content:
- idempotency key and business object (test-only):

Procedure:
1.
2.
3.

Expected user behavior and allowed answer set:
Required facts/fields/actions:
Forbidden facts/fields/actions:
Expected nodes/model/tool side effects:
Expected database/file/external state:
Independent oracle, truth source, and verifier:
Raw response/state captured before parsing:
Fixture validity and environment preflight:
Adversarial implementation this case must reject:

Observed response and post-state:
Command/procedure, exit code, timing, cost, retries:
Evidence paths and artifact digests:
Result: NOT_RUN | PASS | FAIL | BLOCKED | INCOMPLETE | N/A
Defect/blocker/N-A reason:
Cleanup/recovery:
Executor / reviewer / timestamp:
```

## 并行轨道回执

```text
track / owner / authorization / case range / read-write boundary:
worktree_or_candidate_copy / data_dir / database / port:
start_health_pid_port_check:
commands_and_entrypoints:
completed_cases / not_run_cases / blocked_cases:
exit_codes / artifact_paths / artifact_digests:
confirmed_failures / environment_failures / test_defects:
candidate_drift_before_after:
child_handle / timeout_or_retry_policy / producer_quiesced_before_digest:
cleanup_and_external_side_effects:
limitations / handoff_needed:
```

轨道不得共享会写入的数据库、文件、端口、外部对象或结果账本。协调者只汇总已落盘证据；“代理说完成”不是证据。容量不足、连接断开、进程退出和无账号要原样记录为 `NOT_RUN`/`BLOCKED`。

检查器回执还应说明：输入是否来自实现之外；期望是否来自外部真值；是否拒绝空值、错误类型、错误租户/版本/状态、缺失 ID 和不支持来源；是否核对实际副作用和后置读回；失败是产品违约、夹具/环境失败，还是证据不足。不要从观察到的答案生成 expected、完整正则或“通过”标签。

## Live trial JSON 最小 schema

```json
{
  "run_id": "RUN-YYYYMMDD-001",
  "case_id": "B-EXAMPLE",
  "trial_id": "B-EXAMPLE-01",
  "status": "NOT_RUN",
  "delivery_profile": "LIMITED_INTERNAL",
  "environment_level": "L2",
  "candidate_digest": "TO_FILL",
  "dataset_version": "TO_FILL",
  "truth_ids": [],
  "model_configured": "TO_FILL",
  "model_reported": null,
  "prompt_digest": "TO_FILL",
  "knowledge_version": "TO_FILL",
  "embedding_identity": "TO_FILL",
  "principal_fixture": "TEST_ONLY",
  "request_digest": "TO_FILL",
  "oracle_digest": "TO_FILL",
  "raw_response_digest": "TO_FILL",
  "fixture_validated": null,
  "trace_id": null,
  "observed_nodes": [],
  "observed_tool_calls": [],
  "retrieved_evidence_ids": [],
  "hard_boundary_passed": null,
  "task_success": null,
  "fact_correct_count": null,
  "fact_checked_count": null,
  "first_event_ms": null,
  "first_usable_answer_ms": null,
  "completion_ms": null,
  "model_fallback": null,
  "retry_count": null,
  "input_tokens": null,
  "output_tokens": null,
  "total_cost": null,
  "currency": "TO_FILL",
  "grader_version": "TO_FILL",
  "human_review": null,
  "evidence_paths": [],
  "defect_ids": []
}
```

## 缺陷与红绿证据

```text
defect_id / severity / affected users, entrypoints, data:
first_seen_candidate / run-case-trial / contract:
minimal reproduction and expected vs observed:
why this is a product defect rather than fixture/environment failure:

before command / exit code / logs / state readback:
root cause / direct caller / ownership:
smallest fix / changed files and digest:
same input after command / exit code / state readback:
related regression cases / independent review receipt:
counterfactual source or mutation (if fix came first):
limitations if red state could not be restored:
closure condition / owner / residual risk:
```

## 变异实验

```text
target_case / frozen_candidate_digest:
single mutation (e.g. remove tenant filter, skip verify, force success):
expected business assertion to fail:
command / exit code / actual failure reason:
did the test detect the intended bad behavior? yes/no:
original implementation restored and green result:
workspace/data integrity:
conclusion: REJECTED_BAD_IMPLEMENTATION | TEST_GAP | INCOMPLETE | NOT_RUN
```

## 最终决定

```text
candidate / run / scope / delivery_profile / reviewer:
P0/P1 open failures:
PASS / FAIL / BLOCKED / INCOMPLETE / NOT_RUN / N/A counts by capability:
required real-boundary evidence present:
quality, security, ledger, recovery, capacity and cost gates:
known limitations and accepted P2/P3 risks:
independent verifier result:
decision: LIMITED_GO | FULL_GO | NO_GO | INCOMPLETE
release owner / decision time / next action:
```

`FULL_GO` 只能在所有适用 P0/P1、正式承诺边界和独立证据满足冻结门槛后使用。`LIMITED_GO` 只允许用于显式限定的内部/预生产范围，并逐项列出 deferred 和 out-of-scope 能力；这些能力不能被对外文案暗示为已交付。缺环境或证据不足写 `INCOMPLETE`；确认的可达违约行为写 `NO_GO`。不要用测试数量、均分、历史跑次或“页面显示成功”抵销硬门禁。
