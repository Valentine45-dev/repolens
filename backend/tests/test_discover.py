from pathlib import Path

from app.ingest.discover import discover
from app.ingest.redact import REDACTED


def write(root: Path, rel: str, data: str | bytes) -> None:
    path = root / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(data, bytes):
        path.write_bytes(data)
    else:
        path.write_text(data, encoding="utf-8")


def paths(result) -> list[str]:
    return [f.path for f in result.files]


def test_keeps_python_and_text_with_posix_paths(tmp_path):
    write(tmp_path, "pkg/mod.py", "x = 1\n")
    write(tmp_path, "README.md", "# hi\n")
    write(tmp_path, "setup.cfg", "[metadata]\n")
    result = discover(tmp_path, max_files=100, max_file_bytes=1000)
    assert paths(result) == ["README.md", "setup.cfg", "pkg/mod.py"]
    by_path = {f.path: f for f in result.files}
    assert by_path["pkg/mod.py"].language == "python"
    assert by_path["README.md"].language is None


def test_skips_secret_files_vendor_dirs_binaries_and_big_files(tmp_path):
    write(tmp_path, "app.py", "ok = True\n")
    write(tmp_path, ".env", "X=1\n")
    write(tmp_path, ".env.production", "X=1\n")
    write(tmp_path, "certs/server.pem", "x\n")
    write(tmp_path, "id_rsa", "x\n")
    write(tmp_path, "node_modules/a/index.py", "x\n")
    write(tmp_path, ".venv/lib/x.py", "x\n")
    write(tmp_path, "myenv/pyvenv.cfg", "home = /usr\n")
    write(tmp_path, "myenv/lib/y.py", "x\n")
    write(tmp_path, "pkg/__pycache__/m.py", "x\n")
    write(tmp_path, "build/out.py", "x\n")
    write(tmp_path, "blob.py", b"abc\0def")
    write(tmp_path, "huge.py", "x" * 2000)
    write(tmp_path, "image.png", "not really\n")
    result = discover(tmp_path, max_files=100, max_file_bytes=1000)
    assert paths(result) == ["app.py"]


def test_stops_at_file_limit(tmp_path):
    for i in range(5):
        write(tmp_path, f"m{i}.py", "x = 1\n")
    result = discover(tmp_path, max_files=3, max_file_bytes=1000)
    assert len(result.files) == 3
    assert result.hit_file_limit


def test_content_is_redacted_and_secrets_reported(tmp_path):
    secret = "AKIA" + "Q" * 16
    write(tmp_path, "settings.py", f"DEBUG = True\nAWS_KEY = '{secret}'\n")
    (f,) = discover(tmp_path, max_files=10, max_file_bytes=1000).files
    assert secret not in f.content
    assert f.content == f"DEBUG = True\nAWS_KEY = '{REDACTED}'\n"
    assert [(s.line, s.kind) for s in f.secrets] == [(2, "aws-access-key")]
    assert f.loc == 2


def test_crlf_normalised(tmp_path):
    write(tmp_path, "w.py", b"a = 1\r\nb = 2")
    (f,) = discover(tmp_path, max_files=10, max_file_bytes=1000).files
    assert f.content == "a = 1\nb = 2"
    assert f.loc == 2
