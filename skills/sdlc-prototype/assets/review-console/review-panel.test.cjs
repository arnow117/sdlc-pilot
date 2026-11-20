const assert = require("node:assert/strict");
const test = require("node:test");
const PrototypeReviewConsole = require("./review-console.js");
const PrototypeReviewPanel = require("./review-panel.js");

/*
 * A minimal DOM used to exercise the panel without installing anything.
 * It implements only what review-panel.js touches: element creation,
 * attributes, class names, text, children, closest, querySelector and
 * event listeners. Selectors supported: ".class", "[attr]", "[attr=\"value\"]".
 */

function matchesSelector(node, selector) {
  if (!node || node.nodeType !== 1) {
    return false;
  }

  // A compound selector is a list of class and attribute parts.
  const parts = selector.match(/\.[^\.\[]+|\[[^\]]+\]/g) || [];
  if (!parts.length) {
    return false;
  }

  return parts.every(function matchesPart(part) {
    if (part.startsWith(".")) {
      return node.classList.contains(part.slice(1));
    }

    const attribute = /^\[([^\]=]+)(?:="([^"]*)")?\]$/.exec(part);
    if (!attribute) {
      return false;
    }

    const name = attribute[1];
    const value = attribute[2];
    if (!node.hasAttribute(name)) {
      return false;
    }
    return value === undefined || node.getAttribute(name) === value;
  });
}

class MiniNode {
  constructor(ownerDocument) {
    this.ownerDocument = ownerDocument;
    this.nodeType = 1;
    this.tagName = "DIV";
    this.childNodes = [];
    this.parentNode = null;
    this.attributes = new Map();
    this.listeners = new Map();
    this._className = "";
    this._textContent = "";
    this.selected = false;
  }

  get className() {
    return this._className;
  }

  set className(value) {
    this._className = String(value);
  }

  get classList() {
    const names = this._className.split(/\s+/).filter(Boolean);
    return {
      contains: (name) => names.indexOf(name) >= 0,
      add: (name) => {
        if (names.indexOf(name) < 0) {
          names.push(name);
        }
        this._className = names.join(" ");
      },
      remove: (name) => {
        this._className = names.filter((entry) => entry !== name).join(" ");
      },
    };
  }

  get textContent() {
    // The real DOM returns the concatenated text of the whole subtree.
    if (this.childNodes.length) {
      return this.childNodes.map(function childText(child) {
        return child.textContent;
      }).join("");
    }
    return this._textContent;
  }

  set textContent(value) {
    this._textContent = String(value === undefined || value === null ? "" : value);
    this.childNodes = [];
  }

  get firstChild() {
    return this.childNodes.length ? this.childNodes[0] : null;
  }

  get children() {
    return this.childNodes.slice();
  }

  setAttribute(name, value) {
    this.attributes.set(name, String(value));
  }

  getAttribute(name) {
    return this.attributes.has(name) ? this.attributes.get(name) : null;
  }

  hasAttribute(name) {
    return this.attributes.has(name);
  }

  appendChild(child) {
    if (child.parentNode) {
      child.parentNode.removeChild(child);
    }
    child.parentNode = this;
    this.childNodes.push(child);
    return child;
  }

  removeChild(child) {
    const index = this.childNodes.indexOf(child);
    if (index >= 0) {
      this.childNodes.splice(index, 1);
      child.parentNode = null;
    }
    return child;
  }

  closest(selector) {
    let node = this;
    while (node) {
      if (matchesSelector(node, selector)) {
        return node;
      }
      node = node.parentNode;
    }
    return null;
  }

  querySelector(selector) {
    const visit = (node) => {
      for (const child of node.childNodes) {
        if (matchesSelector(child, selector)) {
          return child;
        }
        const found = visit(child);
        if (found) {
          return found;
        }
      }
      return null;
    };
    return visit(this);
  }

  querySelectorAll(selector) {
    const found = [];
    const visit = (node) => {
      for (const child of node.childNodes) {
        if (matchesSelector(child, selector)) {
          found.push(child);
        }
        visit(child);
      }
    };
    visit(this);
    return found;
  }

  get value() {
    if (this.tagName === "SELECT") {
      const option = this.childNodes.find((child) => child.selected);
      return option ? option.getAttribute("value") : "";
    }
    return this.getAttribute("value") || "";
  }

  set value(next) {
    this.setAttribute("value", next);
    if (this.tagName === "SELECT") {
      this.childNodes.forEach((child) => {
        child.selected = child.getAttribute("value") === next;
      });
    }
  }

  addEventListener(type, handler) {
    if (!this.listeners.has(type)) {
      this.listeners.set(type, []);
    }
    this.listeners.get(type).push(handler);
  }

  removeEventListener(type, handler) {
    const handlers = this.listeners.get(type);
    if (!handlers) {
      return;
    }
    const index = handlers.indexOf(handler);
    if (index >= 0) {
      handlers.splice(index, 1);
    }
  }

