"""
活塞参数化模板

用于往复式压缩机 / 内燃机活塞建模。
支持：活塞体、环槽、销孔、裙部、卸荷槽

设计规则参考：
- GB/T 1149 内燃机活塞环
- 压缩机设计手册

用法：
    from templates.piston import PistonBuilder, PistonParams
    piston = PistonBuilder(params)
    json_desc = piston.build_json()
"""

from dataclasses import dataclass, field
from typing import List, Optional, Tuple
import math


# ============================================
# 数据模型
# ============================================

@dataclass
class RingGroove:
    """环槽参数"""
    width: float              # 槽宽 mm
    depth: float              # 槽深 mm
    distance_from_top: float  # 距顶端距离 mm
    type: str = "compression" # compression=气环, oil=油环

@dataclass
class PistonParams:
    """活塞完整设计参数"""
    # 必需参数
    cylinder_diameter: float       # 缸径 D (mm)

    # 可选参数（自动推导的用 None）
    total_length: Optional[float] = None       # 总长
    skirt_length: Optional[float] = None       # 裙部长度
    crown_thickness: Optional[float] = None    # 顶部厚度
    pin_diameter: Optional[float] = None       # 活塞销直径
    pin_hole_length: Optional[float] = None    # 销孔长度
    ring_count: Optional[int] = None           # 气环数量
    oil_ring_count: int = 1                    # 油环数量
    skirt_wall_thickness: Optional[float] = None  # 裙部壁厚
    crown_to_pin_center: Optional[float] = None   # 顶部到销孔中心距离

    # 工艺参数
    pin_offset: float = 0.5     # 销孔偏心距 mm（偏向推力面）
    top_land_diameter: Optional[float] = None  # 一环岸直径（小于缸径）
    clearance: Optional[float] = None          # 配缸间隙

    # 元数据
    name: str = "活塞"
    material: str = "ZL101"
    application: str = "通用"   # 压缩机/内燃机/液压
    unit: str = "mm"

    def __post_init__(self):
        """自动推导未指定的参数"""
        D = self.cylinder_diameter

        # 总长 = 0.9~1.1 × 缸径
        if self.total_length is None:
            self.total_length = round(D * 1.0, 1)

        # 裙部长 = 0.6~0.75 × 缸径
        if self.skirt_length is None:
            self.skirt_length = round(D * 0.7, 1)

        # 顶部厚度 = 0.08~0.12 × 缸径
        if self.crown_thickness is None:
            self.crown_thickness = round(D * 0.10, 1)

        # 活塞销直径 = 0.25~0.3 × 缸径，圆整到5
        if self.pin_diameter is None:
            raw = D * 0.28
            self.pin_diameter = math.ceil(raw / 2) * 2  # 圆整到偶数

        # 销孔长度
        if self.pin_hole_length is None:
            self.pin_hole_length = D * 0.85

        # 环数（只算气环，油环单独算）
        if self.ring_count is None:
            # 默认按中等压力假设 3 道
            self.ring_count = 3

        # 裙部壁厚
        if self.skirt_wall_thickness is None:
            self.skirt_wall_thickness = max(2.0, round(D * 0.04, 1))

        # 顶部到销孔中心 ≈ 0.35~0.45 × 缸径
        if self.crown_to_pin_center is None:
            self.crown_to_pin_center = round(D * 0.38, 1)

        # 配缸间隙 = 0.001~0.002 × 缸径
        if self.clearance is None:
            self.clearance = round(D * 0.0015, 2)

        # 一环岸直径：比缸径小 0.5~1mm（冷态间隙）
        if self.top_land_diameter is None:
            self.top_land_diameter = round(D - 0.5, 1)

    def get_ring_grooves(self) -> List[RingGroove]:
        """根据环数生成环槽列表"""
        grooves = []
        D = self.cylinder_diameter

        # 环槽宽度和深度（按缸径范围取标准值）
        if D <= 50:
            groove_w, groove_d = 2.0, 2.5
        elif D <= 80:
            groove_w, groove_d = 2.5, 3.0
        elif D <= 120:
            groove_w, groove_d = 3.0, 3.5
        else:
            groove_w, groove_d = 4.0, 4.0

        # 一环岸高度
        top_land = D * 0.10

        for i in range(self.ring_count):
            distance = top_land + i * (groove_w + groove_w * 0.5)
            grooves.append(RingGroove(
                width=groove_w,
                depth=groove_d,
                distance_from_top=round(distance, 1),
                type="compression"
            ))

        # 油环槽（在最下方）
        last_groove = grooves[-1]
        oil_distance = last_groove.distance_from_top + groove_w + groove_w * 1.5
        grooves.append(RingGroove(
            width=groove_w * 0.8,
            depth=groove_d * 1.1,
            distance_from_top=round(oil_distance, 1),
            type="oil"
        ))

        return grooves

    def summary(self) -> str:
        """生成参数摘要表"""
        D = self.cylinder_diameter
        grooves = self.get_ring_grooves()
        total_rings = len(grooves)

        lines = [
            "┌───────────────────────────────────────────┐",
            f"│ [Piston] {self.name:<29}│",
            f"│ 应用：{self.application:<34}│",
            f"│ 材料：{self.material:<34}│",
            "├───────────────────────────────────────────┤",
            f"│ 缸径 D = {D} mm{' ' * (24-len(str(D)))}│",
            f"│ 总长 L = {self.total_length} mm{' ' * (22-len(str(self.total_length)))}│",
            f"│ 裙部长 = {self.skirt_length} mm{' ' * (22-len(str(self.skirt_length)))}│",
            f"│ 顶部厚 = {self.crown_thickness} mm{' ' * (22-len(str(self.crown_thickness)))}│",
            f"│ 销直径 = {self.pin_diameter} mm{' ' * (22-len(str(self.pin_diameter)))}│",
            f"│ 销偏心 = {self.pin_offset} mm (向推力面){' ' * (13-len(str(self.pin_offset)))}│",
            f"│ 环数 = {total_rings} (气环{self.ring_count}+油环{self.oil_ring_count}){' ' * (15-len(str(total_rings)))}│",
            f"│ 配缸间隙 = {self.clearance} mm{' ' * (20-len(str(self.clearance)))}│",
            "├───────────────────────────────────────────┤",
            "│ 环槽明细：                                │",
        ]
        for i, g in enumerate(grooves, 1):
            mark = "[C]" if g.type == "compression" else "[O]"
            lines.append(f"│  {mark} 环{i}: {g.width}x{g.depth}mm, 距顶{g.distance_from_top}mm{' ' * (15-len(str(g.distance_from_top)))}│")
        lines.append("└───────────────────────────────────────────┘")
        return "\n".join(lines)

    def validate(self) -> List[str]:
        """验证设计合理性"""
        warnings = []
        D = self.cylinder_diameter

        # 裙长检查
        ratio = self.skirt_length / D
        if ratio < 0.5:
            warnings.append(f"⚠️ 裙长比={ratio:.2f} < 0.5，导向性可能不足")
        elif ratio > 0.8:
            warnings.append(f"⚠️ 裙长比={ratio:.2f} > 0.8，摩擦损失较大")

        # 销径检查
        pin_ratio = self.pin_diameter / D
        if pin_ratio < 0.2:
            warnings.append(f"⚠️ 销径比={pin_ratio:.2f} < 0.2，销强度可能不足")
        elif pin_ratio > 0.35:
            warnings.append(f"⚠️ 销径比={pin_ratio:.2f} > 0.35，销过重")

        # 壁厚检查
        if self.skirt_wall_thickness < 1.5:
            warnings.append(f"⚠️ 裙部壁厚 {self.skirt_wall_thickness}mm < 1.5mm，铸造困难")

        # 总长检查
        if self.total_length > 2 * D:
            warnings.append(f"⚠️ 总长/缸径比={self.total_length/D:.2f} > 2，活塞过长")

        return warnings


