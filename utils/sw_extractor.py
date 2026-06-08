"""
SolidWorks 文件知识提取器

从已有的 .sldprt / .sldasm 文件中提取结构化设计知识，
存入 knowledge/learned_parts/ 供 AI 学习和参考。

用法：
    python sw_extractor.py --input "my_part.sldprt" --output knowledge/learned_parts/

依赖：
    - SolidWorks 2018+ (COM API)
    - pip install pywin32
"""

import json
import os
import sys
import hashlib
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import List, Optional, Dict, Any, Tuple
from enum import Enum


# ============================================
# 提取结果数据模型
# ============================================

class PartType(Enum):
    SHAFT = "shaft"
    PISTON = "piston"
    FLANGE = "flange"
    GEAR = "gear"
    BRACKET = "bracket"
    HOUSING = "housing"
    PLATE = "plate"
    UNKNOWN = "unknown"

@dataclass
class ExtractedDimension:
    """提取到的关键尺寸"""
    name: str
    value: float
    unit: str = "mm"
    category: str = ""  # overall, feature, pattern, clearance, etc.
    context: str = ""    # 这个尺寸来自哪个特征

@dataclass
class ExtractedFeature:
    """提取到的特征"""
    name: str
    type: str          # Extrude, Revolve, Cut, Fillet, Chamfer, Pattern, etc.
    parameters: Dict[str, Any] = field(default_factory=dict)
    sketch_info: Optional[Dict] = None
    suppressed: bool = False
    parent_features: List[str] = field(default_factory=list)

@dataclass
class ExtractedPart:
    """从 .sldprt 提取的完整零件知识"""
    filename: str
    file_hash: str              # 文件哈希，用于去重
    extracted_date: str

    # 文档属性
    part_name: str = ""
    material: str = ""
    author: str = ""
    description: str = ""

    # 自定义属性
    custom_properties: Dict[str, str] = field(default_factory=dict)

    # 物理属性
    mass_kg: float = 0.0
    volume_mm3: float = 0.0
    surface_area_mm2: float = 0.0
    bounding_box: Dict[str, float] = field(default_factory=dict)

    # 推断的零件类型
    part_type: str = "unknown"
    part_type_confidence: float = 0.0

    # 结构化的关键尺寸
    dimensions: List[ExtractedDimension] = field(default_factory=list)

    # 特征树
    features: List[ExtractedFeature] = field(default_factory=list)

    # 设计参数反向推导
    inferred_params: Dict[str, Any] = field(default_factory=dict)

    # 原始提取数据（保留完整信息）
    raw_feature_count: int = 0
    sketch_count: int = 0


# ============================================
# SW 文件解析器
# ============================================

