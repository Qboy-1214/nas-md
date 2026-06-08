"""CLI entry points for the files.md server."""

from __future__ import annotations

import argparse


def cmd_server() -> None:
    """Run the Telegram bot server."""
    import nas_md.config as cfg_mod

    cfg_mod.load_bot_config()
    print("files.md server starting...")
    # In a real implementation, this would start the Telegram bot polling loop


def cmd_backlink() -> None:
    """Generate backlinks for all notes."""
    print("Generating backlinks...")


def cmd_shifttime() -> None:
    """Shift timestamps in journal entries."""
    print("Shifting timestamps...")


def cmd_tomdlinks() -> None:
    """Convert links to markdown format."""
    print("Converting links...")


def cmd_whoop() -> None:
    """Whoop command."""
    print("Whoop!")


def cmd_web() -> None:
    """Start the web server with mount points and PWA frontend."""
    import logging

    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s: %(message)s")

    import nas_md.config as cfg_mod

    cfg_mod.load_bot_config()

    mount_dirs = cfg_mod.server_cfg.mount_dir_list()
    public_mount_dirs = cfg_mod.server_cfg.public_mount_dir_list()
    public_mount_names = cfg_mod.server_cfg.public_mount_names()
    web_root = cfg_mod.server_cfg.web_root
    port = cfg_mod.server_cfg.web_port
    storage_dir = cfg_mod.server_cfg.storage_dir

    from nas_md.webserver import serve

    serve(
        mount_dirs=mount_dirs,
        public_mount_dirs=public_mount_dirs,
        public_mount_names=public_mount_names,
        web_root=web_root,
        port=port,
        storage_dir=storage_dir,
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="files.md - Telegram note-taking bot")
    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("server", help="Run the Telegram bot server")
    subparsers.add_parser("backlink", help="Generate backlinks")
    subparsers.add_parser("shifttime", help="Shift timestamps")
    subparsers.add_parser("tomdlinks", help="Convert links to markdown")
    subparsers.add_parser("whoop", help="Whoop")
    subparsers.add_parser("web", help="Start the web server with mount points")

    args = parser.parse_args()

    commands = {
        "server": cmd_server,
        "backlink": cmd_backlink,
        "shifttime": cmd_shifttime,
        "tomdlinks": cmd_tomdlinks,
        "whoop": cmd_whoop,
        "web": cmd_web,
    }

    if args.command in commands:
        commands[args.command]()
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
