script := shell("basename " + invocation_directory())
tmpfile := `mktemp -u /tmp/script-XXXXXXX.py`

check: lint ty

ty:
    # HACK: Work around the fact that ty requires a .py file extension by copying the script to a temporary file
    cp {{script}} {{tmpfile}}
    # HACK: Need to run the script for UV to create the venv
    -{{tmpfile}}
    # HACK: Tell ty where the script's python is
    uvx ty check {{tmpfile}} --python "$(uv python find --script {{tmpfile}})/../.."

pyright:
    uvx pyright {{script}}

format:
    uvx ruff format {{script}}

lint:
    uvx ruff check {{script}}
