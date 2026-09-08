"""
DAgent 企业级多智能体框架 —— Harness 纯逻辑单元测试
=====================================================
覆盖 src/agent/middlewares/harness.py 中不依赖 LLM 的 4 类逻辑：
  1. 配置加载：真 yaml 可读 / 文件缺失回退默认
  2. 任务类型识别：关键词命中 / 平票取先 / 无命中回退 default
  3. rubric 生成：任务专属优先，未知类型回退 default
  4. todos → Plan 结构化转换

运行方式（项目根目录）：
    ./.venv/bin/python -m pytest tests/ -v
"""
from pathlib import Path
from types import SimpleNamespace

from src.agent.middlewares.harness import (  # noqa: E402
    Plan,
    ReviewResult,
    _build_plan_from_todos,
    build_rubric,
    detect_task_type,
    load_harness_config,
)


def _human(text: str) -> SimpleNamespace:
    """构造一条最小 HumanMessage 替身（仅含 detect 用到的两个属性）。"""
    return SimpleNamespace(type="human", content=text)


# ---------- 1) 配置加载 ----------

def test_load_real_config():
    """真实 yaml：包含 4 个阶段与 review.max_iterations。"""
    config = load_harness_config()
    assert len(config["phases"]) == 4
    assert [p["name"] for p in config["phases"]] == [
        "planning", "executing", "reviewing", "result",
    ]
    assert config["review"]["max_iterations"] == 2


def test_load_missing_config_falls_back():
    """文件缺失：回退到内置默认值而非抛异常。"""
    config = load_harness_config(Path("/nonexistent/harness_config.yaml"))
    assert config["review"]["max_iterations"] == 3
    assert "default" in config["rubrics"]


# ---------- 2) 任务类型识别 ----------

def test_detect_hits_supplier_keywords():
    """命中 supplier 关键词（供应商/信用）→ supplier。"""
    config = load_harness_config()
    assert detect_task_type([_human("看看供应商的信用情况")], config) == "supplier"


def test_detect_no_keyword_hits_default():
    """问候语不命中任何关键词 → default。"""
    config = load_harness_config()
    assert detect_task_type([_human("你好")], config) == "default"


def test_detect_ignores_ai_messages():
    """只取最近一条 human 消息，忽略 AI 消息。"""
    config = load_harness_config()
    messages = [
        SimpleNamespace(type="ai", content="供应商信用评级如下"),
        _human("请用表格展示一下"),
    ]
    # "供应商"只出现在 ai 消息里，不得计入 → 无关键词命中
    assert detect_task_type(messages, config) == "default"


def test_detect_tie_keeps_first_in_yaml():
    """平票（analysis 与 supplier 同分）→ 取 yaml 先出现者 analysis。"""
    config = load_harness_config()
    assert detect_task_type([_human("供应商信用对比分析")], config) == "analysis"


# ---------- 3) rubric 生成 ----------

def test_build_rubric_uses_task_specific():
    """supplier 任务 → 用 supplier 专属 rubric。"""
    config = load_harness_config()
    rubric = build_rubric("supplier", config)
    assert "信用评级" in rubric and "供货能力" in rubric


def test_build_rubric_falls_back_to_default():
    """未知任务类型 → 回退 default rubric。"""
    config = load_harness_config()
    assert build_rubric("unknown_type", config) == config["rubrics"]["default"].strip()


# ---------- 4) todos → Plan 转换 ----------

def test_plan_from_todos_marks_current_step():
    """in_progress 的 todo 应成为 Plan.current_step。"""
    todos = [
        {"content": "查询供应商", "status": "completed"},
        {"content": "汇总评级", "status": "in_progress"},
    ]
    plan = _build_plan_from_todos(todos)
    assert plan is not None
    assert len(plan["steps"]) == 2
    assert plan["current_step"] == "step-1"


def test_plan_from_empty_todos_returns_none():
    """todos 为空或缺失 → 返回 None（不生成空壳 plan）。"""
    assert _build_plan_from_todos(None) is None
    assert _build_plan_from_todos([]) is None


def test_models_have_sane_defaults():
    """模型默认值：ReviewResult 空列表、Plan 空步骤。"""
    review = ReviewResult(verdict="satisfied")
    assert review.explanation == "" and review.iteration == 0
    assert Plan().steps == []


# ---------- 5) API 层：grader 反馈过滤（防御兜底） ----------
# 教学要点：本组测试是"接口边界过滤"模式的回归网。
# 根因修复在 main_agent.py（grader 中文 system_prompt），此层为兜底；
# 任何一边失效，另一边仍能保证用户看不到英文反馈。

def test_is_grader_feedback_detects_english():
    """典型英文反馈首句 → 识别为 grader 反馈。"""
    from src.api.main import _is_grader_feedback
    assert _is_grader_feedback(
        "A grader reviewed your work against the rubric and asked for revisions."
    ) is True
    assert _is_grader_feedback("Grader feedback: criteria not met") is True


def test_is_grader_feedback_detects_rubric_grader_name():
    """诊断实证：grader 反馈以 HumanMessage(name='rubric_grader') 出现。
    即便内容被未来框架改写为中文、关键词不命中，name 也稳定可识别。"""
    from src.api.main import _is_grader_feedback
    # name 命中（内容无关）
    assert _is_grader_feedback("任何内容", name="rubric_grader") is True
    # name 不命中 + 内容不命中
    assert _is_grader_feedback("任何内容", name="") is False
    assert _is_grader_feedback("任何内容", name="user") is False


def test_is_grader_feedback_skips_chinese():
    """正常中文助手回答不误判。"""
    from src.api.main import _is_grader_feedback
    assert _is_grader_feedback("您好，我是采购助手，可以帮您查供应商。") is False
    assert _is_grader_feedback("查询结果：4 家供应商信用评级如下") is False
    # 即便含"评审"二字也不应触发（关键词是英文）
    assert _is_grader_feedback("评审已通过：答案为4家供应商") is False


def test_is_grader_feedback_handles_non_string():
    """非 str 类型（list / dict / None）→ 不识别。"""
    from src.api.main import _is_grader_feedback
    assert _is_grader_feedback(None) is False
    assert _is_grader_feedback([{"text": "grader reviewed"}]) is False
    assert _is_grader_feedback({"feedback": "rubric not met"}) is False
    assert _is_grader_feedback(42) is False


def test_is_grader_feedback_partial_keyword_match():
    """关键词独立出现也命中（避免 grader 改写模板后漏网）。"""
    from src.api.main import _is_grader_feedback
    assert _is_grader_feedback("Your work fails the rubric on criterion 1.") is True
    assert _is_grader_feedback("Criteria that still need work: ...") is True
    assert _is_grader_feedback("Grader asked for revision on tone.") is True
