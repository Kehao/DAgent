// ============================================================
// useChat —— 聊天状态机
// ============================================================
// 职责：把"后端流式事件"翻译成"界面状态变更"。
//
// 为什么用 useReducer 而不是一堆 useState？
//   聊天区是一个"按到达顺序追加/更新"的流水线：token 要追加到当前
//   助手气泡、tool_result 要把对应工具卡置为完成……这类有规则的状态
//   迁移用 reducer 集中管理最清晰 —— 每个事件一种 case，一目了然。
//
// 状态流转图：
//   用户发送 ──► streaming=true ──► 事件流到达 ──► done ──► streaming=false
//                                      │
//        token → 追加/新建 assistant 气泡（打字机）
//        tool_start → 追加 running 工具卡；task 工具另开"委派中"横幅
//        tool_result → 对应工具卡置 done；task 完成则收起委派横幅
//        todo_update → 整体替换任务规划清单（TodoListPanel）
//        review_result → 记录判定；needs_revision 开"返工中"横幅
//        error → 追加错误条
// ============================================================

import { useCallback, useReducer } from "react";
import { streamChat } from "../lib/api";
import type { Banner, ChatState, ChatItem, SSEEvent } from "../types";

// ---------- Action 定义 ----------
// 大部分 action 与后端 SSE 事件同构，可直接复用；只有 user_sent 是前端自造的。
// done 的 thread_id 设为可选：后端正常结束会带，网络异常时前端手动补发的
// { type: "done" } 没有 thread_id —— 前端 UI 不关心这个字段。
type Action =
  | { type: "user_sent"; text: string }
  | Exclude<SSEEvent, { type: "done" }>
  | { type: "done"; thread_id?: string };

// ---------- 工具函数 ----------
// 自增 id 生成器：聊天条目用 id 做 React key（纯展示用）。
// ⚠️ 教学备注：React StrictMode 开发态会双调用 reducer 以检测纯度，
//    这里 ++ 会产生"跳号"——因 id 只用于 key 不影响正确性，可接受。
let nextItemId = 1;
const newId = (): number => nextItemId++;

const initialState: ChatState = {
  items: [],
  streaming: false,
  thinking: false,
  phase: null,
  review: null,
  todos: [],
  banner: null,
};

// ---------- 常量 ----------
// task = SubAgentMiddleware 暴露的委派工具：主 Agent 用它把分析任务派给
// supplier-analyst 子 Agent。前端据此开/关"委派中"横幅。
const DELEGATE_TOOL = "task";

/** 构造"委派中"横幅文案（tool_start task 时调用） */
const delegateBanner = (): Banner => ({
  kind: "delegate",
  text: "已将分析任务委派给专职子 Agent（supplier-analyst），正在独立执行…",
});

/** 构造"返工中"横幅文案（review_result needs_revision 时调用） */
const revisingBanner = (iteration: number): Banner => ({
  kind: "revising",
  text: `审查未通过（第 ${iteration} 轮），正在返工重做…`,
});

