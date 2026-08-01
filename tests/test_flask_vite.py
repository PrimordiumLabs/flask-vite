# Copyright (c) 2022-2024, Abilian SAS
#
# SPDX-License-Identifier: MIT

"""Tests for `flask_vite` package."""

from pathlib import Path

import pytest
from click.testing import CliRunner
from flask import Flask
from werkzeug import Response

from flask_vite import Vite, cli
from flask_vite.extension import ViteError  # re-exported; canonical home is .errors
from flask_vite.npm import NPMError


def test_extension():
    app = Flask(__name__)
    vite = Vite(app)
    assert "vite" in app.extensions
    assert app.extensions["vite"] == vite


def test_cli():
    runner = CliRunner()

    result = runner.invoke(cli.vite)
    assert result.exit_code == 0
    assert "Perform Vite operations" in result.output

    help_result = runner.invoke(cli.vite, ["--help"])
    assert help_result.exit_code == 0
    assert "--help  Show this message and exit." in help_result.output
    assert "init" in help_result.output


def test_npm():
    app = Flask(__name__)
    vite = Vite(app)
    npm = vite.npm
    assert npm.npm_bin_path == "npm"

    Path("vite").mkdir(exist_ok=True)

    with app.app_context():
        npm.run("help")


def test_npm_alt_path():
    app = Flask(__name__)
    app.config["VITE_NPM_BIN_PATH"] = "xxx"
    vite = Vite(app)
    npm = vite.npm
    assert npm.npm_bin_path == "xxx"

    Path("vite").mkdir(exist_ok=True)

    with app.app_context():
        with pytest.raises(NPMError):
            npm.run()


def test_vite_auto_inject(mocker):
    app = Flask(__name__)
    app.config["VITE_AUTO_INSERT"] = True
    app.config["VITE_STATIC_TAG"] = True
    Vite(app, vite_entry_points=["main.js"])

    @app.route("/")
    def index():
        return "<html><head></head><body>OK</body></html>"

    mocker.patch("glob.glob", return_value=["path/to/main-abc123.js"])
    with (
        app.test_client() as client,
        app.app_context(),
    ):
        response = client.get("/")

        assert "<script type='module' src='/_vite/main-abc123.js'>" in response.text


ENTRY_POINTS = ["reactIslands.tsx", "csvParse.ts", "csv.ts"]
BUILT_ASSETS = [
    "vite/dist/assets/reactIslands-AAA111.js",
    "vite/dist/assets/csvParse-BBB222.js",
    "vite/dist/assets/csv-CCC333.js",
    "vite/dist/assets/vendor-react-DDD444.js",
]


def make_app(**config):
    app = Flask(__name__)
    app.config.update(config)
    Vite(app, vite_entry_points=ENTRY_POINTS)
    return app


def test_entry_points_are_keyed_by_name():
    app = make_app()
    assert app.extensions["vite"].vite_entry_points == {
        "reactIslands": "reactIslands.tsx",
        "csvParse": "csvParse.ts",
        "csv": "csv.ts",
    }


def test_static_tag_defaults_to_every_entry_point(mocker):
    app = make_app(VITE_STATIC_TAG=True)
    mocker.patch("glob.glob", return_value=BUILT_ASSETS)

    with app.test_request_context():
        tag = app.jinja_env.globals["vite_tags"]()

    assert "/_vite/reactIslands-AAA111.js" in tag
    assert "/_vite/csvParse-BBB222.js" in tag
    assert "/_vite/csv-CCC333.js" in tag


def test_static_tag_emits_only_the_named_entry_point(mocker):
    app = make_app(VITE_STATIC_TAG=True)
    mocker.patch("glob.glob", return_value=BUILT_ASSETS)

    with app.test_request_context():
        tag = app.jinja_env.globals["vite_tags"]("reactIslands")

    assert "/_vite/reactIslands-AAA111.js" in tag
    assert "csvParse" not in tag
    assert tag.count("<script") == 1


def test_static_tag_does_not_prefix_match_other_entry_points(mocker):
    """`csv` must not pull in `csvParse`, which the old startswith() check did."""
    app = make_app(VITE_STATIC_TAG=True)
    mocker.patch("glob.glob", return_value=BUILT_ASSETS)

    with app.test_request_context():
        tag = app.jinja_env.globals["vite_tags"]("csv")

    assert "/_vite/csv-CCC333.js" in tag
    assert "csvParse" not in tag


def test_static_tag_excludes_shared_chunks(mocker):
    """Vendor chunks are imported by the entry module, not tagged separately."""
    app = make_app(VITE_STATIC_TAG=True)
    mocker.patch("glob.glob", return_value=BUILT_ASSETS)

    with app.test_request_context():
        tag = app.jinja_env.globals["vite_tags"]()

    assert "vendor-react" not in tag


def test_static_tag_preserves_requested_order_and_dedupes(mocker):
    app = make_app(VITE_STATIC_TAG=True)
    mocker.patch("glob.glob", return_value=BUILT_ASSETS)

    with app.test_request_context():
        tag = app.jinja_env.globals["vite_tags"]("csvParse", "reactIslands", "csvParse")

    assert tag.count("<script") == len(["csvParse", "reactIslands"])
    assert tag.index("csvParse-BBB222") < tag.index("reactIslands-AAA111")


