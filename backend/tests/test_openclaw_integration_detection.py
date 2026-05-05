import importlib


def test_is_agent_integrated_uses_marker_only(tmp_path, monkeypatch):
    mod = importlib.import_module("app.services.openclaw_service")
    importlib.reload(mod)

    openclaw_home = tmp_path / ".openclaw"
    ws = openclaw_home / "workspace-agent-1"
    ws.mkdir(parents=True, exist_ok=True)

    (ws / "MEMORY.md").write_text("这里提到钻石记忆系统，但不代表已集成。", encoding="utf-8")

    monkeypatch.setattr(mod, "OPENCLAW_HOME", str(openclaw_home))
    assert mod.openclaw_service.is_agent_integrated("agent-1") is False

    (ws / "HEARTBEAT.md").write_text(f"{mod.DM_SECTION_START}\nX\n{mod.DM_SECTION_END}\n", encoding="utf-8")
    assert mod.openclaw_service.is_agent_integrated("agent-1") is True


def test_remove_section_tolerates_missing_end_marker(tmp_path, monkeypatch):
    mod = importlib.import_module("app.services.openclaw_service")
    importlib.reload(mod)

    openclaw_home = tmp_path / ".openclaw"
    ws = openclaw_home / "workspace-agent-2"
    ws.mkdir(parents=True, exist_ok=True)

    p = ws / "MEMORY.md"
    p.write_text(f"KEEP\n{mod.DM_SECTION_START}\nREMOVED\n", encoding="utf-8")

    monkeypatch.setattr(mod, "OPENCLAW_HOME", str(openclaw_home))
    mod.openclaw_service._remove_section(str(p))

    content = p.read_text(encoding="utf-8")
    assert mod.DM_SECTION_START not in content
    assert "KEEP" in content

