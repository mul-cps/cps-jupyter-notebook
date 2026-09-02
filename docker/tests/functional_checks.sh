#!/bin/sh
# docker/tests/functional_checks.sh
#
# Runs INSIDE a container of the image under test. Takes one argument:
# the variant name (standard-cpu | pytorch-code | tf-code | desktop-ros2 |
# comfyui), which selects which checks apply. Prints PASS/FAIL lines,
# exits non-zero if any check fails.
set -u
VARIANT="${1:?usage: functional_checks.sh <variant-name>}"
FAILURES=0

pass() { echo "PASS: $1"; }
fail() { echo "FAIL: $1: $2"; FAILURES=$((FAILURES + 1)); }

check_cmd() {
  # check_cmd <label> <command...>
  label="$1"; shift
  if "$@" >/tmp/check_out.$$ 2>&1; then
    pass "$label"
  else
    fail "$label" "command failed: $* -- output: $(cat /tmp/check_out.$$)"
  fi
  rm -f /tmp/check_out.$$
}

check_contains() {
  # check_contains <label> <command...> -- <substring>
  label="$1"; shift
  cmd=""
  substr=""
  seen_dashdash=0
  for arg in "$@"; do
    if [ "$arg" = "--" ]; then seen_dashdash=1; continue; fi
    if [ "$seen_dashdash" = "0" ]; then cmd="$cmd $arg"; else substr="$arg"; fi
  done
  out=$(eval "$cmd" 2>&1)
  case "$out" in
    *"$substr"*) pass "$label" ;;
    *) fail "$label" "expected output to contain '$substr', got: $out" ;;
  esac
}

# ---- Checks that apply to EVERY variant ----
check_cmd "jupyter-lab is importable" python3 -c "import jupyterlab"
check_cmd "jupyterlab_git installed" python3 -c "import jupyterlab_git"
check_cmd "code-server binary present" sh -c "command -v code-server"
check_contains "code-server has ms-python.python extension" code-server --list-extensions -- "ms-python.python"
check_contains "code-server has ms-toolsai.jupyter extension" code-server --list-extensions -- "ms-toolsai.jupyter"
check_contains "code-server has mhutchie.git-graph extension" code-server --list-extensions -- "mhutchie.git-graph"
check_cmd "jovyan user exists" id jovyan
check_cmd "jovyan is in sudo group" sh -c "id jovyan | grep -q sudo"
check_cmd "before-notebook.d hooks present" sh -c "[ -x /usr/local/bin/before-notebook.d/00-prepare-readonly-home.sh ] && [ -x /usr/local/bin/before-notebook.d/fix-permissions.sh ]"
check_cmd "ipython_kernel_config.py present" sh -c "[ -f /root/.ipython/profile_default/ipython_kernel_config.py ] || [ -f /home/jovyan/.ipython/profile_default/ipython_kernel_config.py ]"

# ---- Variant-specific checks ----
case "$VARIANT" in
  pytorch-code|desktop-ros2)
    check_cmd "torch is importable" python3 -c "import torch; assert torch.__version__.startswith('2.11'), torch.__version__"
    check_cmd "torchvision is importable" python3 -c "import torchvision"
    check_cmd "transformers is importable" python3 -c "import transformers"
    ;;
esac

case "$VARIANT" in
  tf-code)
    check_cmd "tensorflow is importable" python3 -c "import tensorflow as tf; assert tf.__version__.startswith('2.21'), tf.__version__"
    ;;
esac

case "$VARIANT" in
  desktop-ros2)
    check_cmd "ros2 CLI present" sh -c "command -v ros2 || . /opt/ros/jazzy/setup.sh && command -v ros2"
    check_cmd "Xvnc shim present" sh -c "[ -x /usr/local/bin/Xvnc ]"
    check_cmd "vglrun present" sh -c "command -v vglrun"
    ;;
esac

case "$VARIANT" in
  comfyui)
    check_cmd "ComfyUI checked out" sh -c "[ -f /opt/comfyui/main.py ]"
    check_cmd "torch is importable (comfyui)" python3 -c "import torch"
    check_cmd "jupyter-comfyui-proxy installed" sh -c "pip show jupyter-comfyui-proxy"
    ;;
esac

case "$VARIANT" in
  mujoco-xpra)
    check_cmd "torch is importable" python3 -c "import torch, torchvision"
    check_cmd "MuJoCo is importable" python3 -c "import mujoco, gymnasium"
    check_cmd "MuJoCo version helper" mujoco -v
    check_cmd "Xpra binary present" sh -c "command -v xpra"
    check_cmd "VirtualGL binary present" sh -c "command -v vglrun"
    check_cmd "EGL environment is configured" sh -c '[ "$MUJOCO_GL" = egl ] && [ "$PYOPENGL_PLATFORM" = egl ]'
    check_cmd "jovyan has no sudo" sh -c '! id jovyan | grep -qw sudo'
    ;;
esac

echo "----"
if [ "$FAILURES" -gt 0 ]; then
  echo "RESULT: $FAILURES check(s) FAILED for variant=$VARIANT"
  exit 1
fi
echo "RESULT: all checks PASSED for variant=$VARIANT"
exit 0
