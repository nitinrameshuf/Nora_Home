#!/usr/bin/env bash
#
# Run the test suite and print the short report.
#
# The point of this script is what it does NOT print. Full pytest output is
# hundreds of lines; an agent reading it back over SSH pays for every one of
# them. So the tracebacks go to a file and only the fixed-size report reaches
# the terminal — one line per subsystem, one line per failure. When a failure
# needs more than its assertion, the detail is one file read away:
#
#     ./scripts/run-tests.sh              # everything
#     ./scripts/run-tests.sh tracker      # just tests/test_tracker.py
#     ./scripts/run-tests.sh -k escalate  # anything pytest understands
#
# On the Pi, run it inside the web container so it uses the same Python and the
# same settings the house actually runs on:
#
#     docker compose exec -T web ./scripts/run-tests.sh
#
set -uo pipefail

cd "$(dirname "$0")/.."

LOG_DIR="logs"
FULL_LOG="${LOG_DIR}/test-full.txt"
mkdir -p "${LOG_DIR}"

# A bare word that names a suite is a convenience for `tests/test_<word>.py`;
# anything starting with a dash is passed straight through to pytest.
ARGS=()
if [ "$#" -gt 0 ] && [ "${1#-}" = "$1" ] && [ -f "tests/test_$1.py" ]; then
    ARGS+=("tests/test_$1.py")
    shift
fi
ARGS+=("$@")

PYTHON="${PYTHON:-python}"
command -v "${PYTHON}" >/dev/null 2>&1 || PYTHON=python3

# Pin the settings explicitly, for two separate reasons.
#
# 1. pytest-django's precedence is --ds, then the DJANGO_SETTINGS_MODULE
#    *environment variable*, then the ini file — so pyproject.toml's setting
#    loses inside the container, where the image exports config.settings.pi.
#    --ds is the only level that beats the environment.
# 2. config.settings.test is pinned rather than derived: dev.py still reads the
#    database engine, cache, and house apps from .env, so on the Pi it resolved
#    to the real MySQL and every database test errored on a missing grant.
#
# Override with NORA_HOME_TEST_SETTINGS to run against something else on purpose.
TEST_SETTINGS="${NORA_HOME_TEST_SETTINGS:-config.settings.test}"

# --tb=line keeps the file readable too: one line per failure rather than a
# full stack. Swap to --tb=long by hand when a failure genuinely needs it.
set +e
"${PYTHON}" -m pytest \
    --ds="${TEST_SETTINGS}" \
    --tb=line \
    -q \
    --no-header \
    -p no:cacheprovider \
    ${ARGS[@]+"${ARGS[@]}"} > "${FULL_LOG}" 2>&1
STATUS=$?
set -e

# The report block is delimited by the reporter's own rules; print from the
# first one to the end of the file.
# pytest's own one-line-per-failure recap follows the report and repeats what it
# already said, so it is trimmed rather than paid for twice.
if grep -q "NORA HOME — test report" "${FULL_LOG}"; then
    printf '──────────────────────────────────────────────────────────────\n'
    sed -n '/NORA HOME — test report/,$p' "${FULL_LOG}" \
        | sed '/short test summary info/,$d'
else
    # The reporter never ran — pytest died before collection (a bad import in
    # conftest, a missing dependency). Show the tail; there is nothing else.
    echo "Test run failed before reporting. Last 25 lines:"
    tail -25 "${FULL_LOG}"
fi

echo
echo "Full output: ${FULL_LOG}"
exit ${STATUS}
