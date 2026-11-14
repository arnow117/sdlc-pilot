# Offline vibe-test workflow

The tools use only the Python standard library and make no model, MCP, network,
service or lifecycle calls. The default example and all test receipts are
**synthetic**: model runs are zero. `plan`, `prepare`, `collect`, `report`,
`judge-prepare`, `judge-collect`, `inspect-tree`, `control-handoff` and `compare`
provide an offline handoff and replay mechanism; they do not authenticate a
receipt, user approval, model routing, tool access, permissions or isolation.
CLI live preparation and live judge preparation return `ENV_BLOCKED` without an
in-process host callback. The controlled Python API can process host-attested
evidence; the caller must authenticate that evidence. Live AC01/04 and actual
host control remain NOT_RUN. Do not execute untrusted model code on this host.

## Offline example

Choose a new output root. All paths shown below are relative to the artifact
root; existing output paths are rejected.

```sh
OUTPUT_ROOT="$(python3 -c 'import tempfile; from pathlib import Path; print(Path(tempfile.mkdtemp(prefix="sdlc-vibe-")).resolve())')"
python3 -B scripts/test_vibe_test.py
python3 -B scripts/vibe_test.py oracle --battery examples/vibe-battery-v1/battery.json --out "$OUTPUT_ROOT/oracle"
python3 -B scripts/vibe_test.py plan --config examples/vibe-plan-v1.json --out "$OUTPUT_ROOT/plan"
python3 -B scripts/vibe_test.py prepare --plan "$OUTPUT_ROOT/plan/plan.json" --trial-id B01-r01-control --out "$OUTPUT_ROOT/prepared"
python3 -B scripts/vibe_test.py collect --results examples/vibe-battery-v1/private/report-cases/complete.json --out "$OUTPUT_ROOT/collection"
python3 -B scripts/vibe_test.py report --results "$OUTPUT_ROOT/collection/results.json" --out "$OUTPUT_ROOT/report"
```

The last two commands retain the T1 synthetic collect/report interface. For the
plan-aware interface, use the arguments below. `--help` gives the exact CLI.
Input and output must not overlap. Parent traversal, unsafe IDs, symlinks,
non-regular input files and existing output paths are rejected. Plan and oracle
check raw-byte SHA-256 and file modes; experiment hashes do not use context-v1.

## Plan and handoff

`plan --config PATH --out DIR` accepts a JSON object with `kind` (`synthetic` or
`live`), `battery`, `documents`, `repetitions`, `budget`, `target`, `permissions`,
`limits`, `approval_status`, optional `approval_ref`, and optional `required_dimensions` (a mapping from task ID to a nonempty list of required boolean checker dimensions). Missing required dimension declarations or values make quality evidence incomplete; the sample's `probe` dimension is synthetic only. Paths are absolute or
relative to the config file, without `..`. Each document must have a distinct
filename. `target` contains `providerInstanceId`, `model` and `options`; limits
contain integer `seconds` and `output_tokens`. Optional `judge_limits` defaults
to 900 seconds and 16000 output tokens; optional `wall_seconds` defaults to 12600.
No hard-limit enforcement by the host is claimed.

The sample freezes two tasks, two arms, three repetitions, 12 producer slots,
one judge slot and concurrency one. The budget must equal the planned producer
slots, with at most 12 producer slots, one judge and concurrency one. Ordering
alternates arms by repetition. Prompt, public tree, checker, requested route,
permissions and limits are shared for each pair; only treatment receives the
selected documents. `plan.json` retains source locations and raw-byte hashes,
configuration hash, asset tree, documents, statistical method and all slots.
It is not an authorization record.

`prepare --plan PATH --trial-id ID --out DIR` creates a public-only test copy and
`payload.json`. Synthetic approval states are test fixtures: `approved` permits
only a non-launchable synthetic copy; `unapproved` and `revoked` refuse it.
Changing frozen inputs requires a new plan. A live plan is rejected before copying
unless controlled host code supplies a callback that verifies the required facts. The
approval reference is a locator only. The host must independently verify actual
batch approval, load, visibility, write permissions, network and filesystem
isolation, and the selected model before any real submission. `timeoutMs` is a
wait timeout, not a hard execution limit; the host's time, output-token and wall
clock enforcement capabilities remain unknown. No command automatically retries,
expands a budget, launches, cancels or polls a task.