  dispatchEvent(event) {
    // Events bubble to ancestors, as in a real DOM. The panel listens on the
    // host, so a click on a button inside it must reach the host handler.
    let node = this;
    while (node) {
      const handlers = (node.listeners.get(event.type) || []).slice();
      handlers.forEach((handler) => handler(event));
      node = node.parentNode;
    }
  }
}

class MiniDocument {
  createElement(tagName) {
    const node = new MiniNode(this);
    node.tagName = String(tagName).toUpperCase();
    return node;
  }
}

function createHost() {
  const document = new MiniDocument();
  const host = document.createElement("div");
  return { document, host };
}

function click(node) {
  node.dispatchEvent({ type: "click", target: node });
}

function change(node) {
  node.dispatchEvent({ type: "change", target: node });
}

function twoStepScenario(id, title, kind) {
  return {
    id,
    title,
    goal: "",
    entry: { kind: kind || "normal", label: "普通入口", note: "" },
    steps: [
      { id: "s1", title: "一步", kind: "act", call: "act" },
      { id: "s2", title: "两步", kind: "act", call: "act" },
    ],
  };
}

function scenario(id, title, kind) {
  return {
    id,
    title,
    goal: "",
    entry: { kind: kind || "normal", label: "普通入口", note: "" },
    steps: [{ id: "s1", title: "一步", kind: "act", call: "act" }],
  };
}

function createHarness(scenarios) {
  const calls = [];
  const review = PrototypeReviewConsole.createConsole({
    adapter: {
      pages: () => [{ id: "p1", title: "页面一" }],
      scenarios: () => scenarios,
      call: (name) => {
        calls.push(name);
        return { ok: true };
      },
      reset: () => ({ ok: true }),
      pendingPolicy: "none",
    },
  });

  const { document, host } = createHost();
  const panel = PrototypeReviewPanel.createPanel({
    console: review,
    host,
    document,
    title: "审阅台",
  });

  return { review, panel, host, document, calls };
}

test("the panel renders the scenario list and the page index", () => {
  const { host } = createHarness([scenario("a", "场景一"), scenario("b", "场景二", "review")]);

  const select = host.querySelector(".pr-scenario");
  assert.equal(select.childNodes.length, 2);
  assert.equal(host.querySelector(".pr-pages").children.length, 1);
});

test("choosing a scenario survives a redraw", () => {
  const { review, host, calls } = createHarness([scenario("a", "场景一"), scenario("b", "场景二", "review")]);

  review.start("a");

  const select = host.querySelector(".pr-scenario");
  select.value = "b";
  change(select);

  // A console state change triggers a redraw.
  review.next();
  assert.equal(review.state().scenarioId, "a");

  const afterRedraw = host.querySelector(".pr-scenario");
  assert.equal(afterRedraw.value, "b");
  assert.equal(review.state().scenarioId, "a");

  // Starting now uses the chosen scenario, not the redraw default.
  click(host.querySelector('[data-pr="start"]'));
  assert.equal(review.state().scenarioId, "b");
  assert.deepEqual(calls, ["act"]);
});

test("starting a scenario keeps the chosen scenario selected afterwards", () => {
  const { review, host } = createHarness([scenario("a", "场景一"), scenario("b", "场景二", "review")]);

  const select = host.querySelector(".pr-scenario");
  select.value = "b";
  change(select);
  click(host.querySelector('[data-pr="start"]'));

  assert.equal(review.state().scenarioId, "b");
  assert.equal(host.querySelector(".pr-scenario").value, "b");
});

test("destroy detaches the DOM listeners", () => {
  const { panel, host, review, calls } = createHarness([twoStepScenario("a", "场景一")]);

  review.start("a");
  assert.equal(host.listeners.get("click").length, 1);
  assert.equal(host.listeners.get("change").length, 1);

  panel.destroy();
  assert.equal(host.firstChild, null);

  // No handler may be left on the host, otherwise a remount double-fires.
  assert.equal(host.listeners.get("click").length, 0);
  assert.equal(host.listeners.get("change").length, 0);

  // A click on the emptied host must not reach a handler left behind.
  click(host);
  assert.deepEqual(calls, []);
  assert.equal(review.state().stepIndex, -1);
});

test("remounting a panel does not run an action twice", () => {
  const { panel, host, document, review, calls } = createHarness([twoStepScenario("a", "场景一")]);

  review.start("a");
  panel.destroy();

  const second = PrototypeReviewPanel.createPanel({
    console: review,
    host,
    document,
    title: "审阅台",
  });

  click(host.querySelector('[data-pr="next"]'));

  // One click must advance exactly one step, not two.
  assert.equal(review.state().stepIndex, 0);
  assert.deepEqual(calls, ["act"]);

  second.destroy();
});

