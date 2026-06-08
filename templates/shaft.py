"""
阶梯轴参数化模板

支持：多段圆柱、键槽、卡环槽、中心孔、螺纹段、倒角/圆角
标准：GB/T 1096 平键, GB/T 894 轴用挡圈, GB/T 145 中心孔

用法：
    from templates.shaft import ShaftBuilder
    shaft = ShaftBuilder(params)
    shaft.build(sw_app)
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from enum import Enum
import math
import json


# ============================================
# 数据模型
# ============================================

class FeatureType(Enum):
    PLAIN = "plain"              # 光轴段
    KEYWAY = "keyway"            # 键槽
    RETAINING_GROOVE = "retaining_groove"  # 卡环槽
    THREAD = "thread"            # 螺纹
    SPLINE = "spline"            # 花键
    CENTER_HOLE = "center_hole"  # 中心孔
    OIL_GROOVE = "oil_groove"   # 油槽

@dataclass
class ShaftSegment:
    """单个轴段"""
    diameter: float              # 直径 mm
    length: float                # 长度 mm
    features: List[Tuple[FeatureType, dict]] = field(default_factory=list)
    chamfer_left: float = 0      # 左端倒角 mm
    chamfer_right: float = 0     # 右端倒角 mm
    fillet_left: float = 0       # 左过渡圆角半径 mm
    fillet_right: float = 0      # 右过渡圆角半径 mm
    tolerance: str = ""          # 公差代号 e.g. "k6", "js6"
    surface_roughness: float = 3.2  # Ra μm

    def __post_init__(self):
        # 自动推导倒角（如果未指定）
        if self.chamfer_left == 0 and self.diameter < 80:
            self.chamfer_left = 1.0 if self.diameter < 50 else 1.5
        if self.chamfer_right == 0 and self.diameter < 80:
            self.chamfer_right = 1.0 if self.diameter < 50 else 1.5

@dataclass
class ShaftParams:
    """完整的轴设计参数"""
    name: str = "传动轴"
    segments: List[ShaftSegment] = field(default_factory=list)
    material: str = "45钢"
    heat_treatment: str = "调质"  # 调质/正火/渗碳淬火...
    overall_length: float = 0     # 自动计算
    max_diameter: float = 0       # 自动计算

    def __post_init__(self):
        if self.segments:
            self.overall_length = sum(s.length for s in self.segments)
            self.max_diameter = max(s.diameter for s in self.segments)

    def validate(self) -> List[str]:
        """验证设计合理性，返回警告列表"""
        warnings = []
        L, D = self.overall_length, self.max_diameter

        # 长径比检查
        if D > 0 and L / D > 15:
            warnings.append(f"⚠️ 长径比 L/D={L/D:.1f} > 15，建议增加中间支承或缩短轴长")
        elif D > 0 and L / D < 3:
            warnings.append(f"⚠️ 长径比 L/D={L/D:.1f} < 3，可能为短轴或盘类零件")

        # 相邻段直径差检查（避免应力集中）
        for i in range(len(self.segments) - 1):
            d1, d2 = self.segments[i].diameter, self.segments[i+1].diameter
            if d1 > 0:
                ratio = abs(d2 - d1) / d1
                if ratio > 0.3:
                    warnings.append(f"  段{i+1}→段{i+2}: 直径变化 {ratio*100:.0f}%，应力集中较大，建议增加过渡圆角")

        # 最大直径合理性
        if D < 10:
            warnings.append("  最大直径 < 10mm，注意加工刚性")
        if D > 500:
            warnings.append("  最大直径 > 500mm，注意毛坯选择和加工能力")

        return warnings

    def summary(self) -> str:
        """生成参数摘要表"""
        lines = [
            "┌─────────────────────────────────────────────┐",
            f"│ 零件名称：{self.name:<33}│",
            f"│ 材料：{self.material:<38}│",
            f"│ 热处理：{self.heat_treatment:<36}│",
            f"│ 总长：{self.overall_length}mm{' ' * (32-len(str(self.overall_length)))}│",
            f"│ 最大直径：{self.max_diameter}mm{' ' * (30-len(str(self.max_diameter)))}│",
            "├──────┬──────────┬──────────┬────────────────┤",
            "│ 段号 │ 直径(mm) │ 长度(mm) │ 特征           │",
            "├──────┼──────────┼──────────┼────────────────┤",
        ]
        for i, seg in enumerate(self.segments, 1):
            feat_str = ", ".join([f[0].value for f in seg.features]) or "光轴"
            lines.append(f"│ {i:<4} │ {seg.diameter:<8} │ {seg.length:<8} │ {feat_str:<14} │")
        lines.append("└──────┴──────────┴──────────┴────────────────┘")
        return "\n".join(lines)


# ============================================
# 参数化生成器
# ============================================

class ShaftBuilder:
    """从参数生成轴零件的 JSON 描述 / SolidWorks 模型"""

    KEYWAY_SPEC = {
        # diameter_range: (width, depth_on_shaft)
        6: (6, 3.5), 8: (8, 4.0), 10: (10, 5.0),
        12: (12, 5.5), 14: (14, 6.0), 16: (16, 7.0),
        18: (18, 7.5), 20: (20, 8.5), 22: (22, 9.5),
    }

    @staticmethod
    def recommend_keyway(diameter: float) -> Optional[Tuple[int, float, float]]:
        """
        根据轴径推荐标准平键。

        Returns:
            (键宽b, 轴上槽深t1, 键长L) 或 None
        """
        ranges = [
            (17, 22, 6), (22, 30, 8), (30, 38, 10),
            (38, 44, 12), (44, 50, 14), (50, 58, 16),
            (58, 65, 18), (65, 75, 20), (75, 85, 22),
        ]
        for lo, hi, w in ranges:
            if lo <= diameter < hi:
                width, depth = ShaftBuilder.KEYWAY_SPEC[w]
                # 键长建议 1.2~1.8 倍轴径
                length = round(diameter * 1.5, -1)  # 圆整到10
                return (width, depth, max(length, 10))
        return None

    @staticmethod
    def recommend_chamfer(diameter: float) -> float:
        if diameter < 30: return 0.5
        elif diameter < 50: return 1.0
        elif diameter < 80: return 1.5
        else: return 2.0

    @staticmethod
    def recommend_fillet(diameter: float) -> float:
        if diameter < 30: return 0.5
        elif diameter < 60: return 1.0
        elif diameter < 100: return 1.5
        else: return 2.0

    @staticmethod
    def build_json(params: ShaftParams) -> dict:
        """
        将 ShaftParams 转换成 JSON 零件描述。

        几何策略：
        - 以轴左端面为原点 Z=0
        - 轴的轴线沿 Z 轴
        - 每个轴段通过旋转特征生成（截面绕中心线旋转360°）
        - 键槽通过拉伸切除生成
        """
        z = 0.0  # 当前 Z 位置
        features = []

        # 主旋转体轮廓：轴截面
        # 从原点开始，每一步走到下一个直径台阶
        profile_points = []
        prev_d = None

        for i, seg in enumerate(params.segments):
            if i == 0:
                # 第一段：从中心线开始
                profile_points.append({"z": z, "r": 0})  # 轴端面起点
                if seg.chamfer_left > 0:
                    # 倒角点：径向偏移
                    profile_points.append({"z": z, "r": seg.diameter / 2 - seg.chamfer_left})
                profile_points.append({"z": z, "r": seg.diameter / 2})
            else:
                # 过渡圆角
                if seg.fillet_left > 0:
                    profile_points.append({"z": z, "r": seg.diameter / 2, "fillet": seg.fillet_left})
                else:
                    profile_points.append({"z": z, "r": seg.diameter / 2})

            z += seg.length

            # 段末尾
            if i < len(params.segments) - 1:
                next_d = params.segments[i + 1].diameter
                if next_d < seg.diameter:
                    # 直径减小
                    if seg.chamfer_right > 0:
                        profile_points.append({"z": z - seg.chamfer_right, "r": seg.diameter / 2})
                        profile_points.append({"z": z, "r": next_d / 2})
                    else:
                        profile_points.append({"z": z, "r": seg.diameter / 2})
                        profile_points.append({"z": z, "r": next_d / 2})
                else:
                    profile_points.append({"z": z, "r": seg.diameter / 2})
            else:
                # 最后一段的末端
                if seg.chamfer_right > 0:
                    profile_points.append({"z": z - seg.chamfer_right, "r": seg.diameter / 2})
                    profile_points.append({"z": z, "r": seg.diameter / 2 - seg.chamfer_right})
                profile_points.append({"z": z, "r": seg.diameter / 2})
                profile_points.append({"z": z, "r": 0})  # 回到中心线

        features.append({
            "type": "revolve",
            "name": "轴主体",
            "angle": 360,
            "profile": profile_points,
            "axis": "Z",
        })

        # 键槽特征
        z = 0.0
        keyway_count = 0
        for i, seg in enumerate(params.segments):
            for feat_type, feat_data in seg.features:
                if feat_type == FeatureType.KEYWAY:
                    kw = ShaftBuilder.recommend_keyway(seg.diameter)
                    if kw:
                        keyway_count += 1
                        kw_z_center = z + seg.length / 2
                        features.append({
                            "type": "cut_extrude",
                            "name": f"键槽{keyway_count} ({kw[0]}×{kw[1]}×{kw[2]})",
                            "sketch_plane": "top_plane",
                            "sketch": {
                                "type": "keyway_slot",
                                "width": kw[0],
                                "length": kw[2],
                                "depth": kw[1],
                            },
                            "position_z": kw_z_center,
                            "diameter": seg.diameter,
                        })
                elif feat_type == FeatureType.RETAINING_GROOVE:
                    features.append({
                        "type": "revolve_cut",
                        "name": f"卡环槽 D{seg.diameter}",
                        "position_z": z + feat_data.get("offset", 2),
                        "groove_width": feat_data.get("width", 1.3),
                        "groove_depth": feat_data.get("depth", 0.5),
                        "diameter": seg.diameter,
                    })
                elif feat_type == FeatureType.CENTER_HOLE:
                    features.append({
                        "type": "revolve_cut",
                        "name": "中心孔 (GB/T 145 B型)",
                        "position_z": z,  # 轴端
                        "hole_diameter": seg.diameter * 0.1,
                        "depth": seg.diameter * 0.15,
                    })
            z += seg.length

        # 最终输出
        return {
            "name": params.name,
            "version": "1.0",
            "material": params.material,
            "heat_treatment": params.heat_treatment,
            "overall_length": params.overall_length,
            "max_diameter": params.max_diameter,
            "unit": "mm",
            "segments": [{"index": i, "diameter": s.diameter, "length": s.length,
                          "features": [f[0].value for f in s.features]}
                         for i, s in enumerate(params.segments)],
            "features": features,
            "warnings": params.validate(),
        }


# ============================================
# 方便的工厂函数
# ============================================

def create_simple_shaft(diameters: List[float], lengths: List[float],
                        name: str = "传动轴", material: str = "45钢") -> ShaftParams:
    """
    快速创建简单阶梯轴。

    Args:
        diameters: 各段直径 [30, 40, 35] 单位mm
        lengths: 各段长度 [50, 60, 40] 单位mm
        name: 零件名称
        material: 材料

    Returns:
        ShaftParams 对象
    """
    if len(diameters) != len(lengths):
        raise ValueError(f"直径和长度数量必须一致: {len(diameters)} vs {len(lengths)}")

    segments = []
    for d, l in zip(diameters, lengths):
        chamfer = ShaftBuilder.recommend_chamfer(d)
        segments.append(ShaftSegment(
            diameter=d,
            length=l,
            chamfer_left=chamfer,
            chamfer_right=chamfer,
            fillet_left=ShaftBuilder.recommend_fillet(d),
            fillet_right=ShaftBuilder.recommend_fillet(d),
        ))

    return ShaftParams(name=name, material=material, segments=segments)


def create_transmission_shaft(power_kw: float, speed_rpm: float,
                              output_diameter: float, bearing_positions: List[float],
                              material: str = "45钢") -> ShaftParams:
    """
    根据传动参数创建传动轴。

    Args:
        power_kw: 传递功率 kW
        speed_rpm: 转速 rpm
        output_diameter: 输出端直径（连接联轴器/齿轮）
        bearing_positions: 轴承位置 [距左端距离, ...]
        material: 材料

    Returns:
        ShaftParams 对象
    """
    # 按扭转强度估算最小轴径
    A = {"45钢": 118, "40Cr": 108, "Q235": 135}.get(material, 118)
    d_min = A * (power_kw / speed_rpm) ** (1/3)
    d_min = math.ceil(d_min / 5) * 5  # 圆整到5

    print(f"[Calc] 估算最小轴径: {d_min:.0f}mm (P={power_kw}kW, n={speed_rpm}rpm, {material})")

    # 构建阶梯轴：轴承位直径 = max(d_min, 轴承标准值)
    bearing_d = max(d_min, 20)
    bearing_d = math.ceil(bearing_d / 5) * 5  # 圆整到5（轴承标准内径）

    segments = [
        ShaftSegment(diameter=output_diameter, length=60, features=[(FeatureType.KEYWAY, {})],
                     tolerance="k6"),
        ShaftSegment(diameter=bearing_d, length=25, tolerance="js6"),
        ShaftSegment(diameter=bearing_d + 5, length=50),
        ShaftSegment(diameter=bearing_d, length=25, tolerance="js6"),
        ShaftSegment(diameter=output_diameter, length=60, features=[(FeatureType.KEYWAY, {})],
                     tolerance="k6"),
    ]

    return ShaftParams(name="传动轴", material=material, segments=segments)


# ============================================
# CLI 测试
# ============================================

if __name__ == "__main__":
    # 示例1：简单的3段阶梯轴
    print("=" * 50)
    print("示例1：简单阶梯轴")
    print("=" * 50)
    shaft1 = create_simple_shaft(
        diameters=[25, 35, 30],
        lengths=[50, 60, 40],
        name="泵轴"
    )
    print(shaft1.summary())
    for w in shaft1.validate():
        print(w)

    # 输出 JSON
    json_output = ShaftBuilder.build_json(shaft1)
    print(f"\n[Features] 生成 {len(json_output['features'])} 个特征:")
    for f in json_output['features']:
        print(f"   - {f['name']}")

    # 示例2：传动轴（含键槽）
    print("\n" + "=" * 50)
    print("示例2：传动轴（带键槽）")
    print("=" * 50)
    shaft2 = create_transmission_shaft(
        power_kw=5.5, speed_rpm=1450,
        output_diameter=30, bearing_positions=[80, 180],
        material="45钢"
    )
    print(shaft2.summary())
