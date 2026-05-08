import asyncio
from app.bots import service as bot_service
from app.runtime.manager import get_runtime_manager
from app.auth.models import User, UserRole

async def restart(bot_id: str):
    user = User(id="system", email="system@brindle.ai", role=UserRole.SUPER_ADMIN)
    print(f"Stopping {bot_id}...")
    try:
        bot_service.stop(bot_id, actor_email=user.email, actor_role=user.role.value)
        await get_runtime_manager().stop(bot_id)
    except Exception as e:
        print(f"Stop failed (might already be stopped): {e}")
    
    print(f"Starting {bot_id}...")
    bot = bot_service.start(bot_id, actor_email=user.email, actor_role=user.role.value)
    await get_runtime_manager().start(bot)
    print(f"Started {bot_id}")

async def main():
    await restart("bot_fad5affd27c1")
    await restart("bot_07ac123caaa1")

if __name__ == "__main__":
    import os
    import sys
    sys.path.append(os.getcwd())
    asyncio.run(main())
