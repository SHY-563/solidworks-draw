"""
SolidWorks API 封装层
提供简化的 Python 接口操作 SolidWorks。

依赖：pip install pywin32
SolidWorks 版本：2018+ （COM接口兼容）

如果 SolidWorks 未安装，自动降级为 JSON 描述输出模式。
"""

import json
import os
import math
from dataclasses import dataclass, field
from typing import Optional, List, Tuple, Dict, Any
from enum import Enum


# ============================================
# 数据模型
# ============================================

class Unit(Enum):
    MM = "mm"
    INCH = "inch"

class Plane(Enum):
    FRONT = "Front"        # 前视基准面
    TOP = "Top"            # 上视基准面
    RIGHT = "Right"        # 右视基准面

class ExtrusionDirection(Enum):
    BLIND = 0             # 单向
    MID_PLANE = 1         # 两侧对称
    THROUGH_ALL = 2       # 完全贯穿

@dataclass
class Point2D:
    x: float
    y: float

@dataclass
class Point3D:
    x: float
    y: float
    z: float

@dataclass
class Circle:
    center: Point2D
    radius: float

@dataclass
class Rectangle:
    corner1: Point2D
    corner2: Point2D

@dataclass
class Keyway:
    """键槽定义"""
    width: float          # 宽度
    length: float         # 长度
    depth: float          # 深度
    position_z: float     # 轴上轴向位置
    angle: float = 0      # 周向角度 0=顶部

@dataclass
class ShaftSegment:
    """轴段定义"""
    diameter: float
    length: float
    features: List[str] = field(default_factory=list)  # 'keyway', 'thread', 'groove', 'center_hole'
    chamfer_left: float = 0
    chamfer_right: float = 0
    fillet_left: float = 0
    fillet_right: float = 0
    tolerance: str = ""   # e.g. "js6", "k6"

@dataclass
class ShaftParams:
    """完整轴参数"""
    segments: List[ShaftSegment]
    total_length: float
    material: str = "45钢"
    unit: Unit = Unit.MM

@dataclass
class PistonParams:
    """完整活塞参数"""
    cylinder_diameter: float      # 缸径 D
    total_length: float           # 总长
    skirt_length: float           # 裙部长度
    crown_thickness: float        # 顶部厚度
    pin_diameter: float           # 活塞销直径
    pin_offset: float = 0.5       # 销孔偏心
    ring_grooves: int = 3         # 环槽数
    ring_groove_width: float = 2.5
    ring_groove_depth: float = 3.0
    material: str = "ZL101"
    unit: Unit = Unit.MM


# ============================================
# SolidWorks COM 接口
# ============================================

