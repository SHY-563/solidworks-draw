"""
零件相似度搜索引擎

从 learned_parts/ 知识库中查找与目标参数最接近的已有零件，
帮助 AI 输出更符合企业标准的设计。

用法：
    from utils.similarity import PartSearcher
    searcher = PartSearcher("knowledge/learned_parts/")
    similar = searcher.search(part_type="shaft", diameter=30, length=150)
"""

import json
import os
import math
from typing import List, Dict, Optional, Any, Tuple
from dataclasses import dataclass


@dataclass
class MatchResult:
    """匹配结果"""
    filename: str
    part_name: str
    part_type: str
    material: str
    score: float              # 0~1 综合匹配分数
    dimension_similarity: float  # 尺寸相似度
    type_match: bool
    material_match: bool
    reference_path: str       # JSON 文件路径
    key_dims: Dict[str, float]


class PartSearcher:
    """在已学习的零件库中搜索相似零件"""

    def __init__(self, learned_dir: str):
        """
        Args:
            learned_dir: learned_parts/ 目录路径
        """
        self.learned_dir = learned_dir
        self._parts_cache: Optional[List[Dict]] = None

    @property
    def parts(self) -> List[Dict]:
        """加载所有已学习零件（缓存）"""
        if self._parts_cache is None:
            self._parts_cache = self._load_all()
        return self._parts_cache

    def reload(self):
        """强制重新加载"""
        self._parts_cache = None
        return self.parts

    def _load_all(self) -> List[Dict]:
        """加载目录中所有零件 JSON"""
        parts = []
        if not os.path.isdir(self.learned_dir):
            return parts

        for fn in os.listdir(self.learned_dir):
            if fn.startswith("_") or not fn.endswith(".json"):
                continue
            try:
                with open(os.path.join(self.learned_dir, fn), "r", encoding="utf-8") as f:
                    data = json.load(f)
                    data["_source_file"] = os.path.join(self.learned_dir, fn)
                    parts.append(data)
            except Exception:
                continue

        print(f"[DB] 加载 {len(parts)} 个已学习零件")
        return parts

    def search(
        self,
        part_type: str = None,
        target_dims: Dict[str, float] = None,
        material: str = None,
        top_k: int = 5,
        min_score: float = 0.3,
    ) -> List[MatchResult]:
        """
        搜索最相似的零件。

        Args:
            part_type: 目标零件类型 (shaft/piston/flange/...)
            target_dims: 目标尺寸 {"diameter": 30, "length": 200}
            material: 目标材料
            top_k: 返回前 K 个结果
            min_score: 最低分数阈值

        Returns:
            匹配结果列表，按分数降序排列
        """
        if target_dims is None:
            target_dims = {}

        results = []

        for part in self.parts:
            score, details = self._calculate_score(part, part_type, target_dims, material)
            if score >= min_score:
                results.append(MatchResult(
                    filename=part.get("filename", ""),
                    part_name=part.get("part_name", ""),
                    part_type=part.get("part_type", "unknown"),
                    material=part.get("material", ""),
                    score=score,
                    dimension_similarity=details["dim_sim"],
                    type_match=details["type_match"],
                    material_match=details["material_match"],
                    reference_path=part.get("_source_file", ""),
                    key_dims=self._extract_key_dims(part),
                ))

        results.sort(key=lambda r: r.score, reverse=True)
        return results[:top_k]

    def _calculate_score(
        self, part: Dict, target_type: str, target_dims: Dict[str, float], target_material: str
    ) -> Tuple[float, Dict]:
        """计算综合匹配分数"""
        weights = {
            "type": 0.25,       # 类型匹配权重
            "dimensions": 0.50,  # 尺寸相似度权重（最重要）
            "material": 0.15,    # 材料匹配权重
            "mass": 0.10,        # 质量合理性权重
        }

        # 1. 类型匹配
        type_score = 1.0 if part.get("part_type") == target_type else 0.3
        type_match = part.get("part_type") == target_type

        # 2. 尺寸相似度
        dim_sim = self._dimension_similarity(part, target_dims)

        # 3. 材料匹配
        part_material = part.get("material", "")
        material_score = 1.0 if part_material and target_material and \
            (part_material.lower() == target_material.lower()) else 0.0
        material_match = material_score > 0.5

        # 4. 质量合理性
        mass_score = self._mass_reasonability(part, target_dims)

        total = (
            weights["type"] * type_score +
            weights["dimensions"] * dim_sim +
            weights["material"] * material_score +
            weights["mass"] * mass_score
        )

        return total, {
            "dim_sim": dim_sim,
            "type_match": type_match,
            "material_match": material_match,
        }

    def _dimension_similarity(self, part: Dict, target: Dict[str, float]) -> float:
        """计算尺寸向量的余弦相似度"""
        if not target:
            return 0.5  # 无目标尺寸时给中等分数

        # 提取零件的关键尺寸
        part_dims = self._extract_key_dims(part)

        # 对齐尺寸名称
        alias_map = {
            "diameter": ["diameter", "max_diameter", "outer_diameter", "cylinder_diameter", "overall_width"],
            "length": ["length", "total_length", "overall_length", "overall_length_z"],
            "thickness": ["thickness", "overall_height", "depth"],
            "width": ["width", "overall_width", "overall_width_x"],
            "height": ["height", "overall_height", "overall_height_y"],
        }

        scores = []
        for target_key, target_val in target.items():
            if target_val <= 0:
                continue

            # 在零件尺寸中查找对应值
            best_match = None
            for alias in alias_map.get(target_key, [target_key]):
                if alias in part_dims:
                    best_match = part_dims[alias]
                    break

            if best_match and best_match > 0:
                # 使用比率相似度：ratio 越接近 1 分数越高
                ratio = min(target_val, best_match) / max(target_val, best_match)
                # 映射到 0~1：ratio=0.5 时得分约 0.33
                scores.append(ratio ** 0.5)
            else:
                scores.append(0)

        if not scores:
            return 0.5

        return sum(scores) / len(scores)

    def _mass_reasonability(self, part: Dict, target_dims: Dict[str, float]) -> float:
        """评估质量是否与尺寸匹配（排除异常值）"""
        mass = part.get("mass_kg", 0)
        if mass <= 0:
            return 0.5

        # 粗略估算：钢件密度约 7.85 g/cm³
        # 对于轴类：mass ≈ π/4 × d² × L × ρ
        bb = part.get("bounding_box", {})
        if bb:
            x, y, z = bb.get("x_len", 0), bb.get("y_len", 0), bb.get("z_len", 0)
            envelope_volume = (x * y * z) / 1000  # mm³ → cm³
            if envelope_volume > 0:
                # 实际填充率通常 20%~80%
                expected_mass_kg = envelope_volume * 7.85 / 1000 * 0.4  # 40% 填充率估算
                if expected_mass_kg > 0:
                    ratio = min(mass, expected_mass_kg) / max(mass, expected_mass_kg)
                    return ratio
        return 0.5

    @staticmethod
    def _extract_key_dims(part: Dict) -> Dict[str, float]:
        """从零件数据中提取关键尺寸字典"""
        dims = {}

        # 从 bounding_box
        bb = part.get("bounding_box", {})
        if bb:
            dims["overall_length"] = bb.get("z_len", 0)
            dims["overall_width"] = bb.get("x_len", 0)
            dims["overall_height"] = bb.get("y_len", 0)
            dims["diameter"] = max(bb.get("x_len", 0), bb.get("y_len", 0))
            dims["length"] = bb.get("z_len", 0)

        # 从 extracted dimensions
        for d in part.get("dimensions", []):
            dims[d.get("name", "")] = d.get("value", 0)

        # 从 inferred_params
        for k, v in part.get("inferred_params", {}).items():
            if isinstance(v, (int, float)):
                dims[k] = float(v)

        return dims

    def get_recommendations(
        self, part_type: str, target_dims: Dict[str, float], material: str = None
    ) -> Dict[str, Any]:
        """
        获取设计建议：基于相似零件推荐设计参数。

        Returns:
            {
                "similar_parts": [...],
                "recommended_material": "45钢",
                "recommended_range": {"diameter": [25, 35], "length": [100, 200]},
                "confidence": 0.85
            }
        """
        matches = self.search(part_type, target_dims, material, top_k=5, min_score=0.3)

        if not matches:
            return {
                "similar_parts": [],
                "recommended_material": None,
                "recommended_range": {},
                "confidence": 0.0,
                "note": "未找到足够相似的参考零件"
            }

        # 从相似零件中提取统计信息
        materials = {}
        dim_ranges = {}

        for m in matches:
            mat = m.material
            if mat:
                materials[mat] = materials.get(mat, 0) + 1

            for k, v in m.key_dims.items():
                if k not in dim_ranges:
                    dim_ranges[k] = []
                dim_ranges[k].append(v)

        # 推荐材料（出现最多的）
        best_material = max(materials, key=materials.get) if materials else None

        # 推荐尺寸范围
        recommended_range = {}
        for k, vals in dim_ranges.items():
            if len(vals) >= 2:
                recommended_range[k] = [round(min(vals), 1), round(max(vals), 1)]

        return {
            "similar_parts": [
                {
                    "name": m.part_name,
                    "file": m.filename,
                    "material": m.material,
                    "score": round(m.score, 3),
                    "key_dims": m.key_dims,
                }
                for m in matches
            ],
            "recommended_material": best_material,
            "recommended_range": recommended_range,
            "confidence": round(sum(m.score for m in matches) / len(matches), 2),
        }


