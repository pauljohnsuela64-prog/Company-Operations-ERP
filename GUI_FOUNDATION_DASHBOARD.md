# GUI modernization — Phase 1

The shell and dashboard adopt a navy/slate/white foundation without changes to
application routes, repositories, database code, permissions or operational policy.

## Reusable presentation

`static/css/style.css` defines `--erp-*` tokens for colors, font family, spacing,
radii, shadows and maximum content width. Bootstrap 5.3.8 remains the existing
framework; no dependency or navigation framework is added. Shared buttons and
form controls adopt the foundation. Existing module layouts are not migrated.

The header retains all six permission-aware navigation groups and their exact
links. The native details/summary structure and `navigation.js` controller are
unchanged, including arrow keys, Escape, focus return, viewport menu clamping,
mobile toggle, active states, breadcrumbs, skip link and CSRF-protected logout.
Flash messages gain consistent surfaces and accessible status/alert semantics.

`partials/dashboard_components.html` exposes presentation-only `section`, `kpi`
and `metrics` macros. The caller remains responsible for permission checks. KPI
panels distinguish primary totals from labeled status details and preserve links,
including the APPROVED expense filter and latest-paid Payroll period labels.
Attendance Half Day and lost assets now also display their existing summary values.
No synthetic trends, totals across snapshots, currency amounts or business rules
are inferred. Unavailable data has a dashed panel and explicit text, without a
numeric placeholder; legitimate zero counts remain numeric. An account without
module visibility receives a dedicated empty state.

## Verification workflow

Run the full Python suite, navigation JavaScript tests, CI syntax checks and
`pip check`. For isolated Chrome checks:

1. Save the existing Bootstrap 5.3.8 CDN stylesheet in a temporary file.
2. Set `ERP_GUI_BOOTSTRAP_CSS` to that file and `ERP_GUI_SCREENSHOTS` to a temporary
   artifact directory.
3. Run `python -u -B tests/mysql_gui_foundation_browser.py` with installed MySQL
   and Chrome, using the existing disposable-server identity and cleanup guards.

The wrapper composes the existing cross-module security and HR browser reviews.
It serves the exact Bootstrap stylesheet through CDP, with all other external
browser requests blocked. Browser security flags remain unchanged. The zero-data
fixture is a test-only reader override on the real authenticated dashboard route;
it is not registered in production. Screenshots remain local review artifacts.
The browser matrix covers an all-module synthetic operator, HR Manager without
Administration/Payroll grants, and an account without module permissions at
1440, 1024, 768, 390 and 320 CSS pixels (1000-pixel viewport height), including
keyboard menus, mobile navigation, empty/unavailable/zero states, overflow and
panel overlap. Existing synthetic security tests exercise auth, CSRF and denial.

Phase 1 verification passed: 516 Python tests, 11 JavaScript navigation tests,
161 Python sources/109 Jinja templates and 22 JavaScript syntax checks, dependency
consistency and whitespace. Dashboard and Finance reporting disposable suites
passed. The composed Chrome 155 security/HR/visual review passed with the full
role/width matrix above, no observed panel overlap/horizontal overflow, no uncaught
JavaScript exceptions or console.error calls. Representative desktop/tablet/mobile
screenshots, open menus, empty and zero states were manually inspected. Eleven
foundation text/background pairs have calculated contrast of at least 5.18:1;
this is not a full accessibility certification. Full-page captures use the full
viewport width to avoid cropping the scrollbar-width gutter; open-menu captures
use the viewport to avoid resizing and closing the native menu during capture.

## CI and limits

Post-merge main run 39718347822 failed starting disposable MySQL for Finance
reporting before application assertions ran: loopback port 55290 timed out (10060)
and the identity safeguard retained the unverified server. Python/JavaScript jobs
passed. This repeats the earlier hosted startup symptom; its root cause remains
unproven. No startup timeout, identity check or CI harness is changed here. The
Finance reporting suite passes locally with verified identity and clean shutdown.

This phase does not redesign module interiors, login or application-wide tables.
Other module forms receive shared control styling only. Bootstrap still uses the
existing CDN in production. Real production data volume, long translated text,
production HTTPS, assistive-technology testing and visual acceptance on physical
devices remain future validation. Dashboard aggregates may scan rows; sections
still use independent snapshots; production capacity is unverified. No paused
Payroll/HR Lifecycle feature is activated.
