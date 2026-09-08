// ============================================================
// 后端 API 客户端
// ============================================================
// 职责：把"发一条消息并流式接收回复"封装成一个函数。
// 核心逻辑是旧单页里的那段 fetch 循环，这里独立成模块：
//
//   1) fetch POST /api/chat/stream（body 是 JSON —— 不能直接用
//      EventSource，因为它只支持 GET，而我们要携带 message 内容）
//   2) resp.body.getReader() 逐段读流式字节
//   3) TextDecoder 解码 → SSEParser 拆报文 → onEvent 逐个回调
//
// 前端直连 :8100 可行，因为后端已配 CORS allow_origins=["*"]。
// ============================================================

import { SSEParser } from "./sse-parser";
import type { SSEEvent } from "../types";

/**
 * 后端 API 地址解析（生产部署关键点）
 * 优先级：
 *   1. 构建期环境变量 VITE_API_BASE —— 第三方平台部署时指向真实后端，
 *      如 Vercel/Netlify 上配 VITE_API_BASE=https://api.example.com
 *   2. 同源兜底（生产）：后端与前端同域反代（Nginx/Caddy 把 /api 转给 :8100）
 *      时返回 ""，请求走相对路径 /api/chat/stream，天然无跨域
 *   3. 本地开发（vite dev）：直连 http://localhost:8100
 */
function resolveApiBase(): string {
  const fromEnv = (import.meta.env.VITE_API_BASE as string | undefined)?.trim();
  if (fromEnv) return fromEnv.replace(/\/+$/, "");
  if (!import.meta.env.DEV) return ""; // 生产同源反代 → 相对路径
  return "http://localhost:8100";
}

/** 后端 API 地址（FastAPI，生产可用 VITE_API_BASE 覆盖） */
export const API_BASE = resolveApiBase();

export interface StreamChatOptions {
  message: string; // 用户输入
  onEvent: (event: SSEEvent) => void; // 每条 SSE 事件的回调（驱动 reducer）
  signal?: AbortSignal; // 可选：外部中止（AbortController）
}

/**
 * 发送一条消息并流式接收回复。
 * 不会等全部接收完才返回——事件通过 onEvent 边收边回调（打字机效果由此而来）。
 */
export async function streamChat(options: StreamChatOptions): Promise<void> {
  const { message, onEvent, signal } = options;

  const resp = await fetch(`${API_BASE}/api/chat/stream`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ message }),
    signal, // 传空时 fetch 用默认的（不可中止）
  });
  if (!resp.ok) {
    throw new Error(`HTTP ${resp.status}`);
  }
  if (!resp.body) {
    throw new Error("浏览器不支持流式响应 (response.body 为空)");
  }

  // 流式读取循环：拿字节 → 解码 → 喂解析器 → 分发事件
  const reader = resp.body.getReader();
  const decoder = new TextDecoder();
  const parser = new SSEParser();

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    // decoder.decode(value, { stream: true })：多字节汉字可能被切到两段里，
    // stream:true 让解码器缓存跨段的半个字符，避免乱码 —— 关键细节！
    const events = parser.push(decoder.decode(value, { stream: true }));
    events.forEach(onEvent); // 一条报文一个回调，顺序与后端发射一致
  }
}
