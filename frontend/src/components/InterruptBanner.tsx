// ============================================================
// InterruptBanner —— 过程提醒横幅（C 工业装配线版）
// ============================================================
// 视觉：默认（delegate 委派中）= 芥末黄底 + 黑边 + 4px 硬阴影
//       返工（revising）= rust 锈红底 + 白字 + 黑边
//       都带黑色 mono 徽章（SUB-AGENT / REVISE）
//
// 驱动（不变）：
//   delegate   开: tool_start(name=task)        关: tool_result(name=task)
//   revising   开: review_result(needs_revision) 关: 下一轮终态判定
// ============================================================

import { Bot, RefreshCw } from "lucide-react";
import type { Banner } from "../types";

interface Props {
  banner: Banner | null;
}

const KIND_CONFIG = {
  delegate: { icon: Bot, label: "SUB-AGENT", spin: false },
  revising: { icon: RefreshCw, label: "REVISE", spin: true },
} as const;

export default function InterruptBanner({ banner }: Props) {
  if (!banner) return null;

  const config = KIND_CONFIG[banner.kind] || KIND_CONFIG.delegate;
  const Icon = config.icon;

  return (
    <div className={`interrupt-banner ${banner.kind}`}>
      <span className="interrupt-badge">{config.label}</span>
      <Icon
        size={15}
        className={config.spin ? "interrupt-spin" : ""}
        color="currentColor"
      />
      <span className="interrupt-text">{banner.text}</span>
    </div>
  );
}