class SWFileExtractor:
    """从 SolidWorks 文件提取结构化知识"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self._app = None
        self._doc = None
        self._available = False
        self._init_sw()

    def _init_sw(self):
        """尝试连接 SolidWorks"""
        try:
            import win32com.client
            self._app = win32com.client.Dispatch("SldWorks.Application")
            self._available = True
        except Exception:
            self._available = False
            print("[WARN] SolidWorks 不可用，将尝试离线解析（仅支持基本属性）")

    def _open_document(self):
        """打开文档"""
        if not self._available:
            return False
        try:
            # 尝试以只读方式打开
            self._doc = self._app.OpenDoc6(
                self.filepath, 1, 0, "", 0, 0  # 1=零件
            )
            return self._doc is not None
        except Exception:
            # 尝试作为装配体打开
            try:
                self._doc = self._app.OpenDoc6(
                    self.filepath, 2, 0, "", 0, 0  # 2=装配体
                )
                return self._doc is not None
            except Exception:
                return False

    def _close_document(self):
        """关闭文档"""
        if self._doc and self._available:
            try:
                self._app.CloseDoc(self.filepath)
            except Exception:
                pass

    def extract(self) -> Optional[ExtractedPart]:
        """
        提取文件的完整结构化知识。

        Returns:
            ExtractedPart 或 None（失败时）
        """
        # 计算文件哈希
        file_hash = self._hash_file()

        # 创建基础结果
        result = ExtractedPart(
            filename=os.path.basename(self.filepath),
            file_hash=file_hash,
            extracted_date=datetime.now().isoformat(),
        )

        if self._available and self._open_document():
            try:
                self._extract_document_properties(result)
                self._extract_custom_properties(result)
                self._extract_mass_properties(result)
                self._extract_features(result)
                self._extract_dimensions(result)
                self._infer_part_type(result)
                self._infer_design_params(result)
            finally:
                self._close_document()
        else:
            # 离线模式：只能提取基本文件信息
            self._extract_file_info_only(result)

        return result

    def _hash_file(self) -> str:
        """计算文件的 SHA256 哈希"""
        sha = hashlib.sha256()
        try:
            with open(self.filepath, "rb") as f:
                while chunk := f.read(8192):
                    sha.update(chunk)
        except Exception:
            return "unknown"
        return sha.hexdigest()[:16]

    def _extract_document_properties(self, result: ExtractedPart):
        """提取文档属性"""
        try:
            summary = self._doc.SummaryInfo
            if summary:
                result.author = self._safe_get(summary, "Author") or ""
                result.description = self._safe_get(summary, "Subject") or ""
                result.part_name = self._safe_get(summary, "Title") or ""
        except Exception:
            pass

    def _extract_custom_properties(self, result: ExtractedPart):
        """提取自定义属性（包含材料、零件号等重要信息）"""
        try:
            custom_mgr = self._doc.Extension.CustomPropertyManager("")
            if custom_mgr:
                prop_names = custom_mgr.GetNames()
                if prop_names:
                    for name in prop_names:
                        try:
                            value = custom_mgr.Get2(name)
                            result.custom_properties[name] = str(value) if value else ""
                        except Exception:
                            pass

                    # 识别材料
                    if "Material" in result.custom_properties:
                        result.material = result.custom_properties["Material"]
                    elif "材料" in result.custom_properties:
                        result.material = result.custom_properties["材料"]

                    # 识别零件号
                    if "Number" in result.custom_properties:
                        result.custom_properties["part_number"] = result.custom_properties["Number"]
        except Exception:
            pass

    def _extract_mass_properties(self, result: ExtractedPart):
        """提取物理属性"""
        try:
            mass_props = self._doc.Extension.CreateMassProperty()
            if mass_props:
                result.mass_kg = round(mass_props.Mass, 3)
                result.volume_mm3 = round(mass_props.Volume * 1e9, 1)  # m³ → mm³
                result.surface_area_mm2 = round(mass_props.SurfaceArea * 1e6, 1)  # m² → mm²

                # 包围盒
                try:
                    box = self._doc.GetPartBox(False)
                    if box:
                        result.bounding_box = {
                            "x_min": round(box[0] * 1000, 1),  # m → mm
                            "y_min": round(box[1] * 1000, 1),
                            "z_min": round(box[2] * 1000, 1),
                            "x_max": round(box[3] * 1000, 1),
                            "y_max": round(box[4] * 1000, 1),
                            "z_max": round(box[5] * 1000, 1),
                            "x_len": round((box[3] - box[0]) * 1000, 1),
                            "y_len": round((box[4] - box[1]) * 1000, 1),
                            "z_len": round((box[5] - box[2]) * 1000, 1),
                        }
                except Exception:
                    pass
        except Exception:
            pass

    def _extract_features(self, result: ExtractedPart):
        """提取特征树"""
        try:
            feature = self._doc.FirstFeature()
            while feature:
                feat = self._parse_feature(feature)
                if feat:
                    result.features.append(feat)
                feature = feature.GetNextFeature()
            result.raw_feature_count = len(result.features)
        except Exception:
            pass

    def _parse_feature(self, feature) -> Optional[ExtractedFeature]:
        """解析单个特征"""
        try:
            name = feature.Name
            feat_type = feature.GetTypeName2()

            params = {}
            feat_data = feature.GetDefinition()

            # 根据不同特征类型提取参数
            if feat_type == "Extrusion":
                self._extract_extrude_params(feat_data, params)
            elif feat_type == "Revolve":
                self._extract_revolve_params(feat_data, params)
            elif feat_type == "Fillet":
                self._extract_fillet_params(feat_data, params)
            elif feat_type == "Chamfer":
                self._extract_chamfer_params(feat_data, params)
            elif "Cut" in feat_type:
                params["feature_type"] = "cut"

            return ExtractedFeature(
                name=name,
                type=feat_type,
                parameters=params,
                suppressed=feature.IsSuppressed(),
            )
        except Exception:
            return None

    def _extract_extrude_params(self, feat_data, params: dict):
        """提取拉伸特征参数"""
        try:
            params["depth"] = round(feat_data.GetDepth(True) * 1000, 2)  # m → mm
            params["d1_direction"] = "blind"
            params["d2_depth"] = round(feat_data.GetDepth(False) * 1000, 2)
        except Exception:
            pass

    def _extract_revolve_params(self, feat_data, params: dict):
        """提取旋转特征参数"""
        try:
            params["angle"] = round(feat_data.Angle, 1)
        except Exception:
            pass

    def _extract_fillet_params(self, feat_data, params: dict):
        """提取圆角特征参数"""
        try:
            radius = feat_data.GetRadius(0)
            params["radius"] = round(radius * 1000, 2)
        except Exception:
            pass

    def _extract_chamfer_params(self, feat_data, params: dict):
        """提取倒角特征参数"""
        try:
            params["distance"] = round(feat_data.Distance * 1000, 2)
        except Exception:
            pass

    def _extract_dimensions(self, result: ExtractedPart):
        """提取关键尺寸"""
        # 从包围盒提取总体尺寸
        if result.bounding_box:
            bb = result.bounding_box
            result.dimensions.append(ExtractedDimension(
                name="overall_length", value=bb["z_len"],
                category="overall", context="bounding_box"
            ))
            result.dimensions.append(ExtractedDimension(
                name="overall_width", value=bb["x_len"],
                category="overall", context="bounding_box"
            ))
            result.dimensions.append(ExtractedDimension(
                name="overall_height", value=bb["y_len"],
                category="overall", context="bounding_box"
            ))

        # 从特征提取尺寸
        for feat in result.features:
            if feat.type == "Extrusion" and "depth" in feat.parameters:
                result.dimensions.append(ExtractedDimension(
                    name=f"{feat.name}_depth",
                    value=feat.parameters["depth"],
                    category="feature",
                    context=feat.name
                ))

    def _infer_part_type(self, result: ExtractedPart):
        """从特征名称和几何推断零件类型"""
        name_lower = (result.part_name + " " + os.path.basename(result.filepath)).lower()
        features_lower = " ".join([f.name.lower() for f in result.features])

        type_scores = {
            "shaft": ["轴", "shaft", "spindle"],
            "piston": ["活塞", "piston"],
            "flange": ["法兰", "flange"],
            "gear": ["齿轮", "gear", "tooth"],
            "bracket": ["支架", "bracket", "mount", "座"],
            "housing": ["壳体", "箱体", "housing", "case"],
            "plate": ["板", "plate", "cover", "盖"],
        }

        best_type = "unknown"
        best_score = 0

        for ptype, keywords in type_scores.items():
            score = sum(1 for kw in keywords if kw in name_lower or kw in features_lower)
            if score > best_score:
                best_score = score
                best_type = ptype

        result.part_type = best_type
        result.part_type_confidence = min(best_score / 3, 1.0)  # 归一化到0~1

    def _infer_design_params(self, result: ExtractedPart):
        """从提取数据反向推导设计参数"""
        bb = result.bounding_box
        if not bb:
            return

        inferred = {}

        if result.part_type == "shaft":
            # 推断轴的参数
            lengths = [bb["z_len"]]
            diameters = [max(bb["x_len"], bb["y_len"])]
            inferred["estimated_segments"] = 1
            inferred["total_length"] = bb["z_len"]
            inferred["max_diameter"] = max(bb["x_len"], bb["y_len"])
            # 长径比
            d = inferred["max_diameter"]
            if d > 0:
                inferred["slenderness_ratio"] = round(bb["z_len"] / d, 2)

        elif result.part_type == "piston":
            # 推断活塞参数
            diameter = max(bb["x_len"], bb["y_len"])
            inferred["cylinder_diameter"] = diameter
            inferred["total_length"] = bb["z_len"]
            if diameter > 0:
                inferred["length_diameter_ratio"] = round(bb["z_len"] / diameter, 2)

        elif result.part_type == "flange":
            inferred["outer_diameter"] = max(bb["x_len"], bb["y_len"])
            inferred["thickness"] = bb["z_len"]

        result.inferred_params = inferred

    def _extract_file_info_only(self, result: ExtractedPart):
        """离线模式：仅提取文件基本信息"""
        result.part_name = os.path.splitext(os.path.basename(self.filepath))[0]
        result.part_type = "unknown"
        try:
            stat = os.stat(self.filepath)
            result.custom_properties["file_size_bytes"] = str(stat.st_size)
            result.custom_properties["file_modified"] = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except Exception:
            pass

    @staticmethod
    def _safe_get(obj, attr: str, default: Any = "") -> Any:
        """安全获取 COM 对象属性"""
        try:
            val = getattr(obj, attr)
            return val if val is not None else default
        except Exception:
            return default


# ============================================
# 批量提取工具
# ============================================

class BatchExtractor:
    """批量提取目录中的 SW 文件"""

    def __init__(self, input_dir: str, output_dir: str):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.results: List[ExtractedPart] = []
        self.failures: List[str] = []

    def scan_files(self, extensions: List[str] = None) -> List[str]:
        """扫描目录中的 SW 文件"""
        if extensions is None:
            extensions = [".sldprt", ".sldprt", ".SLDPRT"]
        files = []
        for root, _, filenames in os.walk(self.input_dir):
            for fn in filenames:
                if any(fn.endswith(ext) for ext in extensions):
                    files.append(os.path.join(root, fn))
        return files

    def extract_all(self) -> Dict:
        """提取所有文件"""
        files = self.scan_files()
        print(f"[Scan] 找到 {len(files)} 个 SW 文件")

        os.makedirs(self.output_dir, exist_ok=True)

        for i, filepath in enumerate(files):
            print(f"[{i+1}/{len(files)}] 提取: {os.path.basename(filepath)}")
            try:
                extractor = SWFileExtractor(filepath)
                result = extractor.extract()
                if result:
                    self.results.append(result)
                    self._save_result(result)
                else:
                    self.failures.append(filepath)
            except Exception as e:
                print(f"  [ERROR] {e}")
                self.failures.append(filepath)

        # 保存索引
        self._save_index()

        return {
            "total": len(files),
            "success": len(self.results),
            "failed": len(self.failures),
            "output_dir": self.output_dir,
        }

    def _save_result(self, part: ExtractedPart):
        """保存单个零件的提取结果"""
        safe_name = part.filename.replace("/", "_").replace("\\", "_")
        out_path = os.path.join(self.output_dir, f"{safe_name}.json")
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(self._to_dict(part), f, ensure_ascii=False, indent=2, default=str)

    def _save_index(self):
        """保存所有零件的索引文件"""
        index = {
            "extracted_date": datetime.now().isoformat(),
            "total_parts": len(self.results),
            "parts": []
        }
        for part in self.results:
            index["parts"].append({
                "filename": part.filename,
                "hash": part.file_hash,
                "part_name": part.part_name,
                "part_type": part.part_type,
                "material": part.material,
                "mass_kg": part.mass_kg,
                "dimensions_summary": {
                    d.name: d.value for d in part.dimensions if d.category == "overall"
                },
            })

        with open(os.path.join(self.output_dir, "_index.json"), "w", encoding="utf-8") as f:
            json.dump(index, f, ensure_ascii=False, indent=2)

    @staticmethod
    def _to_dict(part: ExtractedPart) -> dict:
        """将 ExtractedPart 转为可序列化的字典"""
        return {
            "filename": part.filename,
            "file_hash": part.file_hash,
            "extracted_date": part.extracted_date,
            "part_name": part.part_name,
            "material": part.material,
            "author": part.author,
            "description": part.description,
            "custom_properties": part.custom_properties,
            "mass_kg": part.mass_kg,
            "volume_mm3": part.volume_mm3,
            "surface_area_mm2": part.surface_area_mm2,
            "bounding_box": part.bounding_box,
            "part_type": part.part_type,
            "part_type_confidence": part.part_type_confidence,
            "dimensions": [asdict(d) for d in part.dimensions],
            "features": [
                {
                    "name": f.name,
                    "type": f.type,
                    "parameters": f.parameters,
                    "suppressed": f.suppressed,
                }
                for f in part.features[:50]  # 限制前50个特征
            ],
            "inferred_params": part.inferred_params,
            "raw_feature_count": part.raw_feature_count,
        }


# ============================================
# CLI 入口
# ============================================

def main():
    import argparse

    parser = argparse.ArgumentParser(description="从 SolidWorks 文件提取设计知识")
    parser.add_argument("--input", "-i", required=True, help="输入文件或目录")
    parser.add_argument("--output", "-o", default="./knowledge/learned_parts/", help="输出目录")
    parser.add_argument("--batch", "-b", action="store_true", help="批量模式（输入为目录）")

    args = parser.parse_args()

    if args.batch or os.path.isdir(args.input):
        batch = BatchExtractor(args.input, args.output)
        result = batch.extract_all()
        print(f"\n[Done] 成功 {result['success']}/{result['total']}, 输出到 {result['output_dir']}")
    else:
        extractor = SWFileExtractor(args.input)
        part = extractor.extract()
        if part:
            os.makedirs(args.output, exist_ok=True)
            out_path = os.path.join(args.output, f"{part.filename}.json")
            with open(out_path, "w", encoding="utf-8") as f:
                json.dump(BatchExtractor._to_dict(part), f, ensure_ascii=False, indent=2, default=str)
            print(f"[Done] 已提取到: {out_path}")
            print(f"  零件类型: {part.part_type} (置信度: {part.part_type_confidence:.0%})")
            print(f"  材料: {part.material or '未识别'}")
            print(f"  包围盒: {part.bounding_box}")
            print(f"  特征数: {part.raw_feature_count}")
        else:
            print("[ERROR] 提取失败")


if __name__ == "__main__":
    main()
