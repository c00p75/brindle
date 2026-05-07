import os
import sys
import json

# Add current dir to path
sys.path.append(os.getcwd())

import dotenv
dotenv.load_dotenv(".env")

from app.bots import service as bot_svc
from app.configs import service as config_svc
from app.bots.models import BotState

def repair():
    bots = bot_svc.list_bots()
    # Filter non-archived
    bots = [b for b in bots if b.state != BotState.ARCHIVED]
    
    print(f"Checking {len(bots)} active bots for risk cap repair...")
    
    repaired_count = 0
    
    for bot in bots:
        active = config_svc.active_version(bot.id)
        if not active:
            print(f"Skipping {bot.name} ({bot.id}): no active config")
            continue
            
        cfg = active.config
        risk = cfg.risk
        
        # Check if they are using the "old broken defaults"
        # max_position_notional: 5000
        # max_total_exposure: 20000
        # max_daily_loss: 500
        is_default = (
            risk.max_position_notional == 5000 and
            risk.max_total_exposure == 20000 and
            risk.max_daily_loss == 500
        )
        
        if not is_default:
            print(f"Skipping {bot.name} ({bot.id}): user has custom risk caps or already repaired")
            continue
            
        # Repair!
        alloc = bot.allocation or 100.0
        new_risk = risk.model_copy(update={
            "max_position_notional": alloc,
            "max_total_exposure": alloc * 5.0,
            "max_daily_loss": max(20.0, alloc * 0.3),
            "max_drawdown_pct": 25.0,
            "risk_per_trade_pct": 10.0,
        })
        
        # Clean up strategy params: remove 'qty' to prefer risk_per_trade_pct sizing
        new_params = dict(cfg.strategy.params or {})
        if "qty" in new_params:
            del new_params["qty"]
            
        new_cfg = cfg.model_copy(update={
            "risk": new_risk,
            "strategy": cfg.strategy.model_copy(update={"params": new_params})
        })
        
        print(f"Repairing {bot.name} ({bot.id}): ${alloc} alloc. Caps {risk.max_position_notional}/{risk.max_daily_loss} -> {new_risk.max_position_notional}/{new_risk.max_daily_loss}")
        
        # Submit and apply
        try:
            draft = config_svc.create_draft(
                actor_email="system",
                actor_role="system",
                config=new_cfg
            )
            config_svc.validate(
                actor_email="system",
                actor_role="system",
                bot_id=bot.id,
                version=draft.version
            )
            config_svc.apply(
                actor_email="system",
                actor_role="system",
                bot_id=bot.id,
                version=draft.version,
                typed_confirmation="APPLY RISK CHANGE"
            )
            repaired_count += 1
        except Exception as e:
            print(f"Failed to repair {bot.id}: {e}")
            
    print(f"\nDone. Repaired {repaired_count} bots.")
    print("NOTE: Bots were NOT automatically restarted. Please review the alerts and restart them manually.")

if __name__ == "__main__":
    repair()
