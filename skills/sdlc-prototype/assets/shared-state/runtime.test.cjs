const assert = require("node:assert/strict");
const test = require("node:test");
const PrototypeRuntime = require("./runtime.js");

function counterStore(overrides = {}) {
  return PrototypeRuntime.createStore({
    createInitialState: () => ({ count: 0, items: [] }),
    reducer(state, action) {
      if (action.type === "increment") {
        return { ...state, count: state.count + 1 };
      }

      if (action.type === "invalid") {
        return { ...state, count: -1 };
      }

      if (action.type === "throw") {
        const error = new Error("No changes were made.");
        error.code = "DENIED";
        throw error;
      }

      return state;
    },
    validate(state) {
      if (state.count < 0) {
        return { ok: false, code: "NEGATIVE_COUNT", message: "Count cannot be negative." };
      }
    },
    ...overrides,
  });
}

test("reducer and validator failures leave the previous state intact", () => {
  const store = counterStore();
  const before = store.getState();

  const reducerFailure = store.dispatch({ type: "throw" });
  const validatorFailure = store.dispatch({ type: "invalid" });

  assert.deepEqual(reducerFailure, {
    ok: false,
    error: { code: "DENIED", message: "No changes were made." },
  });
  assert.equal(validatorFailure.error.code, "NEGATIVE_COUNT");
  assert.equal(store.getState(), before);
  assert.deepEqual(store.getState(), { count: 0, items: [] });
});

test("snapshots are deeply frozen and subscribers can unsubscribe", () => {
  const store = counterStore();
  const seen = [];
  const unsubscribe = store.subscribe((state, action) => seen.push([state.count, action.type]));

  assert.equal(store.dispatch({ type: "increment" }).ok, true);
  unsubscribe();
  store.dispatch({ type: "increment" });

  assert.deepEqual(seen, [[1, "increment"]]);
  assert.equal(Object.isFrozen(store.getState()), true);
  assert.equal(Object.isFrozen(store.getState().items), true);
  assert.throws(() => store.getState().items.push("mutate"), TypeError);
});

test("reset prevents scheduled actions from writing into a new fixture", async () => {
  const store = counterStore({ createInitialState: () => ({ count: 7, items: [] }) });
  store.schedule({ type: "increment" }, 20);
  store.reset();

  await new Promise((resolve) => setTimeout(resolve, 45));
  assert.equal(store.getState().count, 7);
});

test("scheduled actions execute once and can be cancelled manually", async () => {
  const store = counterStore();
  store.schedule({ type: "increment" }, 5);
  const cancel = store.schedule({ type: "increment" }, 10);
  cancel();

  await new Promise((resolve) => setTimeout(resolve, 30));
  assert.equal(store.getState().count, 1);
});

test("stores are isolated from each other", () => {
  const first = counterStore();
  const second = counterStore();

  first.dispatch({ type: "increment" });

  assert.equal(first.getState().count, 1);
  assert.equal(second.getState().count, 0);
});