test("a redraw does not lose the scenario choice when the list is rebuilt", () => {
  const { review, host } = createHarness([scenario("a", "场景一"), scenario("b", "场景二", "review")]);

  const select = host.querySelector(".pr-scenario");
  select.value = "b";
  change(select);

  // Several redraws in a row.
  review.next();
  review.next();

  assert.equal(host.querySelector(".pr-scenario").value, "b");
});

test("the panel shows the summary counts", () => {
  const { review, host } = createHarness([scenario("a", "场景一")]);

  review.start("a");
  review.next();

  const summary = host.querySelector(".pr-summary");
  assert.match(summary.textContent, /已完成 1 \/ 1/);
});

test("the panel reports a controller error to the reviewer", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: {
      pages: () => [],
      scenarios: () => [scenario("a", "场景一")],
      call: () => ({ ok: false, error: "产品动作失败" }),
      reset: () => ({ ok: true }),
      pendingPolicy: "none",
    },
  });

  const { document, host } = createHost();
  const panel = PrototypeReviewPanel.createPanel({ console: review, host, document });

  review.start("a");
  click(host.querySelector('[data-pr="next"]'));

  const message = host.querySelector(".pr-error");
  assert.ok(message);
  assert.match(message.textContent, /产品动作失败/);

  panel.destroy();
});

test("the panel shows the entry note and the skipped preconditions", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: {
      pages: () => [],
      scenarios: () => [{
        id: "direct",
        title: "审阅直达",
        goal: "",
        entry: { kind: "review", label: "直达详情页", note: "直达跳过列表筛选与列表点击。" },
        steps: [{ id: "s1", title: "一步", kind: "act", call: "act" }],
      }],
      call: () => ({ ok: true }),
      reset: () => ({ ok: true }),
      pendingPolicy: "none",
    },
  });

  const { document, host } = createHost();
  const panel = PrototypeReviewPanel.createPanel({ console: review, host, document });

  review.start("direct");

  const entry = host.querySelector(".pr-entry");
  assert.ok(entry);
  assert.match(entry.textContent, /直达详情页/);

  const note = host.querySelector(".pr-entry-note");
  assert.ok(note);
  assert.match(note.textContent, /跳过列表筛选/);

  const prereq = host.querySelector(".pr-prereq");
  assert.ok(prereq);
  assert.match(prereq.textContent, /跳过的前置条件/);

  panel.destroy();
});

test("the panel says a skipped step was not executed or verified", () => {
  const review = PrototypeReviewConsole.createConsole({
    adapter: {
      pages: () => [],
      scenarios: () => [{
        id: "s",
        title: "场景",
        goal: "",
        entry: { kind: "normal", label: "普通入口", note: "" },
        steps: [
          { id: "s1", title: "会被跳过", kind: "act", call: "act" },
          { id: "s2", title: "第二步", kind: "act", call: "act" },
        ],
      }],
      call: () => ({ ok: true }),
      reset: () => ({ ok: true }),
      pendingPolicy: "none",
    },
  });

  const { document, host } = createHost();
  const panel = PrototypeReviewPanel.createPanel({ console: review, host, document });

  review.start("s");
  review.skip();

  const skipped = host.querySelector(".pr-step.pr-status-skipped");
  assert.ok(skipped);
  assert.match(skipped.textContent, /未执行也未验证/);

  panel.destroy();
});

for (const outcome of ["success", "failure"]) {
  test(`the panel clears an in-flight replay message after asynchronous ${outcome}`, async () => {
    let external = "ready";
    const review = PrototypeReviewConsole.createConsole({
      adapter: {
        pages: () => [],
        scenarios: () => [{
          id: "s", title: "异步回看", goal: "",
          entry: { kind: "normal", label: "入口", note: "" },
          steps: [
            { id: "a", kind: "act", call: "first" },
            { id: "b", kind: "act", call: "async", check: { read: "status", equals: "ready" } },
            { id: "c", kind: "act", call: "last" },
          ],
        }],
        call: (name) => name === "async" ? { ok: true, pending: true } : { ok: true },
        read: () => {
          if (external === "error") throw new Error("读取失败");
          return external;
        },
        reset: () => ({ ok: true }),
        pendingPolicy: "none",
      },
      settleTimeoutMs: 500,
      pollIntervalMs: 20,
    });
    const { document, host } = createHost();
    const panel = PrototypeReviewPanel.createPanel({ console: review, host, document });
    review.start("s");
    review.next();
    review.next();
    review.refresh();
    review.next();
    external = "waiting";
    assert.equal(review.replayTo(2).pending, true);
    click(host.querySelector('[data-pr="next"]'));
    assert.match(host.querySelector(".pr-message").textContent, /外部结果还没到/);
    external = outcome === "success" ? "ready" : "error";
    await new Promise((resolve) => setTimeout(resolve, 80));
    assert.equal(review.state().phase, outcome === "success" ? "complete" : "failed");
    assert.equal(host.querySelector(".pr-message"), null);
    if (outcome === "failure") assert.match(host.querySelector(".pr-error").textContent, /读取失败/);
    panel.destroy();
    review.reset();
  });
}
