const assert = require("node:assert/strict");
const test = require("node:test");
const PrototypeRuntime = require("../shared-state/runtime.js");
const PrototypeReviewConsole = require("./review-console.js");
const MobileParcel = require("./examples/mobile-parcel.js");
const DesktopTicketDesk = require("./examples/desktop-ticket-desk.js");

function createParcelConsole(overrides = {}) {
  const app = MobileParcel.createParcelApp();
  const review = PrototypeReviewConsole.createConsole({
    adapter: app.adapter,
    settleTimeoutMs: 60,
    ...overrides,
  });

  return { app, review };
}

function createTicketConsole(overrides = {}) {
  const app = DesktopTicketDesk.createTicketDeskApp();
  const review = PrototypeReviewConsole.createConsole({
    adapter: app.adapter,
    settleTimeoutMs: 60,
    ...overrides,
  });

  return { app, review };
}

// A minimal adapter used for controller-level rules that no product scenario
// exercises on its own.
function stubAdapter(overrides = {}) {
  return Object.assign({
    pages: () => [],
    scenarios: () => [],
    call: () => ({ ok: true }),
    reset: () => ({ ok: true }),
    read: () => undefined,
    pendingPolicy: "none",
  }, overrides);
}

function scenarioWith(steps, entry) {
  return {
    id: "s",
    title: "场景",
    goal: "",
    entry: entry || { kind: "normal", label: "普通入口", note: "" },
    steps,
  };
}

function wait(milliseconds) {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

test("a scenario runs its steps in order and reaches the observable result", async () => {
  const { app, review } = createParcelConsole();

  review.start("pickup-success");
  assert.equal(review.next().ok, true);
  assert.equal(review.next().ok, true);

  // The scan is an external result; the step waits for it to land.
  const pending = review.next();
  assert.equal(pending.pending, true);
  await wait(60);
  assert.equal(app.selectors.phase(), "opened");

  for (let attempt = 0; attempt < 5 && review.state().phase !== "complete"; attempt += 1) {
    review.next();
  }

  const state = review.state();
  assert.equal(state.phase, "complete");
  assert.equal(state.steps[3].status, "done");
  assert.equal(state.steps[3].observation.actual, "opened");
  assert.equal(app.store.getState().notices.length, 1);
});

test("step kinds separate preparation, injection, product action and observation", () => {
  const { review } = createParcelConsole();

  review.start("pickup-rejected");
  review.next();

  const preparation = review.state().steps[0];
  assert.equal(preparation.kind, "prepare");
  assert.equal(preparation.kindLabel, "准备");

  review.next();
  const injection = review.state().steps[1];
  assert.equal(injection.kind, "inject");
  assert.equal(injection.kindLabel, "状态注入");

  review.next();
  const action = review.state().steps[2];
  assert.equal(action.kind, "act");
  assert.equal(action.kindLabel, "产品操作");

  const observation = review.state().steps[4];
  assert.equal(observation.kind, "observe");
  assert.equal(observation.kindLabel, "观察");
});

test("injection only changes the simulated external result, not the product state", () => {
  const { app, review } = createParcelConsole();

  review.start("pickup-rejected");
  review.next();
  assert.equal(app.selectors.phase(), "idle");

  review.next();
  assert.equal(app.selectors.phase(), "idle");
  assert.equal(app.store.getState().scan.result, "wrong");
});

test("a failing product action stops the run and keeps the earlier state", () => {
  const base = MobileParcel.createParcelApp();
  const review = PrototypeReviewConsole.createConsole({
    adapter: Object.assign({}, base.adapter, {
      call: function call(name, args) {
        if (name === "enter-code") {
          return { ok: false, error: "取件码需要 6 位数字。" };
        }
        return base.adapter.call(name, args);
      },
    }),
    settleTimeoutMs: 60,
  });

  review.start("pickup-success");
  review.next();

  const result = review.next();
  assert.equal(result.ok, false);
  assert.match(result.error, /6 位数字/);

  const state = review.state();
  assert.equal(state.phase, "failed");
  assert.equal(state.steps[1].status, "failed");
  assert.equal(base.selectors.phase(), "idle");
});

test("a failed step is not executed twice", () => {
  const base = MobileParcel.createParcelApp();
  let enterCalls = 0;
  const review = PrototypeReviewConsole.createConsole({
    adapter: Object.assign({}, base.adapter, {
      call: function call(name, args) {
        if (name === "enter-code") {
          enterCalls += 1;
          return { ok: false, error: "取件码需要 6 位数字。" };
        }
        return base.adapter.call(name, args);
      },
    }),
    settleTimeoutMs: 60,
  });

  review.start("pickup-success");
  review.next();
  review.next();
  review.next();

  assert.equal(enterCalls, 1);
  assert.equal(review.state().phase, "failed");
});

test("an expected rejection is recorded without failing the run", () => {
  const { app, review } = createTicketConsole();

  review.start("ticket-duplicate");
  review.next();
  review.next();

  const result = review.next();
  assert.equal(result.ok, true);
  assert.equal(result.rejected, true);

  const state = review.state();
  assert.equal(state.steps[2].status, "rejected");
  assert.equal(state.phase, "running");
  // T-101 was claimed once; the rejected repeat does not change the count.
  assert.equal(app.selectors.pendingCount(), 1);
  assert.equal(app.selectors.statusOf("T-101"), "已受理");
});

test("the parcel example verifies the named expected rejection reason", () => {
  const { app, review } = createParcelConsole();

  review.start("pickup-invalid-code");
  review.next();

  const result = review.next();
  const step = review.state().steps[1];

  assert.equal(result.ok, true);
  assert.equal(result.rejected, true);
  assert.equal(result.reasonVerified, true);
  assert.equal(step.status, "rejected");
  assert.equal(step.rejection.code, "INVALID_CODE");
  assert.equal(app.selectors.phase(), "idle");
});

test("the ticket desk example only proves that a rejection happened", () => {
  const { app, review } = createTicketConsole();

  review.start("ticket-duplicate");
  review.next();
  review.next();

  const result = review.next();
  const step = review.state().steps[2];

  assert.equal(result.ok, true);
  assert.equal(result.rejected, true);
  assert.equal(result.reasonVerified, false);
  assert.equal(step.status, "rejected");
  assert.equal(step.reasonVerified, false);
  assert.equal(step.rejection.code, "ALREADY_CLAIMED");
  assert.equal(app.selectors.pendingCount(), 1);
});

test("replaying to an earlier step re-runs the product actions from the known start", () => {
  const { app, review } = createTicketConsole();

  review.start("ticket-happy");
  review.next();
  review.next();
  review.next();
  assert.equal(app.selectors.statusOf("T-102"), "已受理");

  const result = review.back();
  assert.equal(result.ok, true);

  const state = review.state();
  assert.equal(state.stepIndex, 1);
  assert.equal(state.steps[0].status, "done");
  assert.equal(state.steps[1].status, "done");
  assert.equal(state.steps[2].status, "pending");
  // Replay returns to the known start, so the claim is not applied twice.
  assert.equal(app.selectors.statusOf("T-102"), "待受理");
});

test("replay keeps the counts of repeated product actions consistent", () => {
  const { app, review } = createTicketConsole();

  review.start("ticket-happy");
  review.next();
  review.next();
  review.next();
  assert.equal(app.selectors.pendingCount(), 1);

  review.back();
  assert.equal(app.selectors.pendingCount(), 2);
});

test("reset clears the run and reports which tasks it could cancel", () => {
  const { app, review } = createParcelConsole();

  review.start("pickup-success");
  review.next();
  review.next();

  const report = review.reset();
  assert.equal(report.ok, true);
  assert.equal(report.state.phase, "idle");
  assert.equal(report.state.pendingReport.cancelledOwnedTimers, true);
  assert.equal(report.state.pendingReport.cancelledAdapterPending.moduleTasksCancelled, 0);
  assert.equal(app.selectors.phase(), "idle");
  assert.equal(app.store.getState().notices.length, 0);
});

test("reset cancels the adapter's module tasks", async () => {
  const { app, review } = createParcelConsole();
  let fired = false;
  app.scheduleModuleTask(() => {
    fired = true;
  }, 10);

  review.reset();
  await wait(40);
  assert.equal(fired, false);
});

test("a late module task cannot write into a reset scenario", async () => {
  const { app, review } = createParcelConsole();
  let fired = false;
  app.scheduleModuleTask(() => {
    fired = true;
  }, 15);

  review.reset();
  await wait(60);

  assert.equal(fired, false);
  assert.equal(app.store.getState().notices.length, 0);
});

test("a late scheduled product result cannot write into a reset scenario", async () => {
  const { app, review } = createParcelConsole();

  review.start("pickup-success");
  review.next();
  review.next();
  const pending = review.next();
  assert.equal(pending.pending, true);

  review.reset();
  await wait(60);

  assert.equal(app.selectors.phase(), "idle");
  assert.equal(app.store.getState().parcel.phase, "idle");
});

test("a pending step that never resolves fails with an unconfirmed result", async () => {
  const base = MobileParcel.createParcelApp();
  const review = PrototypeReviewConsole.createConsole({
    adapter: Object.assign({}, base.adapter, {
      call: function call(name, args) {
        if (name === "request-scan") {
          // The external result never arrives.
          base.actions.requestScan();
          return { ok: true, pending: true };
        }
        return base.adapter.call(name, args);
      },
    }),
    settleTimeoutMs: 40,
    pollIntervalMs: 10,
  });

  review.start("pickup-success");
  review.next();
  review.next();
  review.next();

  await wait(120);

  const state = review.state();
  assert.equal(state.phase, "failed");
  assert.match(state.lastError, /结果未确认/);
});

test("starting a scenario resets the product to the known start", async () => {
  const { app, review } = createParcelConsole();

  review.start("pickup-success");
  review.next();
  review.next();
  review.next();
  await wait(60);
  assert.equal(app.selectors.phase(), "opened");

  review.start("pickup-success");
  assert.equal(app.selectors.phase(), "idle");
  assert.equal(review.state().stepIndex, -1);
});

test("the same asset drives two different businesses with the same step vocabulary", () => {
  const parcel = createParcelConsole();
  parcel.review.start("pickup-success");
  parcel.review.next();

  const desk = createTicketConsole();
  desk.review.start("ticket-happy");
  desk.review.next();

  assert.equal(parcel.review.state().steps[0].kind, "prepare");
  assert.equal(desk.review.state().steps[0].kind, "prepare");
  // Same asset, different products: the state is not shared.
  assert.equal(parcel.app.store.getState().parcel.phase, "idle");
  assert.equal(desk.app.store.getState().role, "agent");
});

test("the two businesses expose different entry evidence", () => {
  const parcel = createParcelConsole();
  const desk = createTicketConsole();

  parcel.review.start("pickup-success");
  desk.review.start("ticket-happy");
  assert.equal(parcel.review.state().scenarioEntry.kind, "normal");
  assert.equal(desk.review.state().scenarioEntry.kind, "normal");

  parcel.review.start("pickup-rejected");
  assert.equal(parcel.review.state().scenarioEntry.kind, "review");
  assert.match(parcel.review.state().scenarioEntry.note, /不能当作普通入口走通的证据/);
  assert.match(parcel.review.state().scenarioEntry.note, /跳过首页/);

  desk.review.start("ticket-duplicate");
  assert.equal(desk.review.state().scenarioEntry.kind, "review");
  assert.match(desk.review.state().scenarioEntry.note, /跳过列表筛选/);
});

test("the console never reaches into product state directly", () => {
  const app = MobileParcel.createParcelApp();
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: Object.assign({}, app.adapter, {
      call: function call(name, args) {
        calls.push(name);
        return app.adapter.call(name, args);
      },
    }),
  });

  review.start("pickup-success");
  review.next();
  review.next();

  assert.deepEqual(calls, ["reset-demo", "enter-code"]);
  assert.equal(app.selectors.phase(), "entered");
});

