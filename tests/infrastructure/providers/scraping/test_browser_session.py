"""PlaywrightBrowserSession lifecycle tests against the fake playwright stack
from `fakes.py` - `async_playwright` is monkeypatched, so nothing real starts.
"""

import pytest
from playwright.async_api import Error as PlaywrightError

import src.infrastructure.providers.scraping.browser as browser_module
from src.infrastructure.providers.scraping.browser import (
    DEFAULT_USER_AGENT,
    PlaywrightBrowserSession,
)
from src.infrastructure.providers.scraping.exceptions import ScrapingError
from tests.infrastructure.providers.scraping.fakes import FakeAsyncPlaywright, FakePlaywrightDriver


@pytest.fixture
def driver(monkeypatch: pytest.MonkeyPatch) -> FakePlaywrightDriver:
    fake_driver = FakePlaywrightDriver()
    monkeypatch.setattr(
        browser_module, "async_playwright", lambda: FakeAsyncPlaywright(fake_driver)
    )
    return fake_driver


async def test_session_launches_headless_with_realistic_fingerprint(
    driver: FakePlaywrightDriver,
) -> None:
    async with PlaywrightBrowserSession() as session:
        page = await session.new_page()

    assert driver.chromium.launch_kwargs == {"headless": True}
    assert driver.chromium.browser.new_context_kwargs == {
        "user_agent": DEFAULT_USER_AGENT,
        "viewport": {"width": 1366, "height": 768},
    }
    assert page in driver.chromium.browser.context.pages


async def test_session_configuration_is_passed_through(driver: FakePlaywrightDriver) -> None:
    session = PlaywrightBrowserSession(
        headless=False, user_agent="custom-agent", viewport_width=1920, viewport_height=1080
    )
    async with session:
        pass

    assert driver.chromium.launch_kwargs == {"headless": False}
    assert driver.chromium.browser.new_context_kwargs == {
        "user_agent": "custom-agent",
        "viewport": {"width": 1920, "height": 1080},
    }


async def test_exiting_the_context_manager_releases_every_resource(
    driver: FakePlaywrightDriver,
) -> None:
    async with PlaywrightBrowserSession():
        pass

    assert driver.chromium.browser.context.closed is True
    assert driver.chromium.browser.closed is True
    assert driver.stopped is True


async def test_new_page_requires_a_started_session() -> None:
    session = PlaywrightBrowserSession()
    with pytest.raises(ScrapingError):
        await session.new_page()


async def test_launch_failures_are_translated_and_the_driver_is_stopped(
    driver: FakePlaywrightDriver,
) -> None:
    driver.chromium.launch_failure = PlaywrightError("executable doesn't exist")

    with pytest.raises(ScrapingError):
        await PlaywrightBrowserSession().start()
    assert driver.stopped is True


async def test_non_playwright_startup_failures_propagate_after_cleanup(
    driver: FakePlaywrightDriver,
) -> None:
    driver.chromium.browser.new_context_failure = RuntimeError("boom")

    with pytest.raises(RuntimeError):
        await PlaywrightBrowserSession().start()
    assert driver.chromium.browser.closed is True
    assert driver.stopped is True


async def test_close_releases_the_rest_of_the_stack_even_if_one_step_fails(
    driver: FakePlaywrightDriver,
) -> None:
    driver.chromium.browser.context.close_failure = RuntimeError("context already gone")

    session = PlaywrightBrowserSession()
    await session.start()
    with pytest.raises(RuntimeError):
        await session.close()

    assert driver.chromium.browser.closed is True
    assert driver.stopped is True


async def test_close_is_a_noop_when_never_started() -> None:
    await PlaywrightBrowserSession().close()  # must not raise


async def test_close_is_idempotent(driver: FakePlaywrightDriver) -> None:
    session = PlaywrightBrowserSession()
    await session.start()
    await session.close()
    await session.close()  # second call: everything already handed off

    with pytest.raises(ScrapingError):
        await session.new_page()
