// ============================================================
// App —— 页面骨架
// ============================================================
// 组件树：
//   App
//   ├── header（标题 + 架构说明）
//   ├── HarnessPhaseBar（Agent 运行阶段进度条：
//   │       思考 → 规划 → 执行 → 审查 → 完成，
//   │       由 thinking / phase 状态推导显示到哪一步）
//   ├── InterruptBanner（过程提醒横幅：子 Agent 委派中 / 评审返工中，
//   │       由 todo/task 与 review_result 事件驱动开合）
//   ├── ChatArea（聊天区，props: items）
//   ├── TodoListPanel（任务规划面板：绝对定位 + 可拖拽移动，Agent 拆解的
//   │       执行步骤清单 + 实时进度，数据源 = todo_update 事件）
//   └── InputBar（输入区，props: onSend / streaming）
//
// 状态全部由 useChat 托管，App 只是"组装者"——单向数据流：
//   InputBar.onSend → useChat.send → 后端事件 → reducer → items → ChatArea
// ============================================================

import { useChat } from "./hooks/useChat";
import { ChatArea } from "./components/ChatArea";
import { InputBar } from "./components/InputBar";
import HarnessPhaseBar, { type DisplayPhase } from "./components/HarnessPhaseBar";
import InterruptBanner from "./components/InterruptBanner";
import TodoListPanel from "./components/TodoListPanel";
import type { PhaseName } from "./types";

/**
 * 把 useChat 的原始状态翻译成进度条认识的阶段键。
 *
 * 为什么在这里做翻译而不让 reducer 直接存阶段键？
 *   后端事件只表达"事实"（thinking 布尔、phase 四态），而进度条需要
 *   "五节点完整流水线"。把 thinking + phase 归一化成一条进度线，
 *   属于 UI 展示层语义 —— 放组件边界做，reducer 保持与后端协议 1:1。
 *
 * 归一化规则（优先级从高到低）：
 *   1. phase === "result" → "done"  —— 后端收官（评审走完）即整个工作流完成
 *   2. phase 有值          → 同名    —— planning / executing / reviewing 直接对应
 *   3. thinking / 刚发出   → "thinking"（等待首个事件期间按思考算）
 *   4. 否则                → "idle"  —— 未开始，进度条不渲染
 */
function toDisplayPhase(
  thinking: boolean,
  phase: PhaseName | null,
  streaming: boolean,
): DisplayPhase {
  if (phase === "result") return "done";
  if (phase) return phase;
  if (thinking || streaming) return "thinking";
  return "idle";
}

export default function App() {
  // 单一状态源：消息列表 + streaming + thinking + phase + review
  //             + todos（任务规划清单）+ banner（过程横幅）+ send
  const { items, streaming, thinking, phase, review, todos, banner, send } = useChat();

  const displayPhase = toDisplayPhase(thinking, phase, streaming);
  // 进度条可见规则：流式进行中显示；或上一轮已到"完成"也保留展示
  const phaseBarVisible = streaming || displayPhase === "done";

  return (
    <div className="app">
      <header>
        <div className="logo">D</div>
        <div className="titles">
          <div className="t1">DAgent <em>·</em> 企业级多智能体框架</div>
          <div className="t2">摩托车零部件采购助手 · Multi-Agent Procurement Console</div>
        </div>
        <div className="meta">
          <div className="item"><span className="dot"></span>API <span className="v">:8100</span> · <span className="v">ONLINE</span></div>
          <div className="item">MCP <span className="v">:9100</span></div>
          <div className="item">LLM <span className="v">qwen-plus</span></div>
          <div className="item">SSE <span className="v">9</span> events</div>
        </div>
        {/* 架构明细行 1（链路）：等宽 mono + 工业 chip */}
        <p className="arch">
          <span className="lbl">链路</span>
          <span className="chip">React 19 · Vite :5173</span>
          <span className="chip run"><span style={{ width: 5, height: 5, borderRadius: "50%", background: "@orange", display: "inline-block" }}></span>SSE astream</span>
          <span className="arrow">→</span>
          <span className="chip">FastAPI :8100</span>
          <span className="arrow">→</span>
          <span className="chip">DAgent · LangGraph</span>
          <span className="arrow">→</span>
          <span className="chip">FastMCP :9100</span>
          <span className="arrow">→</span>
          <span className="chip">mock · 8 供应商 / 11 零件</span>
        </p>
        {/* 架构明细行 2（编排）：单独一行 */}
        <p className="arch arch-2">
          <span className="lbl">编排</span>
          <span className="chip">write_todos</span>
          <span className="chip">Harness 阶段机</span>
          <span className="chip">Rubric 评审</span>
          <span className="arrow">→</span>
          <span className="chip">supplier-analyst 子 Agent</span>
        </p>
      </header>

      {/* Harness 阶段进度条：思考→规划→执行→审查→完成 */}
      <HarnessPhaseBar
        phase={displayPhase}
        visible={phaseBarVisible}
        review={review}
      />

      {/* 过程提醒横幅：委派子 Agent / 评审返工（无横幅时为 null，不占位） */}
      <InterruptBanner banner={banner} />

      {/* 聊天消息区 */}
      <ChatArea items={items} />

      {/* 任务规划面板：绝对定位可拖拽（按住头部拖动到任意位置） */}
      <TodoListPanel items={todos} visible={phaseBarVisible} />

      {/* 输入区：streaming 期间禁用发送 */}
      <InputBar onSend={send} streaming={streaming} />
    </div>
  );
}
