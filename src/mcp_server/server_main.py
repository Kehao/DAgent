"""
DAgent 企业级多智能体框架 —— MCP Server 入口
================================================
角色：业务"工具仓库"。把采购领域的查询能力（供应商/零部件/库存）
包装成 MCP 工具，供 Agent 通过 HTTP 调用。

架构位置：
    FastAPI(:8100) → DAgent(LangGraph) → FastMCP Server(:9100, 本文件) → 虚拟数据

教学要点
--------
1. 一个 @mcp.tool() 装饰的函数 = 暴露给 Agent 的一个能力。
   - 函数名 = 工具名（Agent 按名字调用）
   - 函数 docstring = 工具说明（LLM 靠它理解"这个工具是干嘛的、参数啥意思"）
   - 类型注解 + 默认值 = 工具入参 schema（自动生成给 LLM 看）
2. 生产实现中，工具内部会请求远端 ERP 的 HTTP API（通过 erp_client 转发）；
   本仓库直接用内存虚拟数据返回，省去外部依赖，跑通链路为先。
3. transport="http" 是 streamable-http 协议（fastmcp 2.14.7 主推），
   端点路径为 /mcp（无尾斜杠）。SSE 传输已弃用（有连接关闭进程崩溃的 bug）。
"""
import json
import os
import sys

# 保证从任意目录启动都能 import 到 src 包
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", ".."))

from fastmcp import FastMCP

from src.config import MCP_SERVER_URL
from src.data.mock_data import PARTS, STOCK_WARNING_THRESHOLD, SUPPLIERS


# 创建 MCP Server 实例
# instructions: 给整个 Server 的全局说明，LLM 工具选择时会参考
mcp = FastMCP(
    name="dagent-procurement-mcp",
    instructions="摩托车零部件采购管理系统 MCP 网关（教学虚拟数据版），提供供应商、零部件、库存查询能力。",
)


def _to_json(items: list) -> str:
    """把查询结果统一序列化成 JSON 字符串（工具返回值格式）。

    提取原因：3 个工具都做同样的序列化，抽出来避免重复；
    注意 ensure_ascii=False 保证中文可读（而非 \\uXXXX 转义）。
    """
    return json.dumps(items, ensure_ascii=False, indent=2)


def _contains(text: str, keyword: str) -> bool:
    """关键字是否包含在文本里（不区分大小写）。"""
    return keyword.lower() in text.lower()


# ============ 工具 1：供应商查询 ============
@mcp.tool()
async def supplier_search(keyword: str = "", status: int | None = None) -> str:
    """根据关键字查询供应商列表（教学虚拟数据）。

    Args:
        keyword: 供应商名称关键字，如"隆鑫"、"钱江"；为空则返回全部
        status: 合作状态过滤（可选）：1=合作中, 0=已停止；不传则不过滤

    Returns:
        匹配的供应商列表 JSON
    """
    results = []
    for supplier in SUPPLIERS:
        # 关键字匹配（名称，不区分大小写）
        if keyword and not _contains(supplier["supplierName"], keyword):
            continue
        # 状态过滤
        if status is not None and supplier["status"] != status:
            continue
        results.append(supplier)
    return _to_json(results)


# ============ 工具 2：零部件查询 ============
@mcp.tool()
async def part_search(keyword: str = "", supplier_id: int | None = None) -> str:
    """根据关键字查询零部件列表（教学虚拟数据）。

    Args:
        keyword: 零部件名称关键字，如"活塞"、"轮毂"；为空则返回全部
        supplier_id: 按供应商ID过滤（可选）

    Returns:
        匹配的零部件列表 JSON，含供应商、单价、库存
    """
    results = []
    for part in PARTS:
        # 关键字匹配（名称，不区分大小写）
        if keyword and not _contains(part["partName"], keyword):
            continue
        # 供应商过滤
        if supplier_id is not None and part["supplierId"] != supplier_id:
            continue
        results.append(part)
    return _to_json(results)


# ============ 工具 3：库存预警查询 ============
@mcp.tool()
async def stock_warning(threshold: int | None = None) -> str:
    """查询库存偏低的零部件（库存预警）。

    Args:
        threshold: 预警阈值（可选，默认 100），库存低于该值的零部件会被列出

    Returns:
        库存预警清单 JSON（partCode/partName/supplierName/stock/unitPrice）
    """
    limit = threshold if threshold is not None else STOCK_WARNING_THRESHOLD
    warns = [
        {
            "partCode": part["partCode"],
            "partName": part["partName"],
            "supplierName": part["supplierName"],
            "stock": part["stock"],
            "unitPrice": part["unitPrice"],
        }
        for part in PARTS
        if part["stock"] < limit
    ]
    return _to_json(warns)


if __name__ == "__main__":
    # 端口从 MCP_SERVER_URL 提取（默认 9100），保证配置单一来源
    import urllib.parse

    _port = urllib.parse.urlparse(MCP_SERVER_URL).port or 9100
    print(f"🚀 MCP Server 启动: {MCP_SERVER_URL}/mcp (streamable-http)")
    # transport="http" = streamable-http 协议（fastmcp 2.14.7 主推）
    # 不要改回 "sse"：fastmcp 2.14.7 的 SSE 传输存在连接关闭时进程崩溃的 bug
    mcp.run(transport="http", host="0.0.0.0", port=_port)
