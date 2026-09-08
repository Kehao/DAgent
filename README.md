# DAgent —— 企业级多智能体框架

> 基于 **LangGraph + DAgent** 的企业级多智能体框架参考实现：<br>
> 主 Agent（协调者）按 `description` 将分析型任务委派给专职子 Agent，<br>
> Harness 中间件把每次任务编排成"规划 → 执行 → 评审"的生产线，<br>
> Rubric 评审器对执行结果自动打分、不达标自动打回重做。<br>
> 一条链路全部可跑：*浏览器打字 → Agent 规划 → 自主调工具 / 委派子 Agent → 评审 → 流式回答*。

## 架构总览

```
┌──────────────────┐   HTTP/SSE    ┌─────────────────┐   astream    ┌─────────────────────────┐
│  frontend/       │ ────────────▶ │  src/api/       │ ───────────▶ │  src/agent/main_agent.py │
│  React+TS+Vite   │               │  FastAPI  :8100 │              │  DAgent (LangGraph)   │
│  (Vite dev:5173) │ ◀──────────── │  SSE 翻译官     │              │  LLM qwen + 工具调度      │
└──────────────────┘   data: JSON  └─────────────────┘              └───────────┬─────────────┘
                                                            MCP tools 加载   │ 调用工具
                                                            (streamable_http) ▼
                                                                    ┌─────────────────┐
                                                                    │ src/mcp_server/ │
                                                                    │ FastMCP  :9100  │
                                                                    └────────┬────────┘
                                                                             │ 读取
                                                                    ┌────────▼────────┐
                                                                    │ src/data/       │
                                                                    │ mock_data.py    │
                                                                    │ (虚拟供应商/零件) │
                                                                    └─────────────────┘
```

一句话链路：**前端(Vite dev :5173)** → `POST /api/chat/stream`(SSE) → **FastAPI** 驱动 **DAgent(LangGraph)** → Agent 按需调用 **FastMCP(:9100)** 上的工具 → 工具读**虚拟数据** → 结果流式回到前端打字机渲染。

> 端口说明：默认 **MCP:9100 / API:8100 / 前端:5173**。可在 `.env` 里改 `MCP_SERVER_URL` / `API_PORT` 调整，多实例部署互不冲突。

## 目录结构与职责

| 目录/文件 | 角色 | 设计要点 |
|---|---|---|
| `src/mcp_server/server_main.py` | MCP Server，暴露业务工具 | `@mcp.tool()` 一个函数 = 一个能力 |
| `src/agent/main_agent.py` | 组装主 Agent | `create_deep_agent(model, tools, middleware, subagents)`：装配 TodoListMiddleware（规划）+ Harness/Rubric + 委派子 Agent |
| `src/agent/mcp_client.py` | Agent 连 MCP 拿工具 | `MultiServerMCPClient` + streamable_http |
| `src/agent/subagents/` | 子 Agent：yaml 声明式委派 | 加子 Agent = 加一个 yaml；loader 工具子串匹配 |
| `src/agent/middlewares/harness.py` + `harness_config.yaml` | Harness 中间件（阶段机 + 评审 DSL，进阶） | 规划→执行→评审→终态；rubric 不达标自动打回 |
| `src/api/main.py` | FastAPI + SSE 翻译 | `astream()` 逐 token 转发；values 流广播 phase / todo_update / review_result（10 种事件）；终帧插入审查展示停顿 |
| `src/api/agent_loader.py` | Agent 单例持有 | 懒加载 + 单例 |
| `src/data/mock_data.py` | 虚拟数据 | 内存数据替代外部系统，即开即用 |
| `src/config.py` | 环境变量总入口 | LLM/MCP 地址集中管理 |
| `tests/` | 三层单测：MCP 工具 / Harness 纯逻辑 / 子Agent loader | `pytest` 全离线，`FunctionTool.fn` 取原始函数测工具 |
| `frontend/` | React+TS+Vite 聊天页 | 见下方"前端内部结构" |

### 前端内部结构（React + TS + Vite）

