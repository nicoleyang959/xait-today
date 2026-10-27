# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Users

Readers browse the public daily AI briefing on desktop and mobile. Any reader
may opt into a private project library using their own GitHub identity. Readers
must never see another reader's saved projects or notes.

## Product Purpose

xAIT 今日 helps readers discover useful public AI projects and retain their own
research: save a project without interrupting reading, then add notes and track
whether it is to research, tried, or being watched.

## Operating Context

The public briefing is a deterministic static site on GitHub Pages, with genuine
dated archives and a Python-standard-library build. The library is a separate,
optional Supabase Free and GitHub OAuth capability. First login requires a
network connection; an established account may record offline and synchronize
later. Free service interruptions must not break the public briefing.

## Capabilities and Constraints

- One-click saves for GitHub and Product Hunt project entries with verified
  project links, plus manually entered safe HTTP/HTTPS links.
- Private notes and three states: 待研究, 已体验, 重点关注. No public sharing,
  ratings, custom tags, attachments, automatic summaries, or extra collection.
- Account-isolated IndexedDB records and an atomic outbox. Local persistence and
  cloud acknowledgement are distinct states. Conflicts must not erase notes.
- JSON backup/restore and Markdown export never include authentication data.
- Cloud capability is disabled until explicitly configured and verified. Clone
  users can still build and read without npm, Docker, cloud access, or secrets.
- Private records, credentials and browser state never enter public issues,
  generated briefing content, collection inputs, Git or daily publication.
- Cloud registration, terms and OAuth-secret configuration require the human.
  Do not purchase plans or automatically upgrade billing.

## Brand Commitments

Preserve xAIT 今日, its seven existing themes, bilingual reading, compact GitHub
tables, archive sidebar, and responsive reading behavior. Extend the established
interface rather than replacing its visual identity.

## Evidence on Hand

The repository contains real public issue JSON, static templates, CSS/JS,
language catalogs and regression tests. Cloud configuration and real multi-device
acceptance evidence are not supplied; do not fabricate either.

## Product Principles

- Reading stays available even when the optional private service fails.
- One quick save, followed by deliberate private research.
- Never claim cloud success before acknowledgement or local success before a
  successful storage transaction.
- Identity, versions and explicit choices—not device time—resolve changes.
- Privacy and safe defaults are part of the user experience.

## Accessibility & Inclusion

All controls must be keyboard-operable, labelled, responsive and usable under
all seven themes. Saving and synchronization feedback is announced accessibly.
UI labels follow the selected language; user notes are never auto-translated.
