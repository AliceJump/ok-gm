from src.data.FeatureList import FeatureList as fL
from src.tasks.daily.step.daily_arena import DailyArena
from src.tasks.BaseGMTask import BaseGMTask
class TestTask(DailyArena, BaseGMTask):
    def run(self):
        self.wait_until_feature(fL.next_step, fL.skip_pk, self.box_of_screen(0.352, 0.892, 0.398, 0.921), allow_unrecognized_click=True, skip_target_check_after_action=True)

