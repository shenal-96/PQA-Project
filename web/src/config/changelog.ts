// Single source of truth for the app version and its change history.
//
// The version chip shown in the top bar / sidebar / help dialog is always
// `APP_VERSION` (the newest entry below). To cut a release: add a new entry to
// the TOP of CHANGELOG with the bumped version, today's date, and the features /
// fixes it shipped. Nothing else needs editing — every surface reads from here.
//
// Keep `DEVELOPER_EMAIL` in sync with `desktop/usage_log.py:DEVELOPER_EMAIL`
// (the desktop bridge is the authoritative copy; this one drives the in-browser
// `mailto:` fallback for feature requests / bug reports).

export type ChangeKind = 'feature' | 'fix';

export interface ChangelogChange {
  kind: ChangeKind;
  text: string;
}

export interface ChangelogEntry {
  /** Display version, e.g. "v4.2". */
  version: string;
  /** Release date, ISO `YYYY-MM-DD`. */
  date: string;
  /** Optional one-line headline for the release. */
  title?: string;
  changes: ChangelogChange[];
}

/** Newest first. The first entry's `version` is the live app version. */
export const CHANGELOG: ChangelogEntry[] = [
  {
    version: 'v4.2',
    date: '2026-06-28',
    title: 'Version history & in-app feedback',
    changes: [
      { kind: 'feature', text: 'The version number in the top bar is now a button — click it to see every release and what changed.' },
      { kind: 'feature', text: 'Request a new feature or report a bug straight from the app; your message opens a pre-addressed email to the developer.' },
      { kind: 'fix', text: 'ISO 8528-5 two-band recovery no longer reports a false re-entry when the frequency never leaves the start band.' },
    ],
  },
  {
    version: 'v4.1',
    date: '2026-06-26',
    title: 'Report sections & sidebar polish',
    changes: [
      { kind: 'feature', text: 'Optional Compliance summary table and ITIC (CBEMA) curve sections can be added to any report, even when the template has no placeholder for them.' },
      { kind: 'feature', text: 'PDF reports are now produced by direct Word conversion, with the ITIC and compliance sections grouped onto their own page.' },
      { kind: 'feature', text: 'Per-field tooltips added throughout the configuration sidebar.' },
      { kind: 'fix', text: 'ITIC and compliance sections are now anchored off the time-series plots, so they land in the right place regardless of how the template styles its headings.' },
    ],
  },
  {
    version: 'v4.0',
    date: '2026-06-23',
    title: 'Native desktop app',
    changes: [
      { kind: 'feature', text: 'PQA is now a native desktop application — no browser or internet connection required.' },
      { kind: 'feature', text: 'Persistent Word-template library: upload your report templates once and reuse them across sessions.' },
      { kind: 'feature', text: 'Preset configurator, per-snapshot report overrides, and a resizable configuration sidebar.' },
      { kind: 'feature', text: 'Local usage logging and crash reporting to help diagnose problems, with nothing leaving your machine unless you choose to send it.' },
    ],
  },
];

/** The live application version (newest changelog entry). */
export const APP_VERSION = CHANGELOG[0].version;

/**
 * Where feature requests and bug reports are emailed. Mirror of
 * `desktop/usage_log.py:DEVELOPER_EMAIL`. Used for the in-browser `mailto:`
 * fallback; the desktop app routes through the Python bridge instead.
 */
export const DEVELOPER_EMAIL = 'sperera@penskeanz.com';
