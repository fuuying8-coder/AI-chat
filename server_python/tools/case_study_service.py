# -*- coding: utf-8 -*-
"""
Case Study 服务：查询某药物的 Top-N 关联 miRNA
- 加载 drug/miRNA 映射
- 调用 MGCNA 预测（若依赖可用）
- 返回带名称的结构化结果
"""
from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

_TOOLS_DIR = Path(__file__).resolve().parent
if str(_TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(_TOOLS_DIR))

from drug_mirna_mappings import drug_id_to_name, drug_id_to_drugbank_id, drug_name_to_id, mirna_id_to_name

# 最优模型路径（优先 global，其次 fold 中最佳）
BEST_MODEL_GLOBAL = _TOOLS_DIR / "best_model_global.pth"
BEST_MODEL_FOLD_PATTERN = "best_model_fold*.pth"


def _resolve_drug_id(drug: str | int, drug_number: int) -> Tuple[Optional[int], str]:
    """
    解析 drug 为 drug_id。drug 可以是名称或数字。
    返回 (drug_id, error_msg)，成功时 error_msg 为空。
    """
    drug_id = drug_name_to_id(drug) if isinstance(drug, str) else drug
    if drug_id is None:
        return None, f"未找到药物 '{drug}'，请检查药物名称或 ID"
    if drug_id < 0 or drug_id >= drug_number:
        return None, f"drug_id {drug_id} 超出有效范围 [0, {drug_number - 1}]"
    return drug_id, ""


def _load_case_study_predictor():
    """
    尝试加载 casestudy 的预测逻辑。
    需要：data_preprocess5fold, layer3, parms_setting 在 tools 或 PYTHONPATH 中。
    """
    try:
        from data_preprocess5fold import load_data
        from layer3 import MGCNA
        from parms_setting import settings
    except ImportError as e:
        return None, str(e)

    args = settings()
    # 使用 tools/data 下的数据，避免 /data/pos.edgelist 等绝对路径找不到
    args.pos_sample = str(_TOOLS_DIR / "data" / "pos.edgelist")
    args.neg_sample = str(_TOOLS_DIR / "data" / "neg.edgelist")
    # Case Study 服务强制使用 CPU，避免 CUDA 依赖与显存占用
    args.cuda = False
    import torch
    import numpy as np
    np.random.seed(getattr(args, "seed", 42))
    torch.manual_seed(getattr(args, "seed", 42))

    dataset, all_data = load_data(args, test_ratio=0.2)
    model = MGCNA(
        feature=getattr(args, "dimensions", 64),
        hidden1=getattr(args, "hidden1", 32),
        hidden2=getattr(args, "hidden2", 16),
        decoder1=getattr(args, "decoder1", 32),
    )
    # 模型与数据保持在 CPU
    model.to("cpu")

    model_path = None
    if BEST_MODEL_GLOBAL.exists():
        model_path = BEST_MODEL_GLOBAL
    else:
        for p in _TOOLS_DIR.glob(BEST_MODEL_FOLD_PATTERN):
            model_path = p
            break
    if model_path and model_path.exists():
        model.load_state_dict(torch.load(str(model_path), map_location="cpu"))
    else:
        return None, f"未找到模型文件，请将 best_model_global.pth 或 best_model_fold*.pth 放入 {_TOOLS_DIR}"

    model.eval()
    return {
        "model": model,
        "dataset": dataset,
        "args": args,
    }, ""


