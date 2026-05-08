from fastapi import APIRouter, Depends
from app.auth.deps import require
from app.auth.models import User
from app.bots import service as bot_service
from app.configs.service import active_version
from app.adapters.brokers.factory import create_adapter
from pydantic import BaseModel

router = APIRouter(prefix="/api/brokers", tags=["brokers"])

class BrokerBalance(BaseModel):
    broker_type: str
    account_id: str
    environment: str
    available: float | None
    currency: str | None
    error: str | None = None

@router.get("/balances")
async def list_broker_balances(user: User = Depends(require("bot:read"))) -> list[BrokerBalance]:
    """List balances for all unique broker accounts used by the bots."""
    bots = bot_service.list_bots()
    unique_brokers = {} # key: (type, account_id)
    
    for bot in bots:
        cv = active_version(bot.id)
        if not cv:
            continue
        bc = cv.config.broker
        key = (bc.type, bc.account_id, bc.environment)
        if key not in unique_brokers:
            unique_brokers[key] = bc
            
    results = []
    for (btype, account_id, env), config in unique_brokers.items():
        try:
            adapter = create_adapter(config)
            await adapter.connect()
            try:
                balances = await adapter.get_balance()
                if balances:
                    b = balances[0]
                    results.append(BrokerBalance(
                        broker_type=btype,
                        account_id=account_id,
                        environment=env,
                        available=b.available,
                        currency=b.currency
                    ))
                else:
                    results.append(BrokerBalance(
                        broker_type=btype,
                        account_id=account_id,
                        environment=env,
                        available=None,
                        currency=None,
                        error="No balances returned"
                    ))
            finally:
                await adapter.close()
        except Exception as e:
            results.append(BrokerBalance(
                broker_type=btype,
                account_id=account_id,
                environment=env,
                available=None,
                currency=None,
                error=str(e)[:200]
            ))
            
    return results
