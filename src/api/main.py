"""
DAgent 企业级多智能体框架 —— FastAPI 入口（浏览器 ↔ Agent 的翻译官）
======================================================================
角色：接收前端 HTTP 请求，驱动 Agent 执行，把 LangGraph 的流式产出
翻译成 SSE（Server-Sent Events）推给浏览器。

本文件职责单一：
    - 只保留 1 个流式端点 POST /api/chat/stream + 1 个健康检查
    - SSE 事件共 10 种：thinking / token / tool_start / tool_result /
      phase / review_result / todo_update / error / done
      （其中 thinking 带 status: start|end 两个状态，error 仅在异常时兜底；
       phase / review_result / todo_update 是 Harness 机制 + 规划机制的
       观测出口 —— 从 values 流读中间件写入的结构化字段后广播，
       见 src/agent/middlewares/harness.py；review_result 在流中即时广播，
       评审打回（needs_revision）时前端可立刻展示"返工中"横幅。
       ★ 终帧特判：评审一次通过时 phase 不经过 reviewing（直接 executing→result），
       为让用户看清审查过程，终帧会先补播 reviewing + 停留 REVIEW_PAUSE_SECONDS 秒
       再落 result（演示增强，真实产品应移除，见常量定义处注释））
    - 无持久化，无 resume/state/history 端点

教学要点
--------
1. SSE 报文格式：`data: <json>\n\n`（两条换行结束一条消息）。
   本版不区分 event: 字段，全走默认 message 事件，前端按 data 内 type 分流。
2. 核心循环 async for ... in agent.astream(...) 同时监听两种流：
   - stream_mode=["messages", "values"] —— 列表形式，产出
     (namespace, mode, chunk) 三元组；若传字符串则产出二元组，解包会炸。
   - "messages" 流给出 LLM 消息增量，逐 token 转发 → 打字机效果；
   - "values" 流给出每步完整 state 快照，可读到中间件写入的
     phase / review_result / todos 等结构化字段 → 广播给前端（非正则猜文本）。
     ★ values 流逐帧快照会"重复携带"同一份数据：phase 用"变化才广播"、
       todos 用"JSON 签名去重"、review_result 用"verdict+iteration 签名去重"，
       避免同一内容刷屏 —— 这是流式广播的通用去重手法。
3. 工具卡抑制：write_todos 是 TodoListMiddleware 暴露的"规划工具"，它的
   每次更新都会产生 tool_start / tool_result 消息；若原样广播，聊天区会被
   "write_todos 调用中…"刷屏，且与 todo_update 事件（任务规划面板）表达
   的信息重复。故在边界处拦截，规划进度只走 todo_update 一条通道。
4. StreamingResponse + 4 个响应头（尤其 X-Accel-Buffering: no
   关掉 Nginx 缓冲，防止流式内容被"攒着不发"导致前端假死）。
"""
import asyncio
import json
import uuid
from typing import AsyncGenerator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from src.api.agent_loader import agent_loader

# ============ FastAPI 应用 ============
app = FastAPI(title="DAgent API", version="1.0.0")

# 允许前端任意来源访问（当前前端是 Vite dev server :5173，
# 开发期直接跨域直连后端，生产应改为显式 origin 白名单）
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============ 请求模型 ============
class ChatRequest(BaseModel):
    """前端发来的对话请求体。

    message  : 用户输入的一句话
    thread_id: 可选。不传则服务端生成（无状态模式）
    """
    message: str
    thread_id: str = ""


def sse_event(event_type: str, data: dict) -> str:
    """把 (类型, 数据) 序列化成一条 SSE 报文。

    教学要点：SSE 报文 = `data: <json>\n\n`，json 里带 type 字段做分流。
    """
    payload = {"type": event_type, **data}
    return f"data: {json.dumps(payload, ensure_ascii=False)}\n\n"


