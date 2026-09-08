"""
DAgent 企业级多智能体框架 —— 虚拟数据模块
===========================================
用"内存数据"替代真实 ERP 系统，让框架不依赖任何外部服务即可运行。

教学要点
--------
1. 真实项目中，MCP 工具内部会去请求远端 ERP 的 HTTP API；
   本项目为了"即开即用"，直接在工具函数里读这份内存数据。
2. 数据结构刻意模仿真实 ERP：供应商 / 零部件 / 库存 三张"表"。
3. 字段命名使用驼峰（supplierName），贴近真实 Java ERP 的 JSON 返回。

数据如何支撑"子 Agent 委派"演示（重要）
----------------------------------------
supplier-analyst 子 Agent 的价值是"多供应商对比分析"，因此数据刻意设计成：
- 供应商档案含分析字段：
  · 定性：creditRating（评级）/ supplyCapability（供货能力）/
          priceLevel（价格水平）/ deliveryLeadTimeDays（交付周期）/
          cooperationYears（合作年限）
  · 量化：creditScore（评级分，90+=A）/ qualityPassRate（抽检合格率 %）/
          onTimeDeliveryRate（准时交付率 %）→ 供"信用评级分析 /
          风险评估 / 供货能力排序"引用硬指标，而非只读字母评级
- 存在多组"同品类多货源"的零件（同 partName 不同供应商不同价），
  让"谁更适合长期合作 / 比价"这类问题有真实数据可查：
    · 摩托车后视镜   —— S003(55元) vs S005(48元)
    · 火花塞         —— S002(15元) vs S006(9.5元，但库存预警+C级)
    · 高强度链条     —— S001(65元) vs S008(58元) vs S002(70元)（三家比价）
- S006 评级 C + 低价 + 库存不足 + 质量/交付双低 → "风险提示"一节的现成素材；
  S004 已停止合作(status=0) → 演示状态过滤。
想扩展时：直接往列表里加 dict 即可，Agent 立刻能查到。
"""

