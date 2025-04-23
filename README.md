# CAD-Room-Extractor

从CAD文件（DWG/DXF格式）中提取房间和闭合多边形的工具集。本项目提供了多个实现版本，从简单到复杂，适合不同需求场景。

## 功能特点

- 自动识别CAD图纸中的墙体和门窗图层
- 提取墙体线条并去除门窗影响
- 关联墙体线段生成闭合多边形（房间）
- 支持房间骨架提取（在完整版本中）
- 提供多种实现版本，从简单到复杂
- 结果可视化与导出功能

## 安装依赖

```bash
pip install -r requirements.txt
```

主要依赖:
- ezdxf：用于解析和处理DXF文件
- shapely：用于几何操作
- matplotlib：用于数据可视化
- opencv-python：用于图像处理（完整版本需要）
- scikit-image：用于骨架化算法（完整版本需要）
- networkx：用于图形分析（完整版本需要）

## 项目版本

本项目提供了多个实现版本，从简单到复杂：

### 1. 简易版 (extract_skeleton_1.py)

只完成基础的墙体提取和多边形生成步骤，命令行驱动：
- 解析CAD文件（DWG/DXF）
- 查询并识别墙体和门
- 去除门窗、关联墙体，计算闭合多边形

```bash
python extract_skeleton_1.py 输入文件.dxf [--output 输出文件.txt]
```

### 2. 可视化版 (extract_skeleton_2.py)

在简易版基础上增加了可视化功能：
- 解析CAD文件并提取多边形
- 直观可视化墙体分段和闭合多边形
- 保存处理结果为图像和WKT文本

使用前需在脚本中直接修改输入和输出路径：

```bash
python extract_skeleton_2.py
```

### 3. 完整版 (extract_skeleton.py)

全功能版本，支持完整的房间提取、骨架生成和分析流程：
- 自动处理DWG/DXF文件（支持批量）
- 智能识别墙体和房间
- 生成房间骨架线
- 输出多种可视化结果和DXF文件

```bash
python extract_skeleton.py [-h] [-d DATA_DIR] [-o OUTPUT_DIR] [-f FILE] [-a AREA] [-m MAX_AREA] [-s SIZE] [--convert-only] [--oda-path ODA_PATH]
```

参数说明：
- `-h, --help`: 显示帮助信息
- `-d, --data_dir`: 指定DWG/DXF文件所在目录 (默认: data)
- `-o, --output_dir`: 指定输出目录 (默认: output_rooms)
- `-f, --file`: 指定要处理的单个DWG/DXF文件名（位于data_dir中）
- `-a, --area`: 设置识别房间的最小面积阈值 (默认: 1.0)
- `-m, --max-area`: 设置识别房间的最大面积阈值 (默认: 无限制)
- `-s, --size`: 设置处理图像的尺寸 (默认: 2000)
- `--convert-only`: 仅将DWG转换为DXF，不进行骨架提取
- `--oda-path`: 指定ODA File Converter可执行文件的路径

## 使用示例

### 简易版处理单个DXF文件：

```bash
python extract_skeleton_1.py data/FL809X6V_A09-地下车库.dxf --output results.txt
```

### 使用完整版处理文件：

```bash
# 处理特定DWG文件
python extract_skeleton.py -f FL809X6V_A09-地下车库.dwg

# 调整参数处理文件
python extract_skeleton.py -f FL809X6V_A09-地下车库.dwg -a 5.0 -s 3000

# 处理data目录下所有文件并输出到指定目录
python extract_skeleton.py -d data -o results
```

## 输出内容

根据所使用版本的不同，输出内容会有所不同：

### 简易版 (extract_skeleton_1.py)
- 输出多边形的WKT格式列表

### 可视化版 (extract_skeleton_2.py)
- 墙体和多边形的可视化图像
- 多边形WKT文本文件

### 完整版 (extract_skeleton.py)
- `preprocessed.dxf`: 预处理后的DXF文件
- `walls_rooms.dxf`: 识别出的墙体和房间
- `rooms_overview.png`: 房间总览图
- `result.dxf`: 最终结果，包含墙体、房间和骨架线
- 对于每个识别的房间：
  - `room_X_original.png`: 房间原始形状图像
  - `room_X_skeleton.png`: 房间骨架线图像
  - `room_X_skeleton.dxf`: 房间骨架线的DXF文件

## 注意事项

- 处理DWG文件时需要先转换为DXF（完整版能自动处理）
- 对于复杂图纸，可能需要调整参数以获得更好的结果
- 包含大量实体的图纸处理时间可能较长
- 输出目录会自动创建（如不存在）
- 处理日志保存在log目录下
