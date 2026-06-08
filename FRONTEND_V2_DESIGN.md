# Motis Frontend v2 Design

## Summary

Frontend v2 will be a new React/Vite app built beside the current frontend, not a rewrite-in-place. The current app stays runnable for ongoing training and live-route work while v2 is scaffolded, styled, and then functionally ported page by page. v2 must use the existing FastAPI surface exactly as-is: no backend endpoint changes, no API contract changes, and no migration dependency.

The design goal is a readable dark trading terminal: dense, status-rich, operational, and fast to scan, with a Bloomberg-terminal influence expressed through fixed app chrome, compact panels, thin grid lines, route/workbench split panes, and precise status language rather than bright neon or decorative effects.

## Non-Negotiables

- Keep current frontend alive while v2 is being built.
- Do not alter API or backend behavior for v2.
- Preserve existing functionality page by page.
- Tabs must survive page refresh.
- Prioritize terminal clarity over marketing/dashboard decoration.
- Build basics and aesthetic system first, then port functions one page at a time.
- Avoid simply copying the current layouts where they are confusing.

## Recommended Architecture

Create a second app:

```text
apps/web-v2/
```

It should be a standalone Vite React workspace using the same backend base URL and same package ecosystem:

```text
Current v1 web: http://127.0.0.1:5173
New v2 web:     http://127.0.0.1:5174
API:            http://127.0.0.1:8000
```

This keeps v1 available while v2 is built. v2 can later replace v1 after feature parity is verified, but that should be a deliberate cutover.

### Why Separate App

This is safer than editing the current app because `apps/web/src/main.tsx` has become a large mixed file containing API clients, state orchestration, page layout, and component code. A separate v2 app lets us establish routing, shell, tokens, and page structure cleanly without risking the working training/execution UI.

### Shared Code Policy

Do not import from `apps/web` directly. v2 should initially duplicate API client types/functions where necessary, then optionally extract shared frontend contracts later if that becomes useful. The first priority is isolation and uninterrupted v1 operation.

## Routing And Refresh Persistence

Use URL-backed navigation, not local component state, for top-level tabs.

Recommended routes:

```text
/dashboard
/data
/engines
/research/stage0
/research/development
/trading
```

Optional selected entity state should also live in the URL where it affects workflow continuity:

```text
/research/stage0?batch=<stage0_run_id>
/research/development?session=<stage1_session_id>&stage=stage2
/trading?route=<route_id>
/engines?engine=vegas_ema&asset=AAVE
```

Use `@tanstack/react-router` or a small custom URL-state layer. Since `@tanstack/react-router` is already installed in the web workspace, v2 should prefer it unless setup overhead becomes distracting.

On unknown route, redirect to `/dashboard`. On refresh, restore the route, selected sub-tab, and selected row from URL params if present.

## Product Navigation Model

The app should feel like an operator terminal with five primary sections:

```text
Dashboard
Data
Engines
R&D
Trading
```

R&D has persistent second-level navigation:

```text
Stage 0 Batches
Development
```

The sidebar should show both levels clearly, but avoid accordion surprise. If the user is on R&D, both R&D child routes are visible and selectable. If not, child routes can remain visible in a muted compact style or collapse, but URL navigation must remain direct.

## Visual Direction

### Design Voice

Three concrete words:

```text
calibrated, dense, institutional
```

This should look like a serious local trading/research terminal, not a crypto dashboard, landing page, or SaaS analytics template. The reference direction is a dark blue-black operator console: fixed left rail, compact toolbar, dense entity list, large workbench surface, thin panel borders, and restrained green/red/blue status accents.

### Reference Image Direction

Match the overall language of the supplied reference image, not its individual components one-for-one. The important qualities are:

- a fixed, dark app shell with navigation separated from the scrollable workspace
- a narrow left operational list for the selected domain when useful
- a wider right workbench where most decisions happen
- dense table rows, key/value strips, and compact control bars
- dark panels separated by fine cool lines instead of large soft cards
- selected states expressed through thin teal borders, underlines, or quiet tints
- status chips that are small, explicit, and color-coded without glowing
- trading/research objects named plainly in the chrome: asset, engine, strategy, route, batch, session
- action controls attached to the object they affect, never floating as page decoration

