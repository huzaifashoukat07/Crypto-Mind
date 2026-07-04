import asyncio

from app import notifier


class _FakeResponse:
    def __init__(self, status_code=200):
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"http {self.status_code}")


class _FakeAsyncClient:
    response_status = 200
    last_call = None

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    async def post(self, url, json):
        _FakeAsyncClient.last_call = (url, json)
        return _FakeResponse(_FakeAsyncClient.response_status)


def test_is_configured_false_when_unset(monkeypatch):
    monkeypatch.setattr(notifier.settings, "telegram_bot_token", "")
    monkeypatch.setattr(notifier.settings, "telegram_chat_id", "")
    assert notifier.is_configured() is False


def test_is_configured_true_when_both_set(monkeypatch):
    monkeypatch.setattr(notifier.settings, "telegram_bot_token", "TOKEN")
    monkeypatch.setattr(notifier.settings, "telegram_chat_id", "12345")
    assert notifier.is_configured() is True


def test_send_returns_false_when_not_configured(monkeypatch):
    monkeypatch.setattr(notifier.settings, "telegram_bot_token", "")
    monkeypatch.setattr(notifier.settings, "telegram_chat_id", "")
    assert asyncio.run(notifier.send_telegram_message("hello")) is False


def test_send_success_hits_correct_url_and_payload(monkeypatch):
    monkeypatch.setattr(notifier.settings, "telegram_bot_token", "TOKEN")
    monkeypatch.setattr(notifier.settings, "telegram_chat_id", "12345")
    _FakeAsyncClient.response_status = 200
    monkeypatch.setattr(notifier.httpx, "AsyncClient", _FakeAsyncClient)

    result = asyncio.run(notifier.send_telegram_message("hello world"))

    assert result is True
    url, payload = _FakeAsyncClient.last_call
    assert url == "https://api.telegram.org/botTOKEN/sendMessage"
    assert payload == {"chat_id": "12345", "text": "hello world"}


def test_send_failure_returns_false_without_raising(monkeypatch):
    monkeypatch.setattr(notifier.settings, "telegram_bot_token", "TOKEN")
    monkeypatch.setattr(notifier.settings, "telegram_chat_id", "12345")
    _FakeAsyncClient.response_status = 500
    monkeypatch.setattr(notifier.httpx, "AsyncClient", _FakeAsyncClient)

    assert asyncio.run(notifier.send_telegram_message("hello")) is False
