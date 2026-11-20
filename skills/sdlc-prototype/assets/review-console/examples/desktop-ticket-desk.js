(function attachDesktopTicketDesk(globalScope, factory) {
  const desktopTicketDesk = factory(globalScope.PrototypeRuntime);

  if (typeof module === "object" && module.exports) {
    module.exports = desktopTicketDesk;
  }

  globalScope.DesktopTicketDesk = desktopTicketDesk;
})(typeof globalThis !== "undefined" ? globalThis : this, function createDesktopTicketDesk(PrototypeRuntime) {
  "use strict";

  const ROLES = {
    agent: "客服专员",
    reviewer: "复核专员",
    readonly: "只读观察员",
  };

  const INITIAL_TICKETS = [
    { id: "T-101", title: "打印机卡纸", customer: "前台", level: "普通", status: "待受理", owner: null },
    { id: "T-102", title: "无法登录工单系统", customer: "研发组", level: "紧急", status: "待受理", owner: null },
    { id: "T-103", title: "发票抬头错误", customer: "财务", level: "普通", status: "已受理", owner: "林岚" },
  ];

  function createTicketDeskApp() {
    const moduleTasks = new Set();
    let epoch = 0;

    const store = PrototypeRuntime.createStore({
      createInitialState: function createInitialState() {
        return {
          role: "agent",
          filter: "all",
          tickets: JSON.parse(JSON.stringify(INITIAL_TICKETS)),
          selected: null,
          notice: "",
          review: { verdict: "approved" },
        };
      },
      reducer: function reducer(state, action) {
        const tickets = state.tickets;

        if (action.type === "set-role") {
          if (!ROLES[action.role]) {
            const error = new Error("未知的角色。");
            error.code = "UNKNOWN_ROLE";
            throw error;
          }
          return Object.assign({}, state, { role: action.role });
        }

        if (action.type === "set-filter") {
          return Object.assign({}, state, { filter: action.filter || "all" });
        }

        if (action.type === "select-ticket") {
          const ticket = tickets.find(function findTicket(item) {
            return item.id === action.id;
          });
          if (!ticket) {
            const error = new Error("工单不存在。");
            error.code = "NO_TICKET";
            throw error;
          }
          return Object.assign({}, state, { selected: ticket.id });
        }

        if (action.type === "claim-ticket") {
          if (state.role === "readonly") {
            const error = new Error("只读观察员不能受理工单。");
            error.code = "FORBIDDEN";
            throw error;
          }
          const ticket = tickets.find(function findTicket(item) {
            return item.id === action.id;
          });
          if (!ticket) {
            const error = new Error("工单不存在。");
            error.code = "NO_TICKET";
            throw error;
          }
          if (ticket.status !== "待受理") {
            const error = new Error("该工单已由他人受理，不能重复受理。");
            error.code = "ALREADY_CLAIMED";
            throw error;
          }
          const owner = state.role === "reviewer" ? "复核专员" : "林岚";
          return Object.assign({}, state, {
            tickets: tickets.map(function replaceTicket(item) {
              return item.id === ticket.id
                ? Object.assign({}, item, { status: "已受理", owner: owner })
                : item;
            }),
            selected: ticket.id,
            notice: "已受理 " + ticket.id + "。",
          });
        }

        if (action.type === "apply-review") {
          if (state.role === "readonly") {
            const error = new Error("只读观察员不能写入复核结果。");
            error.code = "FORBIDDEN";
            throw error;
          }
          const ticket = tickets.find(function findTicket(item) {
            return item.id === action.id;
          });
          if (!ticket) {
            const error = new Error("工单不存在。");
            error.code = "NO_TICKET";
            throw error;
          }
          const verdict = state.review.verdict;
          if (verdict === "approved") {
            return Object.assign({}, state, {
              tickets: tickets.map(function replaceTicket(item) {
                return item.id === ticket.id
                  ? Object.assign({}, item, { status: "已解决" })
                  : item;
              }),
              notice: ticket.id + " 已解决。",
            });
          }
          return Object.assign({}, state, {
            tickets: tickets.map(function replaceTicket(item) {
              return item.id === ticket.id
                ? Object.assign({}, item, { status: "已退回" })
                : item;
            }),
            notice: ticket.id + " 被退回，需要补充材料。",
          });
        }

        if (action.type === "set-review-verdict") {
          return Object.assign({}, state, { review: { verdict: action.verdict || "approved" } });
        }

        return state;
      },
      validate: function validate(state) {
        const owned = state.tickets.filter(function isClaimed(ticket) {
          return ticket.status === "已受理" || ticket.status === "已解决";
        });
        if (owned.some(function hasOwner(ticket) {
          return !ticket.owner;
        })) {
          return { ok: false, code: "MISSING_OWNER", message: "已受理的工单缺少处理人。" };
        }
      },
    });

    function scheduleModuleTask(callback, delay) {
      const taskEpoch = epoch;
      const timer = setTimeout(function runModuleTask() {
        moduleTasks.delete(timer);
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

    function visibleTickets() {
      const state = store.getState();
      if (state.filter === "pending") {
        return state.tickets.filter(function isPending(ticket) {
          return ticket.status === "待受理";
        });
      }
      if (state.filter === "mine") {
        return state.tickets.filter(function isMine(ticket) {
          return ticket.owner === "林岚";
        });
      }
      return state.tickets;
    }

    const actions = {
      setRole: function setRole(role) {
        return store.dispatch({ type: "set-role", role: role });
      },
      setFilter: function setFilter(filter) {
        return store.dispatch({ type: "set-filter", filter: filter });
      },
      selectTicket: function selectTicket(id) {
        return store.dispatch({ type: "select-ticket", id: id });
      },
      claimTicket: function claimTicket(id) {
        return store.dispatch({ type: "claim-ticket", id: id });
      },
      applyReview: function applyReview(id) {
        return store.dispatch({ type: "apply-review", id: id });
      },
      setReviewVerdict: function setReviewVerdict(verdict) {
        return store.dispatch({ type: "set-review-verdict", verdict: verdict });
      },
    };

    const selectors = {
      pendingCount: function pendingCount() {
        return store.getState().tickets.filter(function isPending(ticket) {
          return ticket.status === "待受理";
        }).length;
      },
      statusOf: function statusOf(id) {
        const ticket = store.getState().tickets.find(function findTicket(item) {
          return item.id === id;
        });
        return ticket ? ticket.status : "";
      },
      notice: function notice() {
        return store.getState().notice;
      },
      role: function role() {
        return store.getState().role;
      },
      visibleCount: function visibleCount() {
        return visibleTickets().length;
      },
    };

    const adapter = {
      pages: function pages() {
        return [
          { id: "list", title: "工单列表", note: "查询区、表格与受理工单；本示例没有详情页" },
        ];
      },
      scenarios: function scenarios() {
        return [
          {
            id: "ticket-happy",
            title: "受理并解决工单",
            goal: "从工单列表受理工单，注入模拟复核结论后关闭。",
            entry: {
              kind: "normal",
              label: "工单列表 → 待受理筛选 → 受理",
              note: "普通入口，先在列表筛选出待受理工单；复核结论由演示注入，不代表真实复核服务。",
            },
            steps: [
              { id: "s1", title: "准备：回到默认角色与筛选", kind: "prepare", call: "reset-demo", expect: "客服专员身份，列表显示全部工单。" },
              { id: "s2", title: "筛选待受理", kind: "act", call: "set-filter", args: { filter: "pending" }, expect: "表格只剩待受理工单。" },
              { id: "s3", title: "受理 T-102", kind: "act", call: "claim-ticket", args: { id: "T-102" }, expect: "工单状态变为已受理并记录处理人，因当前筛选而离开待受理列表。" },
              { id: "s4", title: "观察：待受理计数减少", kind: "observe", check: { read: "pending-count", equals: 1 }, expect: "待受理数量与列表行数一致。" },
              { id: "s5", title: "注入：模拟复核结论", kind: "inject", call: "await-review", expect: "复核结论由演示注入，不是用户的产品操作。" },
              { id: "s6", title: "观察：工单数据已解决", kind: "observe", check: { read: "status-of", args: { id: "T-102" }, equals: "已解决" }, expect: "T-102 的数据状态为已解决；当前待受理筛选下不显示该工单，切换到全部可查看。本示例没有详情页。" },
            ],
          },
          {
            id: "ticket-duplicate",
            title: "重复受理被拒绝",
            goal: "演示同一工单不能被受理两次。",
            entry: {
              kind: "review",
              label: "审阅直达工单列表",
              note: "直达跳过列表筛选与列表点击，不能当作普通入口走通的证据；本示例没有详情页。",
            },
            steps: [
              { id: "s1", title: "准备：回到默认角色与筛选", kind: "prepare", call: "reset-demo" },
              { id: "s2", title: "先受理 T-101", kind: "act", call: "claim-ticket", args: { id: "T-101" } },
              { id: "s3", title: "再次受理 T-101", kind: "act", call: "claim-ticket", args: { id: "T-101" }, expectError: true, expect: "提示已被他人受理，状态与计数都不重复变化。只声明被拒绝，未指定原因。" },
              { id: "s4", title: "观察：仍是已受理一次", kind: "observe", check: { read: "pending-count", equals: 1 }, expect: "待受理数量没有因为重复点击而变化。" },
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

        if (name === "set-role") {
          const result = actions.setRole(payload.role);
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        if (name === "set-filter") {
          const result = actions.setFilter(payload.filter);
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        if (name === "select-ticket") {
          const result = actions.selectTicket(payload.id);
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        if (name === "claim-ticket") {
          const result = actions.claimTicket(payload.id);
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        if (name === "await-review") {
          const result = actions.applyReview(payload.id || "T-102");
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        if (name === "set-review-verdict") {
          const result = actions.setReviewVerdict(payload.verdict);
          return result.ok ? { ok: true } : { ok: false, error: result.error };
        }

        const error = new Error("未知的业务动作：" + name);
        error.code = "UNKNOWN_ACTION";
        return { ok: false, error: error };
      },
      read: function read(name, args) {
        const payload = args || {};

        if (name === "pending-count") {
          return selectors.pendingCount();
        }
        if (name === "status-of") {
          return selectors.statusOf(payload.id);
        }
        if (name === "notice") {
          return selectors.notice();
        }
        if (name === "role") {
          return selectors.role();
        }
        if (name === "visible-count") {
          return selectors.visibleCount();
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
      // The product owns its reset. It cancels the product's own timers and
      // returns the state to the fixture, so the product area can be reset
      // without the review console.
      reset: function reset() {
        resetProduct();
        return { ok: true };
      },
      scheduleModuleTask: scheduleModuleTask,
    };
  }

  return { createTicketDeskApp: createTicketDeskApp };
});
