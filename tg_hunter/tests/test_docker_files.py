from pathlib import Path


def test_cryptg_is_optional_and_wheel_only():
    # cryptg>=0.4 (versiyasiz) eng yangi sdist'ni olib, Rust kerak bo'lib qurishni sindirgan (cryptg 0.6.1, wheel yo'q).
    req = [ln.split("#")[0].strip() for ln in Path("requirements.txt").read_text(encoding="utf-8").splitlines()]
    assert not any(r.lower().startswith("cryptg") for r in req)
    docker = Path("Dockerfile").read_text(encoding="utf-8")
    assert '--only-binary=:all: "cryptg' in docker and "|| echo" in docker  # wheel bo'lmasa qurish to'xtamaydi
    assert docker.index("cryptg") > docker.index("requirements.txt")  # asosiy kutubxonalardan keyin