test("subscribers receive state snapshots and can unsubscribe", () => {
  const { review } = createParcelConsole();
  const seen = [];
  const unsubscribe = review.subscribe((state) => seen.push(state.phase));

  review.start("pickup-success");
  review.next();
  unsubscribe();
  review.next();

  assert.ok(seen.includes("running"));
  assert.equal(seen.length, 2);
});

test("an adapter without the required methods is rejected", () => {
  assert.throws(() => PrototypeReviewConsole.createConsole({ adapter: {} }), /adapter.pages must be a function/);
  assert.throws(() => PrototypeReviewConsole.createConsole({}), /requires an adapter/);
});

/* ------------------------------------------------------------------ *
 * Regressions for the reproduced defects. Each names the defect it
 * covers so a future change cannot silently reintroduce it.
 * ------------------------------------------------------------------ */

// F1: expectError must not pass when the product action actually succeeds.
test("F1 expectError step fails when the product action succeeds", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "预期被拒绝", kind: "act", call: "act", expectError: true }])],
      call: () => ({ ok: true }),
    }),
  });

  review.start("s");
  const result = review.next();
  const state = review.state();

  assert.equal(result.ok, false);
  assert.match(result.error, /预期此步骤被拒绝/);
  assert.equal(state.steps[0].status, "failed");
  assert.notEqual(state.phase, "complete");
});

test("F1 expectError failure also applies during replay", () => {
  let rejecting = true;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "第一步", kind: "act", call: "act" },
        { id: "s2", title: "预期被拒绝", kind: "act", call: "reject", expectError: true },
      ])],
      call: (name) => (name === "reject" && rejecting ? { ok: false, error: "被拒绝" } : { ok: true }),
    }),
  });

  review.start("s");
  review.next();
  review.next();
  assert.equal(review.state().steps[1].status, "rejected");

  // On replay the product no longer rejects, so the expectation is not met.
  rejecting = false;
  const result = review.replayTo(1);

  assert.equal(result.ok, false);
  assert.match(result.error, /预期此步骤被拒绝/);
  assert.equal(review.state().steps[1].status, "failed");
});

// F1b: a named expected rejection reason must actually match.
test("F1b a named expected rejection reason is checked against the actual rejection", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "预期 FORBIDDEN", kind: "act", call: "act", expectError: { code: "FORBIDDEN" } },
      ])],
      call: () => ({ ok: false, error: { code: "BUSY", message: "忙" } }),
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, false);
  assert.match(result.error, /FORBIDDEN/);
  assert.equal(review.state().steps[0].status, "failed");
});

test("F1b a matching named rejection is recorded and the reason is verified", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "预期 FORBIDDEN", kind: "act", call: "act", expectError: { code: "FORBIDDEN" } },
      ])],
      call: () => ({ ok: false, error: { code: "FORBIDDEN", message: "没有权限" } }),
    }),
  });

  review.start("s");
  const result = review.next();
  const step = review.state().steps[0];

  assert.equal(result.ok, true);
  assert.equal(result.rejected, true);
  assert.equal(result.reasonVerified, true);
  assert.equal(step.status, "rejected");
  assert.equal(step.reasonVerified, true);
});

