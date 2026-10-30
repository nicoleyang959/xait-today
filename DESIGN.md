---
name: xAIT 今日
description: Existing bilingual daily reader and its optional private project library.
colors:
  bg: "var(--bg)"
  surface: "var(--surface)"
  surface-alt: "var(--surface-alt)"
  text: "var(--text)"
  text-soft: "var(--text-soft)"
  muted: "var(--muted)"
  faint: "var(--faint)"
  border: "var(--border)"
  accent: "var(--accent)"
  accent-ink: "var(--accent-ink)"
typography:
  display:
    fontFamily: "var(--font-display)"
    fontSize: "clamp(2rem, 4vw, 2.55rem)"
    fontWeight: 700
    lineHeight: 1.08
    letterSpacing: "-.02em"
  body:
    fontFamily: "var(--font-body)"
    fontSize: "16px"
    lineHeight: 1.7
  mono:
    fontFamily: "var(--font-mono)"
rounded:
  radius: "var(--radius)"
components:
  reading-settings:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text-soft}"
    rounded: "{rounded.radius}"
    padding: "7px 11px"
  archive-active:
    backgroundColor: "{colors.bg}"
    textColor: "{colors.accent}"
    padding: "5px 8px"
  reader-card:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.radius}"
  project-save:
    backgroundColor: "transparent"
    textColor: "{colors.accent}"
    rounded: "3px"
    padding: ".12rem .42rem"
  records-button:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius}"
    padding: "7px 12px"
  records-primary:
    backgroundColor: "{colors.accent}"
    textColor: "{colors.accent-ink}"
    rounded: "{rounded.radius}"
    padding: "7px 12px"
  records-field:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.radius}"
    padding: "9px 10px"
---

# Design System: xAIT 今日

## Overview

This is a source-derived record of the existing interface, not a replacement visual direction. The visual authority is the implemented xAIT 今日 reader: seven selectable themes, bilingual reading, a compact project table, a dated archive sidebar, and responsive reading controls. The same content structure persists across themes; palette, system font, corner treatment, and selected theme accents supply their character.

The optional private project library extends that interface with a same-page `#saved` view. It inherits the selected theme and keeps the masthead and archive navigation. Its local layout and state rules are recorded here; its task sequence remains in `.impeccable/records-direction.md` and `.impeccable/surfaces/site-templates-page-html.md`. No new brand metaphor or palette has been selected.

Evidence: `PRODUCT.md`, the two direction briefs, `site/assets/app.css`, `site/assets/records.css`, `site/assets/app.js`, `site/assets/records-ui.js`, `site/templates/page.html`, `site/templates/records.html`, and the generated `docs/index.html`. This document records implementation facts and constraints. It does not certify cloud deployment, OAuth, server permissions, or real two-device acceptance.

**Key Characteristics:**

- Theme-controlled color and system typography, without remote fonts.
- Dense reading hierarchy, explicit dates and sources, compact tabular project data.
- Thin borders and tonal surfaces; depth and corners vary with the selected theme.
- A restrained library list with labelled controls, inline notes, and text-based storage/sync feedback.

The frontmatter aliases the CSS custom properties already used by the page. These aliases describe the live selected theme; they do not introduce new application tokens. The literal tables below record the current implementations of those aliases. CSS remains the implementation source of truth. There is no shared spacing-token scale in the source, so none is invented here.

## Colors

### Primary

The existing `accent` supplies links, selected theme/language controls, active archive markers, focus outlines, save controls, and the library's primary actions. `accent-ink` supplies text on filled accent controls. Library state labels use the current accent and explicit words; there is no separate success, warning, or error palette.

