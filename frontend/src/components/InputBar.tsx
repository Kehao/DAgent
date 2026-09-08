// ============================================================
// InputBar —— 输入区（C 工业装配线版）
// ============================================================
// 视觉：黑底 "INPUT" 铭牌 + 黑边输入框（focus 时暖橙高亮） + 暖橙 send 按钮
//       （带 3px 黑色硬阴影，按下时下沉）
//
// 交互规则（保持不变）：
//   - Enter 发送；Shift + Enter 换行
//   - 流式接收中或输入为空时禁用发送
//   - 聚焦 + 输入为空 → 弹出"常用提示词"面板（点击预填，可再编辑）
// ============================================================

import { useRef, useState } from "react";
import type { KeyboardEvent } from "react";
import { Search, Bot, AlertTriangle, Sparkles } from "lucide-react";
import {
  PROMPT_GROUP_LABEL,
  PROMPT_GROUP_ORDER,
  PROMPT_PANEL_HINT,
  PROMPT_SUGGESTIONS,
  type PromptGroupKey,
  type PromptSuggestion,
} from "../lib/prompts";

interface InputBarProps {
  onSend: (text: string) => void;
  streaming: boolean;
}

const GROUP_ICON: Record<PromptGroupKey, typeof Search> = {
  subagent: Bot,
  query: Search,
  risk: AlertTriangle,
};

export function InputBar({ onSend, streaming }: InputBarProps) {
  const [text, setText] = useState("");
  const [focused, setFocused] = useState(false);
  const taRef = useRef<HTMLTextAreaElement>(null);

  const canSend = text.trim().length > 0 && !streaming;
  const suggestOpen = focused && text.trim() === "" && !streaming;

  const handleSend = () => {
    if (!canSend) return;
    onSend(text);
    setText("");
  };

  const handleKeyDown = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const handlePick = (s: PromptSuggestion) => {
    setText(s.text);
    taRef.current?.focus();
  };

  return (
    <footer className="input-bar">
      <div className="input-field">
        {suggestOpen && (
          <div
            className="prompt-suggest"
            onMouseDown={(e) => e.preventDefault()}
            role="listbox"
            aria-label="常用提示词"
          >
            <div className="prompt-head">
              <div className="prompt-title">
                <Sparkles size={12} color="#e8772e" />
                <span>试试这样问</span>
                <span className="prompt-badge">15 PROMPTS</span>
              </div>
              <span className="prompt-hint">{PROMPT_PANEL_HINT}</span>
            </div>

            {PROMPT_GROUP_ORDER.map((g, gIdx) => {
              const items = PROMPT_SUGGESTIONS.filter((s) => s.group === g);
              if (items.length === 0) return null;
              const Icon = GROUP_ICON[g];
              const num = String(gIdx + 1).padStart(2, "0");
              return (
                <section className="prompt-group" key={g}>
                  <div className="prompt-group-title">
                    <span className="prompt-num">{num}</span>
                    <Icon size={11} />
                    <span>{PROMPT_GROUP_LABEL[g]}</span>
                  </div>
                  {items.map((s) => (
                    <button
                      key={s.id}
                      type="button"
                      role="option"
                      className="prompt-item"
                      onClick={() => handlePick(s)}
                    >
                      {s.text}
                    </button>
                  ))}
                </section>
              );
            })}
          </div>
        )}

        <div className="input-label">INPUT</div>
        <textarea
          ref={taRef}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onFocus={() => setFocused(true)}
          onBlur={() => setFocused(false)}
          onKeyDown={handleKeyDown}
          placeholder="点击输入框查看常用提问示例；也可直接提问（Enter 发送，Shift+Enter 换行）"
          rows={2}
        />
      </div>

      <button
        type="button"
        className="send-btn"
        onClick={handleSend}
        disabled={!canSend}
      >
        {streaming ? "RUN…" : "SEND ➤"}
      </button>
    </footer>
  );
}