| 文件 | 角色 | 要点 |
|---|---|---|
| `frontend/src/main.tsx` | React 挂载入口 | `createRoot` + StrictMode |
| `frontend/src/App.tsx` | 页面骨架 | 单向数据流组装（见下） |
| `frontend/src/types.ts` | 前后端协议类型 | SSE 事件的 discriminated union |
| `frontend/src/lib/sse-parser.ts` | SSE 粘包解析 | 半包/粘包 + buffer 累积 |
| `frontend/src/lib/api.ts` | 流式请求封装 | fetch + `reader.read()` 循环 |
| `frontend/src/hooks/useChat.ts` | 聊天状态机 | `useReducer`：一个事件一个 case；含 todos / 委派与返工横幅的状态迁移 |
| `frontend/src/components/ChatArea.tsx` | 消息气泡渲染 | 按 kind 分四种气泡 |
| `frontend/src/components/HarnessPhaseBar.tsx` | 顶部五节点阶段进度条 | 思考→规划→执行→审查→完成，当前蓝、已过绿、未到灰；评审判定 chip 嵌入底行；已过连接线流光 + 完成节点弹跳 + 标签滑入动画 |
| `frontend/src/components/TodoListPanel.tsx` | 右侧任务规划面板 | 展示 `write_todos` 产出的任务清单：进度条 + 三态图标（pending / in_progress / completed）+ 收起按钮 |
| `frontend/src/components/InterruptBanner.tsx` | 过程横幅 | 委派子 Agent / 评审返工时滑入的提示条，事件驱动开合（tool_start/result task、review_result 状态机） |
| `frontend/src/components/InputBar.tsx` | 输入区 | Enter 发送 / Shift+Enter 换行；**聚焦空输入框弹出常用提示词面板**（点击预填、可编辑后再发） |
| `frontend/src/lib/prompts.ts` | 常用提示词数据 | 按能力分组：子 Agent 委派分析 / 日常查询 / 库存与风险排查；加新建议 = 加一条数据，不动 UI |

## 快速开始

```bash
# 0. 克隆项目并进入项目根目录（后续所有命令都在根目录执行）
git clone <repo-url> && cd dagent

# 1. 创建 Python 虚拟环境并安装后端依赖
python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt -i https://pypi.tuna.tsinghua.edu.cn/simple

# 2. 配置 LLM Key
cp .env.example .env      # 填入 DASHSCOPE_API_KEY=sk-xxx

# 3. 启动 MCP Server(:9100) + Backend API(:8100)
./start.sh all

# 3.5 运行单元测试（39 个用例，不依赖任何服务，离线可跑）
./.venv/bin/python -m pytest tests/ -v

# 4. 安装前端依赖并启动 Vite 开发服务器(:5173)
cd frontend
npm install                 # 首次需要（npmmirror 镜像已配置）
npm run dev                 # 启动后自动打开，或手动访问 http://localhost:5173
```

> 两个后端服务也可分开启动：`./start.sh mcp` / `./start.sh api`；停止：`./start.sh stop`。
> 前端也可 `npm run build` 产出静态文件到 `dist/`，用任意静态服务器托管（生产形态）。

## 部署到第三方平台

架构上是**纯前端 + 两个 Python 常驻服务**，可按平台自由拆分：

```
┌────────────────────────┐   HTTPS/SSE   ┌──────────────────────┐  streamable_http  ┌─────────────────────┐
│ 静态前端 dist/          │ ────────────▶ │  FastAPI API :8100   │ ─────────────────▶ │  FastMCP Server :9100 │
│ (Vercel / CF Pages /   │              │  (Render / Fly.io /  │                    │  与 API 同机或分机    │
│  GitHub Pages / Nginx) │ ◀─────────── │   云主机 systemd)    │ ◀───────────────── │                     │
└────────────────────────┘              └──────────────────────┘                    └─────────────────────┘
```

**① 前端（静态托管，任意支持静态站点的平台）**

```bash
cd frontend
# 关键：把 API_BASE 指到真实后端（不设则生产走同源相对路径 /api/...）
VITE_API_BASE=https://api.your-domain.com npm run build
# → 产出 dist/，整目录上传托管平台即可
```

