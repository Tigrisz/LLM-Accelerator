VERILATOR ?= verilator
PRIMITIVE_RTL = rtl/compute/int4_unpack.sv rtl/compute/mac_lane.sv tests/tb_compute_primitives.sv
CORE_RTL = rtl/compute/int4_unpack.sv rtl/compute/mac_lane.sv rtl/compute/group_acc.sv rtl/compute/gemv_core.sv
PYTHON ?= python3
ADAPTER_RTL = rtl/compute/paired_lane_adapter.sv
INTEGRATION_LANES ?= 32
B_RTL_DIR ?= rtl/memory
B_RTL = $(B_RTL_DIR)/memory_model.sv $(B_RTL_DIR)/weight_reader.sv $(B_RTL_DIR)/activation_cache.sv $(B_RTL_DIR)/paired_input_stream.sv
INTEGRATION_DIR ?= build/integration
INTEGRATION_FLAGS ?=

.PHONY: test-primitives lint-primitives
test-primitives:
	@mkdir -p build
	@set -e; for lanes in 16 32; do \
	  $(VERILATOR) --cc --exe --build -Wall --top-module tb_compute_primitives \
	    -GLANES=$$lanes -CFLAGS "-DTEST_LANES=$$lanes" \
	    --Mdir build/primitives_$$lanes $(PRIMITIVE_RTL) $(CURDIR)/tests/test_compute_primitives.cpp; \
	  ./build/primitives_$$lanes/Vtb_compute_primitives; \
	done

lint-primitives:
	$(VERILATOR) --lint-only -Wall --top-module tb_compute_primitives $(PRIMITIVE_RTL)

.PHONY: test-compute build-compute lint
build-compute: test-primitives
	@set -e; for lanes in 16 32; do \
	  $(VERILATOR) --cc --exe --build --trace -Wall --top-module gemv_core \
	    -GLANES=$$lanes -CFLAGS "-DTEST_LANES=$$lanes" \
	    --Mdir build/core_$$lanes $(CORE_RTL) $(CURDIR)/tests/test_gemv_core.cpp; \
	done

test-compute: build-compute
	$(PYTHON) scripts/run_core_tests.py

lint: lint-primitives
	@set -e; for lanes in 16 32; do \
	  $(VERILATOR) --lint-only -Wall --top-module gemv_core -GLANES=$$lanes $(CORE_RTL); \
	done

.PHONY: test-model test-b-vectors build-integration test-integration lint-integration
test-model:
	$(PYTHON) scripts/run_model_tests.py

test-b-vectors: test-compute test-model
	$(PYTHON) scripts/verify_b_vectors.py

build-integration:
	@mkdir -p build
	$(VERILATOR) --cc --exe --build --trace -Wall $(INTEGRATION_FLAGS) \
	  -GLANES=$(INTEGRATION_LANES) -CFLAGS "-DTEST_LANES=$(INTEGRATION_LANES)" \
	  --top-module tb_b_integration --Mdir $(INTEGRATION_DIR) \
	  $(CORE_RTL) $(ADAPTER_RTL) $(B_RTL) tests/tb_b_integration.sv $(CURDIR)/tests/test_b_integration.cpp

test-integration: test-model build-integration
	$(PYTHON) scripts/verify_b_vectors.py --integration

lint-integration:
	@set -e; for lanes in 16 32; do \
	  $(VERILATOR) --lint-only -Wall --top-module tb_b_integration -GLANES=$$lanes \
	    $(CORE_RTL) $(ADAPTER_RTL) $(B_RTL) tests/tb_b_integration.sv; \
	done

.PHONY: test-monitor regression
test-monitor:
	@mkdir -p build
	$(CXX) -std=c++14 -Wall -Wextra -Werror tests/test_stream_monitor.cpp -o build/test_stream_monitor
	./build/test_stream_monitor

regression:
	$(PYTHON) scripts/run_regression.py

.PHONY: build-integration16
build-integration16:
	$(MAKE) build-integration INTEGRATION_LANES=16 INTEGRATION_DIR=build/integration16

.PHONY: build-adapter
build-adapter:
	$(VERILATOR) --cc --exe --build --trace -Wall --top-module paired_lane_adapter \
	  -GLANES=16 --Mdir build/adapter16 $(ADAPTER_RTL) $(CURDIR)/tests/test_lane_adapter.cpp

.PHONY: test-integration16 test-adapter
test-integration16: test-model build-integration16
	$(PYTHON) scripts/verify_b_vectors.py --integration --integration-lanes 16

test-adapter: build-adapter
	$(PYTHON) scripts/run_adapter_tests.py