| Selected theme | Accent character | `accent` | `accent-ink` |
| --- | --- | --- | --- |
| 数据终端 / Terminal | Bright terminal green | `#33ff45` | `#031006` |
| 赛博霓虹 / Cyber | Cyan | `#00e8ff` | `#001115` |
| 瑞士国际主义 / Swiss | Cobalt blue | `#2149d8` | `#ffffff` |
| 编辑杂志 / Editorial | Brick red | `#8d2c25` | `#fffaf2` |
| 高端咨询报告 / Consulting | Warm brown | `#805719` | `#ffffff` |
| 极简科技 / Minimal | Violet | `#6a45ff` | `#ffffff` |
| 柔和纸张 / Paper | Muted green | `#47654f` | `#fffdf6` |
| Root fallback, not a selectable theme | Dark red | `#8b1a1a` | `#ffffff` |

### Neutral

`bg` is the page canvas; `surface` holds reading containers, fields, and controls; `surface-alt` distinguishes sidebars, table headings, selected saves, and feedback. `text` carries primary content, `text-soft` secondary reading copy, `muted` metadata, and `faint` small labels. `border` supplies dividers and control edges.

| Theme | `bg` | `surface` | `surface-alt` | `text` | `text-soft` | `border` |
| --- | --- | --- | --- | --- | --- | --- |
| Terminal | `#050806` | `#070b08` | `#0a100b` | `#33ff45` | `#21d934` | `#13541a` |
| Cyber | `#070713` | `#0d0d1d` | `#121329` | `#e7fbff` | `#c7dce2` | `#174754` |
| Swiss | `#f2f2ef` | `#fafaf8` | `#e8e8e4` | `#111317` | `#34383f` | `#c8cbd0` |
| Editorial | `#ebe4d8` | `#fbf7ef` | `#f1e9dc` | `#201b18` | `#514941` | `#cfc1af` |
| Consulting | `#e9edf2` | `#ffffff` | `#f2f5f8` | `#142238` | `#33445a` | `#c9d1da` |
| Minimal | `#f7f7f7` | `#ffffff` | `#fafafa` | `#171717` | `#414141` | `#e2e2e2` |
| Paper | `#d9d0c1` | `#f7eedf` | `#eee2cf` | `#3c3027` | `#594a3d` | `#d2c0a5` |
| Root fallback | `#fdfcfa` | `#ffffff` | `#f7f4ef` | `#151515` | `#454545` | `#d2cec7` |

| Theme | `muted` | `faint` |
| --- | --- | --- |
| Terminal | `#159724` | `#159724` |
| Cyber | `#7f98a2` | `#7f98a2` |
| Swiss | `#5e626b` | `#5e626b` |
| Editorial | `#6e6156` | `#6e6156` |
| Consulting | `#5d6c7e` | `#5d6c7e` |
| Minimal | `#6b6b6b` | `#6b6b6b` |
| Paper | `#6c5949` | `#6c5949` |
| Root fallback | `#747474` | `#9b9b9b` |

Terminal and Cyber declare a dark color scheme; the other selectable themes declare light. The template starts in Terminal, and the existing preference logic restores a valid remembered theme.

Theme-specific exceptions already exist: Swiss has a blue sidebar with white text; Consulting uses a navy sidebar with pale text; Minimal uses a white sidebar; Paper uses a beige sidebar and a muted green card edge. Cyber's grid and Paper's dot texture are CSS backgrounds. These exceptions belong to their themes and are not additional library colors or raster assets.

**The Theme Inheritance Rule.** Extend the existing semantic properties for library surfaces, content, and controls. Keep all seven theme definitions and their existing exceptions.

## Typography

**Display and body fonts:** both follow the current theme's system stack. They are separate CSS properties even when their values match.

- Terminal: `ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, monospace`.
- Cyber, Consulting, and Minimal: `ui-sans-serif, -apple-system, BlinkMacSystemFont, "Segoe UI", "PingFang SC", sans-serif`.
- Swiss: the same sans stack with `"Microsoft YaHei"` before `sans-serif`.
- Editorial, Paper, and the root fallback: `ui-serif, "Songti SC", "STSong", "SimSun", Georgia, serif`.

**Metadata/mono font:** `ui-monospace, "SFMono-Regular", Menlo, Monaco, Consolas, "Liberation Mono", monospace`, inherited from the root across themes.

The body uses a generous reading line-height while metadata and controls are deliberately smaller. Library typography uses the body stack rather than introducing another family. The source mixes px and rem; reducing body size below 420px does not change the root rem size.