test("F1b an unnamed rejection only proves that a rejection happened", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "预期被拒绝", kind: "act", call: "act", expectError: true },
      ])],
      call: () => ({ ok: false, error: { code: "BUSY", message: "忙" } }),
    }),
  });

  review.start("s");
  const result = review.next();
  const step = review.state().steps[0];

  assert.equal(result.ok, true);
  assert.equal(result.rejected, true);
  assert.equal(result.reasonVerified, false);
  assert.equal(step.reasonVerified, false);
  assert.equal(step.rejection.code, "BUSY");
});

// F2: an observation without an executable check must not pass silently.
test("F2 an observe step without a check is rejected at definition time", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "没有检查的观察", kind: "observe" }])],
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /必须提供可执行的 check/);
  assert.equal(review.state().phase, "idle");
});

test("F2b an unknown comparator is rejected at definition time", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "未知比较器", kind: "observe", check: { read: "x", greaterThan: 3 } },
      ])],
      read: () => 5,
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /没有可执行的比较方式/);
});

test("F2c a check that needs read is rejected when the adapter has none", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "缺少 read", kind: "observe", check: { read: "x", equals: "y" } },
      ])],
      read: undefined,
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /read/);
});

test("F2d an unknown step kind is rejected instead of becoming a product action", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "未知类型", kind: "teleport", call: "act" }])],
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /kind 无效/);
  assert.equal(review.state().steps.length, 0);
});

test("F2e an unknown entry kind is rejected instead of becoming a normal entry", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith(
        [{ id: "s1", title: "开始", kind: "act", call: "act" }],
        { kind: "somewhere-else", label: "别的入口", note: "" },
      )],
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /entry\.kind/);
  assert.equal(review.state().scenarioEntry, null);
});

// F3: a failed step must stop the run.
test("F3 next cannot continue past a failed step", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "会失败", kind: "act", call: "boom" },
        { id: "s2", title: "下一步", kind: "act", call: "after" },
      ])],
      call: (name) => {
        calls.push(name);
        return name === "boom" ? { ok: false, error: "坏了" } : { ok: true };
      },
    }),
  });

  review.start("s");
  const first = review.next();
  assert.equal(first.ok, false);

  const second = review.next();
  const state = review.state();

  assert.equal(second.ok, false);
  assert.match(second.error, /已停止/);
  assert.notEqual(state.phase, "complete");
  assert.equal(state.steps[1].status, "pending");
  assert.deepEqual(calls, ["boom"]);
});

test("F3b skip cannot continue past a failed step", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "会失败", kind: "act", call: "boom" },
        { id: "s2", title: "下一步", kind: "act", call: "after" },
      ])],
      call: (name) => {
        calls.push(name);
        return name === "boom" ? { ok: false, error: "坏了" } : { ok: true };
      },
    }),
  });

  review.start("s");
  review.next();
  const skipped = review.skip();

  assert.equal(skipped.ok, false);
  assert.notEqual(review.state().phase, "complete");
  assert.deepEqual(calls, ["boom"]);
});

test("F3 a failed run recovers through an explicit reset", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "会失败", kind: "act", call: "boom" },
        { id: "s2", title: "下一步", kind: "act", call: "after" },
      ])],
      call: (name) => (name === "boom" ? { ok: false, error: "坏了" } : { ok: true }),
    }),
  });

  review.start("s");
  review.next();
  assert.equal(review.state().phase, "failed");

  const reset = review.reset();
  assert.equal(reset.ok, true);
  assert.equal(reset.state.phase, "idle");
  assert.equal(review.state().phase, "idle");
});

test("F3 a failed run recovers through an explicit replay", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "第一步", kind: "act", call: "fine" },
        { id: "s2", title: "会失败", kind: "act", call: "boom" },
      ])],
      call: (name) => (name === "boom" ? { ok: false, error: "坏了" } : { ok: true }),
    }),
  });

  review.start("s");
  review.next();
  review.next();
  assert.equal(review.state().phase, "failed");

  const replay = review.replayTo(0);
  assert.equal(replay.ok, true);
  assert.equal(review.state().phase, "running");
  assert.equal(review.state().steps[1].status, "pending");
});

test("F3c a waiting step cannot be skipped", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "等待中", kind: "act", call: "act", check: { read: "x", equals: "done" } },
        { id: "s2", title: "下一步", kind: "act", call: "act" },
      ])],
      call: () => ({ ok: true, pending: true }),
      read: () => "waiting",
    }),
  });

  review.start("s");
  review.next();
  const skipped = review.skip();

  assert.equal(skipped.ok, false);
  assert.match(skipped.error, /不能跳过/);
  assert.equal(review.state().steps[0].status, "waiting");
});

test("F3c a late result cannot carry a waiting step past the end of the scenario", async () => {
  let resolveExternal = false;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "等待中", kind: "act", call: "act", check: { read: "x", equals: "done" } },
      ])],
      call: () => ({ ok: true, pending: true }),
      read: () => (resolveExternal ? "done" : "waiting"),
    }),
    settleTimeoutMs: 500,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  assert.equal(review.state().steps[0].status, "waiting");

  resolveExternal = true;
  await wait(40);

  const state = review.state();
  assert.equal(state.steps[0].status, "done");
  assert.equal(state.phase, "complete");
});

// F4: pending work must be handled before the product state is rebuilt.
test("F4 start cancels the adapter's pending work before rebuilding", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "开始", kind: "act", call: "act" }])],
      call: () => ({ ok: true }),
      cancelPending: () => {
        calls.push("cancelPending");
        return { ok: true, cancelled: 1 };
      },
      reset: () => {
        calls.push("reset");
        return { ok: true };
      },
    }),
  });

  review.start("s");

  assert.deepEqual(calls, ["cancelPending", "reset"]);
  assert.equal(review.state().pendingReport.cancelledAdapterPending.cancelled, 1);
});

test("F4 a scenario switch cancels pending work before the new scenario starts", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [
        Object.assign(scenarioWith([{ id: "s1", title: "开始", kind: "act", call: "act" }]), { id: "first" }),
        Object.assign(scenarioWith([{ id: "s1", title: "开始", kind: "act", call: "act" }]), { id: "second" }),
      ],
      call: () => ({ ok: true }),
      cancelPending: () => {
        calls.push("cancelPending");
        return { ok: true, cancelled: 1 };
      },
      reset: () => {
        calls.push("reset");
        return { ok: true };
      },
    }),
  });

  review.start("first");
  review.start("second");

  assert.deepEqual(calls, ["cancelPending", "reset", "cancelPending", "reset"]);
  assert.equal(review.state().scenarioId, "second");
});

test("F4 a late module callback cannot write into a switched scenario", async () => {
  // The real example app owns a module timer and reports it through
  // cancelPending. The controller must cancel it before the new scenario.
  const { app, review } = createParcelConsole();
  let lateFired = false;

  review.start("pickup-success");
  review.next();
  app.scheduleModuleTask(() => {
    lateFired = true;
  }, 30);

  review.start("pickup-rejected");
  await wait(90);

  assert.equal(lateFired, false);
  assert.equal(review.state().scenarioId, "pickup-rejected");
  assert.equal(app.selectors.phase(), "idle");
});

