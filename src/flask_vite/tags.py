# Copyright (c) 2022-2024, Abilian SAS
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import glob
import re
from pathlib import Path
from textwrap import dedent

from flask import current_app, g
from markupsafe import Markup

from .errors import ViteError

VITE_DEV_HOST = "http://localhost:5173"

# Marks the injected block, and lets templates/tests find it.
HEADER = "<!-- FLASK_VITE_HEADER -->"

# Vite names entry chunks `{name}-{hash}.js`; the hash is absent when the build
# overrides `entryFileNames`, so treat it as optional.
ENTRY_FILE_TEMPLATE = r"{name}(-[\w-]+)?\.js"


def make_tag(*entry_points: str, static: bool = False):
    """Script tags for the named entry points, or for all of them if none are given.

    Args:
        entry_points: The entry points to emit.
        static: Whether to emit static tags.

    Returns:
        Markup: HTML-safe string containing <script> tags for the selected entry points.
    """
    selected = _select_entry_points(entry_points)

    if static or current_app.config["VITE_STATIC_TAG"]:
        tag = make_static_tag(selected)
    else:
        tag = make_debug_tag(selected)
    return Markup(tag)


def _select_entry_points(entry_points: tuple[str, ...]) -> dict[str, str]:
    """
    Map the requested entry point names to their source paths, preserving the order requested.

    Args:
        entry_points: Tuple of entry point names to select.

    Returns:
        dict[str, str]: Mapping from entry point names to their declared source paths.

    Raises:
        ViteError: If any requested entry point name is not declared.
    """
    declared = current_app.extensions["vite"].vite_entry_points

    if not entry_points:
        return declared

    unknown = sorted(set(entry_points) - set(declared))
    if unknown:
        raise ViteError(
            f"Unknown vite entry point(s): {', '.join(unknown)}. "
            f"Declared entry points are: {', '.join(declared) or '(none)'}."
        )

    # dict.fromkeys drops duplicates while preserving the requested order.
    return {name: declared[name] for name in dict.fromkeys(entry_points)}


# Find fingerprinted files that match the selected entry points
def make_static_tag(selected: dict[str, str]) -> str:
    vite_folder_path = current_app.extensions["vite"].vite_folder_path

    # Enables flask-cdn support
    url_for = current_app.jinja_env.globals["url_for"]

    built_files = [
        Path(js_file).name
        for js_file in glob.glob(f"{vite_folder_path}/dist/assets/*.js")
    ]

    script_tags = []
    for name in selected:
        pattern = re.compile(ENTRY_FILE_TEMPLATE.format(name=re.escape(name)))
        matches = sorted(f for f in built_files if pattern.fullmatch(f))
        if not matches:
            raise ViteError(
                f"No built asset found for vite entry point {name!r} in "
                f"{vite_folder_path}/dist/assets. Did you forget to run the Vite build?"
            )
        script_tags += [
            f"<script type='module' src='{url_for('vite.static', filename=src)}'></script>"
            for src in matches
        ]

    return "\n".join([HEADER, *script_tags])


def make_debug_tag(selected: dict[str, str]) -> str:
    # The dev server serves the sources, so it needs the real extension.
    script_tags = [
        f"<script type='module' src='{VITE_DEV_HOST}/src/{src}'></script>"
        for src in selected.values()
    ]

    return "\n".join([HEADER, *_debug_preamble(), *script_tags])


def _debug_preamble() -> list[str]:
    """The react-refresh shim and dev client, emitted at most once per request.

    Selecting entry points per call means one page can legitimately call
    ``vite_tags()`` more than once; injecting the preamble each time would
    re-run the refresh runtime.
    """
    if getattr(g, "vite_preamble_emitted", False):
        return []
    g.vite_preamble_emitted = True

    return [
        dedent(
            f"""
            <script type="module">
                import RefreshRuntime from "{VITE_DEV_HOST}/@react-refresh"
                RefreshRuntime.injectIntoGlobalHook(window)
                window.$RefreshReg$ = () => {{}}
                window.$RefreshSig$ = () => (type) => type
                window.__vite_plugin_react_preamble_installed__ = true
            </script>
            """
        ).strip(),
        f'<script type="module" src="{VITE_DEV_HOST}/@vite/client"></script>',
    ]
