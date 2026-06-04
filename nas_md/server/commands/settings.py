"""Settings bot commands."""

from __future__ import annotations

from nas_md.server.router import command


@command("settings")
def cmd_settings(server, upd, cmd):
    """Show settings."""
    server._cmd_settings(upd, cmd)


@command("toggleMode")
def cmd_toggle_mode(server, upd, cmd):
    """Toggle bot mode."""
    server.tg.send(server.user_id, "Toggle mode - not yet implemented in modular form.")


@command("toggleTwoEmojis")
def cmd_toggle_two_emojis(server, upd, cmd):
    """Toggle two emojis setting."""
    server.tg.send(server.user_id, "Toggle two emojis - not yet implemented in modular form.")


@command("toggleQuickHabits")
def cmd_toggle_quick_habits(server, upd, cmd):
    """Toggle quick habits setting."""
    server.tg.send(server.user_id, "Toggle quick habits - not yet implemented in modular form.")


@command("settingsMode")
def cmd_settings_mode(server, upd, cmd):
    """Settings mode selection."""
    server.tg.send(server.user_id, "Settings mode - not yet implemented in modular form.")


@command("settingsTimezone")
def cmd_settings_timezone(server, upd, cmd):
    """Settings timezone selection."""
    server.tg.send(server.user_id, "Settings timezone - not yet implemented in modular form.")


@command("settingsPomodoro")
def cmd_settings_pomodoro(server, upd, cmd):
    """Settings pomodoro configuration."""
    server.tg.send(server.user_id, "Settings pomodoro - not yet implemented in modular form.")


@command("settingsSchedule")
def cmd_settings_schedule(server, upd, cmd):
    """Settings schedule configuration."""
    server.tg.send(server.user_id, "Settings schedule - not yet implemented in modular form.")


@command("settingsChannel")
def cmd_settings_channel(server, upd, cmd):
    """Settings channel configuration."""
    server.tg.send(server.user_id, "Settings channel - not yet implemented in modular form.")


@command("settingsQuick")
def cmd_settings_quick(server, upd, cmd):
    """Settings quick buttons configuration."""
    server.tg.send(server.user_id, "Settings quick - not yet implemented in modular form.")


@command("settingsTwoEmojis")
def cmd_settings_two_emojis(server, upd, cmd):
    """Settings two emojis configuration."""
    server.tg.send(server.user_id, "Settings two emojis - not yet implemented in modular form.")


@command("settingsQuickHabits")
def cmd_settings_quick_habits(server, upd, cmd):
    """Settings quick habits configuration."""
    server.tg.send(server.user_id, "Settings quick habits - not yet implemented in modular form.")


@command("help")
def cmd_help(server, upd, cmd):
    """Show help."""
    server._cmd_help(upd, cmd)


@command("cancel")
def cmd_cancel(server, upd, cmd):
    """Cancel current operation."""
    server.db.del_input_expectation()
    server.tg.send(server.user_id, "Cancelled.")


@command("home")
def cmd_home(server, upd, cmd):
    """Go to home screen."""
    server._cmd_home(upd, cmd)


@command("back")
def cmd_back(server, upd, cmd):
    """Go back."""
    server._cmd_back(upd, cmd)


@command("stats")
def cmd_stats(server, upd, cmd):
    """Show statistics."""
    server._cmd_stats(upd, cmd)


@command("todayReport")
def cmd_today_report(server, upd, cmd):
    """Show today's report."""
    server.tg.send(server.user_id, "Today report - not yet implemented in modular form.")


@command("channel")
def cmd_channel(server, upd, cmd):
    """Channel settings."""
    server.tg.send(server.user_id, "Channel - not yet implemented in modular form.")


@command("journal")
def cmd_journal(server, upd, cmd):
    """Journal commands."""
    server._cmd_journal(upd, cmd)


@command("journalDir")
def cmd_journal_dir(server, upd, cmd):
    """Journal directory."""
    server.tg.send(server.user_id, "Journal directory - not yet implemented in modular form.")


@command("journalEmoji")
def cmd_journal_emoji(server, upd, cmd):
    """Journal emoji."""
    server.tg.send(server.user_id, "Journal emoji - not yet implemented in modular form.")


@command("day")
def cmd_day(server, upd, cmd):
    """Show a specific day."""
    server.tg.send(server.user_id, "Day - not yet implemented in modular form.")


@command("read")
def cmd_read(server, upd, cmd):
    """Read list."""
    server.tg.send(server.user_id, "Read - not yet implemented in modular form.")


@command("shop")
def cmd_shop(server, upd, cmd):
    """Shopping list."""
    server.tg.send(server.user_id, "Shop - not yet implemented in modular form.")


@command("watch")
def cmd_watch(server, upd, cmd):
    """Watch list."""
    server.tg.send(server.user_id, "Watch - not yet implemented in modular form.")


@command("moveTo")
def cmd_move_to(server, upd, cmd):
    """Move to specific location."""
    server.tg.send(server.user_id, "Move to - not yet implemented in modular form.")


@command("touch")
def cmd_touch(server, upd, cmd):
    """Touch/create file."""
    server.tg.send(server.user_id, "Touch - not yet implemented in modular form.")


@command("merge")
def cmd_merge(server, upd, cmd):
    """Merge files."""
    server.tg.send(server.user_id, "Merge - not yet implemented in modular form.")


@command("toggleArchive")
def cmd_toggle_archive(server, upd, cmd):
    """Toggle archive."""
    server.tg.send(server.user_id, "Toggle archive - not yet implemented in modular form.")
