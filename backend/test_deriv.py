import asyncio
import os
from dotenv import load_dotenv

load_dotenv()

async def test_deriv():
    from app.adapters.brokers.deriv_adapter import DerivAdapter
    from app.adapters.brokers.base import AdapterHealth
    from app.bots.models import BrokerConfig
    
    token = os.getenv("DERIV_API_TOKEN")
    if not token:
        print("DERIV_API_TOKEN not found in env")
        return
        
    print(f"Token found: {token[:10]}...")
    
    # Create a dummy config
    config = BrokerConfig(
        type="deriv",
        environment="demo",
        account_id="demo",
        credential_ref="DERIV_API_TOKEN",
        symbol_namespace="deriv",
        app_id="1089"
    )
    
    adapter = DerivAdapter(config)
    
    try:
        await adapter.connect()
        print("WebSocket connected.")
        
        health = await adapter.health_check()
        print("Health status:", health)
        
        if health == AdapterHealth.HEALTHY:
            print("Deriv trading adapter is fully online and ready for execution.")
        
        await adapter.close()
    except Exception as e:
        print("Error:", e)

if __name__ == "__main__":
    asyncio.run(test_deriv())
