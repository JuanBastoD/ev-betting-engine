"""Hand-rolled fakes for the (tiny) Playwright surface the scrapers touch.

No test in this package ever launches a browser or opens a socket: `FakePage`
stands in for `playwright.async_api.Page`, and the `Fake*` browser stack
stands in for the object chain returned by `async_playwright()`.

Failure queues (`goto_failures`, `wait_failures`, ...) are consumed one
exception per call, so a test can script "fail twice, then succeed" and
exercise the retry paths without real waits.
"""


class FakePage:
    def __init__(self, html_by_selector: dict[str, str] | None = None) -> None:
        self.html_by_selector = dict(html_by_selector or {})
        self.goto_calls: list[str] = []
        self.wait_calls: list[str] = []
        self.click_calls: list[str] = []
        self.closed = False
        self.goto_failures: list[Exception] = []
        self.wait_failures: dict[str, list[Exception]] = {}
        self.click_failures: list[Exception] = []
        self.inner_html_failures: list[Exception] = []

    async def goto(self, url: str, *, timeout: float | None = None, wait_until: str | None = None) -> None:
        self.goto_calls.append(url)
        if self.goto_failures:
            raise self.goto_failures.pop(0)

    async def wait_for_selector(self, selector: str, *, timeout: float | None = None) -> None:
        self.wait_calls.append(selector)
        queue = self.wait_failures.get(selector)
        if queue:
            raise queue.pop(0)

    async def inner_html(self, selector: str) -> str:
        if self.inner_html_failures:
            raise self.inner_html_failures.pop(0)
        return self.html_by_selector[selector]

    async def click(self, selector: str, *, timeout: float | None = None) -> None:
        self.click_calls.append(selector)
        if self.click_failures:
            raise self.click_failures.pop(0)

    async def close(self) -> None:
        self.closed = True


class FakeBrowserSession:
    """Stands in for PlaywrightBrowserSession in provider tests: always hands
    out the single preconfigured page."""

    def __init__(self, page: FakePage) -> None:
        self.page = page

    async def new_page(self) -> FakePage:
        return self.page


class FakeContext:
    def __init__(self) -> None:
        self.closed = False
        self.close_failure: Exception | None = None
        self.pages: list[FakePage] = []

    async def new_page(self) -> FakePage:
        page = FakePage()
        self.pages.append(page)
        return page

    async def close(self) -> None:
        if self.close_failure is not None:
            raise self.close_failure
        self.closed = True


class FakeBrowser:
    def __init__(self) -> None:
        self.closed = False
        self.context = FakeContext()
        self.new_context_kwargs: dict | None = None
        self.new_context_failure: Exception | None = None

    async def new_context(self, **kwargs) -> FakeContext:
        self.new_context_kwargs = kwargs
        if self.new_context_failure is not None:
            raise self.new_context_failure
        return self.context

    async def close(self) -> None:
        self.closed = True


class FakeBrowserType:
    def __init__(self) -> None:
        self.browser = FakeBrowser()
        self.launch_kwargs: dict | None = None
        self.launch_failure: Exception | None = None

    async def launch(self, **kwargs) -> FakeBrowser:
        self.launch_kwargs = kwargs
        if self.launch_failure is not None:
            raise self.launch_failure
        return self.browser


class FakePlaywrightDriver:
    """What `async_playwright().start()` resolves to."""

    def __init__(self) -> None:
        self.stopped = False
        self.chromium = FakeBrowserType()

    async def stop(self) -> None:
        self.stopped = True


class FakeAsyncPlaywright:
    """What the `async_playwright()` call itself returns."""

    def __init__(self, driver: FakePlaywrightDriver) -> None:
        self._driver = driver

    async def start(self) -> FakePlaywrightDriver:
        return self._driver
