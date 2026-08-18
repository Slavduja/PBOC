# PBoC Liquidity — Component Dashboard (Next.js)

Interactive dashboard for the reconstructed PBoC Net Liquidity Injection index.
Each of Howell's components is shown separately with its own chart; tick the
checkboxes to compose them into a combined index, overlaid on the CNCBBS
balance-sheet YoY (the validation anchor ≈ Howell's chart).

Dependency-light: Next.js + React only, charts are hand-rolled SVG (no charting
library).

## Run

```bash
cd dashboard
npm install
npm run dev        # http://localhost:3000
```

## Data

The dashboard reads `public/dashboard_data.json` (weekly per-component YoY series).
Regenerate it from the scraped operations after any scrape/rebuild:

```bash
cd ..                       # project root
python export_dashboard_data.py
```

That recomputes each component's net-stock YoY (reverse repo, outright repo, MLF,
bonds) plus RRR releases and the CNCBBS truth, and writes it into
`dashboard/public/`.

## Structure

| File | Role |
|---|---|
| `app/page.jsx` | route → renders the dashboard |
| `components/Dashboard.jsx` | state, component cards, checkboxes, composed index |
| `components/LineChart.jsx` | reusable SVG line chart (hover tooltip, year/value axes) |
| `app/globals.css` | styling |
| `public/dashboard_data.json` | series data (generated) |

## Notes

- **Composed index** = sum of the ticked components' YoY (YoY of a sum = sum of
  YoYs), so toggling is exact, not approximate.
- Components badged **partial** (outright repo, MLF) have a known recent-month
  data gap and understate until filled from CEIC — see each card's note.
- RRR is **off** by default: it is off-balance-sheet, so it belongs to Howell's
  wider liquidity index rather than the balance-sheet "Net Liquidity Injection"
  chart. Tick it to see the wider impulse.
