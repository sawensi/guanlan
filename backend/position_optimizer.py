"""
观澜 — 当日持仓优化建议

综合「单基金离场策略（管减仓/清仓）+ 大盘定投档位共识（管加仓）+ 单基金技术面」
给每只持仓输出当日操作建议：加仓 / 持有 / 减仓 / 清仓。

决策优先级：离场（风控）优先于加仓。市场「减码/暂停」只抑制加仓、不强制卖出——
卖出始终由单基金离场策略说了算。
"""


def compute_market_context(dashboard: dict | None, insights=None) -> dict:
    """计算大盘环境（周期 + 估值 + 入场共识 + 定投档位共识），一次请求算一次，多基金复用。"""
    from quant_strategies import (
        get_all_strategies, synthesize_entry_decision, synthesize_dca_decision,
    )
    from strategy_engine import compute_all_signals

    cycle_str = (dashboard or {}).get("cycle", "复苏期")
    cycle_conf = (dashboard or {}).get("cycle_confidence", 0)
    valuation = (dashboard or {}).get("valuation") or None

    xuxiaoming_stance = None
    if insights is not None:
        stance = getattr(insights, "xu_xiaoming_stance", None)
        if stance:
            try:
                xuxiaoming_stance = stance.model_dump()
            except AttributeError:
                xuxiaoming_stance = stance

    signals = compute_all_signals()
    strategies = get_all_strategies(cycle_str, signals)
    entry_consensus = synthesize_entry_decision(strategies)
    dca_consensus = synthesize_dca_decision(strategies, valuation)

    return {
        "cycle": cycle_str,
        "cycle_confidence": cycle_conf,
        "valuation": valuation,
        "entry_consensus": entry_consensus,
        "dca_consensus": dca_consensus,
        "xuxiaoming_stance": xuxiaoming_stance,
    }


def compute_add_signal(fund_data: dict, market_ctx: dict) -> dict:
    """
    单基金加仓档位：大盘定投档位（已含估值乘数）为基准 × 单基金技术面微调。

    技术面三因子：
    - 网格位置：60 日区间低位加码、高位减码（对应 _signal_grid 逻辑）
    - 动量：近 1 月跌 >5% 加码、涨 >10% 减码（对应 _signal_dca 逻辑）
    - 均线：多头/金叉上浮、空头/死叉下调
    """
    dca = market_ctx.get("dca_consensus") or {}
    base_mult = dca.get("multiplier")
    if base_mult is None:
        base_mult = 1.0

    latest_nav = fund_data.get("latest_nav")
    grid_high = fund_data.get("grid_high")
    grid_low = fund_data.get("grid_low")
    momentum_1m = fund_data.get("momentum_1m")
    ma_status = fund_data.get("ma_status", "")

    # 网格位置：0=低位(加码) → 1=高位(减码)
    grid_position = None
    grid_tilt = 1.0
    grid_note = ""
    if latest_nav is not None and grid_high is not None and grid_low is not None and grid_high > grid_low:
        grid_position = round((latest_nav - grid_low) / (grid_high - grid_low), 3)
        grid_position = max(0.0, min(1.0, grid_position))
        grid_tilt = round(1.15 - 0.30 * grid_position, 3)
        if grid_position <= 0.2:
            grid_note = "处于60日区间低位"
        elif grid_position >= 0.8:
            grid_note = "处于60日区间高位"
        else:
            grid_note = "处于60日区间中段"

    # 动量：近 1 月跌 >5% 加码、涨 >10% 减码
    mom_tilt = 1.0
    mom_note = ""
    if momentum_1m is not None:
        if momentum_1m <= -5:
            mom_tilt, mom_note = 1.15, f"近1月 {momentum_1m}%（跌超5%加码）"
        elif momentum_1m >= 10:
            mom_tilt, mom_note = 0.85, f"近1月 {momentum_1m}%（涨超10%减码）"
        else:
            mom_note = f"近1月 {momentum_1m}%"

    # 均线：多头/金叉上浮，空头/死叉下调
    ma_tilt = 1.0
    ma_note = ma_status or ""
    if ("金叉" in ma_status) or ("多头" in ma_status):
        ma_tilt = 1.08
    elif ("死叉" in ma_status) or ("空头" in ma_status):
        ma_tilt = 0.92

    technical_tilt = round(grid_tilt * mom_tilt * ma_tilt, 3)
    technical_tilt = max(0.6, min(1.4, technical_tilt))
    multiplier = max(0.0, min(2.0, round(base_mult * technical_tilt, 2)))

    if multiplier >= 1.3:
        tier = "加码"
    elif multiplier <= 0.2:
        tier = "暂停"
    elif multiplier <= 0.6:
        tier = "减码"
    else:
        tier = "正常"

    reasons = [r for r in (grid_note, mom_note, ma_note) if r]

    return {
        "multiplier": multiplier,
        "tier": tier,
        "base_multiplier": base_mult,
        "technical_tilt": technical_tilt,
        "grid_position": grid_position,
        "momentum_1m": momentum_1m,
        "ma_status": ma_status,
        "reasons": reasons,
    }


