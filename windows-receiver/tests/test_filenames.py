import pytest

from mconn_receiver.storage.filenames import resolve_conflict, sanitize_filename


@pytest.mark.parametrize("raw,expected", [
    ("report.zip", "report.zip"),
    ("../../etc/passwd", "passwd"),
    ("..\\..\\Windows\\system32\\evil.dll", "evil.dll"),
    ("C:\\temp\\a.txt", "a.txt"),
    ("a<b>c:d\"e|f?g*.txt", "a_b_c_d_e_f_g_.txt"),
    ("CON", "_CON"),
    ("nul.txt", "_nul.txt"),
    ("COM1.tar.gz", "_COM1.tar.gz"),
    ("trailing. . ", "trailing"),
    ("..", "file"),
    ("", "file"),
    ("   ", "file"),
    (".bashrc", ".bashrc"),
    ("résumé.pdf", "résumé.pdf"),
])
def test_sanitize(raw, expected):
    assert sanitize_filename(raw) == expected


def test_length_limit_keeps_extension():
    out = sanitize_filename("a" * 500 + ".zip")
    assert len(out) <= 200 and out.endswith(".zip")


def test_no_path_separators_ever():
    for evil in ["a/b", "a\\b", "/abs", "\x00x", "x/../../y"]:
        out = sanitize_filename(evil)
        assert "/" not in out and "\\" not in out and "\x00" not in out


def test_conflict_never_overwrites(tmp_path):
    (tmp_path / "a.zip").write_text("1")
    assert resolve_conflict(tmp_path, "a.zip").name == "a (1).zip"
    (tmp_path / "a (1).zip").write_text("2")
    assert resolve_conflict(tmp_path, "a.zip").name == "a (2).zip"
    assert resolve_conflict(tmp_path, "new.txt").name == "new.txt"
