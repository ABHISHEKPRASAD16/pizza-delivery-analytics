# Power BI - two pages, built properly

Canvas is 1280 x 720 (the default 16:9). Every visual below has exact
coordinates, so the result is aligned rather than eyeballed.

**Where to set position:** select a visual → **Format visual** (paint-roller)
→ **General** → **Properties** → **Size** and **Position**. Type the numbers.
This is the single biggest difference between a report that looks designed and
one that looks dragged together.

---

## Palette

Set these once and use nothing else.

| Role | Hex | Used for |
|---|---|---|
| Ink | `#22252A` | headings, KPI values |
| Muted | `#6B7280` | labels, axis text |
| Primary | `#D62828` | the main measure in any chart |
| Secondary | `#F77F00` | the comparison line (7-day average) |
| Positive | `#2E7D5B` | profit, good variance |
| Negative | `#C0392B` | costs, bad variance |
| Card | `#FFFFFF` | visual backgrounds |
| Canvas | `#F4F5F7` | page background |

**Apply the canvas colour:** click empty canvas → **Format** → **Canvas
background** → colour `#F4F5F7`, **Transparency 0%**. Do this on both pages,
it is what stops the report looking like a blank Word document.

**Theme shortcut:** View → Themes → Customize current theme → paste the six
colours into the theme colours. Then every new visual picks them up.

---

## Page 1 - Overview

Rename the page tab to `Overview`.

### Header

**Text box**, position `X 0, Y 0, W 1280, H 56`
- Text: `Pizza Delivery Analytics` — 20pt, Segoe UI Semibold, white
- Second line, 11pt, `#D9DBE0`: `Potsdam branch · daily performance`
- Format → Effects → Background → `#22252A`, transparency 0%

### KPI row - five cards

All at `Y 72, W 238, H 104`. X positions:

| Card | X | Measure |
|---|---|---|
| 1 | 20 | `Revenue` |
| 2 | 270 | `Orders` |
| 3 | 520 | `Avg Order Value` |
| 4 | 770 | `Operating Profit` |
| 5 | 1020 | `Operating Margin %` |

For each card:
- **Callout value**: 28pt Semibold, colour `#22252A` (use `#2E7D5B` for cards 4 and 5)
- **Category label**: on, 10pt, colour `#6B7280`
- **Effects → Background**: `#FFFFFF`
- **Effects → Visual border**: on, rounded corners `8`
- **Effects → Shadow**: on, preset *Outer*, transparency 85%

Display units **None** on Revenue and Operating Profit - `€1,103,270` reads
better than `1M` on a KPI an owner is judging the month by.

### Revenue trend - line chart

`X 20, Y 192, W 832, H 286`

- X-axis: `mart dim_date` → `full_date`
- Y-axis: `Revenue`, then `Revenue 7d Avg`
- Lines → `Revenue`: colour `#D62828`, width 2
- Lines → `Revenue 7d Avg`: colour `#F77F00`, width 3, **dashed**
- Title: `Revenue, daily vs 7-day average` — 12pt, `#22252A`, left aligned
- Y-axis → Title off. Gridlines → `#EDEEF1`, width 1
- **Analytics pane** (magnifying glass) → **Find anomalies** → Add

The anomaly markers should land on the February outage. That one visual
demonstrates more than any amount of explaining.

### Orders by weekday - clustered column

`X 864, Y 192, W 396, H 286`

- X-axis: `mart dim_date` → `day_name`
- Y-axis: `Orders`
- Columns → colour `#D62828`
- Title: `Orders by weekday`
- Data labels on, 9pt