def _run_predict_all_pairs(predictor: dict, drug_id: int, top_k: int) -> Tuple[List[Tuple[int, int]], List[float]]:
    """内联 predict_all_pairs 逻辑，避免导入 casestudy 触发训练脚本执行。"""
    import numpy as np
    import torch

    model = predictor["model"]
    dataset = predictor["dataset"]
    args = predictor["args"]
    m = torch.nn.Sigmoid()
    num_mirnas = getattr(args, "miRNA_number", 1578)
    batch_size = getattr(args, "batch", 256)

    all_pairs_list = [[mirna_id, drug_id] for mirna_id in range(num_mirnas)]
    all_pairs_array = np.array(all_pairs_list, dtype=np.int64)
    scores, pairs = [], []

    model.eval()
    with torch.no_grad():
        for i in range(0, len(all_pairs_array), batch_size):
            batch = all_pairs_array[i : i + batch_size]
            # Case Study 固定 CPU，不使用 .cuda()
            inp = (
                torch.tensor(batch[:, 0], dtype=torch.long),
                torch.tensor(batch[:, 1], dtype=torch.long),
            )
            output = model(dataset, inp)
            # 用 .tolist() 代替 .numpy()，避免 PyTorch 与 NumPy 版本兼容问题
            prob = m(output).detach().cpu().flatten()
            scores.extend(prob.tolist())
            pairs.extend([(int(a), int(b)) for a, b in zip(batch[:, 0], batch[:, 1])])

    scores_array = np.array(scores)
    sorted_indices = np.argsort(scores_array)[::-1]
    sorted_pairs = [pairs[i] for i in sorted_indices]
    sorted_scores = scores_array[sorted_indices]
    top_k = min(top_k, len(sorted_pairs))
    top_pairs = sorted_pairs[:top_k]
    top_scores = sorted_scores[:top_k].tolist()
    return top_pairs, top_scores


def query_drug_top_mirnas(
    drug: str | int,
    top_n: int = 25,
) -> Dict[str, Any]:
    """
    查询某药物的 Top-N 关联 miRNA。

    Args:
        drug: 药物名称或 drug_id
        top_n: 返回前 N 个，默认 25

    Returns:
        {
            "success": bool,
            "error": str | None,
            "drug_id": int | None,
            "drug_name": str,
            "top_mirnas": [{"rank", "mirna_id", "mirna_name", "score"}, ...]
        }
    """
    result: Dict[str, Any] = {
        "success": False,
        "error": None,
        "drug_id": None,
        "drug_name": "",
        "drugbank_id": None,  # 药物名称 → DrugBank_ID → 关联 miRNA → miRNA name
        "top_mirnas": [],
    }

    predictor, err = _load_case_study_predictor()
    if predictor is None:
        return query_drug_top_mirnas_standalone(drug, top_n)

    args = predictor["args"]
    drug_number = getattr(args, "drug_number", 50)
    drug_id, err = _resolve_drug_id(drug, drug_number)
    if drug_id is None:
        result["error"] = err
        return result

    result["drug_id"] = drug_id
    result["drug_name"] = drug_id_to_name(drug_id)
    result["drugbank_id"] = drug_id_to_drugbank_id(drug_id)

    try:
        top_pairs, top_scores = _run_predict_all_pairs(predictor, drug_id, top_n)
    except Exception as e:
        result["error"] = f"预测失败: {e}"
        return result

    top_mirnas = []
    for rank, ((mirna_id, _), score) in enumerate(zip(top_pairs, top_scores), 1):
        top_mirnas.append({
            "rank": rank,
            "mirna_id": mirna_id,
            "mirna_name": mirna_id_to_name(mirna_id),
            "score": round(float(score), 6),
        })
    result["top_mirnas"] = top_mirnas
    result["success"] = True
    return result


def query_drug_top_mirnas_standalone(
    drug: str | int,
    top_n: int = 25,
    drug_mapping_path: Optional[Path] = None,
    mirna_mapping_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """
    独立模式：仅使用 drug/miRNA 映射，不依赖 MGCNA 模型。
    当 data_preprocess5fold / layer3 不可用时，可返回占位结果或调用外部服务。
    此处返回「服务未就绪」提示，便于前端展示。
    """
    drug_id = drug_name_to_id(drug) if isinstance(drug, str) else (drug if isinstance(drug, int) else None)
    drug_name = drug_id_to_name(drug_id) if drug_id is not None else str(drug)
    drugbank_id = drug_id_to_drugbank_id(drug_id) if drug_id is not None else None

    return {
        "success": False,
        "error": "Case Study 预测模块（data_preprocess5fold、layer3）未配置。请将 MGCNA 相关代码与模型放入 tools 目录，或配置 PYTHONPATH。",
        "drug_id": drug_id,
        "drug_name": drug_name,
        "drugbank_id": drugbank_id,
        "top_mirnas": [],
    }
