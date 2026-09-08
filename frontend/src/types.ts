// ============================================================
// DAgent 企业级多智能体框架 —— 前端类型定义
// ============================================================
// 设计要点：
// 1. 这里的每个类型都对应后端 src/api/main.py 的 SSE 事件协议——
//    后端发什么，前端就在这里声明什么，前后端靠这套"协议"解耦。
// 2. TS 的 discriminated union（可辨识联合）：每个事件都带 type 字段，
//    前端 switch(ev.type) 分流时 TS 能自动收窄类型，
//    例如 case "token" 里 ev 自动是 TokenEvent（有 text 字段）。
// ============================================================

// ---------- SSE 事件类型（与后端 sse_event() 发射的 type 一一对应） ----------

export interface ThinkingEvent {
  type: "thinking";
  status: "start" | "end"; // start=Agent 开始思考, end=开始回答/调工具
}

export interface TokenEvent {
  type: "token";
  text: string; // 文本增量（打字机数据源）
}

export interface ToolStartEvent {
  type: "tool_start";
  name: string; // 工具名（如 supplier_search）
}

export interface ToolResultEvent {
  type: "tool_result";
  name: string; // 该工具执行完成
}

export interface ErrorEvent {
  type: "error";
  message: string; // 错误描述（后端异常兜底时发出）
}

export interface DoneEvent {
  type: "done";
  thread_id: string; // 本轮会话的线程 ID（无状态模式下由后端生成）
}

/** Harness 工作流阶段（后端从 values 流读出的结构化字段，非文本猜测） */
export type PhaseName = "planning" | "executing" | "reviewing" | "result";

export interface PhaseEvent {
  type: "phase";
  phase: PhaseName; // 阶段流转：planning → executing → (reviewing) → result
}

/** Rubric 评审判定（verdict 语义见后端 ReviewResult 模型注释） */
export type ReviewVerdict =
  | "satisfied"
  | "needs_revision"
  | "failed"
  | "max_iterations_reached"
  | "grader_error";

export interface ReviewResultEvent {
  type: "review_result";
  verdict: ReviewVerdict; // grader 子 Agent 的评审判定
  iteration: number; // 评审迭代次数
}

// ---------- 任务规划（TodoList）事件 ----------

/** 单条任务（后端从框架 state.todos 广播，status 为框架三态） */
export interface TodoItem {
  id: string; // 稳定 key（后端按 todo-N 编号）
  content: string; // 步骤描述（LLM 用 write_todos 生成，中文）
  status: "pending" | "in_progress" | "completed";
}

export interface TodoUpdateEvent {
  type: "todo_update";
  todos: TodoItem[]; // 全量清单（每次变化都广播全量，前端整体替换）
}

// ---------- 过程横幅（InterruptBanner）类型 ----------

/**
 * 过程提醒横幅（借鉴经典 Agent 工作台的 interrupt 浮层交互，但非阻塞）：
 * 本框架无 HITL（Human-in-the-Loop）中断，不需要用户"审批/补单"，
 * 因此横幅只承载两类"进行中"的过程提醒，由对应事件的到达/收尾驱动：
 *   - delegate：主 Agent 正在调用 task 委派子 Agent（tool_start task 开，
 *               tool_result task 关）
 *   - revising：评审打回、主模型正在返工（review_result needs_revision 开，
 *               下一轮 satisfied/… 或 done 关）
 */
export type BannerKind = "delegate" | "revising";

export interface Banner {
  kind: BannerKind;
  text: string; // 展示文案（reducer 里生成，中文）
}

/** SSE 事件的可辨识联合：后端可能发来的全部事件 */
export type SSEEvent =
  | ThinkingEvent
  | TokenEvent
  | ToolStartEvent
  | ToolResultEvent
  | PhaseEvent
  | ReviewResultEvent
  | TodoUpdateEvent
  | ErrorEvent
  | DoneEvent;

// ---------- 聊天记录模型（前端 UI 状态） ----------

export type ToolStatus = "running" | "done";

/**
 * 一条"渲染单元"。聊天区是流水线式的：用户消息、助手气泡、
 * 工具卡片、错误条按到达顺序排列，所以用联合类型表达四种形态。
 */
export type ChatItem =
  | { id: number; kind: "user"; text: string }
  | { id: number; kind: "assistant"; text: string }
  | { id: number; kind: "tool"; name: string; status: ToolStatus }
  | { id: number; kind: "error"; text: string };

/** 聊天区整体状态（useChat 的 reducer state） */
export interface ChatState {
  items: ChatItem[]; // 全部渲染单元（消息 + 工具卡片 + 错误）
  streaming: boolean; // 是否正在流式接收（期间禁用发送）
  thinking: boolean; // Agent 是否在"思考"（驱动顶部状态条）
  phase: PhaseName | null; // Harness 当前阶段（驱动顶部阶段徽标）
  review: { verdict: ReviewVerdict; iteration: number } | null; // 最近一次评审判定
  todos: TodoItem[]; // 任务规划清单（TodoListPanel 数据源，每轮清空）
  banner: Banner | null; // 过程提醒横幅（InterruptBanner 数据源）
}
