"""
DAgent 企业级多智能体框架 —— Agent 单例持有器
================================================
角色：全局只创建一次 Agent（创建要连 MCP、比较慢），API 层所有请求
共用一个实例。持久化 / 会话历史等能力在框架外层按需接入，
本模块只专注"单例 + 懒加载"这一个职责。

职责分工（重要）：
    - "如何组装 Agent" 在 src/agent/main_agent.py（纯工厂，无缓存）；
    - "只创建一次" 的缓存逻辑在本模块 —— 单例缓存只有这一处。

教学要点
--------
1. 单例模式（__new__ 保证只一个实例）——FastAPI 多请求共享 agent。
2. 懒加载（initialize 时才真正创建）——服务启动快，首个请求才花时间。
3. thread_id = LangGraph 会话标识。配合 checkpointer 可实现"多轮对话记忆 /
   断点续跑"；当前进程内无 checkpointer，每次对话相互独立，
   thread_id 仅作占位，展示"配置结构长什么样"。
"""
import uuid
from typing import Optional


class AgentLoader:
    """Agent 单例持有器 —— 管理 Agent 生命周期。"""

    _instance: Optional["AgentLoader"] = None

    def __new__(cls):
        # 单例：无论 new 多少次，只创建一个底层实例
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance

    def __init__(self):
        # _initialized 保证重复 __init__ 不会重置状态
        if self._initialized:
            return
        self._initialized = True
        self.agent = None  # 编译后的 LangGraph 图对象，懒加载

    async def initialize(self):
        """创建 Agent（进程内只执行一次）。

        幂等设计：重复调用时 agent 已存在则直接返回，
        避免重复连接 MCP / 重复构建图。
        方法内延迟导入 main_agent：把重依赖(deepagents/langchain)留在
        真正创建时才加载，加速 API 服务冷启动。
        """
        if self.agent is not None:
            return
        # 缓存只在"真正缺失"时调用工厂 —— 单例缓存唯一入口
        from src.agent.main_agent import create_teaching_agent

        self.agent = await create_teaching_agent()

    def create_config(self, thread_id: str) -> dict:
        """构造 LangGraph 运行配置。

        接入 checkpointer 后，这里会带上线程级配置实现会话记忆；
        当前无状态模式仅保留 thread_id 占位，展示标准结构。
        """
        return {"configurable": {"thread_id": thread_id}}

    def generate_thread_id(self) -> str:
        """生成新的会话线程 ID（每次请求一个，无状态模式）"""
        return f"thread-{uuid.uuid4().hex[:8]}"


# 全局单例（FastAPI 路由直接 import 它）
agent_loader = AgentLoader()
