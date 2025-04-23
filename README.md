# DWG房间骨架线提取工具

这个工具用于从建筑平面图（DWG/DXF格式）中提取房间的骨架线，采用多步骤流程处理方法。

## 主要功能

- 自动识别DWG/DXF文件中的墙体图层和线条
- 预处理图层和实体，清理不相关元素
- 修复断开的线条和多段线
- 自动构建墙体多边形和识别房间
- 使用多种骨架化算法提取房间骨架线
- 优化骨架线拓扑结构和连接关系
- 智能计算房间面积和周长
- 生成房间总览图，使用不同颜色直观显示
- 将结果输出为图像和DXF文件
- 强大的错误处理和日志记录机制

## 安装

1. 确保已安装Python 3.7或更高版本
2. 安装所需依赖项：

```bash
pip install -r requirements.txt
```

3. 安装DWG到DXF的转换工具（至少选择一种）：
   - **ODA File Converter**（推荐）: [下载链接](https://www.opendesign.com/guestfiles/oda_file_converter)
   - **LibreDWG**: 可以通过[官方网站](https://www.gnu.org/software/libredwg/)安装

## 处理流程

1. **预处理DWG文件**:

   - 清理不必要的图层和实体
   - 识别墙体图层
   - 修复断开的线条和多段线
2. **提取墙体和房间**:

   - 收集所有线条和多段线
   - 转换为二值图像
   - 识别闭合区域作为房间
3. **骨架提取**:

   - 使用多种骨架算法（中轴变换、骨架化、细化）
   - 评估最佳骨架
   - 优化骨架拓扑结构
4. **后处理**:

   - 简化骨架线
   - 保持拓扑连接性
   - 标注主要结构元素
5. **可视化和导出**:

   - 生成房间总览图
   - 创建各房间的详细视图
   - 导出DXF格式文件

## 使用方法

### 基本用法

处理data目录中的所有DWG/DXF文件：

```bash
python extract_skeleton.py
```

### 命令行参数

```bash
python extract_skeleton.py [-h] [-d DATA_DIR] [-o OUTPUT_DIR] [-f FILE] [-a AREA] [-s SIZE] [--convert-only] [--oda-path ODA_PATH]
```

参数说明：

- `-h, --help`: 显示帮助信息
- `-d, --data_dir`: 指定DWG/DXF文件所在目录 (默认: data)
- `-o, --output_dir`: 指定输出目录 (默认: output_rooms)
- `-f, --file`: 指定要处理的单个DWG/DXF文件名（位于data_dir中）
- `-a, --area`: 设置识别房间的最小面积阈值 (默认: 1.0)
- `-m, --max-area`: 设置识别房间的最大面积阈值 (默认: 无限制)
- `-s, --size`: 设置处理图像的尺寸 (默认: 2000x2000)
- `--convert-only`: 仅将DWG转换为DXF，不进行骨架提取
- `--oda-path`: 指定ODA File Converter可执行文件的路径

### 示例

1. 处理特定的DWG文件：

```bash
python extract_skeleton.py -f FL808PNZ_A02-总平面图.dwg
```

2. 调整参数处理文件：

```bash
python extract_skeleton.py -f FL808PNZ_A02-总平面图.dwg -a 5.0 -s 3000
```

3. 更改数据目录和输出目录：

```bash
python extract_skeleton.py -d my_dwg_files -o my_results
```

4. 仅转换DWG到DXF：

```bash
python extract_skeleton.py -f FL808PNZ_A02-总平面图.dwg --convert-only
```

5. 指定ODA File Converter路径：

```bash
python extract_skeleton.py -f FL808PNZ_A02-总平面图.dwg --oda-path "D:\Program Files\ODA\ODAFileConverter.exe"
```

## 输出内容

脚本将生成以下输出：

- `preprocessed.dxf`: 预处理后的DXF文件，包含清理后的墙体线条
- `walls_rooms.dxf`: 识别出的墙体和房间
- `rooms_overview.png`: 房间总览图，使用不同颜色区分房间
- `result.dxf`: 最终结果，包含墙体、房间和骨架线
- 对于每个识别的房间：
  - `room_X_original.png`: 房间原始形状图像
  - `room_X_skeleton.png`: 房间骨架线图像
  - `room_X_skeleton.dxf`: 房间骨架线的DXF文件，可以在CAD软件中打开

## 错误处理机制

本工具实现了强大的错误处理机制，确保即使在处理大型或复杂图纸时也能保持稳定：

- **日志系统**：所有操作都会记录详细日志，便于诊断问题
- **失败恢复**：处理单个房间失败不会影响整体流程，系统会继续处理其他房间
- **错误图像生成**：当无法正常生成房间图像时，会创建包含错误信息的提示图像
- **坐标转换保护**：防止无效坐标转换导致程序崩溃
- **输出目录检查**：自动创建不存在的目录，确保输出文件可以正确保存
- **兼容性处理**：适应不同字符集和操作系统环境
- **转换失败处理**：DWG转DXF失败时提供详细的错误信息和建议

## 注意事项

- ezdxf库只能处理DXF文件，而不能直接处理DWG文件
- 脚本会自动尝试将DWG转换为DXF格式，但需要安装相应的转换工具
- 如果自动转换失败，请检查ODA File Converter是否正确安装，或使用 `--oda-path`指定正确路径
- 转换时可能会出现"Command Line Format"错误，这通常表示ODA File Converter的路径或参数不正确
- 对于复杂的建筑图纸，可能需要手动调整墙体识别参数和骨架提取算法
- 使用 `-a`参数调整面积阈值可以过滤掉一些不必要的小图形
- 使用 `-s`参数增大图像尺寸可以提高骨架线的精度，但会增加处理时间
- 对于特别复杂的图纸，可能需要增加系统内存或调整参数