test("F4 a late module callback cannot write into a replayed scenario", async () => {
  const { app, review } = createParcelConsole();
  let lateFired = false;

  review.start("pickup-success");
  review.next();
  review.next();
  app.scheduleModuleTask(() => {
    lateFired = true;
  }, 30);

  review.replayTo(0);
  await wait(90);

  assert.equal(lateFired, false);
  assert.equal(review.state().phase, "running");
  assert.equal(app.selectors.phase(), "idle");
});

test("F4 a failed cancellation is reported and does not claim a clean reset", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "开始", kind: "act", call: "act" }])],
      cancelPending: () => ({ ok: false, error: "取消失败" }),
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /取消产品待处理任务失败/);
  assert.equal(review.state().phase, "failed");
});

test("F4 a failed product reset is reported and does not claim success", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "开始", kind: "act", call: "act" }])],
      reset: () => ({ ok: false, error: "重置失败" }),
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /重置产品状态失败/);
});

test("F4 an adapter that does not declare how pending work is handled is refused", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "开始", kind: "act", call: "act" }])],
      pendingPolicy: undefined,
      cancelPending: undefined,
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /未声明待处理任务的处理方式/);
});

test("F4 an adapter may declare that it has no pending work", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "开始", kind: "act", call: "act" }])],
      pendingPolicy: "none",
      cancelPending: undefined,
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, true);
  assert.equal(review.state().pendingReport.cancelledAdapterPending.policy, "none");
});

test("F4 replay also cancels pending work before rebuilding", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "一", kind: "act", call: "act" },
        { id: "s2", title: "二", kind: "act", call: "act" },
      ])],
      call: () => ({ ok: true }),
      cancelPending: () => {
        calls.push("cancelPending");
        return { ok: true, cancelled: 1 };
      },
      reset: () => {
        calls.push("reset");
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.next();
  review.next();
  calls.length = 0;

  review.replayTo(0);

  assert.deepEqual(calls, ["cancelPending", "reset"]);
});

// F5: replay must not re-run a skipped action.
test("F5 replay does not execute a previously skipped action", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "会跳过", kind: "act", call: "skipped-call" },
        { id: "s2", title: "前进", kind: "act", call: "second-call" },
      ])],
      call: (name) => {
        calls.push(name);
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.skip();
  review.next();
  calls.length = 0;

  const result = review.replayTo(0);

  assert.equal(result.ok, true);
  assert.deepEqual(calls, []);
  assert.equal(review.state().steps[0].status, "skipped");
  assert.equal(review.state().steps[1].status, "pending");
});

// F6: an out-of-range replay target must be refused before state changes.
test("F6 an out-of-range replay target is refused without changing state", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "一", kind: "act", call: "act" },
        { id: "s2", title: "二", kind: "act", call: "act" },
      ])],
      call: () => ({ ok: true }),
    }),
  });

  review.start("s");
  review.next();
  const before = review.state();

  const result = review.replayTo(99);

  assert.equal(result.ok, false);
  assert.match(result.error, /超出范围/);
  assert.equal(review.state().stepIndex, before.stepIndex);
  assert.equal(review.state().phase, before.phase);
  assert.equal(review.state().steps[1].status, "pending");
});

test("F6 a non-integer replay target is refused", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "一", kind: "act", call: "act" }])],
    }),
  });

  review.start("s");
  const result = review.replayTo(1.5);

  assert.equal(result.ok, false);
  assert.match(result.error, /超出范围/);
});

// F7: an invalid scenario id must not destroy the current run.
test("F7 an invalid scenario id is refused without destroying the current run", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", title: "一", kind: "act", call: "act" }])],
      call: () => ({ ok: true }),
    }),
  });

  review.start("s");
  review.next();
  const before = review.state();

  const result = review.start("no-such-scenario");

  assert.equal(result.ok, false);
  assert.match(result.error, /未找到场景/);
  assert.equal(review.state().scenarioId, before.scenarioId);
  assert.equal(review.state().stepIndex, before.stepIndex);
  assert.equal(review.state().phase, before.phase);
});

test("F7 an invalid scenario definition is refused without destroying the current run", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [
        scenarioWith([{ id: "s1", title: "一", kind: "act", call: "act" }]),
        Object.assign(scenarioWith([{ id: "s1", title: "坏步骤", kind: "teleport" }]), { id: "broken" }),
      ],
      call: () => ({ ok: true }),
    }),
  });

  review.start("s");
  review.next();
  const before = review.state();

  const result = review.start("broken");

  assert.equal(result.ok, false);
  assert.equal(review.state().scenarioId, before.scenarioId);
  assert.equal(review.state().stepIndex, before.stepIndex);
});

test("the summary reports done, rejected, failed and skipped counts", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", title: "一", kind: "act", call: "act" },
        { id: "s2", title: "二", kind: "act", call: "act" },
      ])],
      call: () => ({ ok: true }),
    }),
  });

  review.start("s");
  review.next();
  review.skip();

  const summary = review.state().summary;
  assert.equal(summary.total, 2);
  assert.equal(summary.done, 1);
  assert.equal(summary.skipped, 1);
});

test("an asynchronous action cannot be mistaken for a successful step", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit" }])],
      call: () => Promise.resolve({ ok: false, error: "rejected" }),
    }),
  });
  assert.equal(review.start("s").ok, true);
  assert.equal(review.next().ok, false);
  assert.equal(review.state().steps[0].status, "failed");
  assert.equal(review.state().phase, "failed");
});

test("an adapter error is not mistaken for an expected product rejection", () => {
  for (const action of [
    () => Promise.resolve({ ok: true }),
    () => { throw new Error("adapter failed"); },
  ]) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit", expectError: true }])],
        call: action,
      }),
    });
    assert.equal(review.start("s").ok, true);
    assert.equal(review.next().ok, false);
    assert.equal(review.state().steps[0].status, "failed");
    assert.equal(review.state().phase, "failed");
  }
});

test("an adapter error during replay is not treated as an expected rejection", () => {
  let replaying = false;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit", expectError: true }])],
      call: () => replaying ? Promise.resolve({ ok: true }) : { ok: false, error: "denied" },
    }),
  });
  review.start("s");
  assert.equal(review.next().rejected, true);
  replaying = true;
  assert.equal(review.replayTo(0).ok, false);
  assert.equal(review.state().steps[0].status, "failed");
});

test("missing action results cannot be mistaken for success", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit" }])],
      call: () => undefined,
    }),
  });
  assert.equal(review.start("s").ok, true);
  assert.equal(review.next().ok, false);
  assert.equal(review.state().phase, "failed");
});

test("an asynchronous cancellation cannot report a clean rebuild", () => {
  let resets = 0;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit" }])],
      cancelPending: () => Promise.resolve({ ok: false, error: "still pending" }),
      reset: () => { resets += 1; return { ok: true }; },
    }),
  });
  const result = review.start("s");
  assert.equal(result.ok, false);
  assert.match(result.error, /同步返回/);
  assert.equal(resets, 0);
  assert.equal(review.state().phase, "failed");
});

test("an asynchronous reset cannot report a clean rebuild", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit" }])],
      reset: () => Promise.resolve({ ok: false, error: "reset failed" }),
    }),
  });
  const result = review.start("s");
  assert.equal(result.ok, false);
  assert.match(result.error, /同步返回/);
  assert.equal(review.state().phase, "failed");
});

test("pending cancellation or reset cannot report a clean rebuild", () => {
  for (const overrides of [
    { cancelPending: () => ({ ok: true, pending: true }) },
    { reset: () => ({ ok: true, pending: true }) },
  ]) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit" }])],
        ...overrides,
      }),
    });
    assert.equal(review.start("s").ok, false);
    assert.equal(review.state().phase, "failed");
  }
});

