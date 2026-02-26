# 药物 Top-N 关联 miRNA 查询（Case Study Agent）设计思路

## 一、功能概述

当用户询问「某药物的 top N 个关联 miRNA」时，系统调用 **case_study** 作为 Agent 工具，利用预训练 MGCNA 模型预测药物- miRNA 关联，并返回可读结果（含 drug name、miRNA name）。

## 二、数据与资源（tools 目录）

```
server_python/tools/
├── drug-smiles.xlsx       # Drug ID → Drug Name (及 SMILES)
├── miRNA-sequences.xlsx   # miRNA ID → miRNA Name (及序列)
├── best_model_global.pth  # 最优模型权重（或 best_model_foldX.pth）
├── drug_mirna_mappings.py # ID↔Name 映射加载
├── case_study_service.py  # 预测服务封装
├── casestudy.py           # 原有 MGCNA 训练/预测逻辑（或依赖的模块）
└── DESIGN.md              # 本设计文档
```

### 2.1 映射表说明

| 文件 | 用途 | 列名约定（三列） |
|------|------|------------------|
| drug-smiles.xlsx | 药物名称/DrugBank_ID → 行号(drug_id)，行号 → Drug_Name / DrugBank_ID | **DrugBank_ID**, **smiles**, **Drug_Name** |
| miRNA-sequences.xlsx | 行号(mirna_id) → miRNA_name | **miRNA**, **Sequence**, **miRNA_name** |

**约定**：模型内部使用 `drug_id` / `mirna_id` 为 0-based 行号，与 xlsx 行序一致。流程：用户提问药物名称 → 查 Drug_Name 得 drug_id（及 DrugBank_ID）→ 模型得关联 mirna_id → mirna_id_to_name 得 miRNA_name。

## 三、架构流程

```
用户输入: "查询 Docetaxel 的 top 20 关联 miRNA"
    ↓
[1] 意图识别（LLM 或规则）
    - 提取：drug = "Docetaxel" 或 drug_id
    - 提取：top_n = 20
    ↓
[2] 调用 case_study 工具
    - drug_mirna_mappings: name → id 解析
    - 加载模型 + dataset
    - predict_all_pairs(drug_id, top_k=top_n)
    ↓
[3] 结果映射
    - (mirna_id, drug_id, score) → (miRNA_name, Drug_name, score)
    ↓
[4] 返回给 LLM / 前端
    - 结构化 JSON 或自然语言总结
```

## 四、接口设计

### 4.1 后端 API

```
POST /api/case-study/drug-top-mirnas
Body: {
  "drug": "Docetaxel" | drug_id,   // 药物名或 ID
  "top_n": 20                      // 默认 25
}
Response: {
  "success": true,
  "drug_id": 5,
  "drug_name": "Docetaxel",
  "top_mirnas": [
    { "rank": 1, "mirna_id": 42, "mirna_name": "hsa-miR-xxx", "score": 0.95 },
    ...
  ]
}
```

### 4.2 聊天融合（Agent 模式）

- **方案 A**：类似 RAG，增加「Case Study」模式开关，该模式下走 `/api/chat/case-study`，内部检测药物查询意图后调用工具。
- **方案 B**：统一走千问，通过 Function Calling / Tool Use 注册 `query_drug_top_mirnas` 工具，由 LLM 决定何时调用。

## 五、扩展与延伸

1. **反向查询**：miRNA → Top-N 关联药物（复用 `predict_all_pairs` 逻辑，drug/miRNA 对调）。
2. **批量查询**：一次请求多个药物的 top-N。
3. **阈值过滤**：仅返回 score ≥ threshold 的结果。
4. **导出**：支持 CSV/Excel 导出。
5. **缓存**：对相同 (drug_id, top_n) 结果做短期缓存，减少模型推理。
6. **异步任务**：大规模预测可放入后台任务，返回 job_id 轮询结果。

## 六、实现要点

1. **模型路径**：优先 `tools/best_model_global.pth`，其次 `best_model_fold{best_fold}.pth`。
2. **依赖隔离**：casestudy 依赖 `data_preprocess5fold`、`layer3`、`parms_setting`，需保证 tools 或工作目录可导入；若为独立项目，可抽离为子进程调用。
3. **ID 对齐**：xlsx 行序与 `load_data` 中的 id 需一致，否则需建立显式映射表。
