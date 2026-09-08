"""
DAgent 企业级多智能体框架 —— Harness 编排模块（进阶机制）
============================================================
实现 Harness Engineering 架构的核心骨架：

    Planning(规划) → Executing(执行) → Reviewing(评审，不通过打回) → Result(终态)

本模块只做 4 件事：
  1. 定义强类型模型 Phase / Plan / PlanStep / ReviewResult
     （模型内聚在本文件，减少文件跳转）
  2. load_harness_config() —— 加载 harness_config.yaml（声明式 DSL）
  3. detect_task_type() / build_rubric() —— 按用户问题关键词挑评审标准
  4. HarnessPhaseMiddleware —— 阶段状态机中间件（把阶段写进 graph state）

教学要点（先读这里，再读代码）
------------------------------
1. "Harness" 不是第三方库，而是一种 Agent 架构思想：把一次任务组织成
   "规划 → 执行 → 评审"的生产线。评审不合格就退回执行重做，而不是让
   LLM 自说自话"我觉得我做完了"。
2. 阶段（phase）不再是"用正则猜 LLM 输出文本"，而是中间件在钩子
   （before_agent / after_model / after_agent）里直接写 graph state 的
   结构化字段 —— 可被 checkpoint 持久化、可被 values 流观测。
   本项目的 src/api/main.py 正是从 values 流读 phase 广播给前端。
3. 评审（review）不写进 system prompt 当软约束，而是交给框架自带的
   RubricMiddleware：它内部派一个 grader 子 Agent，按 rubric 逐条对照
   执行记录打分，产出 satisfied / needs_revision / failed 结构化判定；
   needs_revision 时框架自动把任务打回主模型重做 —— 这才是"真回路"。
4. 配置与代码分离：阶段、关键词、评审标准全在 harness_config.yaml，
   改流程 / 改评审口径不需要改代码。

运行依赖（dagent/.venv 已装 deepagents 0.7.10）：
    from langchain.agents.middleware import AgentMiddleware, Runtime
    from langchain.agents.middleware.types import AgentState
"""
from __future__ import annotations

import logging
from enum import Enum
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, Field
from typing_extensions import NotRequired

from langchain.agents.middleware import AgentMiddleware, Runtime
from langchain.agents.middleware.types import AgentState

logger = logging.getLogger("harness")

# DSL 配置文件路径（与 harness_config.yaml 同目录）
HARNESS_CONFIG_PATH = Path(__file__).parent / "harness_config.yaml"


# ============================================================
# 1) 强类型模型（Phase/Plan/PlanStep/ReviewResult）
# ============================================================

class Phase(str, Enum):
    """Harness 工作流阶段（graph state 里的结构化字段，非文本猜测）。

    说明：前端"思考中"态由 API 层的 thinking 事件表达（见 src/api/main.py），
    不占用阶段枚举；本枚举只含中间件会实际写入的 4 个阶段值。
    """
    planning = "planning"      # 规划：任务刚开始，注入评审标准
    executing = "executing"    # 执行：模型开始调用工具
    reviewing = "reviewing"    # 评审：rubric 判定需打回重做
    result = "result"          # 终态：评审通过 / 失败 / 达到上限


class PlanStep(BaseModel):
    """规划中的单个步骤（框架 TodoList 中间件的 todo 项 + 执行结果回填）"""
    id: str = Field(..., description="步骤唯一标识，如 step-0")
    content: str = Field(..., description="步骤描述")
    status: Literal["pending", "in_progress", "completed"] = "pending"
    result: str | None = Field(default=None, description="步骤执行结果摘要")


class Plan(BaseModel):
    """Planning 阶段的产物：结构化任务规划"""
    steps: list[PlanStep] = Field(default_factory=list)
    current_step: str | None = Field(default=None, description="当前执行中的步骤 id")