test("an asynchronous observation cannot pass before it is read", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "a", kind: "observe", check: { read: "value", equals: "ready" } }])],
      read: () => Promise.resolve("ready"),
    }),
  });
  assert.equal(review.start("s").ok, true);
  assert.equal(review.next().ok, false);
  assert.equal(review.state().phase, "failed");
});

test("empty or malformed expected rejection cannot claim its reason was verified", () => {
  for (const expectation of [{}, { code: "" }, "rejected"]) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith([{ id: "a", kind: "act", call: "submit", expectError: expectation }])],
      }),
    });
    assert.equal(review.start("s").ok, false);
    assert.equal(review.state().phase, "idle");
  }
});

test("replay preserves the verified rejection and its reason", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "a", kind: "act", call: "reject", expectError: { code: "DENIED" } },
        { id: "b", kind: "act", call: "continue" },
      ])],
      call: (name) => name === "reject"
        ? { ok: false, error: { code: "DENIED", message: "denied" } }
        : { ok: true },
    }),
  });
  review.start("s");
  review.next();
  review.next();
  assert.equal(review.replayTo(0).ok, true);
  assert.equal(review.state().steps[0].status, "rejected");
  assert.equal(review.state().steps[0].reasonVerified, true);
  assert.equal(review.state().steps[0].rejection.code, "DENIED");
});

test("duplicate step ids and mixed comparison rules are refused before reset", () => {
  let resets = 0;
  const malformed = [
    [{ id: "same", kind: "act", call: "a" }, { id: "same", kind: "act", call: "b" }],
    [{ id: "a", kind: "observe", check: { read: "x", equals: 1, greaterThan: 9 } }],
  ];
  for (const steps of malformed) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({ scenarios: () => [scenarioWith(steps)], reset: () => { resets += 1; return { ok: true }; } }),
    });
    assert.equal(review.start("s").ok, false);
  }
  assert.equal(resets, 0);
});

/* ------------------------------------------------------------------ *
 * Round 3 regressions: the seven gaps from the independent review.
 * ------------------------------------------------------------------ */

// G1: the adapter success contract is explicit and checked before use.
test("G1 a boolean false from cancelPending is not a clean rebuild", () => {
  let resets = 0;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", kind: "act", call: "act" }])],
      pendingPolicy: undefined,
      cancelPending: () => false,
      reset: () => { resets += 1; return { ok: true }; },
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /取消产品待处理任务失败/);
  // A failed cancel must not be followed by a product reset.
  assert.equal(resets, 0);
  assert.equal(review.state().phase, "failed");
});

test("G1 a boolean false from reset is not a clean rebuild", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", kind: "act", call: "act" }])],
      reset: () => false,
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /重置产品状态失败/);
  assert.equal(review.state().phase, "failed");
});

test("G1 a missing success value is not a clean rebuild", () => {
  for (const overrides of [
    { cancelPending: () => undefined },
    { reset: () => undefined },
    { cancelPending: () => "ok" },
    { reset: () => 1 },
  ]) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith([{ id: "s1", kind: "act", call: "act" }])],
        ...overrides,
      }),
    });
    assert.equal(review.start("s").ok, false);
    assert.equal(review.state().phase, "failed");
  }
});

test("G1 a pending result is not a clean rebuild even with ok true", () => {
  for (const overrides of [
    { cancelPending: () => ({ ok: true, pending: true }) },
    { reset: () => ({ ok: true, pending: true }) },
  ]) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith([{ id: "s1", kind: "act", call: "act" }])],
        ...overrides,
      }),
    });
    assert.equal(review.start("s").ok, false);
    assert.equal(review.state().phase, "failed");
  }
});

test("G1 an explicit ok true is accepted", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", kind: "act", call: "act" }])],
      pendingPolicy: undefined,
      cancelPending: () => ({ ok: true, cancelled: 2 }),
      reset: () => ({ ok: true }),
    }),
  });

  assert.equal(review.start("s").ok, true);
  assert.equal(review.state().pendingReport.cancelledAdapterPending.cancelled, 2);
});

// G2: a replay produces its own evidence.
test("G2 a failed replay leaves no evidence from the previous run", () => {
  let rejecting = true;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "reject", expectError: { code: "DENIED" } },
        { id: "s2", kind: "act", call: "act" },
      ])],
      call: (name) => {
        if (name === "reject") {
          return rejecting
            ? { ok: false, error: { code: "DENIED", message: "denied" } }
            : { ok: false, error: { code: "BUSY", message: "busy" } };
        }
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.next();
  review.next();
  assert.equal(review.state().steps[0].status, "rejected");
  assert.equal(review.state().steps[0].reasonVerified, true);
  assert.equal(review.state().log.length, 2);

  // The product now rejects for a different reason.
  rejecting = false;
  const result = review.replayTo(0);

  assert.equal(result.ok, false);
  const state = review.state();
  assert.equal(state.steps[0].status, "failed");
  // The failed step must not keep the earlier verified reason.
  assert.notEqual(state.steps[0].reasonVerified, true);
  assert.equal(state.steps[0].reasonVerified, null);
  // The step that was not replayed must not keep its earlier pass.
  assert.equal(state.steps[1].status, "pending");
  assert.equal(state.steps[1].rejection, null);
  // The log must only hold this replay.
  assert.equal(state.log.length, 1);
  assert.equal(state.log[0].ok, false);
});

test("G2 a replay that succeeds leaves no rejected reason from an earlier run", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "reject", expectError: { code: "DENIED" } },
        { id: "s2", kind: "act", call: "act" },
      ])],
      call: (name) => (name === "reject"
        ? { ok: false, error: { code: "DENIED", message: "denied" } }
        : { ok: true }),
    }),
  });

  review.start("s");
  review.next();
  review.next();
  const result = review.replayTo(1);

  assert.equal(result.ok, true);
  const state = review.state();
  assert.equal(state.steps[0].status, "rejected");
  assert.equal(state.steps[0].reasonVerified, true);
  assert.equal(state.steps[1].status, "done");
  assert.equal(state.log.length, 2);
});

// G3: an expected rejection needs evidence from the product.
test("G3 a rejection without an error is not an expected rejection", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", expectError: true },
      ])],
      call: () => ({ ok: false }),
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, false);
  assert.match(result.error, /没有提供拒绝证据/);
  assert.equal(review.state().steps[0].status, "failed");
  assert.equal(review.state().steps[0].rejection, null);
  assert.equal(review.state().steps[0].reasonVerified, null);
});

test("G3 an empty error message is not rejection evidence", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", expectError: true },
      ])],
      call: () => ({ ok: false, error: { code: "", message: "  " } }),
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, false);
  assert.match(result.error, /没有提供拒绝证据/);
});

test("G3 an observe step may not declare expectError", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "observe", check: { read: "x", equals: "y" }, expectError: true },
      ])],
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /不能声明 expectError/);
});

test("G3 an expected rejection step must still satisfy its own check", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        {
          id: "s1",
          kind: "act",
          call: "reject",
          expectError: { code: "DENIED" },
          check: { read: "state", equals: "untouched" },
        },
      ])],
      call: () => ({ ok: false, error: { code: "DENIED", message: "denied" } }),
      read: () => "changed",
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, false);
  assert.match(result.error, /拒绝后的状态检查与预期不符/);
  assert.equal(review.state().steps[0].status, "failed");
});

