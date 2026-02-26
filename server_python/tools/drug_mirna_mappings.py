# -*- coding: utf-8 -*-
"""
Drug ID ↔ Drug Name、miRNA ID ↔ miRNA Name 映射加载
数据源：tools/drug-smiles.xlsx、tools/miRNA-sequences.xlsx

列名约定（请与 Excel 一致）：
- drug-smiles.xlsx 三列：DrugBank_ID, smiles, Drug_Name
- miRNA-sequences.xlsx 三列：miRNA, Sequence, miRNA_name

流程：用户提问药物名称 → Drug_Name 查得行号(drug_id) / DrugBank_ID → 模型得关联 miRNA 行号(mirna_id) → miRNA_name
模型内部使用 0-based 行号与 xlsx 行序一致。
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple

_TOOLS_DIR = Path(__file__).resolve().parent
DRUG_XLSX = _TOOLS_DIR / "drug-smiles.xlsx"
MIRNA_XLSX = _TOOLS_DIR / "miRNA-sequences.xlsx"


def _ensure_pandas() -> "pd":
    try:
        import pandas as pd
        return pd
    except ImportError:
        raise ImportError("请安装 pandas 和 openpyxl: pip install pandas openpyxl")


def _load_drug_mappings() -> Tuple[Dict[int, str], Dict[str, int], Dict[int, str]]:
    """
    加载药物映射。id 使用 0-based 行号（与模型一致）。
    列名优先：Drug_Name（名称）、DrugBank_ID（可选，用于返回/展示）。
    返回: (id2name, name2id, id2drugbank_id)
    """
    pd = _ensure_pandas()
    id2name: Dict[int, str] = {}
    name2id: Dict[str, int] = {}
    id2drugbank: Dict[int, str] = {}

    if not DRUG_XLSX.exists():
        return id2name, name2id, id2drugbank

    try:
        df = pd.read_excel(DRUG_XLSX, engine="openpyxl")
    except Exception:
        return id2name, name2id, id2drugbank

    # 列名约定：DrugBank_ID, smiles, Drug_Name（优先使用约定列名）
    name_cols = ["Drug_Name", "Drug Name", "drug_name", "name", "drugname", "Name", "Drug", "drug"]
    drugbank_cols = ["DrugBank_ID", "DrugBank ID", "drugbank_id", "id", "drug_id", "index", "idx"]
    name_col = None
    drugbank_col = None

    for c in name_cols:
        if c in df.columns:
            name_col = c
            break
    if name_col is None and len(df.columns) >= 1:
        name_col = df.columns[0]

    for c in drugbank_cols:
        if c in df.columns:
            drugbank_col = c
            break

    for i, row in df.iterrows():
        idx = int(i)  # 0-based 行号，与模型 drug_id 一致
        nm = str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else f"Drug_{idx}"
        id2name[idx] = nm
        name2id[nm.lower()] = idx
        name2id[nm] = idx
        if drugbank_col and pd.notna(row.get(drugbank_col)):
            id2drugbank[idx] = str(row[drugbank_col]).strip()
            # 支持按 DrugBank_ID 查行号
            name2id[str(row[drugbank_col]).strip().lower()] = idx
            name2id[str(row[drugbank_col]).strip()] = idx

    return id2name, name2id, id2drugbank


def _load_mirna_mappings() -> Tuple[Dict[int, str], Dict[str, int]]:
    """
    加载 miRNA 映射。id 使用 0-based 行号（与模型一致）。
    列名优先：miRNA_name（名称）、miRNA（可为 ID 列）。
    """
    pd = _ensure_pandas()
    id2name: Dict[int, str] = {}
    name2id: Dict[str, int] = {}

    if not MIRNA_XLSX.exists():
        return id2name, name2id

    try:
        df = pd.read_excel(MIRNA_XLSX, engine="openpyxl")
    except Exception:
        return id2name, name2id

    # 列名约定：miRNA, Sequence, miRNA_name
    name_cols = ["miRNA_name", "miRNA name", "mirna_name", "name", "miRNA", "mirna", "id"]
    id_cols = ["miRNA", "mirna", "id", "mirna_id", "index", "idx"]
    name_col = None
    id_col = None

    for c in name_cols:
        if c in df.columns:
            name_col = c
            break
    if name_col is None and len(df.columns) >= 1:
        name_col = df.columns[0]

    for c in id_cols:
        if c in df.columns:
            id_col = c
            break

    for i, row in df.iterrows():
        idx = int(i)  # 0-based 行号，与模型 mirna_id 一致
        nm = str(row[name_col]).strip() if name_col and pd.notna(row.get(name_col)) else f"miRNA_{idx}"
        id2name[idx] = nm
        name2id[nm.lower()] = idx
        name2id[nm] = idx
        if id_col and id_col != name_col and pd.notna(row.get(id_col)):
            sid = str(row[id_col]).strip()
            name2id[sid.lower()] = idx
            name2id[sid] = idx

    return id2name, name2id


# 模块级缓存
_drug_id2name: Optional[Dict[int, str]] = None
_drug_name2id: Optional[Dict[str, int]] = None
_drug_id2drugbank: Optional[Dict[int, str]] = None
_mirna_id2name: Optional[Dict[int, str]] = None
_mirna_name2id: Optional[Dict[str, int]] = None


def get_drug_mappings() -> Tuple[Dict[int, str], Dict[str, int], Dict[int, str]]:
    global _drug_id2name, _drug_name2id, _drug_id2drugbank
    if _drug_id2name is None:
        _drug_id2name, _drug_name2id, _drug_id2drugbank = _load_drug_mappings()
    return _drug_id2name, _drug_name2id, _drug_id2drugbank or {}


def get_mirna_mappings() -> Tuple[Dict[int, str], Dict[str, int]]:
    global _mirna_id2name, _mirna_name2id
    if _mirna_id2name is None:
        _mirna_id2name, _mirna_name2id = _load_mirna_mappings()
    return _mirna_id2name, _mirna_name2id


def drug_id_to_name(drug_id: int) -> str:
    id2name, _, _ = get_drug_mappings()
    return id2name.get(drug_id, f"Drug_{drug_id}")


def drug_id_to_drugbank_id(drug_id: int) -> Optional[str]:
    """根据 drug_id（行号）返回对应的 DrugBank_ID。"""
    _, _, id2drugbank = get_drug_mappings()
    return id2drugbank.get(drug_id)


def drug_name_to_id(drug: str | int) -> Optional[int]:
    """根据药物名称或 DrugBank_ID 或数字 id 得到 drug_id（0-based 行号）。"""
    if isinstance(drug, int):
        return drug
    _, name2id, _ = get_drug_mappings()
    s = str(drug).strip()
    if s.lower() in name2id:
        return name2id[s.lower()]
    if s in name2id:
        return name2id[s]
    try:
        return int(s)
    except ValueError:
        return None


def mirna_id_to_name(mirna_id: int) -> str:
    id2name, _ = get_mirna_mappings()
    return id2name.get(mirna_id, f"miRNA_{mirna_id}")  # 关联的 miRNA 行号 → miRNA_name


def mirna_name_to_id(name: str | int) -> Optional[int]:
    if isinstance(name, int):
        return name
    _, name2id = get_mirna_mappings()
    s = str(name).strip()
    if s.lower() in name2id:
        return name2id[s.lower()]
    if s in name2id:
        return name2id[s]
    try:
        return int(s)
    except ValueError:
        return None


def list_drug_names() -> List[str]:
    """返回所有已知药物名称，供 LLM/用户参考。"""
    id2name, _, _ = get_drug_mappings()
    return sorted(set(id2name.values()))


def list_mirna_names(limit: int = 100) -> List[str]:
    """返回前 limit 个 miRNA 名称（miRNA_name）。"""
    id2name, _ = get_mirna_mappings()
    names = sorted(set(id2name.values()))[:limit]
    return names