# ============ Grader 反馈过滤（防御兜底） ============
# 背景：deepagents 的 RubricMiddleware 会让 grader 子 Agent 写一条 ai 消息回到
#       messages 流（feedback / correction 等），其内容是 grader 的内部评审反馈。
#       根因已在 src/agent/main_agent.py 通过传中文 system_prompt 强制 grader
#       用中文输出；此层作为兜底，万一未来 grader 漏掉中文化，聊天区也看不到。
#
# 教学要点 —— "接口边界过滤" 模式：
#   信任上游 ≠ 不做防御。系统与系统之间、流与流之间，边界处应假设"任何脏数据
#   都可能来" —— 即便来源是自家 LLM。本函数就是这个理念的具象：3 行启发式
#   关键词，挡住本不该给用户看的英文反馈。
GRADER_FEEDBACK_KEYWORDS = (
    "a grader reviewed",   # LangChain 模板首句
    "grader feedback",     # 模板小标题
    "rubric",              # 评分标准术语
    "criteria that",       # 模板小标题
    "asked for revision",  # 模板小标题
    "criteria still",      # 模板小标题
)


def _is_grader_feedback(content: object, name: str = "") -> bool:
    """判断一段消息内容是否是 RubricMiddleware grader 的内部反馈。

    两条识别线索（命中任一即跳过广播）：
    1. name == "rubric_grader" —— 框架把 grader 反馈以 HumanMessage 形式塞回
       对话流，name 固定为 rubric_grader（诊断实证：type='human' name='rubric_grader'）。
       这类消息是让主 Agent 按反馈"重做一轮"的内部指令，不是给用户的最终回答。
    2. content 命中 grader 英文模板关键词 —— 兜底：即便名字变了/未来换模板也防漏。

    review_result 事件会从 state 单独广播，前端进度条底行已能展示，无需用户看到原文。

    Returns:
        True  = 识别为 grader 反馈，不广播
        False = 正常助手回答，应广播为 token
    """
    if name == "rubric_grader":
        return True
    if not isinstance(content, str):
        return False
    lower = content.lower()
    return any(k in lower for k in GRADER_FEEDBACK_KEYWORDS)


# TodoListMiddleware 暴露的规划工具名（工具卡抑制用，见模块 docstring 第 3 条）
TODO_PLANNER_TOOL = "write_todos"

# 终态评审的"审查展示停顿"秒数（演示增强，见 stream_chat_response 终帧特判：
# 评审一次通过时 phase 从 executing 直接跳 result，用户看不到审查过程，
# 此处人为停留一段时间让"审查确实发生了"被看见；真实产品应移除该延时）
REVIEW_PAUSE_SECONDS = 5


def _todo_payload(todos: list) -> list[dict]:
    """把框架 todos（[{content, status}]）转成前端 TodoListPanel 需要的结构。

    values 流快照中的 todos 元素是 {content, status} 字典（status 三态：
    pending / in_progress / completed）。前端列表需要稳定的 key，故补 id。
    """
    payload = []
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            continue
        payload.append({
            "id": f"todo-{i}",
            "content": str(t.get("content", "")),
            "status": str(t.get("status", "pending")),
        })
    return payload


