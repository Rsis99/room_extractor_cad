#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
简化版 CAD 房间识别：仅完成前三步：
1. 解析 CAD 文件（DWG/DXF）
2. 查询并识别有效墙体和门
3. 去除门窗、关联墙体，计算闭合多边形
后续房间验证与识别步骤已移除。

依赖：
  pip install ezdxf shapely
"""
import sys
import os
import ezdxf
from shapely.geometry import LineString, MultiLineString
from shapely.ops import unary_union, polygonize
import argparse

def parse_cad_file(file_path):
    """
    解析 DXF 文件（若是 DWG，请先转换为 DXF）
    """
    try:
        doc = ezdxf.readfile(file_path)
        print(f"[INFO] 成功解析 CAD 文件: {file_path}")
        return doc
    except Exception as e:
        print(f"[ERROR] 解析 CAD 文件失败: {e}")
        sys.exit(1)


def query_walls_and_doors(doc):
    """
    遍历 modelspace，按图层名称识别墙体与门实体
    墙体关键词: 'wall', '墙'; 门关键词: 'door', '门'
    返回: (walls, doors) 两个实体列表
    """
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
        a = ent.dxf.start[:2]
        b = ent.dxf.end[:2]
        return LineString([a, b])
    elif et == 'LWPOLYLINE':
        pts = [tuple(p[:2]) for p in ent.get_points()]
        if len(pts) >= 2:
            return LineString(pts)
    elif et == 'POLYLINE':
        pts = []
        for v in ent.vertices:
            if hasattr(v.dxf, 'location'):
                pts.append(tuple(v.dxf.location[:2]))
        if len(pts) >= 2:
            return LineString(pts)
    return None


def remove_doors_from_walls(wall_ents, door_ents):
    """
    用门几何分割墙体：对每段墙体 LineString 执行差集
    返回: list(LineString)
    """
    # 转实体
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
        # 收集剩余线段
        if geom.is_empty:
            continue
        if geom.geom_type == 'LineString':
            result.append(geom)
        elif geom.geom_type == 'MultiLineString':
            result.extend(list(geom.geoms))
    print(f"[INFO] 去除门窗后墙体分段: {len(result)}")
    return result


def associate_walls(wall_lines):
    """
    合并所有墙体线段并 polygonize，提取闭合多边形
    返回: (polygons, union_lines)
    """
    unioned = unary_union(wall_lines)
    polys = list(polygonize(unioned))
    print(f"[INFO] 生成闭合多边形: {len(polys)} 个")
    return polys, unioned


def main():
    parser = argparse.ArgumentParser(description='CAD前处理：墙体+门->闭合多边形')
    parser.add_argument('input', help='输入DXF文件路径')
    parser.add_argument('--output', '-o', help='可选：保存多边形WKT列表到文本文件')
    args = parser.parse_args()

    if not os.path.isfile(args.input):
        print(f"[ERROR] 找不到文件: {args.input}")
        sys.exit(1)

    doc = parse_cad_file(args.input)
    walls, doors = query_walls_and_doors(doc)
    clean_walls = remove_doors_from_walls(walls, doors)
    polys, _ = associate_walls(clean_walls)

    # 输出结果
    if args.output:
        with open(args.output, 'w', encoding='utf-8') as f:
            for i, p in enumerate(polys, 1):
                f.write(f"Polygon {i}: {p.wkt}\n")
        print(f"[INFO] 闭合多边形WKT已保存到: {args.output}")
    else:
        for i, p in enumerate(polys, 1):
            print(f"Polygon {i}: {p.wkt}")

if __name__ == '__main__':
    main()