test("G3 the same check applies during a replay", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        {
          id: "s1",
          kind: "act",
          call: "reject",
          expectError: { code: "DENIED" },
          check: { read: "state", equals: "untouched" },
        },
      ])],
      call: () => ({ ok: false, error: { code: "DENIED", message: "denied" } }),
      read: () => "changed",
    }),
  });

  review.start("s");
  review.next();
  const result = review.replayTo(0);

  assert.equal(result.ok, false);
  assert.match(result.error, /拒绝后的状态检查与预期不符/);
});

// G4: replay semantics.
test("G4 a replay across an async step continues to the requested target", async () => {
  let external = "waiting";
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "first" },
        { id: "s2", kind: "act", call: "async", check: { read: "x", equals: "done" } },
        { id: "s3", kind: "act", call: "third" },
      ])],
      call: (name) => {
        calls.push(name);
        return name === "async" ? { ok: true, pending: true } : { ok: true };
      },
      read: () => external,
    }),
    settleTimeoutMs: 300,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  review.next();
  // The async step settles before the last step is walked.
  external = "done";
  await wait(60);
  review.next();
  assert.equal(review.state().phase, "complete");
  assert.equal(review.state().walkedThrough, 2);

  calls.length = 0;
  external = "waiting";
  const result = review.replayTo(2);

  assert.equal(result.ok, true);
  assert.equal(result.pending, true);

  external = "done";
  await wait(60);

  const state = review.state();
  assert.equal(state.phase, "complete");
  assert.equal(state.stepIndex, 2);
  assert.deepEqual(calls, ["first", "async", "third"]);
});

test("G4 a replay that cannot reach its target says so", async () => {
  let external = "waiting";
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "first" },
        { id: "s2", kind: "act", call: "async", check: { read: "x", equals: "done" } },
        { id: "s3", kind: "act", call: "third" },
      ])],
      call: (name) => (name === "async" ? { ok: true, pending: true } : { ok: true }),
      read: () => external,
    }),
    settleTimeoutMs: 40,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  review.next();
  external = "done";
  await wait(60);
  review.next();
  assert.equal(review.state().phase, "complete");

  external = "waiting";
  review.replayTo(2);
  await wait(120);

  const state = review.state();
  assert.equal(state.phase, "failed");
  assert.match(state.lastError, /没有到达回看目标/);
});

test("G4 replayTo cannot execute a step that was never walked", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "first" },
        { id: "s2", kind: "act", call: "second" },
        { id: "s3", kind: "act", call: "third" },
      ])],
      call: (name) => {
        calls.push(name);
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.next();
  calls.length = 0;

  const result = review.replayTo(2);

  assert.equal(result.ok, false);
  assert.match(result.error, /未走过的步骤不能被回看执行/);
  assert.deepEqual(calls, []);
});

test("G4 the first step can be stepped back to the start", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "first" },
        { id: "s2", kind: "act", call: "second" },
      ])],
      call: (name) => {
        calls.push(name);
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.next();
  assert.equal(review.state().stepIndex, 0);

  const result = review.back();

  assert.equal(result.ok, true);
  assert.equal(review.state().stepIndex, -1);
  assert.equal(review.state().steps[0].status, "pending");
  assert.equal(review.state().phase, "running");
});

test("G4 a skipped step is not executed by a replay and can be re-run explicitly", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "skipped" },
        { id: "s2", kind: "act", call: "second" },
      ])],
      call: (name) => {
        calls.push(name);
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.skip();
  review.next();
  calls.length = 0;

  // The replay must not run the skipped action.
  assert.equal(review.replayTo(1).ok, true);
  assert.deepEqual(calls, ["second"]);
  assert.equal(review.state().steps[0].status, "skipped");

  // Re-running it is an explicit decision.
  calls.length = 0;
  const rerun = review.rerun("s1");
  assert.equal(rerun.ok, true);
  assert.ok(calls.indexOf("skipped") >= 0);
  assert.equal(review.state().steps[0].status, "done");
});

test("G4 a step that was not skipped cannot be re-run", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([{ id: "s1", kind: "act", call: "act" }])],
    }),
  });

  review.start("s");
  const result = review.rerun("s1");

  assert.equal(result.ok, false);
  assert.match(result.error, /只有跳过的步骤可以重新执行/);
});

// G5: definitions must be serializable, and a broken read must not look like a timeout.
test("G5 a definition that cannot be serialized is refused before the product is reset", () => {
  let resets = 0;
  const circular = { code: "1" };
  circular.self = circular;

  const malformed = [
    [{ id: "s1", kind: "act", call: "act", args: { code: 10n } }],
    [{ id: "s1", kind: "act", call: "act", args: circular }],
    [{ id: "s1", kind: "act", call: "act", args: { ratio: Number.NaN } }],
    [{ id: "s1", kind: "act", call: "act", args: { fn: function noop() {} } }],
  ];

  for (const steps of malformed) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith(steps)],
        reset: () => { resets += 1; return { ok: true }; },
      }),
    });

    const result = review.start("s");
    assert.equal(result.ok, false);
    assert.match(result.error, /不能序列化/);
  }

  assert.equal(resets, 0);
});

test("G5 a broken read during a wait reports its own reason", async () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", check: { read: "x", equals: "done" } },
      ])],
      call: () => ({ ok: true, pending: true }),
      read: () => Promise.resolve("done"),
    }),
    settleTimeoutMs: 200,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  await wait(60);

  const state = review.state();
  assert.equal(state.phase, "failed");
  assert.match(state.lastError, /必须同步返回/);
  assert.doesNotMatch(state.lastError, /结果未确认/);
});

/* ------------------------------------------------------------------ *
 * Round 4 regressions: the four P1 items from the independent review.
 * ------------------------------------------------------------------ */

// P1-1: a replay that is waiting for an external result.
test("P1-1 next during an in-flight replay continues it to the target", async () => {
  let external = "waiting";
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "first" },
        { id: "s2", kind: "act", call: "async", check: { read: "x", equals: "done" } },
        { id: "s3", kind: "act", call: "third" },
      ])],
      call: (name) => {
        calls.push(name);
        return name === "async" ? { ok: true, pending: true } : { ok: true };
      },
      read: () => external,
    }),
    settleTimeoutMs: 300,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  review.next();
  external = "done";
  await wait(60);
  review.next();
  assert.equal(review.state().phase, "complete");

  // Replay to the target and stop on the async step.
  calls.length = 0;
  external = "waiting";
  const replay = review.replayTo(2);
  assert.equal(replay.pending, true);

  // The result lands. The reviewer confirms it before the poll runs.
  external = "done";
  const confirmed = review.next();

  assert.equal(confirmed.ok, true);
  const state = review.state();
  assert.equal(state.phase, "complete");
  assert.equal(state.stepIndex, 2);
  assert.deepEqual(calls, ["first", "async", "third"]);
});

test("P1-1 next during an in-flight replay refuses and keeps waiting", async () => {
  let external = "waiting";
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "async", check: { read: "x", equals: "done" } },
        { id: "s2", kind: "act", call: "second" },
      ])],
      call: (name) => (name === "async" ? { ok: true, pending: true } : { ok: true }),
      read: () => external,
    }),
    settleTimeoutMs: 300,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  external = "done";
  await wait(60);
  review.next();

  external = "waiting";
  review.replayTo(1);
  const refused = review.next();

  assert.equal(refused.ok, false);
  assert.match(refused.error, /回看在途/);
  assert.equal(review.state().steps[0].status, "waiting");
  // The poll must still be running, so the replay can still finish.
  assert.equal(review.pendingTasks().ownedTimers, 1);

  external = "done";
  await wait(60);
  assert.equal(review.state().phase, "complete");
});

