from __future__ import annotations

import json
from dataclasses import dataclass
from itertools import count
from urllib.error import URLError
from urllib.request import urlopen
from urllib.parse import urlparse


@dataclass(frozen=True)
class PlaywrightCdpSettings:
    endpoint_url: str
    operation_timeout_ms: int = 15000


class PlaywrightCdpError(RuntimeError):
    pass


class RawCdpClient:
    def __init__(self, endpoint_url: str, timeout_seconds: float):
        self.endpoint_url = endpoint_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self._ids = count(1)

    def evaluate(self, js: str, current_url: str = ""):
        websocket_url = self._select_page_websocket_url(current_url)
        try:
            from websocket import create_connection
        except ImportError as exc:
            raise PlaywrightCdpError(
                "Python package 'websocket-client' is not installed. "
                "Install it with: python -m pip install websocket-client"
            ) from exc

        websocket = create_connection(websocket_url, timeout=self.timeout_seconds)
        try:
            response = self._send_command(
                websocket,
                "Runtime.evaluate",
                {
                    "expression": js,
                    "awaitPromise": True,
                    "returnByValue": True,
                    "userGesture": True,
                },
            )
        finally:
            websocket.close()

        if "exceptionDetails" in response:
            raise PlaywrightCdpError(json.dumps(response["exceptionDetails"], indent=2))

        remote_result = response.get("result", {}).get("result", {})
        if "value" in remote_result:
            return remote_result["value"]
        if "description" in remote_result:
            return remote_result["description"]
        return None

    def _send_command(self, websocket, method: str, params: dict[str, object]):
        command_id = next(self._ids)
        websocket.send(json.dumps({"id": command_id, "method": method, "params": params}))

        while True:
            message = json.loads(websocket.recv())
            if message.get("id") != command_id:
                continue
            if "error" in message:
                raise PlaywrightCdpError(json.dumps(message["error"], indent=2))
            return message

    def _select_page_websocket_url(self, current_url: str) -> str:
        targets = self._get_targets()
        pages = [
            target
            for target in targets
            if target.get("type") == "page" and target.get("webSocketDebuggerUrl")
        ]
        if not pages:
            raise PlaywrightCdpError("No QtWebEngine page target was visible through CDP.")

        normalized_current = (current_url or "").rstrip("/")
        if normalized_current:
            for page in pages:
                if str(page.get("url", "")).rstrip("/") == normalized_current:
                    return str(page["webSocketDebuggerUrl"])

            current_host = urlparse(current_url).hostname
            if current_host:
                for page in pages:
                    if urlparse(str(page.get("url", ""))).hostname == current_host:
                        return str(page["webSocketDebuggerUrl"])

        for page in pages:
            if page.get("url") and page.get("url") != "about:blank":
                return str(page["webSocketDebuggerUrl"])
        return str(pages[0]["webSocketDebuggerUrl"])

    def _get_targets(self) -> list[dict[str, object]]:
        try:
            with urlopen(f"{self.endpoint_url}/json", timeout=self.timeout_seconds) as response:
                data = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, json.JSONDecodeError) as exc:
            raise PlaywrightCdpError(f"Could not read CDP targets from {self.endpoint_url}: {exc}") from exc

        if not isinstance(data, list):
            raise PlaywrightCdpError(f"Unexpected CDP target list from {self.endpoint_url}.")
        return [target for target in data if isinstance(target, dict)]


class PlaywrightCdpEvaluator:
    def __init__(self, settings: PlaywrightCdpSettings):
        self.settings = settings
        self.last_transport = "playwright"

    def evaluate(self, js: str, current_url: str = ""):
        self.last_transport = "playwright"
        try:
            from playwright.sync_api import Error as PlaywrightError
            from playwright.sync_api import sync_playwright
        except ImportError as exc:
            raise PlaywrightCdpError(
                "Python package 'playwright' is not installed. "
                "Install it with: python -m pip install playwright"
            ) from exc

        try:
            with sync_playwright() as playwright:
                browser = playwright.chromium.connect_over_cdp(
                    self.settings.endpoint_url,
                    timeout=self.settings.operation_timeout_ms,
                )
                page = self._select_page(browser, current_url)
                page.set_default_timeout(self.settings.operation_timeout_ms)
                return page.evaluate(js)
        except PlaywrightError as exc:
            if self._should_fallback_to_raw_cdp(str(exc)):
                self.last_transport = "raw-cdp"
                return RawCdpClient(
                    self.settings.endpoint_url,
                    self.settings.operation_timeout_ms / 1000,
                ).evaluate(js, current_url=current_url)
            raise PlaywrightCdpError(str(exc)) from exc

    @staticmethod
    def _should_fallback_to_raw_cdp(error: str) -> bool:
        return (
            "Browser.setDownloadBehavior" in error
            and "Browser context management is not supported" in error
        )

    @staticmethod
    def _select_page(browser, current_url: str):
        pages = [
            page
            for context in browser.contexts
            for page in context.pages
            if not page.url.startswith("devtools://")
        ]
        if not pages:
            raise PlaywrightCdpError("No QtWebEngine page was visible through CDP.")

        normalized_current = (current_url or "").rstrip("/")
        if normalized_current:
            for page in pages:
                if page.url.rstrip("/") == normalized_current:
                    return page

            current_host = urlparse(current_url).hostname
            if current_host:
                for page in pages:
                    if urlparse(page.url).hostname == current_host:
                        return page

        for page in pages:
            if page.url and page.url != "about:blank":
                return page
        return pages[0]
