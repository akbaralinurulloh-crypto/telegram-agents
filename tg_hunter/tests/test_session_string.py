import ipaddress
import os
import struct

import pytest
from telethon.crypto import AuthKey
from telethon.sessions import SQLiteSession, StringSession
from telethon.sessions.string import _STRUCT_PREFORMAT, CURRENT_VERSION

from app.config import AppConfig, Settings
from app.watcher.listener import build_client
from app.watcher.session import ensure_session_file, export_session_string, session_file
from scripts.check import offline_checks


def make_string(dc: int = 2, ip: str = "149.154.167.51", port: int = 443) -> tuple[str, bytes]:
    key = os.urandom(256)
    s = StringSession()
    s.set_dc(dc, ip, port)
    s.auth_key = AuthKey(data=key)
    return s.save(), key


def read_file_session(path) -> SQLiteSession:
    return SQLiteSession(str(session_file(str(path))))


def test_string_roundtrip_creates_working_session_file(tmp_path):
    text, key = make_string()
    path = tmp_path / "data" / "hunter.session"
    assert ensure_session_file(str(path), text) is True
    assert path.exists()
    sess = read_file_session(path)
    try:
        assert (sess.dc_id, sess.server_address, sess.port) == (2, "149.154.167.51", 443)
        assert sess.auth_key.key == key
    finally:
        sess.close()
    assert export_session_string(str(path)) == text  # fayl -> matn -> bir xil


@pytest.mark.parametrize("wrap", ["TG_SESSION_STRING={}", "tg_session_string={}", '"{}"', "'{}'", "  {}  \n"])
def test_pasted_variants_are_cleaned(tmp_path, wrap):
    # foydalanuvchi qiymat maydoniga butun qatorni, tirnoq bilan yoki bo'shliq bilan qo'yib yuborishi mumkin
    text, key = make_string()
    path = tmp_path / "hunter.session"
    assert ensure_session_file(str(path), wrap.format(text)) is True
    sess = read_file_session(path)
    try:
        assert sess.auth_key.key == key
    finally:
        sess.close()


def test_path_without_suffix_gets_session_extension(tmp_path):
    text, _ = make_string()
    assert ensure_session_file(str(tmp_path / "hunter"), text) is True
    assert (tmp_path / "hunter.session").exists()


def test_existing_file_is_not_overwritten(tmp_path):
    first, key1 = make_string()
    second, _ = make_string(dc=4, ip="149.154.167.91")
    path = tmp_path / "hunter.session"
    assert ensure_session_file(str(path), first) is True
    assert ensure_session_file(str(path), second) is False  # fayl ustun
    sess = read_file_session(path)
    try:
        assert sess.dc_id == 2 and sess.auth_key.key == key1
    finally:
        sess.close()


@pytest.mark.parametrize("empty", [None, "", "   \n"])
def test_empty_string_does_nothing(tmp_path, empty):
    assert ensure_session_file(str(tmp_path / "x.session"), empty) is False
    assert not (tmp_path / "x.session").exists()


def test_garbage_string_gives_clear_error_and_no_file(tmp_path):
    with pytest.raises(ValueError, match="TG_SESSION_STRING yaroqsiz"):
        ensure_session_file(str(tmp_path / "x.session"), "1ABCnoto'g'ri")
    assert not (tmp_path / "x.session").exists()


def test_string_with_zero_key_is_rejected(tmp_path):
    # login tugallanmagan sessiya: DC bor, lekin kalit nollardan iborat
    ip = ipaddress.ip_address("149.154.167.51").packed
    keyless = CURRENT_VERSION + StringSession.encode(struct.pack(_STRUCT_PREFORMAT.format(len(ip)), 2, ip, 443, b"\x00" * 256))
    with pytest.raises(ValueError, match="kirish kaliti yo'q"):
        ensure_session_file(str(tmp_path / "x.session"), keyless)
    assert not (tmp_path / "x.session").exists()


def test_export_missing_file_is_clear_error(tmp_path):
    with pytest.raises(FileNotFoundError, match="scripts.login"):
        export_session_string(str(tmp_path / "nope.session"))


