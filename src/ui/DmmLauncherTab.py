from __future__ import annotations

import threading

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import QApplication, QFileDialog, QHBoxLayout, QLineEdit, QVBoxLayout, QWidget
from qfluentwidgets import BodyLabel, CheckBox, ComboBox, FluentIcon, LineEdit, PrimaryPushButton, ProgressBar, PushButton, SubtitleLabel

from ok.gui.widget.CustomTab import CustomTab
from src.config import DMM_AUTO_UPDATE_KEY, DMM_CONFIG_NAME, DMM_ENABLED_KEY, DMM_PROXY_KEY
from src.dmm.browser_proxy import restore_browser_proxy
from src.dmm.helper import DmmHelper, helper_lock
from src.dmm.launcher import browser_login, import_login, launch_game, login_candidate
from src.dmm.accounts import AccountStore
from src.dmm.helper import ensure_game_stopped
from src.dmm.xray import NODE_ENABLED_KEY, NodeStore, operation_proxy
from src.dmm.session import DmmError, LoginRequired, OperationCancelled, data_dir, valid_proxy


class LauncherWorker(QThread):
    progress = Signal(str)
    download = Signal(int, int)
    succeeded = Signal(str)
    failed = Signal(str)

    def __init__(self, action, proxy, auto_update, parent=None, settings=None, number='', name='', node_text=None, node_id=None):
        super().__init__(parent)
        self.action, self.proxy, self.auto_update = action, proxy, auto_update
        self.cancel_event = threading.Event()
        self.settings = settings if settings is not None else {
            DMM_PROXY_KEY: proxy, DMM_AUTO_UPDATE_KEY: auto_update, DMM_ENABLED_KEY: True}
        self.number, self.account_name, self.node_text = number, name, node_text
        self.node_id = node_id

    def cancel(self):
        self.cancel_event.set()

    def check_cancelled(self):
        if self.cancel_event.is_set():
            raise OperationCancelled("操作已取消，已下载的文件可在下次继续")

    def report_download(self, done, total):
        # Qt int signals are 32-bit; transmit a percentage and total MiB.
        self.download.emit(int(done * 100 / total) if total else 100, int(total / 1024 / 1024))

    def login(self, helper):
        browser_login(helper, self.progress.emit)

    def prepare_action(self, helper):
        if self.action == "check":
            result = helper.check()
            return f"版本 {result['latest_version']}：需更新 {result['pending_files']} 个文件，{result['download_bytes'] / 1024 / 1024:.1f} MiB"
        if self.action == "update":
            spec = helper.prepare(True)
            return f"游戏 {spec.version} 已更新并校验完成"
        raise DmmError("不支持的启动器操作")

    def run(self):
        try:
            if self.action == "launch":
                process = launch_game(dict(self.settings) | {DMM_ENABLED_KEY: True}, self.progress.emit, self.check_cancelled,
                                      self.report_download)
                self.succeeded.emit("游戏已启动，正在连接游戏服务器" if process else "游戏已经运行")
                return
            with helper_lock(data_dir()):
                root = data_dir()
                self.check_cancelled()
                restore_browser_proxy(root, progress=self.progress.emit)
                store = AccountStore(root)
                if self.action in {'node-select', 'node-toggle', 'node-remove'}:
                    NodeStore(root).change(self.node_id, self.action.removeprefix('node-'))
                    self.succeeded.emit('节点列表已更新')
                    return
                if self.action == 'account-save':
                    store.save_current(self.number, self.account_name)
                    self.succeeded.emit('当前登录文件已按编号加密保存')
                    return
                if self.action == 'account-switch':
                    entry = store.switch(self.number)
                    self.succeeded.emit(f"已切换到 {entry['number']} · {entry['name']}；下次启动将使用对应登录文件")
                    return
                if self.action == 'core-install':
                    NodeStore(root).install(self.proxy, self.progress.emit)
                    self.succeeded.emit('独立 Xray 内核已就绪')
                    return
                if self.action == 'node-import':
                    NodeStore(root).import_node(self.node_text, self.proxy, self.progress.emit)
                    self.settings[NODE_ENABLED_KEY] = True
                    self.succeeded.emit('节点已保存，独立 Xray 模式已启用')
                    return
                if self.action in {'account-login', 'account-import'}:
                    ensure_game_stopped()
                    store.validate(self.number, self.account_name)
                    if any(e['number'] == self.number for e in store.read()['accounts']):
                        raise DmmError('该编号已有账号，请为新账号指定新的编号')
                with operation_proxy(self.settings, self.progress.emit, self.check_cancelled, root) as proxy:
                    self.run_online(proxy, root, store)
        except DmmError as error:
            self.failed.emit(str(error))
        except Exception as error:
            self.failed.emit(f"操作失败（{type(error).__name__}），敏感信息已隐藏")

    def run_online(self, proxy, root, store):
        helper = DmmHelper(proxy, self.progress.emit, root=root, download_progress=self.report_download)
        helper.session.cancel_check = self.check_cancelled
        self.check_cancelled()
        if self.action in {'account-login', 'account-import'}:
            with login_candidate(helper, fresh=True) as candidate:
                if self.action == 'account-login':
                    browser_login(helper, self.progress.emit)
                else:
                    candidate.import_player()
                candidate.verify_game_identity()
                store.save_current(self.number, self.account_name, candidate.path, new=True)
            message = '新账号登录文件已加密保存并设为当前账号'
        elif self.action == "login":
            self.login(helper)
            message = "登录态已加密保存，之后可直接启动游戏"
        elif self.action == "import":
            copied = import_login(helper)
            if not helper.session.authenticated():
                raise LoginRequired("DMM 登录态已失效，请点击「浏览器登录」")
            message = "已复用 DMM 登录态" if copied else "已复用有效凭证；DMM 正在运行，Cookie 未复制"
        elif self.action == "status":
            if not helper.session.accounts.current_path().exists():
                raise LoginRequired("尚未登录，请点击「浏览器登录」或「复用 DMM 登录态」")
            message = "登录态有效，可直接启动游戏" if helper.session.authenticated() else "登录态已过期，请点击「浏览器登录」"
        elif self.action == "restore":
            message = "临时代理已恢复"
        else:
            try:
                message = self.prepare_action(helper)
            except LoginRequired:
                self.progress.emit("登录态需要续期，将打开常用浏览器")
                self.login(helper)
                message = self.prepare_action(helper)
        self.succeeded.emit(message)


