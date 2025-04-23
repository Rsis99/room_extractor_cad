#!/usr/bin/env python
# -*- coding: utf-8 -*-

import os
import ezdxf
import numpy as np
from skimage.morphology import skeletonize, medial_axis, thin
from skimage import measure, filters, morphology
import matplotlib.pyplot as plt
import matplotlib.font_manager as fm
from matplotlib import rcParams
import cv2
import argparse
import subprocess
import tempfile
import shutil
import sys
import gc
import math
import networkx as nx
import traceback
import logging
import datetime
from pathlib import Path
import ezdxf.transform as transform

# 配置matplotlib支持中文显示
def setup_matplotlib_chinese():
    """配置matplotlib支持中文显示"""
    # 尝试查找系统中的中文字体
    chinese_fonts = []
    # Windows 常见中文字体
    windows_fonts = ['Microsoft YaHei', 'SimHei', 'SimSun', 'FangSong', 'KaiTi', 'STHeiti', 'STXihei', 'STFangsong']
    # Linux/macOS 常见中文字体
    unix_fonts = ['WenQuanYi Micro Hei', 'WenQuanYi Zen Hei', 'Noto Sans CJK SC', 'Noto Sans CJK TC', 'Hiragino Sans GB']
    
    # 合并字体列表
    all_fonts = windows_fonts + unix_fonts
    
    # 检查系统中是否有这些字体
    for font_name in all_fonts:
        font_path = None
        try:
            font_path = fm.findfont(fm.FontProperties(family=font_name))
            if font_path and "ttf" in font_path.lower() and not font_path.endswith('DejaVuSans.ttf'):
                chinese_fonts.append(font_name)
                break
        except:
            continue
    
    # 如果找到了中文字体，设置为matplotlib默认字体
    if chinese_fonts:
        plt.rcParams['font.family'] = chinese_fonts[0]
    else:
        # 尝试使用系统默认字体
        try:
            # 获取所有字体
            font_list = fm.findSystemFonts(fontpaths=None, fontext='ttf')
            
            # 寻找可能的中文字体
            for font_path in font_list:
                try:
                    font = fm.FontProperties(fname=font_path)
                    font_name = font.get_name()
                    if any(name in font_path.lower() for name in ['hei', 'yuan', 'song', 'gothic', 'ming', 'black', 'bold']):
                        plt.rcParams['font.family'] = 'sans-serif'
                        plt.rcParams['font.sans-serif'] = [font_name] + plt.rcParams['font.sans-serif']
                        break
                except:
                    continue
        except:
            log_print("警告: 未找到合适的中文字体，图像中的中文可能显示为方块", 'warning')
    
    # 解决负号显示问题
    plt.rcParams['axes.unicode_minus'] = False

# 全局变量，用于存储ODA File Converter的路径
ODA_PATH = r"D:\01-program\ODAFileConverter\ODAFileConverter.exe"
# 全局日志记录器
logger = None

def setup_logging(log_dir=None):
    """
    设置日志记录系统
    
    参数:
        log_dir: 日志文件保存目录，如果为None则使用当前工作目录下的log文件夹
    
    返回:
        配置好的logger对象
    """
    global logger
    
    # 如果已经设置过日志系统，直接返回
    if logger is not None:
        return logger
    
    # 默认使用当前工作目录下的log文件夹
    if log_dir is None:
        log_dir = os.path.join(os.getcwd(), 'log')
    
    # 确保日志目录存在
    Path(log_dir).mkdir(parents=True, exist_ok=True)
    
    # 创建一个新的日志文件，使用当前时间命名
    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = os.path.join(log_dir, f"process_{timestamp}.log")
    
    # 配置日志记录器
    logger = logging.getLogger('extract_skeleton')
    logger.setLevel(logging.DEBUG)
    
    # 添加文件处理器，记录到文件
    file_handler = logging.FileHandler(log_file, encoding='utf-8')
    file_handler.setLevel(logging.DEBUG)
    
    # 添加控制台处理器，输出到终端
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    
    # 设置日志格式
    formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(formatter)
    console_handler.setFormatter(formatter)
    
    # 添加处理器到日志记录器
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    
    logger.info(f"日志系统已初始化，日志文件: {log_file}")
    return logger

def log_print(message, level='info'):
    """
    同时向控制台输出消息并记录到日志文件
    
    参数:
        message: 要输出的消息
        level: 日志等级，可以是'debug', 'info', 'warning', 'error', 'critical'
    """
    global logger
    
    # 确保日志系统已初始化
    if logger is None:
        logger = setup_logging()
    
    # 根据等级记录日志
    if level == 'debug':
        logger.debug(message)
    elif level == 'info':
        logger.info(message)
    elif level == 'warning':
        logger.warning(message)
    elif level == 'error':
        logger.error(message)
    elif level == 'critical':
        logger.critical(message)
    else:
        logger.info(message)
    
    # 如果没有控制台处理器（意味着消息不会自动打印到控制台），则打印消息
    console_handler_exists = any(isinstance(handler, logging.StreamHandler) and not isinstance(handler, logging.FileHandler) 
                               for handler in logger.handlers)
    if not console_handler_exists:
        print(message)

def convert_dwg_to_dxf(dwg_file, dxf_file=None):
    """
    将DWG文件转换为DXF文件
    
    参数:
        dwg_file: DWG文件路径
        dxf_file: 输出DXF文件路径，如果为None则自动生成
    
    返回:
        转换后的DXF文件路径，如果转换失败则返回None
    """
    # 如果没有指定输出文件，在当前工作目录创建同名的DXF文件
    if dxf_file is None:
        # 获取当前工作目录和文件名
        base_name = os.path.basename(dwg_file)
        file_name_without_ext = os.path.splitext(base_name)[0]
        dxf_file = os.path.join(os.getcwd(), f"{file_name_without_ext}.dxf")
    
    log_print(f"开始转换DWG文件: {dwg_file} -> {dxf_file}")
    
    # 创建临时目录用于ODA转换过程
    temp_dir = None
    try:
        # 创建临时目录
        temp_dir = tempfile.mkdtemp()
        temp_dxf = os.path.join(temp_dir, os.path.basename(os.path.splitext(dwg_file)[0]) + ".dxf")
        
        # 尝试方法1: 使用ODA File Converter (如果安装)
        global ODA_PATH
        if os.path.exists(ODA_PATH):
            try:
                input_dir = os.path.dirname(os.path.abspath(dwg_file))
                
                # 使用临时目录作为输出目录
                output_dir = temp_dir
                input_file = os.path.basename(dwg_file)
                
                # 正确的ODA转换命令格式
                # 直接构建完整的命令字符串，确保路径正确引用
                cmd_str = f'"{ODA_PATH}" "{input_dir}" "{output_dir}" ACAD2013 DXF 0 0 "*.DWG"'
                
                log_print(f"尝试使用ODA File Converter转换: {cmd_str}")
                
                # 使用shell=True执行命令字符串
                subprocess.run(cmd_str, check=True, shell=True)
                
                # 检查临时文件是否生成
                converted_file = os.path.join(output_dir, os.path.splitext(input_file)[0] + ".dxf")
                if os.path.exists(converted_file):
                    # 将转换后的文件复制到目标位置
                    shutil.copy2(converted_file, dxf_file)
                    log_print(f"转换成功，DXF文件已保存到: {dxf_file}")
                    
                    # 同时保存一份到当前工作目录
                    current_dir_copy = os.path.join(os.getcwd(), os.path.basename(dxf_file))
                    if os.path.abspath(current_dir_copy) != os.path.abspath(dxf_file):
                        shutil.copy2(converted_file, current_dir_copy)
                        log_print(f"同时在当前工作目录保存了一份: {current_dir_copy}")
                    
                    return dxf_file
                
            except Exception as e:
                log_print(f"使用ODA File Converter转换失败: {e}", 'error')
                
                # 提供更多调试信息
                log_print("\n尝试手动运行以下命令:", 'warning')
                log_print(f'"{ODA_PATH}" "{input_dir}" "{output_dir}" ACAD2013 DXF 0 0 "*.DWG"', 'warning')
        else:
            log_print(f"ODA File Converter未找到于: {ODA_PATH}", 'warning')
            log_print("请通过--oda-path参数指定正确的路径", 'warning')
        
        # 尝试方法2: 使用LibreDWG (如果安装)
        try:
            cmd = ["dwg2dxf", dwg_file, "-o", dxf_file]
            log_print(f"尝试使用LibreDWG转换: {' '.join(cmd)}")
            subprocess.run(cmd, check=True)
            if os.path.exists(dxf_file):
                log_print(f"转换成功，DXF文件已保存到: {dxf_file}")
                
                # 同时保存一份到当前工作目录
                current_dir_copy = os.path.join(os.getcwd(), os.path.basename(dxf_file))
                if os.path.abspath(current_dir_copy) != os.path.abspath(dxf_file):
                    shutil.copy2(dxf_file, current_dir_copy)
                    log_print(f"同时在当前工作目录保存了一份: {current_dir_copy}")
                    
                return dxf_file
        except Exception as e:
            log_print(f"使用LibreDWG转换失败: {e}", 'error')
        
        # 如果以上方法都失败，提示用户手动转换
        log_print("\n无法自动转换DWG文件到DXF格式。请考虑以下选项:", 'warning')
        log_print("1. 安装ODA File Converter: https://www.opendesign.com/guestfiles/oda_file_converter", 'warning')
        log_print("   并确保可以手动运行ODA File Converter", 'warning')
        log_print("2. 使用AutoCAD或其他CAD软件手动将DWG转换为DXF格式\n", 'warning')
        
        # 建议用户手动运行ODA命令
        input_dir = os.path.dirname(os.path.abspath(dwg_file))
        output_dir = os.path.dirname(os.path.abspath(dxf_file))
        log_print("手动转换命令:", 'info')
        log_print(f'打开命令提示符，输入: "{ODA_PATH}" "{input_dir}" "{output_dir}" ACAD2013 DXF 0 0 "*.DWG"\n', 'info')
        
        return None
    
    finally:
        # 清理所有临时文件和目录
        try:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
                log_print(f"已清理临时目录: {temp_dir}")
        except Exception as e:
            log_print(f"清理临时文件时出错: {e}", 'error')

def generate_original_preview(dxf_file, output_file, img_size=3000):
    """
    为原始DXF文件生成预览图
    
    参数:
        dxf_file: DXF文件路径
        output_file: 预览图输出路径
        img_size: 预览图尺寸
    
    返回:
        extents: 图纸范围 [xmin, ymin, xmax, ymax]
    """
    
    try:
        # 读取DXF文件
        original_doc = ezdxf.readfile(dxf_file)
        
        # 获取绘图范围
        extents = get_drawing_extents(original_doc.modelspace())
        if not extents:
            extents = (0, 0, 1000, 1000)
            log_print("警告: 无法获取绘图范围，使用默认范围")
        
        # 提取所有实体线条
        all_entities = []
        for entity in original_doc.modelspace():
            try:
                if entity.dxftype() == 'LINE':
                    start = (entity.dxf.start.x, entity.dxf.start.y)
                    end = (entity.dxf.end.x, entity.dxf.end.y)
                    all_entities.append([(start, end)])
                elif entity.dxftype() == 'LWPOLYLINE':
                    points = [(point[0], point[1]) for point in entity.get_points()]
                    if len(points) >= 2:
                        segments = []
                        for i in range(len(points) - 1):
                            segments.append((points[i], points[i+1]))
                        if entity.is_closed and len(points) > 2:
                            segments.append((points[-1], points[0]))
                        all_entities.append(segments)
                elif entity.dxftype() in ('ARC', 'CIRCLE', 'ELLIPSE', 'SPLINE'):
                    # 这些实体类型通常使用更复杂的绘制方法，但为简单起见，我们至少标记它们的位置
                    if hasattr(entity.dxf, 'center'):
                        center = (entity.dxf.center.x, entity.dxf.center.y)
                        radius = getattr(entity.dxf, 'radius', 2)  # 默认半径
                        # 添加一个小十字表示中心点
                        size = radius / 2
                        all_entities.append([((center[0]-size, center[1]), (center[0]+size, center[1]))])
                        all_entities.append([((center[0], center[1]-size), (center[0], center[1]+size))])
            except Exception as e:
                log_print(f"提取实体时出错: {e}", 'debug')
        
        # 创建预览图像
        preview_img = create_preview_image(all_entities, extents, output_file, img_size)
        
        if preview_img is not None:
            log_print(f"原始DXF文件预览图已保存到: {output_file}")
            
        return extents
    except Exception as e:
        log_print(f"生成原始预览图像时出错: {e}", 'error')
        return None

