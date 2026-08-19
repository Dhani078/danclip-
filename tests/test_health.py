import asyncio
import traceback
from main import health_check
async def test():
    print(await health_check())
asyncio.run(test())
