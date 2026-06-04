"""Search and knowledge-graph bot commands."""

from __future__ import annotations

from nas_md.server.router import command


@command("search")
def cmd_search(server, upd, cmd):
    """Search notes."""
    server.db.set_input_expectation(cmd)
    server.tg.send(server.user_id, "Enter search query:")


@command("searchNotes")
def cmd_search_notes(server, upd, cmd):
    """Search notes with inline results."""
    query = cmd.data.get("q", "") if cmd.data else ""
    if not query:
        server.db.set_input_expectation(cmd)
        server.tg.send(server.user_id, "Enter search query:")
        return

    try:
        from nas_md.search import init_db, search as fts_search

        init_db()
        results = fts_search(query, limit=10)
        if not results:
            server.tg.send(server.user_id, f"No results for: {query}")
            return

        lines = [f"Search results for <b>{query}</b>:\n"]
        for r in results:
            title = r.get("title", r.get("path", "Unknown"))
            path = r.get("path", "")
            snippet = r.get("snippet", "")[:100]
            lines.append(f"• <b>{title}</b> <code>{path}</code>")
            if snippet:
                lines.append(f"  {snippet}")

        server.tg.send(server.user_id, "\n".join(lines), None, "HTML")
    except Exception as e:
        server.tg.send(server.user_id, f"Search error: {e}")


@command("backlink")
def cmd_backlink(server, upd, cmd):
    """Show backlinks for a page."""
    page = cmd.data.get("page", "") if cmd.data else ""
    if not page:
        server.db.set_input_expectation(cmd)
        server.tg.send(server.user_id, "Enter page name to find backlinks:")
        return

    try:
        from nas_md.search import init_db, query_backlinks

        init_db()
        backlinks = query_backlinks(page)
        if not backlinks:
            server.tg.send(server.user_id, f"No backlinks to: {page}")
            return

        lines = [f"Backlinks to <b>{page}</b>:\n"]
        for bl in backlinks:
            title = bl.get("title", bl.get("path", "Unknown"))
            path = bl.get("path", "")
            line = bl.get("line", "")
            lines.append(f"• <b>{title}</b> <code>{path}</code> (line {line})")

        server.tg.send(server.user_id, "\n".join(lines), None, "HTML")
    except Exception as e:
        server.tg.send(server.user_id, f"Backlink error: {e}")


@command("inlineQuery")
def cmd_inline_query(server, upd, cmd):
    """Handle inline query for search autocomplete."""
    query = cmd.data.get("q", "") if cmd.data else ""
    if not query:
        return

    try:
        from nas_md.search import init_db, search as fts_search

        init_db()
        results = fts_search(query, limit=5)
        # Return as inline results
        server.tg.send(server.user_id, str(results))
    except Exception:
        pass


@command("webApp")
def cmd_web_app(server, upd, cmd):
    """Open web app."""
    from nas_md.config import server_cfg

    url = f"http://{server_cfg.host}:{server_cfg.port}"
    server.tg.send(server.user_id, f"Open web app: {url}")


@command("url")
def cmd_url(server, upd, cmd):
    """Handle URL."""
    server.tg.send(server.user_id, "URL handling - not yet implemented in modular form.")