# ============================================
# CLI 测试
# ============================================

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="搜索相似零件")
    parser.add_argument("--db", default="./knowledge/learned_parts/", help="知识库目录")
    parser.add_argument("--type", "-t", default="shaft", help="零件类型")
    parser.add_argument("--dims", "-d", nargs="*", help="尺寸 key=value")
    parser.add_argument("--material", "-m", default=None, help="材料")

    args = parser.parse_args()

    target_dims = {}
    if args.dims:
        for d in args.dims:
            k, v = d.split("=")
            target_dims[k] = float(v)

    searcher = PartSearcher(args.db)
    results = searcher.get_recommendations(args.type, target_dims, args.material)

    print(f"\n[Search] type={args.type}, dims={target_dims if target_dims else 'auto'}")
    print(f"[Results] 找到 {len(results['similar_parts'])} 个相似零件")
    print(f"[Recommended] 材料: {results['recommended_material']}")
    print(f"[Recommended] 尺寸范围: {results['recommended_range']}")
    print(f"[Confidence] {results['confidence']:.0%}")

    for i, p in enumerate(results["similar_parts"]):
        print(f"\n  {i+1}. {p['name']} (相似度: {p['score']:.0%})")
        print(f"     材料: {p['material']}, 文件: {p['file']}")
        print(f"     尺寸: {p['key_dims']}")