# ============================================
# 参数化生成器
# ============================================

class PistonBuilder:
    """从参数生成活塞的 JSON 描述"""

    @staticmethod
    def build_json(params: PistonParams) -> dict:
        """
        将 PistonParams 转换为 JSON 零件描述。

        几何策略：
        - 以活塞顶部中心为原点
        - 活塞轴线沿 Z 轴（Z+ 向下指向裙部）
        - 主体通过旋转特征生成
        - 环槽通过多个切除特征
        - 销孔通过拉伸切除
        """
        D = params.cylinder_diameter
        features = []

        # ========== 特征1：活塞主体（旋转） ==========
        # 截面轮廓：从中心线出发，描述外轮廓
        profile = []

        # 顶部
        r_top = D / 2 - params.clearance  # 缸径配合面
        profile.append({"z": 0, "r": 0})  # 中心起点
        profile.append({"z": 0, "r": r_top})

        # 顶部厚度
        z = params.crown_thickness
        profile.append({"z": z, "r": r_top})

        # 一环岸（略小直径）
        z += 2  # 岸过渡
        profile.append({"z": z, "r": params.top_land_diameter / 2})

        # 环槽区
        grooves = params.get_ring_grooves()
        for g in grooves:
            # 到槽上沿
            profile.append({"z": g.distance_from_top, "r": params.top_land_diameter / 2})
            # 槽底
            groove_bottom_r = (D / 2) - g.depth
            profile.append({"z": g.distance_from_top, "r": groove_bottom_r})
            # 槽下沿
            z_groove_bottom = g.distance_from_top + g.width
            profile.append({"z": z_groove_bottom, "r": groove_bottom_r})
            profile.append({"z": z_groove_bottom, "r": r_top})

        # 裙部
        z_skirt_start = grooves[-1].distance_from_top + grooves[-1].width + 3
        profile.append({"z": z_skirt_start, "r": r_top})
        z_end = z_skirt_start + params.skirt_length
        profile.append({"z": z_end, "r": r_top - 0.02})  # 微量内收

        # 裙部底端
        profile.append({"z": z_end, "r": 0})  # 回到中心

        features.append({
            "type": "revolve",
            "name": "活塞主体",
            "angle": 360,
            "axis": "Z",
            "profile": profile,
        })

        # ========== 特征2：内腔（旋转切除） ==========
        inner_r = (D / 2) - params.skirt_wall_thickness
        inner_top_z = params.crown_thickness
        inner_bottom_z = z_end - 5  # 裙底留5mm壁
        features.append({
            "type": "revolve_cut",
            "name": "活塞内腔",
            "profile": [
                {"z": inner_top_z, "r": 0},
                {"z": inner_top_z, "r": inner_r},
                {"z": inner_bottom_z, "r": inner_r},
                {"z": inner_bottom_z, "r": 0},
            ],
            "angle": 360,
            "axis": "Z",
        })

        # ========== 特征3：活塞销孔（拉伸切除） ==========
        pin_z = params.crown_to_pin_center
        pin_r = params.pin_diameter / 2
        features.append({
            "type": "cut_extrude",
            "name": f"活塞销孔 Φ{params.pin_diameter}",
            "sketch_plane": "right_plane",
            "sketch": {
                "type": "circle",
                "center_x": pin_z,
                "center_y": params.pin_offset,  # 偏心
                "radius": pin_r,
            },
            "depth": D,  # 贯穿整个活塞
            "direction": "both_sides",
        })

        # ========== 特征4：销孔卡环槽 ==========
        for side in [-1, 1]:
            features.append({
                "type": "revolve_cut",
                "name": f"销孔卡环槽 (侧{1 if side>0 else 2})",
                "position_z": pin_z + side * (params.pin_hole_length / 2 - 2),
                "groove_width": 1.2,
                "groove_depth": 1.0,
                "diameter_at_groove": params.pin_diameter,
            })

        # ========== 特征5：底部倒角和圆角 ==========
        features.append({
            "type": "chamfer",
            "name": "顶部倒角 C0.5",
            "edges": ["top_outer_edge"],
            "distance": 0.5,
            "angle": 45,
        })
        features.append({
            "type": "fillet",
            "name": "环槽根部圆角 R0.3",
            "edges": ["groove_corners"],
            "radius": 0.3,
        })

        return {
            "name": params.name,
            "version": "1.0",
            "material": params.material,
            "application": params.application,
            "cylinder_diameter": params.cylinder_diameter,
            "total_length": params.total_length,
            "unit": "mm",
            "design_ratios": {
                "skirt_length_ratio": round(params.skirt_length / D, 3),
                "pin_diameter_ratio": round(params.pin_diameter / D, 3),
                "crown_thickness_ratio": round(params.crown_thickness / D, 3),
                "total_length_ratio": round(params.total_length / D, 3),
            },
            "features": features,
            "ring_grooves": [
                {"index": i+1, "width": g.width, "depth": g.depth,
                 "dist_from_top": g.distance_from_top, "type": g.type}
                for i, g in enumerate(grooves)
            ],
            "warnings": params.validate(),
        }