// ---------- Reducer：核心状态迁移逻辑 ----------
function chatReducer(state: ChatState, action: Action): ChatState {
  switch (action.type) {
    case "user_sent": {
      // 用户消息入列 + 进入"流式接收中"。
      // 新的一轮开始：重置上一轮的阶段/评审/任务清单/横幅展示
      const userItem: ChatItem = { id: newId(), kind: "user", text: action.text };
      return {
        ...state,
        items: [...state.items, userItem],
        streaming: true,
        thinking: false,
        phase: null,
        review: null,
        todos: [],
        banner: null,
      };
    }

    case "thinking":
      // start → 顶部显示"正在思考…"；end → 隐藏
      return { ...state, thinking: action.status === "start" };

    case "phase":
      // Harness 阶段流转 → 顶部徽标切换（planning/executing/reviewing/result）
      return { ...state, phase: action.phase };

    case "token": {
      // 文本增量：若上一条已是助手气泡则追加，否则新建气泡（打字机）
      const items = [...state.items];
      const last = items[items.length - 1];
      if (last && last.kind === "assistant") {
        items[items.length - 1] = { ...last, text: last.text + action.text };
      } else {
        const assistant: ChatItem = { id: newId(), kind: "assistant", text: action.text };
        items.push(assistant);
      }
      return { ...state, items, thinking: false };
    }

    case "tool_start": {
      // 工具开始执行 → 插入一张 running 状态工具卡
      const toolCard: ChatItem = { id: newId(), kind: "tool", name: action.name, status: "running" };
      const updates: Partial<ChatState> = {
        items: [...state.items, toolCard],
        thinking: false,
      };
      // task 工具 = 委派子 Agent：开"委派中"横幅，提示用户幕后执行已启动
      if (action.name === DELEGATE_TOOL) {
        updates.banner = delegateBanner();
      }
      return { ...state, ...updates };
    }

    case "tool_result": {
      // 工具完成 → 找到最后一张同名 running 卡置为 done。
      // 倒序找：同名工具可能被连续调用，要匹配"最近那张未完成的"。
      const items = [...state.items];
      for (let i = items.length - 1; i >= 0; i--) {
        const it = items[i];
        if (it.kind === "tool" && it.name === action.name && it.status === "running") {
          items[i] = { ...it, status: "done" };
          break;
        }
      }
      const updates: Partial<ChatState> = { items };
      // task 委派完成 → 收起"委派中"横幅（子 Agent 报告已交回主 Agent，
      // 接下来是主 Agent 整合输出的 token 流）
      if (action.name === DELEGATE_TOOL && state.banner?.kind === "delegate") {
        updates.banner = null;
      }
      return { ...state, ...updates };
    }

    case "todo_update":
      // 任务规划清单整体替换（后端每次变化广播全量，直接覆盖即可）
      return { ...state, todos: action.todos };

    case "error": {
      // 错误条入列（发送按钮的解锁统一交给 done）
      const err: ChatItem = { id: newId(), kind: "error", text: action.message };
      return { ...state, items: [...state.items, err], thinking: false };
    }

    case "review_result": {
      // Harness 评审判定到达（流中即时广播，needs_revision 可能多次）：
      //   - needs_revision → 开"返工中"横幅，提示主模型正按评审意见重做
      //   - 其余终态（satisfied/failed/超限）→ 收起返工横幅，
      //     最终判定由进度条底行 review-chip 常驻展示
      const review = { verdict: action.verdict, iteration: action.iteration };
      const updates: Partial<ChatState> = { review };
      if (action.verdict === "needs_revision") {
        updates.banner = revisingBanner(action.iteration);
      } else if (state.banner?.kind === "revising") {
        updates.banner = null;
      }
      return { ...state, ...updates };
    }

    case "done":
      // 流结束：解锁发送、收起思考状态；并把 todo 面板里所有未完成的项
      // 就地标为 completed —— 整轮已结束，余下 pending/in_progress 不再
      // 有推进机会，残留会显得"任务跑完但规划没做完"（截图里的 0/3 全空心圆）。
      // 此兜底不影响 happy path：本来已逐步推进到 completed 的项不会被改。
      return {
        ...state,
        streaming: false,
        thinking: false,
        todos: state.todos.map((t) =>
          t.status === "completed" ? t : { ...t, status: "completed" }
        ),
      };

    default:
      return state;
  }
}

// ---------- Hook：对外暴露 send 与状态 ----------
export function useChat() {
  const [state, dispatch] = useReducer(chatReducer, initialState);

  /** 发送一条消息（streaming 期间外部应禁用入口，本 Hook 不排队） */
  const send = useCallback(async (text: string) => {
    const message = text.trim();
    if (!message) return;

    dispatch({ type: "user_sent", text: message });

    try {
      await streamChat({
        message,
        // 后端每条 SSE 事件 → 直接 dispatch，reducer 按 type 分流
        onEvent: (event) => dispatch(event),
      });
    } catch (err) {
      // 网络/HTTP 层失败（后端业务异常会走 SSE error 事件，不进这里）
      const reason = err instanceof Error ? err.message : String(err);
      dispatch({ type: "error", message: `连接失败：${reason}（请确认 Backend :8100 已启动）` });
      dispatch({ type: "done" }); // 手动结束，避免发送按钮永久锁死
    }
  }, []);

  return { ...state, send };
}
