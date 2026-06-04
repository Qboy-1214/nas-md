"""Task-related bot commands."""

from __future__ import annotations

from nas_md.server.router import command


@command("new")
def cmd_new(server, upd, cmd):
    """Add a new task."""
    server.db.set_input_expectation(cmd)
    server.tg.send(server.user_id, "Enter task:")


@command("done")
def cmd_done(server, upd, cmd):
    """Mark a task as done."""
    idx = cmd.data.get("idx", -1) if cmd.data else -1
    if idx >= 0:
        server._complete_task(idx)
    else:
        server.tg.send(server.user_id, "No task specified.")


@command("del")
def cmd_del(server, upd, cmd):
    """Delete a task."""
    idx = cmd.data.get("idx", -1) if cmd.data else -1
    if idx >= 0:
        server._delete_task(idx)
    else:
        server.tg.send(server.user_id, "No task specified.")


@command("rename")
def cmd_rename(server, upd, cmd):
    """Rename a task."""
    server.db.set_input_expectation(cmd)
    server.tg.send(server.user_id, "Enter new name:")


@command("move")
def cmd_move(server, upd, cmd):
    """Move a task."""
    server.tg.send(server.user_id, "Move - not yet implemented in modular form.")


@command("repeat")
def cmd_repeat(server, upd, cmd):
    """Repeat a task."""
    server.tg.send(server.user_id, "Repeat - not yet implemented in modular form.")


@command("complete")
def cmd_complete(server, upd, cmd):
    """Complete a task."""
    idx = cmd.data.get("idx", -1) if cmd.data else -1
    if idx >= 0:
        server._complete_task(idx)
    else:
        server.tg.send(server.user_id, "No task specified.")


@command("add")
def cmd_add(server, upd, cmd):
    """Add a task directly."""
    text = cmd.data.get("text", "") if cmd.data else ""
    if text:
        server._add_task(text)
    else:
        server.db.set_input_expectation(cmd)
        server.tg.send(server.user_id, "Enter task:")


@command("today")
def cmd_today(server, upd, cmd):
    """Show today's tasks."""
    server._cmd_today(upd, cmd)


@command("tomorrow")
def cmd_tomorrow(server, upd, cmd):
    """Move task to tomorrow."""
    server.tg.send(server.user_id, "Tomorrow - not yet implemented in modular form.")


@command("later")
def cmd_later(server, upd, cmd):
    """Move task to later."""
    server.tg.send(server.user_id, "Later - not yet implemented in modular form.")


@command("quick")
def cmd_quick(server, upd, cmd):
    """Quick buttons."""
    server.tg.send(server.user_id, "Quick - not yet implemented in modular form.")


@command("pomodoro")
def cmd_pomodoro(server, upd, cmd):
    """Start a pomodoro."""
    server.tg.send(server.user_id, "Pomodoro - not yet implemented in modular form.")


@command("checklist")
def cmd_checklist(server, upd, cmd):
    """Show checklist."""
    server.tg.send(server.user_id, "Checklist - not yet implemented in modular form.")


@command("addChecklist")
def cmd_add_checklist(server, upd, cmd):
    """Add a checklist."""
    server.tg.send(server.user_id, "Add checklist - not yet implemented in modular form.")


@command("completeChecklist")
def cmd_complete_checklist(server, upd, cmd):
    """Complete a checklist item."""
    server.tg.send(server.user_id, "Complete checklist - not yet implemented in modular form.")


@command("delChecklist")
def cmd_del_checklist(server, upd, cmd):
    """Delete a checklist."""
    server.tg.send(server.user_id, "Delete checklist - not yet implemented in modular form.")


@command("addChecklistItem")
def cmd_add_checklist_item(server, upd, cmd):
    """Add a checklist item."""
    server.tg.send(server.user_id, "Add checklist item - not yet implemented in modular form.")


@command("delChecklistItem")
def cmd_del_checklist_item(server, upd, cmd):
    """Delete a checklist item."""
    server.tg.send(server.user_id, "Delete checklist item - not yet implemented in modular form.")