def extract_rooms_from_dwg(input_file, output_dir=None, img_size=1024, min_room_area=1.0, max_room_area=None):
    """
    从DWG文件中提取房间轮廓
    
    参数:
        input_file: 输入的DWG文件路径
        output_dir: 输出目录，默认与input_file同目录
        img_size: 图像大小
        min_room_area: 最小房间面积，占图纸总面积的百分比(%)
        max_room_area: 最大房间面积，占图纸总面积的百分比(%)，如果为None则默认为60%
    
    返回:
        rooms: 房间多边形列表
        extents: 范围 [xmin, ymin, xmax, ymax]
    """
    # log_print(f"处理文件: {input_file}")
    
    # 创建输出目录
    if output_dir is None:
        output_dir = os.path.dirname(input_file)
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    # 检查文件类型
    is_dwg = input_file.lower().endswith('.dwg')
    
    # 如果是DWG文件，先转换为DXF
    dxf_file = None
    temp_files_to_clean = []
    try:
        if is_dwg:
            log_print("检测到DWG文件，尝试转换为DXF格式...")
            # 在当前工作目录创建DXF文件
            base_name = os.path.basename(input_file)
            file_name_without_ext = os.path.splitext(base_name)[0]
            dxf_file = os.path.join(os.getcwd(), f"{file_name_without_ext}.dxf")
            
            # 转换DWG到DXF
            converted_dxf = convert_dwg_to_dxf(input_file, dxf_file)
            if converted_dxf is None:
                log_print("无法转换DWG文件，退出处理", 'error')
                return [], None
            
            input_file_to_process = converted_dxf
        else:
            input_file_to_process = input_file
        
        # 0. 输出原始DXF文件的预览图 - 使用独立函数
        original_preview_file = os.path.join(output_dir, "original_preview.png")
        generate_original_preview(input_file_to_process, original_preview_file, img_size=3000)
        
        # 1. 预处理DXF文件
        preprocessed_file = os.path.join(output_dir, "preprocessed.dxf")
        try:
            preprocessed_doc = preprocess_dwg(input_file_to_process, preprocessed_file)
            if preprocessed_doc is None:
                log_print("预处理DXF文件失败，尝试直接处理原始文件")
                preprocessed_doc = ezdxf.readfile(input_file_to_process)
        except Exception as e:
            log_print(f"预处理时出错: {e}，尝试直接处理原始文件")
            preprocessed_doc = ezdxf.readfile(input_file_to_process)
        
        # 2. 提取墙体和房间
        walls, rooms, extents_from_walls = extract_walls_and_rooms(preprocessed_doc, min_room_area, img_size)
        
        # 获取图纸范围 (优先使用这个)
        extents_from_drawing = get_drawing_extents(preprocessed_doc.modelspace())
        
        # 确定最终使用的extents
        if extents_from_drawing:
            final_extents = extents_from_drawing
            log_print("使用从图纸实体计算的范围")
        elif extents_from_walls:
            final_extents = extents_from_walls
            log_print("使用从墙体计算的范围")
        else:
            log_print("警告: 无法确定图纸范围，使用默认范围")
            final_extents = (0, 0, 1000, 1000)
        
        # 3. 保存房间轮廓到DXF文件
        rooms_output_file = os.path.join(output_dir, "rooms.dxf")
        save_rooms_to_dxf(rooms, rooms_output_file)
        
        # 4. 生成房间总览图
        overview_file = os.path.join(output_dir, "rooms_overview.png")
        create_rooms_overview(walls, rooms, final_extents, overview_file, img_size=3000)
        
        # 5. 保存每个房间的单独图像
        log_print(f"保存 {len(rooms)} 个识别出的房间图像和DXF...")
        for i, room in enumerate(rooms):
            try:
                # 创建输出文件名
                output_file = os.path.join(output_dir, f"room_{i+1}")
                
                # 保存房间图像 (use final_extents)
                room_img = room_to_image(room, final_extents, img_size, img_size)
                
                # 使用辅助函数保存房间图像
                plt.figure(figsize=(10, 10))
                plt.imshow(room_img, cmap='gray')
                plt.title(f"Room {i+1}")
                save_image(room_img, f"{output_file}.png", title=f"房间 {i+1}")
                plt.close()
                
                # 将房间轮廓保存为单独的DXF
                save_room_to_dxf(room, f"{output_file}.dxf")
                
                log_print(f"房间 {i+1} 处理完成")
            
            except Exception as e:
                log_print(f"处理房间 {i+1} 时出错: {e}")
                continue
        
        log_print(f"处理完成，已识别 {len(rooms)} 个房间，结果保存在 {output_dir}")
        
        # Return rooms and the final extents used
        return rooms, final_extents
        
    finally:
        # 清理matplotlib缓存
        plt.close('all')
        
        # 释放内存
        gc.collect()

def get_drawing_extents(modelspace):
    """获取图纸的边界范围"""
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    
    entity_count = 0
    
    for entity in modelspace:
        if hasattr(entity, 'get_points'):
            try:
                points = entity.get_points()
                for point in points:
                    min_x = min(min_x, point[0])
                    min_y = min(min_y, point[1])
                    max_x = max(max_x, point[0])
                    max_y = max(max_y, point[1])
                    entity_count += 1
            except Exception as e:
                log_print(f"警告: 处理实体点时出错: {e}", 'debug')  # 改为debug级别
        # 特别处理Circle实体
        elif entity.dxftype() == 'CIRCLE' and hasattr(entity.dxf, 'center') and hasattr(entity.dxf, 'radius'):
            try:
                # 直接使用圆心和半径计算边界
                center = entity.dxf.center
                radius = entity.dxf.radius
                min_x = min(min_x, center.x - radius)
                min_y = min(min_y, center.y - radius)
                max_x = max(max_x, center.x + radius)
                max_y = max(max_y, center.y + radius)
                entity_count += 1
            except Exception as e:
                log_print(f"警告: 处理Circle实体时出错: {e}", 'debug')  # 使用debug级别
        elif hasattr(entity, 'vertices'):
            # 检查vertices是否为方法或属性
            try:
                vertices = entity.vertices
                # 如果是方法，则调用它，对Circle类型特殊处理
                if callable(vertices):
                    # 避免对Circle调用vertices()方法时缺少angles参数
                    if entity.dxftype() == 'CIRCLE':
                        # 跳过Circle实体的vertices处理(因为前面已经特别处理过了)
                        continue
                    else:
                        vertices = vertices()
                
                # 确保vertices是可迭代的
                if hasattr(vertices, '__iter__'):
                    for vertex in vertices:
                        try:
                            if hasattr(vertex, 'dxf') and hasattr(vertex.dxf, 'location'):
                                point = vertex.dxf.location
                                min_x = min(min_x, point[0])
                                min_y = min(min_y, point[1])
                                max_x = max(max_x, point[0])
                                max_y = max(max_y, point[1])
                                entity_count += 1
                        except Exception as e:
                            log_print(f"警告: 处理顶点时出错: {e}", 'debug')  # 改为debug级别
            except Exception as e:
                # 将日志级别改为debug，防止打印到控制台
                log_print(f"警告: 访问实体vertices时出错: {e}", 'debug')
    
    if entity_count == 0:
        return None
    
    return min_x, min_y, max_x, max_y

def is_valid_room(vertices, min_area=1.0):
    """
    检查多边形是否可能是一个房间(基于面积和复杂性)
    """
    # 安全检查
    if not vertices or len(vertices) < 3:
        return False
    
    try:
        # 计算多边形面积
        area = 0
        for i in range(len(vertices)):
            j = (i + 1) % len(vertices)
            area += vertices[i][0] * vertices[j][1]
            area -= vertices[j][0] * vertices[i][1]
        area = abs(area) / 2.0
        
        # 使用参数指定的最小面积阈值
        return area >= min_area
    except Exception as e:
        log_print(f"警告: 计算面积时出错: {e}")
        return False

def room_to_image(room, extents, img_width, img_height):
    """
    将房间多边形转换为二进制图像
    """
    try:
        min_x, min_y, max_x, max_y = extents
        
        # 创建空白图像
        img = np.zeros((img_height, img_width), dtype=np.uint8)
        
        # 转换坐标到图像空间
        scaled_room = []
        for x, y in room:
            px = int((x - min_x) / (max_x - min_x) * (img_width - 1))
            py = int((y - min_y) / (max_y - min_y) * (img_height - 1))
            scaled_room.append((px, py))
        
        # 绘制填充多边形
        poly = np.array(scaled_room, dtype=np.int32)
        cv2.fillPoly(img, [poly], 255)
        
        return img > 0
    except Exception as e:
        log_print(f"警告: 转换房间到图像时出错: {e}")
        # 返回空图像
        return np.zeros((img_height, img_width), dtype=bool)

def save_skeleton_to_dxf(coords, output_file):
    """
    将骨架线保存为DXF文件
    """
    try:
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        
        # 创建POLYLINE对象表示骨架线
        if coords:
            # 简单处理：将点集合转换为多段线
            # 这里可以添加更复杂的处理，如检测分支点并创建多条线段
            polyline = msp.add_lwpolyline(coords)
            polyline.dxf.color = 1  # 红色
        
        doc.saveas(output_file)
        return True
    except Exception as e:
        log_print(f"警告: 保存骨架线到DXF文件时出错: {e}")
        return False

def preprocess_dwg(dxf_file, output_dxf=None):
    """
    预处理DWG文件：清理不必要的图层和实体，修复断开的线条
    
    参数:
        dxf_file: DXF文件路径
        output_dxf: 输出处理后的DXF文件路径，如果为None则不输出
    
    返回:
        预处理后的ezdxf文档对象
    """
    # log_print(f"预处理DXF文件: {dxf_file}")
    
    try:
        # 读取DXF文件
        doc = ezdxf.readfile(dxf_file)
        msp = doc.modelspace()
        
        # 1. 分析图层
        layers_info = analyze_layers(doc)
        log_print(f"找到 {len(layers_info)} 个图层")
        
        # 2. 识别需要保留的图层(墙体和门窗)
        relevant_layers = identify_wall_layers(layers_info)
        # log_print(f"将保留 {len(relevant_layers)} 个图层: {', '.join(relevant_layers)}")
        
        # 记录清理前的实体数量
        original_entities = len(list(doc.modelspace()))
        
        # 3. 清理不需要的图层和实体
        cleaned_doc = clean_layers(doc, keep_layers=relevant_layers)
        
        # 记录清理后的实体数量
        remaining_entities = len(list(cleaned_doc.modelspace()))
        log_print(f"清理图层完成：从 {original_entities} 个实体减少到 {remaining_entities} 个实体，清理率: {(original_entities - remaining_entities) / original_entities * 100:.1f}%")
        
        # 4. 修复断开的线条 - 临时注释掉此步骤
        # repaired_doc = repair_broken_lines(cleaned_doc, tolerance=0.1)
        repaired_doc = cleaned_doc  # 直接使用清理后的文档，跳过修复断开线条的步骤
        log_print("跳过修复断开线条的步骤")
        
        # 如果需要输出预处理后的文件
        if output_dxf:
            repaired_doc.saveas(output_dxf)
            log_print(f"预处理后的DXF文件已保存到: {output_dxf}")
            
            # 同时保存预览图像
            try:
                # 获取绘图范围
                extents = get_drawing_extents(repaired_doc.modelspace())
                if not extents:
                    extents = (0, 0, 1000, 1000)
                    log_print("警告: 无法获取绘图范围，使用默认范围")
                
                # 提取墙体线条
                walls = []
                for entity in repaired_doc.modelspace():
                    try:
                        if entity.dxftype() == 'LINE':
                            start = (entity.dxf.start.x, entity.dxf.start.y)
                            end = (entity.dxf.end.x, entity.dxf.end.y)
                            walls.append([(start, end)])
                        elif entity.dxftype() == 'LWPOLYLINE':
                            points = [(point[0], point[1]) for point in entity.get_points()]
                            if len(points) >= 2:
                                segments = []
                                for i in range(len(points) - 1):
                                    segments.append((points[i], points[i+1]))
                                if entity.is_closed and len(points) > 2:
                                    segments.append((points[-1], points[0]))
                                walls.append(segments)
                    except Exception as e:
                        log_print(f"提取墙体时出错: {e}")
                
                # 创建预览图像文件路径 - 与DXF文件同名但扩展名为.png
                preview_file = os.path.splitext(output_dxf)[0] + "_preview.png"
                
                # 创建预览图像
                img_size = 2000  # 预览图像尺寸
                preview_img = create_preview_image(walls, extents, preview_file, img_size)
                
                if preview_img is not None:
                    log_print(f"预处理后的预览图像已保存到: {preview_file}")
            except Exception as e:
                log_print(f"保存预览图像时出错: {e}", 'error')
        
        return repaired_doc
    
    except Exception as e:
        log_print(f"预处理DXF文件时出错: {e}")
        return None

