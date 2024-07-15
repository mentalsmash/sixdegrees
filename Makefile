###############################################################################
# Global makefile configuration
###############################################################################
# Python module version
PY_VERSION := $(shell grep __version__ sixdegrees/__init__.py | cut -d= -f2- | tr -d \" | cut '-d ' -f2-)
# Name of the Python module
PY_NAME := $(shell grep '^name =' pyproject.toml | cut -d= -f2- | tr -d \" | cut '-d ' -f2-)
ifneq ($(PY_NAME),sixdegrees)
$(warning unexpected Python module name: '$(PY_NAME)')
endif
# Local clone
ROOT_DIR ?= $(shell pwd)
# Directory where to generate test logs
# When running inside do It MUST be a subdirectory of ROOT_DIR
TEST_RESULTS_DIR ?= $(ROOT_DIR)/test-results
# A unique ID for the test run
TEST_ID ?= local
# The date when the tests were run
TEST_DATE ?= $(shell date +%Y%m%d-%H%M%S)
# Common prefix for the JUnit XML report generated by tests
TEST_JUNIT_REPORT ?= $(PY_NAME)-test-$(TEST_ID)__$(TEST_DATE)
# Directory where to generate file
OUT_DIR ?= $(ROOT_DIR)

# Set default verbosity from DEBUG flag
ifneq ($(DEBUG),)
VERBOSITY ?= debug
endif
export VERBOSITY
export DEBUG

.PHONY: \
	code \
	code-check \
	code-format \
	code-format-check \
	code-style \
	code-style-check \
	test \
	venv-install \

# Run unit tests
test: .venv
	mkdir -p $(TEST_RESULTS_DIR)
	pytest -s -v \
    --junit-xml=$(TEST_RESULTS_DIR)/$(TEST_JUNIT_REPORT)__unit.xml \
    test $(UNIT_TEST_ARGS)

# Install package and its dependencies in a virtual environment.
venv-install: .venv ;

#
.venv: pyproject.toml
	rm -rf $@
	python3 -m venv $@
	$@/bin/pip install -U pip setuptools ruff pre-commit pytest
	$@/bin/pip install -e .

# Code validation targets
code: \
  code-style \
  code-format ;

code-check: \
  code-precommit ;

code-format: .venv
	$</bin/ruff format

code-format-check: .venv
	$</bin/ruff format --check

code-style: .venv
	$</bin/ruff check --fix

code-style-check: .venv
	$</bin/ruff check

code-precommit: .venv
	$</bin/pre-commit run --all