def test_static_tag_raises_when_an_entry_point_was_never_built(mocker):
    app = make_app(VITE_STATIC_TAG=True)
    mocker.patch("glob.glob", return_value=[])

    with app.test_request_context(), pytest.raises(ViteError) as e:
        app.jinja_env.globals["vite_tags"]("reactIslands")

    assert "No built asset found for vite entry point 'reactIslands'" in str(e.value)


def test_unknown_entry_point_raises():
    app = make_app(VITE_STATIC_TAG=True)

    with app.test_request_context(), pytest.raises(ViteError) as e:
        app.jinja_env.globals["vite_tags"]("nope")

    assert "Unknown vite entry point(s): nope" in str(e.value)


def test_debug_tag_points_at_the_dev_server_sources():
    app = make_app(VITE_STATIC_TAG=False)

    with app.test_request_context():
        tag = app.jinja_env.globals["vite_tags"]("reactIslands")

    assert "http://localhost:5173/src/reactIslands.tsx" in tag
    assert "@vite/client" in tag
    assert "csvParse" not in tag


def test_debug_tag_emits_the_refresh_preamble_once_per_request():
    app = make_app(VITE_STATIC_TAG=False)

    with app.test_request_context():
        vite_tags = app.jinja_env.globals["vite_tags"]
        first = vite_tags("reactIslands")
        second = vite_tags("csvParse")

    assert first.count("@react-refresh") == 1
    assert second.count("@react-refresh") == 0
    # The entry point script itself is still emitted on the second call.
    assert "/src/csvParse.ts" in second


def test_vite_and_flask_host_mismatch():
    app = Flask(__name__, host_matching=False)
    app.config["VITE_AUTO_INSERT"] = True

    with pytest.raises(ViteError) as e:
        Vite(app, vite_routes_host="vite.domain.com")

    assert (
        str(e.value)
        == "`vite_routes_host` should only be set if your Flask app is using `host_matching`."
    )


def test_vite_conflicting_vite_routes_host_configuration():
    app = Flask(__name__, host_matching=True, static_host="static.domain.com")
    app.config["VITE_AUTO_INSERT"] = True
    vite = Vite(vite_routes_host="vite.domain.com")

    with pytest.raises(ViteError) as e:
        vite.init_app(app, vite_routes_host="*")

    assert str(e.value) == (
        "`vite_routes_host` has been configured differently in two places; use either "
        "`Vite(vite_routes_host=...)` or `Vite().init_app(vite_routes_host=...)`, not both."
    )


def test_vite_host_variables_rejected():
    app = Flask(__name__, host_matching=True, static_host="static.domain.com")
    app.config["VITE_AUTO_INSERT"] = True

    with pytest.raises(ViteError) as e:
        Vite(app, vite_routes_host="<my_host>.com")

    assert str(e.value) == (
        "`vite_routes_host` must either be a host name with no variables, to serve all "
        "vite assets from a single host, or the wildcard value `*` to serve from the same host as the "
        "current request."
    )


def test_vite_auto_inject_explicit_host(mocker):
    app = Flask(__name__, host_matching=True, static_host="static.domain.com")
    app.config["VITE_AUTO_INSERT"] = True
    app.config["VITE_STATIC_TAG"] = True
    Vite(app, vite_routes_host="vite.domain.com", vite_entry_points=["main.js"])

    @app.route("/", host="myapp.com")
    def index():
        return "<html><head></head><body>OK</body></html>"

    mocker.patch("glob.glob", return_value=["path/to/main-abc123.js"])
    with (
        app.test_client() as client,
        app.app_context(),
    ):
        response = client.get("/", headers={"Host": "myapp.com"})

        assert (
            "<script type='module' "
            "src='http://vite.domain.com/_vite/main-abc123.js'>" in response.text
        )


def test_vite_auto_inject_match_request_host(mocker):
    app = Flask(__name__, host_matching=True, static_host="static.domain.com")
    app.config["VITE_AUTO_INSERT"] = True
    app.config["VITE_STATIC_TAG"] = True
    Vite(app, vite_routes_host="*", vite_entry_points=["main.js"])

    @app.route("/", host="myapp.com")
    def index():
        return "<html><head></head><body>OK</body></html>"

    mocker.patch("glob.glob", return_value=["path/to/main-abc123.js"])
    with (
        app.test_client() as client,
        app.app_context(),
    ):
        response = client.get("/", headers={"Host": "myapp.com"})
        assert "<script type='module' src='/_vite/main-abc123.js'>" in response.text


@pytest.mark.parametrize(
    ("vite_routes_host", "request_host", "expected_status_code"),
    [
        ("vite.domain.com", "vite.domain.com", 200),
        ("vite.domain.com", "myapp.com", 404),
        ("vite.domain.com", "static.domain.com", 404),
        ("*", "vite.domain.com", 200),
        ("*", "myapp.com", 200),
        ("*", "static.domain.com", 200),
    ],
)
def test_vite_serves_assets_from_explicit_host(
    mocker, request_host, expected_status_code, vite_routes_host
):
    app = Flask(__name__, host_matching=True, static_host="static.domain.com")
    app.config["VITE_AUTO_INSERT"] = True
    Vite(app, vite_routes_host=vite_routes_host)

    mocker.patch(
        "flask.helpers.werkzeug.utils.send_from_directory",
        return_value=Response(b"fake-file", mimetype="text/css", status=200),
    )
    with (
        app.test_client() as client,
        app.app_context(),
    ):
        response = client.get("/_vite/some-file", headers={"Host": request_host})
        assert response.status_code == expected_status_code
