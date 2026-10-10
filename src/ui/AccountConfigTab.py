"""Per-account task editor using the same ConfigCard pattern as ok-end-field."""
from __future__ import annotations

import copy

from PySide6.QtCore import QTimer
from PySide6.QtWidgets import QHBoxLayout, QWidget
from qfluentwidgets import BodyLabel, ComboBox, FluentIcon, PrimaryPushButton, PushButton, SubtitleLabel
from ok.gui.tasks.ConfigCard import ConfigCard
from ok.gui.widget.CustomTab import CustomTab

from src.dmm.accounts import AccountStore
from src.dmm.session import DmmError, data_dir
from src.tasks.account.account_scope_store import (
    bind_dmm_accounts, dmm_account_id, get_account_task_overrides,
    remove_account_task_overrides, set_account_task_overrides,
)
from src.tasks.mixin.account_override_mixin import AccountOverrideMixin

CONTROL_KEYS = {'多账户模式', '多账户独立配置', '账号列表'}


class InMemoryConfig(dict):
    def __init__(self, initial, defaults):
        super().__init__(copy.deepcopy(initial))
        self.default = copy.deepcopy(defaults)

    def get_default(self, key):
        return self.default.get(key)

    def has_user_config(self):
        return any(not str(key).startswith('_') for key in self)


def account_task_config(task, overrides):
    defaults, initial = {}, {}
    for key, default in task.default_config.items():
        meta = task.config_type.get(key, {}) or {}
        if key in CONTROL_KEYS or str(key).startswith('_') or meta.get('type') in {'button', 'global'}:
            continue
        if not isinstance(default, (bool, int, float, str, list)):
            continue
        defaults[key] = copy.deepcopy(default)
        raw_get = getattr(task.config, '_raw_get', task.config.get)
        base = raw_get(key, default)
        initial[key] = AccountOverrideMixin._coerce_override_value(base, overrides.get(key, base))
    return InMemoryConfig(initial, defaults)


class AccountConfigTab(CustomTab):
    def __init__(self):
        super().__init__()
        self.icon = FluentIcon.PEOPLE
        self.editor = self.virtual_config = None
        self.edit_key = None
        self.drafts = {}
        self.add_widget(SubtitleLabel(self.tr('账号配置')))
        hint = BodyLabel(self.tr('选择启动器中保存的账号，再设置该账号的任务参数。改名或重新保存登录文件会保留这些配置。'))
        hint.setWordWrap(True)
        self.add_widget(hint)
        self.account_selector, self.task_selector = ComboBox(), ComboBox()
        self.add_widget(self.account_selector)
        self.add_widget(self.task_selector)
        row = QWidget()
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        self.save_button = PrimaryPushButton(self.tr('保存账号任务配置'))
        self.reset_button = PushButton(self.tr('恢复使用任务默认配置'))
        self.refresh_button = PushButton(self.tr('刷新账号列表'))
        for button in (self.save_button, self.reset_button, self.refresh_button):
            layout.addWidget(button)
        self.add_widget(row)
        self.status = BodyLabel(self.tr('账号配置只在任务运行时应用；任务运行期间不能编辑。'))
        self.status.setWordWrap(True)
        self.add_widget(self.status)
        self.save_button.clicked.connect(self.save_current)
        self.reset_button.clicked.connect(self.reset_current)
        self.refresh_button.clicked.connect(self.refresh)
        self.account_selector.currentIndexChanged.connect(self.render)
        self.task_selector.currentIndexChanged.connect(self.render)
        from src.ui.launcher_events import events
        events().profiles_changed.connect(self.refresh)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.update_lock)
        self.timer.start(500)
        self.refresh()

    @property
    def name(self):
        return '账号配置'

    @property
    def add_after_default_tabs(self):
        return False

    def showEvent(self, event):
        super().showEvent(event)
        self.refresh()

    def stash(self):
        if self.edit_key and self.virtual_config is not None:
            self.drafts[self.edit_key] = copy.deepcopy(dict(self.virtual_config))

    def refresh(self):
        self.stash()
        account_number = self.account_selector.currentData()
        task = self.task_selector.currentData()
        for selector in (self.account_selector, self.task_selector):
            selector.blockSignals(True)
            selector.clear()
        try:
            entries = AccountStore(data_dir()).read()['accounts']
            bind_dmm_accounts(entries)
            if not entries:
                self.account_selector.addItem(self.tr('请先在游戏启动器保存账号'), userData=None)
            for entry in entries:
                self.account_selector.addItem(f"{entry['number']} · {entry['name']}", userData=entry['number'])
            self.account_selector.setCurrentIndex(next((i for i, e in enumerate(entries) if e['number'] == account_number), 0))
            tasks = list(self.executor.get_all_tasks()) if self.executor is not None else []
            supported = [t for t in tasks if isinstance(t, AccountOverrideMixin)]
            if not supported:
                self.task_selector.addItem(self.tr('没有支持账号配置的任务'), userData=None)
            for item in supported:
                self.task_selector.addItem(self.tr(item.name), userData=item)
            self.task_selector.setCurrentIndex(next((i for i, t in enumerate(supported) if t is task), 0))
        except DmmError as error:
            self.status.setText(str(error))
        finally:
            for selector in (self.account_selector, self.task_selector):
                selector.blockSignals(False)
        self.render()

    def render(self):
        self.stash()
        if self.editor is not None:
            self.removeWidget(self.editor)
            self.editor.deleteLater()
            self.editor = None
        self.virtual_config, self.edit_key = None, None
        number, task = self.account_selector.currentData(), self.task_selector.currentData()
        if number is not None and task is not None:
            account_id, task_name = dmm_account_id(number), task.__class__.__name__
            self.edit_key = (account_id, task_name)
            values = self.drafts.get(self.edit_key)
            if values is None:
                values = get_account_task_overrides(account_id, task_name)
            self.virtual_config = account_task_config(task, values)
            keys = set(self.virtual_config)
            descriptions = {k: v for k, v in task.config_description.items() if k in keys}
            types = {k: v for k, v in task.config_type.items() if k in keys}
            self.editor = ConfigCard(None, task.name, self.virtual_config,
                self.tr('保存后仅覆盖所选账号的任务参数'), {}, descriptions, types, task.icon or FluentIcon.SETTING)
            self.editor.setExpand(True)
            self.add_widget(self.editor)
        self.update_lock()

    def task_running(self):
        return self.executor is not None and any(t.running for t in self.executor.get_all_tasks())

    def update_lock(self):
        idle = not self.task_running()
        for selector in (self.account_selector, self.task_selector):
            selector.setEnabled(idle)
        for button in (self.save_button, self.reset_button):
            button.setEnabled(idle and self.edit_key is not None)
        self.refresh_button.setEnabled(idle)
        if self.editor is not None:
            self.editor.setEnabled(idle)

    def save_current(self):
        if self.task_running() or not self.edit_key:
            return
        self.stash()
        set_account_task_overrides(*self.edit_key, dict(self.virtual_config))
        self.status.setText(self.tr('当前账号的任务配置已保存'))

    def reset_current(self):
        if self.task_running() or not self.edit_key:
            return
        key = self.edit_key
        remove_account_task_overrides(*key)
        self.drafts.pop(key, None)
        # Prevent render from restoring the draft that was explicitly reset.
        self.virtual_config = None
        self.render()
        self.status.setText(self.tr('当前账号将使用任务默认配置'))
