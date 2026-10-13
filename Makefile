.PHONY: test-compute test-integration bench-memory smoke

PYTHON ?= python

test-compute:
	$(PYTHON) scripts/run_model_tests.py

test-integration:
	@echo "RTL integration testbench is ready for Verilator/iverilog; no simulator is bundled in this workspace."
	$(PYTHON) scripts/run_model_tests.py

bench-memory:
	@echo "Memory benchmark becomes executable when the Day 7 top-level testbench is connected."
	$(PYTHON) scripts/generate_smoke_case.py

smoke: test-compute