def test_export_of_unauthorized_file_is_rejected(tmp_path):
    p = tmp_path / "blank.session"
    SQLiteSession(str(p)).close()  # kalitsiz bo'sh sessiya
    with pytest.raises(ValueError, match="kirish kaliti yo'q"):
        export_session_string(str(p))


def test_build_client_seeds_session_from_string(tmp_path):
    text, key = make_string()
    s = Settings(
        _env_file=None,
        TG_API_ID=12345,
        TG_API_HASH="0123456789abcdef0123456789abcdef",
        TG_SESSION_PATH=str(tmp_path / "data" / "hunter.session"),
        TG_SESSION_STRING=text,
    )
    client = build_client(s, AppConfig())
    try:
        assert (tmp_path / "data" / "hunter.session").exists()
        assert client.session.auth_key.key == key
    finally:
        client.session.close()


def test_railway_block_is_clean_and_forces_dry_run():
    from scripts.export_session import railway_block

    s = Settings(
        _env_file=None,
        TG_API_ID=123,
        TG_API_HASH="h" * 32,
        BOT_TOKEN="1:abc",
        ADMIN_ID=5,
        TARGET_CHANNEL="@c",
        SOURCE_CHANNELS="@a,@b",
        GEMINI_API_KEY="k",
        DRY_RUN=False,
    )
    lines = railway_block(s, "TG_SESSION_STRING=XYZ").splitlines()
    assert {"TG_API_ID=123", "TARGET_CHANNEL=@c", "SOURCE_CHANNELS=@a,@b", "ADMIN_ID=5", "BOT_TOKEN=1:abc"} <= set(lines)
    assert "DRY_RUN=true" in lines  # birinchi Railway ishga tushirishi har doim DRY-RUN
    assert lines[-1] == "TG_SESSION_STRING=XYZ"
    assert not any(line.startswith("ANTHROPIC_API_KEY") for line in lines)  # bo'sh qiymatlar tushirib qoldiriladi
    assert all("#" not in line and " " not in line for line in lines)  # inline izoh yoki ortiqcha bo'shliq yo'q


@pytest.mark.parametrize("flag", ["--vars", "--railway"])
def test_export_script_variables_flag_writes_clean_block(tmp_path, monkeypatch, flag):
    from app.config import get_settings
    from scripts import export_session

    text, _ = make_string()
    sess = tmp_path / "hunter.session"
    assert ensure_session_file(str(sess), text) is True
    out = tmp_path / "variables.txt"
    env = {
        "TG_API_ID": "111",
        "TG_API_HASH": "0123456789abcdef0123456789abcdef",
        "BOT_TOKEN": "1:fake",
        "ADMIN_ID": "5",
        "TARGET_CHANNEL": "@kanal",
        "SOURCE_CHANNELS": "@a,@b",
        "GEMINI_API_KEY": "fakekey",
        "DRY_RUN": "false",
        "TG_SESSION_PATH": str(sess),
    }
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    get_settings.cache_clear()
    monkeypatch.setattr("sys.argv", ["export_session", flag, "--out", str(out)])
    try:
        export_session.main()
    finally:
        get_settings.cache_clear()
    data = out.read_text(encoding="utf-8")
    lines = data.splitlines()
    assert "DRY_RUN=true" in lines and "TG_API_ID=111" in lines and "SOURCE_CHANNELS=@a,@b" in lines
    assert lines[-1] == f"TG_SESSION_STRING={text}"
    assert not data.endswith("\n")  # oxirida ortiqcha qator uzilishi yo'q


def test_offline_check_accepts_session_string_without_file(tmp_path):
    text, _ = make_string()
    s = Settings(_env_file=None, TG_SESSION_PATH=str(tmp_path / "none.session"), TG_SESSION_STRING=text)
    res = {m: ok for ok, m in offline_checks(s, AppConfig())}
    assert any(ok for m, ok in res.items() if "TG_SESSION_STRING" in m)
    s2 = Settings(_env_file=None, TG_SESSION_PATH=str(tmp_path / "none.session"))
    res2 = {m: ok for ok, m in offline_checks(s2, AppConfig())}
    assert any((not ok) and "Telethon session" in m for m, ok in res2.items())