- 平台侧建环境变量 `VITE_API_BASE`（**构建期**注入，改后需重新 build）；例如 Vercel/Netlify/Cloudflare Pages 的 Project Settings → Environment Variables。
- 若后端与前端**同域**（如 Nginx/Caddy 把 `/api` 反代到 :8100），可不设该变量——构建产物自动用相对路径，无跨域问题。
- 本地想预览 build 产物并连本机后端：`VITE_API_BASE=http://localhost:8100 npm run preview`。
- 后端 CORS 当前 `allow_origins=["*"]` 仅为开发便利；生产建议在 `src/api/main.py` 收紧为真实前端域名。

**② 后端两个 Python 服务（选支持长驻进程的平台）**

```bash
# 每个平台实例执行一次（Render/Railway/Fly.io 的 Start Command 或云主机 systemd）：
python3 -m venv .venv && ./.venv/bin/pip install -r requirements.txt
cp .env.example .env      # 填 DASHSCOPE_API_KEY；API 与 MCP 分机部署时，
                          # MCP 机的 MCP_SERVER_URL 要能被 API 机访问
./.venv/bin/python -m src.mcp_server.server_main &   # MCP :9100
./.venv/bin/python -m src.api.main                   # API :8100（前台）
```

- 平台若强制单进程单端口（如 Render Web Service），可用 Nginx/Caddy 做内部反代，或把两个服务放同一容器。
- 端口可用环境变量覆盖：`API_PORT` / `MCP_SERVER_URL`（见 `src/config.py`）。
- SSE 流经反代时若被缓冲导致前端"假死"，确认反代已关闭缓冲（响应头 `X-Accel-Buffering: no` 已内置，Nginx 侧可再加 `proxy_buffering off;`）。
- 完整可复制的**单机 systemd / docker-compose** 部署模板，见上方"能力地图"演进方向（当前仓库未内置，按需再补）。

## 试试这些对话

| 输入 | 预期行为 |
|---|---|
| "查一下有哪些供应商" | Agent 调用 `supplier_search` → 列出全部在册供应商（当前 8 家） |
| "帮我看看哪些零件库存偏低了" | Agent 调用 `stock_warning` → 列出低于 100 的零件 |
| "有没有卖轮毂的供应商？" | Agent 调用 `part_search` 找轮毂 → 关联到钱江 |
| "对比分析一下这几家供应商谁更适合长期合作？" | Agent **委派子 Agent**（`task` 工具 → supplier-analyst）→ 子 Agent 自查工具出结构化对比报告 → 主 Agent 整合呈现 |
| "对比 S003 与 S005 后视镜供应商，推荐一家" | 委派 supplier-analyst → 按价格 / 供货能力 / 合作风险三维度量化对比 → 输出对比表 + 明确推荐 |
| "分析供应商信用评级、评估合作风险" | 委派 supplier-analyst → 基于评级分 / 质量合格率 / 准时交付率等量化字段评级与风险提示 |
| "你好" | Agent 纯文本回复（**不**调用工具）|

> 虚拟数据（`src/data/mock_data.py`）：**8 家供应商 / 10 种零件**，专为子 Agent 分析任务设计 ——
> 每家档案含 3 个**量化字段**（`creditScore` 评级分 / `qualityPassRate` 质量合格率 / `onTimeDeliveryRate` 准时交付率），
> 并埋了多组**同品类多货源**比价素材（火花塞 2 家、后视镜 2 家、高强度链条 3 家 65/58/70 三档），
> 让"对比多家 / 信用评级 / 供货与价格差异 / 风险与推荐"每类问题都有真实数据可查。

