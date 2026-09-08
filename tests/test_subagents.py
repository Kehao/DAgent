"""
DAgent 企业级多智能体框架 —— 子 Agent loader 单元测试
=======================================================
覆盖 src/agent/subagents/loader.py 中不依赖 LLM 的逻辑：
  1. 真 yaml 目录可加载，必填字段齐全
  2. 非法配置（缺字段 / yaml 损坏）被跳过
  3. tools"子串匹配"：pattern in tool.name
  4. 去重：同一工具被多个 pattern 命中只出现一次

运行方式（项目根目录）：
    ./.venv/bin/python -m pytest tests/test_subagents.py -v
"""
from pathlib import Path
from types import SimpleNamespace

import pytest

import src.agent.subagents.loader as loader
from src.agent.subagents.loader import (
    REQUIRED_FIELDS,
    load_subagent_configs,
    resolve_subagent_tools,
)

# 真实配置目录（本测试对真实 yaml 只读断言，不写盘）
CONFIGS_DIR = Path(__file__).parent.parent / "src" / "agent" / "subagents" / "configs"


def _fake_tool(name: str) -> SimpleNamespace:
    """构造一个最小 BaseTool 替身（resolve 只用 tool.name）。"""
    return SimpleNamespace(name=name)


# ============ 1. 真实目录加载 ============

def test_loads_real_supplier_analyst_config():
    """真实 configs/ 目录能加载 supplier-analyst 且必填字段齐全。"""
    configs = load_subagent_configs()
    assert len(configs) >= 1
    analyst = next(c for c in configs if c["name"] == "supplier-analyst")
    for field in REQUIRED_FIELDS:
        assert analyst.get(field), f"字段 {field} 缺失或为空"


# ============ 2. 非法配置跳过 ============

def test_skips_invalid_and_corrupt_configs(tmp_path, monkeypatch):
    """缺必填字段 / 非法 yaml 的配置被跳过，不影响合法配置。"""
    good = tmp_path / "good.yaml"
    good.write_text(
        "name: good-agent\n"
        "description: 好配置\n"
        "system_prompt: 你是好配置。\n"
        "tools:\n"
        "  - supplier\n",
        encoding="utf-8",
    )
    (tmp_path / "no_tools.yaml").write_text(
        "name: broken-agent\ndescription: 缺 tools\nsystem_prompt: x\n",
        encoding="utf-8",
    )
    (tmp_path / "corrupt.yaml").write_text("name: [未闭合的yaml\n", encoding="utf-8")

    monkeypatch.setattr(loader, "CONFIGS_DIR", tmp_path)
    configs = load_subagent_configs()
    assert [c["name"] for c in configs] == ["good-agent"]


# ============ 3. 工具子串匹配 ============

def test_resolve_substring_matching():
    """pattern 是子串匹配：'supplier' 命中 supplier_search / supplier_page 等。"""
    all_tools = [
        _fake_tool("supplier_search"),
        _fake_tool("supplier_page"),
        _fake_tool("part_search"),
    ]
    config = {
        "name": "x",
        "description": "d",
        "system_prompt": "s",
        "tools": ["supplier"],
    }
    specs = resolve_subagent_tools([config], all_tools)
    matched = {t.name for t in specs[0]["tools"]}
    assert matched == {"supplier_search", "supplier_page"}


def test_resolve_full_tool_name():
    """pattern 写全名 'part_search' 也只精确命中一个。"""
    all_tools = [_fake_tool("supplier_search"), _fake_tool("part_search")]
    config = {
        "name": "x", "description": "d", "system_prompt": "s",
        "tools": ["part_search"],
    }
    specs = resolve_subagent_tools([config], all_tools)
    assert [t.name for t in specs[0]["tools"]] == ["part_search"]


def test_resolve_no_match_keeps_spec_with_empty_tools():
    """无匹配时 spec 仍生成，tools 为空列表（不抛异常）。"""
    all_tools = [_fake_tool("stock_warning")]
    config = {
        "name": "x", "description": "d", "system_prompt": "s",
        "tools": ["order_"],
    }
    specs = resolve_subagent_tools([config], all_tools)
    assert specs[0]["name"] == "x"
    assert specs[0]["tools"] == []


def test_resolve_dedup_when_multiple_patterns_hit_same_tool():
    """两个 pattern 命中同一工具 → 去重只保留一次。"""
    all_tools = [_fake_tool("supplier_search")]
    config = {
        "name": "x", "description": "d", "system_prompt": "s",
        "tools": ["supplier", "search"],
    }
    specs = resolve_subagent_tools([config], all_tools)
    assert len(specs[0]["tools"]) == 1


# ============ 4. spec 结构符合 deepagents SubAgent 契约 ============

def test_spec_shape_matches_subagent_contract():
    """spec 的键与 deepagents SubAgent(TypedDict) 必需键一致。"""
    config = {
        "name": "x", "description": "d", "system_prompt": "s",
        "tools": ["supplier"],
    }
    specs = resolve_subagent_tools([config], [_fake_tool("supplier_search")])
    assert set(specs[0].keys()) == {"name", "description", "system_prompt", "tools"}
