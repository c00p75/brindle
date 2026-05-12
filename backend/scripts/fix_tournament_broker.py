import asyncio
import os
import sys
from dotenv import load_dotenv

# Ensure app is importable
sys.path.append(os.getcwd())

# Load environment variables
load_dotenv()

from app.bots import service as bot_service
from app.configs import service as config_service
from app.runtime.manager import get_runtime_manager

# List of bots provided by the user
BOT_IDS = [
    "bot_432b3b7de51f", "bot_bee30d41cc97", "bot_bf1c9ff67fd7", "bot_956cbe5ff6e9", 
    "bot_5f08c68037af", "bot_6132f8295a78", "bot_07ac123caaa1", "bot_1207371ed217", 
    "bot_fad5affd27c1", "bot_c2214040c72a", "bot_be871631618f", "bot_2a7b935ac31e", 
    "bot_a26c1754731d", "bot_b82c41551804", "bot_3244a4c7bacc", "bot_616077e7aad6", 
    "bot_tourn_1"
]

async def fix_broker_config(bot_id: str, account_id: str = "VRTC7003444", credential_ref: str = "secret://env/DERIV_API_TOKEN"):
    print(f"--- Fixing {bot_id} ---")
    
    # 1. Fetch active config
    av = config_service.active_version(bot_id)
    if not av:
        print(f"  ⚠️  No active config found for {bot_id}, skipping.")
        return

    cfg = av.config
    
    # Check if update is actually needed
    if cfg.broker.account_id == account_id and cfg.broker.credential_ref == credential_ref:
        print(f"  ✓  {bot_id} already has correct broker config.")
        return

    print(f"  Updating broker: {cfg.broker.account_id} -> {account_id}")
    
    # 2. Update broker fields
    cfg.broker.account_id = account_id
    cfg.broker.credential_ref = credential_ref
    
    # 3. Create, Validate, Approve, Apply
    try:
        actor = "system/fixer"
        role = "admin"
        
        new_v = config_service.create_draft(actor_email=actor, actor_role=role, config=cfg)
        config_service.validate(actor_email=actor, actor_role=role, bot_id=bot_id, version=new_v.version)
        config_service.approve(actor_email=actor, actor_role=role, bot_id=bot_id, version=new_v.version)
        config_service.apply(actor_email=actor, actor_role=role, bot_id=bot_id, version=new_v.version, typed_confirmation="APPLY RISK CHANGE")
        
        print(f"  ✅ Applied new config v{new_v.version} for {bot_id}")
        
        # 4. Restart if running
        mgr = get_runtime_manager()
        if mgr.is_running(bot_id):
            print(f"  Restarting runtime for {bot_id}...")
            await mgr.stop(bot_id)
            bot = bot_service.get(bot_id)
            await mgr.start(bot)
            print(f"  ✅ Restarted {bot_id}")
            
    except Exception as e:
        print(f"  ❌ Failed to fix {bot_id}: {e}")

async def main():
    # If the user provides a specific account_id via environment, use it.
    # Otherwise, we use the placeholder VRTC7003444.
    target_account = os.environ.get("TARGET_ACCOUNT_ID", "VRTC7003444")
    
    for bid in BOT_IDS:
        await fix_broker_config(bid, account_id=target_account)

if __name__ == "__main__":
    asyncio.run(main())