The visual memory should be “institutional execution console”: structured, compressed, stateful, and sober. It should not feel like a web landing page, consumer portfolio tracker, generic SaaS dashboard, or decorative crypto app.

### Bloomberg Influence With A Dark Operator Console

Use Bloomberg-like ideas:

- dense market-data tables
- strong status color language
- compact rows
- clear command/action zones
- ticker/instrument identity always visible
- terminal-style panels with crisp borders
- numeric alignment and concise labels

Do not copy Bloomberg’s black/orange literal theme. The product should feel like a modern internal trading terminal: dark, compact, and information-rich, but still readable for long sessions.

### Theme

Use a dark terminal base with blue-black structural surfaces. The overall look should match the provided reference: dark fixed sidebar, dark main canvas, dark panels with thin low-contrast borders, subtle teal selected states, compact route/entity cards, and small high-signal status chips.

Recommended palette direction:

```text
App background: near-black blue/green graphite
Sidebar: deeper blue-black with fixed chrome feel
Workspace surface: dark desaturated navy/teal black
Panel surface: slightly lifted dark graphite-blue
Panel border/grid lines: cool slate/teal lines at low opacity
Primary text: soft off-white, never pure white
Secondary text: blue-gray
Muted text: slate gray
Selected/focus: thin teal underline, border, or quiet row tint, not a large filled block
Positive/connected: restrained exchange green
Negative/risk/stop: clean muted red
Warning/live armed: controlled amber
Info/link: muted terminal blue
```

Avoid:

- bright neon-on-black
- purple/blue gradients
- glassmorphism
- decorative glow
- one-note beige or one-note slate
- large rounded cards everywhere
- big light surfaces inside dark chrome
- heavy shadows as depth
- literal Bloomberg orange dominance

### Typography

Use a practical terminal pairing:

- A legible sans for labels/body.
- A tabular-numeric face or font-feature setup for numbers.
- Monospace only where it adds value: IDs, timestamps, order ids, signal ids, route ids, and exact numeric readouts.

Text should be compact and crisp. Use small uppercase section labels, clear route titles, tabular aligned values, and strong object identifiers in the workbench header. Do not use oversized hero typography. This is an operational app.

### Density

The UI should be denser than v1 but not cramped. Favor:

- 32-36px table rows
- 28-32px detail rows in key/value panels
- sticky table headers
- compact filters
- split-pane work areas
- status chips with stable width
- table-first information design
- many small bounded panels on one screen when the workflow benefits from simultaneous context
- left-list/right-workbench compositions for object-heavy pages such as Engines, Development, and Trading

Avoid repeated metric cards as page decoration. Metrics should appear only where they directly help an operator decide what to do.

## Global Shell

The v2 shell should have three stable regions:

```text
Left rail: navigation and app identity
Main workspace: route/page content
Right/inspector panel: optional, page-specific selected entity details
```

For pages that do not need an inspector, main workspace should use full width. Do not force every page into the same two-column layout, but object-heavy pages should usually use the reference-image pattern: compact entity list on the left, detailed workbench on the right.

The shell must behave like an application, not a webpage. The left rail stays fixed in place while only the active workspace region scrolls. Page-level scrolling should be avoided; long tables, workbenches, and inspectors get their own bounded scroll regions. This keeps navigation and route context visible during research, data review, and live trading operations.

Recommended shell behavior:

```text
Viewport: 100vh app frame
Left rail: fixed/sticky, full height, no page-scroll coupling
Workspace: independent overflow region
Tables/panels: internal scroll when needed
```

This also means v2 should avoid landing-page conventions such as full-document sections, large vertical page journeys, or content that pushes navigation out of view.

### Dashboard-Only Top Bar And Metrics

The top bar and metric grid should exist only on the Dashboard. Other pages should not carry the global title block, hero copy, or dashboard metric cards. They should start directly with their working surface: filters, selected entity context, tables, workbench tabs, or route controls.

The Dashboard top bar should show operational context, not marketing copy:

```text
Motis Quant Terminal
API: ready
DB: configured
OKX CLI: connected/disconnected when relevant
Mode: live/demo where relevant
Current UTC time
```

The Dashboard top bar should not include a generic global “Run Cycle” button. Route actions belong on route cards or route detail panels only.

