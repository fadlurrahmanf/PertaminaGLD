"""ATEX candidate build preflight; no publishing or automatic cleanup.

Set PLATFORMIO_BUILD_DIR to the project's .pio/build-atex-private-candidates.
Never share this directory: its header and compiled outputs contain the shared
credential. If it contains prior compiled outputs, stop; an operator must first
remove the specific candidate build directory after checking its exact path.
Path checks assume a trusted, non-concurrently-mutated filesystem and private
ACLs; they do not prevent TOCTOU or establish access control.
"""
import importlib.util
from pathlib import Path

_ARTIFACT_EXTENSIONS = frozenset((".o", ".obj", ".a", ".lib", ".elf", ".bin", ".hex"))


def configure(env):
    project = Path(env.subst("$PROJECT_DIR")).absolute()
    build = Path(env.subst("$BUILD_DIR")).absolute()
    name = env.subst("$PIOENV")
    # PlatformIO executes extra scripts via SCons without defining __file__.
    helper_path = project / "tools" / "prepare_atex_workflow_wifi.py"
    spec = importlib.util.spec_from_file_location("_atex_workflow_build_helper", helper_path)
    if spec is None or spec.loader is None:
        raise RuntimeError("ATEX build preflight failed")
    helper = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(helper)
    try:
        if name not in helper.CANDIDATES:
            raise ValueError()
        expected = project / ".pio" / "build-atex-private-candidates" / name
        helper._reject_redirects(build)
        if build.resolve() != expected or expected.resolve() != expected:
            raise ValueError()
        if build.exists():
            for item in build.rglob("*"):
                helper._reject_redirects(item)
                if item.is_file() and item.suffix.lower() in _ARTIFACT_EXTENSIONS:
                    raise ValueError()
        header = helper.prepare(project, build, name)
        env.Prepend(CPPPATH=[str(header.parent)])
    except Exception:
        raise RuntimeError("ATEX build preflight failed") from None


try:
    Import("env")
except NameError:
    env = None

if env is not None:
    configure(env)