| Existing role | Size / line-height | Weight and treatment |
| --- | --- | --- |
| Page masthead | `clamp(2rem, 4vw, 2.55rem)` / `1.08` | `700`, `-.02em` tracking; Editorial alone uses `clamp(2.3rem, 5vw, 3.5rem)` |
| Body | `16px` / `1.7` | Inherited normal weight; `15px` at widths up to `420px` |
| Reader module heading | `1.45rem` / `1.3` | `700`, display stack |
| Reader section heading | `1.3rem` / `1.35` | `700`, display stack |
| Table heading | `.78rem` / `1.4` | `700`, display stack, `.04em` tracking |
| Library heading | `clamp(1.65rem, 2.4vw, 2rem)` / `1.2` | `700`, body stack, `-.02em` tracking; `1.4rem` at widths up to `600px` |
| Saved-project title | `1rem` / `1.4` | `700`, body stack |
| Library form labels | `.82rem` / inherited | `600` |
| Library fields | `.9rem` / `1.5` | `400` |
| Library buttons | `.8rem` / `1.35` | `600` |
| Compact save | `.72rem` / `1.4` | `600` |
| Saved-project URL and metadata | `.76rem` / `1.5` for URL | Soft text; wrap long content |
| Saved notes | `.86rem` / inherited | Preserve whitespace; maximum width `72ch` |

The Chinese and English UI share this hierarchy. Library labels, placeholders, accessible labels, and state copy follow the selected language. User notes retain the language entered by the user. Do not replace them with translated text or change factual content to fit a layout.

## Layout

The desktop page is a flex layout: a sticky archive sidebar (`220px` wide, viewport height) and a flexible main area with `min-width: 0`. The masthead and reader container are centered at `min(980px, 100%)`. The project library uses a compact masthead while its working view is open. Desktop horizontal padding is `36px`; the reader's bottom padding is `42px`. The masthead separates identity and reading controls with a `22px` gap. Reading content uses two-column module grids with `16px` gaps, with source-specific full-width sections.

The library replaces only the briefing area inside the existing reader container. Its own maximum width is `1120px`, but that does not expand the enclosing `980px` reader. A header and return link precede account/status feedback, search/status controls, manual addition, backup actions, the aligned project list, and the inline notes editor. Search and status use `minmax(0, 1fr) minmax(160px, 220px)` with a `16px` gap. Forms use two equal flexible columns with `14px 18px` gaps. List rows use a flexible content column and automatic action column, `12px 24px` gaps, and `20px` vertical padding.

There is no single mathematical spacing scale in the implementation. Reused measured spacings include `8px` action gaps, `12px` panel/list gaps, `16px` grid gaps, `18px` section/control separation, and `24px` major library separation. Preserve the local density rather than creating a new global scale.

### Existing responsive behavior

| Breakpoint | Implemented change |
| --- | --- |
| Up to `920px` | Masthead stacks; display settings and the projects link wrap together, with an expanded settings panel occupying the available width; some social metadata moves below content. |
| Up to `840px` | Sidebar becomes an off-canvas panel of `min(82vw, 290px)`; masthead has room for the fixed toggle; container padding becomes `18px`; content grids become one column; theme choices use four columns; project tables become labelled rows. |
| Up to `600px` | Library tools, forms, rows, and conflict comparison become one column; account label takes a full line; actions align to the start; toast uses `16px` side and bottom offsets. |
| Up to `420px` | Container padding becomes `10px`; body becomes `15px`; settings/theme controls and project table rows simplify further; theme choices use two columns. |

Desktop GitHub tables keep four columns (`28% / 15% / 15% / 42%`) from `841px`, with `10px 12px` cell padding and wrapped long text. Their minimum width is zero, overriding the generic table's `540px`. At `840px` and below, headers are visually hidden and cell labels come from `data-label`; rows use two columns, then one at `420px`. Compact save controls sit next to the project name and do not add a table column.

