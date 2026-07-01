import asyncio


async def test_pytest_asyncio_is_configured() -> None:
    await asyncio.sleep(0)
    assert True
