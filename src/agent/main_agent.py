"""
DAgent 企业级多智能体框架 —— Agent 组装（核心中的核心）
========================================================
角色：把 LLM + 工具 + 系统提示词 组装成一个 DAgent(LangGraph 状态图)，
暴露给上层 API 调用。这是"对话 + 自主调用工具"的引擎。

注意职责分工（避免双份缓存）：
    - 本模块只负责"如何组装"（纯工厂），每次调用都新建 Agent；
    - "只创建一次"的缓存逻辑在 src/api/agent_loader.py（单例持有器）。

架构位置：
    FastAPI(:8100) → agent_loader(单例) → 【本模块 create_teaching_agent】 → LLM + MCP工具

框架能力地图（当前已实现 / 可演进方向）：
    任务规划清单（TodoList）       → 已启用：装配框架 TodoListMiddleware
                                      （write_todos 工具），复杂任务先拆解成
                                      2~5 步清单并随执行实时更新状态；API 层从
                                      values 流广播 todo_update 事件驱动前端
                                      "任务规划"面板 —— 见 src/api/main.py
    多 Agent 协作（子 Agent 委派）  → 已注册 1 个专职子 Agent supplier-analyst，
                                      见 src/agent/subagents/（yaml 声明式注册，
                                      主 Agent 按 description 委派 —— 加子 Agent
                                      只需新增一个 yaml）
    规划 → 执行 → 评审（Harness）   → 已启用：HarnessPhaseMiddleware（阶段状态机）
                                      + RubricMiddleware（评审器），见
                                      middlewares/harness.py —— 这是
                                      "规划→执行→评审"主骨架
    沙箱执行代码 / 更多业务中间件    → 演进方向：可平滑接入（当前用默认
                                      StateBackend，纯内存）
    会话持久化（checkpointer/store）→ 演进方向：接入 MongoDB 等实现多轮记忆
                                      （当前进程内存即忘）

教学要点
--------
1. create_deep_agent() = LangGraph 的 create_agent() 的"深度"封装，
   返回一个可被 astream() 驱动的图对象。
2. 三个最核心参数：
   - model        : LLM 实例（默认阿里云通义千问 qwen-plus，可在 config.py 换厂商）
   - tools        : 工具列表（来自 MCP Server 的 3 个采购查询工具）
   - system_prompt: 给 Agent 的"人设 + 行为准则"，决定它怎么用工具
3. Agent 本质：循环 [LLM 思考 → 决定调用哪个工具 → 看结果 → 再思考…]
   直到认为任务完成。这个循环由框架驱动，我们只负责"喂工具和提示词"。
"""
from src.agent.mcp_client import load_mcp_tools
from src.config import MCP_SERVER_URL, get_llm

# ============ 系统提示词 ============
# 要点：提示词决定 Agent 的行为边界。
# 企业级 Agent 的提示词通常会展开到几百行（人设/工具协议/输出规范/委派协议），
# 这里浓缩为"角色 + 能力范围 + 行为准则 + 委派原则"，保持可读可演。
# 第 5 条委派原则是子 Agent 机制的"开关"：不写它，模型倾向自己调工具；
# 写了它，模型才把 task 工具纳入决策（可删掉该条对比委派触发率）。
# 第 6 条任务规划原则是 TodoList 机制的"引导"：write_todos 工具自带英文
# 使用说明，但何时用取决于模型判断；明示"多步任务先建清单"可显著提高
# 触发率，让"任务规划"面板在演示中稳定出现。
MAIN_SYSTEM_PROMPT = """\
你是一个专业的摩托车零部件采购助手，隶属于某摩托车制造企业的采购部。

你的能力：
- 你可以通过 MCP 工具查询供应商信息（supplier_search）、
  零部件信息（part_search）、库存预警（stock_warning）。
- 数据源是"教学虚拟数据库"，查询结果以 JSON 返回。
- 你还拥有 write_todos（任务清单）与 task（子 Agent 委派）两个规划工具。

你的行为准则：
1. 用户问题涉及"供应商 / 零部件 / 库存"时，必须先调用相应工具
   获取真实数据，再基于数据回答，不要凭空编造。
2. 查询结果用简洁、结构化的中文呈现（可用列表/小表格排版）。
3. 如果用户的问题超出你的能力范围，礼貌说明你只会处理采购查询。
4. 回答保持专业、克制，不闲聊发挥。
5. ★委派原则：当用户要求"对比多家供应商 / 分析供应商信用评级或供货能力 /
   推荐最合适的供应商 / 评估合作风险"这类**分析型任务**时，
   不要自己逐个调查询工具，而是直接调用 **task 工具**，把任务
   委派给系统提示中列出的 supplier-analyst 子 Agent；
   拿到它返回的结构化报告后，再整合成面向用户的最终中文回答。
   反之，普通查询（"有哪些供应商""某零件谁在卖"）保持自己直接调用。
6. ★任务规划原则：凡涉及多步执行的任务（典型如第 5 条的分析型任务：
   拆解为"明确需求→收集供应商档案→对比评分→给出推荐"等 2~5 步），
   动手前**先调用 write_todos 建立任务清单**（步骤内容用中文），
   随后每完成一步立即调用 write_todos 把对应项标记为 completed，
   让用户全程看到你的执行计划与进度。
"""


