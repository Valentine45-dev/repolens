"""Entry-point patterns, read from text (nothing is executed)."""

from app.reach import entries as ent


def test_main_block_both_spellings_and_not_a_comment():
    assert ent.has_main_block('x = 1\nif __name__ == "__main__":\n    main()\n')
    assert ent.has_main_block("if '__main__' == __name__:\n    main()\n")
    assert not ent.has_main_block('# if __name__ == "__main__":\n')
    assert not ent.has_main_block('    if __name__ == "__main__":\n        pass\n')  # nested


def test_decorators_that_register_handlers():
    text = (
        "@app.route('/')\ndef index(): ...\n\n"
        "@click.command()\n@click.option('--x')\ndef run(): ...\n\n"
        "@shared_task\ndef job(): ...\n\n"
        "@functools.lru_cache\ndef cached(): ...\n\n"
        "@property\ndef p(self): ...\n\n"
        "@router.get('/x')\nasync def x(): ...\n"
    )
    assert ent.decorated_entry_lines(text) == [
        (1, "app.route"), (4, "click.command"), (8, "shared_task"), (17, "router.get"),
    ]


def test_django_url_handlers():
    text = (
        "urlpatterns = [\n"
        "    path('', views.index, name='index'),\n"
        "    path('a/<int:pk>/', views.Detail.as_view(), name='d'),\n"
        "    re_path(r'^x/(?P<id>[0-9]+)$', views.old),\n"
        "    path('api/', include('api.urls')),\n"
        "    url(r'^plain$', plain_view),\n"
        "]\n"
    )
    assert ent.url_handler_names(text) == ["index", "Detail", "old", "plain_view"]


def test_pyproject_scripts_and_plugin_groups():
    text = (
        '[project]\nname = "x"\n'
        '[project.scripts]\nblack = "black:patched_main"\n'
        '[project.entry-points."flask.commands"]\nrun = "x.cli:cmd [extra]"\n'
        '[tool.poetry.scripts]\npoet = "poetpkg.main:go"\n'
    )
    refs = {(r.kind, r.label, r.module, r.attr) for r in ent.script_refs("pyproject.toml", text)}
    assert refs == {
        ("console-script", "black", "black", "patched_main"),
        ("plugin-entry", "run", "x.cli", "cmd"),
        ("console-script", "poet", "poetpkg.main", "go"),
    }


def test_setup_cfg_and_setup_py_are_read_not_run():
    cfg = "[options.entry_points]\nconsole_scripts =\n    one = pkg.a:main\n    two = pkg.b\n"
    assert {(r.label, r.module, r.attr) for r in ent.script_refs("setup.cfg", cfg)} == {
        ("one", "pkg.a", "main"), ("two", "pkg.b", None)}
    py = (
        "import os\nENTRY = {'console_scripts': ['tool = pkg.cli:run']}\n"
        "os.system('echo this must never run')\n"
        "setup(name='x', entry_points=ENTRY)\n"
    )
    assert [(r.label, r.module, r.attr) for r in ent.script_refs("setup.py", py)] == [
        ("tool", "pkg.cli", "run")]
    # a value built at run time is skipped, not evaluated
    assert ent.script_refs("setup.py", "setup(entry_points=make_entry_points())\n") == []


def test_broken_files_give_nothing():
    assert ent.script_refs("pyproject.toml", "[project\nnot toml") == []
    assert ent.script_refs("setup.py", "def (:") == []
    assert ent.package_json_refs("package.json", "{not json") == []


def test_package_json_main_bin_exports_and_node_scripts():
    text = (
        '{"main": "lib/index.js", "bin": {"tool": "bin/tool.js"},'
        ' "exports": {".": {"import": "./esm/x.mjs", "require": "./cjs/x.cjs"},'
        ' "./package.json": "./package.json"},'
        ' "scripts": {"start": "node --inspect server/app.js", "test": "mocha",'
        ' "dev": "nodemon src/dev.ts"}}'
    )
    paths = {r.path for r in ent.package_json_refs("pkg/package.json", text)}
    assert paths == {"pkg/lib/index.js", "pkg/bin/tool.js", "pkg/esm/x.mjs", "pkg/cjs/x.cjs",
                     "pkg/server/app.js", "pkg/src/dev.ts"}


def test_package_json_without_main_means_index():
    refs = ent.package_json_refs("package.json", '{"name": "x"}')
    assert [(r.path, r.attr) for r in refs] == [(".", "index")]


def test_exports_of_an_init_file():
    text = (
        "from .app import Flask as Flask, helper\nfrom . import json\nfrom .x import *\n"
        "__all__ = ['Flask', 'json']\n\n\ndef public(): ...\n\n\ndef _private(): ...\n\n\n"
        "class Thing: ...\n"
    )
    imports, all_names, defined = ent.python_exports(text)
    assert imports == [(1, "app", "Flask", "Flask"), (1, "app", "helper", "helper"),
                       (1, "", "json", "json")]
    assert all_names == ["Flask", "json"]
    assert defined == ["public", "Thing"]


def test_shebang():
    assert ent.has_shebang("#!/usr/bin/env python3\nprint()")
    assert ent.has_shebang("#!/usr/bin/env node\n")
    assert not ent.has_shebang("#!/bin/sh\n")
    assert not ent.has_shebang("import os\n")


def test_decorators_and_main_blocks_inside_docstrings_are_not_entry_points():
    text = (
        "def template_filter(self):\n"
        '    """Use it like this:\n\n'
        "    @app.template_filter()\n"
        "    def reverse(s):\n"
        "        return s[::-1]\n\n"
        '    if __name__ == "__main__":\n'
        "        run()\n"
        '    """\n'
        "    return None\n"
    )
    assert ent.decorated_entry_lines(text) == []
    assert not ent.has_main_block(text)


def test_a_file_that_does_not_parse_gives_no_entry_points():
    assert ent.decorated_entry_lines("@app.route('/')\ndef (:\n") == []
    assert not ent.has_main_block("print 'py2'\nif __name__ == '__main__': main()\n")
