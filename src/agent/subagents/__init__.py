"""
DAgent 企业级多智能体框架 —— 子 Agent（SubAgent）包
====================================================
用"声明式 yaml + 工具子串匹配"注册专职子 Agent 的机制实现。

子 Agent 是什么（一句话）：
    主 Agent（协调者）把"需要多步 / 专业领域"的任务，通过框架自动暴露的
    task 工具委派给专职子 Agent；子 Agent 独立跑完（可自己调工具）后，
    把结构化结果交回主 Agent，由主 Agent 面向用户。

本包文件分工：
    loader.py             —— yaml → 校验 → 工具匹配 → spec 列表（唯一逻辑）
    configs/*.yaml        —— 声明子 Agent（name / description / tools / system_prompt）
"""
