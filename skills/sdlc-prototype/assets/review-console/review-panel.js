(function attachPrototypeReviewPanel(globalScope, factory) {
  const reviewPanel = factory(globalScope.document);

  if (typeof module === "object" && module.exports) {
    module.exports = reviewPanel;
  }

  globalScope.PrototypeReviewPanel = reviewPanel;
})(typeof globalThis !== "undefined" ? globalThis : this, function createReviewPanelFactory(defaultDocument) {
  "use strict";

  const STATUS_LABELS = {
    pending: "待执行",
    waiting: "等待外部结果",
    done: "已完成",
    rejected: "按预期拒绝",
    failed: "失败",
    skipped: "已跳过",
  };

  const ENTRY_LABELS = {
    normal: "普通用户入口",
    review: "审阅直达",
    injected: "注入步骤",
  };

  function createPanel(options) {
    if (!options || !options.console) {
      throw new TypeError("createPanel requires a console.");
    }

    const reviewConsole = options.console;
    const host = options.host;
    const title = options.title || "审阅台";
    const showPages = options.showPages !== false;
    const ownerDocument = (options.document || defaultDocument);

    if (!host || typeof host !== "object") {
      throw new TypeError("createPanel requires a host element.");
    }

    if (!ownerDocument || typeof ownerDocument.createElement !== "function") {
      throw new TypeError("createPanel requires a document with createElement().");
    }

    let lastMessage = "";
    // The chosen scenario belongs to the panel, not to the console. Keeping it
    // here means a redraw cannot silently drop the reviewer's choice.
    let selectedScenarioId = "";

    function element(tag, spec) {
      const node = ownerDocument.createElement(tag);
      const settings = spec || {};

      if (settings.className) {
        node.className = settings.className;
      }

      if (settings.text !== undefined && settings.text !== null) {
        node.textContent = settings.text;
      }

      if (settings.attrs) {
        Object.keys(settings.attrs).forEach(function setAttribute(name) {
          node.setAttribute(name, settings.attrs[name]);
        });
      }

      if (settings.children) {
        settings.children.forEach(function appendChild(child) {
          node.appendChild(child);
        });
      }

      return node;
    }

    function clearHost() {
      while (host.firstChild) {
        host.removeChild(host.firstChild);
      }
    }

    function knownScenarios() {
      return reviewConsole.listScenarios();
    }

    function selectedScenario() {
      const scenarios = knownScenarios();
      const known = scenarios.some(function isKnown(scenario) {
        return scenario.id === selectedScenarioId;
      });

      if (known) {
        return selectedScenarioId;
      }

      selectedScenarioId = scenarios.length ? scenarios[0].id : "";
      return selectedScenarioId;
    }

    function renderStep(step, index, currentIndex) {
      const statusLabel = STATUS_LABELS[step.status] || step.status;
      const notes = [];

      if (step.expect) {
        notes.push(element("span", {
          className: "pr-expect",
          text: "看点：" + step.expect,
        }));
      }

      if (step.rejection) {
        const reason = step.reasonVerified
          ? "拒绝原因已核对"
          : "只证明被拒绝，未核对具体原因";
        notes.push(element("span", {
          className: "pr-expect",
          text: reason + "：" + step.rejection.message,
        }));
      }

      if (step.error) {
        notes.push(element("span", {
          className: "pr-error",
          text: step.error,
        }));
      }

      if (step.status === "skipped") {
        notes.push(element("span", {
          className: "pr-expect",
          text: "本次跳过，未执行也未验证。",
        }));
      }

      const tags = element("span", {
        className: "pr-tags",
        children: [
          element("span", { className: "pr-tag pr-kind", text: step.kindLabel }),
          element("span", { className: "pr-tag pr-state", text: statusLabel }),
        ],
      });

      const body = element("span", {
        className: "pr-step-body",
        children: [
          element("strong", { text: step.title }),
          tags,
        ].concat(notes),
      });

      const className = "pr-step pr-status-" + step.status + (index === currentIndex ? " pr-current" : "");
      return element("li", {
        className,
        children: [
          element("span", { className: "pr-step-index", text: String(index + 1) }),
          body,
        ],
      });
    }

    function renderSteps(state) {
      if (!state.steps.length) {
        return element("p", { className: "pr-empty", text: "尚未选择场景。" });
      }

      const currentIndex = state.phase === "complete" ? -1 : state.stepIndex + 1;
      return element("ol", {
        className: "pr-steps",
        children: state.steps.map(function toStep(step, index) {
          return renderStep(step, index, currentIndex);
        }),
      });
    }

    function renderScenarioSelect() {
      const scenarios = knownScenarios();
      if (!scenarios.length) {
        return null;
      }

      const current = selectedScenario();
      const select = element("select", { className: "pr-scenario" });

      scenarios.forEach(function addOption(scenario) {
        const entry = scenario.entry && scenario.entry.label ? " · " + scenario.entry.label : "";
        const option = element("option", {
          text: scenario.title + entry,
          attrs: { value: scenario.id },
        });

        if (scenario.id === current) {
          option.selected = true;
          option.setAttribute("selected", "selected");
        }

        select.appendChild(option);
      });

      return element("label", {
        className: "pr-field",
        children: [
          element("span", { text: "场景" }),
          select,
        ],
      });
    }

    function renderPages() {
      if (!showPages) {
        return null;
      }

      const pages = reviewConsole.listPages();
      if (!pages.length) {
        return null;
      }

      const items = pages.map(function toItem(page) {
        const children = [element("span", { className: "pr-page-title", text: page.title || page.id })];

        if (page.note) {
          children.push(element("span", { className: "pr-page-note", text: page.note }));
        }

        return element("li", { children: children });
      });

      return element("section", {
        className: "pr-section",
        children: [
          element("h3", { text: "页面与场景" }),
          element("ul", { className: "pr-pages", children: items }),
        ],
      });
    }

    function actionButton(action, label) {
      return element("button", {
        text: label,
        attrs: { type: "button", "data-pr": action },
      });
    }

    function render() {
      const focused = ownerDocument.activeElement;
      const focusInPanel = focused && typeof host.contains === "function" && host.contains(focused);
      const focusedAction = focusInPanel && typeof focused.getAttribute === "function"
        ? focused.getAttribute("data-pr")
        : null;
      const focusedScenario = focusInPanel && focused.classList && focused.classList.contains("pr-scenario");
      const state = reviewConsole.state();
      const entry = state.scenarioEntry;
      const entryLabel = entry
        ? (ENTRY_LABELS[entry.kind] || entry.kind) + (entry.label ? " · " + entry.label : "")
        : "";
      const summary = state.summary || {};

      const actions = element("div", {
        className: "pr-actions",
        children: [
          actionButton("start", "开始场景"),
          actionButton("next", "下一步"),
          actionButton("back", "回看上一步"),
          actionButton("reset", "重置演示"),
        ],
      });

      const guideChildren = [element("h3", { text: "导览" })];
      const scenarioSelect = renderScenarioSelect();
      if (scenarioSelect) {
        guideChildren.push(scenarioSelect);
      }
      guideChildren.push(actions);

      if (entry) {
        guideChildren.push(element("p", { className: "pr-entry", text: "当前入口：" + entryLabel }));
        // The note says which preconditions the entry does not establish.
        if (entry.note) {
          guideChildren.push(element("p", { className: "pr-note pr-entry-note", text: entry.note }));
        }
        if (entry.kind === "review" || entry.kind === "injected") {
          guideChildren.push(element("p", {
            className: "pr-prereq",
            text: "该入口跳过的前置条件未由本次运行建立，不能当作普通入口走通。",
          }));
        }
      }
      if (state.scenarioGoal) {
        guideChildren.push(element("p", { className: "pr-goal", text: state.scenarioGoal }));
      }

      const summaryText = "已完成 " + (summary.done || 0) + " / " + (summary.total || 0)
        + (summary.rejected ? "，按预期拒绝 " + summary.rejected : "")
        + (summary.skipped ? "，已跳过 " + summary.skipped : "")
        + (summary.failed ? "，失败 " + summary.failed : "");
      guideChildren.push(element("p", { className: "pr-summary", text: summaryText }));
      guideChildren.push(renderSteps(state));

      if (state.lastError) {
        guideChildren.push(element("p", { className: "pr-error", text: state.lastError, attrs: { role: "alert" } }));
      }
      if (lastMessage) {
        guideChildren.push(element("p", { className: "pr-message", text: lastMessage, attrs: { role: "status" } }));
      }

      const children = [
        element("header", {
          className: "pr-header",
          children: [
            element("h2", { text: title }),
            element("p", {
              className: "pr-note",
              text: "审阅控件不属于产品导航。直达与注入只用于复现状态，不代表普通入口已走通。",
            }),
          ],
        }),
      ];

      const pages = renderPages();
      if (pages) {
        children.push(pages);
      }

      children.push(element("section", { className: "pr-section", children: guideChildren }));

      const root = element("section", { className: "pr-root", attrs: { "data-pr-phase": state.phase } });
      children.forEach(function appendChild(child) {
        root.appendChild(child);
      });

      clearHost();
      host.appendChild(root);
      // Rebuilding the panel must not eject keyboard users from its controls.
      // Do not move focus if it was outside the panel before this render.
      const focusTarget = focusedAction
        ? host.querySelector(`[data-pr="${focusedAction}"]`)
        : (focusedScenario ? host.querySelector(".pr-scenario") : null);
      if (focusTarget && typeof focusTarget.focus === "function") {
        focusTarget.focus({ preventScroll: true });
      }
    }

    function handleAction(action) {
      let result;

      if (action === "start") {
        const select = host.querySelector(".pr-scenario");
        const scenarioId = select && select.value ? select.value : selectedScenario();
        selectedScenarioId = scenarioId;
        result = reviewConsole.start(scenarioId);
      } else if (action === "next") {
        result = reviewConsole.next();
      } else if (action === "back") {
        result = reviewConsole.back();
      } else if (action === "reset") {
        result = reviewConsole.reset();
      } else {
        return;
      }

      lastMessage = result && result.ok === false ? result.error : "";
      render();
    }

    function onClick(event) {
      const button = event.target.closest("[data-pr]");
      if (!button) {
        return;
      }

      handleAction(button.getAttribute("data-pr"));
    }

    function onChange(event) {
      const target = event.target;
      if (target && target.classList && target.classList.contains("pr-scenario")) {
        selectedScenarioId = target.value;
        lastMessage = "";
        render();
      }
    }

    host.addEventListener("click", onClick);
    host.addEventListener("change", onChange);

    const unsubscribe = reviewConsole.subscribe(function onStateChange() {
      // A state transition makes a previous action-level message stale. A
      // current failure remains visible through state.lastError instead.
      lastMessage = "";
      render();
    });

    render();

    return {
      render: render,
      selectedScenarioId: function readSelectedScenarioId() {
        return selectedScenario();
      },
      // destroy() must detach the DOM listeners too. Leaving them behind makes
      // a remounted panel run the same action twice.
      destroy: function destroy() {
        unsubscribe();
        host.removeEventListener("click", onClick);
        host.removeEventListener("change", onChange);
        clearHost();
      },
    };
  }

  return { createPanel: createPanel };
});
