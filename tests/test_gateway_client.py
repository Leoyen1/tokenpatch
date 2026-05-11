import httpx

from mmdev.models.gateway_client import MMDevGatewayClient


def test_gateway_client_posts_structured_request_and_maps_response(monkeypatch):
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
                "patch": "diff --git a/a.py b/a.py\n--- a/a.py\n+++ b/a.py\n",
                "changed_files": ["a.py"],
                "summary": "done",
                "risks": [],
                "verification_hint": "pytest",
                "usage": {"input_tokens": 11, "output_tokens": 22},
                "charged_credits": 0.12,
                "provider_cost": 0.03,
            },
        )

    monkeypatch.setattr(httpx, "post", fake_post)
    result = MMDevGatewayClient(
        "https://gateway.example.test/",
        "secret",
        country="SG",
        entity="tenant-001",
    ).complete(
        prompt="bounded task",
        model="gateway-executor",
        timeout_seconds=12,
    )

    assert captured["url"] == "https://gateway.example.test/v1/executor/run"
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["headers"]["X-MMDEV-Country"] == "SG"
    assert captured["headers"]["X-MMDEV-Entity"] == "tenant-001"
    assert captured["json"]["protocol"] == "mmdev.executor.v1"
    assert captured["json"]["prompt"] == "bounded task"
    assert result.input_tokens == 11
    assert result.output_tokens == 22
    assert result.charged_credits == 0.12
    assert result.provider_cost == 0.03
    assert '"changed_files": ["a.py"]' in result.text