✅ Must read Monday → Sunday. Alphabetical means the sort-by-column step is
missing: select `day_name` → **Column tools → Sort by column → weekday_sort`.

### What drives demand - Key influencers

`X 20, Y 490, W 832, H 210`

- Analyse: `mart kpi_daily` → `orders`
- Explain by: `is_weekend`, `is_rainy`, `is_public_holiday`, `day_name`
- Title: `What drives order volume`

Free built-in ML. It runs a decision tree and writes the finding in English.

### Date slicer

`X 864, Y 490, W 396, H 210`

- Field: `mart dim_date` → `full_date`
- Slicer settings → Style → **Between**
- Title: `Period`

---

## Page 2 - Profit

New page (**+** at the bottom), rename to `Profit`. Same canvas colour and the
same header text box, but the subtitle reads `where the money actually goes`.

Page 1 answers "how are we doing". Page 2 answers "where does the money go".
Nothing is repeated between them - a KPI that appears twice is a wasted slot.

### KPI row - the cost stack

All at `Y 72, W 238, H 104`. X: `20`, `270`, `520`, `770`, `1020`.

| Card | Measure | Value | Colour |
|---|---|---|---|
| 1 | `Food Cost %` | 29.2 % | `#C0392B` |
| 2 | `Labour Cost %` | 33.1 % | `#C0392B` |
| 3 | `Fixed Costs` | EUR 114,055 | `#6B7280` |
| 4 | `Franchise Fees` | EUR 75,902 | `#6B7280` |
| 5 | `Commission Paid` | EUR 25,496 | `#6B7280` |

Red for the two costs that can be acted on this week, grey for the three that
are contractual. The colour split is the message.

### Margin per order by channel - clustered bar

`X 20, Y 192, W 610, H 250`

- Y-axis: `mart dim_channel` -> `channel_name`
- X-axis: `Margin per Order`
- Bars `#C0392B`, data labels on
- Title: `Margin per order by channel`

Expect Website 19.77, Telefon 19.59, App 19.42, Abholung 18.16,
Lieferando 15.98.

The most valuable visual in the report. The aggregator earns EUR 3.79 less per
order than the branch's own website - about EUR 29,000 across the year - and
it points straight at a decision: push customers to the app.

### Cost lines - clustered bar

`X 650, Y 192, W 610, H 250`

- X-axis (values): `Fixed Costs`, `Franchise Fees`, `Commission Paid`
- Title: `Cost lines`

Do NOT mix the percentage measures with the euro ones in a single chart - the
axis has to serve both and ends up meaningless for each. The percentages are
already the KPI cards above.

### Operating profit by month - line

`X 20, Y 458, W 610, H 242`

- X-axis: `mart dim_date` -> `month_name`
- Y-axis: `Operating Profit`
- Line `#2E7D5B`, width 3
- Must read January -> December, else set Sort by column -> `month_sort`

### What the profit assumes - table

`X 650, Y 458, W 610, H 242`

- From `mart dim_cost_assumption`: `cost_item`, `cost_type`, `monthly_eur`
- Style presets -> Minimal

Nobody has to take the 13.7% margin on trust - they can read the rent, the
energy bill and the franchise rate, and argue with them. That is the
difference between a credible report and an asserted number.

---

## Finishing touches

Worth the five minutes:

1. **View → Page view → Fit to page** so it scales on any screen.
2. Turn OFF titles on the KPI cards - the category label already says what it
   is, and two labels on one card looks cluttered.
3. **Selection pane** (View → Selection) → rename each visual to something
   meaningful. Future-you will thank you.
4. Set page tooltips off if you are not using them (Format → Page information).
5. **Ctrl+S** often. Power BI does not autosave.

## Common traps

| Symptom | Cause |
|---|---|
| Weekdays read Friday, Monday, Saturday | sort-by-column not set on `day_name` |
| Months read April, August, December | sort-by-column not set on `month_name` |
| A percentage shows as `€ 0.0811` | measure format is Currency, should be Percentage |
| A card reads `1M` | Callout value → Display units → set to None |
| Blank visual using `forecast_daily` | do not relate it to `dim_date`; it holds future dates that do not exist there, so the join drops every row |
