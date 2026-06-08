# 已学习零件库

这个目录存放从 SolidWorks 文件中提取的结构化设计知识。

## 使用方式

### 1. 从 SolidWorks 文件提取知识

```bash
# 提取单个文件
python utils/sw_extractor.py -i "D:/CAD/engine_piston.sldprt" -o knowledge/learned_parts/

# 批量提取整个目录
python utils/sw_extractor.py -i "D:/CAD/project1/" -o knowledge/learned_parts/ --batch
```

### 2. 搜索相似零件

```bash
python utils/similarity.py --type shaft --dims diameter=30 length=200
```

### 3. 在 Skill 中使用

当需要画新零件时，Skill 会自动：
1. 搜索此目录中相似的已有零件
2. 参考已有零件的尺寸、材料、结构
3. 让新设计保持一致性

## 文件格式

每个 .json 文件代表一个零件，包含：
- 文件名、材料、自定义属性
- 包围盒和物理属性（质量、体积）
- 特征树（特征类型、参数）
- 推断的设计参数

## 索引文件

`_index.json` 是所有零件的快速索引，用于加速搜索。
