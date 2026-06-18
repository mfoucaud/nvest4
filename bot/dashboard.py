from datetime import datetime, timezone


def _perf_explanation(trade: dict) -> str:
    pnl = trade.get("pnl")
    if pnl is None:
        return "Données de sortie indisponibles."
    entry = trade.get("entry")
    exit_ = trade.get("exit")
    qty   = trade.get("qty", 0)
    pct   = ((exit_ - entry) / entry * 100) if (entry and exit_) else None
    reasoning = trade.get("reasoning", "")
    short_reason = (reasoning[:120] + "…") if len(reasoning) > 120 else reasoning

    if pnl > 0:
        msg = f"Trade gagnant"
        if pct:
            msg += f" (+{pct:.1f}%)"
        msg += ". Le stop suiveur a sécurisé les gains."
        if short_reason:
            msg += f" Signal d'entrée : {short_reason}"
    else:
        msg = f"Trade perdant"
        if pct:
            msg += f" ({pct:.1f}%)"
        msg += ". Le stop suiveur s'est déclenché avant retournement."
        if short_reason:
            msg += f" Signal d'entrée : {short_reason}"
    return msg


def render_dashboard(
    positions: list[dict],
    closed_trades: list[dict],
    analyses: list[dict],
    portfolio: dict,
) -> str:
    now        = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M")
    capital    = portfolio.get("capital", 0)
    pnl_day    = portfolio.get("pnl", 0)
    win_rate   = portfolio.get("win_rate", 0.0)
    trades_cnt = portfolio.get("trades", 0)
    wins       = portfolio.get("wins", 0)
    losses     = portfolio.get("losses", 0)

    pnl_day_color = "#3fb950" if pnl_day >= 0 else "#f85149"
    pnl_day_sign  = "+" if pnl_day >= 0 else ""

    # ── Open positions ──────────────────────────────────────────────────────
    open_rows = ""
    for p in positions:
        pnl_val   = p.get("pnl", 0)
        pnl_pct   = p.get("pnl_pct", 0)
        pnl_color = "#3fb950" if pnl_val >= 0 else "#f85149"
        pnl_sign  = "+" if pnl_val >= 0 else ""
        stop      = p.get("stop_price")
        stop_str  = f"${stop:.2f}" if stop else "—"
        stop_color = "#d29922" if stop else "#8b949e"
        ticker    = p["ticker"]
        direction = p.get("direction", "LONG")
        dir_badge = '<span class="badge short-badge">SHORT</span>' if direction == "SHORT" else '<span class="badge long-badge">LONG</span>'
        entry     = p.get("entry", 0)
        current   = p.get("current", 0)
        qty       = p.get("qty", 0)
        open_rows += f"""
<tr>
  <td><strong>{ticker}</strong> {dir_badge}</td>
  <td>${entry:.2f}</td>
  <td>${current:.2f}</td>
  <td>{qty}</td>
  <td style="color:{stop_color};font-weight:600">{stop_str}</td>
  <td style="color:{pnl_color};font-weight:600">{pnl_sign}${pnl_val:.2f} ({pnl_sign}{pnl_pct:.1f}%)</td>
</tr>"""

    if not open_rows:
        open_rows = '<tr><td colspan="6" style="text-align:center;color:#8b949e;padding:20px">Aucune position ouverte</td></tr>'

    # ── Closed trades ───────────────────────────────────────────────────────
    closed_rows = ""
    for c in closed_trades:
        pnl_val = c.get("pnl")
        if pnl_val is None:
            badge = '<span class="badge exp">?</span>'
            pnl_str = "—"
        elif pnl_val > 0:
            badge   = '<span class="badge win">GAGNANT</span>'
            pnl_str = f'<span style="color:#3fb950;font-weight:600">+${pnl_val:.2f}</span>'
        else:
            badge   = '<span class="badge loss">PERDANT</span>'
            pnl_str = f'<span style="color:#f85149;font-weight:600">-${abs(pnl_val):.2f}</span>'

        entry = c.get("entry")
        exit_ = c.get("exit")
        entry_str = f"${entry:.2f}" if entry else "—"
        exit_str  = f"${exit_:.2f}" if exit_ else "—"
        expl  = _perf_explanation(c)
        direction = c.get("direction", "LONG")
        dir_badge = '<span class="badge short-badge">SHORT</span>' if direction == "SHORT" else '<span class="badge long-badge">LONG</span>'

        closed_rows += f"""
<tr>
  <td>{c.get("timestamp", "")}</td>
  <td><strong>{c["ticker"]}</strong> {dir_badge}</td>
  <td>{entry_str}</td>
  <td>{exit_str}</td>
  <td>{c.get("qty", "—")}</td>
  <td>{pnl_str}</td>
  <td>{badge}</td>
  <td style="color:#8b949e;font-size:.82em;max-width:260px">{expl}</td>
</tr>"""

    if not closed_rows:
        closed_rows = '<tr><td colspan="8" style="text-align:center;color:#8b949e;padding:20px">Aucun trade clôturé</td></tr>'

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>!nvest Dashboard — {now}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{ background: #0d1117; color: #e6edf3; font-family: 'Segoe UI', Arial, sans-serif; font-size: 14px; }}
  .header {{ background: linear-gradient(135deg, #161b22 0%, #0d1117 100%); border-bottom: 1px solid #30363d; padding: 20px 32px; display: flex; align-items: center; justify-content: space-between; }}
  .header h1 {{ font-size: 1.5em; font-weight: 700; color: #58a6ff; }}
  .header .date {{ color: #8b949e; font-size: .9em; }}
  .container {{ max-width: 1400px; margin: 0 auto; padding: 24px 32px; }}
  .kpi-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(150px, 1fr)); gap: 14px; margin-bottom: 28px; }}
  .kpi {{ background: #161b22; border: 1px solid #21262d; border-radius: 10px; padding: 18px 20px; text-align: center; }}
  .kpi .label {{ font-size: .75em; color: #8b949e; text-transform: uppercase; letter-spacing: .5px; margin-bottom: 8px; }}
  .kpi .value {{ font-size: 1.6em; font-weight: 700; }}
  .section-title {{ font-size: 1em; font-weight: 700; color: #58a6ff; margin: 28px 0 12px; padding-bottom: 6px; border-bottom: 1px solid #21262d; }}
  .table-wrap {{ overflow-x: auto; background: #0d1117; border: 1px solid #21262d; border-radius: 10px; margin-bottom: 28px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: .85em; }}
  th {{ background: #161b22; color: #8b949e; padding: 10px 14px; text-align: left; font-weight: 600; font-size: .8em; text-transform: uppercase; letter-spacing: .4px; border-bottom: 1px solid #21262d; }}
  td {{ padding: 10px 14px; border-bottom: 1px solid #1c2128; vertical-align: middle; }}
  tr:last-child td {{ border-bottom: none; }}
  tr:hover td {{ background: #1c2128; }}
  .badge {{ display: inline-block; padding: 2px 8px; border-radius: 4px; font-size: .75em; font-weight: 700; letter-spacing: .3px; }}
  .badge.win        {{ background: #1a3a1a; color: #3fb950; }}
  .badge.loss       {{ background: #3a1a1a; color: #f85149; }}
  .badge.exp        {{ background: #2a2a1a; color: #d29922; }}
  .badge.long-badge {{ background: #1a2a3a; color: #58a6ff; }}
  .badge.short-badge{{ background: #2a1a3a; color: #bc8cff; }}
  .footer {{ text-align: center; padding: 24px; color: #8b949e; font-size: .78em; }}
</style>
</head>
<body>

<div class="header">
  <h1>!nvest — Trading Dashboard</h1>
  <span class="date">Généré le {now} UTC &bull; Paper Trading</span>
</div>

<div class="container">

<div class="kpi-grid">
  <div class="kpi">
    <div class="label">Portefeuille</div>
    <div class="value" style="color:#58a6ff">${capital:,.2f}</div>
  </div>
  <div class="kpi">
    <div class="label">PnL du jour</div>
    <div class="value" style="color:{pnl_day_color}">{pnl_day_sign}${pnl_day:,.2f}</div>
  </div>
  <div class="kpi">
    <div class="label">Win Rate</div>
    <div class="value" style="color:#d29922">{win_rate:.0f}%</div>
  </div>
  <div class="kpi">
    <div class="label">Trades totaux</div>
    <div class="value" style="color:#8b949e">{trades_cnt}</div>
  </div>
  <div class="kpi">
    <div class="label">Gagnants / Perdants</div>
    <div class="value"><span style="color:#3fb950">{wins}</span> / <span style="color:#f85149">{losses}</span></div>
  </div>
  <div class="kpi">
    <div class="label">Positions ouvertes</div>
    <div class="value" style="color:#58a6ff">{len(positions)}</div>
  </div>
</div>

<div class="section-title">Positions Ouvertes ({len(positions)})</div>
<div class="table-wrap">
<table>
  <thead>
    <tr>
      <th>Actif</th><th>Entrée</th><th>Actuel</th><th>Qté</th>
      <th>Stop Loss</th><th>PnL Latent</th>
    </tr>
  </thead>
  <tbody>{open_rows}</tbody>
</table>
</div>

<div class="section-title">Trades Clôturés ({len(closed_trades)})</div>
<div class="table-wrap">
<table>
  <thead>
    <tr>
      <th>Date</th><th>Actif</th><th>Entrée</th><th>Sortie</th><th>Qté</th>
      <th>PnL Réalisé</th><th>Résultat</th><th>Explication</th>
    </tr>
  </thead>
  <tbody>{closed_rows}</tbody>
</table>
</div>

</div>

<div class="footer">
  Généré le {now} UTC &bull; Paper Trading Alpaca &bull; Tous les ordres sont fictifs à but éducatif.
</div>
</body>
</html>"""