# ============ 核心：SSE 流式对话生成器 ============
async def stream_chat_response(req: ChatRequest) -> AsyncGenerator[str, None]:
    """驱动 Agent 并把流式事件翻译成 SSE 推给前端。"""
    # 1) 确保 Agent 已创建（懒加载，仅首次耗时）
    await agent_loader.initialize()
    agent = agent_loader.agent

    # 2) 准备线程配置（无状态模式：每次新 thread_id）
    thread_id = req.thread_id or agent_loader.generate_thread_id()

    # 3) 状态缓冲：工具调用的拼装变量
    tool_calls_buffer = []  # 正在进行的工具调用 [{name, args, result}]
    thinking_emitted = False
    # 已拼装给前端的助手文本（供最终兜底输出）
    assistant_text_parts: list[str] = []
    # Harness 观测变量：上一帧 phase / todos 签名 / review 签名与最新 state 快照
    #   - phase 变化才广播（避免刷屏）
    #   - todos 签名去重：values 逐帧全量携带 todos，签名相同说明没变，跳过
    #   - review 签名 = verdict + iteration：needs_revision 第 N 轮与第 N+1 轮
    #     签名不同，保证每次"打回返工"都即时广播一次
    last_phase: str | None = None
    last_todos_sig: str | None = None
    last_review_sig: str | None = None
    last_state: dict = {}

    # 4) 广播"开始思考"
    yield sse_event("thinking", {"status": "start"})

    # 5) 核心循环：astream 驱动 LangGraph 图，消费两种流
    #    - "messages" 流：LLM 消息增量 → 逐 token 转发（打字机/工具事件）
    #    - "values" 流  ：每步完整 state 快照 → 读中间件写入的
    #                      phase / review_result / todos，广播观测事件（进阶机制）
    try:
        async for namespace, chunk_type, chunk in agent.astream(
            {"messages": [("user", req.message)]},
            config=agent_loader.create_config(thread_id),
            # ★ stream_mode 必须传"列表"：列表 → 产出 (namespace, mode, chunk) 三元组
            #   若传字符串(如 "messages") → 产出 (namespace, chunk) 二元组，解包会炸
            stream_mode=["messages", "values"],
            subgraphs=True,
        ):
            # ---------- 前置隔离：子 Agent 的图内消息一律不广播 ----------
            # subgraphs=True 时，子 Agent 委派（task 工具触发的 subgraph）的
            # 消息增量也会出现在流里，且 namespace 非空（主图恒为 ()）。
            # 子 Agent 是"幕后执行者"：它的思考/token/工具调用若转发给前端，
            # 会和主 Agent 的输出混在一起造成串台（上上版 grader 泄漏同源）。
            # 它最终的结构化报告会以 tool_result 回到主 Agent，由主 Agent
            # 整合后再产出给用户的回答 —— 用户只需看到主 Agent 的输出。
            # 想看子 Agent 内部执行过程：去掉下面这行，日志里即出现
            # namespace=("supplier-analyst",...) 的消息。
            if namespace:
                continue

            # ---------- 前置分支：values 流 = state 快照（含结构化字段） ----------
            # 三个中间件往 state 写的字段都在这里观测：
            #   HarnessPhaseMiddleware → phase / plan / review_result
            #   TodoListMiddleware     → todos
            # 逐帧全量快照 → 各自"签名去重"后广播，避免同一内容反复推送
            if chunk_type == "values":
                # ① 阶段流转（变化才广播）
                phase = chunk.get("phase")
                # ② 任务规划清单（todos 签名去重 → todo_update）
                todos = chunk.get("todos")
                # ③ 评审判定（verdict+iteration 签名去重 → 流中即时广播）
                #    打回（needs_revision）时前端据此显示"返工中"横幅，
                #    不必等整轮结束 —— 这是与上一版"只在结尾广播一次"的关键差异
                review_result = chunk.get("review_result")
                rv = str(review_result.get("verdict", "")) if isinstance(review_result, dict) else ""
                it = int(review_result.get("iteration", 0) or 0) if isinstance(review_result, dict) else 0
                review_sig = f"{rv}:{it}"

                # ---------- 终帧特判：评审展示停顿（演示增强） ----------
                # 背景：只有 needs_revision 才让中间件写 phase=reviewing（打回重做）；
                #       一次通过（satisfied）等终态判定是"瞬间"的 —— phase 从
                #       executing 直接跳到 result，审查过程用户完全无感知。
                # 处理：识别"终帧"（phase=result 且 review_result 尚未广播过），
                #       人为补一段"审查中"展示序列：
                #         reviewing（进度条停在审查节点）
                #         → review_result（评审 chip 亮在底行）
                #         → sleep REVIEW_PAUSE_SECONDS 秒
                #         → result（收尾，随后 done）
                terminal_review = (
                    phase == "result"
                    and isinstance(review_result, dict)
                    and review_sig != last_review_sig
                )

                if terminal_review:
                    import sys, time as _t
                    print(f"[api] terminal branch enter @ {_t.time():.3f}", file=sys.stderr)
                    # ① 先让进度条停在"审查"（而非瞬间跳到"完成"）
                    yield sse_event("phase", {"phase": "reviewing"})
                    # ② 评审判定先亮出来，与审查节点一起被用户看到
                    last_review_sig = review_sig
                    yield sse_event("review_result", {"verdict": rv, "iteration": it})
                    # ③ 审查展示停顿（真实产品应删：评审本身是瞬间判定，
                    #    此处人为拉长以便演示"评审确实发生了"）
                    print(f"[api] sleep {REVIEW_PAUSE_SECONDS}s start @ {_t.time():.3f}", file=sys.stderr)
                    await asyncio.sleep(REVIEW_PAUSE_SECONDS)
                    print(f"[api] sleep end @ {_t.time():.3f}", file=sys.stderr)
                    # ④ 落终态
                    last_phase = phase
                    yield sse_event("phase", {"phase": phase})
                else:
                    # 常规帧 / 打回帧（needs_revision，phase=reviewing）：原逻辑
                    if phase and phase != last_phase:
                        last_phase = phase
                        yield sse_event("phase", {"phase": phase})
                    if isinstance(review_result, dict) and review_sig != last_review_sig:
                        last_review_sig = review_sig
                        yield sse_event("review_result", {"verdict": rv, "iteration": it})

                # 任务规划清单（终帧与常规帧都可能带 todo 变化，统一在此处理）
                if todos is not None:
                    todos_sig = json.dumps(todos, ensure_ascii=False, sort_keys=True)
                    if todos_sig != last_todos_sig:
                        last_todos_sig = todos_sig
                        yield sse_event("todo_update", {
                            "todos": _todo_payload(todos),
                        })

                last_state = chunk
                continue

            # 消息块结构：(message_chunk, metadata)，取第一个元素
            message_chunk = chunk[0] if isinstance(chunk, (list, tuple)) else chunk
            if message_chunk is None:
                continue

            content = getattr(message_chunk, "content", "")
            # tool_call_chunks：模型决定调工具时，参数以增量碎片到达
            tool_call_chunks = getattr(message_chunk, "tool_call_chunks", None)
            msg_type = getattr(message_chunk, "type", "")

            # ---------- 前置：首次产出"用户可见内容"时广播 thinking:end ----------
            # 三种可见内容：工具调用增量 / 工具结果 / 纯文本 token。
            # 任何一类首次到达都说明"模型已结束思考、开始行动/说话"，
            # 因此三者共享同一段 thinking:end 广播（先判定后分支，避免重复 9 行）。
            visible_content = bool(tool_call_chunks) or msg_type == "tool" or bool(content)
            if visible_content and not thinking_emitted:
                yield sse_event("thinking", {"status": "end"})
                thinking_emitted = True

            # ---------- 5a. 工具调用增量：拼装并广播 tool_start ----------
            # ★ 顺序关键：AIMessage 带 tool_call_chunks 时必须最先处理，
            #   否则其空 content 可能被后续纯文本分支误判
            if tool_call_chunks:
                for tc in tool_call_chunks:
                    if tc.get("name"):
                        # 工具名到达 → 新工具调用开始
                        tool_calls_buffer.append(
                            {"name": tc["name"], "args": "", "result": None}
                        )
                        # write_todos 是规划工具，进度交给 todo_update 事件表达，
                        # 不广播 tool_start 卡（详见模块 docstring 第 3 条）
                        if tc["name"] != TODO_PLANNER_TOOL:
                            yield sse_event("tool_start", {"name": tc["name"]})
                    if tc.get("args") and tool_calls_buffer:
                        # 参数增量到达 → 拼到最近一条
                        tool_calls_buffer[-1]["args"] += tc["args"]
                continue

            # ---------- 5b. ToolMessage：工具执行完成，广播结果 ----------
            # ★ 顺序关键：tool 消息的 content 是"工具原始返回"，必须先于
            #   纯文本分支拦截，否则会被当成助手回复原样吐给用户(上一版bug)
            if msg_type == "tool":
                tool_name = getattr(message_chunk, "name", "unknown")
                tool_result = content if isinstance(content, str) else str(content)
                # 标记对应工具调用完成
                for tc in tool_calls_buffer:
                    if tc["name"] == tool_name:
                        tc["result"] = tool_result
                        break
                # write_todos 同样抑制 tool_result 卡（与 5a 对称）
                if tool_name != TODO_PLANNER_TOOL:
                    yield sse_event("tool_result", {"name": tool_name})
                continue

            # ---------- 5c. 纯文本 token：转发给前端（打字机） ----------
            if content:
                # 5c-pre: 拦截 grader 内部反馈（详见 _is_grader_feedback 注释）
                # 评审子 Agent 写入的 HumanMessage(name=rubric_grader) 不是给用户的最终回答，
                # 跳过 token 广播；review_result 事件从 state 单独广播
                if _is_grader_feedback(content, getattr(message_chunk, "name", "")):
                    continue
                text = content if isinstance(content, str) else str(content)
                assistant_text_parts.append(text)
                yield sse_event("token", {"text": text})

    except Exception as e:
        # 异常兜底：广播 error 事件，前端提示而非白屏
        yield sse_event("error", {"message": f"Agent 执行出错: {e}"})
        # 若此前没产出任何文字，补一条错误文本，保证界面有反馈
        if not assistant_text_parts:
            yield sse_event("token", {"text": f"（出错了：{e}）"})

    # 6) 补发 todo 与 review_result 兜底：覆盖"流末广播"的边界情况
    #    ① review_result（与原逻辑一致，未广播过的最终判定补发一次）
    #    ② todos（强制再广播一次最后 state.todos）—— values 流签名去重可能
    #      因中间帧一致而漏发最末值，强制补发保证前端拿到最终快照；
    #      前端 useChat.done 还会再做一次"未完成项就地 completed"兜底，
    #      双保险避免 "任务跑完但 todo 还显示 pending" 的视觉残留。
    review_result = last_state.get("review_result")
    if isinstance(review_result, dict):
        rv = str(review_result.get("verdict", ""))
        it = int(review_result.get("iteration", 0) or 0)
        if f"{rv}:{it}" != last_review_sig:
            yield sse_event("review_result", {"verdict": rv, "iteration": it})

    final_todos = last_state.get("todos")
    if isinstance(final_todos, list):
        yield sse_event("todo_update", {"todos": _todo_payload(final_todos)})

    # 7) 广播完成
    yield sse_event("done", {"thread_id": thread_id})


# ============ HTTP 端点 ============
@app.get("/health")
def health():
    """健康检查（无 await，无需 async def）"""
    return {"status": "ok", "service": "dagent-teaching-api"}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatRequest):
    """对话端点：返回 SSE 流。

    教学要点：返回值不是 JSON 而是 StreamingResponse(media_type="text/event-stream")，
    浏览器 fetch 后要用 reader.read() 逐段读，不能当普通 JSON 解析。
    """
    return StreamingResponse(
        stream_chat_response(req),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",      # 禁止缓存（流式内容实时性）
            "Connection": "keep-alive",       # 长连接
            "X-Accel-Buffering": "no",        # 关 Nginx 缓冲（防假死）
            "Content-Type": "text/event-stream; charset=utf-8",
        },
    )


if __name__ == "__main__":
    import uvicorn
    from src.config import API_HOST, API_PORT
    uvicorn.run(app, host=API_HOST, port=API_PORT)