# ============ 供应商表 ============
# 字段说明（比价分析维度）：
#   creditRating        信用评级 A/B/C/D
#   creditScore         信用评分（量化评级依据：90+=A, 80-89=B, 70-79=C, <70=D）
#   qualityPassRate     来料质量抽检合格率（%，质量风险硬指标）
#   onTimeDeliveryRate  准时交付率（%，供货可靠性硬指标）
#   status              1=合作中, 0=已停止
#   supplyCapability    供货能力（月产能 + 主力覆盖区域）
#   priceLevel          价格水平（高/中/低，用于定性对比）
#   deliveryLeadTimeDays 交付周期（天）
#   cooperationYears    合作年限（年，判断"新供应商"风险）
SUPPLIERS = [
    {
        "id": 1,
        "supplierCode": "S001",
        "supplierName": "重庆隆鑫发动机配件厂",
        "contactPerson": "王建国",
        "phone": "13800000001",
        "creditRating": "A",
        "creditScore": 92,
        "qualityPassRate": 99.5,
        "onTimeDeliveryRate": 98.0,
        "status": 1,
        "address": "重庆市九龙坡区华龙大道 8 号",
        "supplyCapability": "月产能 8 万件，主力供应西南片区",
        "priceLevel": "中",
        "deliveryLeadTimeDays": 3,
        "cooperationYears": 12,
    },
    {
        "id": 2,
        "supplierCode": "S002",
        "supplierName": "浙江钱江摩托零部件有限公司",
        "contactPerson": "李慧敏",
        "phone": "13800000002",
        "creditRating": "A",
        "creditScore": 95,
        "qualityPassRate": 99.8,
        "onTimeDeliveryRate": 97.0,
        "status": 1,
        "address": "浙江省温岭市城东街道 66 号",
        "supplyCapability": "月产能 6 万件，品牌件主力，覆盖华东片区",
        "priceLevel": "高",
        "deliveryLeadTimeDays": 5,
        "cooperationYears": 8,
    },
    {
        "id": 3,
        "supplierCode": "S003",
        "supplierName": "广州大长江减震器厂",
        "contactPerson": "张伟",
        "phone": "13800000003",
        "creditRating": "B",
        "creditScore": 85,
        "qualityPassRate": 98.0,
        "onTimeDeliveryRate": 94.0,
        "status": 1,
        "address": "广州市增城区新塘镇工业大道 12 号",
        "supplyCapability": "月产能 5 万件，专注减震与后视镜件",
        "priceLevel": "中",
        "deliveryLeadTimeDays": 4,
        "cooperationYears": 5,
    },
    {
        "id": 4,
        "supplierCode": "S004",
        "supplierName": "江苏春兰制动系统有限公司",
        "contactPerson": "陈晓东",
        "phone": "13800000004",
        "creditRating": "B",
        "creditScore": 78,
        "qualityPassRate": 95.5,
        "onTimeDeliveryRate": 88.0,  # 曾因批次质量问题停用，交付率偏低
        "status": 0,                # 已停止合作（演示 status 过滤）
        "address": "江苏省泰州市海陵区春兰路 1 号",
        "supplyCapability": "月产能 2 万件，曾因批次质量问题停用",
        "priceLevel": "低",
        "deliveryLeadTimeDays": 7,
        "cooperationYears": 3,
    },
    {
        "id": 5,
        "supplierCode": "S005",
        "supplierName": "安徽全柴精密零部件有限公司",
        "contactPerson": "王磊",
        "phone": "13800000005",
        "creditRating": "A",
        "creditScore": 90,
        "qualityPassRate": 99.2,
        "onTimeDeliveryRate": 99.0,  # 新晋供应商但交付最稳（对比素材）
        "status": 1,
        "address": "安徽省合肥市经开区玉兰大道 21 号",
        "supplyCapability": "月产能 7 万件，价格与交期俱佳的新晋供应商",
        "priceLevel": "低",
        "deliveryLeadTimeDays": 2,
        "cooperationYears": 1,
    },
    {
        "id": 6,
        "supplierCode": "S006",
        "supplierName": "山东鲁轻机械配件厂",
        "contactPerson": "孙秀兰",
        "phone": "13800000006",
        "creditRating": "C",
        "creditScore": 65,           # 低评级（演示"低价但高风险"权衡）
        "qualityPassRate": 94.0,     # 合格率最低 → 质量风险硬指标
        "onTimeDeliveryRate": 85.0,  # 准时率最低 → 交付风险硬指标
        "status": 1,
        "address": "山东省临沂市兰山区工业园 3 号",
        "supplyCapability": "月产能 1.5 万件，小厂供货稳定性存疑",
        "priceLevel": "低",
        "deliveryLeadTimeDays": 6,
        "cooperationYears": 2,
    },
    {
        "id": 7,
        "supplierCode": "S007",
        "supplierName": "江苏新陵车灯电器有限公司",
        "contactPerson": "周海燕",
        "phone": "13800000007",
        "creditRating": "B",
        "creditScore": 82,
        "qualityPassRate": 97.5,
        "onTimeDeliveryRate": 93.0,
        "status": 1,
        "address": "江苏省丹阳市界牌镇灯城大道 33 号",
        "supplyCapability": "月产能 3 万件，车灯电器件专业厂",
        "priceLevel": "中",
        "deliveryLeadTimeDays": 4,
        "cooperationYears": 4,
    },
    {
        "id": 8,
        "supplierCode": "S008",
        "supplierName": "广东华丰传动件有限公司",
        "contactPerson": "郑国强",
        "phone": "13800000008",
        "creditRating": "A",
        "creditScore": 91,
        "qualityPassRate": 99.0,
        "onTimeDeliveryRate": 96.0,
        "status": 1,
        "address": "广东省东莞市寮步镇金富路 58 号",
        "supplyCapability": "月产能 6 万件，华南区链条/传动件主力",
        "priceLevel": "低",
        "deliveryLeadTimeDays": 3,
        "cooperationYears": 3,
    },
]

