"""Keep ordinary task cards consistent with the account editor during execution."""
from functools import wraps

_installed = False


def install_task_config_lock():
    global _installed
    if _installed:
        return
    from ok.gui.tasks.TaskCard import TaskCard
    update = TaskCard.update_buttons

    @wraps(update)
    def update_buttons(card, task):
        update(card, task)
        editable = not card.task.running
        for widget in card.config_widgets:
            widget.setEnabled(editable)
        if card.reset_config is not None:
            card.reset_config.setEnabled(editable)

    TaskCard.update_buttons = update_buttons
    _installed = True
