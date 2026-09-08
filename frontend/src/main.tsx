// ============================================================
// main.tsx —— React 挂载入口
// ============================================================
// Vite 的入口约定：index.html 里 <script type="module" src="/src/main.tsx">
// 指向这里。职责只有一件：把 <App /> 渲染进 <div id="root">。
//
// StrictMode：
//   React 开发模式的"双执行"检查器（渲染函数会被调用两次以暴露副作用 bug）。
//   聊天请求只在用户点击时触发（事件处理器不双跑），故可安全开启。
// ============================================================

import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import App from "./App";
import "./styles.less"; // 全局样式（Less：变量 + 嵌套 + & 父引用，气泡配色沿用原单页）

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <App />
  </StrictMode>
);