## Results, judge and comparison

`collect --plan PATH --trial-id ID --receipt PATH --submission DIR --out DIR`
reads the submission tree and records file hashes and modes, never executing it.
The receipt is preserved verbatim and separately from the requested target. The
fields `taskId`, `runId`, `threadId`, `providerInstanceId`, `model`, `options`,
`executedModel`, `start`, `end`, `status`, `dimensions`, `integrity`,
`plan_sha256` and `checker_sha256` are preserved when supplied. An absent
`executedModel` remains null/unknown. Contradictory plan or checker hashes are
rejected; missing bindings are reported. These fields are untrusted data until
the main agent checks native records. Synthetic records produce only synthetic
quality outcomes. Live quality requires an independent isolated scorer supplied
through the controlled callback; no JSON flag can make itself live evidence.

`report --plan PATH --results DIR --out DIR [--strict]` reads collected result
subdirectories, detects duplicate trial/run/task or reused thread, checks stored
receipts, reports changed submissions and compares actual reported route fields.
Missing native metadata, failed facilities, skipped checks, missing trials and
missing judge are explicit. Timeout with otherwise valid conditions stays in the
quality denominator as a failure. Any observed severe integrity violation stops
the entire batch comparison; a partially complete batch does not get a difference
interval. A synthetic report is always incomplete as live evidence, so `--strict`
returns nonzero regardless of which arm wins or how many synthetic tasks pass.
Individual task/arm rates use Wilson 95%; differences use Newcombe independent
proportions, z=1.959963984540054, without continuity correction. Small samples,
context independence, stable conditions, cache and time variation limit inference.
An interval containing zero is described as “区间含 0，未观察到显著差异”.

`judge-prepare --plan PATH --results DIR --out DIR` generates one shuffled,
anonymous synthetic `payload.json`, containing public contracts, raw text
artifacts and deterministic evidence. It refuses identifying arm labels in
artifacts and refuses a batch above 262144 bytes instead of splitting it. The
adjacent `private-map.json` is host-only: send only `payload.json` to an authorized
judge. `judge-collect --payload PATH --ratings PATH --out DIR` accepts synthetic
ratings of 0/1/2 for correctness, readability and protocol with location evidence.
It preserves deterministic status even when a judge gives a higher score.
Optional `report --judge-result ... --judge-map ... --judge-payload ...` binds a
synthetic replay to its plan; it still does not establish independent live judging.

`inspect-tree --baseline DIR --submission DIR --access-log PATH [--allow PATH]
--out DIR` compares local trees and lists observed forbidden access records. The
access log and inspection are unauthenticated: absence of events never proves no
access or isolation. `control-handoff --plan PATH --results DIR --out DIR` lists
unverified observed IDs without recommending cancellation. The controlled Python
API with host context uses the caller-verified full attempt list, including
uncollected attempts, and suggests only identified in-batch IDs for investigation.
The host must confirm ownership and status before cancellation. Unknown outcomes
must not be resubmitted automatically.

`compare --before DIR --after DIR --out DIR [--strict]` compares report inputs,
conditions, routes and document hashes. It reports “基线缺失”, changed conditions,
unknown/changed actual routes and incomplete batches as reasons. The displayed
CLI comparison is synthetic/incomplete and cannot attribute a real effect to
documents. The Python API can attribute only when the host independently
authenticates both complete reports, their frozen snapshots and comparable
conditions. Each batch has its own budget; the tool does not run either batch or
call it a regression curve.

## Battery and source scope

