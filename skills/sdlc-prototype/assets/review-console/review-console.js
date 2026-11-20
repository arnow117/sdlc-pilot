(function attachPrototypeReviewConsole(globalScope, factory) {
  const reviewConsole = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = reviewConsole;
  }

  globalScope.PrototypeReviewConsole = reviewConsole;
})(typeof globalThis !== "undefined" ? globalThis : this, function createReviewConsoleFactory() {
  "use strict";

  const STEP_KINDS = Object.freeze(["prepare", "inject", "act", "observe"]);

  const STEP_KIND_LABELS = Object.freeze({
    prepare: "准备",
    inject: "状态注入",
    act: "产品操作",
    observe: "观察",
  });

  const ENTRY_KINDS = Object.freeze(["normal", "review", "injected"]);

  const ENTRY_KIND_LABELS = Object.freeze({
    normal: "普通用户入口",
    review: "审阅直达",
    injected: "注入步骤",
  });

  const CHECK_COMPARATORS = Object.freeze(["equals", "contains"]);

  const STEP_STATUSES = Object.freeze({
    pending: "pending",
    waiting: "waiting",
    done: "done",
    rejected: "rejected",
    failed: "failed",
    skipped: "skipped",
  });

  const PHASES = Object.freeze({
    idle: "idle",
    running: "running",
    failed: "failed",
    complete: "complete",
  });

  const DEFAULT_SETTLE_TIMEOUT_MS = 3000;
  const DEFAULT_POLL_INTERVAL_MS = 20;

  function cloneJson(value) {
    return value === undefined ? undefined : JSON.parse(JSON.stringify(value));
  }

  // The adapter contract is synchronous. An asynchronous operation must be
  // reported as {ok:true, pending:true} and settled through read/check instead.
  function requireSynchronous(value, name) {
    if (value && typeof value.then === "function") {
      Promise.resolve(value).catch(function ignoreUnsupportedRejection() {});
      throw new TypeError(`${name} 必须同步返回；异步结果应使用 pending 与检查。`);
    }
    return value;
  }

  function requireActionResult(value) {
    const result = requireSynchronous(value, "adapter.call()");
    if (!result || typeof result !== "object") {
      throw new TypeError("adapter.call() 必须返回包含布尔值 ok 的结果。");
    }
    // Read untrusted result fields once, inside the caller's failure boundary.
    const ok = result.ok;
    if (typeof ok !== "boolean") {
      throw new TypeError("adapter.call() 必须返回包含布尔值 ok 的结果。");
    }
    if (ok) {
      return { ok: true, pending: result.pending === true };
    }

    // Capture evidence once. Diagnostics use only these strings: coercing the
    // product's error object can execute product code and change later steps.
    const evidence = readErrorEvidence(result.error);
    return { ok: false, evidence: evidence, diagnostic: rejectionText(evidence) };
  }

  function readErrorField(error, name) {
    try {
      const value = error[name];
      return typeof value === "string" ? value : null;
    } catch (_error) {
      return null;
    }
  }

  function stringifyError(error) {
    if (!error) {
      return "操作未返回结果。";
    }
    // Object coercion can call adapter code; display a stable fallback instead.
    if (typeof error === "object" || typeof error === "function") {
      return "无法读取错误信息。";
    }
    try {
      const text = String(error);
      return text.trim() ? text : "无法读取错误信息。";
    } catch (_error) {
      return "无法读取错误信息。";
    }
  }

  function readErrorParts(error) {
    if (!error) {
      return { code: null, message: "操作未返回结果。" };
    }

    if (typeof error === "string") {
      return { code: null, message: error.trim() ? error : "无法读取错误信息。" };
    }

    const code = readErrorField(error, "code");
    const message = readErrorField(error, "message");
    if (message && message.trim()) {
      return { code: code, message: message };
    }
    if (code && code.trim()) {
      return { code: code, message: code };
    }

    return { code: code, message: stringifyError(error) };
  }

  function isPlainRecord(value) {
    return value !== null && typeof value === "object" && !Array.isArray(value);
  }

  // The adapter reports success explicitly. Anything else — false, {ok:false},
  // {pending:true}, a missing value, a non-object — is not a clean success.
  function requireAdapterSuccess(value, name) {
    const outcome = requireSynchronous(value, name);

    if (!isPlainRecord(outcome)) {
      throw new TypeError(`${name} 必须返回 {ok:true} 表示成功。`);
    }

    // A pending result is not a success, even when it also carries ok:true.
    if (outcome.pending === true) {
      throw new Error(`${name} 尚未完成，不能继续。`);
    }

    if (outcome.ok === true) {
      return outcome;
    }

    if (outcome.ok === false) {
      throw new Error(readErrorParts(outcome.error).message);
    }

    throw new TypeError(`${name} 必须返回 {ok:true} 表示成功。`);
  }

  // A rejection only counts when the product supplied evidence for it. The
  // controller's own fallback wording is never used as the rejection reason.
  function readErrorEvidence(error) {
    if (error === undefined || error === null) {
      return null;
    }

    if (typeof error === "string") {
      const text = error.trim();
      return text ? { code: null, message: text } : null;
    }

    if (typeof error !== "object") {
      return null;
    }

    const rawCode = readErrorField(error, "code");
    const rawMessage = readErrorField(error, "message");
    const code = rawCode && rawCode.trim() ? rawCode.trim() : null;
    const message = rawMessage && rawMessage.trim() ? rawMessage.trim() : null;

    if (!code && !message) {
      return null;
    }

    // The message stays null when the product did not give one. A fallback
    // must never stand in for a real error.message.
    return { code: code, message: message };
  }

  // The wording shown to a reviewer. It is never used to satisfy an
  // expected reason.
  function rejectionText(rejection) {
    if (!rejection) {
      return "（产品没有提供错误信息）";
    }
    return rejection.message || rejection.code || "（产品没有提供错误信息）";
  }

  // Scenario definitions are stored in the controller state and snapshotted as
  // JSON. A definition that cannot survive that round trip is rejected before
  // the product state is touched.
  function describeJsonUnsafe(value, path, seen) {
    if (value === null) {
      return null;
    }

    const type = typeof value;

    if (type === "bigint") {
      return `${path} 是 BigInt，不能序列化。`;
    }
    if (type === "function") {
      return `${path} 是函数，不能序列化。`;
    }
    if (type === "symbol") {
      return `${path} 是 Symbol，不能序列化。`;
    }
    if (type === "undefined") {
      return `${path} 是 undefined，不能序列化。`;
    }
    if (type === "number") {
      return Number.isFinite(value) ? null : `${path} 不是有限数值，不能序列化。`;
    }
    if (type !== "object") {
      return null;
    }
    if (seen.has(value)) {
      return `${path} 存在循环引用，不能序列化。`;
    }

    seen.add(value);
    let message = null;

    if (Array.isArray(value)) {
      for (let index = 0; index < value.length && !message; index += 1) {
        message = describeJsonUnsafe(value[index], `${path}[${index}]`, seen);
      }
    } else {
      const keys = Object.keys(value);
      for (let index = 0; index < keys.length && !message; index += 1) {
        message = describeJsonUnsafe(value[keys[index]], `${path}.${keys[index]}`, seen);
      }
    }

    seen.delete(value);
    return message;
  }

  function assertJsonSafe(value, path) {
    const structural = describeJsonUnsafe(value, path, new Set());
    if (structural) {
      return structural;
    }

    // A boxed primitive has no own enumerable properties, so the structural
    // walk cannot see it. The round trip the controller state uses can.
    try {
      JSON.stringify(value);
    } catch (error) {
      return `${path} 不能序列化：${readErrorParts(error).message}`;
    }

    return null;
  }

  function hasKnownComparator(check) {
    return CHECK_COMPARATORS.some(function hasComparator(comparator) {
      return Object.prototype.hasOwnProperty.call(check, comparator);
    });
  }

  function compareCheck(check, actual) {
    if (Object.prototype.hasOwnProperty.call(check, "equals")) {
      return { ok: actual === check.equals, actual: actual };
    }

    if (typeof check.contains === "string") {
      const ok = typeof actual === "string" && actual.indexOf(check.contains) >= 0;
      return { ok: ok, actual: actual };
    }

    return { ok: false, actual: actual };
  }

  function summarizeSteps(steps) {
    const summary = { total: steps.length, done: 0, rejected: 0, failed: 0, skipped: 0, waiting: 0, pending: 0 };
    steps.forEach(function countStatus(step) {
      if (Object.prototype.hasOwnProperty.call(summary, step.status)) {
        summary[step.status] += 1;
      }
    });
    return summary;
  }

  function createConsole(options) {
    if (!options || !options.adapter) {
      throw new TypeError("createConsole requires an adapter.");
    }

    const adapter = options.adapter;
    const settleTimeoutMs = Number.isFinite(options.settleTimeoutMs) && options.settleTimeoutMs > 0
      ? options.settleTimeoutMs
      : DEFAULT_SETTLE_TIMEOUT_MS;
    const pollIntervalMs = Number.isFinite(options.pollIntervalMs) && options.pollIntervalMs > 0
      ? options.pollIntervalMs
      : DEFAULT_POLL_INTERVAL_MS;

    ["pages", "scenarios", "call", "reset"].forEach(function requireAdapterMethod(name) {
      if (typeof adapter[name] !== "function") {
        throw new TypeError(`adapter.${name} must be a function.`);
      }
    });

    const listeners = new Set();
    let settleTimer = null;
    let generation = 0;
    let state = createInitialState();
    // Keep the adapter's original argument and comparison references; state
    // remains a serializable snapshot of the same scenario.
    let executionSteps = new Map();

    function createInitialState() {
      return {
        scenarioId: null,
        scenarioTitle: "",
        scenarioGoal: "",
        scenarioEntry: null,
        stepIndex: -1,
        phase: PHASES.idle,
        steps: [],
        log: [],
        lastError: null,
        pendingReport: null,
        walkedThrough: -1,
        replayTarget: null,
        summary: summarizeSteps([]),
      };
    }

    function snapshotState() {
      const copy = cloneJson(state);
      copy.summary = summarizeSteps(state.steps);
      return copy;
    }

    function notify() {
      const current = snapshotState();
      listeners.forEach(function notifyListener(listener) {
        listener(current);
      });
    }

    function commit(nextState) {
      state = nextState;
      notify();
      return snapshotState();
    }

    function invalidScenario(id, index, error) {
      return {
        scenario: null,
        summary: {
          id: id,
          title: id || `场景 ${index + 1}`,
          goal: "",
          entry: null,
          stepCount: 0,
          error: readErrorParts(error).message,
        },
      };
    }

    function inspectScenario(scenario, index) {
      let id = "";
      try {
        if (!scenario || typeof scenario !== "object" || Array.isArray(scenario)) {
          throw new TypeError("场景定义无效。");
        }
        id = typeof scenario.id === "string" ? scenario.id : "";
        const originalError = validateScenario(scenario);
        if (originalError) {
          throw new TypeError(originalError);
        }

        // Capture only fields consumed by the controller. Validate a stable
        // state snapshot before reset while retaining adapter input references.
        const execution = Array.from(scenario.steps, function captureStep(step) {
          return {
            id: step.id, title: step.title, kind: step.kind, call: step.call,
            args: step.args, check: step.check, expect: step.expect, expectError: step.expectError,
          };
        });
        const stable = cloneJson({
          id: scenario.id,
          title: scenario.title,
          goal: scenario.goal,
          entry: scenario.entry,
          steps: execution,
        });
        const snapshotError = validateScenario(stable);
        if (snapshotError) {
          throw new TypeError(snapshotError);
        }
        return {
          scenario: stable,
          execution: execution,
          summary: {
            id: stable.id,
            title: stable.title || stable.id,
            goal: stable.goal || "",
            entry: stable.entry || null,
            stepCount: stable.steps.length,
          },
        };
      } catch (error) {
        return invalidScenario(id, index, error);
      }
    }

    function inspectScenarios() {
      const scenarios = requireSynchronous(adapter.scenarios(), "adapter.scenarios()");
      if (!Array.isArray(scenarios)) {
        throw new TypeError("adapter.scenarios() 必须返回场景数组。");
      }
      const entries = [];
      for (let index = 0; index < scenarios.length; index += 1) {
        try {
          entries.push(inspectScenario(scenarios[index], index));
        } catch (error) {
          // An array slot can itself have a throwing accessor.
          entries.push(invalidScenario("", index, error));
        }
      }
      return entries;
    }

    function findScenario(scenarioId) {
      const entries = inspectScenarios();
      const valid = entries.find(function findValid(entry) {
        return entry.summary.id === scenarioId && entry.scenario;
      });
      if (valid) {
        return valid;
      }
      return entries.find(function findInvalid(entry) {
        return entry.summary.id === scenarioId;
      }) || null;
    }

    function stepLabel(step, index) {
      return (step && (step.id || step.title)) || `第 ${index + 1} 步`;
    }

    // A scenario definition is checked before anything runs. An unknown step
    // kind, an unknown entry kind, or an observation without an executable
    // check is reported instead of being defaulted into a trusted state.
    function validateScenario(scenario) {
      const entryKind = scenario.entry && scenario.entry.kind;

      if (ENTRY_KINDS.indexOf(entryKind) < 0) {
        return "场景必须声明 entry.kind（normal / review / injected），未知的入口类型不能当作普通入口。";
      }

      if (typeof scenario.id !== "string" || !scenario.id.trim()) {
        return "场景必须有字符串 id。";
      }

      // Every field that ends up in the review state must survive the JSON
      // round trip, otherwise the state cannot be snapshotted.
      const scenarioFields = [
        ["title", scenario.title],
        ["goal", scenario.goal],
        ["entry", scenario.entry],
      ];

      for (const [name, value] of scenarioFields) {
        if (value === undefined || value === null) {
          continue;
        }
        const unsafe = assertJsonSafe(value, `场景 ${scenario.id} 的 ${name}`);
        if (unsafe) {
          return unsafe;
        }
      }

      const steps = scenario.steps || [];
      if (!Array.isArray(steps) || !steps.length) {
        return "场景至少需要一个步骤。";
      }

      const stepIds = new Set();

      for (let index = 0; index < steps.length; index += 1) {
        const step = steps[index];
        const label = stepLabel(step, index);

        if (!step || typeof step !== "object" || Array.isArray(step)) {
          return `步骤 ${label} 的定义无效。`;
        }

        const stepId = step.id || `step-${index + 1}`;
        if (typeof stepId !== "string" || !stepId.trim()) {
          return `步骤 ${label} 的 id 必须是字符串。`;
        }
        if (stepIds.has(stepId)) {
          return `步骤编号 ${stepId} 重复，无法区分跳过与回看。`;
        }
        stepIds.add(stepId);

        // An absent field is normal; a present one must survive the JSON
        // round trip the controller state uses.
        const stepFields = [
          ["title", step.title],
          ["expect", step.expect],
          ["args", step.args],
          ["check", step.check],
        ];

        for (const [name, value] of stepFields) {
          if (value === undefined || value === null) {
            continue;
          }
          const unsafe = assertJsonSafe(value, `步骤 ${stepId} 的 ${name}`);
          if (unsafe) {
            return unsafe;
          }
        }

        if (STEP_KINDS.indexOf(step.kind) < 0) {
          return `步骤 ${label} 的 kind 无效。未知的步骤类型不能当作产品操作；可用类型：${STEP_KINDS.join(" / ")}。`;
        }

        if (step.kind === "observe" && step.call !== undefined && step.call !== null) {
          return `观察步骤 ${label} 不能指定产品动作；请使用 check 读取观察值。`;
        }

        if (step.kind !== "observe" && (typeof step.call !== "string" || !step.call.trim())) {
          return `步骤 ${label} 必须指定要调用的产品动作。`;
        }

        if (step.expectError !== undefined && step.expectError !== null && step.expectError !== false && step.expectError !== true) {
          if (typeof step.expectError !== "object" || Array.isArray(step.expectError)) {
            return `步骤 ${label} 的 expectError 必须是 true 或包含 code / message 的对象。`;
          }
          const unexpectedKey = Object.keys(step.expectError).find(function findUnknownKey(key) {
            return key !== "code" && key !== "message";
          });
          if (unexpectedKey) {
            return `步骤 ${label} 的 expectError 含未知字段 ${unexpectedKey}；可用字段：code / message。`;
          }
          const expectedKeys = Object.keys(step.expectError);
          if (!expectedKeys.length || expectedKeys.some(function invalidReason(key) {
            return typeof step.expectError[key] !== "string" || !step.expectError[key].trim();
          })) {
            return `步骤 ${label} 的预期拒绝原因必须是非空字符串；没有指定原因请使用 true。`;
          }
        }

        if (step.check !== undefined && step.check !== null) {
          if (typeof step.check !== "object" || Array.isArray(step.check)) {
            return `步骤 ${label} 的检查定义无效。`;
          }
          const unknownCheck = Object.keys(step.check).find(function findUnknownCheck(key) {
            return key !== "read" && key !== "args" && CHECK_COMPARATORS.indexOf(key) < 0;
          });
          const comparatorCount = CHECK_COMPARATORS.filter(function hasComparator(key) {
            return Object.prototype.hasOwnProperty.call(step.check, key);
          }).length;
          if (!hasKnownComparator(step.check)) {
            return `步骤 ${label} 的检查没有可执行的比较方式；可用比较：${CHECK_COMPARATORS.join(" / ")}。`;
          }
          if (unknownCheck || comparatorCount !== 1) {
            return `步骤 ${label} 的检查必须且只能使用一种已知比较方式。`;
          }
          if (Object.prototype.hasOwnProperty.call(step.check, "contains") && typeof step.check.contains !== "string") {
            return `步骤 ${label} 的 contains 必须是字符串。`;
          }
          if (typeof step.check.read !== "string" || !step.check.read) {
            return `步骤 ${label} 的检查必须指定 read，才能取得被比较的值。`;
          }
          if (typeof adapter.read !== "function") {
            return `步骤 ${label} 的检查需要适配器提供 read()，当前适配器没有该能力。`;
          }
        }

        if (step.kind === "observe" && !step.check) {
          return `观察步骤 ${label} 必须提供可执行的 check，否则无法判定观察结果。`;
        }

        // An observation reads state; it does not perform an action, so it has
        // no rejection to expect.
        if (step.kind === "observe" && step.expectError) {
          return `观察步骤 ${label} 不能声明 expectError；观察步骤不执行产品动作。`;
        }
      }

      return null;
    }

    function buildSteps(scenario) {
      return (scenario.steps || []).map(function normalizeStep(step, index) {
        return {
          id: step.id || `step-${index + 1}`,
          title: step.title || `第 ${index + 1} 步`,
          kind: step.kind,
          kindLabel: STEP_KIND_LABELS[step.kind],
          call: step.call || null,
          args: step.args || {},
          check: step.check || null,
          expect: step.expect || "",
          expectError: step.expectError === true ? { plain: true } : (step.expectError || null),
          status: STEP_STATUSES.pending,
          error: null,
          observation: null,
          rejection: null,
          reasonVerified: null,
        };
      });
    }

    function clearSettleTimer() {
      if (settleTimer !== null) {
        clearTimeout(settleTimer);
        settleTimer = null;
      }
    }

    function readCheckValue(check) {
      return requireSynchronous(adapter.read(check.read, check.args), "adapter.read()");
    }

    function performAction(step) {
      const execution = executionSteps.get(step.id);
      return requireActionResult(adapter.call(step.call, execution ? execution.args || {} : step.args));
    }

    function evaluateCheck(step) {
      if (!step.check) {
        return { ok: true, actual: undefined, hasCheck: false };
      }

      const execution = executionSteps.get(step.id);
      const check = execution && execution.check ? execution.check : step.check;
      let actual;
      let result;
      try {
        actual = readCheckValue(check);
        result = compareCheck(check, actual);
      } catch (error) {
        return {
          ok: false,
          actual: undefined,
          hasCheck: true,
          error: "读取检查目标失败：" + readErrorParts(error).message,
        };
      }

      // An absent asynchronous receipt is a normal not-yet-matched value.
      if (actual === undefined) {
        return { ok: result.ok, actual: undefined, hasCheck: true };
      }

      try {
        const unsafe = describeJsonUnsafe(actual, "检查结果", new Set());
        if (unsafe) {
          return { ok: false, actual: undefined, hasCheck: true, error: unsafe };
        }
        // Serialize exactly once. All later diagnostics and state snapshots
        // consume this stable value, even if the adapter has a mutable toJSON.
        const encoded = JSON.stringify(actual);
        if (encoded === undefined) {
          return { ok: false, actual: undefined, hasCheck: true, error: "检查结果不能序列化。" };
        }
        return { ok: result.ok, actual: JSON.parse(encoded), hasCheck: true };
      } catch (error) {
        return { ok: false, actual: undefined, hasCheck: true,
          error: "检查结果不能序列化：" + readErrorParts(error).message };
      }
    }

    function withStep(steps, index, patch) {
      const next = steps.slice();
      next[index] = Object.assign({}, next[index], patch);
      return next;
    }

    function phaseAfterStep(steps, index) {
      return index === steps.length - 1 ? PHASES.complete : PHASES.running;
    }

    function pendingIndex() {
      return state.stepIndex + 1;
    }

    function currentStep() {
      return state.steps[pendingIndex()] || null;
    }

    function stopSettleTimer() {
      clearSettleTimer();
    }

    function markStepDone(index, observation) {
      stopSettleTimer();
      const steps = withStep(state.steps, index, {
        status: STEP_STATUSES.done,
        error: null,
        observation: observation,
      });

      return commit(Object.assign({}, state, {
        steps: steps,
        stepIndex: index,
        phase: phaseAfterStep(steps, index),
        lastError: null,
      }));
    }

    function markStepFailed(index, message) {
      stopSettleTimer();
      const steps = withStep(state.steps, index, {
        status: STEP_STATUSES.failed,
        error: message,
      });

      // The cursor stays on the failed step so it is never executed twice.
      // The run cannot continue until the caller resets or replays.
      return commit(Object.assign({}, state, {
        steps: steps,
        stepIndex: index,
        phase: PHASES.failed,
        lastError: message,
        replayTarget: null,
      }));
    }

    // A rejection only counts as the expected rejection when the step declared
    // one and the action really failed. When the step did not name a reason,
    // the run can only prove that a rejection happened.
    function evaluateExpectedRejection(step, parts) {
      const expect = step.expectError;

      if (!parts) {
        // The product reported a failure without saying why. That is not a
        // rejection reason, and the controller's own wording must not stand in
        // for one.
        return {
          declared: !!expect,
          matched: false,
          reasonVerified: false,
          rejection: null,
          reason: "产品动作返回失败但没有提供拒绝证据（error 缺失或没有内容），不能记为预期拒绝。",
        };
      }

      if (!expect) {
        return { declared: false, matched: false, reasonVerified: false, rejection: parts };
      }

      if (expect.plain) {
        return { declared: true, matched: true, reasonVerified: false, rejection: parts };
      }

      if (expect.code && parts.code !== expect.code) {
        return {
          declared: true,
          matched: false,
          reasonVerified: false,
          rejection: parts,
          reason: `预期拒绝 code=${expect.code}，实际 ${parts.code === null ? "（无 code）" : parts.code}`,
        };
      }

      if (expect.message) {
        if (!parts.message) {
          return {
            declared: true,
            matched: false,
            reasonVerified: false,
            rejection: parts,
            reason: `预期拒绝包含「${expect.message}」，但产品没有提供 error.message（只有 ${parts.code ? `code=${parts.code}` : "错误信息"}）`,
          };
        }
        if (parts.message.indexOf(expect.message) < 0) {
          return {
            declared: true,
            matched: false,
            reasonVerified: false,
            rejection: parts,
            reason: `预期拒绝包含「${expect.message}」，实际「${parts.message}」`,
          };
        }
      }

      return { declared: true, matched: true, reasonVerified: true, rejection: parts };
    }

    function armSettleTimer(index) {
      clearSettleTimer();
      const timerGeneration = generation;
      const deadline = Date.now() + settleTimeoutMs;

      function poll() {
        if (timerGeneration !== generation) {
          return;
        }

        const step = state.steps[index];
        if (!step || step.status !== STEP_STATUSES.waiting) {
          return;
        }

        if (state.phase === PHASES.complete) {
          return;
        }

        const observation = evaluateCheck(step);

        // A broken read contract is reported with its own reason. It is not a
        // timeout and must not be dressed up as one.
        if (observation.error) {
          stopSettleTimer();
          markStepFailed(index, observation.error);
          return;
        }

        if (observation.hasCheck && observation.ok) {
          stopSettleTimer();
          markStepDone(index, observation);
          // A replay that was waiting for this result continues towards the
          // target it was asked for.
          if (state.replayTarget !== null) {
            runReplay(index + 1);
          }
          return;
        }

        if (Date.now() >= deadline) {
          stopSettleTimer();
          const message = state.replayTarget !== null && state.replayTarget > index
            ? "结果未确认：等待超时，没有到达回看目标 " + state.replayTarget + "。"
            : "结果未确认：等待超时，请重试或检查外部依赖。";
          markStepFailed(index, message);
          return;
        }

        settleTimer = setTimeout(poll, pollIntervalMs);
      }

      settleTimer = setTimeout(poll, pollIntervalMs);
    }

    // Rebuilding the product state must first deal with pending work. The
    // controller cancels its own timers; the adapter cancels the product's.
    // A product that has no self-managed pending work must say so.
    function rebuildProduct() {
      stopSettleTimer();
      generation += 1;

      const report = { cancelledOwnedTimers: true, cancelledAdapterPending: null, resetResult: null };

      if (typeof adapter.cancelPending === "function") {
        let outcome;
        try {
          outcome = requireAdapterSuccess(adapter.cancelPending(), "adapter.cancelPending()");
        } catch (error) {
          // A failed cancel must not be followed by a product reset: the old
          // tasks are still live and would write into the new scenario.
          return { ok: false, error: "取消产品待处理任务失败：" + readErrorParts(error).message, report: report };
        }

        report.cancelledAdapterPending = cloneJson(outcome);
      } else if (adapter.pendingPolicy !== "none") {
        return {
          ok: false,
          error: "适配器未声明待处理任务的处理方式：提供 cancelPending()，或显式声明 pendingPolicy=\"none\"。",
          report: report,
        };
      } else {
        report.cancelledAdapterPending = { ok: true, policy: "none" };
      }

      let resetResult;
      try {
        resetResult = requireAdapterSuccess(adapter.reset(), "adapter.reset()");
      } catch (error) {
        return { ok: false, error: "重置产品状态失败：" + readErrorParts(error).message, report: report };
      }

      report.resetResult = cloneJson(resetResult);

      return { ok: true, report: report };
    }

    function failRun(message, report) {
      executionSteps = new Map();
      return commit(Object.assign(createInitialState(), {
        phase: PHASES.failed,
        lastError: message,
        pendingReport: report || null,
      }));
    }

    function start(scenarioId) {
      // Look up and validate before touching anything. An invalid scenario id
      // or an invalid definition must not destroy the current run.
      let entry;
      try {
        entry = findScenario(scenarioId);
      } catch (error) {
        return { ok: false, error: readErrorParts(error).message, state: snapshotState() };
      }
      if (!entry) {
        return { ok: false, error: `未找到场景：${scenarioId}`, state: snapshotState() };
      }
      if (!entry.scenario) {
        return { ok: false, error: entry.summary.error, state: snapshotState() };
      }
      const scenario = entry.scenario;

      const rebuild = rebuildProduct();
      if (!rebuild.ok) {
        failRun(rebuild.error, rebuild.report);
        return { ok: false, error: rebuild.error, state: snapshotState() };
      }

      const scenarioEntry = scenario.entry;
      executionSteps = new Map(entry.execution.map(function executionInput(step, index) {
        return [scenario.steps[index].id || `step-${index + 1}`, step];
      }));

      const next = commit(Object.assign(createInitialState(), {
        scenarioId: scenario.id,
        scenarioTitle: scenario.title || scenario.id,
        scenarioGoal: scenario.goal || "",
        scenarioEntry: {
          kind: scenarioEntry.kind,
          kindLabel: ENTRY_KIND_LABELS[scenarioEntry.kind],
          label: scenarioEntry.label || "",
          note: scenarioEntry.note || "",
        },
        steps: buildSteps(scenario),
        phase: PHASES.running,
        pendingReport: rebuild.report,
      }));

      return { ok: true, state: next };
    }

    function next() {
      if (state.phase === PHASES.idle) {
        return { ok: false, error: "尚未开始场景，请先选择一个场景。" };
      }

      if (state.phase === PHASES.complete) {
        return { ok: false, error: "已到最后一步。" };
      }

      if (state.phase === PHASES.failed) {
        return { ok: false, error: "上一步失败，本次运行已停止。请重置或回看后继续。" };
      }

      const index = pendingIndex();
      if (index >= state.steps.length) {
        return { ok: false, error: "已到最后一步。" };
      }

      const step = state.steps[index];

      // A replay that is waiting for an external result drives itself. The
      // reviewer may confirm the result, but must not push the run forward.
      // Clearing the poll here would leave the replay stuck.
      if (state.replayTarget !== null) {
        if (step.status !== STEP_STATUSES.waiting) {
          return { ok: false, error: "回看在途，暂不能推进；请等待回看完成或重置演示。" };
        }

        const confirmed = evaluateCheck(step);
        if (confirmed.error) {
          markStepFailed(index, confirmed.error);
          return { ok: false, error: confirmed.error };
        }
        if (!confirmed.hasCheck || !confirmed.ok) {
          return { ok: false, error: "回看在途，外部结果还没到；请等待或用 refresh() 手动确认。" };
        }

        stopSettleTimer();
        markStepDone(index, confirmed);
        const continued = runReplay(index + 1);
        return continued.ok
          ? Object.assign({}, continued, { step: step.id, replayed: true })
          : continued;
      }

      // Remember how far this run has reached, so a replay can never execute
      // a step that was never walked.
      state = Object.assign({}, state, {
        walkedThrough: Math.max(state.walkedThrough, index),
      });

      // A step that was skipped is never executed. It keeps its history; only
      // rerun() or a reset runs it again.
      if (step.status === STEP_STATUSES.skipped) {
        const steps = state.steps.slice();
        commit(Object.assign({}, state, {
          steps: steps,
          stepIndex: index,
          phase: phaseAfterStep(steps, index),
        }));
        return { ok: true, skipped: step.id };
      }

      // A step waiting on an external result is confirmed first. It is never
      // executed twice.
      if (step.status === STEP_STATUSES.waiting) {
        const settled = evaluateCheck(step);
        if (settled.error) {
          markStepFailed(index, settled.error);
          return { ok: false, error: settled.error };
        }
        if (!settled.hasCheck || !settled.ok) {
          return { ok: true, pending: true, step: step.id };
        }

        stopSettleTimer();
        markStepDone(index, settled);
        return { ok: true, step: step.id };
      }

      if (step.kind === "observe") {
        const observation = evaluateCheck(step);
        if (!observation.ok) {
          const message = observation.error
            || `观察结果与预期不符：实际 ${JSON.stringify(observation.actual)}`;
          markStepFailed(index, message);
          return { ok: false, error: message };
        }

        markStepDone(index, observation);
        return { ok: true, step: step.id };
      }

      let result;
      try {
        result = performAction(step);
      } catch (error) {
        const message = "产品动作未按适配器契约执行：" + readErrorParts(error).message;
        markStepFailed(index, message);
        return { ok: false, error: message };
      }

      // Record the captured diagnostic without reading the product again.
      const appendLog = function appendLog() {
        return state.log.concat([{
          stepId: step.id,
          kind: step.kind,
          kindLabel: step.kindLabel,
          call: step.call,
          ok: result.ok !== false,
          error: result.ok === false ? result.diagnostic : null,
        }]);
      };

      if (result.ok === false) {
        const expectation = evaluateExpectedRejection(step, result.evidence);
        let rejectionObservation = null;
        let failureMessage = null;

        // A step that did not declare an expected rejection fails here. Only a
        // declared, evidenced and actually matched rejection counts.
        if (!expectation.declared || !expectation.matched) {
          failureMessage = expectation.declared
            ? expectation.reason
            : rejectionText(expectation.rejection);
        } else if (step.check) {
          // A step that also declares a check must still satisfy it after the
          // rejection. The check is read once: the verdict and the stored
          // observation come from the same reading. It is read before anything
          // is formatted, so a diagnostic conversion cannot change it.
          rejectionObservation = evaluateCheck(step);
          if (!rejectionObservation.ok) {
            failureMessage = rejectionObservation.error
              || `拒绝后的状态检查与预期不符：实际 ${JSON.stringify(rejectionObservation.actual)}`;
          }
        }

        const nextLog = appendLog();

        if (failureMessage !== null) {
          const steps = withStep(state.steps, index, {
            status: STEP_STATUSES.failed,
            error: failureMessage,
            rejection: expectation.rejection,
            reasonVerified: null,
          });
          commit(Object.assign({}, state, {
            steps: steps,
            log: nextLog,
            stepIndex: index,
            phase: PHASES.failed,
            lastError: failureMessage,
          }));
          return { ok: false, error: failureMessage };
        }

        const message = rejectionText(expectation.rejection);
        const steps = withStep(state.steps, index, {
          status: STEP_STATUSES.rejected,
          error: message,
          rejection: expectation.rejection,
          reasonVerified: expectation.reasonVerified,
          observation: rejectionObservation,
        });
        commit(Object.assign({}, state, {
          steps: steps,
          log: nextLog,
          stepIndex: index,
          phase: phaseAfterStep(steps, index),
          lastError: null,
        }));
        return { ok: true, rejected: true, reasonVerified: expectation.reasonVerified, step: step.id };
      }

      if (step.expectError) {
        const message = "预期此步骤被拒绝，但产品动作成功了；不能记为已验证。";
        const steps = withStep(state.steps, index, {
          status: STEP_STATUSES.failed,
          error: message,
        });
        commit(Object.assign({}, state, {
          steps: steps,
          log: appendLog(),
          stepIndex: index,
          phase: PHASES.failed,
          lastError: message,
        }));
        return { ok: false, error: message };
      }

      if (result.pending === true) {
        const steps = withStep(state.steps, index, { status: STEP_STATUSES.waiting });
        commit(Object.assign({}, state, { steps: steps, log: appendLog() }));
        armSettleTimer(index);
        return { ok: true, pending: true, step: step.id };
      }

      const observation = evaluateCheck(step);
      if (!observation.ok) {
        const message = observation.error
          || `观察结果与预期不符：实际 ${JSON.stringify(observation.actual)}`;
        const steps = withStep(state.steps, index, {
          status: STEP_STATUSES.failed,
          error: message,
        });
        commit(Object.assign({}, state, {
          steps: steps,
          log: appendLog(),
          stepIndex: index,
          phase: PHASES.failed,
          lastError: message,
        }));
        return { ok: false, error: message };
      }

      const steps = withStep(state.steps, index, {
        status: STEP_STATUSES.done,
        error: null,
        observation: observation,
      });
      commit(Object.assign({}, state, {
        steps: steps,
        log: appendLog(),
        stepIndex: index,
        phase: phaseAfterStep(steps, index),
        lastError: null,
      }));

      return { ok: true, step: step.id };
    }

    // A replay produces its own evidence. Steps that this replay did not
    // reach keep nothing from the previous run.
    function resetStepsForReplay() {
      return state.steps.map(function resetStep(step) {
        if (step.status === STEP_STATUSES.skipped) {
          // The skipped history is kept. It is never executed and never
          // reported as verified.
          return Object.assign({}, step, {
            status: STEP_STATUSES.skipped,
            error: null,
            observation: null,
            rejection: null,
            reasonVerified: null,
          });
        }
        return Object.assign({}, step, {
          status: STEP_STATUSES.pending,
          error: null,
          observation: null,
          rejection: null,
          reasonVerified: null,
        });
      });
    }

    function failReplay(index, message, steps, log, rejection) {
      const next = steps.map(function clearStep(step, position) {
        // Earlier entries were produced by this replay, not by the previous
        // run. Keep their observations consistent with the replay log.
        if (position < index) {
          return step;
        }
        if (position === index) {
          return Object.assign({}, step, {
            status: STEP_STATUSES.failed,
            error: message,
            rejection: rejection || null,
            reasonVerified: null,
            observation: null,
          });
        }
        if (step.status === STEP_STATUSES.skipped) {
          return Object.assign({}, step, {
            status: STEP_STATUSES.skipped,
            error: null,
            observation: null,
            rejection: null,
            reasonVerified: null,
          });
        }
        return Object.assign({}, step, {
          status: STEP_STATUSES.pending,
          error: null,
          observation: null,
          rejection: null,
          reasonVerified: null,
        });
      });

      commit(Object.assign({}, state, {
        steps: next,
        log: log,
        stepIndex: index,
        phase: PHASES.failed,
        lastError: message,
        replayTarget: null,
      }));

      return { ok: false, error: message };
    }

    // Runs the replayed steps one by one. It stops on the first step that
    // cannot be confirmed and reports what actually happened.
    function runReplay(fromIndex) {
      const target = state.replayTarget;

      if (target === null) {
        return { ok: true };
      }

      const steps = state.steps.slice();
      const log = state.log.slice();

      for (let index = fromIndex; index <= target; index += 1) {
        const step = steps[index];

        if (step.status === STEP_STATUSES.skipped) {
          continue;
        }

        if (step.kind === "observe") {
          const observation = evaluateCheck(step);
          if (!observation.ok) {
            const message = observation.error
              || `观察结果与预期不符：实际 ${JSON.stringify(observation.actual)}`;
            return failReplay(index, message, steps, log);
          }
          steps[index] = Object.assign({}, step, {
            status: STEP_STATUSES.done,
            error: null,
            observation: observation,
            rejection: null,
            reasonVerified: null,
          });
          continue;
        }

        let result;
        try {
          result = performAction(step);
        } catch (error) {
          const message = "产品动作未按适配器契约执行：" + readErrorParts(error).message;
          return failReplay(index, message, steps, log);
        }

        const evidence = result.ok === false ? result.evidence : null;
        // Record the captured diagnostic without reading the product again.
        const writeLogEntry = function writeLogEntry() {
          log.push({
            stepId: step.id,
            kind: step.kind,
            kindLabel: step.kindLabel,
            call: step.call,
            ok: result.ok !== false,
            error: result.ok === false ? result.diagnostic : null,
          });
        };

        if (result.ok === false) {
          const expectation = evaluateExpectedRejection(step, evidence);
          let rejectionObservation = null;
          let failureMessage = null;

          if (!expectation.declared || !expectation.matched) {
            failureMessage = expectation.declared
              ? expectation.reason
              : rejectionText(expectation.rejection);
          } else if (step.check) {
            // The check after a rejection is read once, before anything is
            // formatted, so a diagnostic conversion cannot change it.
            rejectionObservation = evaluateCheck(step);
            if (!rejectionObservation.ok) {
              failureMessage = rejectionObservation.error
                || `拒绝后的状态检查与预期不符：实际 ${JSON.stringify(rejectionObservation.actual)}`;
            }
          }

          writeLogEntry();

          if (failureMessage !== null) {
            return failReplay(index, failureMessage, steps, log, expectation.rejection);
          }

          steps[index] = Object.assign({}, step, {
            status: STEP_STATUSES.rejected,
            error: rejectionText(expectation.rejection),
            rejection: expectation.rejection,
            reasonVerified: expectation.reasonVerified,
            observation: rejectionObservation,
          });
          continue;
        }

        if (step.expectError) {
          const message = "预期此步骤被拒绝，但产品动作成功了；不能记为已验证。";
          writeLogEntry();
          return failReplay(index, message, steps, log);
        }

        if (result.pending === true) {
          writeLogEntry();
          steps[index] = Object.assign({}, step, { status: STEP_STATUSES.waiting });
          commit(Object.assign({}, state, {
            steps: steps,
            log: log,
            stepIndex: index - 1,
            phase: PHASES.running,
            lastError: null,
          }));
          armSettleTimer(index);
          return { ok: true, pending: true };
        }

        const observation = evaluateCheck(step);
        if (!observation.ok) {
          const message = observation.error
            || `观察结果与预期不符：实际 ${JSON.stringify(observation.actual)}`;
          writeLogEntry();
          return failReplay(index, message, steps, log);
        }

        writeLogEntry();
        steps[index] = Object.assign({}, step, {
          status: STEP_STATUSES.done,
          error: null,
          observation: observation,
          rejection: null,
          reasonVerified: null,
        });
      }

      commit(Object.assign({}, state, {
        steps: steps,
        log: log,
        stepIndex: target,
        phase: target === state.steps.length - 1 ? PHASES.complete : PHASES.running,
        lastError: null,
        replayTarget: null,
      }));

      return { ok: true };
    }

    function replayTo(targetIndex) {
      if (state.phase === PHASES.idle) {
        return { ok: false, error: "尚未开始场景。" };
      }

      if (!Number.isInteger(targetIndex) || targetIndex < -1 || targetIndex >= state.steps.length) {
        return {
          ok: false,
          error: `回看目标 ${targetIndex} 超出范围（可用 -1 到 ${state.steps.length - 1}）。`,
          state: snapshotState(),
        };
      }

      // A replay may only re-run steps this run has actually reached. It must
      // not execute a step that was never walked.
      if (targetIndex > state.walkedThrough) {
        return {
          ok: false,
          error: `回看目标 ${targetIndex} 超出了本次已走到的范围（已走到 ${state.walkedThrough}）；未走过的步骤不能被回看执行。`,
          state: snapshotState(),
        };
      }

      const rebuild = rebuildProduct();
      if (!rebuild.ok) {
        failRun(rebuild.error, rebuild.report);
        return { ok: false, error: rebuild.error, state: snapshotState() };
      }

      commit(Object.assign({}, state, {
        steps: resetStepsForReplay(),
        log: [],
        stepIndex: -1,
        phase: PHASES.running,
        lastError: null,
        replayTarget: targetIndex,
        pendingReport: rebuild.report,
      }));

      if (targetIndex < 0) {
        commit(Object.assign({}, state, { replayTarget: null }));
        return { ok: true };
      }

      return runReplay(0);
    }

    // Re-running a skipped step is an explicit decision. It is never a side
    // effect of a replay.
    function rerun(stepId) {
      if (state.phase === PHASES.idle) {
        return { ok: false, error: "尚未开始场景。" };
      }

      const index = state.steps.findIndex(function findStep(step) {
        return step.id === stepId;
      });

      if (index < 0) {
        return { ok: false, error: `未找到步骤：${stepId}` };
      }

      if (state.steps[index].status !== STEP_STATUSES.skipped) {
        return { ok: false, error: "只有跳过的步骤可以重新执行。" };
      }

      const steps = state.steps.slice();
      steps[index] = Object.assign({}, steps[index], { status: STEP_STATUSES.pending });
      commit(Object.assign({}, state, { steps: steps }));

      return replayTo(index);
    }

    function back() {
      if (state.phase === PHASES.idle) {
        return { ok: false, error: "尚未开始场景。" };
      }

      if (state.stepIndex < 0) {
        return { ok: false, error: "已经在起点，无法再回退。" };
      }

      return replayTo(state.stepIndex - 1);
    }

    function skip() {
      if (state.phase === PHASES.idle) {
        return { ok: false, error: "尚未开始场景。" };
      }

      if (state.phase === PHASES.complete) {
        return { ok: false, error: "已到最后一步。" };
      }

      if (state.phase === PHASES.failed) {
        return { ok: false, error: "上一步失败，本次运行已停止。请重置或回看后继续。" };
      }

      const index = pendingIndex();
      if (index >= state.steps.length) {
        return { ok: false, error: "已到最后一步。" };
      }

      if (state.replayTarget !== null) {
        return { ok: false, error: "回看在途，暂不能跳过；请等待回看完成或重置演示。" };
      }

      const step = state.steps[index];
      if (step.status === STEP_STATUSES.waiting) {
        return { ok: false, error: "该步骤正在等待外部结果，不能跳过。" };
      }

      const steps = withStep(state.steps, index, { status: STEP_STATUSES.skipped });
      commit(Object.assign({}, state, {
        steps: steps,
        stepIndex: index,
        phase: phaseAfterStep(steps, index),
        walkedThrough: Math.max(state.walkedThrough, index),
      }));

      return { ok: true, step: steps[index].id };
    }

    function refresh() {
      const step = currentStep();
      if (!step || step.status !== STEP_STATUSES.waiting) {
        return { ok: false, error: "没有待确认的步骤。" };
      }

      const index = pendingIndex();
      const observation = evaluateCheck(step);

      // A broken read contract keeps its own reason. It must not be replaced
      // by a later success or by the timeout message.
      if (observation.error) {
        markStepFailed(index, observation.error);
        return { ok: false, error: observation.error };
      }

      if (!observation.hasCheck || !observation.ok) {
        return { ok: false, error: "外部结果仍未到达。" };
      }

      stopSettleTimer();
      markStepDone(index, observation);
      if (state.replayTarget !== null) {
        const continued = runReplay(index + 1);
        if (!continued.ok) {
          // The replay failed after this confirmation. Say so.
          return continued;
        }
        return Object.assign({}, continued, { step: step.id, replayed: true });
      }
      return { ok: true, step: step.id };
    }

    function reset() {
      const rebuild = rebuildProduct();
      if (!rebuild.ok) {
        failRun(rebuild.error, rebuild.report);
        return { ok: false, error: rebuild.error, state: snapshotState() };
      }

      executionSteps = new Map();
      const next = commit(Object.assign(createInitialState(), {
        pendingReport: rebuild.report,
      }));

      return { ok: true, state: next };
    }

    function listPages() {
      const pages = requireSynchronous(adapter.pages(), "adapter.pages()");
      if (!Array.isArray(pages)) {
        throw new TypeError("adapter.pages() 必须返回页面数组。");
      }
      return cloneJson(pages);
    }

    function listScenarios() {
      return inspectScenarios().map(function summarize(entry) {
        return entry.summary;
      });
    }

    function subscribe(listener) {
      if (typeof listener !== "function") {
        throw new TypeError("subscribe requires a listener function.");
      }

      listeners.add(listener);
      return function unsubscribe() {
        listeners.delete(listener);
      };
    }

    function pendingTasks() {
      return {
        ownedTimers: settleTimer === null ? 0 : 1,
        waitingSteps: state.steps.filter(function isWaiting(step) {
          return step.status === STEP_STATUSES.waiting;
        }).length,
        adapterPending: state.pendingReport ? state.pendingReport.cancelledAdapterPending : null,
      };
    }

    return {
      start: start,
      next: next,
      back: back,
      skip: skip,
      refresh: refresh,
      reset: reset,
      replayTo: replayTo,
      rerun: rerun,
      listPages: listPages,
      listScenarios: listScenarios,
      subscribe: subscribe,
      state: snapshotState,
      pendingTasks: pendingTasks,
      stepKinds: STEP_KINDS,
      stepKindLabels: STEP_KIND_LABELS,
      entryKinds: ENTRY_KINDS,
      entryKindLabels: ENTRY_KIND_LABELS,
      stepStatuses: STEP_STATUSES,
      phases: PHASES,
    };
  }

  return { createConsole: createConsole };
});