def create_preview_image(walls, extents, output_file, img_size=2000):
    """
    创建墙体线条的预览图像
    
    参数:
        walls: 墙体线条列表
        extents: 图纸范围 (min_x, min_y, max_x, max_y)
        output_file: 输出文件路径
        img_size: 图像尺寸
    
    返回:
        生成的图像
    """
    # log_print(f"生成预处理预览图像: {output_file}")
    
    try:
        # 创建空白RGB图像
        img = np.ones((img_size, img_size, 3), dtype=np.uint8) * 255
        
        # 检查墙体数据是否为空
        if not walls:
            log_print("警告: 没有墙体数据，生成空白预览图", 'warning')
            cv2.putText(img, "预处理文件 (无墙体数据)", (50, 50), cv2.FONT_HERSHEY_COMPLEX, 
                       1.0, (0, 0, 0), 2, cv2.LINE_AA)
        else:
            # 检查范围是否有效
            if extents is None or len(extents) != 4:
                log_print("警告: 图纸范围无效，使用默认范围")
                extents = (0, 0, 1000, 1000)
            
            min_x, min_y, max_x, max_y = extents
            
            # 检查范围的有效性，防止除零错误
            if max_x - min_x < 1e-10 or max_y - min_y < 1e-10:
                log_print("警告: 图纸范围过小，使用默认范围")
                min_x, max_x = 0, 1000
                min_y, max_y = 0, 1000
                
            width = max_x - min_x
            height = max_y - min_y
            
            # 确保缩放比例有效
            if width < 1e-5 or height < 1e-5:
                scale = 1.0
            else:
                scale = min(img_size / width, img_size / height) * 0.9
                
            offset_x = (img_size - width * scale) / 2
            offset_y = (img_size - height * scale) / 2
            
            # 坐标转换函数，将原始坐标转换为图像坐标
            def transform(point):
                try:
                    x = int(offset_x + (point[0] - min_x) * scale)
                    y = int(img_size - (offset_y + (point[1] - min_y) * scale))  # Y坐标反转
                    # 确保坐标在图像范围内
                    x = max(0, min(x, img_size - 1))
                    y = max(0, min(y, img_size - 1))
                    return (x, y)
                except Exception as e:
                    log_print(f"坐标转换出错: {e}, 点: {point}")
                    return (0, 0)  # 返回安全值
            
            # 绘制所有的墙体
            walls_drawn = 0
            for wall in walls:
                for segment in wall:
                    start, end = segment
                    cv2.line(img, transform(start), transform(end), (0, 0, 0), 2)
                    walls_drawn += 1
            
            log_print(f"已绘制 {walls_drawn} 条墙体线段")
        
        # 添加标题
        cv2.putText(img, "预处理文件预览", (50, 50), cv2.FONT_HERSHEY_COMPLEX, 
                   1.0, (0, 0, 0), 2, cv2.LINE_AA)
        
        # 使用辅助函数保存图像
        save_image(img, output_file, title="预处理文件预览")
        
        return img
        
    except Exception as e:
        log_print(f"生成预处理预览图像时出错: {e}", 'error')
        traceback.print_exc()
        
        # 将异常堆栈也记录到日志
        log_print(traceback.format_exc(), 'debug')
        
        # 尝试生成一个简单的错误图像
        try:
            error_img = np.ones((800, 800, 3), dtype=np.uint8) * 255
            error_text = f"生成预览图像时出错: {str(e)[:50]}..."
            cv2.putText(error_img, error_text, (50, 400), cv2.FONT_HERSHEY_SIMPLEX, 
                       1, (0, 0, 255), 2, cv2.LINE_AA)
            
            # 使用辅助函数保存错误图像
            backup_file = os.path.join(os.getcwd(), f"error_preview_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.png")
            save_image(error_img, backup_file, title="错误信息")
            
            log_print(f"已创建错误提示图像: {backup_file}")
            return error_img
        except:
            log_print("创建错误提示图像也失败了", 'error')
            return None

def analyze_layers(doc):
    """
    分析DXF文件中的所有图层及其包含的实体类型
    
    返回:
        字典，键为图层名，值为该图层的信息（包含实体类型及数量）
    """
    layers_info = {}
    
    # 获取所有图层
    for layer in doc.layers:
        try:
            layer_name = layer.dxf.name
            # 处理无效颜色值 - 确保颜色值是有效的正整数
            color = layer.dxf.color if hasattr(layer.dxf, 'color') and layer.dxf.color > 0 else 7  # 使用默认颜色(白色)
            
            layers_info[layer_name] = {
                'entity_types': {},
                'color': color,
                'is_on': not layer.is_off if hasattr(layer, 'is_off') else True,
                'is_frozen': layer.is_frozen if hasattr(layer, 'is_frozen') else False,
                'linetype': layer.dxf.linetype if hasattr(layer.dxf, 'linetype') else 'CONTINUOUS'
            }
        except Exception as e:
            log_print(f"警告: 处理图层 {layer} 时出错: {e}")
            # 添加图层，但使用默认值
            layers_info[layer.dxf.name if hasattr(layer.dxf, 'name') else f'未知图层_{len(layers_info)}'] = {
                'entity_types': {},
                'color': 7,  # 默认颜色(白色)
                'is_on': True,
                'is_frozen': False,
                'linetype': 'CONTINUOUS'
            }
    
    # 分析各图层中的实体
    for entity in doc.entitydb.values():
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer'):
            layer_name = entity.dxf.layer
            entity_type = entity.dxftype()
            
            # 如果图层不在字典中（可能是因为图层表中没有定义），添加它
            if layer_name not in layers_info:
                layers_info[layer_name] = {
                    'entity_types': {},
                    'color': 7,  # 默认颜色
                    'is_on': True,
                    'is_frozen': False,
                    'linetype': 'CONTINUOUS'
                }
            
            # 更新该图层中此类实体的数量
            if entity_type in layers_info[layer_name]['entity_types']:
                layers_info[layer_name]['entity_types'][entity_type] += 1
            else:
                layers_info[layer_name]['entity_types'][entity_type] = 1
    
    return layers_info

