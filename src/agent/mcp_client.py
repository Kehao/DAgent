"""
DAgent 企业级多智能体框架 —— MCP 工具加载（Agent 侧客户端）
============================================================
角色：在 Agent 进程内，通过 HTTP 连接 MCP Server，把远程工具
"拉"成本地可调用对象（LangChain BaseTool），交给 Agent。

架构位置：
    FastAPI(:8100) → DAgent(LangGraph) → 【本模块】 → FastMCP Server(:9100)

教学要点
--------
1. langchain-mcp-adapters 的 MultiServerMCPClient 负责握手：
   - transport="streamable_http" 对应 MCP Server 的 /mcp 端点（无尾斜杠，
     带斜杠会被 307 重定向、跟随失败 404）
   - 每个 server 配一个别名（这里叫 "procurement"）
2. get_tools() 返回的 tools 可直接作为参数传给 create_deep_agent(tools=...)。
3. 连接策略：一次连接 + 失败重试；MCP Server 不可达时降级为空工具列表，
   保证 Agent 仍能以纯对话模式运行（服务不因依赖故障而崩溃）。
"""
import asyncio

from langchain_mcp_adapters.client import MultiServerMCPClient

from src.config import MCP_HTTP_URL

# MCP Server 未启动时的重试次数与间隔
MAX_RETRIES = 3
RETRY_DELAY = 2.0  # 秒


async def load_mcp_tools() -> list:
    """连接 MCP Server 并加载全部工具。

    Returns:
        LangChain 工具列表；若 MCP Server 不可达，重试后返回空列表
        （Agent 降级为"没有工具也能对话"，不会因此崩溃）
    """
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            print(f"⏳ 尝试连接 MCP Server ({attempt}/{MAX_RETRIES}): {MCP_HTTP_URL}")
            # 单 server 连接：别名 procurement → 远程工具都以原名暴露
            client = MultiServerMCPClient(
                {
                    "procurement": {
                        "url": MCP_HTTP_URL,
                        "transport": "streamable_http",
                    }
                }
            )
            tools = await client.get_tools()
            print(f"✅ 已加载 {len(tools)} 个 MCP 工具: {[t.name for t in tools]}")
            return tools
        except Exception as e:
            print(f"⚠️  第 {attempt} 次连接失败: {e}")
            if attempt < MAX_RETRIES:
                await asyncio.sleep(RETRY_DELAY)

    print(f"❌ MCP Server 连接失败（已重试 {MAX_RETRIES} 次），Agent 将以无工具模式运行")
    return []
