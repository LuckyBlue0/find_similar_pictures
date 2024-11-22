from PIL import Image
import os
import imagehash
from pathlib import Path
from collections import defaultdict
import sys
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                            QHBoxLayout, QPushButton, QLabel, QScrollArea, 
                            QGridLayout, QCheckBox, QMessageBox, QFileDialog,
                            QProgressDialog, QSlider, QFrame)
from PyQt5.QtGui import QPixmap, QImage
from PyQt5.QtCore import Qt, QTimer

def calculate_image_hash(image_path):
    """计算图片的多重哈希值，包含旋转不变性"""
    try:
        with Image.open(image_path) as img:
            if img.mode != 'RGB':
                img = img.convert('RGB')
            
            # 基础哈希
            phash = imagehash.phash(img)
            dhash = imagehash.dhash(img)
            
            # 计算4个旋转角度的哈希值
            rotations = [
                str(imagehash.average_hash(img)),
                str(imagehash.average_hash(img.rotate(90))),
                str(imagehash.average_hash(img.rotate(180))),
                str(imagehash.average_hash(img.rotate(270)))
            ]
            
            # 水平和垂直翻转的哈希值
            flipped_h = str(imagehash.average_hash(img.transpose(Image.FLIP_LEFT_RIGHT)))
            flipped_v = str(imagehash.average_hash(img.transpose(Image.FLIP_TOP_BOTTOM)))
            
            return {
                'phash': str(phash),
                'dhash': str(dhash),
                'rotations': rotations,
                'flipped_h': flipped_h,
                'flipped_v': flipped_v
            }
    except Exception as e:
        print(f"处理图片 {image_path} 时出错: {str(e)}")
        return None

def calculate_similarity(hash1, hash2):
    """计算考虑旋转和翻转的综合相似度"""
    # 基础哈希相似度
    phash_distance = sum(c1 != c2 for c1, c2 in zip(hash1['phash'], hash2['phash']))
    dhash_distance = sum(c1 != c2 for c1, c2 in zip(hash1['dhash'], hash2['dhash']))
    
    # 计算所有旋转角度的最小距离
    rotation_distances = []
    for rot1 in hash1['rotations']:
        for rot2 in hash2['rotations']:
            dist = sum(c1 != c2 for c1, c2 in zip(rot1, rot2))
            rotation_distances.append(dist)
    min_rotation_distance = min(rotation_distances) if rotation_distances else 0
    
    # 计算翻转的最小距离
    flip_h_distance = sum(c1 != c2 for c1, c2 in zip(hash1['flipped_h'], hash2['flipped_h']))
    flip_v_distance = sum(c1 != c2 for c1, c2 in zip(hash1['flipped_v'], hash2['flipped_v']))
    min_flip_distance = min(flip_h_distance, flip_v_distance)
    
    # 综合加权计算
    weighted_distance = (
        0.4 * phash_distance +      # 感知哈希权重
        0.3 * dhash_distance +      # 差异哈希权重
        0.2 * min_rotation_distance + # 旋转不变性权重
        0.1 * min_flip_distance      # 翻转不变性权重
    )
    
    return weighted_distance

def find_similar_images(folder_path, threshold=4, progress_callback=None):
    """查找相似图片"""
    image_extensions = {'.jpg', '.jpeg', '.png', '.bmp', '.gif'}
    hash_dict = {}
    similar_groups = defaultdict(list)
    
    # 首先计算文件总数用于进度显示
    folder = Path(folder_path)
    image_files = [f for f in folder.rglob('*') if f.suffix.lower() in image_extensions]
    total_files = len(image_files)
    
    # 处理每个文件并更新进度
    for i, image_path in enumerate(image_files):
        if progress_callback:
            progress_callback(i, total_files)
            
        img_hash = calculate_image_hash(image_path)
        if img_hash:
            hash_dict[str(image_path)] = img_hash

    # 查找相似图片
    processed = set()
    for path1, hash1 in hash_dict.items():
        if path1 in processed:
            continue
            
        group = [path1]
        for path2, hash2 in hash_dict.items():
            if path1 != path2 and path2 not in processed:
                similarity = calculate_similarity(hash1, hash2)
                if similarity <= threshold:
                    group.append(path2)
                    processed.add(path2)
        
        if len(group) > 1:
            processed.add(path1)
            similar_groups[hash1['phash']] = group

    return similar_groups

