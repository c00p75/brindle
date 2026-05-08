import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure app is importable
sys.path.append(os.getcwd())

# Load environment variables (DATABASE_URL etc)
load_dotenv()

from app.bots import service as bot_service
from app.configs import service as config_service
from app.runtime.manager import get_runtime_manager

async def fix_and_restart(bot_id: str, new_exposure: float = None):
    print(f"--- Processing {bot_id} ---")
    
    # 1. Update config if needed (for MM and GRID)
    if new_exposure:
        print(f"Updating max_total_exposure to {new_exposure}...")
        av = config_service.active_version(bot_id)
        if av:
            cfg = av.config
            cfg.risk.max_total_exposure = new_exposure
            # Create a new version and apply it
            try:
                new_v = config_service.create_draft(
                    actor_email="system@brindle.ai",
                    actor_role="admin",
                    config=cfg
                )
                config_service.validate(
                    actor_email="system@brindle.ai",
                    actor_role="admin",
                    bot_id=bot_id,
                    version=new_v.version
                )
                config_service.approve(
                    actor_email="system@brindle.ai",
                    actor_role="admin",
                    bot_id=bot_id,
                    version=new_v.version
                )
                config_service.apply(
                    actor_email="system@brindle.ai",
                    actor_role="admin",
                    bot_id=bot_id,
                    version=new_v.version,
                    typed_confirmation="APPLY RISK CHANGE"
                )
                print(f"Applied new config v{new_v.version}")
            except Exception as e:
                print(f"Config update failed: {e}")
        else:
            print(f"No active config found for {bot_id}")

    # 2. Reset baseline (for VOL BREAKOUT and others for safety)
    print(f"Resetting baseline for {bot_id}...")
    bot_service.reset_starting_balance(bot_id)

    # 3. Stop and Start
    print(f"Restarting {bot_id}...")
    try:
        # Halt if running/paused to clear state
        bot_service.stop(bot_id, actor_email="system@brindle.ai", actor_role="admin")
        await get_runtime_manager().stop(bot_id)
    except Exception as e:
        print(f"Stop failed: {e}")

    try:
        # Start fresh
        bot = bot_service.start(bot_id, actor_email="system@brindle.ai", actor_role="admin")
        await get_runtime_manager().start(bot)
        print(f"Successfully started {bot_id}")
    except Exception as e:
        print(f"Start failed: {e}")

async def main():
    # MM V1
    await fix_and_restart("bot_07ac123caaa1", new_exposure=500.0)
    # GRID V1
    await fix_and_restart("bot_fad5affd27c1", new_exposure=500.0)
    # VOL BREAKOUT V1
    await fix_and_restart("bot_432b3b7de51f")

if __name__ == "__main__":
    asyncio.run(main())