class SWApp:
    """SolidWorks 应用程序接口"""

    def __init__(self, visible: bool = True):
        """
        初始化 SolidWorks 连接。

        Args:
            visible: 是否显示 SolidWorks 窗口
        """
        self._app = None
        self._available = False
        try:
            import win32com.client
            self._app = win32com.client.Dispatch("SldWorks.Application")
            self._app.Visible = visible
            self._available = True
            print("✅ 已连接到 SolidWorks")
        except Exception:
            print("⚠️  SolidWorks 未安装或无法连接，将使用 JSON 输出模式")
            self._available = False

    @property
    def is_available(self) -> bool:
        return self._available

    def new_part(self, template_path: str = "") -> Any:
        """创建新零件文档"""
        if not self._available:
            return None
        if not template_path:
            template_path = self._app.GetDocumentTemplate(1)  # 1=零件模板
        return self._app.NewDocument(template_path, 0, 0, 0)

    def new_sketch(self, plane: Plane = Plane.FRONT) -> Any:
        """在指定基准面上插入草图"""
        if not self._available:
            return None
        part = self._app.ActiveDoc
        part.InsertSketch2(True)
        # 选择基准面
        part.SelectByID2(plane.value, "PLANE", 0, 0, 0, False, 0, None, 0)
        return part

    def sketch_circle(self, x: float, y: float, radius: float):
        """在活动草图中绘制圆"""
        part = self._app.ActiveDoc
        part.CreateCircleByRadius2(x, y, 0, radius)
        return part

    def sketch_rectangle(self, x1: float, y1: float, x2: float, y2: float):
        """在活动草图中绘制矩形"""
        part = self._app.ActiveDoc
        part.CreateRectangle(x1, y1, 0, x2, y2, 0)
        return part

    def sketch_line(self, x1: float, y1: float, x2: float, y2: float):
        """在活动草图中绘制直线"""
        part = self._app.ActiveDoc
        part.CreateLine2(x1, y1, 0, x2, y2, 0)
        return part

    def extrude(self, depth: float, direction: ExtrusionDirection = ExtrusionDirection.BLIND, draft_angle: float = 0):
        """拉伸特征"""
        part = self._app.ActiveDoc
        # 参数：单向/双向, 是否反向, 方向类型, ...
        part.FeatureExtrusion2(
            True,        # 单向
            False,       # 不反向
            False,       # 不拔模
            0,           # 拔模方向
            0,           # 拔模角度
            depth,
            0,           # 方向2深度
            False, False, False, False, 0, 0,
            False, False, False, False,
            True, True, True, 0, 0, False
        )
        return part

    def extrude_cut(self, depth: float):
        """拉伸切除"""
        part = self._app.ActiveDoc
        part.FeatureCut3(
            True, False, False, 0, 0, depth, 0,
            False, False, False, False, 0, 0, False
        )
        return part

    def revolve(self, angle: float = 360):
        """旋转特征"""
        part = self._app.ActiveDoc
        part.FeatureRevolve2(angle / 180 * math.pi, True, False, False, False)
        return part

    def fillet(self, radius: float, edges: List[str] = None):
        """圆角"""
        part = self._app.ActiveDoc
        part.FeatureFillet2(radius, 1)  # 等半径
        return part

    def chamfer(self, distance: float, angle: float = 45):
        """倒角"""
        part = self._app.ActiveDoc
        part.FeatureChamfer2(distance, angle * math.pi / 180, 1)
        return part

    def linear_pattern(self, count: int, spacing: float, direction: str = "X"):
        """线性阵列"""
        part = self._app.ActiveDoc
        part.FeatureLinearPattern2(count, spacing, 1, 1, False)
        return part

    def circular_pattern(self, count: int, total_angle: float = 360):
        """圆周阵列"""
        part = self._app.ActiveDoc
        part.FeatureCircularPattern2(count, total_angle / 180 * math.pi, False, "", False)
        return part

    def save(self, filepath: str):
        """保存零件"""
        if self._available:
            self._app.ActiveDoc.SaveAs(filepath)
            print(f"💾 已保存: {filepath}")

    def close(self):
        """关闭 SolidWorks（不保存）"""
        if self._available:
            self._app.CloseAllDocuments(False)
            print("🔒 SolidWorks 已关闭")


# ============================================
# JSON 描述降级模式
# ============================================

