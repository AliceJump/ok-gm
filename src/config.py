import os

import numpy as np
from ok import ConfigOption
from src.interaction.EfInteraction import EfInteraction
from src.dmm.launcher import resolve_game_exe
from src.dmm.xray import NODE_ENABLED_KEY
version = "dev"
#不需要修改version, Github Action打包会自动修改

VPN_CONFIG_NAME = "VPN 设置"
VPN_START_PATH_KEY = "VPN启动路径"
VPN_WORKING_DIRECTORY_KEY = "VPN工作目录"
DMM_CONFIG_NAME = "DMM 启动助手"
DMM_ENABLED_KEY = "使用本地助手"
DMM_PROXY_KEY = "本地代理入口"
DMM_AUTO_UPDATE_KEY = "自动更新游戏"

dmm_config_option = ConfigOption(
    DMM_CONFIG_NAME,
    {
        DMM_ENABLED_KEY: True,
        DMM_PROXY_KEY: "http://127.0.0.1:10808",
        DMM_AUTO_UPDATE_KEY: True,
        NODE_ENABLED_KEY: False,
    },
    description="通过本地代理获取有效登录凭证、校验更新并启动游戏",
    config_description={
        DMM_ENABLED_KEY: "自动使用保存的登录态检查更新并启动游戏；登录与下载操作在「游戏启动器」页面进行。",
        DMM_PROXY_KEY: "本地 HTTP 代理地址；需在 v2rayN 选择日本节点并确认 DMM 域名分流。",
        DMM_AUTO_UPDATE_KEY: "下载并校验官方游戏文件后替换；下载中断后可续传。",
        NODE_ENABLED_KEY: "使用加密保存的节点配置运行独立 Xray，不随 v2rayN 的节点切换而改变。",
    },
)

vpn_config_option = ConfigOption(
    VPN_CONFIG_NAME,
    {
        VPN_START_PATH_KEY: r"D:\Programs\v2rayn\v2rayN.exe",
        VPN_WORKING_DIRECTORY_KEY: r"D:\Programs\v2rayn",
    },
    description="启动游戏前自动启动 VPN 客户端",
    config_description={
        VPN_START_PATH_KEY: "VPN 客户端可执行文件的完整路径；留空则不启动 VPN。",
        VPN_WORKING_DIRECTORY_KEY: "VPN 客户端工作目录；留空时使用可执行文件所在目录。",
    },
)

config = {
    'custom_tasks':True, # enable creating and editing custom tasks
    'debug': False,  # Optional, default: False
    'gui': {'type': 'qt'},
    'config_folder': 'configs', #最好不要修改
    'gui_icon': 'icons/icon.png', #窗口图标, 最好不需要修改文件名
    'wait_until_before_delay': 0,
    'wait_until_check_delay': 0,
    'wait_until_settle_time': 0, #调用 wait_until时候, 在第一次满足条件的时候, 会等待再次检测, 以避免某些滑动动画没到预定位置就在动画路径中被检测到
    'ocr': { #可选, 使用的OCR库
        'lib': 'onnxocr',
        'auto_simplify': True, #自动繁体转简体, 需要ppocrv5等可以识别繁体的库
        'params': {
            'use_openvino': True,
        }
    },
    'windows': {  # Windows游戏请填写此设置
        'exe': ['gakumas.exe'],
        # optional, if set, will search the exe only
        'hwnd_class': 'UnityWndClass', #增加重名检查准确度
        'interaction': [EfInteraction], # Genshin:某些操作可以后台, 部分游戏支持 PostMessage:可后台点击, 极少游戏支持 ForegroundPostMessage:前台使用PostMessage Pynput/PyDirect:仅支持前台使用
        'capture_method': ['WGC', 'BitBlt_RenderFull', 'BitBlt'],  # Windows版本支持的话, 优先使用WGC, 否则使用BitBlt_Full. 支持的capture有 BitBlt, WGC, BitBlt_RenderFull, DXGI
        'check_hdr': False, #当用户开启AutoHDR时候提示用户, 但不禁止使用
        'force_no_hdr': False, #True=当用户开启AutoHDR时候禁止使用
        'require_bg': True, # 要求使用后台截图
        "start_exe": True,
        "calculate_pc_exe_path": resolve_game_exe,
    },
    'start_timeout': 120,  # default 60
    'window_size': { #ok-script窗口大小
        'width': 1200,
        'height': 800,
        'min_width': 600,
        'min_height': 450,
    },
    'supported_resolution': {
        'ratio': '9:16', #支持的游戏分辨率
        'min_size': (720, 1280), #支持的最低游戏分辨率
        'resize_to': [(1440, 2560), (1080, 1920), (900, 1600), (720, 1280)], #可选, 如果非16:9自动缩放为 resize_to
    },
    'links': { # 关于里显示的链接, 可选
            'default': {
                'github': 'https://github.com/ok-oldking/ok-py',
                'discord': 'https://discord.gg/vVyCatEBgA',
                'share': 'Download from https://github.com/ok-oldking/ok-py',
                'qq_group':'https://qm.qq.com/q/3Gq4VLvQe',
                'qq_channel': 'https://pd.qq.com/s/djmm6l44y',
                'faq': 'https://github.com/ok-oldking/ok-py'
            }
        },
    'screenshots_folder': "screenshots", #截图存放目录, 每次重新启动会清空目录
    'gui_title': 'ok-gm',  #窗口名
    'template_matching': { # 可选, 如使用OpenCV的模板匹配
        'coco_feature_json': os.path.join('assets', 'coco_annotations.json'), #coco格式标记, 需要png图片, 在debug模式运行后, 会对进行切图仅保留被标记部分以减少图片大小
        'default_horizontal_variance': 0.002, #默认x偏移, 查找不传box的时候, 会根据coco坐标, match偏移box内的
        'default_vertical_variance': 0.002, #默认y偏移
        'default_threshold': 0.8, #默认threshold
    },
    'version': version, #版本
    'my_app': ['src.globals', 'Globals'], #可选. 全局单例对象, 可以存放加载的模型, 使用og.my_app调用
    'global_configs': [
        vpn_config_option,
        dmm_config_option,
    ],
    'custom_tabs': [["src.ui.DmmLauncherTab", "DmmLauncherTab"], ["src.ui.AccountConfigTab", "AccountConfigTab"]],
    'onetime_tasks': [  # 用户点击触发的任务
        ["src.tasks.DailyTask", "DailyTask"],
        ["src.tasks.TestTask", "TestTask"],
        ["ok", "DiagnosisTask"],
    ],
}

# The framework CLI imports this config directly, without running main.py.
from src.patches.startup import install_startup_patches
install_startup_patches()