Sidebar expansion/collapse and theme selection retain their existing memory. A collapsed sidebar is hidden and inert, with its state reflected on the toggle. Opening the library focuses its heading and stores the reading position; returning restores the briefing position and the previous focus when available. These are navigation behavior, not new page layouts.

## Elevation & Depth

Depth is theme-dependent. The root, Terminal, and Swiss have no shared outer shadow; other themes define one. Most library structure remains flat, separated by a border or alternate surface. The settings panel, mobile archive, modal backdrop, and toast provide contextual depth. The library does not wrap every saved record in a card.

### Shadow Vocabulary

| Existing use | Exact CSS value |
| --- | --- |
| Root shared shadow; Terminal and Swiss inherit | `none` |
| Cyber shared shadow | `0 0 24px rgba(0,232,255,.07)` |
| Editorial shared shadow | `0 10px 32px rgba(49,36,24,.08)` |
| Consulting shared shadow | `0 8px 28px rgba(20,34,56,.09)` |
| Minimal shared shadow | `0 14px 45px rgba(0,0,0,.045)` |
| Paper shared shadow | `0 12px 30px rgba(66,48,30,.09)` |
| Terminal reading/social containers | `inset 0 0 24px rgba(51,255,69,.018)` |
| Desktop settings panel, after the theme shadow | `0 12px 30px rgba(0,0,0,.12)` |
| Mobile archive sidebar | `12px 0 34px rgba(0,0,0,.14)` |
| Library toast | `0 5px 20px rgb(0 0 0 / .18)` |

The modal uses a fixed black backdrop (`rgb(0 0 0 / .5)`). Terminal and Cyber set a theme glow (`rgba(51,255,69,.42)` and `rgba(0,232,255,.42)` respectively); selected theme controls use that glow, and Cyber applies it to selected decorative reader details.

Motion stays functional: theme color changes use `.18s ease`; sidebar geometry uses `.22s ease`; archive-toggle color uses `.15s ease`; library buttons use `.16s ease` for border/background color. The reduced-motion query removes smooth scrolling and reduces general animation/transition duration; library button transitions are disabled explicitly. Toast visibility currently lasts `6000ms`.

## Shapes

The reader's shared radius is theme-controlled: Terminal `0`, Cyber `3px`, Swiss `0`, Editorial `12px`, Consulting `2px`, Minimal `14px`, and Paper `8px`. Reading cards, navigation pills, the sidebar toggle, and display settings use that property, generally with `1px` borders. The masthead uses a double rule by default, with existing theme-specific treatments.

Fields and regular buttons inherit the theme radius; compact save controls use `3px`, toast `6px`, and dialog `10px`. Feedback and conflict-version boxes use square bordered surfaces. These local values are documented facts, not changes to the reader radius token.

### Existing differences to retain as evidence

- Library fields and buttons inherit the selected theme radius; the toast and dialog retain their local radii.
- The library's `1120px` maximum is wider than its enclosing reader's `980px` maximum, so the outer reader remains the effective width constraint.
- Toast shadow and modal backdrop are fixed across themes; they are not driven by the shared shadow or glow properties.
- Reader settings use the mono stack; library controls use the body stack. Their focus outline offsets also differ (`2px` for general reader controls, `3px` for library controls).
- Status and error emphasis share the theme accent; the text and action explain the state. There is no independent semantic status color system.

These differences are intentional aspects of the implemented system.

## Components

### Buttons

Reader theme/language controls use the theme surfaces and radius. Active choices fill with accent and accent-ink, and pressed state is exposed accessibly. The archive toggle stays compact (`34px` square). Language controls become at least `38px` high below `840px`.

Compact project saves are inline-flex, with a `.3rem` icon/label gap, `.6rem` leading margin (`.35rem` below `600px`), and an `.85rem` icon. They have a thin border and transparent background. A saved state uses primary text on the alternate surface and `aria-pressed="true"`. Hover shifts border/text to accent; disabled controls use `.65` opacity and a not-allowed cursor. These controls retain explicit text, not an icon-only action.