class DmmLauncherTab(CustomTab):
    def __init__(self, settings=None):
        super().__init__()
        if settings is None:
            from ok import og
            settings = og.global_config.get_config(DMM_CONFIG_NAME)
        self.settings = settings
        self.icon = FluentIcon.PLAY
        self.worker = None
        self.buttons = []
        from src.ui.launcher_events import events
        self.launcher_events = events()
        self.add_widget(SubtitleLabel(self.tr("游戏启动器")))
        intro = BodyLabel(self.tr("保存登录态，使用指定代理检查更新并启动学园偶像大师。"))
        intro.setWordWrap(True)
        self.add_widget(intro)

        proxy_row = QWidget()
        layout = QHBoxLayout(proxy_row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.addWidget(BodyLabel(self.tr("本地代理入口")))
        self.proxy = LineEdit()
        self.proxy.setPlaceholderText("http://127.0.0.1:10808")
        self.proxy.setText(settings[DMM_PROXY_KEY])
        layout.addWidget(self.proxy, 1)
        self.save_button = PushButton(self.tr("保存代理"))
        self.save_button.clicked.connect(self.save_settings)
        layout.addWidget(self.save_button)
        self.add_widget(proxy_row)
        hint = BodyLabel(self.tr("外部代理模式在 v2rayN 选择日本节点；独立 Xray 使用下方保存的节点。"))
        hint.setWordWrap(True)
        self.add_widget(hint)

        self.fixed_node = CheckBox(self.tr('使用独立 Xray 节点'))
        self.fixed_node.setChecked(settings.get(NODE_ENABLED_KEY, False))
        self.fixed_node.toggled.connect(lambda checked: self.settings.__setitem__(NODE_ENABLED_KEY, checked))
        self.add_widget(self.fixed_node)
        self.node_status = BodyLabel('')
        self.node_status.setWordWrap(True)
        self.add_widget(self.node_status)
        self.node_selector = ComboBox()
        self.add_widget(self.node_selector)
        node_actions = QWidget()
        node_actions_layout = QHBoxLayout(node_actions)
        node_actions_layout.setContentsMargins(0, 0, 0, 0)
        for action, label in (('node-select', '下次优先使用'), ('node-toggle', '启用或停用节点'), ('node-remove', '移除节点')):
            button = PushButton(self.tr(label))
            button.clicked.connect(lambda checked=False, action=action: self.start_action(action))
            node_actions_layout.addWidget(button)
            self.buttons.append(button)
        self.add_widget(node_actions)
        pool_hint = BodyLabel(self.tr('节点按顺序轮换；连接失败自动尝试下一个，下载会保留断点。'))
        pool_hint.setWordWrap(True)
        self.add_widget(pool_hint)
        node_row = QWidget()
        node_layout = QHBoxLayout(node_row)
        node_layout.setContentsMargins(0, 0, 0, 0)
        self.node_input = LineEdit()
        self.node_input.setEchoMode(QLineEdit.Password)
        self.node_input.setPlaceholderText(self.tr('粘贴节点分享链接，内容会隐藏'))
        node_layout.addWidget(self.node_input, 1)
        import_node = PushButton(self.tr('保存节点'))
        import_node.clicked.connect(lambda: self.start_action('node-import'))
        node_layout.addWidget(import_node)
        self.buttons.append(import_node)
        self.add_widget(node_row)
        core_row = QWidget()
        core_layout = QHBoxLayout(core_row)
        core_layout.setContentsMargins(0, 0, 0, 0)
        for label, callback in ((self.tr('导入 JSON 文件'), self.import_node_file),
                                (self.tr('安装独立 Xray'), lambda: self.start_action('core-install'))):
            button = PushButton(label)
            button.clicked.connect(callback)
            core_layout.addWidget(button)
            self.buttons.append(button)
        self.add_widget(core_row)

        self.add_widget(SubtitleLabel(self.tr('账号登录文件')))
        self.current_account_label = BodyLabel('')
        self.add_widget(self.current_account_label)
        self.account_selector = ComboBox()
        self.account_selector.currentIndexChanged.connect(self.fill_account_fields)
        self.add_widget(self.account_selector)
        account_fields = QWidget()
        field_layout = QHBoxLayout(account_fields)
        field_layout.setContentsMargins(0, 0, 0, 0)
        self.account_number = LineEdit()
        self.account_number.setPlaceholderText(self.tr('账号编号，例如 1'))
        self.account_name = LineEdit()
        self.account_name.setPlaceholderText(self.tr('账号名称'))
        field_layout.addWidget(self.account_number)
        field_layout.addWidget(self.account_name)
        self.add_widget(account_fields)
        account_actions = QWidget()
        account_layout = QVBoxLayout(account_actions)
        account_layout.setContentsMargins(0, 0, 0, 0)
        for group in ((('account-save', '保存当前登录态'), ('account-switch', '切换所选账号')),
                      (('account-login', '新账号登录并保存'), ('account-import', '记录当前 DMM 为新账号'))):
            row = QHBoxLayout()
            for action, label in group:
                button = PushButton(self.tr(label))
                button.clicked.connect(lambda checked=False, action=action: self.start_action(action))
                row.addWidget(button)
                self.buttons.append(button)
            account_layout.addLayout(row)
        self.add_widget(account_actions)
        account_hint = BodyLabel(self.tr('新账号使用新编号保存。切换前先关闭游戏；不会覆盖 DMM Player 的账号文件。'))
        account_hint.setWordWrap(True)
        self.add_widget(account_hint)

        self.auto_update = CheckBox(self.tr("启动前自动检查并更新游戏"))
        self.auto_update.setChecked(settings[DMM_AUTO_UPDATE_KEY])
        self.auto_update.toggled.connect(lambda checked: self.settings.__setitem__(DMM_AUTO_UPDATE_KEY, checked))
        self.add_widget(self.auto_update)
        self.use_helper = CheckBox(self.tr("框架启动游戏时使用此启动器"))
        self.use_helper.setChecked(settings[DMM_ENABLED_KEY])
        self.use_helper.toggled.connect(lambda checked: self.settings.__setitem__(DMM_ENABLED_KEY, checked))
        self.add_widget(self.use_helper)

        actions = QWidget()
        rows = QVBoxLayout(actions)
        rows.setContentsMargins(0, 0, 0, 0)
        for action_row in ((('login', '浏览器登录'), ('import', '复用 DMM 登录态'), ('status', '检查登录状态')),
                           (('check', '检查更新'), ('update', '更新游戏'), ('launch', '启动游戏'))):
            row = QHBoxLayout()
            for action, label in action_row:
                button = PrimaryPushButton(self.tr(label)) if action == 'launch' else PushButton(self.tr(label))
                button.clicked.connect(lambda checked=False, action=action: self.start_action(action))
                self.buttons.append(button)
                row.addWidget(button)
            rows.addLayout(row)
        self.add_widget(actions)

        self.status = BodyLabel(self.tr("已有加密登录态，可检查状态或直接启动。") if (data_dir() / 'session.dpapi').exists()
                                else self.tr("首次使用请登录，或复用 DMM Player 的登录态。"))
        self.status.setWordWrap(True)
        self.add_widget(self.status)
        self.download_label = BodyLabel("")
        self.add_widget(self.download_label)
        self.progress_bar = ProgressBar()
        self.progress_bar.setRange(0, 100)
        self.progress_bar.setValue(0)
        self.add_widget(self.progress_bar)
        self.cancel_button = PushButton(self.tr("取消当前操作"))
        self.cancel_button.setEnabled(False)
        self.cancel_button.clicked.connect(self.cancel)
        self.add_widget(self.cancel_button)
        login_hint = BodyLabel(self.tr("浏览器登录可使用已保存密码。成功后按 Ctrl+L、Ctrl+C 复制成功页地址；登录期间临时启用代理，结束后恢复。"))
        login_hint.setWordWrap(True)
        self.add_widget(login_hint)
        self.launcher_events.progress.connect(self.status.setText)
        self.launcher_events.download.connect(self.show_download)
        QApplication.instance().aboutToQuit.connect(self.shutdown)
        self.refresh_profiles()

    @property
    def name(self):
        return "游戏启动器"

    @property
    def add_after_default_tabs(self):
        return False

    def save_settings(self):
        try:
            self.settings[DMM_PROXY_KEY] = valid_proxy(self.proxy.text().strip())
            self.status.setText(self.tr("代理设置已保存"))
            return True
        except DmmError as error:
            self.status.setText(str(error))
            return False

    def controls(self):
        return [*self.buttons, self.proxy, self.save_button, self.auto_update, self.use_helper,
                self.fixed_node, self.node_input, self.node_selector, self.account_selector, self.account_number, self.account_name]

    def refresh_profiles(self):
        store = AccountStore(data_dir())
        try:
            value = store.read()
            self.account_selector.blockSignals(True)
            self.account_selector.clear()
            self.account_selector.addItem(self.tr('选择已保存账号'), userData=None)
            active_index = 0
            for index, entry in enumerate(value['accounts'], 1):
                self.account_selector.addItem(f"{entry['number']} · {entry['name']}", userData=entry['number'])
                if entry['key'] == value['active']:
                    active_index = index
            self.account_selector.setCurrentIndex(active_index)
            active = next((e for e in value['accounts'] if e['key'] == value['active']), None)
            self.current_account_label.setText(f"{self.tr('当前账号')}：{active['number']} · {active['name']}"
                                               if active else self.tr('当前登录态尚未归档'))
            self.account_selector.blockSignals(False)
            self.fill_account_fields()
            node_store = NodeStore(data_dir())
            selected_node = self.node_selector.currentData()
            self.node_selector.clear()
            if node_store.path.exists():
                pool = node_store.read()
                for node in pool['nodes']:
                    state = self.tr('已启用') if node['enabled'] else self.tr('已停用')
                    self.node_selector.addItem(f"{node['name']} · {node['outbound']['protocol']} · {state}", userData=node['id'])
                target = selected_node or pool['next']
                index = next((i for i, n in enumerate(pool['nodes']) if n['id'] == target), 0)
                self.node_selector.setCurrentIndex(index)
                next_node = next((n for n in pool['nodes'] if n['id'] == pool['next'] and n['enabled']),
                                 next((n for n in pool['nodes'] if n['enabled']), None))
                self.node_status.setText(self.tr('下次开始节点：') + (next_node['name'] if next_node else self.tr('没有启用节点')))
            else:
                self.node_status.setText(self.tr('尚未导入固定节点；导入成功后自动启用独立 Xray。'))
            self.fixed_node.setChecked(self.settings.get(NODE_ENABLED_KEY, False))
        except DmmError as error:
            self.status.setText(str(error))
        finally:
            self.account_selector.blockSignals(False)

    def fill_account_fields(self):
        number = self.account_selector.currentData()
        if number is None:
            return
        try:
            entry = next(e for e in AccountStore(data_dir()).read()['accounts'] if e['number'] == number)
            self.account_number.setText(entry['number'])
            self.account_name.setText(entry['name'])
        except (DmmError, StopIteration):
            pass

    def import_node_file(self):
        from pathlib import Path
        filename, _ = QFileDialog.getOpenFileName(self, self.tr('导入节点配置'), '', 'JSON (*.json);;All files (*)')
        if not filename:
            return
        try:
            file = Path(filename)
            if file.stat().st_size > 1024 * 1024:
                raise ValueError()
            text = file.read_text(encoding='utf-8-sig')
        except (OSError, UnicodeError, ValueError):
            self.status.setText(self.tr('节点文件无法读取或超过 1 MiB'))
            return
        self.start_action('node-import', node_text=text)

    def start_action(self, action, node_text=None):
        if self.worker is not None or not self.save_settings():
            return
        from ok import og
        current_task = getattr(og.executor, 'current_task', None)
        if action in {'account-save', 'account-switch', 'account-login', 'account-import', 'login', 'import'} and getattr(current_task, 'running', False):
            self.status.setText(self.tr('任务运行中，不能修改或切换登录账号'))
            return
        self.progress_bar.setValue(0)
        self.download_label.setText("")
        self.status.setText(self.tr("正在处理，请稍候…"))
        for widget in self.controls():
            widget.setEnabled(False)
        self.cancel_button.setEnabled(True)
        number = self.account_selector.currentData() if action == 'account-switch' else self.account_number.text().strip()
        worker = LauncherWorker(action, self.settings[DMM_PROXY_KEY], self.auto_update.isChecked(), self,
            settings=self.settings, number=number, name=self.account_name.text().strip(),
            node_text=node_text if node_text is not None else self.node_input.text(), node_id=self.node_selector.currentData())
        self.worker = worker
        worker.progress.connect(self.status.setText)
        worker.download.connect(self.show_download)
        worker.succeeded.connect(self.status.setText)
        worker.failed.connect(self.status.setText)
        worker.finished.connect(self.action_finished)
        worker.start()

    def show_download(self, percent, total_mib):
        self.progress_bar.setValue(percent)
        self.download_label.setText(f"{percent}% · {total_mib} MiB")

    def action_finished(self):
        worker = self.worker
        self.worker = None
        for widget in self.controls():
            widget.setEnabled(True)
        self.cancel_button.setEnabled(False)
        if worker is not None:
            if worker.action == 'node-import':
                self.node_input.clear()
            worker.deleteLater()
        self.refresh_profiles()
        if worker is not None and worker.action.startswith('account-'):
            self.launcher_events.profiles_changed.emit()

    def cancel(self):
        if self.worker:
            self.worker.cancel()
            self.cancel_button.setEnabled(False)
            self.status.setText(self.tr("正在取消并恢复设置…"))

    def shutdown(self):
        if self.worker:
            self.worker.cancel()
            self.worker.wait()
