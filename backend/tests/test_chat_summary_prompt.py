from app.api import chat_routes


def test_build_summary_input_skips_empty():
    text = chat_routes._build_summary_input(
        [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": ""},
        ]
    )
    assert "user: hello" in text
    assert "assistant:" not in text

