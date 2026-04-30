from __future__ import annotations

from app.alerts import service as alert_service
from app.audit import service as audit_service
from app.bots import service as bot_service
from app.execution import persistence as exec_persistence
from app.research.runner import BacktestManifest, run_backtest
from app.runtime.manager import get_runtime_manager

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_bots",
            "description": "List all trading bots with their current status and state",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bot",
            "description": "Get detailed info about a specific trading bot",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID (e.g. bot_abc123)"},
                },
                "required": ["bot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "start_bot",
            "description": "Start a trading bot that is in READY or PAUSED state",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to start"},
                },
                "required": ["bot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "stop_bot",
            "description": "Stop a running trading bot (sets state to HALTED)",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to stop"},
                },
                "required": ["bot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "pause_bot",
            "description": "Pause a running trading bot temporarily",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to pause"},
                },
                "required": ["bot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_alerts",
            "description": "List alerts from the system",
            "parameters": {
                "type": "object",
                "properties": {
                    "active_only": {
                        "type": "boolean",
                        "description": "If true, only return active (unacknowledged) alerts",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "acknowledge_alert",
            "description": "Acknowledge (dismiss) an alert by ID",
            "parameters": {
                "type": "object",
                "properties": {
                    "alert_id": {"type": "string", "description": "Alert ID to acknowledge"},
                },
                "required": ["alert_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_audit_log",
            "description": "Get the audit log of recent actions in the system",
            "parameters": {
                "type": "object",
                "properties": {
                    "resource_id": {
                        "type": "string",
                        "description": "Optional: filter by resource ID (e.g. a bot ID)",
                    },
                },
                "required": [],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_positions",
            "description": "List current open positions for a bot",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to get positions for"},
                },
                "required": ["bot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_orders",
            "description": "List recent orders for a bot",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to get orders for"},
                    "limit": {"type": "integer", "description": "Max orders to return (default 20)"},
                },
                "required": ["bot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_bot",
            "description": "Create a new trading bot with the given name",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Display name for the bot"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_backtest",
            "description": (
                "Run a backtest simulation for a strategy. "
                "Returns PnL, win rate, Sharpe ratio, and drawdown metrics."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {
                        "type": "string",
                        "description": "Strategy ID to test (e.g. 'trend')",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Symbol to backtest (e.g. 'EUR/USD', 'BTC/USD')",
                    },
                    "bars": {
                        "type": "integer",
                        "description": "Number of price bars to simulate (default 500)",
                    },
                    "params": {
                        "type": "object",
                        "description": "Strategy-specific parameters (key-value pairs)",
                    },
                },
                "required": ["strategy_id", "symbol"],
            },
        },
    },
]


async def execute_tool(name: str, args: dict, user) -> dict:
    try:
        if name == "list_bots":
            bots = bot_service.list_bots()
            refreshed = [bot_service.refresh_state_from_config(b) for b in bots]
            return {"bots": [b.model_dump() for b in refreshed]}

        elif name == "get_bot":
            bot = bot_service.get(args["bot_id"])
            if bot is None:
                return {"error": f"Bot {args['bot_id']} not found"}
            return bot_service.refresh_state_from_config(bot).model_dump()

        elif name == "start_bot":
            bot_id = args["bot_id"]
            bot = bot_service.start(bot_id, actor_email=user.email, actor_role=user.role.value)
            await get_runtime_manager().start(bot)
            return {"status": "started", "bot": bot.model_dump()}

        elif name == "stop_bot":
            bot_id = args["bot_id"]
            bot = bot_service.stop(bot_id, actor_email=user.email, actor_role=user.role.value)
            await get_runtime_manager().stop(bot_id)
            return {"status": "stopped", "bot": bot.model_dump()}

        elif name == "pause_bot":
            bot_id = args["bot_id"]
            bot = bot_service.pause(bot_id, actor_email=user.email, actor_role=user.role.value)
            await get_runtime_manager().stop(bot_id)
            return {"status": "paused", "bot": bot.model_dump()}

        elif name == "list_alerts":
            from app.alerts.models import AlertStatus
            status = AlertStatus.ACTIVE if args.get("active_only") else None
            alerts = alert_service.list_alerts(status=status)
            return {"alerts": [a.model_dump() for a in alerts[:20]]}

        elif name == "acknowledge_alert":
            alert = alert_service.acknowledge(args["alert_id"], actor_email=user.email)
            if alert is None:
                return {"error": f"Alert {args['alert_id']} not found"}
            return {"status": "acknowledged", "alert": alert.model_dump()}

        elif name == "get_audit_log":
            events = audit_service.list_events(resource_id=args.get("resource_id"))
            return {"events": [e.model_dump() for e in events[:30]]}

        elif name == "list_positions":
            positions = exec_persistence.list_positions(args["bot_id"])
            return {"positions": positions}

        elif name == "list_orders":
            orders = exec_persistence.list_orders(args["bot_id"], limit=args.get("limit", 20))
            return {"orders": orders}

        elif name == "create_bot":
            bot = bot_service.create(
                name=args["name"],
                owner_email=user.email,
                actor_email=user.email,
                actor_role=user.role.value,
            )
            return {"status": "created", "bot": bot.model_dump()}

        elif name == "run_backtest":
            manifest = BacktestManifest(
                strategy_id=args["strategy_id"],
                params=args.get("params", {}),
                symbols=[args["symbol"]],
                bars=args.get("bars", 500),
            )
            metrics = run_backtest(manifest, output_dir=None)
            return metrics.to_dict()

        else:
            return {"error": f"Unknown tool: {name}"}

    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Tool execution failed: {e}"}
