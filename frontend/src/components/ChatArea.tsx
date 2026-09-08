// ============================================================
// ChatArea —— 聊天区渲染（C 工业装配线版）
// ============================================================
// 按 ChatItem.kind 渲染：
//    user      → 右侧黑底白字气泡（em 暖橙强调）
//    assistant → 左侧白底气泡（strong 锈红强调、em 衬线斜体、tnum 等宽）
//    tool      → 工业铭牌卡（黑边 + 硬阴影 + ICO 方块 + 等宽名 + tag）
//                running: 暖橙 ICO + 旋转 / done: 橄榄 ICO + ✓
//    error     → 锈红硬阴影错误条
// 自动滚动：items 每次变化都滚到底部（useEffect + ref）。
// ============================================================

import { useEffect, useRef } from "react";
import type { ChatItem } from "../types";

interface ChatAreaProps {
  items: ChatItem[];
}

export function ChatArea({ items }: ChatAreaProps) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    // 只滚动聊天容器自身，绝不用 scrollIntoView —— 后者会一路冒泡滚动
    // 外层祖先（甚至 body），导致 absolute 的 todo 面板随页面位移。
    const scroller = bottomRef.current?.parentElement;
    scroller?.scrollTo({ top: scroller.scrollHeight, behavior: "smooth" });
  }, [items]);

  return (
    <div id="chat" className="chat-area">
      {items.map((item) => {
        switch (item.kind) {
          case "user":
            return (
              <div key={item.id} className="msg user">
                <div className="role">YOU</div>
                <div className="bubble">{item.text}</div>
              </div>
            );
          case "assistant":
            return (
              <div key={item.id} className="msg assistant">
                <div className="role">AGENT</div>
                <div className="bubble">{item.text}</div>
              </div>
            );
          case "tool":
            // 工业铭牌：黑边 + 3px 硬阴影 + ICO 方块 + 名 + 状态 + tag
            return (
              <div key={item.id} className={`tool-card ${item.status}`}>
                <div className="tool-ico">
                  {item.status === "running" ? "⟳" : "✓"}
                </div>
                <div className="tool-body">
                  <div className="tool-name">{item.name}</div>
                  <div className="tool-state">
                    {item.status === "running" ? "调用中…" : "执行完成"}
                  </div>
                </div>
                <span className="tool-tag">MCP</span>
              </div>
            );
          case "error":
            return (
              <div key={item.id} className="error">
                ❌ {item.text}
              </div>
            );
        }
      })}
      <div ref={bottomRef} />
    </div>
  );
}
