# Copyright (c) 2022-2024, Abilian SAS
#
# SPDX-License-Identifier: MIT

from __future__ import annotations

import glob
from pathlib import Path
from textwrap import dedent
import re

from flask import current_app, url_for
from markupsafe import Markup


def make_tag(*, static: bool = False):
    if static or current_app.config['VITE_STATIC_TAG']:
        tag = make_static_tag()
    else:
        tag = make_debug_tag()
    return Markup(tag)

# Find fingerprinted files that match declared entry points
def make_static_tag():
    vite_entry_points = current_app.extensions["vite"].vite_entry_points
    vite_folder_path = current_app.extensions["vite"].vite_folder_path
    
    js_files = glob.glob(f"{vite_folder_path}/dist/assets/*.js")
    entry_points = [re.sub(r'\..+$', '', src) for src in vite_entry_points]
    
    entry_files = [
        Path(js_file).name 
        for js_file in js_files 
        for entry in entry_points 
        if Path(js_file).name.startswith(entry)
    ]
    
    # Enables flask-cdn support
    url_for = current_app.jinja_env.globals["url_for"]
    script_tags = '\n'.join(f"<script type='module' src='{url_for('vite.static', filename=src)}'></script>" for src in entry_files)

    return dedent(
        f"""
            <!-- FLASK_VITE_HEADER -->
            {script_tags}
        """
    ).strip()


def make_debug_tag():
    vite_entry_points = current_app.extensions["vite"].vite_entry_points
    vite_dev_host = "http://localhost:5173"
    
    script_tags = '\n'.join(f"<script type='module' src='{vite_dev_host}/src/{src}'></script>" for src in vite_entry_points)
    
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