## Page Design Briefs

### Dashboard

Purpose: summarize system state and direct the user to the next operational task.

Primary content:

- API/database/worker readiness
- active route count and latest wake status
- open execution blockers
- latest Stage 0 batches
- latest Stage 1/2/3/4 development activity
- data coverage warnings

Layout:

- terminal status strip at top
- compact operational summary below
- recent activity table

Avoid decorative metric cards. Every dashboard item should answer: “what needs attention?” The Dashboard may use metric cells, but they should feel like terminal readouts in a system monitor, not marketing KPI cards.

### Data

Purpose: show canonical local market-data coverage and allow filling gaps.

Primary content:

- dataset catalog grouped by asset and data type
- raw candles as canonical source
- derived candles as dependent data
- coverage start/end with UTC timestamp precision
- row counts
- freshness status
- update/fill action per dataset or asset

Layout:

- left/filter rail for asset/type/timeframe
- main dense coverage table
- right inspector for selected dataset with refs, storage URI, derived dependencies, last fill result

Design emphasis:

- make source-of-truth obvious: Parquet is canonical for market data
- clearly distinguish raw vs derived
- show exact UTC timestamps, not just dates

### Engines

Purpose: show signal engines, required data, signal pool coverage, and update/generation actions.

Primary content:

- engine registry
- required data contract
- per-asset signal pool rows
- packet count
- scanned coverage end from canonical Parquet-backed market data
- emitted packet end from DB signal rows
- update signals action

Layout:

- engine list on left
- selected engine detail on right
- asset signal pool table as the dominant surface

Design emphasis:

- make the difference between scanned coverage and emitted packet coverage explicit
- show when no signal emitted despite scanned data
- expose failures and source refs without raw filesystem clutter in primary rows

### R&D: Stage 0

Purpose: create and review batch-level Stage 0 training sessions.

Primary user action:

Create a Stage 0 batch by choosing engine, tickers, train window, walk-forward window, forward hours, and trigger threshold.

Layout:

- left: past Stage 0 batch sessions table
- right: new batch setup form
- bottom or inspector: selected batch candidates table

Design emphasis:

- Stage 0 is universe/batch-level
- candidates are engine-asset pairs
- show evaluated signal count per candidate
- show accepted/watchlist/pending/failed counts
- “Open Development” should clearly move the user to candidate-level workflow

The form should use simple date inputs for train and walk-forward windows. No exact timestamp entry.

### R&D: Development

Purpose: develop one strategy-engine-asset candidate through Stage 1-4.

Primary user action:

Select one accepted Stage 0 candidate/session and work through stage-specific actions.

Layout:

- left queue: candidate/session list, grouped by Stage 0 batch
- top of workbench: selected candidate identity and current gate state
- stage tabs across the workbench: Stage 1, Stage 2, Stage 3, Stage 4
- selected stage panel only, not one growing page

Stage 1:

- show training and walk-forward test status
- show iterations as a compact ledger
- per-iteration actions: prompt, audit, score, delete
- freeze/canonical readout action when gates pass
- prompt modal/view should include absolute paths and scoped instructions

Stage 2:

- capture curve result
- required upstream artifact
- run/re-run action

Stage 3:

- grid setup and pyramid behavior search
- show selected TP/SL/pyramid candidates

Stage 4:

- realized expectancy and promotion readiness
- promote execution bundle action

Design emphasis:

- Development is candidate-level, not batch-level
- Stage 1 is iteration-heavy and needs the clearest UX
- Stage 2-4 should feel like stage tabs with crisp artifact requirements
- Do not expose raw artifact paths in primary action areas; put them in inspector/details

### Trading

Purpose: operate promoted execution routes.

Primary user action:

Start/stop a route lifecycle and understand whether it is safe to auto-submit live orders.

Layout:

- left: narrow promoted route list
- right: selected route detail
- right detail sections:
  - route status and lifecycle control
  - execution setup: cron, exchange, account profile, margin allocation, leverage, live orders toggle
  - bundle setup summary: TP, SL, pyramid legs, step, max hold
  - exchange health: OKX CLI connected/blocked/disconnected
  - latest wake
  - pending intent
  - exchange snapshot
  - recent decisions

