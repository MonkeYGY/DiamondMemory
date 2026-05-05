import importlib


def test_chat_settings_defaults():
    settings_module = importlib.import_module("app.config.settings")
    settings_module = importlib.reload(settings_module)
    s = settings_module.settings

    assert int(getattr(s, "chat_memory_limit_greeting")) == 3
    assert int(getattr(s, "chat_memory_limit_normal")) == 6
    assert int(getattr(s, "chat_greeting_recent_n")) == 30
    assert float(getattr(s, "chat_greeting_min_score")) == 0.55

    assert bool(getattr(s, "chat_auto_summary_enabled")) is True
    assert int(getattr(s, "chat_auto_summary_trigger_token")) == 300
    assert int(getattr(s, "chat_auto_summary_max_tokens")) == 600


def test_detect_intent_greeting():
    from app.api import chat_routes

    assert chat_routes.detect_intent("你好") == "greeting"
    assert chat_routes.detect_intent(" hi ") == "greeting"


def test_detect_intent_preference():
    from app.api import chat_routes

    assert chat_routes.detect_intent("我喜欢喝茶") == "preference"


def test_detect_intent_normal():
    from app.api import chat_routes

    assert chat_routes.detect_intent("为什么会超出上下文？") == "normal"
