(function attachMobileParcel(globalScope, factory) {
  const mobileParcel = factory(globalScope.PrototypeRuntime);

  if (typeof module === "object" && module.exports) {
    module.exports = mobileParcel;
  }

  globalScope.MobileParcel = mobileParcel;
})(typeof globalThis !== "undefined" ? globalThis : this, function createMobileParcel(PrototypeRuntime) {
  "use strict";

  const CODE_PATTERN = /^\d{6}$/;

  const INITIAL_STATE = {
    session: { signedIn: true, name: "小林" },
    parcel: { code: "", phase: "idle", locker: "", error: "" },
    scan: { state: "idle", result: "success" },
    notices: [],
  };

  function createParcelApp() {
    // Module-owned timers are tracked so the adapter can report and cancel them.
    // They are not owned by the shared-state runtime.
    const moduleTasks = new Set();
    let epoch = 0;

    const store = PrototypeRuntime.createStore({
      createInitialState: function createInitialState() {
        return JSON.parse(JSON.stringify(INITIAL_STATE));
      },
      reducer: function reducer(state, action) {
        const parcel = state.parcel;

        if (action.type === "enter-code") {
          const code = String(action.code || "").trim();
          if (!CODE_PATTERN.test(code)) {
            const error = new Error("取件码需要 6 位数字。");
            error.code = "INVALID_CODE";
            throw error;
          }
          if (parcel.phase === "checking") {
            const error = new Error("正在查询，请稍候。");
            error.code = "BUSY";
            throw error;
          }
          return Object.assign({}, state, {
            parcel: { code: code, phase: "entered", locker: "", error: "" },
          });
        }

        if (action.type === "request-scan") {
          if (parcel.phase !== "entered") {
            const error = new Error("请先输入取件码。");
            error.code = "NO_CODE";
            throw error;
          }
          return Object.assign({}, state, {
            parcel: { code: parcel.code, phase: "checking", locker: "", error: "" },
            scan: { state: "pending", result: state.scan.result },
          });
        }

        if (action.type === "apply-scan") {
          if (state.scan.state !== "pending") {
            const error = new Error("当前没有待确认的查询。");
            error.code = "NO_PENDING_SCAN";
            throw error;
          }
          const result = state.scan.result;
          if (result === "success") {
            return Object.assign({}, state, {
              parcel: { code: parcel.code, phase: "opened", locker: "A-12", error: "" },
              scan: { state: "resolved", result: result },
            });
          }
          if (result === "wrong") {
            return Object.assign({}, state, {
              parcel: { code: parcel.code, phase: "rejected", locker: "", error: "柜机没有找到这个包裹。" },
              scan: { state: "resolved", result: result },
            });
          }
          return Object.assign({}, state, {
            parcel: { code: parcel.code, phase: "entered", locker: "", error: "结果未确认，请重试。" },
            scan: { state: "resolved", result: result },
          });
        }

        if (action.type === "confirm-pickup") {
          if (parcel.phase !== "opened") {
            const error = new Error("柜门尚未打开。");
            error.code = "NOT_OPEN";
            throw error;
          }
          return Object.assign({}, state, {
            parcel: { code: parcel.code, phase: "picked", locker: parcel.locker, error: "" },
            notices: state.notices.concat([{ id: "n" + (state.notices.length + 1), text: "已取出包裹 " + parcel.code }]),
          });
        }

        if (action.type === "set-scan-result") {
          return Object.assign({}, state, {
            scan: { state: state.scan.state, result: action.result || "success" },
          });
        }

        return state;
      },
      validate: function validate(state) {
        if (state.parcel.phase === "opened" && !state.parcel.locker) {
          return { ok: false, code: "MISSING_LOCKER", message: "柜门已开但缺少柜号。" };
        }
      },
    });

    function scheduleModuleTask(callback, delay) {
      const taskEpoch = epoch;
      const timer = setTimeout(function runModuleTask() {
        moduleTasks.delete(timer);
        // Module tasks are not cancelled by the runtime. The product guards
        // late writes with its own epoch instead.
        if (taskEpoch !== epoch) {
          return;
        }
        callback();
      }, delay);
      moduleTasks.add(timer);
      return timer;
    }

    function cancelModuleTasks() {
      const count = moduleTasks.size;
      moduleTasks.forEach(function clearTask(timer) {
        clearTimeout(timer);
      });
      moduleTasks.clear();
      return count;
    }

    function resetProduct() {
      epoch += 1;
      cancelModuleTasks();
      store.reset();
    }

    const actions = {
      enterCode: function enterCode(code) {
        return store.dispatch({ type: "enter-code", code: code });
      },
      requestScan: function requestScan() {
        return store.dispatch({ type: "request-scan" });
      },
      applyScan: function applyScan() {
        return store.dispatch({ type: "apply-scan" });
      },
      confirmPickup: function confirmPickup() {
        return store.dispatch({ type: "confirm-pickup" });
      },
      setScanResult: function setScanResult(result) {
        return store.dispatch({ type: "set-scan-result", result: result });
      },
    };

    const selectors = {
      phase: function phase() {
        return store.getState().parcel.phase;
      },
      locker: function locker() {
        return store.getState().parcel.locker;
      },
      error: function error() {
        return store.getState().parcel.error;
      },
      scanState: function scanState() {
        return store.getState().scan.state;
      },
      notices: function notices() {
        return store.getState().notices.map(function toText(notice) {
          return notice.text;
        });
      },
    };

    const adapter = {
      pages: function pages() {
        return [
          { id: "code", title: "输入取件码", note: "示例产品区的起点，首页未实现" },
          { id: "result", title: "开柜结果", note: "展示柜机返回结果" },
        ];
      },
      scenarios: function scenarios() {
        return [
          {
            id: "pickup-success",
            title: "正常取件",
            goal: "从输入取件码走到取出包裹。",
            entry: {
              kind: "normal",
              label: "取件码页",
              note: "示例产品区直接进入取件码页，没有实现首页与包裹列表；这里只证明取件码页这一段。",
            },
            steps: [
              { id: "s1", title: "准备：回到取件码页", kind: "prepare", call: "reset-demo", expect: "初始为空态，取件码输入框可用。" },
              { id: "s2", title: "输入取件码", kind: "act", call: "enter-code", args: { code: "482913" }, expect: "取件码被接受，进入待查询。" },
              { id: "s3", title: "提交查询并等待柜机返回", kind: "act", call: "request-scan", check: { read: "scan-state", equals: "resolved" }, expect: "提交为产品操作；柜机响应由本地定时器模拟，查询完成后进入开柜结果。" },
              { id: "s4", title: "观察：柜门已开", kind: "observe", check: { read: "phase", equals: "opened" }, expect: "显示柜号 A-12，可以确认取件。" },
              { id: "s5", title: "确认取件", kind: "act", call: "confirm-pickup", expect: "记录一条已取出包裹的通知。" },
            ],
          },
          {
            id: "pickup-invalid-code",
            title: "取件码格式不对",
            goal: "演示输入校验失败时状态不变化、错误可定位。",
            entry: {
              kind: "normal",
              label: "取件码页",
              note: "示例产品区直接进入取件码页，没有实现首页与包裹列表；输入位数不足时给出格式提示。",
            },
            steps: [
              { id: "s1", title: "准备：回到取件码页", kind: "prepare", call: "reset-demo" },
              { id: "s2", title: "输入位数不足的取件码", kind: "act", call: "enter-code", args: { code: "4829" }, expectError: { code: "INVALID_CODE" }, expect: "提示需要 6 位数字，状态不变化。" },
              { id: "s3", title: "观察：仍是初始空态", kind: "observe", check: { read: "phase", equals: "idle" }, expect: "错误的输入没有进入待查询状态。" },
            ],
          },
          {
            id: "pickup-rejected",
            title: "柜机没有这个包裹",
            goal: "演示外部结果被拒绝时的反馈。",
            entry: {
              kind: "review",
              label: "审阅直达取件码页",
              note: "直达跳过首页与包裹列表，只从取件码页开始；不能当作普通入口走通的证据。",
            },
            steps: [
              { id: "s1", title: "准备：回到取件码页", kind: "prepare", call: "reset-demo" },
              { id: "s2", title: "注入：柜机返回未找到", kind: "inject", call: "set-scan-result", args: { result: "wrong" }, expect: "只改外部结果，不直接改产品状态。" },
              { id: "s3", title: "输入取件码", kind: "act", call: "enter-code", args: { code: "482913" } },
              { id: "s4", title: "提交查询并等待柜机返回", kind: "act", call: "request-scan", check: { read: "scan-state", equals: "resolved" } },
              { id: "s5", title: "观察：显示拒绝原因", kind: "observe", check: { read: "phase", equals: "rejected" }, expect: "说明柜机没有找到包裹，可以改码重试。" },
            ],
          },
        ];
      },
      call: function call(name, args) {
        const payload = args || {};

        if (name === "reset-demo") {
          resetProduct();
          return { ok: true };
        }

        if (name === "enter-code") {
          const result = actions.enterCode(payload.code);
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        if (name === "request-scan") {
          const result = actions.requestScan();
          if (!result.ok) {
            return { ok: false, error: result.error };
          }
          // The shared-state runtime owns this delayed result. Its reset()
          // cancels it, so a late callback cannot write into a new scenario.
          store.schedule({ type: "apply-scan" }, 20);
          return { ok: true, pending: true };
        }

        if (name === "confirm-pickup") {
          const result = actions.confirmPickup();
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        if (name === "set-scan-result") {
          const result = actions.setScanResult(payload.result);
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        const error = new Error("未知的业务动作：" + name);
        error.code = "UNKNOWN_ACTION";
        return { ok: false, error: error };
      },
      read: function read(name) {
        if (name === "phase") {
          return selectors.phase();
        }
        if (name === "locker") {
          return selectors.locker();
        }
        if (name === "error") {
          return selectors.error();
        }
        if (name === "scan-state") {
          return selectors.scanState();
        }
        if (name === "notices") {
          return selectors.notices();
        }
        return undefined;
      },
      reset: function reset() {
        resetProduct();
        return { ok: true };
      },
      cancelPending: function cancelPending() {
        return { ok: true, moduleTasksCancelled: cancelModuleTasks(), epoch: epoch };
      },
    };

    return {
      store: store,
      actions: actions,
      selectors: selectors,
      adapter: adapter,
      scheduleModuleTask: scheduleModuleTask,
      // The product owns its reset. It cancels the product's own timers and
      // returns the state to the fixture, so the product area can be reset
      // without the review console.
      reset: function reset() {
        resetProduct();
        return { ok: true };
      },
    };
  }

  return { createParcelApp: createParcelApp };
});
