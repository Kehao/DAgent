// ============================================================
// SSE 粘包解析器
// ============================================================
// 背景：后端返回 text/event-stream，字节是"一段段到达"的，
// 一条 SSE 报文可能被网络切成多段（半包），也可能多段粘在一起（粘包）。
//
// 解法：把收到的文本累积进 buffer，按 SSE 报文分隔符 \n\n 切出完整报文，
// 切不出来的残余留在 buffer 里等下一段字节到达。这是流式协议的通用解法。
// ============================================================

import type { SSEEvent } from "../types";

export class SSEParser {
  /** 累积的未处理字节（已解码为文本） */
  private buffer = "";

  /**
   * 喂入一段新到达的文本，吐出其中所有完整报文解析出的事件。
   * @param text 本次 reader.read() 解码出的增量文本
   * @returns 解析出的完整事件数组（可能为空 = 全是半包）
   */
  push(text: string): SSEEvent[] {
    this.buffer += text;
    const events: SSEEvent[] = [];

    // 循环切分：每次从 buffer 头找 \n\n，取走一条完整报文
    let idx: number;
    while ((idx = this.buffer.indexOf("\n\n")) !== -1) {
      const raw = this.buffer.slice(0, idx).trim(); // 一条完整报文原文
      this.buffer = this.buffer.slice(idx + 2); // 移除已消费部分

      // SSE 报文形如 "data: {json}\n\n"，取 data: 后的 JSON 文本
      const match = raw.match(/^data: (.*)$/s);
      if (!match) continue; // 跳过非 data 行（本框架后端只发 data）

      try {
        const payload = JSON.parse(match[1]) as SSEEvent;
        // 防御：解析出的对象必须带 type 字段才是合法事件
        if (payload && typeof payload.type === "string") {
          events.push(payload);
        }
      } catch {
        // 坏报文直接跳过 —— 流式解析不能因单条脏数据中断整条链路
      }
    }
    return events;
  }

  /** 清空残余 buffer（新一轮对话开始时调用） */
  reset(): void {
    this.buffer = "";
  }
}