test("P1-1 a skipped step is not executed after skip, back and next", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "skipped-call" },
        { id: "s2", kind: "act", call: "second-call" },
      ])],
      call: (name) => {
        calls.push(name);
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.skip();
  review.back();
  calls.length = 0;

  const result = review.next();

  assert.equal(result.ok, true);
  assert.equal(result.skipped, "s1");
  assert.deepEqual(calls, []);
  assert.equal(review.state().steps[0].status, "skipped");
  assert.equal(review.state().steps[1].status, "pending");
});

test("P1-1 a replay does not execute a skipped step and needs an explicit rerun", () => {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "skipped-call" },
        { id: "s2", kind: "act", call: "second-call" },
      ])],
      call: (name) => {
        calls.push(name);
        return { ok: true };
      },
    }),
  });

  review.start("s");
  review.skip();
  review.next();
  calls.length = 0;

  review.replayTo(1);
  assert.deepEqual(calls, ["second-call"]);
  assert.equal(review.state().steps[0].status, "skipped");

  calls.length = 0;
  review.rerun("s1");
  assert.ok(calls.indexOf("skipped-call") >= 0);
});

test("P1-1 refresh reports a failed replay continuation", () => {
  let failing = false;
  let external = "done";
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "async", check: { read: "x", equals: "done" } },
        { id: "s2", kind: "act", call: "second" },
      ])],
      call: (name) => {
        if (name === "async") {
          return { ok: true, pending: true };
        }
        return failing ? { ok: false, error: "后续步骤失败" } : { ok: true };
      },
      read: () => external,
    }),
    settleTimeoutMs: 300,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  review.next();
  review.next();
  assert.equal(review.state().phase, "complete");

  failing = true;
  external = "waiting";
  review.replayTo(1);
  // The replay is waiting on the async step; the manual confirmation drives
  // it forward and the continuation fails.
  external = "done";
  const result = review.refresh();

  assert.equal(result.ok, false);
  assert.match(result.error, /后续步骤失败/);
  assert.equal(review.state().phase, "failed");
});

test("P1-1 skip is refused while a replay is in flight", () => {
  let external = "done";
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "async", check: { read: "x", equals: "done" } },
        { id: "s2", kind: "act", call: "second" },
      ])],
      call: (name) => (name === "async" ? { ok: true, pending: true } : { ok: true }),
      read: () => external,
    }),
    settleTimeoutMs: 200,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  review.next();
  review.next();
  assert.equal(review.state().phase, "complete");

  // A replay that waits on the async step is now in flight.
  external = "waiting";
  review.replayTo(1);
  assert.notEqual(review.state().replayTarget, null);

  const skipped = review.skip();
  assert.equal(skipped.ok, false);
  assert.match(skipped.error, /回看在途/);
});

// P1-2: the rejection evidence and a single reading of the check.
test("P1-2 the check after an expected rejection is read once", () => {
  const readings = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        {
          id: "s1",
          kind: "act",
          call: "reject",
          expectError: { code: "DENIED" },
          check: { read: "state", equals: "ready" },
        },
      ])],
      call: () => ({ ok: false, error: { code: "DENIED", message: "denied" } }),
      read: () => {
        readings.push(Date.now());
        return readings.length === 1 ? "ready" : "changed";
      },
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, true);
  assert.equal(readings.length, 1);
  const step = review.state().steps[0];
  assert.equal(step.status, "rejected");
  assert.equal(step.observation.ok, true);
  assert.equal(step.observation.actual, "ready");
});

test("P1-2 the replay reads the check after a rejection once as well", () => {
  const readings = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        {
          id: "s1",
          kind: "act",
          call: "reject",
          expectError: { code: "DENIED" },
          check: { read: "state", equals: "ready" },
        },
      ])],
      call: () => ({ ok: false, error: { code: "DENIED", message: "denied" } }),
      read: () => {
        readings.push(Date.now());
        return readings.length === 1 ? "ready" : "changed";
      },
    }),
  });

  review.start("s");
  review.next();
  readings.length = 0;
  const result = review.replayTo(0);

  assert.equal(result.ok, true);
  assert.equal(readings.length, 1);
  assert.equal(review.state().steps[0].observation.ok, true);
});

test("P1-2 an expected message is not satisfied by the code fallback", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", expectError: { message: "没有权限" } },
      ])],
      call: () => ({ ok: false, error: { code: "FORBIDDEN" } }),
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, false);
  assert.match(result.error, /没有提供 error\.message/);
  assert.equal(review.state().steps[0].status, "failed");
  assert.equal(review.state().steps[0].reasonVerified, null);
});

test("P1-2 an expected message matches a real message", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", expectError: { message: "没有权限" } },
      ])],
      call: () => ({ ok: false, error: { code: "FORBIDDEN", message: "没有权限，不能受理" } }),
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, true);
  assert.equal(result.reasonVerified, true);
  assert.equal(review.state().steps[0].rejection.message, "没有权限，不能受理");
});

test("P1-2 a rejection with only a code is still a verified code match", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", expectError: { code: "FORBIDDEN" } },
      ])],
      call: () => ({ ok: false, error: { code: "FORBIDDEN" } }),
    }),
  });

  review.start("s");
  const result = review.next();

  assert.equal(result.ok, true);
  assert.equal(result.reasonVerified, true);
  assert.equal(review.state().steps[0].rejection.message, null);
});

// P1-3: definitions are checked before the product state is touched.
test("P1-3 every scenario field is checked for JSON safety before the reset", () => {
  let resets = 0;
  const boxed = Object(1n);
  const nested = { inner: {} };
  nested.inner.parent = nested;

  const malformed = [
    [{ id: "s1", kind: "act", call: "act" }, { id: "s2", kind: "act", call: "act", title: 1n }],
    [{ id: "s1", kind: "act", call: "act", args: { boxed: boxed } }],
    [{ id: "s1", kind: "act", call: "act", args: { nested: nested } }],
    [{ id: "s1", kind: "act", call: "act", args: { fn: function noop() {} } }],
    [{ id: "s1", kind: "act", call: "act", expect: 1n }],
  ];

  for (const steps of malformed) {
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith(steps)],
        reset: () => { resets += 1; return { ok: true }; },
      }),
    });

    const result = review.start("s");
    assert.equal(result.ok, false);
    assert.match(result.error, /不能序列化/);
  }

  // A definition that cannot be serialised must not reset the product.
  assert.equal(resets, 0);
});

test("P1-3 a scenario title that cannot be serialised is refused before the reset", () => {
  let resets = 0;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [Object.assign(scenarioWith([{ id: "s1", kind: "act", call: "act" }]), { title: 1n })],
      reset: () => { resets += 1; return { ok: true }; },
    }),
  });

  const result = review.start("s");

  assert.equal(result.ok, false);
  assert.match(result.error, /不能序列化/);
  assert.equal(resets, 0);
});

test("P1-3 a manual confirmation keeps the original read error", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", check: { read: "x", equals: "done" } },
      ])],
      call: () => ({ ok: true, pending: true }),
      read: () => { throw new Error("读取目标炸了"); },
    }),
    settleTimeoutMs: 300,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();

  const result = review.refresh();

  assert.equal(result.ok, false);
  assert.match(result.error, /读取目标炸了/);
  assert.doesNotMatch(result.error, /结果未确认/);
});

