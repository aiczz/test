"""离线构建菜定向量索引 —— 给食时 10000 道菜生成 embedding。

搬自 Project2 的 scripts/build_embeddings.py，做了三个关键适配：
  1. 数据源换成食时自己的清洗库（SQLite dishes 表 + dish_ingredients + seasonal_dish_links）
  2. embedding 文本模板是中文 + 加了时令月份、食养功效、做法标签 —— Project2 英文数据没有这些
  3. 进度条 + checkpoint 断点续跑 —— 防止中途网络挂了白跑

使用：
    cd back
    python -m scripts.build_embeddings           # 增量模式（已有的向量跳过）
    python -m scripts.build_embeddings --rebuild # 全量重建

输出：data/embeddings_dishes.npz（float16 压缩）
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any

import numpy as np

# 让脚本能从 back/ 目录直接跑 —— `python -m scripts.build_embeddings`
# 如果被直接 `python scripts/build_embeddings.py` 调，sys.path 可能没 app
_this_dir = os.path.dirname(os.path.abspath(__file__))
_back_dir = os.path.dirname(_this_dir)
if _back_dir not in sys.path:
    sys.path.insert(0, _back_dir)

from sqlalchemy import text as sqlt
from sqlmodel import Session

from app.core.config import settings
from app.core.database import engine, uses_compact_catalog
from app.services.retrieval.embed_client import embed_text, is_embedding_configured

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger("build_embeddings")

# ----------------------------------------------------------------------
# 常量
# ----------------------------------------------------------------------

MAX_MAIN_ING = 10    # embedding 文本里最多放多少个主要食材
MAX_ALL_ING = 20     # 全部配料
MAX_TAGS = 8         # 标签条数

OUTPUT_DIR = os.path.join(_back_dir, "data")
OUTPUT_FILE = os.path.join(_back_dir, settings.vector_index_path)


# ----------------------------------------------------------------------
# 小工具
# ----------------------------------------------------------------------


def _in_clause(values: list[int], prefix: str = "v") -> tuple[str, dict]:
    """SQLAlchemy 2.x 兼容的 IN 子句。返回 (':v_0, :v_1, ...', {v_0: val0, ...})"""
    names = [f":{prefix}_{i}" for i in range(len(values))]
    params = {f"{prefix}_{i}": v for i, v in enumerate(values)}
    return ", ".join(names), params


# ----------------------------------------------------------------------
# 取数
# ----------------------------------------------------------------------


def _list_all_dishes(session: Session) -> list[dict[str, Any]]:
    """读所有菜的 id + 名字 + 标签 + 时长 + 营养。"""
    compact = uses_compact_catalog(engine)
    table = "dishes" if compact else "recipes"

    # 先列一下表有什么列（兼容最小测试库）
    from sqlalchemy import inspect
    available = {c["name"] for c in inspect(session.get_bind()).get_columns(table)}

    wanted = [
        "id",
        "dish_name", "name",           # 菜名，两种命名都可能
        "tags_json",                   # 标签
        "duration_minutes",            # 时长
        "energy_kcal", "protein_g", "fat_g", "cho_g", "dietary_fiber_g", "na_mg",
    ]
    selected = [c for c in wanted if c in available]
    if {"dish_name", "name"} <= available:
        selected = [c for c in selected if c != "name"]  # 两张表都有时只取 dish_name
    elif "dish_name" in available and "name" not in available:
        pass  # compact 库只有 dish_name
    elif "name" in selected:
        pass  # legacy 库只有 name

    rows = session.execute(
        sqlt(f"SELECT {', '.join(selected)} FROM {table} ORDER BY id")
    ).mappings()

    result = []
    for row in rows:
        result.append({
            "id": int(row["id"]),
            "name": str(row.get("dish_name") or row.get("name") or ""),
            "tags_json": row.get("tags_json"),
            "duration_minutes": int(row.get("duration_minutes") or 30),
            "energy_kcal": row.get("energy_kcal"),
            "protein_g": row.get("protein_g"),
            "fat_g": row.get("fat_g"),
            "cho_g": row.get("cho_g"),
            "dietary_fiber_g": row.get("dietary_fiber_g"),
            "na_mg": row.get("na_mg"),
        })
    logger.info("读到 %d 道菜", len(result))
    return result


def _load_ingredients(session: Session, dish_ids: list[int]) -> dict[int, tuple[list[str], list[int]]]:
    """批量读每道菜的主料和完整配料名。

    返回 {dish_id: (主料名列表, 全部配料名列表)}
    """
    compact = uses_compact_catalog(engine)
    if compact:
        ing_table = "dish_ingredients"
        dish_col = "dish_id"
        name_col = "raw_name"
        role_col = "role"
        id_col = "ingredient_id"
    else:
        ing_table = "recipe_ingredients"
        dish_col = "recipe_id"
        name_col = "ingredient_name"
        role_col = None
        id_col = "food_id"

    if not dish_ids:
        return {}
    placeholders, params = _in_clause(dish_ids, "did")
    rows = session.execute(
        sqlt(
            f"SELECT {dish_col}, {name_col}"
            + (f", {role_col}" if role_col else "")
            + f" FROM {ing_table} "
            + f"WHERE {dish_col} IN ({placeholders})"
        ),
        params,
    ).mappings()

    mains: dict[int, list[str]] = {}
    all_names: dict[int, list[str]] = {}
    for row in rows:
        did = int(row[dish_col])
        name = str(row[name_col] or "").strip()
        if not name:
            continue
        all_names.setdefault(did, [])
        if name not in all_names[did]:
            all_names[did].append(name)
        # 主料：role 为 main/core/空 都算
        if role_col and str(row.get(role_col) or "") in {"main", "core", ""}:
            mains.setdefault(did, [])
            if name not in mains[did]:
                mains[did].append(name)
        elif not role_col:
            # legacy 库不区分 role，全部算主料
            mains.setdefault(did, [])
            if name not in mains[did]:
                mains[did].append(name)

    return {did: (mains.get(did, []), all_names.get(did, [])) for did in dish_ids}


def _load_seasonal_months(session: Session, dish_ids: list[int]) -> dict[int, list[str]]:
    """查每道菜关联的时令季节（通过 seasonal_dish_links → seasonal_food）。

    返回 {dish_id: ["春", "冬"]} 这样的季节列表
    """
    compact = uses_compact_catalog(engine)
    if not compact:
        return {}

    # 先查 seasonal_food 的 id → season
    food_rows = session.execute(
        sqlt("SELECT id, season FROM seasonal_food WHERE season IS NOT NULL AND season != ''")
    ).mappings()
    food_season: dict[str, str] = {}
    for row in food_rows:
        sid = str(row["id"])
        season = str(row["season"] or "")
        if sid and season:
            food_season[sid] = season

    if not dish_ids:
        return {}
    placeholders, params = _in_clause(dish_ids, "dlink")
    # dish → seasonal_food_id
    links = session.execute(
        sqlt(
            "SELECT d.dish_id, d.seasonal_food_id FROM seasonal_dish_links d "
            f"WHERE d.dish_id IN ({placeholders})"
        ),
        params,
    ).mappings()

    result: dict[int, list[str]] = {}
    for link in links:
        did = int(link["dish_id"])
        sid = str(link["seasonal_food_id"])
        season = food_season.get(sid)
        if season:
            result.setdefault(did, [])
            if season not in result[did]:
                result[did].append(season)
    return result


def _load_food_effects(session: Session, all_food_ids: set[int]) -> dict[int, list[str]]:
    """批量查食材的 effects_json（食养功效）。"""
    compact = uses_compact_catalog(engine)
    if not compact or not all_food_ids:
        return {}

    ids_list = sorted(all_food_ids)
    placeholders, params = _in_clause(ids_list, "fid")
    rows = session.execute(
        sqlt(
            "SELECT id, effects_json FROM ingredients "
            f"WHERE id IN ({placeholders})"
        ),
        params,
    ).mappings()

    result: dict[int, list[str]] = {}
    for row in rows:
        fid = int(row["id"])
        raw = row.get("effects_json")
        if not raw:
            continue
        try:
            tags = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(tags, list):
                result[fid] = [str(t) for t in tags if t]
        except (json.JSONDecodeError, TypeError):
            continue
    return result


# ----------------------------------------------------------------------
# Embedding 文本模板
# ----------------------------------------------------------------------


def _build_embedding_text(
    dish: dict[str, Any],
    mains: list[str],
    all_names: list[str],
    tags: list[str],
    seasonal: list[str],
    effects: list[str],
) -> str:
    """把一道菜的所有信息拼成一段中文文本，给 embedding 模型编码。

    注意：这里不放 step 做法全文——Project2 实测步骤文本太长噪声大，
    会稀释菜名/食材的核心信号。做法只放标签里的关键字。
    """
    name = dish["name"]
    dur = dish["duration_minutes"]
    na = dish["na_mg"]
    protein = dish["protein_g"]
    fiber = dish["dietary_fiber_g"]

    parts: list[str] = [f"菜名：{name}"]

    if mains:
        parts.append(f"主要食材：{'、'.join(mains[:MAX_MAIN_ING])}")
    if all_names:
        parts.append(f"全部配料：{'、'.join(all_names[:MAX_ALL_ING])}")

    # 从标签里提取做法关键字
    method_tags = [t for t in tags if t in ("炖", "煮", "蒸", "炒", "凉拌", "烤", "炸", "焖", "烧", "煲", "煎")]
    if method_tags:
        parts.append(f"做法：{'、'.join(method_tags)}")
    if tags:
        parts.append(f"标签：{'、'.join(tags[:MAX_TAGS])}")

    if dur and dur > 0:
        parts.append(f"时长：{dur}分钟")

    nutri_parts = []
    if protein is not None:
        nutri_parts.append(f"蛋白{protein:g}g")
    if na is not None:
        nutri_parts.append(f"钠{na:g}mg")
    if fiber is not None:
        nutri_parts.append(f"纤维{fiber:g}g")
    if nutri_parts:
        parts.append("营养：" + "、".join(nutri_parts))

    if seasonal:
        parts.append(f"应季季节：{'、'.join(seasonal)}")
    if effects:
        parts.append(f"食养功效：{'、'.join(effects[:5])}")

    return "\n".join(parts)


# ----------------------------------------------------------------------
# 向量存读
# ----------------------------------------------------------------------


def _save(npz_path: str, ids: list[str], vecs: list[np.ndarray]) -> None:
    os.makedirs(os.path.dirname(npz_path), exist_ok=True)
    arr_ids = np.array(ids, dtype="<U64")  # 定长 unicode，allow_pickle=False 能加载
    arr_vecs = np.stack(vecs).astype(np.float16)
    tmp = npz_path + ".tmp.npz"
    np.savez_compressed(tmp, ids=arr_ids, vecs=arr_vecs)
    os.replace(tmp, npz_path)  # 原子写
    logger.info("✓ 向量索引保存到 %s（%d 条，%.1f MB）", npz_path, len(ids), os.path.getsize(npz_path) / 1024 / 1024)


def _load_existing(npz_path: str) -> dict[str, int]:
    """增量模式：读已有 npz 返回 {id: 行号}，已有的向量就跳过。"""
    if not os.path.isfile(npz_path):
        return {}
    try:
        data = np.load(npz_path, allow_pickle=False)
        ids = data["ids"].astype(str)
        return {str(rid): i for i, rid in enumerate(ids)}
    except Exception:
        return {}


# ----------------------------------------------------------------------
# 主流程
# ----------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(description="构建菜定向量索引")
    parser.add_argument("--rebuild", action="store_true", help="全量重建（忽略已有向量）")
    parser.add_argument("--limit", type=int, default=0, help="只处理前 N 条（调试用）")
    parser.add_argument("--dry-run", action="store_true", help="只构建文本不调 API（看模板效果）")
    args = parser.parse_args()

    if not args.dry_run and not is_embedding_configured():
        logger.error("Embedding 未配置，退出。检查 EMBEDDING_API_KEY / AI_API_KEY / EMBEDDING_BASE_URL")
        sys.exit(1)

    os.makedirs(OUTPUT_DIR, exist_ok=True)

    with Session(engine) as session:
        # 1. 读菜
        dishes = _list_all_dishes(session)
        if args.limit > 0:
            dishes = dishes[: args.limit]

        # 2. 批量读食材
        all_food_ids_set: set[int] = set()
        all_dish_ids = [d["id"] for d in dishes]
        ing_map = _load_ingredients(session, all_dish_ids)
        for mains, all_names in ing_map.values():
            # 从 main 表里查 ingredient_id 太麻烦，直接按名字反查 effects
            pass

        # 3. 时令月份
        seasonal_map = _load_seasonal_months(session, all_dish_ids)

        # 4. effects 从 ingredients 表查（按食材名匹配回来）
        compact = uses_compact_catalog(engine)
        food_name_to_effects: dict[str, list[str]] = {}
        if compact:
            rows = session.execute(
                sqlt("SELECT id, name, effects_json FROM ingredients WHERE is_edible = 1")
            ).mappings()
            for row in rows:
                fid = int(row["id"])
                fname = str(row["name"] or "")
                raw = row.get("effects_json")
                if not fname or not raw:
                    continue
                try:
                    tags = json.loads(raw) if isinstance(raw, str) else raw
                    if isinstance(tags, list):
                        food_name_to_effects[fname] = [str(t) for t in tags if t]
                except (json.JSONDecodeError, TypeError):
                    continue

        # 5. 读已有向量（增量模式）
        existing = {} if args.rebuild else _load_existing(OUTPUT_FILE)
        logger.info("已存在 %d 条向量，本次 %d 道菜（%s）",
                    len(existing), len(dishes),
                    "全量重建" if args.rebuild else "增量模式")

        # 6. 逐条构建文本
        texts: list[str] = []
        ids_out: list[str] = []
        for dish in dishes:
            did = dish["id"]
            if not args.rebuild and str(did) in existing:
                continue

            mains, all_names = ing_map.get(did, ([], []))

            # tags_json 可能是 JSON 字符串
            tags_raw = dish["tags_json"]
            tags = []
            if tags_raw:
                try:
                    tags = json.loads(tags_raw) if isinstance(tags_raw, str) else tags_raw
                    tags = [str(t) for t in tags if t]
                except (json.JSONDecodeError, TypeError):
                    tags = []

            seasonal = seasonal_map.get(did, [])

            # 功效：主料里有哪些食材带功效
            effects: list[str] = []
            for m in mains[:5]:
                eff = food_name_to_effects.get(m)
                if eff:
                    for e in eff:
                        if e not in effects:
                            effects.append(e)

            text = _build_embedding_text(
                dish, mains, all_names, tags, seasonal, effects,
            )
            texts.append(text)
            ids_out.append(str(did))

    # 7. Dry-run：只看文本
    if args.dry_run:
        logger.info("=== DRY RUN：构建了 %d 条文本 ===", len(texts))
        sample = texts[0] if texts else "(无)"
        logger.info("--- 样例文本 ---\n%s\n--- END ---", sample)
        return

    # 8. 调 embedding API（逐条，失败零向量占位）
    logger.info("开始调用 embedding API，共 %d 条……", len(texts))
    vecs: list[np.ndarray] = []
    zero_vec = np.zeros(settings.embedding_dim, dtype=np.float32)
    t0 = time.perf_counter()
    for i, text in enumerate(texts):
        if i % 50 == 0:
            elapsed = time.perf_counter() - t0
            rate = (i + 1) / elapsed if elapsed > 0 else 0
            logger.info("  %d/%d（%.1f 条/秒）", i, len(texts), rate)

        v = embed_text(text)
        if v is None:
            logger.warning("  第 %d 条 embedding 失败，零向量占位", i)
            vecs.append(zero_vec.copy())
        else:
            vecs.append(np.array(v, dtype=np.float32))

        # 限速：每条之间间隔 0.1s，防止把服务打爆
        time.sleep(0.1)

    elapsed = time.perf_counter() - t0
    coverage = int(sum(1 for v in vecs if np.linalg.norm(v) > 0))
    logger.info("Embedding 完成：%d/%d 成功，耗时 %.1fs（%.1f 条/秒）",
                coverage, len(texts), elapsed, len(texts) / elapsed if elapsed > 0 else 0)

    # 9. 合并已有向量 + 新向量，一起保存
    if existing and not args.rebuild:
        logger.info("合并已有 %d + 新增 %d", len(existing), len(vecs))
        # 读回已有
        data = np.load(OUTPUT_FILE, allow_pickle=False)
        old_ids = data["ids"].astype(str).tolist()
        old_vecs = data["vecs"].astype(np.float32)

        # 构建 {id: 新向量} 的覆盖映射
        id_to_new_vec = {id_: v for id_, v in zip(ids_out, vecs)}

        # 已有向量里被重建的替换掉
        new_vec_list = []
        for i, old_id in enumerate(old_ids):
            if old_id in id_to_new_vec:
                new_vec_list.append(id_to_new_vec.pop(old_id))
            else:
                new_vec_list.append(old_vecs[i])

        # 剩下的新 id（增量）追加
        for remaining_id, remaining_v in id_to_new_vec.items():
            old_ids.append(remaining_id)
            new_vec_list.append(remaining_v)

        _save(OUTPUT_FILE, old_ids, new_vec_list)
    else:
        _save(OUTPUT_FILE, ids_out, vecs)


if __name__ == "__main__":
    main()
