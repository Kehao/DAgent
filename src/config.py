"""
DAgent 企业级多智能体框架 —— 全局配置模块
=============================================
本模块是项目的"环境变量总入口"，所有进程（MCP Server / Agent / API）
都从这里读取配置，避免散落硬编码。

教学要点
--------
1. 配置优先级：环境变量 > .env 文件 > 代码默认值
2. .env 文件不提交 git，只提交 .env.example（脱敏模板）
3. LLM 走 OpenAI 兼容协议，因此换任何模型厂商只改 base_url
"""
import os
from dotenv import load_dotenv

# 自动读取项目根目录的 .env 文件（若存在）
# 注意：进程的工作目录必须是项目根，否则这里读不到 —— start.sh 已处理
load_dotenv()


def get_env(key: str, default: str = "") -> str:
    """读取环境变量，去掉首尾空白（.env 里值前后可能带空格）"""
    return os.getenv(key, default).strip()


# ============ LLM 配置（通义千问，走 OpenAI 兼容接口） ============
# 全部可被环境变量覆盖：换模型厂商只需改 LLM_BASE_URL + LLM_MODEL
LLM_MODEL = get_env("LLM_MODEL", "qwen-plus")
# 阿里云百炼 DashScope 的 OpenAI 兼容端点（默认值，可在 .env 覆盖）
LLM_BASE_URL = get_env(
    "LLM_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
# API Key 从 .env 读取（DASHSCOPE_API_KEY=sk-xxx）
LLM_API_KEY = get_env("DASHSCOPE_API_KEY", "")
# 温度越低回答越稳定；0.1 适合工具调用类任务
LLM_TEMPERATURE = float(get_env("LLM_TEMPERATURE", "0.1"))
LLM_MAX_TOKENS = int(get_env("LLM_MAX_TOKENS", "4096"))


def get_llm() -> "ChatOpenAI":
    """懒加载 LLM 实例（避免模块导入时依赖未就绪）"""
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(
        model=LLM_MODEL,
        base_url=LLM_BASE_URL,
        api_key=LLM_API_KEY,
        temperature=LLM_TEMPERATURE,
        max_tokens=LLM_MAX_TOKENS,
    )


# ============ MCP Server 配置 ============
# MCP Server 监听端口（Agent 通过 HTTP 连它拿业务工具）
# 默认 9100，可在 .env 用 MCP_SERVER_URL 覆盖
MCP_SERVER_URL = get_env("MCP_SERVER_URL", "http://localhost:9100")
# streamable-http 协议的端点路径。注意：fastmcp 2.14.7 实测默认路由是
# /mcp（无尾斜杠）；若写成 /mcp/ 服务端返回 307 → langchain-mcp-adapters
# 跟随重定向时把绝对 Location 拼成 path（http%3A//...）→ 404，工具全挂。
MCP_HTTP_URL = f"{MCP_SERVER_URL}/mcp"

# ============ API 服务配置 ============
# host/port 均可被环境变量覆盖（默认 8100）
API_HOST = get_env("API_HOST", "0.0.0.0")
API_PORT = int(get_env("API_PORT", "8100"))
