// ============================================================
// HarnessPhaseBar —— Harness 工作流阶段进度条（工业装配线版）
// ============================================================
// 视觉：C 工业装配线派 —— 五站点 + 四段传送带 + 工业 icon + 编号 01-05
//   站点三态：
//     · past    橄榄绿底（已完成）
//     · current 暖橙底 + 硬阴影 + 抬升 + icon 旋转（执行中）
//     · future  默认灰
//   传送带：past 橄榄绿；run 暖橙流光；future 牛皮纸灰
//   底部状态行：阶段描述（衬线斜体）+ 评审判定 mono 徽章
//
// 数据：父组件 App 传入 displayPhase 键；本组件只负责照着阶段画装配线。
// ============================================================

import { Clock, ListChecks, Wrench, Search, CheckCircle2 } from "lucide-react";
import type { ReviewVerdict } from "../types";

// 进度条能展示的阶段键（"idle"= 尚未开始，不渲染）
export type DisplayPhase =
  | "thinking"
  | "planning"
  | "executing"
  | "reviewing"
  | "done"
  | "idle";

interface Props {
  phase: DisplayPhase;
  visible: boolean;
  review: { verdict: ReviewVerdict; iteration: number } | null;
}

// 五站点定义：icon 用 lucide；idx 为编号 01-05
const STATIONS = [
  { key: "thinking", label: "思考", idx: "01", icon: Clock },
  { key: "planning", label: "规划", idx: "02", icon: ListChecks },
  { key: "executing", label: "执行", idx: "03", icon: Wrench },
  { key: "reviewing", label: "审查", idx: "04", icon: Search },
  { key: "done", label: "完成", idx: "05", icon: CheckCircle2 },
] as const;

const PHASE_ORDER = STATIONS.map((s) => s.key);

const VERDICT_LABEL: Record<ReviewVerdict, string> = {
  satisfied: "✓ 评审通过",
  needs_revision: "↻ 要求修改",
  failed: "✗ 评审未通过",
  max_iterations_reached: "⚠ 已达上限",
  grader_error: "评审异常",
};

const DESC: Record<Exclude<DisplayPhase, "idle">, string> = {
  thinking: "正在理解你的问题",
  planning: "正在拆解任务、规划执行步骤",
  executing: "正在调用工具执行任务",
  reviewing: "正在评审执行结果是否达标",
  done: "本轮任务已完成",
};

export default function HarnessPhaseBar({ phase, visible, review }: Props) {
  if (!visible || phase === "idle") return null;

  const currentIdx = PHASE_ORDER.indexOf(phase);

  return (
    <div className="phase-bar">
      <div className="phase-line-inner">
        {STATIONS.map((s, idx) => {
          const Icon = s.icon;
          const stateClass =
            idx < currentIdx ? "past" : idx === currentIdx ? "current" : "future";
          return (
            <div key={s.key} style={{ display: "contents" }}>
              {/* 站点 */}
              <div className={`phase-station ${stateClass}`}>
                <div className="phase-ico">
                  <Icon strokeWidth={2.5} />
                </div>
                <span className="phase-name">{s.label}</span>
                <span className="phase-idx">{s.idx}</span>
              </div>
              {/* 传送带：站点之间，4 段共 4 段 */}
              {idx < STATIONS.length - 1 && (
                <div
                  className={`phase-conveyor ${
                    idx < currentIdx ? "past" : idx === currentIdx ? "run" : "future"
                  }`}
                />
              )}
            </div>
          );
        })}
      </div>

      <div className="phase-foot">
        <span className="label" key={phase}>
          {DESC[phase]}
        </span>
        {review && (
          <span
            key={`chip-${review.iteration}`}
            className={`badge ${review.verdict === "satisfied" ? "" : "warn"}`}
          >
            {VERDICT_LABEL[review.verdict]} · ITER {review.iteration}
          </span>
        )}
      </div>
    </div>
  );
}
