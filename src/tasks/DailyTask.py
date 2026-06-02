import re

from qfluentwidgets import FluentIcon

from ok import og
from src.tasks.BaseGMTask import BaseGMTask


class DailyTask(BaseGMTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Configuration Demo Task"
        self.description = "Demonstrates every configuration widget for English to Chinese translation."
        self.icon = FluentIcon.SYNC
        

    def run(self):
        self.show_config_values()