class SWJsonBuilder:
    """
    JSON 模式：不依赖 SolidWorks，生成零件描述 JSON 文件。
    适合无 SolidWorks 环境下的设计验证和参数检查。
    """

    def __init__(self, name: str):
        self.name = name
        self.steps: List[Dict] = []
        self.features: List[Dict] = []
        self.current_sketch = None

    def add_sketch(self, plane: str) -> "SWJsonBuilder":
        self.current_sketch = {"plane": plane, "entities": []}
        self.steps.append({"type": "sketch", "plane": plane})
        return self

    def add_circle(self, x: float, y: float, r: float) -> "SWJsonBuilder":
        self.current_sketch["entities"].append({"type": "circle", "x": x, "y": y, "r": r})
        return self

    def add_rectangle(self, x1: float, y1: float, x2: float, y2: float) -> "SWJsonBuilder":
        self.current_sketch["entities"].append({"type": "rectangle", "x1": x1, "y1": y1, "x2": x2, "y2": y2})
        return self

    def add_extrude(self, depth: float, name: str = "") -> "SWJsonBuilder":
        self.features.append({"type": "extrude", "depth": depth, "name": name or f"Extrude-{len(self.features)+1}"})
        return self

    def add_revolve(self, angle: float = 360, name: str = "") -> "SWJsonBuilder":
        self.features.append({"type": "revolve", "angle": angle, "name": name or f"Revolve-{len(self.features)+1}"})
        return self

    def add_cut(self, depth: float, name: str = "") -> "SWJsonBuilder":
        self.features.append({"type": "cut", "depth": depth, "name": name or f"Cut-{len(self.features)+1}"})
        return self

    def add_fillet(self, radius: float, edges: List[str] = None) -> "SWJsonBuilder":
        self.features.append({"type": "fillet", "radius": radius, "edges": edges or []})
        return self

    def add_chamfer(self, distance: float, angle: float = 45) -> "SWJsonBuilder":
        self.features.append({"type": "chamfer", "distance": distance, "angle": angle})
        return self

    def build(self) -> Dict:
        return {
            "name": self.name,
            "version": "1.0",
            "features": self.features,
            "steps": self.steps,
        }

    def save(self, filepath: str):
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(self.build(), f, ensure_ascii=False, indent=2)
        print(f"📄 零件描述已保存: {filepath}")
        print(f"   包含 {len(self.features)} 个特征，{len(self.steps)} 个步骤")
        return filepath


# ============================================
# 辅助函数
# ============================================

def mm_to_m(val_mm: float) -> float:
    """毫米转米（SolidWorks API 默认单位）"""
    return val_mm / 1000.0

def deg_to_rad(deg: float) -> float:
    """角度转弧度"""
    return deg * math.pi / 180.0

def recommend_keyway_width(shaft_diameter: float) -> Optional[int]:
    """根据轴径推荐标准平键宽度 (GB/T 1096)"""
    ranges = [
        (17, 22, 6), (22, 30, 8), (30, 38, 10),
        (38, 44, 12), (44, 50, 14), (50, 58, 16),
        (58, 65, 18), (65, 75, 20), (75, 85, 22),
    ]
    for lo, hi, w in ranges:
        if lo <= shaft_diameter < hi:
            return w
    return None

def recommend_chamfer(diameter: float) -> float:
    """根据轴径推荐倒角大小"""
    if diameter < 30:
        return 1.0
    elif diameter < 50:
        return 1.0
    elif diameter < 80:
        return 1.5
    else:
        return 2.0

# ============================================
# 顶层 API：供 Skill 调用
# ============================================

def create_part_from_json(name: str, description: Dict, output_dir: str = ".") -> str:
    """
    从 JSON 描述生成 SolidWorks 零件。

    优先使用 SolidWorks COM API，降级时输出 JSON 文件。

    Args:
        name: 零件名称
        description: 零件描述字典
        output_dir: 输出目录

    Returns:
        生成的文件路径
    """
    sw = SWApp()
    filepath = os.path.join(output_dir, f"{name}.json")

    if sw.is_available:
        # TODO: 从 description 解析并调用 SW API
        # 目前先输出 JSON，API 逐步完善
        builder = SWJsonBuilder(name)
        # ... 解析 description 构建特征
        filepath = os.path.join(output_dir, f"{name}.json")
        builder.save(filepath)
    else:
        builder = SWJsonBuilder(name)
        filepath = os.path.join(output_dir, f"{name}.json")
        builder.save(filepath)

    return filepath


if __name__ == "__main__":
    # 测试：创建一个简单轴
    builder = SWJsonBuilder("test_shaft")
    builder.add_sketch("Front")
    builder.add_circle(0, 0, 15)  # 直径30
    builder.add_extrude(50, "第一段")
    builder.add_chamfer(1, 45)
    builder.save("./test_shaft.json")

    # 检查 SolidWorks
    sw = SWApp(visible=False)
    print(f"SolidWorks 状态: {'可用' if sw.is_available else '不可用（JSON模式）'}")