The trusted offline oracle imports the checkers supplied by its battery and runs
only bundled references and negatives. Never use it to run model submissions.
The frozen battery manifest hashes all original asset bytes except the manifest
and provenance themselves, which are hashed externally. Public and private trees
are separate. B02's public schema defines byte-change booleans and aliases,
ordered ID observations and location fields; no standard findings are included in
its public tree. Provenance records source G and its crop mapping. The example
target documents are raw snapshots of published E, with separate source and hash
records in `examples/vibe-documents-v1/provenance.json`.


## Controlled host API

This is an in-process interface for the authorized main agent. It is not a CLI
option and no JSON field constructs a `HostContext`. The host must authenticate
native sources and implement the callback; the class itself does not authenticate
anything. The executable contract test below uses stub evidence and makes **zero
model or MCP calls**:

```sh
python3 -B scripts/test_vibe_host.py
```

A host imports `vibe_test` and `vibe_host`, creates
`HostContext(verifier)`, then passes `host_context=host` to `prepare`,
`collect_trial`, `judge_prepare`, `judge_collect`, `report_plan` and `compare`.
The callback receives `(stage, facts)` and returns caller-verified evidence for
that stage. The contract test demonstrates the exact call sequence, native T3
field aliases, independent scoring, judge binding, strict report and compare.
Its simulated reports are temporary fixtures, not real experiment evidence.

For each stage the callback must bind `plan_sha256`, exact `approved_trials` and
`approved_judge`, current approval and revocation, oracle battery/hash/result,
isolation, full workspace and access evidence. It also binds the requested target,
permissions, limits and a policy evidence hash; limit enforcement is either
`enforced` or `not-enforced-disclosed`. It supplies the complete native attempt list, including submitted-but-uncollected and unknown attempts. Each
attempt carries trial ID or judge role and native task/run/thread IDs. Duplicate
IDs, reused threads, exhausted budgets and unresolved in-flight attempts are
rejected; no retry is scheduled. Cancellation remains a host decision limited to
independently verified task IDs.

For `collect`, the callback verifies `native_receipt_sha256` and returns the
independent isolated `scorer` result bound to plan, trial, checker and submission
tree hashes, including an evidence hash and reference, independent scorer session ID,
dimensions, quality status and integrity. The scorer is external; this script never executes the submission.
The adapter accepts `childRunId`/`runId`, `childThreadId`/`threadId` and options
objects or arrays of name/value entries. Raw native data is retained. Null
`executedModel` remains unknown; native `completed` does not imply quality pass.

For `judge_collect`, the callback verifies the independent judge's native receipt,
actual route, payload hash and ratings hash; its session must differ from every
producer. Ratings cannot change deterministic quality. For `compare`, the
callback separately verifies the exact report hash and completeness for each
plan. Strict report or compare can succeed with quality failures/timeouts only
when every required caller-attested binding is complete. JSON report flags alone
never provide this assurance. Plans store raw document bytes as base64 together
with their SHA-256, so later changes to the source path do not replace the recorded
before snapshot. The host remains responsible for preserving and authenticating
all other referenced raw evidence.


## Acceptance coverage

- **AC01 — 对照与辅助评分：** 冻结两臂条件、保留原始结果与逐任务区间，并在实际能力和授权成立时由独立 judge 补充评价。真实完整对照尚未执行。
- **AC02 — 判定器自检：** 无模型运行的 oracle 必须让参考解通过、已知负例在预期维度失败；故意放宽的判定器必须使自检失败。
- **AC03 — 统计与缺口：** 分别报告各任务和臂的分母、失败归因及预定区间；缺证据不能算通过，区间含 0 时声明未观察到显著差异及小样本限制。
- **AC04 — 改动前后比较：** 仅在准确 before、after 与条件可比时比较；缺基线或 checker、模型等条件变化时说明原因，不归因文档。真实重跑尚未执行。
- **AC05 — 预算与停止：** 实际批次由主 Agent 先核实能力、负载和该批授权，在批准的次数、并发和停止条件内控制；脚本本身不启动或取消模型任务。

这些是使用者核对证据的摘要；被跟踪工作仍以其产品上下文中的验收条件为权威。离线 stub、合成报告和 API 的存在不认证当前宿主的访问隔离或真实模型路由。
