"""A real headless browser executes inert fixture JS; no paid service is contacted."""
import pytest
from src import scrapling_engine


@pytest.mark.asyncio
async def test_actual_browser_executes_fixture_javascript(monkeypatch):
    from scrapling.fetchers import Fetcher, StealthyFetcher
    original = StealthyFetcher.fetch
    marker = "JSEXECUTEDOWNER20261027"
    html = "<html><body><main id='output'>Before JavaScript</main><script>document.getElementById('output').textContent='" + marker + "';</script></body></html>"
    # Intercept a public fixture URL inside the actual browser, keeping all other guards.
    def browser_fixture(url, **kwargs):
        original_setup = kwargs["page_setup"]
        def setup(page):
            original_setup(page)
            page.route("**/owner-js-fixture", lambda route: route.fulfill(status=200, content_type="text/html", body=html))
        return original(url, **{**kwargs, "page_setup": setup})
    monkeypatch.setattr(StealthyFetcher, "fetch", browser_fixture)
    monkeypatch.setattr(Fetcher, "get", lambda *a, **kw: pytest.fail("Actual browser test may not use a static fallback"))
    result = await scrapling_engine.stealth_scrape_and_sanitize("https://example.org/owner-js-fixture", render_js=True)
    assert result["status_code"] == 200 and result["fetch_method"] == "scrapling_stealthy_browser"
    assert marker in result["token_compressed_markdown"] and "Before JavaScript" not in result["token_compressed_markdown"]