Design emphasis:

- one route equals one strategy-engine-asset-account execution lane
- route cards should be compact list entries, not tall dashboards
- the selected route detail should read like an execution console with workbench tabs, key/value setup rows, wake logs, pending intent, and exchange snapshot
- if scheduler is running, primary button must say Stop Execution
- if live orders are off, label it intent-only mode
- if live orders are on, make risk state unmistakable
- protection update, pyramid, entry, and exit intents should be visibly different

## Interaction Model

### Refresh And Polling

Use React Query as in v1. Add conservative polling only where useful:

- Trading route list and selected wakes: short interval when selected route is running.
- Exchange health: manual refresh plus stale indicator; avoid heavy polling.
- Data/engines/R&D: manual refresh or mutation-driven refresh.

### Selection

Selected row state should be URL-backed where practical:

- selected route
- selected Stage 0 batch
- selected development session/candidate
- selected engine/asset

This prevents refresh from losing workflow context.

### Confirmation

Live-order actions still require explicit confirmation through existing API request fields and UI confirmation copy. v2 should not weaken live execution gates.

### Loading And Error States

Every page needs:

- initial loading state
- empty state
- mutation pending state
- API error state
- stale data indication where route execution is involved

Errors should be concise and operational. Example:

```text
Signal update blocked: canonical raw 5m candles missing for AAVE.
```

## Component System

Build v2 from small components rather than another monolithic `main.tsx`.

Recommended structure:

```text
apps/web-v2/src/
  app/
    router.tsx
    queryClient.ts
    api.ts
  shell/
    TerminalShell.tsx
    SidebarNav.tsx
    CommandBar.tsx
  components/
    StatusBadge.tsx
    DataTable.tsx
    SplitPane.tsx
    InspectorPanel.tsx
    ConfirmButton.tsx
    FieldRow.tsx
    MetricCell.tsx
  pages/
    DashboardPage.tsx
    DataPage.tsx
    EnginesPage.tsx
    ResearchStage0Page.tsx
    ResearchDevelopmentPage.tsx
    TradingPage.tsx
  styles/
    tokens.css
    base.css
    shell.css
    tables.css
    forms.css
```

API functions can live in `app/api.ts` initially. If it grows too large, split by domain:

```text
api/marketData.ts
api/engines.ts
api/research.ts
api/trading.ts
```

## Aesthetic System

### Token Categories

Use CSS custom properties:

```text
--surface-base
--surface-panel
--surface-raised
--surface-selected
--surface-workbench
--surface-list
--ink-primary
--ink-secondary
--ink-muted
--line-subtle
--line-grid
--line-strong
--status-pass
--status-warn
--status-risk
--status-live
--status-idle
--space-1 through --space-8
--radius-sm
--radius-md
```

Cards should use `8px` radius or less. Tables and panels should use tighter radius where appropriate.

Panel depth should come from surface contrast and border/grid discipline, not from large shadows. Prefer one-pixel separators, sticky headers, and tight internal rhythm.

### Table Rules

- Numeric columns right-aligned.
- IDs use clipped monospace with tooltip/copy affordance.
- Sticky headers for long tables.
- Row hover should be subtle.
- Selected rows should use a quiet tint, not heavy shadows.
- Status cells should have stable width to avoid layout shift.
- Table borders should be fine and cool-toned, closer to terminal grid lines than spreadsheet boxes.
- Important table rows may have denser metadata, but row height should stay stable.

### Button Rules

- Icon + label for major commands.
- Icon-only allowed for refresh/copy/delete when tooltip or accessible label is present.
- Live-risk actions must not look like ordinary primary actions.
- Stop Execution should be visually distinct from Start Execution.
- Toolbars should be compact and horizontal; avoid large page-level button blocks.

## Functional Parity Checklist

v2 is not complete until these v1 behaviors are present:

- Dashboard loads catalog/engine/stage summaries.
- Data page lists canonical market data refs and can refresh/fill datasets.
- Engines page lists engines, signal sets, coverage, and update signal pool actions.
- Stage 0 page can create batch sessions, auto-run Stage 0 candidates, delete batches, and open accepted candidates.
- Development page can create Stage 1 sessions, create/delete iterations, score training/walk-forward, generate audit/prompt, run canonical readout, run Stage 2, Stage 3 grid, Stage 3 pyramid, Stage 4, and promote execution bundle.
- Trading page can list routes, update route settings, check exchange health, start/stop lifecycle, show latest wakes, show pending intents, manually submit intents, and reflect auto-submit/live-order mode.
- All top-level and sub-level tabs survive refresh through URL routing.

