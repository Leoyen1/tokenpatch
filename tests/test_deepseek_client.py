import httpx

from mmdev.models.deepseek_client import DeepSeekChatClient


def test_deepseek_client_posts_official_chat_completion_shape(monkeypatch):
    captured = {}

    def fake_post(url, headers, json, timeout):
        captured["url"] = url
        captured["headers"] = headers
        captured["json"] = json
        captured["timeout"] = timeout
        return httpx.Response(
            200,
            request=httpx.Request("POST", url),
            json={
                "choices": [{"message": {"content": '{"ok": true}'}}],
                "usage": {"prompt_tokens": 12, "completion_tokens": 3},
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)

    result = DeepSeekChatClient("secret", "https://api.deepseek.com/v1").complete(
        prompt='Return JSON: {"ok": true}',
        model="deepseek-v4-pro",
        timeout_seconds=30,
    )

    assert captured["url"] == "https://api.deepseek.com/chat/completions"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["json"]["model"] == "deepseek-v4-pro"
    assert captured["json"]["messages"] == [{"role": "user", "content": 'Return JSON: {"ok": true}'}]
    assert captured["json"]["response_format"] == {"type": "json_object"}
    assert captured["json"]["thinking"] == {"type": "disabled"}
    assert result.text == '{"ok": true}'
    assert result.input_tokens == 12
    assert result.output_tokens == 3