> 每一轮对话顶部会实时显示 **Harness 阶段进度条**：
> 思考 🧠 → 规划 📝 → 执行 ⚙️ → 审查 🔍 → 完成 ✅
> 当前阶段节点蓝底高亮 + 图标脉冲，已过节点变绿，未到节点灰色，连接线随状态变色；
> 进度条底行还会显示 **当前阶段描述**（如"正在调用工具执行任务…"）和
> **评审判定 chip**（✓评审通过 / ↻要求修改 / ⚠已达上限…）。
> 这是进阶机制 `src/agent/middlewares/harness.py` 的观测出口，不了解时忽略即可，不影响主链路使用。
>
> 同一轮还会看到 **TodoListPanel**（右侧任务清单，写 todos 后逐步勾选完成）和
> **InterruptBanner**（委派子 Agent / 评审返工时的过程横幅）。
> 审查阶段特意保留约 5 秒展示停顿（`api/main.py` 的 `REVIEW_PAUSE_SECONDS`），
> 让"评审确实发生"可见；这是演示用行为，真实产品应移除。

## 源码阅读顺序（推荐路线）

1. `src/config.py` —— 看配置怎么集中管理
2. `src/mcp_server/server_main.py` —— 看"工具"长什么样（最简单）
3. `src/agent/mcp_client.py` → `src/agent/main_agent.py` —— 看工具如何被 Agent 拿到并组装
4. `src/api/main.py` —— 看 `astream()` 如何驱动 Agent 并翻译成 SSE（**核心**）
5. `src/agent/middlewares/harness.py` + `harness_config.yaml` —— 进阶：Harness 阶段状态机 + rubric 评审
   （`middleware` 注册顺序、`after_agent` 逆序执行是关键，模块 docstring 有完整讲解）；
   `main_agent.py` 另装配了 LangChain 内置 `TodoListMiddleware`（`write_todos` 工具 →
   `state.todos`），`_build_plan_from_todos` 把它同步成结构化 plan —— 规划机制的真正数据源
6. `src/agent/subagents/` —— 进阶：子 Agent 委派。yaml 声明"人设"→ loader 子串匹配
   工具 → `create_deep_agent(subagents=...)` 自动暴露 `task` 工具；
   当前 supplier-analyst 覆盖 4 类分析任务（多供应商对比 / 信用评级 / 供货与价格差异 /
   风险与推荐），提示词里明确了量化字段读取口径；
   留意 `src/api/main.py` 循环开头 `if namespace: continue` —— 子 Agent
   是幕后执行者，它的图内消息要按 namespace 隔离，不能与主 Agent 输出串台
7. `frontend/src/lib/sse-parser.ts` → `src/lib/api.ts` —— 看浏览器如何逐段解析 SSE（打字机来源）
8. `frontend/src/hooks/useChat.ts` → `components/*` —— 看 SSE 事件如何变成界面气泡（`useReducer` 状态机）
9. `frontend/src/components/HarnessPhaseBar.tsx` —— 进阶：五节点进度条如何从后端 phase 事件还原成流水线视觉（含动画）
10. `frontend/src/components/TodoListPanel.tsx` / `InterruptBanner.tsx` / `lib/prompts.ts` —— 进阶：任务清单面板、
    委派 / 返工横幅、常用提示词入口如何消费 `todo_update`、`tool_start(task)` 等事件（`useChat.ts` reducer 是对照表）

## 框架能力地图（当前实现 vs 演进方向）

| 能力维度 | 当前实现 | 演进方向 |
|---|---|---|
| 数据源 | 内存虚拟数据（mock_data） | 接入真实 ERP / 业务系统 HTTP 接口 |
| 持久化 | 无，每轮独立 | MongoDB：会话 / checkpoint / store |
| 多 Agent 协作 | 主 Agent + Harness 阶段机 + Rubric 评审 + 专职子 Agent supplier-analyst（多供应商对比 / 信用评级 / 供货与价格差异 / 风险与推荐，8 家供应商档案带量化字段支撑） | 按需注册更多业务子 Agent（每个 = 一个 yaml） |
| 代码执行 | 无沙箱 | Docker 沙箱执行代码 |
| 前端 | React+Vite + Less + 打字机 + 五节点阶段进度条（流光 / 弹跳动画）+ TodoListPanel + InterruptBanner + 常用提示词入口 | 审批卡片 / 人工介入（HITL，需引入 checkpointer）|