def identify_wall_layers(layers_info):
    """
    识别可能的墙体图层、门窗图层和房间图层
    
    参数:
        layers_info: 图层信息字典
    
    返回:
        保留的图层名称列表（墙体+门窗图层），同时识别房间图层但不包含在返回结果中
    """
    # 初始化各类图层列表
    wall_layers = []       # 墙体图层
    door_window_layers = [] # 门窗图层
    room_layers = []       # 房间图层
    excluded_layers = []   # 排除图层
    text_layers = []       # 文字相关图层
    
    # ===== 关键词定义 =====
    # 墙体相关关键词
    wall_keywords = ['WALL', 'wall', '墙', '墙体', 'A-WALL', 'S-WALL', 'WALX', 'ARCH-WALL', '墙线', 
                    'QA', 'QZ', 'MQ', 'QIANG', 'BZ', '隔墙', '砖墙','柱',
                    '建-墙', '结构-墙', '建筑-墙', '剪力墙', '承重墙', '隔墙-砖墙', '隔墙—砖墙', 'I—隔墙']
    
    # 门窗相关关键词
    door_window_keywords = ['DOOR', 'door', '门', 'A-DOOR', 'WINDOW', 'window', '窗', 'A-WINDOW', 
                           'DOOR_WINDOW', 'OPENING', '建-窗', '建-门', 'I—平面—门', 'I-平面-窗', '门窗']
    
    # 房间相关关键词
    room_keywords = ['ROOM', 'Room', 'room', '房间', '房', 'SPACE', 'Space', 'space', '空间', 
                     'AREA', 'Area', 'area', '区域', 'ARCH-ROOM', 'A-ROOM', 'A-ZONE']
    
    # 文字和标注相关关键词
    text_keywords = ['TEXT', 'DIM', 'TITLE', '标注', '文字', '标题', '编号', '图框', '图例', 
                    'ANNOTATION', 'LABEL', 'NUMBER', 'NOTE', '备注', 'MARK', '符号', 'SYMBOL']
    
    # 其他应排除的关键词
    exclude_keywords = [
        # 家具相关
        'FURN', 'furniture', '家具', 'DESK', 'TABLE', 'CHAIR', 'BED', 'SOFA', 
        '桌', '椅', '床', '沙发', '柜', '橱', '移动家具', '室-家具', 'MOVABLE',
        
        # 设备相关
        'EQUIP', 'EQUIPMENT', '设备', '洁具', '卫生间', '装饰', '灯', '灯具', 
        '电气', 'ELEC', '暖通', 'HVAC', '给排水', 'PLUMBING', '空调', 'AC', 'AIR',
        
        # 装饰和结构元素
        '地坪', '踏步', '栏杆', '分隔', '填充', '轮廓线', '面层线', '平顶',
        'CEILING', '天花', 'FLOOR', '地面', 'STAIR', '楼梯', 'RAILING', '扶手', 
        'DECORATION', '装饰', 'FINISHING', '饰面', 'PATTERN', '图案',
        
        # 其他非墙体图层
        'GRID', '轴网', 'COLUMN', '柱', 'BEAM', '梁',
        'LANDSCAPE', '景观', 'VEGETATION', '植被', 
        'SITE', '场地', 'LINE', '线条', 'LAYOUT', '布局'
    ]
    
    # ===== 辅助函数 =====
    def check_keywords(name, keywords):
        """检查图层名称是否包含关键词列表中的任一关键词"""
        name_lower = name.lower()
        return any(keyword.lower() in name_lower for keyword in keywords)
    
    def is_text_layer(name):
        """判断是否为文字图层"""
        return check_keywords(name, text_keywords) or '文字' in name or '编号' in name
    
    def is_room_layer(name, info):
        """判断是否为房间图层"""
        # 基于名称判断
        if check_keywords(name, room_keywords):
            return True
        
        # 基于实体类型判断 - 房间常用闭合多段线或填充表示
        entity_types = info['entity_types']
        if ('LWPOLYLINE' in entity_types or 'POLYLINE' in entity_types or 'HATCH' in entity_types) and \
           not info['is_frozen']:
            # 额外判断：房间图层通常不包含大量线条
            line_count = entity_types.get('LINE', 0)
            polyline_count = entity_types.get('LWPOLYLINE', 0) + entity_types.get('POLYLINE', 0)
            hatch_count = entity_types.get('HATCH', 0)
            
            # 如果多段线或填充数量较多，而线条相对较少，可能是房间图层
            if (polyline_count > 5 or hatch_count > 0) and (line_count == 0 or polyline_count / line_count > 0.5):
                return True
        
        return False
    
    # ===== 第一步：预处理 - 识别文字、房间和其他基础图层 =====
    for layer_name, info in layers_info.items():
        # 检查是否为文字图层
        if is_text_layer(layer_name):
            text_layers.append(layer_name)
            excluded_layers.append(layer_name)
            continue
            
        # 检查是否为房间图层
        if is_room_layer(layer_name, info):
            room_layers.append(layer_name)
            # 注意：房间图层不自动加入排除列表，因为有些图层可能既是房间图层又是墙体图层
            continue
    
    # ===== 第二步：主处理 - 识别墙体和门窗图层 =====
    for layer_name, info in layers_info.items():
        # 跳过已识别的文字图层
        if layer_name in text_layers:
            continue
        
        # 判断墙体图层 (优先级最高)
        if '隔墙' in layer_name or '砖墙' in layer_name or check_keywords(layer_name, wall_keywords):
            wall_layers.append(layer_name)
            continue
        
        # 判断门窗图层 (确保不是文字图层)
        if check_keywords(layer_name, door_window_keywords) and not is_text_layer(layer_name):
            door_window_layers.append(layer_name)
            continue
        
        # 判断排除图层
        if check_keywords(layer_name, exclude_keywords) and not check_keywords(layer_name, wall_keywords):
            excluded_layers.append(layer_name)
            continue
            
        # 特殊情况检查
        if any(keyword in layer_name for keyword in ['灯', '洁具', '栏杆', '踏步', '暖通', 
                                                 ('隔断' if '墙' not in layer_name else ''), '家具']):
            excluded_layers.append(layer_name)
            continue
            
        # 未分类图层，基于图层内容进行判断
        entity_types = info['entity_types']
        line_count = entity_types.get('LINE', 0) + entity_types.get('LWPOLYLINE', 0) + entity_types.get('POLYLINE', 0)
        text_count = entity_types.get('TEXT', 0) + entity_types.get('MTEXT', 0)
        
        # 可能的墙体图层：线条多，文本少
        if (line_count > 20 and (text_count == 0 or line_count / text_count > 10) 
                and info['is_on'] and not info['is_frozen']):
            wall_layers.append(layer_name)
        else:
            excluded_layers.append(layer_name)
    
    # ===== 第三步：检查隔墙类型的图层是否被误排除，恢复它们 =====
    for layer_name in list(excluded_layers):
        if '隔墙' in layer_name or '砖墙' in layer_name:
            excluded_layers.remove(layer_name)
            if layer_name not in wall_layers:
                wall_layers.append(layer_name)
                log_print(f"从排除列表中恢复墙体图层: {layer_name}")
    
    # ===== 第四步：最终清理 - 确保图层分类的一致性 =====
    # 处理墙体图层
    for layer_name in list(wall_layers):
        # 如果是文字图层或已被排除的图层（除了特殊的隔墙和砖墙图层）
        if is_text_layer(layer_name) or (layer_name in excluded_layers and 
                                        '隔墙' not in layer_name and '砖墙' not in layer_name):
            wall_layers.remove(layer_name)
            if layer_name not in excluded_layers:
                excluded_layers.append(layer_name)
                log_print(f"从墙体图层中移除非墙体图层: {layer_name}")
    
    # 处理门窗图层
    for layer_name in list(door_window_layers):
        # 门窗图层不应出现在排除图层中
        if layer_name in excluded_layers:
            door_window_layers.remove(layer_name)
            log_print(f"从门窗图层中移除被排除的图层: {layer_name}")
        # 门窗图层不应是文字图层
        elif is_text_layer(layer_name):
            door_window_layers.remove(layer_name)
            if layer_name not in excluded_layers:
                excluded_layers.append(layer_name)
                log_print(f"从门窗图层中移除文字/编号图层: {layer_name}")
    
    # ===== 第五步：处理房间图层与其他图层的关系 =====
    # 记录既是房间图层又是墙体/门窗图层的情况
    wall_room_overlap = [layer for layer in room_layers if layer in wall_layers]
    door_room_overlap = [layer for layer in room_layers if layer in door_window_layers]
    
    if wall_room_overlap:
        log_print(f"警告：以下图层既被识别为墙体图层又被识别为房间图层: {', '.join(wall_room_overlap)}")
    
    if door_room_overlap:
        log_print(f"警告：以下图层既被识别为门窗图层又被识别为房间图层: {', '.join(door_room_overlap)}")
    
    # 合并墙体和门窗图层
    all_layers = list(set(wall_layers + door_window_layers))
    
    # 输出日志
    log_print(f"识别出的墙体图层: {', '.join(wall_layers)}")
    log_print(f"识别出的门窗图层: {', '.join(door_window_layers)}")
    log_print(f"识别出的房间图层: {', '.join(room_layers)}")
    log_print(f"排除的非墙体图层: {', '.join(excluded_layers)}")
    # log_print(f"保留的总图层数: {len(all_layers)}")
    
    return all_layers

def clean_layers(doc, keep_layers):
    """
    保留指定的图层，删除其他图层的实体
    
    参数:
        doc: ezdxf文档对象
        keep_layers: 要保留的图层名称列表 (由identify_wall_layers函数返回)
    
    返回:
        清理后的ezdxf文档对象，只包含keep_layers和0图层中的实体
    """
    # 导入transform模块
    import ezdxf.transform as transform
    
    # 确保0图层被包含在要保留的图层列表中
    if '0' not in keep_layers:
        keep_layers.append('0')
    
    log_print(f"保留以下图层: {', '.join(keep_layers)}")
    
    # 创建新文档
    new_doc = ezdxf.new(dxfversion=doc.dxfversion)
    
    # 复制所有需要的图层定义
    for layer_name in keep_layers:
        if layer_name in doc.layers:
            try:
                source_layer = doc.layers.get(layer_name)
                # 确保颜色值和线型是有效的
                color = source_layer.dxf.color if hasattr(source_layer.dxf, 'color') and source_layer.dxf.color > 0 else 7
                linetype = source_layer.dxf.linetype if hasattr(source_layer.dxf, 'linetype') else 'CONTINUOUS'
                
                # 添加图层到新文档
                if layer_name != '0':  # 0图层默认存在
                    new_doc.layers.add(
                        name=layer_name,
                        color=color,
                        linetype=linetype
                    )
            except Exception as e:
                log_print(f"警告: 添加图层 {layer_name} 时出错: {e}")
    
    # 使用transform模块复制保留图层中的实体
    new_msp = new_doc.modelspace()
    source_msp = doc.modelspace()
    
    # 初始化计数器
    total_entities = 0
    entities_kept = 0
    
    # 先收集要保留的实体
    entities_to_copy = []
    
    # 遍历源文档中的所有实体
    for entity in source_msp:
        total_entities += 1
        
        if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer'):
            if entity.dxf.layer in keep_layers:
                entities_to_copy.append(entity)
    
    # 使用transform.copies函数批量复制实体
    if entities_to_copy:
        try:
            # 使用transform.copies模块复制实体
            logger, copied_entities = transform.copies(entities_to_copy)
            
            # 将复制的实体添加到新的模型空间
            for entity in copied_entities:
                new_msp.add_entity(entity)
                
            entities_kept = len(entities_to_copy)
        except Exception as e:
            log_print(f"使用transform.copies复制实体时出错: {e}")
            # 如果批量复制失败，回退到单独处理每个实体
            log_print("回退到逐个实体处理模式...")
            entities_kept = 0
            
            # 手动逐个复制实体
            for entity in entities_to_copy:
                try:
                    entity_type = entity.dxftype()
                    
                    if entity_type == 'LINE':
                        new_entity = new_msp.add_line(
                            start=entity.dxf.start,
                            end=entity.dxf.end
                        )
                        new_entity.dxf.layer = entity.dxf.layer
                        entities_kept += 1
                    
                    elif entity_type == 'LWPOLYLINE':
                        points = list(entity.get_points())
                        if points:
                            new_entity = new_msp.add_lwpolyline(points)
                            new_entity.dxf.layer = entity.dxf.layer
                            if hasattr(entity, 'closed'):
                                new_entity.closed = entity.closed
                            entities_kept += 1
                    
                    elif entity_type == 'POLYLINE':
                        try:
                            vertices = []
                            vertex_list = entity.vertices
                            if callable(vertex_list):
                                vertex_list = vertex_list()
                                
                            for vertex in vertex_list:
                                if hasattr(vertex, 'dxf') and hasattr(vertex.dxf, 'location'):
                                    vertices.append(vertex.dxf.location)
                            
                            if vertices:
                                new_entity = new_msp.add_lwpolyline(vertices)
                                new_entity.dxf.layer = entity.dxf.layer
                                if hasattr(entity, 'is_closed') and entity.is_closed:
                                    new_entity.closed = True
                                entities_kept += 1
                        except Exception as ve:
                            log_print(f"警告: 处理POLYLINE顶点时出错: {ve}")
                    
                    elif entity_type == 'ARC':
                        new_entity = new_msp.add_arc(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius,
                            start_angle=entity.dxf.start_angle,
                            end_angle=entity.dxf.end_angle
                        )
                        new_entity.dxf.layer = entity.dxf.layer
                        entities_kept += 1
                    
                    elif entity_type == 'CIRCLE':
                        new_entity = new_msp.add_circle(
                            center=entity.dxf.center,
                            radius=entity.dxf.radius
                        )
                        new_entity.dxf.layer = entity.dxf.layer
                        entities_kept += 1
                    
                    elif entity_type == 'ELLIPSE':
                        new_entity = new_msp.add_ellipse(
                            center=entity.dxf.center,
                            major_axis=entity.dxf.major_axis,
                            ratio=entity.dxf.ratio,
                            start_param=entity.dxf.start_param if hasattr(entity.dxf, 'start_param') else 0,
                            end_param=entity.dxf.end_param if hasattr(entity.dxf, 'end_param') else 6.28318
                        )
                        new_entity.dxf.layer = entity.dxf.layer
                        entities_kept += 1
                    
                    elif entity_type == 'SPLINE':
                        try:
                            # 尝试从样条曲线中获取点
                            points = None
                            
                            # 首先尝试获取拟合点
                            if hasattr(entity, 'fit_points') and entity.fit_points and len(entity.fit_points) >= 2:
                                points = entity.fit_points
                                log_print(f"从SPLINE获取了 {len(points)} 个拟合点", level='debug')
                            # 如果没有拟合点，尝试获取控制点
                            elif hasattr(entity, 'control_points') and entity.control_points and len(entity.control_points) >= 2:
                                points = entity.control_points
                                log_print(f"从SPLINE获取了 {len(points)} 个控制点", level='debug')
                            
                            # 如果有足够的点，创建LWPOLYLINE
                            if points is not None and len(points) >= 2:
                                # 获取二维点
                                points_2d = [(p.x, p.y) if hasattr(p, 'x') and hasattr(p, 'y') else (p[0], p[1]) for p in points]
                                
                                # 检查是否是闭合曲线
                                is_closed = False
                                if hasattr(entity, 'is_closed'):
                                    is_closed = entity.is_closed
                                
                                # 创建LWPOLYLINE
                                new_entity = new_msp.add_lwpolyline(
                                    points=points_2d,
                                    dxfattribs={
                                        'layer': entity.dxf.layer
                                    },
                                    close=is_closed
                                )
                                
                                log_print(f"已将SPLINE转换为LWPOLYLINE，共 {len(points_2d)} 个点, 闭合状态: {is_closed}", level='debug')
                                entities_kept += 1
                            else:
                                log_print(f"跳过SPLINE：未找到足够的点", level='warning')
                        except Exception as e:
                            log_print(f"处理SPLINE实体时出错: {e}", level='warning')
                    
                    elif entity_type == 'INSERT':
                        try:
                            # 获取源块名称
                            block_name = entity.dxf.name
                            
                            # 检查目标文档中是否已存在该块定义
                            if block_name not in new_doc.blocks:
                                # 获取源块定义
                                source_block = doc.blocks.get(block_name)
                                if source_block:
                                    # 创建新块定义
                                    target_block = new_doc.blocks.new(block_name)
                                    
                                    # 复制简单实体
                                    for block_entity in source_block:
                                        try:
                                            # 只处理基本实体类型
                                            if block_entity.dxftype() in ['LINE', 'LWPOLYLINE', 'POLYLINE', 'ARC', 'CIRCLE', 'ELLIPSE']:
                                                # 使用transform.copy_entity复制实体
                                                copied_entity = transform.copy_entity(block_entity, target_block)
                                                log_print(f"已复制块'{block_name}'中的实体: {block_entity.dxftype()}", level='debug')
                                        except Exception as be:
                                            log_print(f"复制块'{block_name}'中的实体时出错: {be}", level='warning')
                                else:
                                    log_print(f"未找到块定义: {block_name}", level='warning')
                            
                            # 创建块引用
                            new_entity = new_msp.add_blockref(
                                name=block_name,
                                insert=(entity.dxf.insert.x, entity.dxf.insert.y),
                                dxfattribs={
                                    'layer': entity.dxf.layer
                                }
                            )
                            
                            # 设置比例和旋转
                            if hasattr(entity.dxf, 'xscale'):
                                new_entity.dxf.xscale = entity.dxf.xscale
                            if hasattr(entity.dxf, 'yscale'):
                                new_entity.dxf.yscale = entity.dxf.yscale
                            if hasattr(entity.dxf, 'zscale'):
                                new_entity.dxf.zscale = entity.dxf.zscale
                            if hasattr(entity.dxf, 'rotation'):
                                new_entity.dxf.rotation = entity.dxf.rotation
                                
                            log_print(f"成功处理INSERT: {block_name}", level='debug')
                            entities_kept += 1
                        except Exception as e:
                            log_print(f"处理INSERT实体时出错: {e}", level='warning')
                    
                    elif entity_type == 'HATCH':
                        try:
                            boundaries_processed = False
                            # 获取填充边界
                            for path in entity.paths:
                                # path可能是坐标列表或带有vertices属性的对象
                                vertices = []
                                if hasattr(path, 'vertices'):
                                    # 某些版本的ezdxf，path有vertices属性
                                    vertices = path.vertices
                                elif isinstance(path, (list, tuple)):
                                    # 某些版本的ezdxf，path直接是坐标列表
                                    vertices = path
                                
                                # 处理顶点
                                valid_vertices = []
                                for vertex in vertices:
                                    if isinstance(vertex, (list, tuple)) and len(vertex) >= 2:
                                        valid_vertices.append((vertex[0], vertex[1]))
                                    elif hasattr(vertex, 'x') and hasattr(vertex, 'y'):
                                        valid_vertices.append((vertex.x, vertex.y))
                                
                                # 如果有足够的顶点，创建多段线边界
                                if len(valid_vertices) >= 3:
                                    polyline = new_msp.add_lwpolyline(valid_vertices)
                                    polyline.dxf.layer = entity.dxf.layer
                                    polyline.dxf.closed = True  # 填充边界通常是闭合的
                                    boundaries_processed = True
                            
                            if boundaries_processed:
                                log_print(f"HATCH转换为边界多段线成功", level='debug')
                                entities_kept += 1
                            else:
                                log_print(f"未能处理HATCH边界: 没有有效的点", level='warning')
                        except Exception as e:
                            log_print(f"处理HATCH实体时出错: {e}", level='warning')
                    
                    else:
                        log_print(f"跳过未处理的实体类型: {entity_type}")
                
                except Exception as e:
                    log_print(f"手动复制实体时出错: {e}, 类型: {entity.dxftype() if hasattr(entity, 'dxftype') else '未知'}")
    
    # 打印统计信息
    log_print(f"原始实体总数: {total_entities}")
    log_print(f"已保留实体数: {entities_kept}")
    
    return new_doc

