"""
跑分标签页模块
"""
import os
import uuid
import asyncio
import time
from PyQt6.QtWidgets import (
    QWidget,
    QVBoxLayout,
    QHBoxLayout,
    QGroupBox,
    QLabel,
    QComboBox,
    QPushButton,
    QFormLayout,
    QLineEdit,
    QSplitter,
    QMessageBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QHeaderView,
    QFileDialog,
    QSizePolicy,
    QSpinBox,
    QRadioButton,
    QTextEdit,
    QDialog,
    QDialogButtonBox,
    QCheckBox
)
from PyQt6.QtCore import Qt, QThread, pyqtSignal, QSize, QEventLoop
from PyQt6.QtGui import QFont, QIcon
from src.utils.config import config
from src.utils.logger import setup_logger
from src.gui.i18n.language_manager import LanguageManager
from src.gui.widgets.gpu_monitor import GPUMonitorWidget
from src.gui.widgets.test_progress import TestProgressWidget  # 导入测试进度组件
from src.gui.benchmark_history_tab import BenchmarkHistoryTab
from src.benchmark.integration import benchmark_integration  # 导入跑分模块集成
from src.data.db_manager import db_manager  # 导入数据库管理器
from datetime import datetime

# 设置日志记录器
logger = setup_logger("benchmark_tab")


class BenchmarkThread(QThread):
    """跑分测试线程"""
    progress_updated = pyqtSignal(dict)  # 进度更新信号
    test_finished = pyqtSignal(dict)  # 测试完成信号
    test_error = pyqtSignal(str)  # 测试错误信号
    
    def __init__(self, config):
        super().__init__()
        self.config = config
        self.running = False
        
        # 连接信号
        logger.debug("正在连接benchmark_integration信号到BenchmarkThread")
        
        # 定义进度更新处理函数，添加调试日志
        def on_progress_updated(progress_data):
            logger.debug(f"BenchmarkThread: 收到进度更新，转发信号. 数据键: {list(progress_data.keys() if isinstance(progress_data, dict) else ['非字典数据'])}")
            self.progress_updated.emit(progress_data)
            
        # 定义测试完成处理函数，添加调试日志
        def on_test_finished(result_data):
            logger.debug(f"BenchmarkThread: 收到测试完成信号，转发信号. 数据键: {list(result_data.keys() if isinstance(result_data, dict) else ['非字典数据'])}")
            self.test_finished.emit(result_data)
            
        # 定义测试错误处理函数，添加调试日志
        def on_test_error(error_msg):
            logger.debug(f"BenchmarkThread: 收到测试错误信号，转发信号: {error_msg}")
            self.test_error.emit(error_msg)
        
        # 连接信号
        benchmark_integration.progress_updated.connect(on_progress_updated)
        benchmark_integration.test_finished.connect(on_test_finished)
        benchmark_integration.test_error.connect(on_test_error)
    
    def run(self):
        """运行跑分测试"""
        self.running = True
        logger.debug("BenchmarkThread: 开始执行跑分测试")
        try:
            # 执行跑分测试
            benchmark_integration.run_benchmark(self.config)
            logger.debug("BenchmarkThread: 跑分测试执行完成")
        except Exception as e:
            logger.error(f"BenchmarkThread: 跑分测试错误: {str(e)}")
            if self.running:
                self.test_error.emit(str(e))
        finally:
            self.running = False
            logger.debug("BenchmarkThread: 线程执行完毕")
    
    def stop(self):
        """停止测试"""
        logger.debug("BenchmarkThread: 正在停止测试")
        self.running = False
        benchmark_integration.stop_benchmark()


