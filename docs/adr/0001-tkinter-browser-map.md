# ADR-0001: Tkinter and a browser map

- Status: accepted
- Date: 2026-11-09

## Context

The app needs a small desktop form (one ZIP, scenario presets, staleness,
open map) and a Folium choropleth. The primary machine is an unsigned
student Mac. An embedded browser widget is painful to notarize and makes
the bundle large.

## Decision

The v1 shell is Tkinter from the standard library. Folium writes an HTML
file. The shell opens that file with `webbrowser.open`. PySide6 and
Qt WebEngine are out of scope.

## Consequences

- `dce.app` must not import `tkinter` at import time until the GUI milestone,
  so headless CI does not need a display.
- On Debian and Ubuntu, `python3-tk` is a system package. It is not in
  `pyproject.toml`.
- Map failures stay in the HTML file. They do not take down a web engine
  inside the process.
- Revisit only if Jacob asks for a native widget set.
