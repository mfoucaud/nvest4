def render_dashboard(positions: list[dict], analyses: list[dict], portfolio: dict) -> str:
    capital   = portfolio.get("capital", 0)
    pnl       = portfolio.get("pnl", 0)
    win_rate  = portfolio.get("win_rate", 0)
    trades    = portfolio.get("trades", 0)

    positions_rows = ""
    for p in positions:
        pnl_val = p.get("pnl", 0)
        color   = "#2ecc71" if pnl_val >= 0 else "#e74c3c"
        positions_rows += f"""
        <tr>
          <td>{p['ticker']}</td>
          <td>${p['entry']:.2f}</td>
          <td>${p['current']:.2f}</td>
          <td>{p['qty']}</td>
          <td style="color:{color}">${pnl_val:.2f}</td>
          <td>{p.get('reasoning', '')}</td>
        </tr>"""

    analyses_rows = ""
    for a in reversed(analyses):
        analyses_rows += f"""
        <tr>
          <td>{a.get('timestamp', '')}</td>
          <td>{a['ticker']}</td>
          <td>{a['action']}</td>
          <td>{'✓' if a.get('traded') else '—'}</td>
          <td>{a.get('reasoning', '')}</td>
        </tr>"""

    return f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8">
  <title>!nvest4 Dashboard</title>
  <style>
    body {{ font-family: monospace; background: #1a1a2e; color: #eee; padding: 2rem; }}
    h1   {{ color: #e94560; }}
    h2   {{ color: #0f3460; border-bottom: 1px solid #333; padding-bottom: .5rem; }}
    table {{ width: 100%; border-collapse: collapse; margin-bottom: 2rem; }}
    th    {{ background: #0f3460; padding: .5rem; text-align: left; }}
    td    {{ padding: .5rem; border-bottom: 1px solid #333; }}
    .kpi  {{ display: flex; gap: 2rem; margin-bottom: 2rem; }}
    .kpi-box {{ background: #16213e; padding: 1rem 2rem; border-radius: 8px; }}
    .kpi-box .val {{ font-size: 1.8rem; font-weight: bold; color: #e94560; }}
  </style>
</head>
<body>
  <h1>!nvest4 — Trading Bot Dashboard</h1>

  <div class="kpi">
    <div class="kpi-box"><div class="val">${capital:,.0f}</div>Capital</div>
    <div class="kpi-box"><div class="val">${pnl:,.2f}</div>P&amp;L Total</div>
    <div class="kpi-box"><div class="val">{win_rate*100:.0f}%</div>Win Rate</div>
    <div class="kpi-box"><div class="val">{trades}</div>Trades</div>
  </div>

  <h2>Positions ouvertes</h2>
  <table>
    <tr><th>Ticker</th><th>Entrée</th><th>Actuel</th><th>Qty</th><th>P&amp;L</th><th>Reasoning</th></tr>
    {positions_rows or '<tr><td colspan="6">Aucune position ouverte</td></tr>'}
  </table>

  <h2>Historique des analyses</h2>
  <div style="max-height: 400px; overflow-y: auto; border: 1px solid #333;">
    <table>
      <thead style="position: sticky; top: 0;">
        <tr><th>Timestamp</th><th>Ticker</th><th>Action</th><th>Tradé</th><th>Reasoning</th></tr>
      </thead>
      <tbody>
        {analyses_rows or '<tr><td colspan="5">Aucune analyse</td></tr>'}
      </tbody>
    </table>
  </div>
</body>
</html>"""
