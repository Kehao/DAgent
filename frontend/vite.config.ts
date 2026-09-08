// ============================================================
// DAgent 企业级多智能体框架 —— Vite 配置
// ============================================================
// 设计要点：
// 1. 本工程用 @vitejs/plugin-react 支持 React 的 JSX 转换
//    （React 19 的 "react-jsx" 转换器，无需手动 import React）。
// 2. 前端直连后端 API :8100，靠后端 CORSMiddleware(allow_origins=["*"]) 放行，
//    因此无需在这里配 proxy。若未来后端收紧 CORS，可改为：
//       server.proxy = { "/api": "http://localhost:8100" }
//    并让前端请求相对路径 /api/...
// ============================================================
import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173, // Vite 开发服务器端口（仅本地开发用）
  },
});