## Build Sequence

### Phase 1: Shell And Style Only

- Add `apps/web-v2`.
- Configure Vite/React/TypeScript.
- Add route-backed shell.
- Build terminal visual tokens.
- Add static placeholder pages.
- Run v2 on port `5174`.

Success criteria:

- v1 still runs on `5173`.
- v2 runs on `5174`.
- Refresh preserves selected tab route.
- Visual system reads as a dark institutional trading terminal matching the reference image’s overall density, chrome, and panel language.

### Phase 2: Shared API Client And Dashboard

- Port API base handling.
- Port health/catalog/summary queries.
- Build dashboard with operational status.

### Phase 3: Data Page

- Port market-data catalog and refresh actions.
- Improve coverage table and selected dataset inspector.

### Phase 4: Engines Page

- Port engine list, signal sets, signal coverage, and update signals.
- Clarify scanned coverage vs emitted packet coverage.

### Phase 5: R&D Stage 0

- Port batch creation, batch list, progress, candidates, delete, and open development handoff.

### Phase 6: R&D Development

- Port Stage 1-4 flows with stage-tab workbench layout.
- Make Stage 1 iteration workflow much clearer than v1.

### Phase 7: Trading

- Port route list, settings, exchange health, lifecycle start/stop, wakes, pending intents, manual submit.
- Make live-order mode and intent-only mode visually unambiguous.

### Phase 8: Parity QA And Cutover Readiness

- Compare v1/v2 endpoint behavior page by page.
- Run `npm run build:web` for v1 and v2 equivalent build.
- Browser-test v2 routes and refresh persistence.
- Only then discuss replacing v1 or keeping both.

## Testing Plan

Frontend:

- TypeScript build for v2.
- Browser smoke test for each route.
- Refresh persistence checks for all top-level tabs and R&D sub-tabs.
- Mutation smoke tests against local API where safe.
- No live order submission tests unless explicitly authorized.

Backend:

- No new backend tests required unless v2 exposes an existing API mismatch.
- Existing backend suite should remain unchanged and passing.

UX checks:

- Data-dense pages remain readable at 1280px width.
- Tables do not overflow incoherently on laptop viewport.
- No route action appears globally outside its route context.
- Live Trading controls clearly distinguish intent-only vs auto-submit.

## Risks And Mitigations

### Risk: v2 Drifts From v1 Functionality

Mitigation: port one page at a time with a parity checklist. Do not redesign workflow semantics while porting.

### Risk: The Terminal Aesthetic Becomes Too Dark

Mitigation: keep the dark theme, but separate surfaces with sufficient contrast, use soft off-white primary text, avoid pure black, and test long tables for readability at laptop brightness. Do not solve readability by switching workspaces back to light panels.

### Risk: Another Monolithic Frontend File

Mitigation: enforce page/component/API separation from the scaffold.

### Risk: Route State Becomes Confusing

Mitigation: use URL-backed route state for tabs and selected primary entities. Avoid hidden local-only selected state for workflow-critical selections.

### Risk: Live Trading Controls Become Too Easy To Misuse

Mitigation: preserve confirmation copy, status gates, and explicit Live Orders toggle. Make live auto-submit visually distinct.

## Open Decisions For Implementation

- Whether v2 should use `@tanstack/react-router` formally or a smaller custom URL-state router.
- Whether v2 should import lucide icons like v1 or reduce icon usage for a more terminal-native feel.
- Whether v2 should later replace `apps/web` or remain as `apps/web-v2` until a manual cutover.

## Self-Review

- No backend changes are required or proposed.
- v1 stays alive on its current port while v2 is built on a separate port.
- Refresh persistence is handled through URL-backed navigation.
- The design is dense, dark, and terminal-oriented without relying on neon, gradients, glass, or decorative glow.
- The build plan ports existing functionality page by page instead of changing workflows during redesign.
