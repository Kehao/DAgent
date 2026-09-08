// ============================================================
// 常用提示词建议（Prompt Suggestions）
// ============================================================
// 职责：输入框聚焦且为空时，向上弹出"试试这样问"面板的数据源。
// 分组即能力地图：
//   - subagent：会触发子 Agent 委派（supplier-analyst）的多步分析任务，
//     覆盖其 description 声明的四类工作：对比多家 / 信用评级 /
//     供货能力与价格差异 / 推荐最合适 / 评估合作风险
//   - query   ：单步日常查询（主 Agent 直接调 MCP 工具即可回答）
//   - risk    ：库存 / 风险类排查（依赖 stock_warning 与供应商评级）
//
// 设计要点：
// 1. 文案与 src/data/mock_data.py 的虚拟数据逐条对齐（S 编码 / 单价 /
//    库存 / 评级 / 量化字段），保证"点了就能跑通、且结果有看头"：
//    · 同品类多货源：后视镜 S003(55) vs S005(48)；火花塞 S002(15) vs S006(9.5)；
//      高强度链条 S001(65) / S008(58) / S002(70) —— 三家比价
//    · 量化字段：creditScore / qualityPassRate / onTimeDeliveryRate
//    · 风险素材：S006(C级+双低指标)、S004(已停用)、S005(新供应商1年)、
//      P004 卡钳库存 0 + 供应商停用（断供双险）
// 2. 点击行为 = "预填到输入框"（不直接发送），用户可编辑后再 Enter；
// 3. 想加新示例 → 往 PROMPT_SUGGESTIONS 加一条即可，无需改组件。
// ============================================================

/** 分组键：决定面板里的分组标题与图标 */
export type PromptGroupKey = "subagent" | "query" | "risk";

/** 单条提示词建议 */
export interface PromptSuggestion {
  id: string;
  group: PromptGroupKey;
  /** 点击后填入输入框的完整提示词 */
  text: string;
}

/** 分组展示顺序 */
export const PROMPT_GROUP_ORDER: PromptGroupKey[] = ["subagent", "query", "risk"];

/** 分组标题文案 */
export const PROMPT_GROUP_LABEL: Record<PromptGroupKey, string> = {
  subagent: "委派分析 · 子 Agent（supplier-analyst）",
  query: "日常查询",
  risk: "库存与风险排查",
};

/** 分组 hover 底色微差说明用的提示（面板头部展示） */
export const PROMPT_PANEL_HINT = "点击填入输入框，可编辑后按 Enter 发送";

export const PROMPT_SUGGESTIONS: PromptSuggestion[] = [
  // ═══════ 子 Agent 委派：多步对比 / 评级 / 推荐 / 风险评估 ═══════
  // 对比多家（双家）：后视镜 S003(55元/B) vs S005(48元/A) —— 低价 vs 高评级权衡
  {
    id: "cmp-mirror",
    group: "subagent",
    text: "对比后视镜供应商 S003 与 S005：从价格、供货能力、合作风险三个角度分析，推荐一家更合适的",
  },
  // 对比多家（双家）：火花塞 S002(15元/A) vs S006(9.5元/C 级 + 库存预警)
  {
    id: "cmp-spark",
    group: "subagent",
    text: "分析火花塞供应商 S002 与 S006 的价格与供货能力，评估谁更值得长期合作",
  },
  // 对比多家（三家同品）：高强度链条 65/58/70 三档，真正意义的"多家比价"
  {
    id: "cmp-chain-3",
    group: "subagent",
    text: "高强度链条有三家货源：S001(65元)、S008(58元)、S002(70元)，对比价格、质量合格率与交付能力，推荐最合适的一家",
  },
  // 信用评级 + 量化指标全量排序（四类任务之二、之三）
  {
    id: "rate-all",
    group: "subagent",
    text: "对全部 8 家供应商做信用评级分析：结合评级分、质量合格率、准时交付率排序，指出谁最稳健、谁风险最高",
  },
  // 推荐最合适的供应商（综合打分 Top 3）
  {
    id: "recommend-top",
    group: "subagent",
    text: "从合作中的供应商里推荐 Top 3 长期合作候选：按评级、供货能力、交付与价格综合打分排序",
  },
  // 评估合作风险（D 类）：S005 低价快交期但只合作 1 年 —— 新供应商依赖风险
  {
    id: "assess-s005-new",
    group: "subagent",
    text: "评估与 S005 合作的潜在风险：它价格低、交付快，但合作仅 1 年，把后视镜订单集中给它是否稳妥",
  },
  // ═══════ 日常查询：主 Agent 直接调 supplier_search / part_search ═══════
  {
    id: "list-suppliers",
    group: "query",
    text: "查询目前有哪些供应商，各自的评级与供货能力如何",
  },
  {
    id: "supplier-profile",
    group: "query",
    text: "供应商 S003 的完整档案：评级、评级分、供货能力、价格水平与合作年限",
  },
  // 需要两步：supplier_search("钱江") 拿 id → part_search(supplier_id=2)
  {
    id: "supplier-parts-qianjiang",
    group: "query",
    text: "钱江（S002）都供应哪些零件？各自的单价与库存是多少",
  },
  // 交付能力横向比：交付周期 + 准时交付率两个字段都有明显极值
  {
    id: "delivery-ranking",
    group: "query",
    text: "对比各供应商的交付周期与准时交付率，谁交付最快、最稳定",
  },
  // ═══════ 库存与风险排查：依赖 stock_warning 预警与供应商评级 ═══════
  {
    id: "stock-low",
    group: "risk",
    text: "帮我看看哪些零件库存偏低、需要补货",
  },
  // 断供双险：P004 卡钳库存 0，且其供应商 S004 已停止合作
  {
    id: "out-of-stock-brake",
    group: "risk",
    text: "盘式制动卡钳库存为 0，查一下它的供应商是否还在合作？会不会断供",
  },
  {
    id: "risk-c-grade",
    group: "risk",
    text: "S006 是 C 级风险供应商，核查一下它的供货情况与相关零件的库存",
  },
  // 交叉排查：低库存零件的供应商是否同时评级偏弱（卡钳→停用的 S004，火花塞→C 级 S006）
  {
    id: "low-stock-weak-supplier",
    group: "risk",
    text: "交叉排查：库存偏低的零件里，供应商是否也存在评级偏低或停用风险",
  },
  // 参数化预警阈值演示（threshold=150 → 多出轮毂 P002 一条）
  {
    id: "stock-threshold-150",
    group: "risk",
    text: "把库存预警线提高到 150 件，重新排查一遍哪些零件接近缺货",
  },
];