def repair_broken_lines(doc, tolerance=0.1):
    """
    修复断开的线条，将端点足够接近的线条连接起来
    
    参数:
        doc: ezdxf文档对象
        tolerance: 端点距离容差
    
    返回:
        修复后的ezdxf文档对象
    """
    msp = doc.modelspace()
    
    # 提取所有线段的端点
    lines = []
    for entity in msp.query('LINE'):
        start = (entity.dxf.start.x, entity.dxf.start.y)
        end = (entity.dxf.end.x, entity.dxf.end.y)
        lines.append((start, end, entity))
    
    # 识别需要合并的线段
    i = 0
    while i < len(lines):
        start1, end1, entity1 = lines[i]
        merged = False
        
        j = i + 1
        while j < len(lines):
            start2, end2, entity2 = lines[j]
            
            # 计算各端点之间的距离
            d_s1s2 = math.sqrt((start1[0] - start2[0])**2 + (start1[1] - start2[1])**2)
            d_s1e2 = math.sqrt((start1[0] - end2[0])**2 + (start1[1] - end2[1])**2)
            d_e1s2 = math.sqrt((end1[0] - start2[0])**2 + (end1[1] - start2[1])**2)
            d_e1e2 = math.sqrt((end1[0] - end2[0])**2 + (end1[1] - end2[1])**2)
            
            # 找到最小距离及对应的端点
            min_dist = min(d_s1s2, d_s1e2, d_e1s2, d_e1e2)
            
            if min_dist <= tolerance:
                # 这两条线可以合并
                if min_dist == d_s1s2:
                    # start1 连接 start2，需要翻转第二条线
                    new_line = (end1, end2, None)
                elif min_dist == d_s1e2:
                    # start1 连接 end2
                    new_line = (end1, start2, None)
                elif min_dist == d_e1s2:
                    # end1 连接 start2
                    new_line = (start1, end2, None)
                else:  # min_dist == d_e1e2
                    # end1 连接 end2，需要翻转第二条线
                    new_line = (start1, start2, None)
                
                # 移除原来的两条线
                msp.delete_entity(entity1)
                msp.delete_entity(entity2)
                
                # 添加合并后的新线
                new_entity = msp.add_line(new_line[0], new_line[1])
                lines[i] = (new_line[0], new_line[1], new_entity)
                lines.pop(j)
                
                merged = True
                break
            
            j += 1
        
        if not merged:
            i += 1
    
    return doc

def extract_walls_and_rooms(doc, min_room_area, img_size=2000):
    """
    从DXF文档中提取墙体线条和房间
    
    参数:
        doc: DXF文档对象
        min_room_area: 最小有效房间面积
        img_size: 图像大小
    
    返回:
        walls: 墙体线条列表
        rooms: 识别出的房间列表
        extents: 图纸范围 [xmin, ymin, xmax, ymax]
    """
    log_print("提取墙体线条和房间...")
    
    # 获取建模空间
    msp = doc.modelspace()
    
    # 0. 分析图层信息
    layers_info = analyze_layers(doc)
    
    # 识别墙体图层和房间图层
    keep_layers = identify_wall_layers(layers_info)
    
    # 从墙体图层函数的返回中获取房间图层信息
    # 临时提取房间图层列表，不影响原有代码逻辑
    room_layers = []
    for layer_name, info in layers_info.items():
        # 使用与identify_wall_layers中相同的is_room_layer判断逻辑
        # 判断是否为房间图层
        if any(keyword in layer_name.lower() for keyword in ['room', 'room', '房间', '房', 'space', 'space', '空间', 
                                                           'area', 'area', '区域', 'arch-room', 'a-room', 'a-zone']):
            room_layers.append(layer_name)
            continue
            
        # 基于实体类型判断
        entity_types = info['entity_types']
        if ('LWPOLYLINE' in entity_types or 'POLYLINE' in entity_types or 'HATCH' in entity_types) and \
           not info['is_frozen']:
            # 额外判断
            line_count = entity_types.get('LINE', 0)
            polyline_count = entity_types.get('LWPOLYLINE', 0) + entity_types.get('POLYLINE', 0)
            hatch_count = entity_types.get('HATCH', 0)
            
            if (polyline_count > 5 or hatch_count > 0) and (line_count == 0 or polyline_count / line_count > 0.5):
                room_layers.append(layer_name)
    
    # 1. 先尝试从专门的房间图层提取房间
    rooms_from_layers = []
    extents_from_rooms = None
    
    if room_layers:
        log_print("尝试从专门的房间图层直接提取房间...")
        
        # 提取多段线实体，这些通常定义了房间边界
        for entity in msp.query('LWPOLYLINE POLYLINE HATCH'):
            try:
                if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer') and entity.dxf.layer in room_layers:
                    if entity.dxftype() == 'LWPOLYLINE':
                        # 检查多段线是否闭合
                        if entity.is_closed:
                            points = [(point[0], point[1]) for point in entity.get_points()]
                            if len(points) >= 3 and is_valid_room(points, min_room_area):
                                rooms_from_layers.append(points)
                    
                    elif entity.dxftype() == 'POLYLINE':
                        try:
                            if entity.is_closed:
                                vertices = entity.vertices
                                if callable(vertices):
                                    vertices = vertices()
                                
                                points = []
                                if hasattr(vertices, '__iter__'):
                                    for vertex in vertices:
                                        if hasattr(vertex, 'dxf') and hasattr(vertex.dxf, 'location'):
                                            points.append((vertex.dxf.location[0], vertex.dxf.location[1]))
                                
                                if len(points) >= 3 and is_valid_room(points, min_room_area):
                                    rooms_from_layers.append(points)
                        except Exception as e:
                            log_print(f"警告: 处理房间图层POLYLINE时出错: {e}")
                    
                    # 处理填充区域（有时用于表示房间）
                    elif entity.dxftype() == 'HATCH':
                        try:
                            for path in entity.paths:
                                if path.is_polyline_path and len(path.vertices) >= 3:
                                    # 将填充区域边界作为房间
                                    points = [(vertex[0], vertex[1]) for vertex in path.vertices]
                                    if is_valid_room(points, min_room_area):
                                        rooms_from_layers.append(points)
                        except Exception as e:
                            log_print(f"警告: 处理房间图层HATCH时出错: {e}")
            except Exception as e:
                log_print(f"警告: 处理房间图层实体时出错: {e}")
        
        log_print(f"从专门的房间图层直接识别出 {len(rooms_from_layers)} 个可能的房间")
        
        # 计算这些房间的范围
        if rooms_from_layers:
            min_x, min_y = float('inf'), float('inf')
            max_x, max_y = float('-inf'), float('-inf')
            
            for room in rooms_from_layers:
                for point in room:
                    min_x = min(min_x, point[0])
                    min_y = min(min_y, point[1])
                    max_x = max(max_x, point[0])
                    max_y = max(max_y, point[1])
            
            if min_x < float('inf') and min_y < float('inf') and max_x > float('-inf') and max_y > float('-inf'):
                extents_from_rooms = (min_x, min_y, max_x, max_y)
    
    # 2. 收集所有线条和多段线（用于墙体识别）
    walls = []
    exclude_layers = set()
    # 排除家具、设备、标注等非墙体图层
    furniture_equipment_keywords = ['家具', 'FURN', 'furniture', '设备', 'EQUIP', 'equipment', 
                                   '标注', 'TEXT', 'text', 'ANNO', 'annotation', '轴网', 
                                   'GRID', 'grid', '灯具', 'LIGHT', '卫生', 'TOILET', 
                                   'PLUMB', '管道', 'PIPE', '电气', 'ELEC']
    
    # 创建排除图层集合
    for layer_name in layers_info.keys():
        if any(keyword in layer_name for keyword in furniture_equipment_keywords):
            exclude_layers.add(layer_name)
    
    log_print(f"排除的非墙体图层: {len(exclude_layers)} 个")
    
    for entity in msp.query('LINE LWPOLYLINE POLYLINE'):
        try:
            # 跳过来自排除图层的实体
            if hasattr(entity, 'dxf') and hasattr(entity.dxf, 'layer') and entity.dxf.layer in exclude_layers:
                continue
                
            # 处理不同类型的实体
            if entity.dxftype() == 'LINE':
                start = (entity.dxf.start.x, entity.dxf.start.y)
                end = (entity.dxf.end.x, entity.dxf.end.y)
                walls.append([(start, end)])
            
            elif entity.dxftype() == 'LWPOLYLINE':
                points = [(point[0], point[1]) for point in entity.get_points()]
                if len(points) >= 2:
                    segments = []
                    for i in range(len(points) - 1):
                        segments.append((points[i], points[i+1]))
                    # 如果是闭合的多段线，连接最后一点和第一点
                    if entity.is_closed:
                        segments.append((points[-1], points[0]))
                    walls.append(segments)
            
            elif entity.dxftype() == 'POLYLINE':
                try:
                    vertices = entity.vertices
                    if callable(vertices):
                        vertices = vertices()
                    
                    points = []
                    if hasattr(vertices, '__iter__'):
                        for vertex in vertices:
                            if hasattr(vertex, 'dxf') and hasattr(vertex.dxf, 'location'):
                                points.append((vertex.dxf.location[0], vertex.dxf.location[1]))
                    
                    if len(points) >= 2:
                        segments = []
                        for i in range(len(points) - 1):
                            segments.append((points[i], points[i+1]))
                        # 如果是闭合的多段线，连接最后一点和第一点
                        if entity.is_closed:
                            segments.append((points[-1], points[0]))
                        walls.append(segments)
                except Exception as e:
                    log_print(f"警告: 处理POLYLINE时出错: {e}")
        
        except Exception as e:
            log_print(f"警告: 处理实体时出错: {e}")
    
    log_print(f"收集到 {len(walls)} 条墙体线/多段线")
    
    # 3. 将墙体线条转换为栅格图像
    walls_img, extents_from_walls = convert_walls_to_image(walls, img_size)
    
    # 4. 从墙体图像识别房间（闭合区域）
    rooms_from_walls = identify_rooms(walls_img, extents_from_walls, min_room_area, max_room_area=None)
    log_print(f"从墙体图像识别出 {len(rooms_from_walls)} 个可能的房间")
    
    # 5. 合并两种方式获取的房间
    all_rooms = []
    
    # 添加从专门房间图层获取的房间（优先）
    if rooms_from_layers:
        all_rooms.extend(rooms_from_layers)
    
    # 添加从墙体图像识别出的房间（如果还没有足够的房间）
    if len(all_rooms) < 3 and rooms_from_walls:  # 假设至少需要3个房间才算合理结果
        all_rooms.extend(rooms_from_walls)
    
    # 确定最终使用的extents
    final_extents = None
    if extents_from_rooms:
        final_extents = extents_from_rooms
        log_print("使用从房间图层计算的范围")
    elif extents_from_walls:
        final_extents = extents_from_walls
        log_print("使用从墙体计算的范围")
    else:
        log_print("警告: 无法确定图纸范围，使用默认范围")
        final_extents = (0, 0, 1000, 1000)
    
    log_print(f"最终识别出 {len(all_rooms)} 个房间")
    
    # Return the original walls list, rooms list, and the calculated extents
    return walls, all_rooms, final_extents

