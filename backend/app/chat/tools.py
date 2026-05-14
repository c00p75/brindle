from __future__ import annotations

from app.alerts import service as alert_service
from app.audit import service as audit_service
from app.bots import service as bot_service
from app.chat import market_tools, research_tools
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
            "description": "Get the current state and metadata of a specific trading bot (id, name, state, allocation, active version number). Does NOT return the full strategy configuration — use get_bot_config for strategy params and risk limits.",
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
            "name": "get_bot_config",
            "description": "Get the current active configuration for a bot (strategy params, risk limits, symbols, etc.)",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to get config for"},
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
            "description": "List all system alerts, notifications, and error flags. Use this to find out why a bot stopped, what risk limits were hit, or to get a general system health check.",
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
                    "allocation": {"type": "number", "description": "Initial capital allocation/budget for this bot (e.g. 100.0)"},
                },
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_bot_config",
            "description": "Create and apply a new configuration draft for a bot. Use this to change parameters like stake, strategy, or risk settings.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to update"},
                    "config": {
                        "type": "object",
                        "description": "Full BotConfig object with updated values. Always get current config first.",
                    },
                },
                "required": ["bot_id", "config"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_bot_analytics",
            "description": "Get bucketed performance analytics (hourly/daily) for a bot to analyze trends, win rates, and PnL over time.",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to analyze"},
                    "since_ms": {"type": "integer", "description": "Start timestamp in ms"},
                    "until_ms": {"type": "integer", "description": "End timestamp in ms"},
                    "granularity": {"type": "string", "enum": ["hour", "day"], "default": "hour"},
                },
                "required": ["bot_id", "since_ms", "until_ms"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_broker_balance",
            "description": "Get the live account balance from the Deriv broker (real-time, not cached). Returns available balance and currency.",
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "archive_bot",
            "description": "Archive a bot that is no longer needed (destructive action).",
            "parameters": {
                "type": "object",
                "properties": {
                    "bot_id": {"type": "string", "description": "Bot ID to archive"},
                },
                "required": ["bot_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "run_backtest",
            "description": (
                "Run a backtest simulation for a strategy. "
                "Returns PnL, win rate, Sharpe ratio, and drawdown metrics. "
                "Use data_source='deriv' to validate user ideas on real Deriv "
                "history; data_source='synthetic' (default) is faster and "
                "deterministic but not predictive of live performance."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {
                        "type": "string",
                        "description": "Strategy ID to test (e.g. 'trend_v1')",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Symbol to backtest (e.g. 'EUR/USD', 'V75/USD')",
                    },
                    "bars": {
                        "type": "integer",
                        "description": "Number of price bars to simulate (default 500)",
                    },
                    "params": {
                        "type": "object",
                        "description": "Strategy-specific parameters (key-value pairs)",
                    },
                    "data_source": {
                        "type": "string",
                        "enum": ["synthetic", "deriv"],
                        "description": (
                            "'synthetic' (default) for a fast deterministic run, "
                            "or 'deriv' to fetch real Deriv tick history. Use 'deriv' "
                            "before recommending any user-facing config change."
                        ),
                    },
                },
                "required": ["strategy_id", "symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_strategies_meta",
            "description": (
                "Return id, one-line description, and default parameters for "
                "every registered strategy. Use this when the user describes a "
                "trading idea in natural language ('I want to buy when MACD "
                "crosses up', 'something for ranging markets') so you can pick "
                "the closest registered strategy and reasonable starting params "
                "before calling run_backtest."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_quote",
            "description": (
                "Fetch the current market price for a Deriv symbol. "
                "Use this BEFORE making any statement about a symbol's current price, "
                "trend, or condition — never speculate from training data."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": (
                            "Canonical symbol (e.g. 'EUR/USD', 'V75/USD', 'BOOM1000/USD')."
                        ),
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_recent_bars",
            "description": (
                "Fetch the most recent price bars for a Deriv symbol. "
                "Use this to assess short-term price action and trend before answering "
                "questions about market behavior."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Canonical symbol (e.g. 'EUR/USD', 'V75/USD').",
                    },
                    "count": {
                        "type": "integer",
                        "description": "Number of bars to fetch (1-500, default 100).",
                    },
                },
                "required": ["symbol"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_indicators",
            "description": (
                "Compute technical indicators on recent Deriv price data. "
                "Supported: rsi, ema, macd, atr, bollinger. Use this to ground any "
                "discussion of overbought/oversold conditions, trend strength, "
                "volatility, or breakout setups in actual numbers."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "symbol": {
                        "type": "string",
                        "description": "Canonical symbol (e.g. 'EUR/USD', 'V75/USD').",
                    },
                    "indicators": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["rsi", "ema", "macd", "atr", "bollinger"],
                        },
                        "description": "List of indicators to compute.",
                    },
                    "bars": {
                        "type": "integer",
                        "description": "Bars of history for computation (default 100).",
                    },
                    "params": {
                        "type": "object",
                        "description": (
                            "Optional overrides. Keys: rsi_period, ema_fast, ema_slow, "
                            "macd_fast, macd_slow, macd_signal, atr_period, bb_period, bb_k."
                        ),
                    },
                },
                "required": ["symbol", "indicators"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "analyze_portfolio",
            "description": (
                "Aggregate every active bot into a portfolio diagnostic: total PnL, "
                "win rates, by-state breakdown, top winners/losers, and flagged "
                "issues (low win rate, drawdown, idle running bots, symbol "
                "concentration). Use this when the user asks 'how am I doing?', "
                "'what's wrong with my portfolio?', or before suggesting changes."
            ),
            "parameters": {"type": "object", "properties": {}, "required": []},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "scan_setups",
            "description": (
                "Run a strategy's signal logic on current Deriv bars across multiple "
                "symbols and return ranked candidates (signal_buy/signal_sell first, "
                "then weak/cooldown/watching). Use this when the user asks 'what's "
                "setting up?', 'any signals on V75/EUR-USD?', or wants to find live "
                "opportunities. Does NOT place orders."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {
                        "type": "string",
                        "description": "Strategy id, e.g. 'trend_v1', 'bollinger_v1'.",
                    },
                    "symbols": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Canonical symbols to scan (e.g. ['V75/USD','EUR/USD']).",
                    },
                    "bars": {
                        "type": "integer",
                        "description": "Bars of history per symbol (default 100).",
                    },
                },
                "required": ["strategy_id", "symbols"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "suggest_params",
            "description": (
                "Run a small parameter sweep for a strategy on synthetic data and "
                "return the top 3 candidates ranked by Sharpe + PnL. Output is a "
                "starting point — recommend the user confirms the winner with "
                "run_backtest on real Deriv data before changing any bot's config."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "strategy_id": {
                        "type": "string",
                        "description": "Strategy id, e.g. 'trend_v1'.",
                    },
                    "symbol": {
                        "type": "string",
                        "description": "Canonical symbol to evaluate against (e.g. 'V75/USD').",
                    },
                    "bars": {
                        "type": "integer",
                        "description": "Bars per backtest run (default 300).",
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

        elif name == "get_bot_config":
            from app.configs import service as config_service
            bot_id = args["bot_id"]
            av = config_service.active_version(bot_id)
            if av is None:
                return {"error": f"No active configuration found for bot {bot_id}"}
            return av.config.model_dump()

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
                allocation=args.get("allocation"),
            )
            return {"status": "created", "bot": bot.model_dump()}

        elif name == "archive_bot":
            bot_id = args["bot_id"]
            bot = bot_service.archive(bot_id, actor_email=user.email, actor_role=user.role.value)
            return {"status": "archived", "bot": bot.model_dump()}

        elif name == "update_bot_config":
            from app.configs import service as config_service
            from app.bots.models import BotConfig
            bot_id = args["bot_id"]
            new_config = BotConfig.model_validate(args["config"])
            # Lifecycle: draft -> validate -> apply
            draft = config_service.create_draft(
                actor_email=user.email,
                actor_role=user.role.value,
                config=new_config
            )
            config_service.validate(
                actor_email=user.email,
                actor_role=user.role.value,
                bot_id=bot_id,
                version=draft.version
            )
            # AI is trusted to apply immediately if the user asked for it
            applied = config_service.apply(
                actor_email=user.email,
                actor_role=user.role.value,
                bot_id=bot_id,
                version=draft.version,
                typed_confirmation="APPLY RISK CHANGE"
            )
            return {"status": "applied", "version": applied.version, "config": applied.config.model_dump()}

        elif name == "get_bot_analytics":
            from app.execution import balance_history
            data = balance_history.analytics(
                bot_id=args["bot_id"],
                since_ms=args["since_ms"],
                until_ms=args["until_ms"],
                granularity=args.get("granularity", "hour")
            )
            return {"buckets": data}

        elif name == "run_backtest":
            data_source = args.get("data_source", "synthetic")
            if data_source not in ("synthetic", "deriv"):
                return {"error": f"invalid data_source '{data_source}' (use 'synthetic' or 'deriv')"}
            manifest = BacktestManifest(
                strategy_id=args["strategy_id"],
                params=args.get("params", {}),
                symbols=[args["symbol"]],
                bars=args.get("bars", 500),
                data_source=data_source,
            )
            metrics = run_backtest(manifest, output_dir=None)
            return metrics.to_dict()

        elif name == "list_strategies_meta":
            return research_tools.list_strategies_meta()

        elif name == "get_quote":
            return await market_tools.get_quote(args["symbol"])

        elif name == "get_recent_bars":
            return await market_tools.get_recent_bars(
                args["symbol"], int(args.get("count", 100)),
            )

        elif name == "get_indicators":
            return await market_tools.get_indicators(
                args["symbol"],
                args["indicators"],
                int(args.get("bars", 100)),
                args.get("params"),
            )

        elif name == "get_broker_balance":
            from app.bots import service as bot_service
            from app.configs.service import active_version
            from app.adapters.brokers.factory import create_adapter
            mgr = get_runtime_manager()
            seen: set[tuple] = set()
            results = []
            for bot in bot_service.list_bots():
                cv = active_version(bot.id)
                if not cv:
                    continue
                bc = cv.config.broker
                key = (bc.type, bc.account_id)
                if key in seen:
                    continue
                seen.add(key)
                # Use cached balance if available (avoids a new WS connection)
                cached = mgr.get_cached_balance(bot.id)
                if cached:
                    results.append({
                        "broker": bc.type,
                        "account_id": bc.account_id,
                        "environment": bc.environment,
                        "available": cached["available"],
                        "currency": cached["currency"],
                    })
                    break
            return {"balances": results} if results else {"error": "No cached balance available — bots may still be starting up."}

        elif name == "analyze_portfolio":
            return await research_tools.analyze_portfolio()

        elif name == "scan_setups":
            return await research_tools.scan_setups(
                args["strategy_id"],
                list(args["symbols"]),
                int(args.get("bars", 100)),
            )

        elif name == "suggest_params":
            return await research_tools.suggest_params(
                args["strategy_id"],
                args["symbol"],
                int(args.get("bars", 300)),
            )

        else:
            return {"error": f"Unknown tool: {name}"}

    except ValueError as e:
        return {"error": str(e)}
    except Exception as e:
        return {"error": f"Tool execution failed: {e}"}


WRITE_TOOLS = {
    "start_bot",
    "stop_bot",
    "pause_bot",
    "create_bot",
    "archive_bot",
    "update_bot_config",
    "acknowledge_alert",
}
