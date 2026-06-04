"""Note-related bot commands."""

from __future__ import annotations

from nas_md.server.router import command


@command("notes")
def cmd_notes(server, upd, cmd):
    """List notes directories."""
    dirs = server.user_fs.only_dirs(server.user_fs.notes_dir())
    if not dirs:
        server.tg.send(server.user_id, "No notes found.")
        return
    from nas_md.pkg.tg.types import new_btn, new_row, new_keyboard, new_cmd

    rows = []
    for d in dirs:
        name = server.user_fs.display_name(d)
        rows.append(new_row([new_btn(name, new_cmd("notes", {"dir": d}))]))
    server.tg.send(server.user_id, "Notes:", new_keyboard(rows))


@command("file")
def cmd_file(server, upd, cmd):
    """View a file."""
    path = cmd.data.get("path", "") if cmd.data else ""
    if not path:
        return
    content = server.user_fs.read_file(path)
    if content:
        from nas_md.pkg.txt.md import markdown_to_html

        html = markdown_to_html(content)
        server.tg.send(server.user_id, html, None, "HTML")
    else:
        server.tg.send(server.user_id, "File not found.")


@command("newDir")
def cmd_new_dir(server, upd, cmd):
    """Create a new directory."""
    server.db.set_input_expectation(cmd)
    server.tg.send(server.user_id, "Enter directory name:")


@command("renameDir")
def cmd_rename_dir(server, upd, cmd):
    """Rename a directory."""
    server.db.set_input_expectation(cmd)
    server.tg.send(server.user_id, "Enter new name:")


@command("delDir")
def cmd_del_dir(server, upd, cmd):
    """Delete a directory."""
    path = cmd.data.get("path", "") if cmd.data else ""
    if path:
        server.user_fs.del_dir(path)
        server.tg.send(server.user_id, "Directory deleted.")


@command("touchFile")
def cmd_touch_file(server, upd, cmd):
    """Create an empty file."""
    path = cmd.data.get("path", "") if cmd.data else ""
    if path:
        server.user_fs.new_file(path, "")
        server.tg.send(server.user_id, f"Created {path}")


@command("mergeFile")
def cmd_merge_file(server, upd, cmd):
    """Merge a file."""
    path = cmd.data.get("path", "") if cmd.data else ""
    if path:
        server.tg.send(server.user_id, f"Merge for {path} - not yet implemented in modular form.")


@command("archive")
def cmd_archive(server, upd, cmd):
    """Archive a note."""
    server.tg.send(server.user_id, "Archive - not yet implemented in modular form.")


@command("media")
def cmd_media(server, upd, cmd):
    """Handle media files."""
    server.tg.send(server.user_id, "Media - not yet implemented in modular form.")