test("P1-3 a poll that hits a read error keeps the original reason", async () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", check: { read: "x", equals: "done" } },
      ])],
      call: () => ({ ok: true, pending: true }),
      read: () => { throw new Error("轮询读取炸了"); },
    }),
    settleTimeoutMs: 300,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();
  await wait(60);

  const state = review.state();
  assert.equal(state.phase, "failed");
  assert.match(state.lastError, /轮询读取炸了/);
  assert.doesNotMatch(state.lastError, /结果未确认/);
});

test("P1-3 an asynchronous read during a wait is reported as a contract error", async () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "s1", kind: "act", call: "act", check: { read: "x", equals: "done" } },
      ])],
      call: () => ({ ok: true, pending: true }),
      read: () => Promise.resolve("done"),
    }),
    settleTimeoutMs: 300,
    pollIntervalMs: 10,
  });

  review.start("s");
  review.next();

  const manual = review.refresh();
  assert.equal(manual.ok, false);
  assert.match(manual.error, /必须同步返回/);

  await wait(60);
  const state = review.state();
  assert.equal(state.phase, "failed");
  assert.match(state.lastError, /必须同步返回/);
});

for (const mode of ["next", "refresh", "replay-next", "replay-refresh"]) {
  test(`a transient manual read error stops the waiting run: ${mode}`, async () => {
    let shouldThrow = false;
    let reads = 0;
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith([
          { id: "async", kind: "act", call: "async", check: { read: "result", equals: "ready" } },
          { id: "later", kind: "act", call: "later" },
        ])],
        call: (name) => name === "async" ? { ok: true, pending: true } : { ok: true },
        read: () => {
          reads += 1;
          if (shouldThrow) {
            shouldThrow = false;
            throw new Error("读取暂时失败");
          }
          return "ready";
        },
      }),
      settleTimeoutMs: 500,
      pollIntervalMs: 30,
    });
    review.start("s");
    review.next();
    if (mode.startsWith("replay")) {
      review.refresh();
      review.next();
      assert.equal(review.replayTo(1).pending, true);
    }
    shouldThrow = true;
    const result = mode.endsWith("refresh") ? review.refresh() : review.next();
    const readsAfterError = reads;
    assert.equal(result.ok, false);
    assert.match(result.error, /读取暂时失败/);
    assert.equal(review.state().phase, "failed");
    assert.equal(review.state().steps[0].status, "failed");
    assert.equal(review.state().replayTarget, null);
    assert.equal(review.pendingTasks().ownedTimers, 0);
    await wait(80);
    assert.equal(reads, readsAfterError);
    assert.equal(review.state().phase, "failed");
    assert.match(review.state().lastError, /读取暂时失败/);
    review.reset();
  });
}

for (const mode of ["next", "refresh", "poll"]) {
  test(`an async replay target finishes when confirmed by ${mode}`, async () => {
    let external = "ready";
    const review = PrototypeReviewConsole.createConsole({
      adapter: stubAdapter({
        scenarios: () => [scenarioWith([
          { id: "async", kind: "act", call: "async", check: { read: "result", equals: "ready" } },
          { id: "later", kind: "act", call: "later" },
        ])],
        call: (name) => name === "async" ? { ok: true, pending: true } : { ok: true },
        read: () => external,
      }),
      settleTimeoutMs: 500,
      pollIntervalMs: 20,
    });
    review.start("s");
    review.next();
    review.refresh();
    review.next();
    external = "waiting";
    assert.equal(review.replayTo(0).pending, true);
    external = "ready";
    if (mode === "poll") await wait(60);
    else assert.equal(review[mode]().ok, true);
    const state = review.state();
    assert.equal(state.replayTarget, null);
    assert.equal(state.stepIndex, 0);
    assert.equal(state.steps[0].status, "done");
    assert.equal(review.next().ok, true);
    assert.equal(review.state().phase, "complete");
    review.reset();
  });
}

test("a manual replay confirmation reports when the next replayed step is still pending", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "a", kind: "act", call: "async", check: { read: "result", equals: "ready" } },
        { id: "b", kind: "act", call: "async", check: { read: "result", equals: "ready" } },
        { id: "c", kind: "act", call: "end" },
      ])],
      call: (name) => name === "async" ? { ok: true, pending: true } : { ok: true },
      read: () => "ready",
    }),
  });
  review.start("s");
  review.next();
  review.refresh();
  review.next();
  review.refresh();
  review.next();
  assert.equal(review.replayTo(1).pending, true);
  const result = review.refresh();
  assert.equal(result.ok, true);
  assert.equal(result.pending, true);
  assert.equal(review.state().steps[1].status, "waiting");
  review.reset();
});

test("back during an async replay cancels that replay and remains at the requested earlier position", async () => {
  let external = "ready";
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "a", kind: "act", call: "first" },
        { id: "b", kind: "act", call: "async", check: { read: "result", equals: "ready" } },
        { id: "c", kind: "act", call: "last" },
      ])],
      call: (name) => {
        calls.push(name);
        return name === "async" ? { ok: true, pending: true } : { ok: true };
      },
      read: () => external,
    }),
    settleTimeoutMs: 500,
    pollIntervalMs: 20,
  });
  review.start("s");
  review.next();
  review.next();
  review.refresh();
  review.next();
  external = "waiting";
  assert.equal(review.replayTo(2).pending, true);
  assert.equal(review.back().ok, true);
  const callsAtBack = calls.length;
  external = "ready";
  await wait(60);
  assert.equal(review.state().stepIndex, -1);
  assert.equal(review.state().replayTarget, null);
  assert.deepEqual(review.state().steps.map((step) => step.status), ["pending", "pending", "pending"]);
  assert.equal(review.pendingTasks().ownedTimers, 0);
  assert.equal(calls.length, callsAtBack);
  review.reset();
});

test("an observation carrying an invalid action is rejected before the product resets", () => {
  let resets = 0;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "observe", kind: "observe", call: 1n, check: { read: "status", equals: "ready" } },
      ])],
      reset: () => { resets += 1; return { ok: true }; },
      read: () => "ready",
    }),
  });
  let result;
  assert.doesNotThrow(() => { result = review.start("s"); });
  assert.equal(result.ok, false);
  assert.equal(resets, 0);
  assert.equal(review.state().phase, "idle");
});

test("a failed replay keeps observations from steps completed in that replay", () => {
  let run = 0;
  const review = PrototypeReviewConsole.createConsole({
    adapter: stubAdapter({
      scenarios: () => [scenarioWith([
        { id: "a", kind: "act", call: "a", check: { read: "status", contains: "ready" } },
        { id: "b", kind: "act", call: "b" },
      ])],
      call: (name) => name === "b" && run === 1
        ? { ok: false, error: { code: "DENIED", message: "拒绝" } }
        : { ok: true },
      read: () => `ready-${run}`,
    }),
  });
  review.start("s");
  review.next();
  review.next();
  assert.equal(review.state().steps[0].observation.actual, "ready-0");
  run = 1;
  assert.equal(review.replayTo(1).ok, false);
  const state = review.state();
  assert.equal(state.phase, "failed");
  assert.equal(state.steps[0].status, "done");
  assert.equal(state.steps[0].observation.actual, "ready-1");
  assert.equal(state.steps[1].status, "failed");
  assert.equal(state.log.length, 2);
  assert.equal(state.log[0].ok, true);
});
