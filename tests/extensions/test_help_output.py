from __future__ import annotations

import io
from contextlib import redirect_stdout

from agentcontrol.cli.main import build_parser


def _extension_parser():
    parser = build_parser()
    subparsers = parser._subparsers._group_actions[0]
    return subparsers.choices["extension"]


def test_extension_help_snapshot():
    parser = _extension_parser()
    buffer = io.StringIO()
    with redirect_stdout(buffer):
        parser.print_help()
    output = buffer.getvalue().strip()
    expected = """usage: agentcall extension [-h] [--path PATH]
                           {init,add,list,remove,lint,publish} ...

Lifecycle commands for project extensions.

Quickstart recipes:
  1. agentcall extension init docs_sync
  2. agentcall extension add docs_sync --source extensions/docs_sync
  3. agentcall extension publish --json

Outputs:
  - --json emits structured catalog entries for add/list/remove/publish.

positional arguments:
  {init,add,list,remove,lint,publish}
    init                Scaffold a new extension
    add                 Register an existing extension in the catalog
    list                List registered extensions
    remove              Remove an extension from the catalog
    lint                Validate extension manifests
    publish             Export extension catalog

options:
  -h, --help            show this help message and exit
  --path PATH           Project path (default: current directory)

Avoid:
  - Running inside the SDK repository (use scripts/test-place.sh instead).
  - Mixing --source and --git flags in a single add command.
  - Registering scaffolds before manifest.json passes lint.

Docs:
  - docs/tutorials/extensions.md"""
    assert output == expected
    for line in output.splitlines():
        assert len(line) <= 80