def convert_walls_to_image(walls, img_size=2000, line_thickness=5):
    """
    将墙体线条转换为二值图像
    
    参数:
        walls: 墙体线条列表
        img_size: 图像大小
        line_thickness: 墙体线条粗细
    
    返回:
        img: 墙体二值图像
        extents: 图像范围 (min_x, min_y, max_x, max_y)
    """
    # 计算所有线条的边界范围
    min_x, min_y = float('inf'), float('inf')
    max_x, max_y = float('-inf'), float('-inf')
    
    for wall in walls:
        for segment in wall:
            start, end = segment
            min_x = min(min_x, start[0], end[0])
            min_y = min(min_y, start[1], end[1])
            max_x = max(max_x, start[0], end[0])
            max_y = max(max_y, start[1], end[1])
    
    # 创建空白图像
    img = np.zeros((img_size, img_size), dtype=np.uint8)
    
    # 绘制墙体线条
    for wall in walls:
        for segment in wall:
            start, end = segment
            # 转换坐标到图像空间
            start_x = int((start[0] - min_x) / (max_x - min_x + 1e-10) * (img_size - 1))
            start_y = int((start[1] - min_y) / (max_y - min_y + 1e-10) * (img_size - 1))
            end_x = int((end[0] - min_x) / (max_x - min_x + 1e-10) * (img_size - 1))
            end_y = int((end[1] - min_y) / (max_y - min_y + 1e-10) * (img_size - 1))
            
            # 绘制线条
            cv2.line(img, (start_x, start_y), (end_x, end_y), 255, line_thickness)
    
    extents = (min_x, min_y, max_x, max_y)
    return img, extents

def identify_rooms(img, extents, min_room_area=1.0, max_room_area=None):
    """
    从墙体图像中识别闭合区域（可能的房间）
    
    参数:
        img: 墙体二值图像
        extents: 图像范围
        min_room_area: 最小房间面积，占图纸总面积的百分比(%)
        max_room_area: 最大房间面积，占图纸总面积的百分比(%)，如果为None则默认为60%
    
    返回:
        rooms: 房间多边形列表，每个多边形是一个顶点列表[(x1,y1), (x2,y2), ...]
    """
    min_x, min_y, max_x, max_y = extents
    img_size = img.shape[0]
    
    # 获取整张图的总面积（实际坐标系中）
    total_area = (max_x - min_x) * (max_y - min_y)
    # 获取图像中一个像素代表的实际面积
    pixel_area_ratio = total_area / (img_size * img_size)
    
    # 计算最小房间面积（像素单位）
    # 将百分比转换为像素面积（例如：min_room_area=1.0表示图纸总面积的1%）
    min_room_area_pixels = int((min_room_area / 100.0) * (img_size * img_size))
    
    # 如果未指定max_room_area，则将其设为总面积的60%
    if max_room_area is None:
        max_room_area_pixels = int(0.6 * img_size * img_size)
    else:
        max_room_area_pixels = int((max_room_area / 100.0) * (img_size * img_size))
    
    log_print(f"房间面积范围: {min_room_area_pixels} - {max_room_area_pixels} 像素")
    log_print(f"对应实际面积比例: {min_room_area}% - {max_room_area if max_room_area else 60}% 的图纸总面积")
    
    # 保存中间结果，用于诊断
    try:
        debug_dir = os.path.join(os.getcwd(), 'debug')
        if not os.path.exists(debug_dir):
            os.makedirs(debug_dir)
        save_image(img, os.path.join(debug_dir, 'walls_binary.png'), title="墙体二值图")
    except Exception as e:
        log_print(f"保存调试图像时出错: {e}")
    
    # 反转图像，使墙体为0（黑），空间为1（白）
    # 首先生成全1图像
    filled_img = np.ones_like(img)
    # 将墙体部分设为0
    filled_img[img > 0] = 0
    
    # 保存中间结果，用于诊断
    try:
        save_image(filled_img * 255, os.path.join(debug_dir, 'inverted_walls.png'), title="反转墙体图")
    except Exception as e:
        log_print(f"保存调试图像时出错: {e}")
    
    # 增加形态学操作，填充小的缝隙和孔洞
    kernel = np.ones((3, 3), np.uint8)
    filled_img = cv2.morphologyEx(filled_img, cv2.MORPH_CLOSE, kernel)
    
    # 保存中间结果，用于诊断
    try:
        save_image(filled_img * 255, os.path.join(debug_dir, 'filled_gaps.png'), title="填充缝隙后的图像")
    except Exception as e:
        log_print(f"保存调试图像时出错: {e}")
    
    # 标记连通区域
    labeled_img = measure.label(filled_img, connectivity=2)
    props = measure.regionprops(labeled_img)
    
    # 保存标记图像，用于诊断
    try:
        # 归一化标记图像以便显示
        label_viz = np.zeros_like(labeled_img, dtype=np.uint8)
        for i, prop in enumerate(props):
            label_viz[labeled_img == prop.label] = (i % 254) + 1
        save_image(label_viz, os.path.join(debug_dir, 'labeled_regions.png'), title="标记的连通区域")
    except Exception as e:
        log_print(f"保存调试图像时出错: {e}")
    
    # 获取边缘区域的标签
    edge_labels = set()
    for x in range(img_size):
        if labeled_img[0, x] > 0:
            edge_labels.add(labeled_img[0, x])
        if labeled_img[img_size-1, x] > 0:
            edge_labels.add(labeled_img[img_size-1, x])
    for y in range(img_size):
        if labeled_img[y, 0] > 0:
            edge_labels.add(labeled_img[y, 0])
        if labeled_img[y, img_size-1] > 0:
            edge_labels.add(labeled_img[y, img_size-1])
    
    # 筛选可能的房间
    rooms = []
    filtered_count = 0
    edge_filtered = 0
    area_filtered = 0
    shape_filtered = 0
    
    for prop in props:
        area = prop.area
        label = prop.label
        
        # 过滤条件1: 检查面积是否在要求的范围内
        if area < min_room_area_pixels:
            area_filtered += 1
            continue
        if max_room_area_pixels is not None and area > max_room_area_pixels:
            area_filtered += 1
            continue
        
        # 过滤条件2: 排除接触图像边缘的区域（通常是外部空间而非房间）
        if label in edge_labels:
            edge_filtered += 1
            continue
        
        # 过滤条件3: 检查形状
        # 计算紧凑度 (4π*面积/周长²)，接近1表示圆形，接近0表示复杂形状
        perimeter = prop.perimeter
        if perimeter > 0:
            compactness = 4 * np.pi * area / (perimeter * perimeter)
            # 降低形状限制，允许更多形状
            if compactness < 0.03:  # 原来是0.05，现在放宽到0.03
                shape_filtered += 1
                continue
        
        # 获取区域边界
        contours = measure.find_contours(labeled_img == label, 0.5)
        if contours:
            # 选择最长的轮廓
            longest_contour = max(contours, key=len)
            
            # 将轮廓点转换回原始坐标系
            room_poly = []
            for y, x in longest_contour:
                orig_x = min_x + (x / (img_size - 1)) * (max_x - min_x)
                orig_y = min_y + (y / (img_size - 1)) * (max_y - min_y)
                room_poly.append((orig_x, orig_y))
            
            # 简化多边形，根据区域大小调整简化容差
            tolerance = 1.0
            if area > 5000:  # 大型区域使用更大的容差以减少点数
                tolerance = 2.0
            
            if len(room_poly) > 3:
                room_poly = simplify_polygon(room_poly, tolerance)
            
            # 过滤条件4: 顶点数过少或过多的多边形
            if len(room_poly) < 3:
                shape_filtered += 1
                continue
            if len(room_poly) > 100:  # 原来是50，现在放宽到100
                shape_filtered += 1
                continue
            
            rooms.append(room_poly)
    
    # 打印过滤统计信息
    log_print(f"过滤掉的区域: 面积不符: {area_filtered}, 边缘区域: {edge_filtered}, 形状异常: {shape_filtered}")
    log_print(f"保留的房间数量: {len(rooms)}")
    
    return rooms

def simplify_polygon(points, tolerance=1.0):
    """
    简化多边形，减少顶点数
    
    参数:
        points: 多边形顶点列表
        tolerance: 简化容差
    
    返回:
        简化后的多边形顶点列表
    """
    # 转换为numpy数组，便于处理
    points_np = np.array(points)
    
    # 转换为OpenCV格式的轮廓
    contour = np.expand_dims(points_np.astype(np.float32), 1)
    
    # 使用Douglas-Peucker算法简化多边形
    epsilon = tolerance
    simplified = cv2.approxPolyDP(contour, epsilon, True)
    
    # 转换回原始格式
    simplified_points = [(p[0][0], p[0][1]) for p in simplified]
    
    return simplified_points