# ============ 评审器 system_prompt（强制中文反馈） ============
# 根因：deepagents 的 RubricMiddleware 默认 grader 用英文写 feedback / correction
#       等文本字段，会以 ai 消息形式回到 messages 流，前端可能误当成"助手回答"
#       展示给用户（看不懂英文、困惑"为什么有英文"）。
# 修复：覆盖 grader 默认 system_prompt，强制要求反馈文本字段用中文。
# 注意：verdict 字段是 LangChain 的 Pydantic 字面量（satisfied / needs_revision /
#       failed / max_iterations_reached / grader_error），不能翻译；只约束文本字段。
# 兜底：API 层 src/api/main.py 的 _is_grader_feedback() 仍做英文关键词识别，
#       双保险。
GRADER_SYSTEM_PROMPT = """\
你是一名严格的评审员，对助手的回答按评分标准（rubric）逐条评判。

要求：
1. verdict 字段保留英文字面量：satisfied / needs_revision / failed（框架约束，不可改）
2. 其余所有文本字段（feedback / correction / 逐条说明）必须全部用中文
3. 行文简洁，按评分点逐条罗列"达标 / 未达标 + 原因"
4. 严禁使用英文段落描述，避免最终用户在前端聊天区看到非中文反馈
"""


async def create_teaching_agent():
    """组装框架主 Agent（纯工厂，不做缓存）。

    完整流程：
      1. 拿 LLM 实例
      2. 连 MCP Server 加载工具（连不上则空工具，Agent 仍可对话）
      3. 组装并返回可 astream 的图对象

    调用方注意：本函数每次都会新建 Agent（成本较高，需连 MCP + 初始化图），
    业务层应复用其结果 —— 见 agent_loader.initialize() 的单例缓存。

    Returns:
        CompiledStateGraph —— LangGraph 编译后的可执行图
    """
    print("🤖 正在创建教学 Agent ...")
    print(f"   LLM     : qwen-plus (DashScope)")
    print(f"   MCP URL : {MCP_SERVER_URL}")

    from deepagents import RubricMiddleware, create_deep_agent

    # Harness 阶段状态机 + 评审器（进阶机制）：
    #   - TodoListMiddleware     : 给 Agent 暴露 write_todos 工具，复杂任务先拆解成
    #                              步骤清单（写入 graph state.todos）—— 前端"任务
    #                              规划"面板的数据源；HarnessPhaseMiddleware 还会把
    #                              todos 同步成结构化 plan（见 harness.py）
    #   - HarnessPhaseMiddleware : 把 phase/plan/review_result 写进 graph state
    #   - RubricMiddleware       : 框架自带评审器，rubric 不达标自动打回主模型重做
    # 中间件注册顺序是关键：after_agent 钩子按逆序执行，评审器须注册在
    # 阶段中间件之后，其判定才能被阶段中间件读到（详见 harness.py）。
    # 评审迭代上限从 harness_config.yaml 读取 —— 改配置即改评审力度。
    from langchain.agents.middleware import TodoListMiddleware
    from src.agent.middlewares.harness import (
        HarnessPhaseMiddleware,
        load_harness_config,
    )

    harness_config = load_harness_config()
    max_review_iterations = harness_config.get("review", {}).get(
        "max_iterations", 3
    )

    # 1) LLM
    llm = get_llm()

    # 2) MCP 工具（连接失败时返回空列表，Agent 降级为纯对话）
    mcp_tools = await load_mcp_tools()

    # 2.5) 子 Agent 装配（进阶机制）：
    #   - configs/supplier_analyst.yaml 声明"人设 + 可用工具"（DSL，改配置即加子Agent）
    #   - loader 做 yaml → 校验 → 工具"子串匹配" → deepagents SubAgent spec 列表
    #   - create_deep_agent(subagents=...) 内部注册 SubAgentMiddleware：
    #     自动给主 Agent 暴露 task 工具 + 注入 "- 名字: 描述" 委派清单，
    #     主 Agent 按 description 决定"这活派给谁"
    # 框架当前演示 1 个子 Agent；想要第 2 个 → 在 configs/ 里再加一个 yaml
    from src.agent.subagents.loader import (
        load_subagent_configs,
        resolve_subagent_tools,
    )

    subagent_specs = resolve_subagent_tools(
        load_subagent_configs(), mcp_tools
    )

    # 3) 组装 Agent
    #    不传 backend → 框架默认用 StateBackend（纯内存状态，无需 Docker）
    #    不传 checkpointer/store → 无持久化，每次调用相互独立（教学够用）
    agent = create_deep_agent(
        model=llm,
        tools=mcp_tools,
        system_prompt=MAIN_SYSTEM_PROMPT,
        middleware=[
            # 规划中间件放最前：它为图补充 todos state 字段（OmitFromInput），
            # 与 HarnessPhaseState 的 plan 字段经框架自动合并，values 流可见
            TodoListMiddleware(),
            HarnessPhaseMiddleware(),
            # system_prompt 强制 grader feedback 用中文 —— 详见模块顶部 GRADER_SYSTEM_PROMPT 注释
            RubricMiddleware(
                model=llm,
                max_iterations=max_review_iterations,
                system_prompt=GRADER_SYSTEM_PROMPT,
            ),
        ],
        subagents=subagent_specs or None,  # 无合法配置时退化为单 Agent
        name="teaching-procurement-agent",
    )

    print(f"✅ Agent 创建完成，携带 {len(mcp_tools)} 个 MCP 工具")
    print(f"   子 Agent 数量   : {len(subagent_specs)}")
    print(f"   Harness 评审上限 : {max_review_iterations} 次")
    return agent