# ============================================
# 工厂函数
# ============================================

def create_compressor_piston(cylinder_diameter: float, pressure_mpa: float = 2.0,
                             material: str = "ZL101") -> PistonParams:
    """
    创建压缩机活塞。

    Args:
        cylinder_diameter: 缸径 mm
        pressure_mpa: 工作压力 MPa（决定环数）
        material: 材料
    """
    # 根据压力决定环数
    if pressure_mpa < 1.0:
        rings = 2
    elif pressure_mpa < 3.0:
        rings = 3
    else:
        rings = 4

    return PistonParams(
        cylinder_diameter=cylinder_diameter,
        ring_count=rings,
        material=material,
        application="往复式压缩机",
        name=f"压缩机活塞 D{cylinder_diameter}"
    )


def create_engine_piston(cylinder_diameter: float, is_turbo: bool = False,
                         material: str = "ZL109") -> PistonParams:
    """
    创建内燃机活塞。

    Args:
        cylinder_diameter: 缸径 mm
        is_turbo: 是否涡轮增压（增加环数和顶部厚度）
        material: 材料（常用 ZL109 共晶铝硅合金）
    """
    rings = 3 if is_turbo else 2
    crown_mult = 1.2 if is_turbo else 1.0

    return PistonParams(
        cylinder_diameter=cylinder_diameter,
        ring_count=rings,
        crown_thickness=round(cylinder_diameter * 0.10 * crown_mult, 1),
        material=material,
        application="内燃机（增压）" if is_turbo else "内燃机",
        name=f"发动机活塞 D{cylinder_diameter}"
    )