def save_rooms_to_dxf(rooms, output_file):
    """
    将房间多边形保存到DXF文件
    
    参数:
        rooms: 房间多边形列表
        output_file: 输出DXF文件路径
    """
    try:
        # 创建输出目录（如果不存在）
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 创建新的DXF文档
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        
        # 创建图层
        doc.layers.add(name='ROOMS', color=2)  # 黄色
        
        # 添加房间多边形
        rooms_count = 0
        if rooms:
            for i, room in enumerate(rooms):
                try:
                    if not room or len(room) < 3:
                        continue
                    polyline = msp.add_lwpolyline(room)
                    polyline.dxf.layer = 'ROOMS'
                    polyline.closed = True
                    rooms_count += 1
                except Exception as e:
                    log_print(f"警告: 添加房间 {i+1} 到DXF时出错: {e}")
        
        log_print(f"已添加 {rooms_count} 个房间到DXF")
        
        # 保存DXF文件
        doc.saveas(output_file)
        log_print(f"DXF文件已成功保存到: {output_file}")
        return True
    
    except Exception as e:
        log_print(f"保存房间到DXF文件时出错: {e}")
        traceback.print_exc()
        return False

def create_rooms_overview(walls, rooms, extents, output_file, img_size=2000, title="房间分析总览图"):
    """
    创建房间总览图，包含墙体和房间信息
    
    参数:
        walls: 墙体线条列表
        rooms: 房间多边形列表
        extents: 图纸范围 (min_x, min_y, max_x, max_y)
        output_file: 输出文件路径
        img_size: 图像尺寸
        title: 图像标题
    
    返回:
        生成的图像
    """
    log_print(f"生成房间总览图像: {output_file}")
    
    try:
        # 创建空白RGB图像
        img = np.ones((img_size, img_size, 3), dtype=np.uint8) * 255
        
        # 检查数据是否为空
        if not walls and not rooms:
            log_print("警告: 没有墙体和房间数据，无法生成总览图", 'warning')
            # 创建一个包含错误消息的图像
            text = "未检测到有效的墙体和房间数据"
            cv2.putText(img, text, (50, 400), cv2.FONT_HERSHEY_SIMPLEX, 
                      1.5, (0, 0, 255), 3, cv2.LINE_AA)
            save_image(img, output_file, title="未检测到数据")
            return None
        
        # 检查范围是否有效
        if extents is None or len(extents) != 4:
            log_print("警告: 图纸范围无效，使用默认范围")
            extents = (0, 0, 1000, 1000)
        
        min_x, min_y, max_x, max_y = extents
        
        # 检查范围的有效性，防止除零错误
        if max_x - min_x < 1e-10 or max_y - min_y < 1e-10:
            log_print("警告: 图纸范围过小，使用默认范围")
            min_x, max_x = 0, 1000
            min_y, max_y = 0, 1000
            
        width = max_x - min_x
        height = max_y - min_y
        
        # 确保缩放比例有效
        if width < 1e-5 or height < 1e-5:
            scale = 1.0
        else:
            scale = min(img_size / width, img_size / height) * 0.9
            
        offset_x = (img_size - width * scale) / 2
        offset_y = (img_size - height * scale) / 2
        
        # 坐标转换函数，将原始坐标转换为图像坐标
        def transform(point):
            try:
                x = int(offset_x + (point[0] - min_x) * scale)
                y = int(img_size - (offset_y + (point[1] - min_y) * scale))  # Y坐标反转
                # 确保坐标在图像范围内
                x = max(0, min(x, img_size - 1))
                y = max(0, min(y, img_size - 1))
                return (x, y)
            except Exception as e:
                log_print(f"坐标转换出错: {e}, 点: {point}")
                return (0, 0)  # 返回安全值
        
        # 使用不同颜色填充房间
        colors = [
            (173, 216, 230),  # 浅蓝
            (144, 238, 144),  # 浅绿
            (255, 182, 193),  # 浅粉
            (255, 218, 185),  # 浅橙
            (230, 230, 250),  # 浅紫
            (152, 251, 152),  # 淡绿
            (238, 232, 170),  # 淡黄
            (240, 128, 128),  # 浅红
            (176, 224, 230),  # 粉蓝
            (238, 130, 238)   # 紫色
        ]
        
        # 绘制和标记房间
        rooms_drawn = 0
        if rooms:
            for i, room in enumerate(rooms):
                try:
                    if not room or len(room) < 3:
                        continue
                    
                    # 准备房间多边形
                    points = np.array([transform(point) for point in room], dtype=np.int32)
                    
                    # 填充房间（半透明颜色）
                    color = colors[i % len(colors)]
                    overlay = img.copy()
                    cv2.fillPoly(overlay, [points], color)
                    cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)  # 设置透明度
                    
                    # 绘制房间边界
                    cv2.polylines(img, [points], True, color, 2)
                    
                    # 添加房间编号
                    centroid_x = sum(point[0] for point in room) / len(room)
                    centroid_y = sum(point[1] for point in room) / len(room)
                    center = transform((centroid_x, centroid_y))
                    cv2.putText(img, f"{i+1}", center, cv2.FONT_HERSHEY_SIMPLEX, 
                               1.5, (0, 0, 0), 3, cv2.LINE_AA)
                    
                    rooms_drawn += 1
                except Exception as e:
                    log_print(f"绘制房间 {i+1} 时出错: {e}")
        
        log_print(f"已绘制 {rooms_drawn} 个房间")
        
        # 添加图例和标题
        # 标题
        cv2.putText(img, title, (50, 30), cv2.FONT_HERSHEY_COMPLEX, 
                   1.2, (0, 0, 0), 2, cv2.LINE_AA)
        
        # 图例背景
        cv2.rectangle(img, (20, 40), (220, 110), (240, 240, 240), -1)
        cv2.rectangle(img, (20, 40), (220, 110), (200, 200, 200), 1)
        
        # 图例
        legend_y = 70
        cv2.putText(img, "图例:", (30, legend_y), cv2.FONT_HERSHEY_SIMPLEX, 
                   1, (0, 0, 0), 2, cv2.LINE_AA)
        
        # 房间图例
        legend_y += 30
        sample_color = colors[0]
        cv2.rectangle(img, (30, legend_y-10), (80, legend_y+10), sample_color, -1)
        cv2.rectangle(img, (30, legend_y-10), (80, legend_y+10), (0, 0, 0), 1)
        cv2.putText(img, "房间", (100, legend_y+5), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (0, 0, 0), 1, cv2.LINE_AA)
        
        # 保存图像
        return save_image(img, output_file, title=title)
        
    except Exception as e:
        log_print(f"生成房间总览图像时出错: {e}", 'error')
        traceback.print_exc()
        
        # 将异常堆栈也记录到日志
        log_print(traceback.format_exc(), 'debug')
        
        # 尝试生成一个简单的错误图像
        try:
            error_img = np.ones((800, 1200, 3), dtype=np.uint8) * 255
            error_text = f"生成图像时出错: {str(e)[:50]}..."
            cv2.putText(error_img, error_text, (50, 400), cv2.FONT_HERSHEY_SIMPLEX, 
                       1, (0, 0, 255), 2, cv2.LINE_AA)
            save_image(error_img, output_file, title="错误信息")
            log_print(f"已创建错误提示图像: {output_file}")
        except:
            log_print("创建错误提示图像也失败了")
        
        return False

def save_room_to_dxf(room, output_file):
    """
    将单个房间多边形保存到DXF文件
    
    参数:
        room: 房间多边形顶点列表
        output_file: 输出DXF文件路径
    """
    try:
        # 创建输出目录（如果不存在）
        output_dir = os.path.dirname(output_file)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir)
            
        # 创建新的DXF文档
        doc = ezdxf.new('R2010')
        msp = doc.modelspace()
        
        # 创建图层
        doc.layers.add(name='ROOM', color=2)  # 黄色
        
        # 添加房间多边形
        if room and len(room) >= 3:
            polyline = msp.add_lwpolyline(room)
            polyline.dxf.layer = 'ROOM'
            polyline.closed = True
            
            # 添加房间中心点
            centroid_x = sum(point[0] for point in room) / len(room)
            centroid_y = sum(point[1] for point in room) / len(room)
            
            # 在中心点添加标记
            center_point = msp.add_circle((centroid_x, centroid_y), radius=0.5)
            center_point.dxf.layer = 'ROOM'
            
            # 计算房间面积和周长
            area = 0
            perimeter = 0
            for i in range(len(room)):
                j = (i + 1) % len(room)
                area += room[i][0] * room[j][1]
                area -= room[j][0] * room[i][1]
                
                # 计算两点之间的距离
                dx = room[j][0] - room[i][0]
                dy = room[j][1] - room[i][1]
                perimeter += math.sqrt(dx*dx + dy*dy)
            
            area = abs(area) / 2
            
            # 添加面积和周长文本
            text = msp.add_text(f"面积: {area:.2f}平方单位\n周长: {perimeter:.2f}单位")
            text.dxf.insert = (centroid_x, centroid_y - 2)
            text.dxf.height = 0.5
            text.dxf.layer = 'ROOM'
        
        # 保存DXF文件
        doc.saveas(output_file)
        return True
    
    except Exception as e:
        log_print(f"保存房间到DXF文件时出错: {e}")
        return False

def save_image(img, output_file, title=None):
    """
    保存图像到文件，使用matplotlib而不是cv2.imwrite，提高可靠性
    
    参数:
        img: 要保存的图像 (numpy数组)
        output_file: 输出文件路径
        title: 可选的图像标题
    
    返回:
        成功返回True，失败返回False
    """
    try:
        # 确保输出目录存在
        try:
            output_dir = os.path.dirname(output_file)
            if output_dir and not os.path.exists(output_dir):
                os.makedirs(output_dir)
                log_print(f"创建目录: {output_dir}")
        except Exception as e:
            log_print(f"创建输出目录时出错: {e}", 'error')
            # 尝试使用当前工作目录
            output_file = os.path.join(os.getcwd(), os.path.basename(output_file))
            log_print(f"改用当前工作目录: {output_file}")

        # 转换OpenCV的BGR图像到RGB (如果需要)
        if len(img.shape) == 3 and img.shape[2] == 3:
            img_to_save = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        else:
            # 如果是二值图像或灰度图像
            img_to_save = img
            
        # 保存图像但不包含中文标题 - 更可靠的方式
        # 第一步：生成图像，但先不设置中文标题
        plt.figure(figsize=(10, 10))
        if len(img.shape) == 2 or (len(img.shape) == 3 and img.shape[2] == 1):
            plt.imshow(img_to_save, cmap='gray')
        else:
            plt.imshow(img_to_save)
            
        plt.axis('off')  # 不显示坐标轴
        plt.tight_layout()  # 调整布局
        
        # 保存图像
        plt.savefig(output_file, bbox_inches='tight', pad_inches=0)
        plt.close()
        
        # 如果有中文标题，尝试使用PIL添加标题 - 这通常比matplotlib更可靠
        if title and os.path.exists(output_file):
            try:
                from PIL import Image, ImageDraw, ImageFont
                
                # 打开保存的图像
                pil_img = Image.open(output_file)
                draw = ImageDraw.Draw(pil_img)
                
                # 尝试找到中文字体
                font_size = 36
                font = None
                
                # 优先尝试Windows系统字体
                windows_font_paths = [
                    r"C:\Windows\Fonts\simhei.ttf",  # 黑体
                    r"C:\Windows\Fonts\msyh.ttc",    # 微软雅黑
                    r"C:\Windows\Fonts\simsun.ttc",  # 宋体
                ]
                
                for font_path in windows_font_paths:
                    if os.path.exists(font_path):
                        try:
                            font = ImageFont.truetype(font_path, font_size)
                            # log_print(f"使用PIL字体: {font_path}")
                            break
                        except:
                            continue
                
                # 如果没有找到系统字体，使用默认字体
                if font is None:
                    font = ImageFont.load_default()
                    # log_print("使用PIL默认字体")
                
                # 添加标题到图像顶部
                text_bbox = draw.textbbox((0, 0), title, font=font)
                text_width = text_bbox[2] - text_bbox[0]
                text_height = text_bbox[3] - text_bbox[1]
                
                # 计算文本位置（居中）
                x = (pil_img.width - text_width) // 2
                y = 20  # 距离顶部20像素
                
                # 绘制文本
                draw.text((x, y), title, font=font, fill=(0, 0, 0))  # 黑色文本
                
                # 保存添加了标题的图像
                pil_img.save(output_file)
                # log_print("使用PIL添加了中文标题")
            except Exception as pil_error:
                log_print(f"使用PIL添加标题失败: {pil_error}", 'warning')
                # 失败后尝试使用matplotlib的标题
                try:
                    # 重新创建图像，这次添加标题
                    plt.figure(figsize=(10, 10))
                    if len(img.shape) == 2 or (len(img.shape) == 3 and img.shape[2] == 1):
                        plt.imshow(img_to_save, cmap='gray')
                    else:
                        plt.imshow(img_to_save)
                        
                    # 尝试设置字体以支持中文
                    try:
                        font_props = fm.FontProperties(family=plt.rcParams['font.family'])
                        plt.title(title, fontproperties=font_props)
                    except:
                        plt.title(title)  # 如果设置字体失败，直接设置标题
                        
                    plt.axis('off')
                    plt.tight_layout()
                    plt.savefig(output_file, bbox_inches='tight', pad_inches=0)
                    plt.close()
                except:
                    log_print("使用matplotlib添加标题也失败了", 'warning')
        
        # 验证文件是否创建成功
        if os.path.exists(output_file):
            log_print(f"图像已成功保存到: {output_file}")
            # log_print(f"文件大小: {os.path.getsize(output_file)} 字节")
            return True
        else:
            log_print(f"保存图像失败: {output_file}", 'error')
            
            # 尝试备用路径
            filename = os.path.basename(output_file)
            name, ext = os.path.splitext(filename)
            backup_file = os.path.join(os.getcwd(), f"{name}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}")
            
            log_print(f"尝试保存到备用路径: {backup_file}")
            plt.figure(figsize=(10, 10))
            if len(img.shape) == 2 or (len(img.shape) == 3 and img.shape[2] == 1):
                plt.imshow(img_to_save, cmap='gray')
            else:
                plt.imshow(img_to_save)
            
            plt.axis('off')
            plt.savefig(backup_file)
            plt.close()
            
            if os.path.exists(backup_file):
                log_print(f"成功保存到备用路径: {backup_file}")
                return True
            
            return False
            
    except Exception as e:
        log_print(f"保存图像时出错: {e}", 'error')
        traceback.print_exc()
        
        try:
            # 最后尝试直接使用cv2.imwrite
            log_print("最后尝试使用cv2.imwrite")
            result = cv2.imwrite(output_file, img)
            return result
        except:
            return False

