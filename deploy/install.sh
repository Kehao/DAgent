#!/bin/bash
# ============================================================
# DAgent —— 安装 systemd 服务（在部署服务器上以 root 执行）
# ============================================================
# 用法：
#   sudo bash deploy/install.sh [/opt/dagent]
#     参数1（可选）：项目根目录，默认 /opt/dagent
#
# 效果：
#   1) 拷贝 deploy/dagent-mcp.service、dagent-api.service 到 /etc/systemd/system
#   2) 用 sed 把模板里的 /opt/dagent 替换为你的实际项目路径
#   3) daemon-reload + enable（开机自启）+ start（立即启动）
#
# 前置条件：
#   · 项目已就位且 venv 已建好（.venv/bin/python 存在）
#   · .env 已配置（DASHSCOPE_API_KEY 等），见 deploy 目录说明
# ============================================================
set -euo pipefail

APP_DIR="${1:-/opt/dagent}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

echo "==> 项目目录: $APP_DIR"
[ -x "$APP_DIR/.venv/bin/python" ] || { echo "✗ 未找到 $APP_DIR/.venv/bin/python，请先创建 venv"; exit 1; }
[ -f "$APP_DIR/.env" ] || { echo "✗ 未找到 $APP_DIR/.env，请先 cp .env.example .env 并填 key"; exit 1; }

for svc in dagent-mcp dagent-api; do
    echo "==> 安装 $svc.service"
    sed "s|/opt/dagent|$APP_DIR|g" "$SCRIPT_DIR/$svc.service" > "/etc/systemd/system/$svc.service"
done

echo "==> daemon-reload + enable + start"
systemctl daemon-reload
systemctl enable dagent-mcp.service dagent-api.service
systemctl start dagent-mcp.service
systemctl start dagent-api.service

echo "==> 状态："
systemctl is-active dagent-mcp dagent-api

echo "==> 完成。常用命令："
echo "    systemctl status dagent-api      # 状态"
echo "    journalctl -u dagent-api -f      # 跟踪日志"
echo "    systemctl restart dagent-*       # 改代码/.env 后重启"