Regular library buttons have a minimum height of `40px` (`44px` on small screens), a thin border, and the selected theme radius. Primary actions fill with accent and accent-ink; primary hover applies `brightness(.92)`. Destructive actions use a softer-text border and explicit wording. Focus uses a `2px` accent outline with `3px` offset. Disabled state must remain distinct from success.

### Cards / Containers

The reader's dated article is a theme-surfaced, bordered container; its body padding is `8px 24px 24px` on desktop and `5px 17px 20px` below `840px`. Theme-specific edges, shadows, and heading details remain intact. The library uses a plain list with border-separated rows, an inline editor on a theme-surface panel, and alternate-surface feedback. It does not introduce decorative image cards or nested collection cards.

### Inputs / Fields

Library labels remain visible above their fields, with a `6px` label gap. Inputs/selects/textareas use a surface background, text color, thin theme border, accent caret, and the existing local radius. Placeholders use soft text at full opacity. Textareas resize vertically and have a minimum height of `130px`. Long titles, URLs, notes, account names, and messages wrap; note whitespace is preserved. Field constraints and help text remain visible where supplied.

### Navigation

The archive uses a `2px` leading marker: transparent at rest, border-colored on hover, accent-colored when active. Active links use accent text and stronger weight; theme-specific sidebar overrides still apply. Settings remain a native disclosure. The masthead contains one My projects link to `#saved`; the library provides Back to briefing. No second navigation system is introduced.

### Project table and saved list

The compact reader table remains the discovery surface. A source save action has a text label and pressed/disabled state. The library row separates project identity and private notes from editing/removal actions, with the research state and synchronization state written in the metadata. The three research states remain 待研究 / To research, 已体验 / Tried, and 重点关注 / Watching.

### Storage, synchronization, and gates

Feedback, sync state, and toast regions announce updates politely. Local save copy says the project or notes were saved on this device; cloud copy says cloud confirmation. Pending, offline, draft, conflict, and error remain separate visible text states. The saved button is evidence of a local record, not cloud acknowledgement. A storage failure must not present a success state.

The shipped default configuration is disabled with empty cloud fields. The visible library gate explains that cloud saving is not configured; login stays hidden and source save controls stay disabled. A configured sign-in gate is a separate state. Human cloud registration/configuration and genuine acceptance evidence are required before calling the optional service available. Documentation and simulated UI states do not establish real backend/OAuth/two-device success.

### Dialog and toast

The native modal dialog is at most `640px` wide with `16px` viewport clearance, `24px` padding (`20px` below `600px`), and scrolling within the available viewport. Conflict versions are shown side-by-side, then stacked below `600px`, without discarding either text. Cancellation is the default focus/return value, and focus returns to the invoking control.

The toast is fixed above content at a `20px` right/bottom offset, at most `420px` wide and constrained to the viewport. Mobile uses `16px` side/bottom offsets. It uses the current theme's surface/text/accent, a thin accent border, the local radius, and the fixed shadow listed above. Its message remains honest about local persistence and cloud acknowledgement.

## Do's and Don'ts

### Do

- **Do** preserve the seven themes, their memory, existing font stacks, and theme-specific reader details.
- **Do** keep the bilingual reader, dated archive sidebar, compact GitHub table, visible focus, and mobile labelled rows.
- **Do** inherit theme colors and body typography for library controls and use explicit text for research/storage/sync state.
- **Do** preserve a reader's position and focus when they return from the library.
- **Do** keep disabled, empty, filtered-empty, offline, pending, conflict, and storage-failure states understandable in both UI languages.
- **Do** keep private user notes outside public content and leave their entered language intact.

### Don't

- **Don't** replace the incumbent visual identity or consolidate seven themes into one new palette.
- **Don't** add remote fonts, decorative raster imagery, or a new image-based brand system for the library.
- **Don't** expand the GitHub table with a separate save column or replace the compact list with nested cards.
- **Don't** use color alone to imply saved, synced, failed, or conflicted state.
- **Don't** treat local persistence as cloud success, or document an unconfigured/untested cloud service as live.
- **Don't** reinterpret this source-derived record as authorization to normalize the documented local differences.
