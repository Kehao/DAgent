"""
DAgent 企业级多智能体框架 —— MCP 工具单元测试
================================================
覆盖 3 个 MCP 工具（supplier_search / part_search / stock_warning）的
核心过滤逻辑。不依赖 MCP Server 运行 —— 工具内部只读 mock_data，
是"离线可跑"的单测范例。

教学要点
--------
1. @mcp.tool() 装饰后，函数不再是普通函数，而是 FastMCP 的 FunctionTool
   对象（内含 schema 等元数据），不能直接调用。
   → 用 `.fn` 属性取回"原始函数"再测试（本文件统一这么用）。
2. 工具函数是 async 的 → 用 asyncio.run() 包一层同步调用。
3. 断言围绕"过滤行为"而非实现细节：关键字/状态/供应商/阈值 四类过滤。
4. 测试数据来自 src/data/mock_data.py，测试前先读该文件了解字段。

运行方式（项目根目录）：
    ./.venv/bin/python -m pytest tests/ -v
"""
import asyncio
import json

from src.mcp_server.server_main import part_search, stock_warning, supplier_search

# @mcp.tool() 把函数包装成 FunctionTool；.fn 是其原始可调用函数
supplier_search_fn = supplier_search.fn
part_search_fn = part_search.fn
stock_warning_fn = stock_warning.fn


def test_supplier_search_keyword_filters():
    """关键字过滤：只返回名称含"隆鑫"的供应商。"""
    raw = asyncio.run(supplier_search_fn(keyword="隆鑫"))
    suppliers = json.loads(raw)
    assert len(suppliers) == 1
    assert suppliers[0]["supplierName"] == "重庆隆鑫发动机配件厂"


def test_supplier_search_keyword_empty_returns_all():
    """关键字为空 → 返回全部 8 家供应商（4 老 + 4 新比价素材）。"""
    raw = asyncio.run(supplier_search_fn(keyword=""))
    assert len(json.loads(raw)) == 8


def test_supplier_search_status_filter():
    """状态过滤：status=0 只返回已停止合作的供应商。"""
    raw = asyncio.run(supplier_search_fn(status=0))
    suppliers = json.loads(raw)
    assert len(suppliers) == 1
    assert suppliers[0]["supplierCode"] == "S004"


def test_supplier_search_no_match_returns_empty():
    """无匹配 → 返回空列表。"""
    raw = asyncio.run(supplier_search_fn(keyword="不存在的供应商"))
    assert json.loads(raw) == []


def test_part_search_supplier_filter():
    """零部件按供应商 ID 过滤。"""
    raw = asyncio.run(part_search_fn(supplier_id=1))
    parts = json.loads(raw)
    # mock_data 中 supplierId=1 的零件有 2 个（活塞环组件 + 高强度链条）
    assert len(parts) == 2
    assert all(p["supplierId"] == 1 for p in parts)


def test_part_search_keyword_filters():
    """关键字过滤：返回名称含"轮毂"的零件。"""
    raw = asyncio.run(part_search_fn(keyword="轮毂"))
    parts = json.loads(raw)
    assert len(parts) == 1
    assert parts[0]["partName"] == "铝合金轮毂"


def test_stock_warning_default_threshold():
    """默认阈值（100）：库存低于 100 的零件被列出。"""
    raw = asyncio.run(stock_warning_fn())
    warns = json.loads(raw)
    # mock_data 中库存低于 100 的有 3 个：
    # 液压减震器(80)、盘式制动卡钳(0)、鲁轻火花塞(90，低价货源风险素材)
    assert len(warns) == 3
    assert all(w["stock"] < 100 for w in warns)
    # P009 是 C 级低价供应商(鲁轻)的火花塞 —— 供子 Agent "风险提示"联动引用
    assert "P009" in {w["partCode"] for w in warns}


def test_stock_warning_custom_threshold():
    """自定义阈值（200）：库存低于 200 的零件被列出。"""
    raw = asyncio.run(stock_warning_fn(threshold=200))
    warns = json.loads(raw)
    # <200 的零件：轮毂(120)、减震器(80)、卡钳(0)、火花塞(90) 共 4 个
    assert len(warns) == 4
    assert all(w["stock"] < 200 for w in warns)


def test_stock_warning_low_threshold_returns_empty():
    """阈值设为 0：没有库存为负的零件 → 空列表。"""
    raw = asyncio.run(stock_warning_fn(threshold=0))
    assert json.loads(raw) == []


# ============ 子 Agent 比价素材（supplier-analyst 委派演示的数据基础） ============

