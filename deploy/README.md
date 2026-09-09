# DAgent 生产部署文件（阿里云 ECS 实测）

DAgent 是**纯前端 + 两个 Python 常驻服务**，本目录提供在单机（systemd）上
一键复刻生产部署所需的全部文件。

| 文件 | 作用 |
|---|---|
| `dagent-mcp.service` | MCP Server（:9100，业务工具仓库）的 systemd 单元模板 |
| `dagent-api.service`  | Backend API（:8100，SSE 对话端点）的 systemd 单元模板 |
| `install.sh`          | 一键安装脚本：拷贝单元 → 替换路径 → daemon-reload → enable → start |

## 快速安装（服务器上）

```bash
# 前置：项目已就位 + venv 已建 + .env 已填
# 例如项目在 /opt/dagent：
sudo bash /opt/dagent/deploy/install.sh /opt/dagent
```

## 单元文件关键点

- `WorkingDirectory=<项目根>`：`src/config.py` 的 `load_dotenv()` 靠它读到 `.env`
- `EnvironmentFile=<项目根>/.env`：把配置注入进程环境
- `ExecStart=<venv python> -m src.xxx`：用 venv 解释器运行（本仓库需 Python ≥3.11）
- `Restart=always`：崩溃自动拉起
- `dagent-api` 带 `Requires/After=dagent-mcp`：确保 MCP 先起，Agent 初始化能连到 :9100

## 常用运维命令

```bash
systemctl start/stop/restart dagent-mcp dagent-api   # 启停/重启
systemctl status dagent-api                          # 状态
journalctl -u dagent-api -f                          # 实时日志
curl -s http://127.0.0.1:8100/health                # 健康检查
```

## 配套：Nginx 站点（同域反代 /api）

前端静态托管 + `/api/` 反代到 `127.0.0.1:8100` 的 Nginx 配置示例
与完整部署实录见仓库 README 的「阿里云 ECS 部署实录」章节。