# ============ 零部件表 ============
# 同 partName 多行的零件 = "同品类多货源"，供子 Agent 比价分析。
PARTS = [
    {
        "id": 101,
        "partCode": "P001",
        "partName": "摩托车活塞环组件",
        "supplierId": 1,
        "supplierName": "重庆隆鑫发动机配件厂",
        "unitPrice": 45.00,
        "stock": 500,
        "spec": "125cc 通用",
    },
    {
        "id": 102,
        "partCode": "P002",
        "partName": "铝合金轮毂",
        "supplierId": 2,
        "supplierName": "浙江钱江摩托零部件有限公司",
        "unitPrice": 320.00,
        "stock": 120,
        "spec": "17 寸 3.50-17",
    },
    {
        "id": 103,
        "partCode": "P003",
        "partName": "液压减震器（后双）",
        "supplierId": 3,
        "supplierName": "广州大长江减震器厂",
        "unitPrice": 260.00,
        "stock": 80,
        "spec": "330mm 双筒",
    },
    {
        "id": 104,
        "partCode": "P004",
        "partName": "盘式制动卡钳",
        "supplierId": 4,
        "supplierName": "江苏春兰制动系统有限公司",
        "unitPrice": 180.00,
        "stock": 0,                 # 缺货（演示库存预警）
        "spec": "双活塞对向",
    },
    {
        "id": 105,
        "partCode": "P005",
        "partName": "高强度链条",
        "supplierId": 1,
        "supplierName": "重庆隆鑫发动机配件厂",
        "unitPrice": 65.00,
        "stock": 300,
        "spec": "428H 加强型",
    },
    {
        "id": 106,
        "partCode": "P006",
        "partName": "摩托车后视镜（通用右）",
        "supplierId": 3,
        "supplierName": "广州大长江减震器厂",
        "unitPrice": 55.00,
        "stock": 260,
        "spec": "通用右镜",
    },
    {
        "id": 107,
        "partCode": "P007",
        "partName": "摩托车后视镜（通用右）",
        "supplierId": 5,
        "supplierName": "安徽全柴精密零部件有限公司",
        "unitPrice": 48.00,         # 同品更低价（S003 vs S005 比价组）
        "stock": 380,
        "spec": "通用右镜",
    },
    {
        "id": 108,
        "partCode": "P008",
        "partName": "火花塞（通用型）",
        "supplierId": 2,
        "supplierName": "浙江钱江摩托零部件有限公司",
        "unitPrice": 15.00,
        "stock": 600,
        "spec": "标准型",
    },
    {
        "id": 109,
        "partCode": "P009",
        "partName": "火花塞（通用型）",
        "supplierId": 6,
        "supplierName": "山东鲁轻机械配件厂",
        "unitPrice": 9.50,
        "stock": 90,                # 低价但库存偏低（S002 vs S006 比价组 + 风险素材）
        "spec": "标准型",
    },
    {
        "id": 110,
        "partCode": "P010",
        "partName": "高强度链条",
        "supplierId": 8,
        "supplierName": "广东华丰传动件有限公司",
        "unitPrice": 58.00,         # 同品更低价（S001 vs S008 比价组）
        "stock": 420,
        "spec": "428H 加宽型",
    },
    {
        "id": 111,
        "partCode": "P011",
        "partName": "高强度链条",
        "supplierId": 2,
        "supplierName": "浙江钱江摩托零部件有限公司",
        "unitPrice": 70.00,         # 链条第三货源（A级高价档：65/58/70 三档比价）
        "stock": 350,
        "spec": "428H 加宽型",
    },
]

# ============ 库存预警线（简化为固定阈值，教学够用） ============
STOCK_WARNING_THRESHOLD = 100  # 低于 100 视为库存偏低