def test_part_search_rearview_mirror_two_suppliers():
    """后视镜为"同品多货源"：大长江(S003, 55元) vs 全柴(S005, 48元)。

    子 Agent 对比"谁更适合供货后视镜"时，会同时查到 2 条记录做比价。
    """
    raw = asyncio.run(part_search_fn(keyword="后视镜"))
    parts = json.loads(raw)
    assert len(parts) == 2
    assert sorted(p["unitPrice"] for p in parts) == [48.00, 55.00]


def test_part_search_chain_three_suppliers():
    """链条为三货源：隆鑫(S001, 65元) vs 华丰(S008, 58元) vs 钱江(S002, 70元)。

    同一 partName 有三个供应商供货 → 子 Agent 可做真正的"多家（≥3）比价"。
    """
    raw = asyncio.run(part_search_fn(keyword="链条"))
    parts = json.loads(raw)
    assert len(parts) == 3
    assert sorted(p["unitPrice"] for p in parts) == [58.00, 65.00, 70.00]
    assert {p["supplierName"] for p in parts} == {
        "重庆隆鑫发动机配件厂",
        "广东华丰传动件有限公司",
        "浙江钱江摩托零部件有限公司",
    }


def test_part_search_spark_plug_two_suppliers():
    """火花塞双货源：钱江(S002, 15元) vs 鲁轻(S006, 9.5元，C级+低库存)。"""
    raw = asyncio.run(part_search_fn(keyword="火花塞"))
    parts = json.loads(raw)
    assert len(parts) == 2
    assert {p["supplierId"] for p in parts} == {2, 6}


def test_supplier_profile_has_analysis_fields():
    """供应商档案含子 Agent 对比分析所需字段（评级/供货能力/价格/交期/年限）。"""
    raw = asyncio.run(supplier_search_fn(keyword="全柴"))
    suppliers = json.loads(raw)
    assert len(suppliers) == 1
    profile = suppliers[0]
    for field in (
        "creditRating",
        "supplyCapability",
        "priceLevel",
        "deliveryLeadTimeDays",
        "cooperationYears",
    ):
        assert profile.get(field), f"供应商档案缺对比分析字段: {field}"
    # 全柴：A 级 + 低价 + 交期短但仅合作 1 年 —— "能力优秀但资历新"的权衡素材
    assert profile["creditRating"] == "A"
    assert profile["cooperationYears"] == 1


def test_supplier_search_low_rating_risk_case():
    """C 级供应商（鲁轻）可查 —— 子 Agent 报告"风险提示"一节的素材来源。"""
    raw = asyncio.run(supplier_search_fn(keyword="鲁轻"))
    suppliers = json.loads(raw)
    assert len(suppliers) == 1
    assert suppliers[0]["creditRating"] == "C"
    assert "稳定性存疑" in suppliers[0]["supplyCapability"]


# ============ 供应商量化指标（评级/风险的硬数据支撑） ============

def test_supplier_profile_has_quantified_fields():
    """供应商档案含量化指标字段：评级分 / 抽检合格率 / 准时交付率。

    子 Agent 做"信用评级分析 / 风险评估 / 供货能力排序"时，
    需要数值型硬指标支撑结论，而不是只看 A/B/C 字母评级。
    """
    raw = asyncio.run(supplier_search_fn(keyword="全柴"))
    suppliers = json.loads(raw)
    assert len(suppliers) == 1
    profile = suppliers[0]
    assert profile["creditRating"] == "A"
    assert profile["creditScore"] >= 90           # A 级对应 90+ 分
    assert profile["qualityPassRate"] >= 99.0     # 优质供应商合格率 99% 以上
    assert profile["onTimeDeliveryRate"] >= 95.0  # 交付可靠


def test_low_rating_supplier_quantified_weakness():
    """C 级供应商（鲁轻 S006）量化指标全面垫底 —— "低价但高风险"的数值依据。

    让子 Agent 推荐时能说清：不是"因为评级 C 所以风险高"，
    而是"合格率 94% / 准时率 85% 显著低于 A 级同行"。
    """
    raw_all = asyncio.run(supplier_search_fn())
    suppliers = json.loads(raw_all)
    active = [s for s in suppliers if s["status"] == 1]
    low = next(s for s in active if s["creditRating"] == "C")
    a_level = [s for s in active if s["creditRating"] == "A"]
    # C 级供应商在质量与交付两个维度都明显弱于 A 级同行
    assert low["qualityPassRate"] < min(s["qualityPassRate"] for s in a_level)
    assert low["onTimeDeliveryRate"] < min(s["onTimeDeliveryRate"] for s in a_level)
    assert low["creditScore"] < min(s["creditScore"] for s in a_level)
