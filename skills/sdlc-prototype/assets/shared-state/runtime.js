(function attachPrototypeRuntime(globalScope, factory) {
  const runtime = factory();

  if (typeof module === "object" && module.exports) {
    module.exports = runtime;
  }

  globalScope.PrototypeRuntime = runtime;
})(typeof globalThis !== "undefined" ? globalThis : this, function createRuntime() {
  "use strict";

  function fail(code, message) {
    const error = new Error(message);
    error.code = code;
    throw error;
  }

  function isPlainObject(value) {
    if (value === null || typeof value !== "object") {
      return false;
    }

    const prototype = Object.getPrototypeOf(value);
    return prototype === Object.prototype || prototype === null;
  }

  function assertJsonValue(value, path) {
    if (value === null || typeof value === "string" || typeof value === "boolean") {
      return;
    }

    if (typeof value === "number") {
      if (!Number.isFinite(value)) {
        fail("INVALID_STATE", `${path} must contain finite numbers.`);
      }
      return;
    }

    if (Array.isArray(value)) {
      value.forEach(function assertItem(item, index) {
        assertJsonValue(item, `${path}[${index}]`);
      });
      return;
    }

    if (isPlainObject(value)) {
      Object.keys(value).forEach(function assertProperty(key) {
        assertJsonValue(value[key], `${path}.${key}`);
      });
      return;
    }

    fail("INVALID_STATE", `${path} must be JSON-safe data.`);
  }

  function cloneJson(value) {
    assertJsonValue(value, "state");
    return JSON.parse(JSON.stringify(value));
  }

  function deepFreeze(value) {
    if (value === null || typeof value !== "object" || Object.isFrozen(value)) {
      return value;
    }

    Object.getOwnPropertyNames(value).forEach(function freezeProperty(key) {
      deepFreeze(value[key]);
    });

    return Object.freeze(value);
  }

  function formatError(error, fallbackCode) {
    return {
      code: error && error.code ? error.code : fallbackCode,
      message: error && error.message ? error.message : "The operation could not be completed.",
    };
  }

  function validateState(validate, candidate) {
    if (typeof validate !== "function") {
      return;
    }

    const result = validate(candidate);

    if (result === false) {
      fail("VALIDATION_FAILED", "State validation rejected the update.");
    }

    if (typeof result === "string") {
      fail("VALIDATION_FAILED", result);
    }

    if (result && result.ok === false) {
      fail(result.code || "VALIDATION_FAILED", result.message || "State validation rejected the update.");
    }
  }

  function createStore(options) {
    if (!options || typeof options.createInitialState !== "function" || typeof options.reducer !== "function") {
      throw new TypeError("createStore requires createInitialState and reducer functions.");
    }

    const listeners = new Set();
    const scheduled = new Set();
    let generation = 0;
    let state;

    function buildInitialState() {
      const initial = cloneJson(options.createInitialState());
      validateState(options.validate, initial);
      return deepFreeze(initial);
    }

    function notify(action) {
      listeners.forEach(function notifyListener(listener) {
        try {
          listener(state, action);
        } catch (error) {
          // A view listener must not invalidate an already committed state update.
          setTimeout(function rethrowListenerError() {
            throw error;
          }, 0);
        }
      });
    }

    function publish(candidate, action) {
      const normalized = cloneJson(candidate);
      validateState(options.validate, normalized);
      state = deepFreeze(normalized);
      notify(action);
      return { ok: true, state: state };
    }

    state = buildInitialState();

    function dispatch(action) {
      try {
        const workingState = cloneJson(state);
        const candidate = options.reducer(workingState, action);

        if (candidate === undefined) {
          fail("INVALID_REDUCER_RESULT", "The reducer must return the next complete state.");
        }

        return publish(candidate, action);
      } catch (error) {
        return { ok: false, error: formatError(error, "REDUCER_FAILED") };
      }
    }

    return {
      getState: function getState() {
        return state;
      },

      dispatch,

      subscribe: function subscribe(listener) {
        if (typeof listener !== "function") {
          throw new TypeError("subscribe requires a listener function.");
        }

        listeners.add(listener);
        return function unsubscribe() {
          listeners.delete(listener);
        };
      },

      reset: function reset() {
        generation += 1;
        scheduled.forEach(function clearScheduled(entry) {
          clearTimeout(entry.timer);
        });
        scheduled.clear();
        state = buildInitialState();
        notify({ type: "@@PROTOTYPE_RUNTIME/RESET" });
        return { ok: true, state: state };
      },

      schedule: function schedule(action, delay) {
        const scheduledGeneration = generation;
        const milliseconds = Number.isFinite(delay) && delay >= 0 ? delay : 0;
        const entry = { timer: null };

        entry.timer = setTimeout(function runScheduledAction() {
          scheduled.delete(entry);
          if (scheduledGeneration === generation) {
            dispatch(action);
          }
        }, milliseconds);

        scheduled.add(entry);
        return function cancelScheduledAction() {
          clearTimeout(entry.timer);
          scheduled.delete(entry);
        };
      },
    };
  }

  return { createStore: createStore };
});
