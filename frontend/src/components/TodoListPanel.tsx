// ============================================================
// TodoListPanel —— 任务规划面板（C 工业装配线版 · 绝对定位可拖拽）
// ============================================================
// 数据源：后端 todo_update 事件（来自 TodoListMiddleware 维护的 state.todos）
//
// 视觉（C 工业铭牌）：
//   · 头部：黑底白字 + 暖橙编号徽章（X/Y）——整个头部是拖拽手柄
//   · 进度条：橄榄绿斜纹（45° 重复条纹，机械仪表感）
//   · 任务清单：每条带黑边方块编号（1/2/3/4）、标题 + 等宽 meta 行
//     · pending 灰边框 / 灰字
//     · in_progress 暖橙底 + 整行橙底高亮 + 阴影下陷
//     · completed 橄榄绿 + 标题删除线
//   · 收起态：小黑铭牌（带橙色"凸起"硬阴影），**同样可拖拽移动**；
//     位移 > 4px 视为拖拽（抑制展开），否则视为点击展开
//
// 定位：absolute（参照系 = .app）。默认右上角（CSS right/top）；
//       按住头部（展开态）或小铭牌（收起态）拖动后，把新的 left/top 写入
//       state → inline style 覆盖，展开面板与收起小铭牌共用同一位置，
//       来回切换不跳位。
// ============================================================

import { useCallback, useRef, useState } from "react";
import type { PointerEvent as ReactPointerEvent } from "react";
import { ListTodo, X } from "lucide-react";
import type { TodoItem } from "../types";

interface Props {
  items: TodoItem[];
  visible: boolean;
}

export default function TodoListPanel({ items, visible }: Props) {
  const [open, setOpen] = useState(true);
  // 拖拽位置：null = 未拖过（用 CSS 默认右上角）；{x,y} = 相对 .app 的左上角
  const [pos, setPos] = useState<{ x: number; y: number } | null>(null);
  const dragStart = useRef<{ px: number; py: number; sx: number; sy: number } | null>(null);
  // 本轮 pointer 会话是否发生真实拖拽（位移 > 4px）：用于区分「拖拽」与「点击展开」
  const dragMoved = useRef(false);

  // 通用拖拽：node = 当前被拖动的元素（展开面板或收起 fab），
  // clamp 用 node 实时尺寸，保证不超出视口（也不撑大 body 滚动区）
  const startDrag = useCallback(
    (e: ReactPointerEvent<HTMLElement>, node: HTMLElement | null) => {
      if (!node) return;
      e.preventDefault();
      dragMoved.current = false;
      const r = node.getBoundingClientRect();
      dragStart.current = { px: e.clientX, py: e.clientY, sx: r.left, sy: r.top };

      const onMove = (ev: PointerEvent) => {
        const d = dragStart.current;
        if (!d) return;
        const dx = ev.clientX - d.px;
        const dy = ev.clientY - d.py;
        if (Math.hypot(dx, dy) > 4) dragMoved.current = true;
        const clamp = (v: number, min: number, max: number) =>
          Math.min(Math.max(v, min), max);
        const maxX = Math.max(8, window.innerWidth - node.offsetWidth - 8);
        const maxY = Math.max(8, window.innerHeight - node.offsetHeight - 8);
        setPos({ x: clamp(d.sx + dx, 8, maxX), y: clamp(d.sy + dy, 8, maxY) });
      };
      const onUp = () => {
        dragStart.current = null;
        window.removeEventListener("pointermove", onMove);
        window.removeEventListener("pointerup", onUp);
      };
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    },
    [],
  );

  // 展开面板头部拖拽（X 收起按钮点击不触发）
  const onHeadPointerDown = useCallback(
    (e: ReactPointerEvent<HTMLElement>) => {
      if ((e.target as HTMLElement).closest("button")) return;
      startDrag(e, (e.currentTarget as HTMLElement).closest(".todo-panel") as HTMLElement);
    },
    [startDrag],
  );

  // fab 点击：拖拽过的 pointer 会话不再展开（防拖完误触发）
  const onFabClick = () => {
    if (dragMoved.current) {
      dragMoved.current = false;
      return;
    }
    setOpen(true);
  };

  if (!visible || items.length === 0) return null;

  const completedCount = items.filter((i) => i.status === "completed").length;
  const progress = (completedCount / items.length) * 100;

  // 展开面板与收起小铭牌共用同一拖拽位置：来回切换不跳位
  const posStyle = pos ? { left: pos.x, top: pos.y } : undefined;

  // 收起态：小铭牌（带橙色硬阴影；可拖拽移动，拖过则在拖到的位置显示）
  if (!open) {
    return (
      <button
        className="todo-fab"
        style={posStyle}
        onPointerDown={(e) => startDrag(e, e.currentTarget)}
        onClick={onFabClick}
        title="拖拽移动 · 点击展开"
      >
        <ListTodo size={12} />
        <span className="todo-fab-num">{completedCount}/{items.length}</span>
      </button>
    );
  }

  return (
    <div className="todo-panel" style={posStyle}>
      {/* 头部：黑底 + 暖橙 count 徽章（整行 = 拖拽手柄） */}
      <div className="todo-head" onPointerDown={onHeadPointerDown}>
        <div className="todo-title">
          <ListTodo size={12} />
          <span>任务规划</span>
        </div>
        <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
          <span className="todo-count">{completedCount}/{items.length}</span>
          <button
            onClick={() => setOpen(false)}
            title="收起"
            style={{
              background: "transparent",
              border: "none",
              color: "@paper",
              cursor: "pointer",
              padding: 0,
              display: "flex",
            }}
          >
            <X size={14} color="#f3ede0" />
          </button>
        </div>
      </div>

      {/* 斜纹进度条 */}
      <div className="todo-bar">
        <span style={{ width: `${progress}%` }} />
      </div>

      {/* 任务清单 */}
      <div className="todo-list">
        {items.map((item, idx) => {
          const status = item.status || "pending";
          const num = String(idx + 1).padStart(2, "0");
          return (
            <div key={item.id} className={`todo-item ${status}`}>
              <div className="todo-num">
                {status === "completed" ? "✓" : num}
              </div>
              <div className="todo-body">
                <div className="todo-text">{item.content}</div>
                <div className="todo-meta">
                  {status === "in_progress" ? "RUNNING · MCP:9100" : status === "completed" ? "DONE" : "PENDING"}
                </div>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
