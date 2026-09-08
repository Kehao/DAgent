#!/bin/zsh
# ============================================================
# DAgent 企业级多智能体框架 —— 一键启动脚本
# 启动两个服务：
#   1. MCP Server   :9100  （业务工具仓库，读虚拟数据）
#   2. Backend API  :8100  （对话流式端点）
# 前端（工程版 React+Vite）：
#   · 开发：cd frontend && npm run dev（:5173）
#   · 生产：cd frontend && npm run build → dist/ 静态托管
#
# ⚠️ 默认端口 MCP:9100 / API:8100。如需调整，改 .env 里的
#    MCP_SERVER_URL / API_PORT（本脚本按端口精确启停）
#
# 用法：
#   前台运行（两个终端各跑一半）：
#     ./start.sh mcp / ./start.sh api
#   后台一键启动：
#     ./start.sh all
#   停止：
#     ./start.sh stop
# ============================================================

cd "$(dirname "$0")"
# 关键：清掉代理环境变量 —— WorkBuddy 沙箱的 HTTP_PROXY 会劫持
# localhost 流量导致 502（开发中多次踩坑）
unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy ALL_PROXY all_proxy 2>/dev/null

VENV=.venv/bin/python
MCP_LOG=/tmp/dagent_mcp.log
API_LOG=/tmp/dagent_api.log

start_mcp() {
  echo "🚀 启动 MCP Server (:9100) → $MCP_LOG"
  nohup $VENV -m src.mcp_server.server_main > "$MCP_LOG" 2>&1 &
  echo "   PID=$!"
}

start_api() {
  echo "🚀 启动 Backend API (:8100) → $API_LOG"
  nohup $VENV -m src.api.main > "$API_LOG" 2>&1 &
  echo "   PID=$!"
}

stop_all() {
  echo "🛑 停止 DAgent 服务..."
  # ⚠️ 只能按端口杀（9100/8100），不要 pkill -f 模块名：
  #   同机若有其它进程也以 src.mcp_server.server_main 等模块名启动，
  #   用模块名匹配会误杀无关服务（曾踩坑）
  lsof -ti :9100 2>/dev/null | xargs kill 2>/dev/null
  lsof -ti :8100 2>/dev/null | xargs kill 2>/dev/null
  echo "   已停止（日志保留在 /tmp/dagent_*.log）"
}

case "${1:-all}" in
  mcp)  start_mcp ;;
  api)  start_api ;;
  all)  start_mcp; start_api; echo "📄 前端开发请运行: cd frontend && npm run dev" ;;
  stop) stop_all ;;
  *)    echo "用法: ./start.sh [mcp|api|all|stop]" ;;
esac
