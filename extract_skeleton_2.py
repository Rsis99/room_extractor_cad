#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版 CAD 前处理与可视化（直接在脚本中指定路径，无需命令行参数或 argparse）：
1. 解析 CAD 文件（DWG/DXF）
2. 查询并识别有效墙体和门
3. 去除门窗、关联墙体，计算闭合多边形
4. 可视化墙体分段与闭合多边形，并保存图片与 WKT

依赖：
  pip install ezdxf shapely matplotlib
"""
import sys
import os
import ezdxf
from shapely.geometry import LineString
from shapely.ops import unary_union, polygonize
import matplotlib.pyplot as plt

# --- 核心函数 ----------------------------------------------------------------
def parse_cad_file(file_path):
    try:
        doc = ezdxf.readfile(file_path)
        print(f"[INFO] 成功解析 CAD 文件: {file_path}")
        return doc
    except Exception as e:
        print(f"[ERROR] 解析 CAD 文件失败: {e}")
        sys.exit(1)

def query_walls_and_doors(doc):
    msp = doc.modelspace()
    walls, doors = [], []
    for ent in msp:
        layer = ent.dxf.layer.lower() if hasattr(ent.dxf, 'layer') else ''
        etype = ent.dxftype()
        if etype in ('LINE', 'LWPOLYLINE', 'POLYLINE'):
            if 'wall' in layer or '墙' in layer:
                walls.append(ent)
            elif 'door' in layer or '门' in layer:
                doors.append(ent)
    print(f"[INFO] 识别到墙体实体: {len(walls)}，门实体: {len(doors)}")
    return walls, doors

def entity_to_lines(ent):
    """
    将 DXF 实体转换为 Shapely LineString
    支持 LINE, LWPOLYLINE, POLYLINE
    """
    et = ent.dxftype()
    if et == 'LINE':
        # ezdxf 的 Vec3 不支持切片，需用下标访问
        start = ent.dxf.start  # Vec3
        end   = ent.dxf.end    # Vec3
        a = (start[0], start[1])
        b = (end[0],   end[1])
        return LineString([a, b])

    elif et == 'LWPOLYLINE':
        pts = [tuple(p[:2]) for p in ent.get_points()]
        return LineString(pts) if len(pts) >= 2 else None

    elif et == 'POLYLINE':
        pts = []
        for v in ent.vertices:
            if hasattr(v.dxf, 'location'):
                loc = v.dxf.location  # Vec3
                pts.append((loc[0], loc[1]))
        return LineString(pts) if len(pts) >= 2 else None

    return None


def remove_doors_from_walls(wall_ents, door_ents):
    wall_lines = [l for l in (entity_to_lines(w) for w in wall_ents) if l]
    door_lines = [l for l in (entity_to_lines(d) for d in door_ents) if l]
    result = []
    for w in wall_lines:
        geom = w
        for d in door_lines:
            if geom.intersects(d):
                geom = geom.difference(d)
                if geom.is_empty:
                    break
        if geom.is_empty:
            continue
        if geom.geom_type == 'LineString':
            result.append(geom)
        else:
            result.extend(list(geom.geoms))
    print(f"[INFO] 去除门窗后墙体分段: {len(result)}")
    return result

def associate_walls(wall_lines):
    unioned = unary_union(wall_lines)
    polys = list(polygonize(unioned))
    print(f"[INFO] 生成闭合多边形: {len(polys)} 个")
    return polys, unioned

def visualize(wall_lines, polygons, output_path):
    fig, ax = plt.subplots(figsize=(10, 10))
    for seg in wall_lines:
        x, y = seg.xy
        ax.plot(x, y, linewidth=1)
    for poly in polygons:
        x, y = poly.exterior.xy
        ax.plot(x, y, linewidth=2)
    ax.set_aspect('equal')
    ax.axis('off')
    plt.tight_layout()
    fig.savefig(output_path, dpi=300)
    print(f"[INFO] 可视化图像已保存到: {output_path}")

# --- 主流程 ------------------------------------------------------------------
if __name__ == '__main__':
    # 直接在此处指定输入和输出路径，无需通过命令行
    input_path = r'E:\03-pkusz\03-杂项\09-dwg\data\3二层平面布置图-总规0613.dxf'
    output_dir = r'E:\03-pkusz\03-杂项\09-dwg\output_绿房子'     # 输出目录
    output_wkt = os.path.join(output_dir, 'polygons.txt')        # WKT 列表输出
    output_img = os.path.join(output_dir, 'output.png')          # 可视化图像输出

    if not os.path.isfile(input_path):
        print(f"[ERROR] 找不到文件: {input_path}")
        sys.exit(1)
        
    # 确保输出目录存在
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
        print(f"[INFO] 创建输出目录: {output_dir}")

    # 执行前处理
    doc = parse_cad_file(input_path)
    walls, doors = query_walls_and_doors(doc)
    clean_walls = remove_doors_from_walls(walls, doors)
    polys, _ = associate_walls(clean_walls)

    # 保存 WKT
    with open(output_wkt, 'w', encoding='utf-8') as f:
        for i, p in enumerate(polys, 1):
            f.write(f"Polygon {i}: {p.wkt}\n")
    print(f"[INFO] WKT 已保存到: {output_wkt}")

    # 可视化并保存图像
    visualize(clean_walls, polys, output_img)
