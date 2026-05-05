import importlib
import os
import sys
import uuid


def _reload_settings_with_data_dir(tmp_path, monkeypatch):
    """为本测试用例隔离 data-dir，并确保后续导入都绑定到新的 settings 实例。"""
    data_dir = tmp_path / "backend-data"
    data_dir.mkdir(parents=True, exist_ok=True)

    monkeypatch.setattr(sys, "argv", ["backend", "--data-dir", str(data_dir)])

    settings_module = importlib.import_module("app.config.settings")
    settings_module = importlib.reload(settings_module)

    # 关键：app.config.__init__ 会 `from .settings import settings`，需要一起 reload
    config_pkg = importlib.import_module("app.config")
    importlib.reload(config_pkg)

    # 同步 reload 存储层，让 `from app.storage import SQLiteStore` 等导入拿到同一份 settings
    storage_pkg = importlib.import_module("app.storage")
    importlib.reload(storage_pkg)
    sqlite_store_module = importlib.import_module("app.storage.sqlite_store")
    importlib.reload(sqlite_store_module)

    return settings_module.settings


def _fresh_store():
    storage_pkg = importlib.import_module("app.storage")
    importlib.reload(storage_pkg)
    sqlite_store_module = importlib.import_module("app.storage.sqlite_store")
    sqlite_store_module = importlib.reload(sqlite_store_module)
    return sqlite_store_module.SQLiteStore()


def test_recent_by_layer_returns_latest(tmp_path, monkeypatch):
    _reload_settings_with_data_dir(tmp_path, monkeypatch)
    store = _fresh_store()

    old_id = str(uuid.uuid4())
    new_id = str(uuid.uuid4())

    store.create(memory_id=old_id, content="old", category="conversation", layer=1, tags=["对话记录"])

    # 手动把第一条的 created_at 调整为更早，避免相同时间戳导致顺序不稳定
    conn = store._get_conn()  # noqa: SLF001（测试内部允许）
    cur = conn.cursor()
    cur.execute("UPDATE memories SET created_at = '2000-01-01 00:00:00', updated_at = '2000-01-01 00:00:00' WHERE id = ?", (old_id,))
    conn.commit()

    store.create(memory_id=new_id, content="new", category="conversation", layer=1, tags=["对话记录"])

    recent = store.get_recent_by_layer(1, limit=1)
    assert len(recent) == 1
    assert recent[0]["id"] == new_id


def test_openclaw_preference_settings_defaults(tmp_path, monkeypatch):
    settings = _reload_settings_with_data_dir(tmp_path, monkeypatch)

    assert getattr(settings, "openclaw_preference_enable_l1_fallback") is True
    assert int(getattr(settings, "openclaw_preference_l1_recent_n")) == 30
    assert getattr(settings, "openclaw_preference_disable_cache") is True
    expands = list(getattr(settings, "openclaw_preference_keyword_expands"))
    for w in ("喜欢", "偏好", "不喜欢", "习惯", "风格", "格式"):
        assert w in expands


def test_preference_query_filters_categories_and_falls_back_to_l1(tmp_path, monkeypatch):
    _reload_settings_with_data_dir(tmp_path, monkeypatch)
    store = _fresh_store()

    # 1) L4 的 preference（应命中）
    pref_id = str(uuid.uuid4())
    store.create(
        memory_id=pref_id,
        content="## 用户偏好\n我喜欢用 VSCode。",
        category="preference",
        layer=4,
        tags=["用户偏好"],
    )

    # 2) 同样内容但 category=conversation（不应影响 preference 主结果；但允许 L1 兜底）
    conv_id = str(uuid.uuid4())
    store.create(
        memory_id=conv_id,
        content="我喜欢用 VSCode 作为主要开发工具。",
        category="conversation",
        layer=1,
        tags=["对话记录"],
    )

    retrieval_mod = importlib.import_module("app.services.retrieval_service")
    retrieval_mod = importlib.reload(retrieval_mod)
    retrieval_service = retrieval_mod.retrieval_service

    # 贴近 OpenClaw 固定查询词：包含中文偏好关键词，保证 keyword path 可命中
    result = retrieval_service.query("用户偏好 喜欢", categories=["preference"], limit=10)
    memories = result.get("memories") or []

    # L4/L6/L2 必须严格为 preference 分类
    for m in memories:
        if m.get("layer") in (2, 4, 6):
            assert m.get("category") == "preference"

    # 至少能看到 L4 偏好（如果未命中，将会触发更明显的失败）
    assert any("VSCode" in (m.get("content") or "") for m in memories)


def test_preference_query_works_when_embedding_unavailable(tmp_path, monkeypatch):
    _reload_settings_with_data_dir(tmp_path, monkeypatch)
    store = _fresh_store()

    pref_id = str(uuid.uuid4())
    store.create(
        memory_id=pref_id,
        content="## 用户偏好\n我喜欢用 VSCode。",
        category="preference",
        layer=4,
        tags=["用户偏好"],
    )

    # monkeypatch embedding 不可用：强制返回空向量
    emb_mod = importlib.import_module("app.services.embedding_service")
    emb_mod = importlib.reload(emb_mod)
    monkeypatch.setattr(emb_mod.embedding_service, "embed_text", lambda *args, **kwargs: [])

    retrieval_mod = importlib.import_module("app.services.retrieval_service")
    retrieval_mod = importlib.reload(retrieval_mod)
    retrieval_service = retrieval_mod.retrieval_service

    # degraded 模式下会强制走 keyword + 中文扩展
    result = retrieval_service.query("我喜欢什么", categories=["preference"], limit=10)
    memories = result.get("memories") or []
    assert any("VSCode" in (m.get("content") or "") for m in memories)


def test_preference_query_keeps_short_l1_preference_sentence(tmp_path, monkeypatch):
    """回归：短偏好句（例如“我不喜欢下雨天”）不能被 post_retrieval_dedup 当作垃圾过滤掉。"""
    _reload_settings_with_data_dir(tmp_path, monkeypatch)
    store = _fresh_store()

    short_id = str(uuid.uuid4())
    store.create(
        memory_id=short_id,
        content="我不喜欢下雨天",
        category="conversation",
        layer=1,
        tags=["对话记录"],
    )

    retrieval_mod = importlib.import_module("app.services.retrieval_service")
    retrieval_mod = importlib.reload(retrieval_mod)
    retrieval_service = retrieval_mod.retrieval_service

    # 贴近真实 OpenClaw：query 中包含 “不喜欢”，即使 categories 不传也会触发 preference 兜底
    result = retrieval_service.query("我不喜欢什么", categories=None, limit=10)
    memories = result.get("memories") or []
    assert any("下雨天" in (m.get("content") or "") for m in memories)
