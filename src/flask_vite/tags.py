# Copyright (c) 2022-2024, Abilian SAS
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import glob
from pathlib import Path
from textwrap import dedent

from flask import current_app, url_for
from markupsafe import Markup


def make_tag(*, static: bool = False):
    if static or not current_app.debug:
        tag = make_static_tag()
    else:
        tag = make_debug_tag()
    return Markup(tag)


def make_static_tag():
    vite_folder_path = current_app.extensions["vite"].vite_folder_path
    js_file = Path(glob.glob(f"{vite_folder_path}/dist/assets/*.js")[0]).name
    css_file = Path(glob.glob(f"{vite_folder_path}/dist/assets/*.css")[0]).name

    js_file_url = url_for(f"{vite_folder_path}.static", filename=js_file)
    css_file_url = url_for(f"{vite_folder_path}.static", filename=css_file)

    return dedent(
        f"""
            <!-- FLASK_VITE_HEADER -->
            <script type="module" src="{js_file_url}"></script>
            <link rel="stylesheet" href="{css_file_url}"></link>
        """
    ).strip()


def make_debug_tag():
    vite_entry_points = current_app.extensions["vite"].vite_entry_points
    vite_dev_host = "http://localhost:5173"
    
    script_tags = '\n'.join(f"<script type='module' src='{vite_dev_host}/{src}'></script>" for src in vite_entry_points)
    
    return dedent(
        f"""
            <!-- FLASK_VITE_HEADER -->
            <script type="module">
                import RefreshRuntime from "{vite_dev_host}/@react-refresh"
                RefreshRuntime.injectIntoGlobalHook(window)
                window.$RefreshReg$ = () => {{}}
                window.$RefreshSig$ = () => (type) => type
                window.__vite_plugin_react_preamble_installed__ = true
            </script>
            <script type="module" src="{vite_dev_host}/@vite/client"></script>
            {script_tags}
        """
    ).strip()