class ReviewResult(BaseModel):
    """Review 阶段的产物：评审器对执行结果的结构化判定。

    由 RubricMiddleware 的 grader 子 Agent 产出。
    """
    verdict: Literal[
        "satisfied", "needs_revision", "failed",
        "max_iterations_reached", "grader_error",
    ]
    explanation: str = ""
    criteria: list[dict] = Field(default_factory=list)
    iteration: int = 0


# ============================================================
# 2) 声明式配置加载（缺文件时降级，不阻塞 Agent 启动）
# ============================================================

_DEFAULT_CONFIG: dict[str, Any] = {
    "review": {"max_iterations": 3, "model": None},
    "task_types": {},
    "rubrics": {"default": "1. 完整回答用户问题\n2. 不编造数据\n3. 输出格式规范"},
}


def load_harness_config(config_path: Path | None = None) -> dict[str, Any]:
    """加载 Harness DSL 配置，文件缺失或解析失败时回退到内置默认值。

    Args:
        config_path: 配置文件路径，默认取模块目录下的 harness_config.yaml。
    """
    path = config_path or HARNESS_CONFIG_PATH
    if not path.exists():
        logger.warning("Harness config not found at %s, using defaults", path)
        return _DEFAULT_CONFIG
    try:
        with open(path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        return config if isinstance(config, dict) else _DEFAULT_CONFIG
    except Exception:
        logger.exception("Failed to parse harness config, using defaults")
        return _DEFAULT_CONFIG


# ============================================================
# 3) 任务类型识别 + rubric 生成（"什么任务配什么评审标准"）
# ============================================================

def detect_task_type(messages: list[Any], config: dict[str, Any]) -> str:
    """按最近一条用户消息命中 task_types 关键词，返回任务类型。

    多个任务类型同时命中时，取关键词命中数最多者；平票取 yaml 中
    先出现者；无命中返回 "default"。

    Args:
        messages: graph state 中的消息列表（含 human/ai/tool 消息）。
        config: load_harness_config() 的返回值。
    """
    task_types = config.get("task_types", {})
    if not task_types:
        return "default"

    user_text = ""
    for msg in reversed(messages or []):
        if getattr(msg, "type", "") == "human":
            user_text = str(getattr(msg, "content", "") or "")
            break
    if not user_text:
        return "default"

    best_type, best_score = "default", 0
    for task_type, spec in task_types.items():
        keywords = spec.get("keywords", []) if isinstance(spec, dict) else []
        score = sum(1 for kw in keywords if kw in user_text)
        if score > best_score:
            best_type, best_score = task_type, score
    return best_type


def build_rubric(task_type: str, config: dict[str, Any]) -> str:
    """按任务类型返回评审标准（rubric）字符串。

    RubricMiddleware 收到该字符串后，grader 子 Agent 逐条对照执行记录
    打分，驱动"是否重做"的判定。
    """
    rubrics = config.get("rubrics", {})
    rubric = rubrics.get(task_type) or rubrics.get("default", "")
    return rubric.strip()


def _build_plan_from_todos(todos: list | None) -> dict | None:
    """把 TodoList 中间件的 todos 转成结构化 Plan（让 Plan 模型真正生效）。

    todos 来源：TodoListMiddleware 已在 src/agent/main_agent.py 装配，
    Agent 通过 write_todos 工具维护 state.todos（见该中间件声明），
    因此本函数在 after_model / after_agent 钩子里能读到真实任务清单。

    todos 格式（框架产出）: [{content: str, status: "pending"|"in_progress"|"completed"}]
    Plan 格式（Harness 结构化）: {steps: [...], current_step}

    Returns:
        Plan.model_dump()，todos 为空时返回 None。
    """
    if not todos:
        return None

    steps: list[PlanStep] = []
    current_step: str | None = None
    for i, t in enumerate(todos):
        if not isinstance(t, dict):
            continue
        status = t.get("status", "pending")
        step = PlanStep(id=f"step-{i}", content=t.get("content", ""), status=status)
        steps.append(step)
        if status == "in_progress" and current_step is None:
            current_step = step.id

    return Plan(steps=steps, current_step=current_step).model_dump()


# ============================================================
# 4) 阶段状态机中间件（本模块的核心）
# ============================================================

class HarnessPhaseState(AgentState):
    """扩展 graph state：追加阶段 / 计划 / 评审结果三个字段。

    通过 HarnessPhaseMiddleware.state_schema 声明，框架自动合并进
    graph state，因此这些字段会出现在 values 流中（可观测）。
    """
    phase: NotRequired[str]
    """当前阶段，取值见 Phase"""
    plan: NotRequired[dict]
    """结构化任务规划（Plan.model_dump()）"""
    review_result: NotRequired[dict]
    """评审结果（ReviewResult.model_dump()）"""


class HarnessPhaseMiddleware(AgentMiddleware):
    """Harness 阶段状态机：在三个钩子里维护 phase 字段。

    三个钩子的职责（注意执行时机差异）：
    - before_agent : 每轮 agent 调用前执行 → 识别任务类型、注入 rubric、
                     置 phase=planning
    - after_model  : 模型返回后执行 → 发现模型要调工具则置 phase=executing；
                     同时把 todos 同步成结构化 plan
    - after_agent  : 整轮 agent 结束后执行 → 依据评审状态置终态 phase，
                     并组装 review_result

    与 RubricMiddleware 的配合（关键时序）：
    after_agent 钩子按【逆序】执行。RubricMiddleware 注册在本中间件
    之后，因此它的评审钩子会先跑完、把判定写进 state 的私有键
    _rubric_status，本中间件的 after_agent 再读取 —— 顺序反了就读不到。
    """

    state_schema = HarnessPhaseState

    def __init__(self, config_path: Path | None = None):
        self._config = load_harness_config(config_path)
        self.tools = []

    @property
    def name(self) -> str:
        return "HarnessPhaseMiddleware"

    def before_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        """执行前：注入 rubric + 置初始阶段为 planning。"""
        updates: dict[str, Any] = {"phase": Phase.planning.value}

        # 调用方已显式传入 rubric 时不覆盖（保留外部评审标准）
        if state.get("rubric"):
            return updates

        task_type = detect_task_type(state.get("messages", []), self._config)
        rubric = build_rubric(task_type, self._config)
        if rubric:
            updates["rubric"] = rubric
            logger.info("rubric injected (task_type=%s)", task_type)
        return updates

    def after_model(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        """模型返回后：跟踪阶段 + 同步结构化 plan。"""
        updates: dict[str, Any] = {}

        messages = state.get("messages", [])
        if messages and getattr(messages[-1], "tool_calls", None):
            updates["phase"] = Phase.executing.value

        todos = state.get("todos")
        plan = _build_plan_from_todos(todos)
        if plan:
            updates["plan"] = plan
        return updates or None

    def after_agent(self, state: Any, runtime: Runtime) -> dict[str, Any] | None:
        """执行后：按评审状态置终态阶段 + 组装结构化评审结果。"""
        updates: dict[str, Any] = {}

        status = state.get("_rubric_status")
        if status:
            evaluations = state.get("_rubric_evaluations") or []
            last = evaluations[-1] if evaluations else {}
            review_result = ReviewResult(
                verdict=status,
                explanation=last.get("explanation", ""),
                criteria=[dict(c) for c in last.get("criteria", [])],
                iteration=last.get("iteration", 0),
            )
            updates["review_result"] = review_result.model_dump()
            logger.info(
                "review verdict=%s (iteration=%s)", status, review_result.iteration
            )

        todos = state.get("todos")
        plan = _build_plan_from_todos(todos)
        if plan:
            updates["plan"] = plan

        # needs_revision → 评审未过、将打回重做 → reviewing；
        # 其余（satisfied/failed/超限/异常/无 rubric）→ 终态 result
        updates["phase"] = (
            Phase.reviewing.value if status == "needs_revision"
            else Phase.result.value
        )
        return updates
