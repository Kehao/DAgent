# 阿里云 ECS 部署实录（agent.kehao.info）

> 生产环境部署到阿里云大陆 ECS 的完整记录：**前置约束（域名备案）+ 服务器环境 + systemd 启停命令**。
> 部署架构与 README「部署到第三方平台」①/② 一致：前端静态由 Nginx 托管，`/api/` 同域反代到 :8100。

## 部署清单（本机/服务器两侧）

| 内容 | 位置 / 命令 |
|---|---|
| 代码目录 | 服务器 `/opt/dagent`（本地 tar 打包 → `workbench upload` 上传解压；GitHub 直连在国内 ECS 上不稳） |
| 前端产物 | 服务器 `/var/www/agent-www`（本地 `npm run build` 后上传；**不设 `VITE_API_BASE`** → 走同源相对 `/api/`） |
| Python | 系统自带 3.10 **不够**（deepagents 0.7.10 需 ≥3.11）→ 用 python-build-standalone 装 **3.12.14** 到 `/opt/python` |
| venv | `/opt/dagent/.venv`（`/opt/python/bin/python3 -m venv .venv`） |
| 环境变量 | `/opt/dagent/.env`（由 `.env.example` 复制，填真实 `DASHSCOPE_API_KEY`） |
| Nginx 站点 | `/etc/nginx/sites-available/agent` → 软链进 `sites-enabled`；`server_name agent.kehao.info`，`listen 80 + 81` |

## 服务管理（systemd，开机自启）

```bash
# 登录服务器（root）
ssh root@47.114.36.224

# ---------- 启动 ----------
systemctl start dagent-mcp.service    # MCP Server  :9100（业务工具）
systemctl start dagent-api.service    # Backend API :8100（SSE 对话端点）
# 注：dagent-api 依赖 dagent-mcp（Unit 里 Requires/After 已声明），先起 mcp 更稳

# ---------- 停止 ----------
systemctl stop dagent-api.service
systemctl stop dagent-mcp.service

# ---------- 重启（改代码/改 .env 后） ----------
systemctl restart dagent-api.service
systemctl restart dagent-mcp.service

# ---------- 查看状态 ----------
systemctl status dagent-api.service          # 状态 + 最近日志
systemctl is-active dagent-mcp dagent-api    # 输出 active 即健康

# ---------- 查看/跟踪日志 ----------
journalctl -u dagent-api.service -f          # 实时跟踪 API 日志（-f 跟随）
journalctl -u dagent-mcp.service --no-pager | tail -50
journalctl -u dagent-api.service --since "10 min ago"

# ---------- Nginx ----------
systemctl reload nginx            # 改 nginx 配置后热加载（nginx -t 先自检）
systemctl restart nginx           # 必要时重启
nginx -t                          # 配置语法自检
```

systemd 单元模板见同目录 `dagent-mcp.service` / `dagent-api.service`，一键安装：

```bash
sudo bash doc/deploy/install.sh    # 自动装到 /etc/systemd/system + daemon-reload + enable
```

## 日常维护速查

```bash
# 更新代码：本地打包 → 上传 → 覆盖（以 2026-09 实操为准）
#   tar --exclude={.venv,node_modules,.git,.workbuddy} -czf src.tar.gz .  # 本地
#   workbench upload src.tar.gz /opt/ --instance-id <实例ID> --force        # 上传
#   tar -xzf /opt/src.tar.gz -C /opt/dagent && systemctl restart dagent-*   # 解压+重启

# 访问入口（⚠️ 域名未完成 ICP 备案前，80/443 被阿里云拦截，走 81）
#   备案完成前：http://agent.kehao.info:81/     （nginx 已 listen 81，安全组需放行 81）
#   备案完成后：http://agent.kehao.info/  （或 443 + certbot 签证书）

# 健康检查（服务器本机）
curl -s http://127.0.0.1:8100/health          # {"status":"ok",...}
curl -s http://127.0.0.1:81/health            # 经 nginx 反代同款

# 完整链路冒烟：SSE 流式对话
curl -N -X POST http://127.0.0.1:8100/api/chat/stream \
  -H 'Content-Type: application/json' \
  -d '{"message":"有哪些供应商"}'
```

> ⚠️ **ICP 备案提醒**：阿里云大陆 ECS 会对未备案域名**强制阻断 80/443**（响应 `Server: Beaver` / "Non-compliance ICP Filing"）。`agent.kehao.info` 部署时即遇此拦截——备案通过前请用 **81 端口**访问；域名备案/接入（beian.aliyun.com）审核通过后 80/443 自动放行，无需改服务器。
> ⚠️ 实例安全组需放行所用端口：本次 81 端口公网不可达就是安全组未放行所致（控制台 → ECS → 安全组 → 入方向 → TCP 81/81 允许 0.0.0.0/0）。