# ============================================
# CLI 测试
# ============================================

if __name__ == "__main__":
    # 示例1：压缩机活塞
    print("=" * 55)
    print("示例1：压缩机活塞 (D=80mm, P=2.0MPa)")
    print("=" * 55)
    piston1 = create_compressor_piston(cylinder_diameter=80, pressure_mpa=2.0)
    print(piston1.summary())
    warnings = piston1.validate()
    if warnings:
        for w in warnings:
            print(w)
    else:
        print("[OK] 设计参数通过验证")

    # 生成 JSON
    json1 = PistonBuilder.build_json(piston1)
    print(f"\n[Features] 生成 {len(json1['features'])} 个特征:")
    for f in json1['features']:
        print(f"   - [{f['type']}] {f['name']}")
    print(f"[Design Ratios] {json1['design_ratios']}")

    # 示例2：小活塞
    print("\n" + "=" * 55)
    print("示例2：小型压缩机活塞 (D=40mm)")
    print("=" * 55)
    piston2 = create_compressor_piston(cylinder_diameter=40, pressure_mpa=0.8)
    print(piston2.summary())

    # 示例3：内燃机活塞
    print("\n" + "=" * 55)
    print("示例3：增压发动机活塞 (D=86mm, Turbo)")
    print("=" * 55)
    piston3 = create_engine_piston(cylinder_diameter=86, is_turbo=True)
    print(piston3.summary())
