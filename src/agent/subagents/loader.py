"""
DAgent 企业级多智能体框架 —— 子 Agent 配置加载器
=================================================
实现"yaml 声明式注册子 Agent"，主要做 3 件事：
    1. load_subagent_configs()     扫 configs/*.yaml，校验必填字段
    2. resolve_subagent_tools()    把 yaml 里的 tools 字符串（如 "supplier"）
                                   按"子串包含"匹配成真实工具对象
    3. 返回 spec 列表直接喂给 create_deep_agent(subagents=[...])

设计要点
--------
1. 子 Agent 的"人设"（name/description/system_prompt）全在 yaml 里，
   加新子 Agent = 新增一个 yaml + 无需改代码（改流程不改代码的 DSL 思想）。
2. description 是关键：deepagents 的 SubAgentMiddleware 会把
   "- {name}: {description}" 清单自动注入主 Agent 系统提示词，
   主 Agent 正是靠 description 决定"这个任务该委派给谁"。
3. tools 用"子串匹配"（pattern in tool.name）：yaml 写 "supplier"，
   就会把 supplier_search / supplier_page / ... 全部配给该子 Agent，
   从工具集中挑选子集；本框架有 3 个采购工具，yaml 里写 "search"
   即可把三个全给子 Agent（展示子串匹配威力）。
"""
from pathlib import Path

import yaml

# 配置文件目录：本文件同级的 configs/ 文件夹
CONFIGS_DIR = Path(__file__).parent / "configs"

# 子 Agent 必填字段（缺一个或为空 → 该配置作废并告警）
REQUIRED_FIELDS = ["name", "description", "system_prompt", "tools"]


def load_subagent_configs() -> list[dict]:
    """扫描 configs/*.yaml，返回通过必填校验的配置列表。

    Returns:
        合法的子 Agent 配置字典列表（非法配置跳过并打印原因）。
    """
    configs = []
    for yaml_file in sorted(CONFIGS_DIR.glob("*.yaml")):
        try:
            with open(yaml_file, encoding="utf-8") as f:
                config = yaml.safe_load(f)
        except Exception as e:  # 读取/解析失败：跳过该文件，不影响其它
            print(f"⚠️  子Agent配置读取失败 {yaml_file.name}: {e}")
            continue

        if config and all(config.get(field) for field in REQUIRED_FIELDS):
            configs.append(config)
            print(f"✅ 已加载子Agent配置: {config['name']}")
        else:
            missing = [f for f in REQUIRED_FIELDS if not config.get(f)]
            print(f"⚠️  非法配置 {yaml_file.name}（缺少字段: {missing}），已跳过")
    return configs


def resolve_subagent_tools(
    configs: list[dict], all_tools: list
) -> list[dict]:
    """把配置里的工具字符串（pattern）子串匹配成真实工具对象。

    匹配规则：pattern in tool.name（子串包含）
    例：yaml 写 "supplier" → 匹配 name 含 "supplier" 的全部工具。
    本框架当前有 supplier_search / part_search / stock_warning 三个采购工具，
    yaml 里写 "search" 即可把三个全给子 Agent（展示子串匹配威力）。

    Args:
        configs:    load_subagent_configs() 的返回值
        all_tools:  主 Agent 已加载的全部工具（这里传 MCP 工具列表即可）

    Returns:
        deepagents SubAgent TypedDict 兼容的 spec 列表：
        [{name, description, system_prompt, tools}, ...]
    """
    specs = []
    for config in configs:
        matched = []
        for pattern in config.get("tools", []):
            for tool in all_tools:
                # 子串包含匹配 + 去重
                if pattern in tool.name and tool not in matched:
                    matched.append(tool)

        specs.append(
            {
                "name": config["name"],
                "description": config["description"],
                "system_prompt": config["system_prompt"],
                "tools": matched,
            }
        )
        print(
            f"🔧 子Agent '{config['name']}' 匹配到 {len(matched)} 个工具: "
            f"{[t.name for t in matched]}"
        )
    return specs