class BenchmarkTab(QWidget):
    """跑分标签页"""

    def __init__(self):
        super().__init__()
        
        # 获取语言管理器实例
        self.language_manager = LanguageManager()
        
        # 初始化成员变量
        self.benchmark_thread = None
        self.device_id = self._generate_device_id()
        
        # 初始化界面
        self.init_ui()
        
        # 更新界面文本
        self.update_ui_text()
        
        # 不再自动注册设备
        # self._register_device_if_needed()
    
    def _generate_device_id(self):
        """生成设备ID"""
        # 获取设备ID
        device_id = config.get("benchmark.device_id", "")
        if not device_id:
            # 生成新的设备ID
            device_id = str(uuid.uuid4())
            config.set("benchmark.device_id", device_id)
        return device_id
    
    def _register_device_if_needed(self):
        """如果需要，注册设备"""
        # 获取API密钥
        api_key = config.get("benchmark.api_key", "")
        if not api_key and self.mode_select.currentIndex() == 0:  # 联网模式
            # 获取昵称
            nickname = self.nickname_input.text()
            if not nickname:
                nickname = "未命名设备"
            
            # 注册设备
            benchmark_integration.register_device(nickname, self._on_register_result)
    
    def _on_register_result(self, success, message):
        """设备注册结果处理"""
        if success:
            QMessageBox.information(self, "注册成功", message)
        else:
            QMessageBox.warning(self, "注册失败", message)
    
    def init_ui(self):
        """初始化界面"""
        # 创建主布局
        main_layout = QVBoxLayout()
        
        # 创建顶部工具栏
        toolbar_layout = QHBoxLayout()
        
        # 添加跑分基础设置按钮
        self.settings_button = QPushButton("跑分基础设置")
        self.settings_button.clicked.connect(self._show_settings_dialog)
        toolbar_layout.addWidget(self.settings_button)
        
        # 添加访问服务器按钮
        self.server_link_button = QPushButton("visit_server")
        self.server_link_button.clicked.connect(self._open_server_link)
        toolbar_layout.addWidget(self.server_link_button)
        
        # 添加说明标签
        toolbar_layout.addStretch()
        self.status_label = QLabel()
        self._update_status_label()  # 更新状态文本
        toolbar_layout.addWidget(self.status_label)
        
        main_layout.addLayout(toolbar_layout)
        
        # 创建主内容区域
        content_splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # 创建左侧布局（模型选择、数据集选择、并发设置、开始测试按钮）
        left_layout = QVBoxLayout()
        
        # 模型选择
        model_select_group = QGroupBox("模型选择")
        model_select_layout = QHBoxLayout()
        
        # 模型下拉框
        self.model_combo = QComboBox()
        self.model_combo.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        model_select_layout.addWidget(self.model_combo)
        
        # 刷新按钮
        refresh_button = QPushButton("刷新")
        refresh_button.setIcon(QIcon.fromTheme("view-refresh", QIcon(":/icons/refresh.png")))
        refresh_button.setIconSize(QSize(16, 16))
        refresh_button.setCursor(Qt.CursorShape.PointingHandCursor)
        refresh_button.setStyleSheet("""
            QPushButton {
                background-color: #2196F3;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #0b7dda;
            }
            QPushButton:pressed {
                background-color: #0a69b7;
            }
        """)
        refresh_button.clicked.connect(self.load_models)
        model_select_layout.addWidget(refresh_button)
        
        model_select_group.setLayout(model_select_layout)
        left_layout.addWidget(model_select_group)
        
        # 数据集选择
        dataset_group = QGroupBox("数据集选择")
        dataset_layout = QVBoxLayout()
        
        # 添加数据集信息显示区域
        self.dataset_info_text = QTextEdit()
        self.dataset_info_text.setReadOnly(True)
        self.dataset_info_text.setMaximumHeight(120)
        self.dataset_info_text.setPlaceholderText("数据集信息将在这里显示")
        dataset_layout.addWidget(self.dataset_info_text)
        
        # 添加数据集操作按钮
        button_layout = QHBoxLayout()
        
        # 添加获取数据集按钮（联网模式）
        self.dataset_download_button = QPushButton("获取数据集")
        self.dataset_download_button.clicked.connect(self._get_offline_package)  # 直接连接到方法
        button_layout.addWidget(self.dataset_download_button)
        
        # 添加上传数据集按钮（离线模式）
        self.dataset_upload_button = QPushButton("上传数据集")
        self.dataset_upload_button.clicked.connect(self._load_offline_package)
        button_layout.addWidget(self.dataset_upload_button)
        
        dataset_layout.addLayout(button_layout)
        
        # 设置布局
        dataset_group.setLayout(dataset_layout)
        left_layout.addWidget(dataset_group)
        
        # 并发设置
        concurrency_group = QGroupBox("并发设置")
        concurrency_layout = QHBoxLayout()
        
        # 添加并发数输入
        concurrency_layout.addWidget(QLabel("总并发数:"))
        self.concurrency_input = QSpinBox()
        self.concurrency_input.setMinimum(1)
        self.concurrency_input.setMaximum(9999)
        self.concurrency_input.setValue(1)
        concurrency_layout.addWidget(self.concurrency_input)
        
        # 添加运行方式选择
        concurrency_layout.addWidget(QLabel("运行方式:"))
        self.run_mode_group = QHBoxLayout()
        
        self.stream_mode_radio = QRadioButton("流式输出")
        self.stream_mode_radio.setChecked(True)
        self.run_mode_group.addWidget(self.stream_mode_radio)
        
        self.direct_mode_radio = QRadioButton("直接输出")
        self.run_mode_group.addWidget(self.direct_mode_radio)
        
        concurrency_layout.addLayout(self.run_mode_group)
        
        concurrency_group.setLayout(concurrency_layout)
        left_layout.addWidget(concurrency_group)
        
        # 测试控制
        test_control_group = QGroupBox("测试控制")
        test_control_layout = QVBoxLayout()
        
        # 添加开始按钮
        self.start_button = QPushButton("开始跑分测试")
        self.start_button.setIcon(QIcon.fromTheme("media-playback-start", QIcon(":/icons/start.png")))
        self.start_button.setIconSize(QSize(16, 16))
        self.start_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.start_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:pressed {
                background-color: #3d8b40;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.start_button.clicked.connect(self.start_benchmark)
        
        # 添加停止按钮 (替换原有的复选框)
        self.stop_button = QPushButton("停止测试")
        self.stop_button.setIcon(QIcon.fromTheme("media-playback-stop", QIcon(":/icons/stop.png")))
        self.stop_button.setIconSize(QSize(16, 16))
        self.stop_button.setCursor(Qt.CursorShape.PointingHandCursor)
        self.stop_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 4px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #d32f2f;
            }
            QPushButton:pressed {
                background-color: #b71c1c;
            }
            QPushButton:disabled {
                background-color: #cccccc;
                color: #666666;
            }
        """)
        self.stop_button.clicked.connect(self.stop_benchmark)
        self.stop_button.setEnabled(False)  # 初始状态禁用
        
        # 将开始和停止按钮放在同一行
        buttons_layout = QHBoxLayout()
        buttons_layout.addWidget(self.start_button)
        buttons_layout.addWidget(self.stop_button)
        test_control_layout.addLayout(buttons_layout)
        
        test_control_group.setLayout(test_control_layout)
        left_layout.addWidget(test_control_group)
        
        # 创建左侧容器
        left_container = QWidget()
        left_container.setLayout(left_layout)
        
        # 创建右侧布局（GPU监控、测试进度、测试结果）
        right_layout = QVBoxLayout()
        
        # 添加GPU监控
        gpu_monitor_group = QGroupBox("GPU监控")
        gpu_monitor_layout = QVBoxLayout()
        
        # 添加GPU监控组件
        self.gpu_monitor = GPUMonitorWidget()
        gpu_monitor_layout.addWidget(self.gpu_monitor)
        
        gpu_monitor_group.setLayout(gpu_monitor_layout)
        right_layout.addWidget(gpu_monitor_group)
        
        # 添加测试信息 - 使用TestProgressWidget来显示测试进度
        test_info_group = QGroupBox("测试信息")
        test_info_layout = QVBoxLayout()
        
        # 使用TestProgressWidget替换原有的测试进度显示
        self.test_progress_widget = TestProgressWidget()
        test_info_layout.addWidget(self.test_progress_widget)
        
        test_info_group.setLayout(test_info_layout)
        right_layout.addWidget(test_info_group)
        
        # 创建右侧容器
        right_container = QWidget()
        right_container.setLayout(right_layout)
        
        # 添加左右两侧到分割器
        content_splitter.addWidget(left_container)
        content_splitter.addWidget(right_container)
        content_splitter.setSizes([400, 600])  # 设置初始大小
        
        main_layout.addWidget(content_splitter)
        
        # 添加测试结果表格
        result_group = QGroupBox("测试结果")
        result_layout = QVBoxLayout()
        
        # 创建表格
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(8)
        self.result_table.setHorizontalHeaderLabels([
            "数据集", "完成/总数", "成功率", "平均响应时间", "平均生成速度", "总耗时", "总字符数", "平均TPS"
        ])
        self.result_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        result_layout.addWidget(self.result_table)
        
        result_group.setLayout(result_layout)
        main_layout.addWidget(result_group)
        
        # 添加错误信息区域
        error_group = QGroupBox("错误")
        error_layout = QVBoxLayout()
        
        self.error_text = QTextEdit()
        self.error_text.setReadOnly(True)
        self.error_text.setPlaceholderText("测试过程中的错误信息将在此显示...")
        error_layout.addWidget(self.error_text)
        
        error_group.setLayout(error_layout)
        main_layout.addWidget(error_group)
        
        # 设置主布局
        self.setLayout(main_layout)
        
        # 加载模型列表
        self.load_models()
        
        # 初始化UI状态
        self._update_mode_ui()
        
        # 更新状态标签
        self._update_status_label()
    
    def _create_user_config(self):
        """创建用户配置组件"""
        # 创建分组框
        group_box = QGroupBox("用户配置")
        
        # 创建布局
        layout = QFormLayout()
        
        # 添加昵称输入
        self.nickname_input = QLineEdit()
        self.nickname_input.setText(config.get("benchmark.nickname", "未命名设备"))
        self.nickname_input.textChanged.connect(self._on_nickname_changed)
        self.nickname_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # 水平方向自适应
        layout.addRow("设备名称:", self.nickname_input)
        
        # 添加API密钥输入和清除按钮
        api_key_layout = QHBoxLayout()
        
        # API密钥输入框
        self.api_key_input = QLineEdit()
        self.api_key_input.setEchoMode(QLineEdit.EchoMode.Password)  # 密码模式，不显示明文
        
        # 如果配置中有API密钥，显示在输入框中
        saved_api_key = config.get("benchmark.api_key", "")
        if saved_api_key:
            self.api_key_input.setText(saved_api_key)
            self.api_key_input.setPlaceholderText("")
        else:
            self.api_key_input.setPlaceholderText("请输入API密钥")
        
        self.api_key_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # 水平方向自适应
        # 确保API密钥输入框默认是启用的，并添加特殊样式使其看起来始终可编辑
        self.api_key_input.setEnabled(True)
        self.api_key_input.setStyleSheet("QLineEdit { background-color: white; color: black; }")
        self.api_key_input.setReadOnly(False)  # 确保不是只读的
        api_key_layout.addWidget(self.api_key_input)
        
        # 添加清除按钮
        clear_button = QPushButton("清除")
        clear_button.setFixedWidth(60)  # 设置固定宽度
        clear_button.setCursor(Qt.CursorShape.PointingHandCursor)
        clear_button.setStyleSheet("""
            QPushButton {
                background-color: #f44336;
                color: white;
                border: none;
                padding: 4px 8px;
                border-radius: 4px;
            }
            QPushButton:hover {
                background-color: #e53935;
            }
            QPushButton:pressed {
                background-color: #d32f2f;
            }
        """)
        # 点击时清空API密钥输入框并清除配置中的API密钥
        clear_button.clicked.connect(self._clear_api_key)
        api_key_layout.addWidget(clear_button)
        
        # 将API密钥布局添加到表单
        layout.addRow("API密钥:", api_key_layout)
        
        # 添加模式选择
        self.mode_select = QComboBox()
        self.mode_select.addItem("联网模式")
        self.mode_select.addItem("离线模式")
        self.mode_select.setCurrentIndex(config.get("benchmark.mode", 0))  # 根据配置设置默认值
        self.mode_select.currentIndexChanged.connect(self._on_mode_changed)
        layout.addRow("运行模式:", self.mode_select)
        
        # 添加控制按钮
        button_layout = QHBoxLayout()
        
        # 创建启用跑分模块按钮
        self.enable_button = QPushButton("启用跑分模块")
        self.enable_button.clicked.connect(self._enable_benchmark_module)
        button_layout.addWidget(self.enable_button)
        
        # 创建禁用跑分模块按钮
        self.disable_button = QPushButton("禁用跑分模块")
        self.disable_button.clicked.connect(self._disable_benchmark_module)
        button_layout.addWidget(self.disable_button)
        
        # 添加按钮布局到表单
        layout.addRow("", button_layout)
        
        # 设置布局
        group_box.setLayout(layout)
        
        return group_box
    
    def _create_dataset_manager(self):
        """创建数据集管理器部分"""
        # 创建数据集管理器组
        dataset_group = QGroupBox("数据集管理")
        layout = QVBoxLayout()
        
        # 创建按钮布局
        button_layout = QHBoxLayout()
        
        # 创建获取数据集按钮
        self.dataset_download_button = QPushButton("获取数据集")
        self.dataset_download_button.clicked.connect(self._get_offline_package)  # 直接连接到方法
        button_layout.addWidget(self.dataset_download_button)
        
        # 添加上传数据集按钮（离线模式）
        self.dataset_upload_button = QPushButton("上传数据集")
        self.dataset_upload_button.clicked.connect(self._load_offline_package)
        button_layout.addWidget(self.dataset_upload_button)
        
        layout.addLayout(button_layout)
        
        # 设置布局
        dataset_group.setLayout(layout)
        
        # 根据当前模式更新按钮显示状态
        self._update_dataset_buttons()
        
        return dataset_group
    
    def _create_model_config(self):
        """创建模型配置组件"""
        # 创建分组框
        group_box = QGroupBox("模型配置")
        
        # 创建布局
        layout = QFormLayout()
        
        # 添加精度选择
        self.precision_combo = QComboBox()
        self.precision_combo.addItem("FP32")
        self.precision_combo.addItem("FP16")
        self.precision_combo.addItem("INT8")
        layout.addRow("精度:", self.precision_combo)
        
        # 添加参数量输入
        self.params_input = QLineEdit()
        self.params_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # 水平方向自适应
        layout.addRow("参数量(M):", self.params_input)
        
        # 添加框架配置输入
        self.framework_input = QLineEdit()
        self.framework_input.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)  # 水平方向自适应
        layout.addRow("框架配置:", self.framework_input)
        
        # 添加按钮
        button_layout = QHBoxLayout()
        self.model_config_button = QPushButton("保存配置")
        button_layout.addWidget(self.model_config_button)
        layout.addRow("", button_layout)
        
        # 设置布局
        group_box.setLayout(layout)
        
        return group_box
    
    def _enable_benchmark_module(self):
        """启用跑分模块"""
        # 禁用按钮，防止重复点击
        self.enable_button.setEnabled(False)
        self.enable_button.setText("正在启用...")
        
        # 获取昵称
        nickname = self.nickname_input.text()
        if not nickname:
            nickname = "未命名设备"
        
        # 获取API密钥
        api_key = self.api_key_input.text()
        
        # 保存配置
        config.set("benchmark.nickname", nickname)
        config.set("benchmark.mode", self.mode_select.currentIndex())
        
        # 验证API密钥
        if not api_key:
            QMessageBox.warning(self, "警告", "请输入API密钥")
            self.enable_button.setEnabled(True)
            self.enable_button.setText("启用跑分模块")
            return
        
        # 保存API密钥到配置
        config.set("benchmark.api_key", api_key)
        # 设置API密钥到benchmark_integration
        benchmark_integration.set_api_key(api_key, self.device_id, nickname)
        
        # 设置跑分模块已启用标志
        config.set("benchmark.enabled", True)
        
        # 更新状态标签
        self._update_status_label()
        
        # 更新模式UI
        self._update_mode_ui()
        
        # 显示成功消息
        QMessageBox.information(self, "成功", "跑分模块已启用")
        
        # 恢复按钮状态
        self.enable_button.setEnabled(True)
        self.enable_button.setText("启用跑分模块")
    
    def _disable_benchmark_module(self):
        """禁用跑分模块"""
        # 禁用按钮，防止重复点击
        self.disable_button.setEnabled(False)
        self.disable_button.setText("正在禁用...")
        
        # 禁用跑分模块
        benchmark_integration.disable_benchmark_module(self._on_disable_result)
    
    def _on_disable_result(self, success, message):
        """禁用跑分模块结果处理"""
        # 恢复按钮状态
        self.disable_button.setEnabled(True)
        self.disable_button.setText("禁用跑分模块")
        
        if success:
            # 设置跑分模块已禁用标志
            config.set("benchmark.enabled", False)
            # 更新状态标签
            self._update_status_label()
            # 更新模式UI
            self._update_mode_ui()
            # 显示成功消息
            QMessageBox.information(self, "成功", message)
        else:
            # 显示错误消息
            QMessageBox.warning(self, "警告", message)
    
    def load_models(self):
        """加载模型列表"""
        try:
            # 清空模型下拉框
            self.model_combo.clear()
            
            # 从数据库中加载模型列表而不是从配置中加载
            from src.data.db_manager import db_manager
            models = db_manager.get_model_configs()
            for model in models:
                if "name" in model:
                    self.model_combo.addItem(model["name"])
            
            logger.info(f"加载了 {self.model_combo.count()} 个模型")
        except Exception as e:
            logger.error(f"加载模型列表失败: {str(e)}")
    
    def get_selected_model(self) -> dict:
        """获取选中的模型配置"""
        if self.model_combo.count() == 0 or self.model_combo.currentIndex() < 0:
            return {}
        
        # 获取选中的模型名称
        model_name = self.model_combo.currentText()
        
        # 从数据库中获取模型信息而不是从配置中获取
        from src.data.db_manager import db_manager
        models = db_manager.get_model_configs()
        model = next((m for m in models if m["name"] == model_name), None)
        
        # 如果没有找到匹配的模型，返回基本信息
        return model if model else {"name": model_name}
    
    def _on_nickname_changed(self, text):
        """昵称变更处理"""
        config.set("benchmark.nickname", text)
    
    def _on_mode_changed(self):
        """
        当运行模式改变时的处理函数
        """
        # 获取当前模式
        mode = config.get("benchmark.mode", 0)  # 0=联网模式，1=离线模式
        
        # 更新UI状态
        self._update_mode_ui()
    
    def _update_mode_ui(self):
        """根据模式更新UI"""
        mode = self.mode_select.currentIndex() if hasattr(self, 'mode_select') else config.get("benchmark.mode", 0)
        is_enabled = config.get("benchmark.enabled", True)
        api_key = config.get("benchmark.api_key", "")
        
        can_test = bool(is_enabled and (mode == 1 or (mode == 0 and api_key)))
        self.start_button.setEnabled(can_test)
        self.stop_button.setEnabled(can_test)
    
    def _update_status_label(self):
        """更新状态标签"""
        # 获取设备ID和模式
        device_id = self.device_id
        mode = self.mode_select.currentIndex() if hasattr(self, 'mode_select') else config.get("benchmark.mode", 0)
        api_key = config.get("benchmark.api_key", "")
        is_enabled = config.get("benchmark.enabled", True)
        
        # 构建状态文本
        if is_enabled:
            if mode == 0:  # 联网模式
                if api_key:
                    status_text = f"跑分模式: 已启用 | API密钥: 已配置 | 运行模式: 联网模式"
                else:
                    status_text = f"跑分模式: 已启用 | API密钥: 未配置 | 运行模式: 联网模式"
            else:  # 离线模式
                status_text = f"跑分模式: 已启用 | 运行模式: 离线模式"
        else:
            status_text = "跑分模式: 未启用"
        
        # 设置状态文本
        self.status_label.setText(status_text)
    
    def _clear_api_key(self):
        """清除API密钥"""
        # 清空输入框
        self.api_key_input.clear()
        
        # 清除配置中的API密钥
        config.set("benchmark.api_key", "")
        
        # 如果已经设置了API密钥到benchmark_integration，也需要清除
        if hasattr(self, 'benchmark_integration') and hasattr(benchmark_integration, 'set_api_key'):
            benchmark_integration.set_api_key("", self.device_id, self.nickname_input.text())
        
        # 更新状态标签
        self._update_status_label()
        
        # 显示提示消息
        QMessageBox.information(self, "成功", "API密钥已清除") 

    def _get_offline_package(self):
        """获取离线测试数据包"""
        try:
            # 检查API密钥
            api_key = config.get("benchmark.api_key")
            logger.debug(f"当前API密钥状态: {'已设置' if api_key else '未设置'}")
            if not api_key:
                QMessageBox.warning(self, "错误", "请先配置API密钥")
                return
            
            # 禁用按钮
            self.dataset_download_button.setEnabled(False)
            self.dataset_download_button.setText("正在获取...")
            
            # 重置状态
            if hasattr(benchmark_integration, 'running') and benchmark_integration.running:
                logger.warning("有正在进行的操作，先停止它")
                benchmark_integration.stop_benchmark()
            
            # 定义回调函数
            def on_package_received(success: bool, message: str = None, package: dict = None):
                try:
                    # 恢复按钮状态
                    self.dataset_download_button.setEnabled(True)
                    self.dataset_download_button.setText("获取数据集")
                    
                    if success:
                        logger.info(f"离线包获取成功，开始解密流程")
                        if package:
                            logger.debug(f"离线包内容: {package.keys() if isinstance(package, dict) else type(package)}")
                        
                        # 更新数据集信息显示
                        self._update_dataset_info_display()
                        
                        # 检查数据集是否成功加载
                        dataset_info = benchmark_integration.get_dataset_info()
                        logger.debug(f"数据集信息: {dataset_info if isinstance(dataset_info, dict) else type(dataset_info)}")
                        
                        # 判断数据集是否加载成功（兼容返回布尔值或字典的情况）
                        if dataset_info and (isinstance(dataset_info, dict) or dataset_info is True):
                            QMessageBox.information(self, "获取成功", "数据集获取并解密成功")
                            # 启用开始测试按钮
                            self.start_button.setEnabled(True)
                        else:
                            QMessageBox.warning(self, "解密失败", "数据集获取成功但解密失败，请检查API密钥是否正确")
                    else:
                        error_msg = message or "未知错误"
                        logger.error(f"离线包获取失败: {error_msg}")
                        QMessageBox.warning(self, "获取失败", error_msg)
                except Exception as e:
                    logger.error(f"回调处理异常: {str(e)}")
                    QMessageBox.warning(self, "处理失败", f"数据处理失败: {str(e)}")
                finally:
                    # 确保按钮状态恢复
                    self.dataset_download_button.setEnabled(True)
                    self.dataset_download_button.setText("获取数据集")
            
            # 发起获取离线包请求
            logger.info(f"开始获取离线包，使用API密钥: {api_key[:4]}...")
            # 调用benchmark_integration获取离线包方法，传入ID为1的数据集（默认数据集）
            benchmark_integration.get_offline_package(1, on_package_received)
        
        except Exception as e:
            logger.error(f"获取离线包出错: {str(e)}")
            QMessageBox.warning(self, "错误", f"获取离线包失败: {str(e)}")
            # 确保按钮状态恢复
            self.dataset_download_button.setEnabled(True)
            self.dataset_download_button.setText("获取数据集")

    def _load_offline_package(self):
        """加载离线包"""
        try:
            # 检查API密钥
            api_key = config.get("benchmark.api_key", "")
            if not api_key:
                QMessageBox.warning(self, "错误", "请先配置API密钥")
                return
            
            # 打开文件选择对话框
            file_path, _ = QFileDialog.getOpenFileName(
                self,
                "选择离线包文件",
                "",
                "JSON文件 (*.json);;所有文件 (*)"
            )
            
            if not file_path:
                return
            
            # 禁用按钮，防止重复点击
            self.dataset_upload_button.setEnabled(False)
            self.dataset_upload_button.setText("正在加载...")
            
            # 定义回调函数
            def on_package_loaded(success: bool, message: str):
                # 恢复按钮状态
                self.dataset_upload_button.setEnabled(True)
                self.dataset_upload_button.setText("上传数据集")
                
                if success:
            # 更新数据集信息显示
                    self._update_dataset_info_display()
                    QMessageBox.information(self, "加载成功", "数据集加载成功")
                else:
                    QMessageBox.warning(self, "加载失败", message)
            
            # 加载离线包
            benchmark_integration.load_offline_package(file_path, callback=on_package_loaded)
            
        except Exception as e:
            # 恢复按钮状态
            self.dataset_upload_button.setEnabled(True)
            self.dataset_upload_button.setText("上传数据集")
            
            error_msg = str(e)
            logger.error(f"加载数据集错误: {error_msg}")
            QMessageBox.warning(self, "加载失败", f"数据集加载失败: {error_msg}")

    def _update_dataset_info_display(self):
        """更新数据集信息显示"""
        dataset_info = benchmark_integration.get_dataset_info()
        if not dataset_info:
            self.dataset_info_text.setText("未加载数据集")
            return
        
        logger.debug(f"更新数据集信息显示，数据集信息: {dataset_info}")
        
        # 构建信息文本
        info_text = ""
        
        # 获取元数据信息
        metadata = dataset_info.get('metadata', {})
        logger.debug(f"元数据信息: {metadata}")
        
        # 获取文件大小 - 使用实际大小或元数据中的大小
        file_size = dataset_info.get('size', 0)
        logger.debug(f"文件大小: {file_size} 字节")
        
        # 计算并格式化数据集大小
        dataset_size = file_size / 1024  # 转换为KB
        size_text = f"{dataset_size:.2f} KB" if dataset_size < 1024 else f"{dataset_size/1024:.2f} MB"
        
        # 处理下载时间
        download_time = metadata.get('download_time', int(time.time() * 1000))
        download_time_str = datetime.fromtimestamp(download_time/1000).strftime('%Y-%m-%d %H:%M:%S')
        
        # 获取离线包格式版本
        package_format = metadata.get('package_format', '3.0')
        
        # 构建信息文本
        info_text = "数据集信息:\n"
        info_text += f"dataset_name: {metadata.get('dataset_name', dataset_info.get('名称', '未知'))}\n"
        info_text += f"dataset_version: {metadata.get('dataset_version', dataset_info.get('版本', '未知'))}\n"
        info_text += f"package_format: {package_format}\n"
        info_text += f"download_time: {download_time_str}\n"
        info_text += f"大小: {size_text}\n"
        
        # 添加记录数
        if "记录数" in dataset_info:
            info_text += f"记录数: {dataset_info['记录数']}\n"
        
        # 添加描述
        if "描述" in dataset_info:
            info_text += f"描述: {dataset_info['描述']}\n"
        
        # 添加创建时间
        if "created_at" in dataset_info:
            # 尝试格式化ISO时间字符串
            try:
                created_at = dataset_info["created_at"]
                if isinstance(created_at, str) and 'T' in created_at:
                    # ISO格式的日期时间
                    date_part = created_at.split('T')[0]
                    time_part = created_at.split('T')[1].split('.')[0] if '.' in created_at.split('T')[1] else created_at.split('T')[1]
                    info_text += f"创建时间: {date_part} {time_part}\n"
                else:
                    info_text += f"创建时间: {created_at}\n"
            except:
                info_text += f"创建时间: {dataset_info.get('created_at', '未知')}\n"
        
        # 添加到期时间
        if "expires_at" in dataset_info:
            # 尝试格式化ISO时间字符串
            try:
                expires_at = dataset_info["expires_at"]
                if isinstance(expires_at, str) and 'T' in expires_at:
                    # ISO格式的日期时间
                    date_part = expires_at.split('T')[0]
                    time_part = expires_at.split('T')[1].split('.')[0] if '.' in expires_at.split('T')[1] else expires_at.split('T')[1]
                    info_text += f"到期时间: {date_part} {time_part}\n"
                else:
                    info_text += f"到期时间: {expires_at}\n"
            except:
                info_text += f"到期时间: {dataset_info.get('expires_at', '未知')}\n"
        
        # 设置信息文本
        self.dataset_info_text.setText(info_text)
        
        # 启用数据集相关按钮
        self._update_dataset_buttons()

    def _on_test_start(self):
        """
        开始测试时的处理函数
        """
        # 获取当前模式
        mode = config.get("benchmark.mode", 0)  # 0=联网模式，1=离线模式
        
        # 检查API密钥
        if mode == 0 and not config.get("benchmark.api_key"):
            QMessageBox.warning(self, "警告", "联网模式下需要配置API密钥")
            return
        
        # 其他代码保持不变...
    
    def start_benchmark(self):
        """
        开始基准测试
        """
        logger.debug("开始基准测试")
        
        # 检查数据集是否已加载
        dataset_info = benchmark_integration.get_dataset_info()
        if not dataset_info:
            QMessageBox.warning(self, "错误", "请先获取或上传数据集")
            return
        
        # 检查是否选择了模型
        if not self.model_combo.currentText():
            QMessageBox.warning(self, "错误", "请选择要测试的模型")
            return
        
        # 获取模型配置
        model_name = self.model_combo.currentText()
        model_config = self.get_selected_model()
        
        # 获取并验证并发数
        try:
            concurrency = int(self.concurrency_input.text())
            if concurrency < 1:
                raise ValueError("并发数必须大于0")
        except ValueError as e:
            QMessageBox.warning(self, "错误", f"并发数设置错误: {str(e)}")
            return
        
        # 构建测试配置
        config_dict = {
            "model_name": model_name,
            "model": model_config.get("model", model_name),  # 添加model字段，优先使用model_config中的model值，如果没有则使用model_name
            "precision": model_config.get("precision", "FP16"),
            "model_params": model_config.get("params", {}),
            "concurrency": concurrency,
            "timeout": int(config.get("test.timeout", 30)),
            "retry_count": int(config.get("test.retry_count", 1))
        }
        
        # 添加API URL
        if "api_url" in model_config:
            config_dict["api_url"] = model_config["api_url"]
        elif "api_url" in model_config.get("framework_config", {}):
            config_dict["api_url"] = model_config["framework_config"]["api_url"]
        else:
            # 如果模型配置中没有API URL，显示错误消息
            QMessageBox.warning(self, "错误", "所选模型缺少API URL配置")
            self.start_button.setEnabled(True)
            self.stop_button.setEnabled(False)
            return
        
        # 更新UI状态
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.status_label.setText("测试状态: 正在进行")
        self.test_progress_widget.progress_bar.setValue(0)
        
        # 清空结果表格
        self.result_table.setRowCount(0)
        
        # 创建并启动测试线程
        self.benchmark_thread = BenchmarkThread(config_dict)
        self.benchmark_thread.progress_updated.connect(self._on_progress_updated)
        self.benchmark_thread.test_finished.connect(self._on_test_finished)
        self.benchmark_thread.test_error.connect(self._on_test_error)
        self.benchmark_thread.start()
        
        logger.debug(f"基准测试线程已启动，配置: {config_dict}")
    
    def stop_benchmark(self):
        """
        停止基准测试
        """
        logger.debug("停止基准测试")
        
        if hasattr(self, 'benchmark_thread') and self.benchmark_thread.isRunning():
            self.benchmark_thread.stop()
            logger.debug("已发送停止信号到测试线程")
        
        # 更新UI状态
        self.status_label.setText("测试状态: 已停止")
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
    
    def _on_progress_updated(self, progress_data):
        """
        处理进度更新
        
        Args:
            progress_data: 进度数据字典
        """
        logger.debug(f"收到进度更新: {list(progress_data.keys() if isinstance(progress_data, dict) else ['非字典数据'])}")
        
        try:
            # 检查进度数据是否有效
            if not isinstance(progress_data, dict):
                logger.error(f"进度数据类型错误: {type(progress_data)}")
                return
            
            # 获取状态信息
            status = progress_data.get("status", "测试进行中")
            
            # 更新状态标签
            self.status_label.setText(f"测试状态: {status}")
            
            # 处理数据集进度
            if "datasets" in progress_data and progress_data["datasets"]:
                datasets = progress_data["datasets"]
                
                # 清空结果表格
                self.result_table.setRowCount(0)
                
                # 总进度计算变量
                total_completed = 0
                total_items = 0
                
                # 遍历所有数据集
                for dataset_name, dataset_data in datasets.items():
                    # 获取数据集进度信息
                    completed = dataset_data.get("completed", 0)
                    total = dataset_data.get("total", 0)
                    success_rate = dataset_data.get("success_rate", 0)
                    avg_response_time = dataset_data.get("avg_response_time", 0)
                    avg_generation_speed = dataset_data.get("avg_generation_speed", 0)
                    total_time = dataset_data.get("total_time", 0)
                    total_duration = dataset_data.get("total_duration", 0)  # 新增字段
                    
                    # 使用可用的耗时字段
                    duration = total_duration if total_duration > 0 else total_time
                    
                    # 累计总进度
                    total_completed += completed
                    total_items += total if total > 0 else 0
                    
                    # 格式化值
                    success_rate_text = f"{success_rate:.2f}%" if isinstance(success_rate, (int, float)) else str(success_rate)
                    avg_response_time_text = f"{avg_response_time:.2f}s" if isinstance(avg_response_time, (int, float)) else str(avg_response_time)
                    avg_generation_speed_text = f"{avg_generation_speed:.2f} token/s" if isinstance(avg_generation_speed, (int, float)) else str(avg_generation_speed)
                    
                    # 格式化耗时
                    if isinstance(duration, (int, float)):
                        if duration < 60:
                            duration_text = f"{duration:.2f}秒"
                        elif duration < 3600:
                            minutes = int(duration / 60)
                            seconds = duration % 60
                            duration_text = f"{minutes}分{seconds:.2f}秒"
                        else:
                            hours = int(duration / 3600)
                            minutes = int((duration % 3600) / 60)
                            seconds = duration % 60
                            duration_text = f"{hours}时{minutes}分{seconds:.2f}秒"
                    else:
                        duration_text = str(duration)
                    
                    # 添加到结果表格
                    row = self.result_table.rowCount()
                    self.result_table.insertRow(row)
                    
                    # 设置表格内容
                    self.result_table.setItem(row, 0, QTableWidgetItem(dataset_name))
                    self.result_table.setItem(row, 1, QTableWidgetItem(f"{completed}/{total}"))
                    self.result_table.setItem(row, 2, QTableWidgetItem(success_rate_text))
                    self.result_table.setItem(row, 3, QTableWidgetItem(avg_response_time_text))
                    self.result_table.setItem(row, 4, QTableWidgetItem(avg_generation_speed_text))
                    self.result_table.setItem(row, 5, QTableWidgetItem(duration_text))
                
                # 计算总进度百分比
                if total_items > 0:
                    percentage = int((total_completed / total_items) * 100)
                    # 更新进度条
                    self.test_progress_widget.progress_bar.setValue(percentage)
                    # 更新进度文本
                    self.test_progress_widget.status_label.setText(f"进度: {percentage}% ({total_completed}/{total_items})")
                    
                    # 更新详细信息
                    detail_text = f"完成测试项: {total_completed}/{total_items}\n"
                    detail_text += f"状态: {status}\n"
                    self.test_progress_widget.detail_text.setText(detail_text)
            
            # 处理可能的错误信息
            if "error" in progress_data:
                error_msg = progress_data["error"]
                self.error_text.append(f"错误: {error_msg}")
            
            # 确保UI更新
            from PyQt6.QtWidgets import QApplication
            QApplication.processEvents()
            
        except Exception as e:
            logger.error(f"处理进度更新时出错: {str(e)}")
            self.error_text.append(f"处理进度更新错误: {str(e)}")
    
    def _on_test_finished(self, result):
        """
        测试完成时的处理函数
        """
        # 获取当前模式
        mode = config.get("benchmark.mode", 0)  # 0=联网模式，1=离线模式
        
        # 更新UI状态
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("测试状态: 已完成")
        
        # 确保进度条显示100%
        self.test_progress_widget.progress_bar.setValue(100)
        
        # 记录测试完成日志
        logger.info("基准测试完成")
        
        # 显示完成消息
        QMessageBox.information(self, "测试完成", "基准测试已完成")
    
    def _on_test_error(self, error_msg):
        """
        测试错误处理函数
        
        Args:
            error_msg: 错误信息
        """
        logger.error(f"测试错误: {error_msg}")
        
        # 更新UI状态
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self.status_label.setText("测试状态: 出错")
        
        # 添加错误信息到错误文本框
        self.error_text.append(f"错误: {error_msg}")
        
        # 显示错误消息
        error_title = "测试错误"
        error_detail = ""
        
        # 判断错误信息类型
        if isinstance(error_msg, dict):
            # 如果是字典类型，提取ui_message字段作为显示信息
            error_content = error_msg.get("ui_message", str(error_msg))
            error_detail = error_msg.get("ui_detail", "")
        else:
            # 如果是字符串类型，直接显示
            error_content = str(error_msg)
        
        # 显示错误消息对话框
        error_dialog = QMessageBox(self)
        error_dialog.setIcon(QMessageBox.Icon.Critical)
        error_dialog.setWindowTitle(error_title)
        error_dialog.setText(error_content)
        
        if error_detail:
            error_dialog.setDetailedText(error_detail)
        
        error_dialog.exec()

    def save_config(self):
        """
        保存配置
        """
        # 保存当前模式
        mode = config.get("benchmark.mode", 0)  # 0=联网模式，1=离线模式
        config.set("benchmark.mode", mode)
        
        # 其他代码保持不变... 

    def _open_server_link(self):
        """打开服务器网站"""
        try:
            import webbrowser
            server_url = config.get("benchmark.server_url", "http://localhost:8083")
            # 确保URL以http://或https://开头
            if not server_url.startswith("http://") and not server_url.startswith("https://"):
                server_url = "http://" + server_url
            webbrowser.open(server_url)
            logger.info(f"已打开服务器网站: {server_url}")
        except Exception as e:
            logger.error(f"打开服务器网站失败: {str(e)}")
            QMessageBox.critical(self, "错误", f"打开服务器网站失败: {str(e)}")

    def _show_settings_dialog(self):
        """显示用户配置对话框"""
        # 创建对话框
        dialog = QDialog(self)
        dialog.setWindowTitle("跑分基础设置")
        dialog.setMinimumWidth(400)
        
        # 创建布局
        layout = QVBoxLayout(dialog)
        
        # 创建用户配置组件
        user_config = self._create_user_config()
        layout.addWidget(user_config)
        
        # 添加确定按钮
        button_box = QDialogButtonBox(QDialogButtonBox.StandardButton.Ok)
        button_box.accepted.connect(dialog.accept)
        layout.addWidget(button_box)
        
        # 确保API密钥输入框是启用的
        # 在对话框中查找API密钥输入框和清除按钮
        api_key_inputs = dialog.findChildren(QLineEdit)
        clear_buttons = dialog.findChildren(QPushButton)
        
        # 找到API密钥输入框
        api_key_input = None
        for input_field in api_key_inputs:
            if input_field.placeholderText() == "请输入API密钥" or config.get("benchmark.api_key", ""):
                api_key_input = input_field
                api_key_input.setEnabled(True)
                api_key_input.setStyleSheet("QLineEdit { background-color: white; color: black; }")
                api_key_input.setReadOnly(False)
                break
        
        # 找到清除按钮并重新连接信号
        if api_key_input:
            for button in clear_buttons:
                if button.text() == "清除":
                    # 断开所有现有连接
                    try:
                        button.clicked.disconnect()
                    except:
                        pass
                    
                    # 创建一个新的清除函数，在对话框中使用
                    def clear_api_key_in_dialog():
                        # 清空输入框
                        api_key_input.clear()
                        
                        # 清除配置中的API密钥
                        config.set("benchmark.api_key", "")
                        
                        # 如果已经设置了API密钥到benchmark_integration，也需要清除
                        if hasattr(benchmark_integration, 'set_api_key'):
                            benchmark_integration.set_api_key("", self.device_id, self.nickname_input.text())
                        
                        # 更新状态标签
                        self._update_status_label()
                        
                        # 显示提示消息
                        QMessageBox.information(dialog, "成功", "API密钥已清除")
                    
                    # 连接新的清除函数
                    button.clicked.connect(clear_api_key_in_dialog)
                    break
        
        # 显示对话框
        dialog.exec()

    def _update_dataset_buttons(self):
        """根据当前模式更新按钮显示状态"""
        mode = config.get("benchmark.mode", 0)  # 0=联网模式，1=离线模式
        self.dataset_download_button.setEnabled(mode == 0)
        self.dataset_upload_button.setEnabled(mode == 1)

    def update_ui_text(self):
        """更新UI文本"""
        # 更新按钮文本
        self.start_button.setText("开始测试")
        self.stop_button.setText("停止测试")
        self.settings_button.setText("设置")
        self.server_link_button.setText("打开服务器")
        
        # 更新标签文本
        if hasattr(self, 'model_label'):
            self.model_label.setText("选择模型:")
        if hasattr(self, 'concurrency_label'):
            self.concurrency_label.setText("并发数:")
        if hasattr(self, 'dataset_label'):
            self.dataset_label.setText("数据集:")
        
        # 更新数据集按钮
        if hasattr(self, 'dataset_download_button'):
            self.dataset_download_button.setText("获取数据集")
        if hasattr(self, 'dataset_upload_button'):
            self.dataset_upload_button.setText("上传数据集")
        
        # 更新模式选择
        if hasattr(self, 'mode_select'):
            # 保存当前索引
            current_index = self.mode_select.currentIndex()
            # 清空并重新添加项目
            self.mode_select.clear()
            self.mode_select.addItem("联网模式")
            self.mode_select.addItem("离线模式")
            # 恢复之前的选择
            if current_index >= 0 and current_index < self.mode_select.count():
                self.mode_select.setCurrentIndex(current_index)
        
        # 更新启用/禁用按钮
        if hasattr(self, 'enable_button'):
            self.enable_button.setText("启用")
        if hasattr(self, 'disable_button'):
            self.disable_button.setText("禁用")
        
        # 更新表格头
        if hasattr(self, 'result_table'):
            self.result_table.setHorizontalHeaderLabels([
                "数据集",
                "完成数",
                "总数",
                "成功率",
                "平均响应时间",
                "平均生成速度",
                "总时间"
            ])

    def _on_test_start(self):
        """
        开始测试时的处理函数
        """
        # 获取当前模式
        mode = config.get("benchmark.mode", 0)  # 0=联网模式，1=离线模式
        
        # 检查API密钥
        if mode == 0 and not config.get("benchmark.api_key"):
            QMessageBox.warning(self, "警告", "联网模式下需要配置API密钥")
            return
        
        # 其他代码保持不变...
    
    def _on_test_finished(self, result):
        """
        测试完成时的处理函数
        """
        # 获取当前模式
        mode = config.get("benchmark.mode", 0)  # 0=联网模式，1=离线模式
        
        # 其他代码保持不变... 