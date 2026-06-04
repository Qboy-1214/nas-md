"""Habit-related bot commands."""

from __future__ import annotations

from nas_md.server.router import command


@command("habits")
def cmd_habits(server, upd, cmd):
    """Show habits."""
    server._cmd_habits(upd, cmd)


@command("habitEmoji")
def cmd_habit_emoji(server, upd, cmd):
    """Set habit emoji."""
    server.tg.send(server.user_id, "Habit emoji - not yet implemented in modular form.")


@command("habitsDir")
def cmd_habits_dir(server, upd, cmd):
    """Show habits directory."""
    server.tg.send(server.user_id, "Habits directory - not yet implemented in modular form.")


@command("insights")
def cmd_insights(server, upd, cmd):
    """Show insights."""
    server.tg.send(server.user_id, "Insights - not yet implemented in modular form.")