def create_overview_image(rooms, extents, output_file, img_size=2000, title="房间总览图"):
    """
    创建房间总览图，只包含房间信息
    
    参数:
        rooms: 房间多边形列表
        extents: 图纸范围 (min_x, min_y, max_x, max_y)
        output_file: 输出文件路径
        img_size: 图像尺寸
        title: 图像标题
    
    返回:
        成功创建返回True，否则返回False
    """
    log_print(f"生成房间总览图像: {output_file}")
    
    try:
        # 创建空白RGB图像
        img = np.ones((img_size, img_size, 3), dtype=np.uint8) * 255
        
        # 检查房间数据是否为空
        if not rooms:
            log_print("警告: 没有房间数据，无法生成总览图", 'warning')
            # 创建一个包含错误消息的图像
            text = "未检测到有效的房间数据"
            cv2.putText(img, text, (50, 400), cv2.FONT_HERSHEY_SIMPLEX, 
                      1.5, (0, 0, 255), 3, cv2.LINE_AA)
            return save_image(img, output_file, title="未检测到房间")
        
        # 检查范围是否有效
        if extents is None or len(extents) != 4:
            log_print("警告: 图纸范围无效，使用默认范围")
            extents = (0, 0, 1000, 1000)
        
        min_x, min_y, max_x, max_y = extents
        
        # 检查范围的有效性，防止除零错误
        if max_x - min_x < 1e-10 or max_y - min_y < 1e-10:
            log_print("警告: 图纸范围过小，使用默认范围")
            min_x, max_x = 0, 1000
            min_y, max_y = 0, 1000
            
        width = max_x - min_x
        height = max_y - min_y
        
        # 确保缩放比例有效
        if width < 1e-5 or height < 1e-5:
            scale = 1.0
        else:
            scale = min(img_size / width, img_size / height) * 0.9
            
        offset_x = (img_size - width * scale) / 2
        offset_y = (img_size - height * scale) / 2
        
        # 坐标转换函数，将原始坐标转换为图像坐标
        def transform(point):
            try:
                x = int(offset_x + (point[0] - min_x) * scale)
                y = int(img_size - (offset_y + (point[1] - min_y) * scale))  # Y坐标反转
                # 确保坐标在图像范围内
                x = max(0, min(x, img_size - 1))
                y = max(0, min(y, img_size - 1))
                return (x, y)
            except Exception as e:
                log_print(f"坐标转换出错: {e}, 点: {point}")
                return (0, 0)  # 返回安全值
        
        # 使用不同颜色填充房间
        colors = [
            (173, 216, 230),  # 浅蓝
            (144, 238, 144),  # 浅绿
            (255, 182, 193),  # 浅粉
            (255, 218, 185),  # 浅橙
            (230, 230, 250),  # 浅紫
            (152, 251, 152),  # 淡绿
            (238, 232, 170),  # 淡黄
            (240, 128, 128),  # 浅红
            (176, 224, 230),  # 粉蓝
            (238, 130, 238)   # 紫色
        ]
        
        # 绘制和标记房间
        rooms_drawn = 0
        if rooms:
            for i, room in enumerate(rooms):
                try:
                    if not room or len(room) < 3:
                        continue
                    
                    # 准备房间多边形
                    points = np.array([transform(point) for point in room], dtype=np.int32)
                    
                    # 填充房间（半透明颜色）
                    color = colors[i % len(colors)]
                    overlay = img.copy()
                    cv2.fillPoly(overlay, [points], color)
                    cv2.addWeighted(overlay, 0.3, img, 0.7, 0, img)  # 设置透明度
                    
                    # 绘制房间边界
                    cv2.polylines(img, [points], True, color, 2)
                    
                    # 添加房间编号
                    centroid_x = sum(point[0] for point in room) / len(room)
                    centroid_y = sum(point[1] for point in room) / len(room)
                    center = transform((centroid_x, centroid_y))
                    cv2.putText(img, f"{i+1}", center, cv2.FONT_HERSHEY_SIMPLEX, 
                               1.5, (0, 0, 0), 3, cv2.LINE_AA)
                    
                    rooms_drawn += 1
                except Exception as e:
                    log_print(f"绘制房间 {i+1} 时出错: {e}")
        
        log_print(f"已绘制 {rooms_drawn} 个房间")
        
        # 添加图例和标题
        # 标题
        cv2.putText(img, title, (50, 30), cv2.FONT_HERSHEY_COMPLEX, 
                   1.2, (0, 0, 0), 2, cv2.LINE_AA)
        
        # 图例背景
        cv2.rectangle(img, (20, 40), (220, 110), (240, 240, 240), -1)
        cv2.rectangle(img, (20, 40), (220, 110), (200, 200, 200), 1)
        
        # 图例
        legend_y = 70
        cv2.putText(img, "图例:", (30, legend_y), cv2.FONT_HERSHEY_SIMPLEX, 
                   1, (0, 0, 0), 2, cv2.LINE_AA)
        
        # 房间图例
        legend_y += 30
        sample_color = colors[0]
        cv2.rectangle(img, (30, legend_y-10), (80, legend_y+10), sample_color, -1)
        cv2.rectangle(img, (30, legend_y-10), (80, legend_y+10), (0, 0, 0), 1)
        cv2.putText(img, "房间", (100, legend_y+5), cv2.FONT_HERSHEY_SIMPLEX, 
                   0.8, (0, 0, 0), 1, cv2.LINE_AA)
        
        # 保存图像
        return save_image(img, output_file, title=title)
        
    except Exception as e:
        log_print(f"生成房间总览图像时出错: {e}", 'error')
        traceback.print_exc()
        
        # 将异常堆栈也记录到日志
        log_print(traceback.format_exc(), 'debug')
        
        # 尝试生成一个简单的错误图像
        try:
            error_img = np.ones((800, 1200, 3), dtype=np.uint8) * 255
            error_text = f"生成图像时出错: {str(e)[:50]}..."
            cv2.putText(error_img, error_text, (50, 400), cv2.FONT_HERSHEY_SIMPLEX, 
                       1, (0, 0, 255), 2, cv2.LINE_AA)
            save_image(error_img, output_file, title="错误信息")
            log_print(f"已创建错误提示图像: {output_file}")
        except:
            log_print("创建错误提示图像也失败了")
        
        return False

def main():
    # 创建命令行参数解析器
    parser = argparse.ArgumentParser(description='从DWG文件中提取房间骨架线')
    parser.add_argument('-d', '--data_dir', type=str, default='data', help='DWG文件所在目录 (默认: data)')
    parser.add_argument('-o', '--output_dir', type=str, default='output_rooms', help='输出目录 (默认: output_rooms)')
    parser.add_argument('-f', '--file', type=str, help='指定要处理的DWG文件名（位于data_dir中）')
    parser.add_argument('-a', '--area', type=float, default=1.0, help='识别房间的最小面积阈值 (默认: 1.0)')
    parser.add_argument('-s', '--size', type=int, default=2000, help='处理图像的尺寸 (默认: 2000x2000)')
    parser.add_argument('--convert-only', action='store_true', help='仅转换DWG到DXF，不进行骨架提取')
    parser.add_argument('--oda-path', type=str, help='指定ODA File Converter可执行文件的路径')
    parser.add_argument('--log-dir', type=str, help='指定日志文件保存目录')
    
    args = parser.parse_args()
    
    # 设置日志系统
    setup_logging(args.log_dir)
    log_print("=== 房间提取程序开始运行 ===")
    
    # 设置matplotlib支持中文
    setup_matplotlib_chinese()
    
    # 如果指定了ODA路径，设置全局变量
    if args.oda_path:
        global ODA_PATH
        ODA_PATH = args.oda_path
        log_print(f"使用自定义ODA File Converter路径: {ODA_PATH}")
    
    # 设置目录
    data_dir = args.data_dir
    output_dir = args.output_dir
    
    # 如果指定了特定文件
    if args.file:
        dwg_path = os.path.join(data_dir, args.file)
        if not os.path.exists(dwg_path):
            log_print(f"错误: 文件 {dwg_path} 不存在", 'error')
            return
        
        # 检查是否为DWG或DXF文件
        if not (dwg_path.lower().endswith('.dwg') or dwg_path.lower().endswith('.dxf')):
            log_print(f"错误: 文件 {dwg_path} 不是DWG或DXF格式", 'error')
            return
        
        # 如果仅转换
        if args.convert_only and dwg_path.lower().endswith('.dwg'):
            dxf_path = os.path.splitext(dwg_path)[0] + '.dxf'
            log_print(f"仅转换模式: {dwg_path} -> {dxf_path}")
            convert_dwg_to_dxf(dwg_path, dxf_path)
            return
        
        file_output_dir = os.path.join(output_dir, os.path.splitext(os.path.basename(args.file))[0])
        log_print(f"正在处理特定文件: {dwg_path}")
        rooms, extents = extract_rooms_from_dwg(dwg_path, file_output_dir, args.size, args.area)
        return
    
    # 处理目录中的所有DWG文件
    if not os.path.exists(data_dir):
        log_print(f"错误: 目录 {data_dir} 不存在", 'error')
        return
    
    dwg_files = [f for f in os.listdir(data_dir) if f.lower().endswith(('.dwg', '.dxf'))]
    
    if not dwg_files:
        log_print(f"在 {data_dir} 中没有找到DWG或DXF文件", 'warning')
        return
    
    # 处理每个DWG文件
    for dwg_file in dwg_files:
        dwg_path = os.path.join(data_dir, dwg_file)
        file_output_dir = os.path.join(output_dir, os.path.splitext(dwg_file)[0])
        rooms, extents = extract_rooms_from_dwg(dwg_path, file_output_dir, args.size, args.area)

    log_print("=== 房间提取程序运行完成 ===")

if __name__ == "__main__":
    main() 