class ImageViewer(QMainWindow):
    def __init__(self, similar_groups):
        super().__init__()
        self.similar_groups = similar_groups
        self.image_widgets = []
        self.checkboxes = []
        
        self.init_ui()
        self.load_all_groups()
        self.center_window()

    def init_ui(self):
        self.setWindowTitle('相似图片查看器')
        self.setGeometry(100, 100, 1200, 800)

        # 创建主窗口部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)

        # 控制按钮区域
        control_layout = QHBoxLayout()
        self.group_label = QLabel(f"共 {len(self.similar_groups)} 组相似图片")
        self.delete_all_button = QPushButton('删除所有选中')

        self.delete_all_button.clicked.connect(self.delete_all_selected)

        control_layout.addWidget(self.group_label)
        control_layout.addStretch()
        control_layout.addWidget(self.delete_all_button)

        layout.addLayout(control_layout)

        # 创建滚动区域
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        layout.addWidget(scroll)

        # 创建图片显示区域
        self.image_widget = QWidget()
        self.image_layout = QVBoxLayout(self.image_widget)  # 使用垂直布局
        scroll.setWidget(self.image_widget)

    def load_all_groups(self):
        # 清除当前显示的图片
        for widget in self.image_widgets:
            widget.setParent(None)
        self.image_widgets.clear()
        self.checkboxes.clear()

        # 遍历所有组
        for group_idx, (_, group) in enumerate(self.similar_groups.items()):
            # 创建组容器
            group_container = QWidget()
            group_layout = QVBoxLayout(group_container)
            
            # 添加组标签
            group_label = QLabel(f"第 {group_idx + 1} 组")
            group_label.setStyleSheet("font-weight: bold; font-size: 14px; padding: 10px;")
            group_layout.addWidget(group_label)
            
            # 创建图片网格布局
            images_grid = QGridLayout()
            row = 0
            col = 0
            max_cols = 3

            for i, img_path in enumerate(group):
                try:
                    # 创建图片容器
                    container = QWidget()
                    container_layout = QVBoxLayout(container)

                    # 加载和显示图片
                    img = Image.open(img_path)
                    img.thumbnail((300, 300))
                    img_qt = img.convert('RGB')
                    height, width = img_qt.size
                    bytes_per_line = 3 * width
                    qt_image = QImage(img_qt.tobytes(), width, height, bytes_per_line, QImage.Format_RGB888)
                    pixmap = QPixmap.fromImage(qt_image)
                    
                    image_label = QLabel()
                    image_label.setPixmap(pixmap)
                    container_layout.addWidget(image_label)

                    # 添加文件名
                    name_label = QLabel(os.path.basename(img_path))
                    name_label.setWordWrap(True)
                    container_layout.addWidget(name_label)

                    # 添加复选框，除第一张图片外都默认选中
                    checkbox = QCheckBox("选择删除")
                    if i > 0:  # 如果不是第一张图片，则默认选中
                        checkbox.setChecked(True)
                    container_layout.addWidget(checkbox)
                    self.checkboxes.append((checkbox, img_path))

                    images_grid.addWidget(container, row, col)
                    self.image_widgets.append(container)

                    col += 1
                    if col >= max_cols:
                        col = 0
                        row += 1

                except Exception as e:
                    print(f"加载图片失败 {img_path}: {str(e)}")

            # 添加分隔线
            group_layout.addLayout(images_grid)
            separator = QFrame()
            separator.setFrameShape(QFrame.HLine)
            separator.setFrameShadow(QFrame.Sunken)
            group_layout.addWidget(separator)
            
            # 将组添加到主布局
            self.image_layout.addWidget(group_container)
            self.image_widgets.append(group_container)

    def delete_all_selected(self):
        """一键删除所有组中选中的图片"""
        # 收集所有选中的图片
        to_delete = []
        for checkbox, path in self.checkboxes:
            if checkbox.isChecked():
                to_delete.append(path)

        if not to_delete:
            QMessageBox.information(self, "提示", "请先选择要删除的图片")
            return

        reply = QMessageBox.question(self, '确认', 
                                   f"确定要删除所有选中 {len(to_delete)} 张图片吗？",
                                   QMessageBox.Yes | QMessageBox.No)

        if reply == QMessageBox.Yes:
            # 删除文件
            for path in to_delete:
                try:
                    os.remove(path)
                    print(f"已删除: {path}")
                except Exception as e:
                    print(f"删除失败 {path}: {str(e)}")

            # 更新所有组
            self.similar_groups = {k: [p for p in v if p not in to_delete] 
                                 for k, v in self.similar_groups.items()}
            # 移除只剩一张图片的组
            self.similar_groups = {k: v for k, v in self.similar_groups.items() if len(v) > 1}

            if not self.similar_groups:
                QMessageBox.information(self, "提示", "所有组都已处理完毕")
                self.close()
            else:
                self.load_all_groups()

    def center_window(self):
        # 获取屏幕几何信息
        screen = QApplication.desktop().screenGeometry()
        # 获取窗口几何信息
        size = self.geometry()
        # 计算居中位置
        x = (screen.width() - size.width()) // 2
        y = (screen.height() - size.height()) // 2
        # 移动窗口
        self.move(x, y)

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.init_ui()
        self.center_window()

    def init_ui(self):
        self.setWindowTitle('相似图片查找器')
        self.setGeometry(100, 100, 400, 300)

        # 创建中央部件和布局
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        layout = QVBoxLayout(central_widget)
        layout.setSpacing(20)

        # 添加说明文本
        label = QLabel('点击下面的按钮选择要扫描的文件夹')
        label.setAlignment(Qt.AlignCenter)
        layout.addWidget(label)

        # 添加阈值选择部分
        threshold_container = QWidget()
        threshold_layout = QHBoxLayout(threshold_container)
        
        threshold_label = QLabel('相似度阈值(1-10):')
        self.threshold_slider = QSlider(Qt.Horizontal)
        self.threshold_slider.setMinimum(1)
        self.threshold_slider.setMaximum(10)
        self.threshold_slider.setValue(4)
        self.threshold_slider.setTickPosition(QSlider.TicksBelow)
        self.threshold_slider.setTickInterval(1)
        
        self.threshold_value_label = QLabel('4')
        self.threshold_slider.valueChanged.connect(self.update_threshold_label)
        
        threshold_layout.addWidget(threshold_label)
        threshold_layout.addWidget(self.threshold_slider)
        threshold_layout.addWidget(self.threshold_value_label)
        
        layout.addWidget(threshold_container)

        # 添加阈值说明
        threshold_desc = QLabel('阈值越小要求越严格（图片越相似）')
        threshold_desc.setAlignment(Qt.AlignCenter)
        layout.addWidget(threshold_desc)

        # 添加选择文件夹按钮
        select_button = QPushButton('选择文件夹')
        select_button.clicked.connect(self.select_folder)
        select_button.setMinimumWidth(120)
        select_button.setMinimumHeight(40)
        layout.addWidget(select_button, alignment=Qt.AlignCenter)

        # 添加状态标签
        self.status_label = QLabel('')
        self.status_label.setAlignment(Qt.AlignCenter)
        layout.addWidget(self.status_label)

        # 添加一些空白空间
        layout.addStretch()

    def center_window(self):
        # 获取屏幕几何信息
        screen = QApplication.desktop().screenGeometry()
        # 获取窗口几何信息
        size = self.geometry()
        # 计算居中位置
        x = (screen.width() - size.width()) // 2
        y = (screen.height() - size.height()) // 2
        # 移动窗口
        self.move(x, y)

    def update_threshold_label(self, value):
        self.threshold_value_label.setText(str(value))

    def select_folder(self):
        folder_path = QFileDialog.getExistingDirectory(
            self,
            "选择要扫描的文件夹",
            "",
            QFileDialog.ShowDirsOnly | QFileDialog.DontResolveSymlinks
        )
        
        if not folder_path:
            return
            
        if not os.path.exists(folder_path):
            QMessageBox.critical(self, "错误", "文件夹不存在！")
            return

        # 创建进度对话框，使用 QString 来处理中文
        progress = QProgressDialog()
        progress.setWindowTitle("扫描进度")
        progress.setLabelText("正在扫描图片...")
        progress.setCancelButtonText("取消")
        progress.setRange(0, 100)
        progress.setWindowModality(Qt.WindowModal)
        progress.setAutoClose(True)
        progress.setMinimumDuration(0)
        
        def update_progress(current, total):
            if progress.wasCanceled():
                return
            percent = int((current / total) * 100)
            progress.setValue(percent)
            QApplication.processEvents()

        # 获取当前选择的阈值
        threshold = self.threshold_slider.value()
        
        # 开始扫描
        similar_groups = find_similar_images(folder_path, threshold=threshold, 
                                          progress_callback=update_progress)
        
        progress.setValue(100)

        if not similar_groups:
            QMessageBox.information(self, "提示", "未找到相似图片。")
            return

        # 显示找到的相似图片数量
        self.status_label.setText(f"找到 {len(similar_groups)} 组相似图片")
        
        # 打开图片查看器
        self.viewer = ImageViewer(similar_groups)
        self.viewer.show()
        # 居中显示图片查看器
        self.viewer.center_window()

def main():
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()
    sys.exit(app.exec_())

if __name__ == "__main__":
    main()