def synthesize_position_advice(fund_code: str, return_rate, entry_date, market_ctx: dict) -> dict:
    """单基金当日持仓建议：加仓 / 持有 / 减仓 / 清仓。"""
    from fund_data import fetch_fund_history
    from exit_strategies import (
        get_all_exit_strategies, synthesize_exit_decision, _compute_days_held,
    )

    result = {
        "fund_code": fund_code,
        "fund_name": fund_code,
        "fund_type": "unknown",
        "latest_nav": None,
        "latest_nav_date": None,
        "return_rate": return_rate,
        "entry_date": entry_date,
        "days_held": None,
        "action": "数据不足",
        "action_detail": "",
        "confidence": None,
        "key_reasons": [],
        "add_signal": None,
        "exit_summary": None,
        "error": None,
    }

    try:
        fund_data = fetch_fund_history(fund_code)
    except Exception as e:
        result["error"] = f"拉取数据失败: {e}"
        return result

    if fund_data is None:
        result["error"] = "无法获取基金数据，请检查代码"
        return result

    result["fund_name"] = fund_data.get("fund_name", fund_code)
    result["fund_type"] = fund_data.get("fund_type", "unknown")
    result["latest_nav"] = fund_data.get("latest_nav")
    result["latest_nav_date"] = fund_data.get("latest_nav_date")
    result["days_held"] = _compute_days_held(entry_date, fund_data)

    cycle_str = market_ctx.get("cycle", "复苏期")
    xuxiaoming_stance = market_ctx.get("xuxiaoming_stance")

    # 1. 离场信号（单基金）
    exit_strats = get_all_exit_strategies(
        fund_data, None, entry_date, cycle_str, return_rate,
        xuxiaoming_stance=xuxiaoming_stance,
    )
    exit_decision = synthesize_exit_decision(exit_strats, fund_data)

    # 2. 加仓信号（大盘档位 + 单基金技术面）
    add_signal = compute_add_signal(fund_data, market_ctx)
    result["add_signal"] = add_signal

    # 3. 最终建议
    recommendation = exit_decision.get("recommendation", "")
    confidence = exit_decision.get("confidence")
    result["confidence"] = confidence

    if "清仓" in recommendation:
        action = "清仓"
        detail = exit_decision.get("suggested_action") or {}
        action_detail = detail.get("detail", "建议全部离场")
    elif "减仓" in recommendation:
        action = "减仓"
        detail = exit_decision.get("suggested_action") or {}
        action_detail = detail.get("detail", "建议先减仓观察")
    else:
        # 离场信号未触发（持有/数据不足），看加仓档位
        if add_signal["tier"] == "加码":
            action = "加仓"
            action_detail = f"离场信号未触发，加仓档位 {add_signal['multiplier']}x，可加码"
        elif add_signal["tier"] == "暂停":
            action = "持有"
            action_detail = "离场信号未触发，但定投档位建议暂停，暂不加仓"
        elif add_signal["tier"] == "减码":
            action = "持有"
            action_detail = "离场信号未触发，但定投档位建议减码，暂不加仓"
        else:
            action = "持有"
            action_detail = "离场信号未触发，加仓档位正常，继续持有/按计划定投"

    result["action"] = action
    result["action_detail"] = action_detail

    # 4. 关键理由：离场 top 2 + 技术面
    key_reasons = list(exit_decision.get("key_reasons", []))[:2]
    for r in add_signal.get("reasons", []):
        key_reasons.append(f"【技术面】{r}")
    result["key_reasons"] = key_reasons[:4]

    # 5. 裁剪离场摘要供前端展示
    result["exit_summary"] = {
        "recommendation": recommendation,
        "consensus": exit_decision.get("consensus"),
        "confidence": confidence,
        "breakdown": exit_decision.get("breakdown"),
        "suggested_action": exit_decision.get("suggested_action"),
    }

    return result
