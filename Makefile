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
	  -GLANES=16 --Mdir build/adapter16 $(ADAPTER_RTL) $(CURDIR)/tests/test_paired_lane_adapter.cpp

.PHONY: test-integration16 test-adapter
test-integration16: test-model build-integration16
	$(PYTHON) scripts/verify_b_vectors.py --integration --integration-lanes 16

test-adapter: build-adapter
	$(PYTHON) scripts/run_adapter_tests.py

.PHONY: benchmark-lanes
benchmark-lanes:
	$(PYTHON) scripts/benchmark_lanes.py

LANE_ADAPTER_RTL = rtl/compute/lane_adapter_32_to_16.sv tests/tb_lane_adapter.sv
LANE_ADAPTER_DIR ?= build/lane_adapter

lint-lane-adapter:
	$(VERILATOR) --lint-only -Wall --top-module tb_lane_adapter $(LANE_ADAPTER_RTL)

build-lane-adapter:
	@mkdir -p build
	$(VERILATOR) --cc --exe --build --trace -Wall \
	  --top-module tb_lane_adapter --Mdir $(LANE_ADAPTER_DIR) \
	  $(LANE_ADAPTER_RTL) $(CURDIR)/tests/test_lane_adapter.cpp

test-lane-adapter: build-lane-adapter
	./$(LANE_ADAPTER_DIR)/Vtb_lane_adapter


CONTROL_RTL = $(B_RTL) rtl/compute/lane_adapter_32_to_16.sv rtl/control/control_regs.sv rtl/control/task_controller.sv rtl/control/accelerator_control_top.sv
CONTROL_DIR ?= build/control
CONTROL16_DIR ?= build/control16
CONTROL_FIXTURE ?= build/b_fixtures/case_n3_k256.txt

control-fixture:
	$(PYTHON) scripts/prepare_control_fixture.py

build-control:
	@mkdir -p build
	$(VERILATOR) --cc --exe --build --trace -Wall \
	  --top-module tb_control --Mdir $(CONTROL_DIR) \
	  $(CORE_RTL) $(CONTROL_RTL) tests/tb_control.sv $(CURDIR)/tests/test_control.cpp

test-control: control-fixture build-control
	@set -e; \
	./$(CONTROL_DIR)/Vtb_control $(CONTROL_FIXTURE); \
	./$(CONTROL_DIR)/Vtb_control --errors

lint-control:
	$(VERILATOR) --lint-only -Wall --top-module tb_control \
	  $(CORE_RTL) $(CONTROL_RTL) tests/tb_control.sv

build-control-16:
	@mkdir -p build
	$(VERILATOR) --cc --exe --build --trace -Wall -GLANES=16 \
	  --top-module tb_control --Mdir $(CONTROL16_DIR) \
	  $(CORE_RTL) $(CONTROL_RTL) tests/tb_control.sv $(CURDIR)/tests/test_control.cpp

lint-control-16:
	$(VERILATOR) --lint-only -Wall -GLANES=16 --top-module tb_control \
	  $(CORE_RTL) $(CONTROL_RTL) tests/tb_control.sv

test-control-16: control-fixture build-control-16
	@set -e; \
	./$(CONTROL16_DIR)/Vtb_control $(CONTROL_FIXTURE); \
	./$(CONTROL16_DIR)/Vtb_control --errors

test-system-control: test-model test-control test-control-16

FIXED_SLICE_RTL = $(CORE_RTL) rtl/compute/lane_adapter_32_to_16.sv rtl/model/fixed_slice_runner.sv rtl/model/fixed_slice_demo_top.sv rtl/model/fixed_slice_qwen_demo_top.sv
FIXED_SLICE_DIR ?= build/fixed_slice
FIXED_SLICE_TEST_DIR ?= build/fixed_slice_sim
FIXED_SLICE_QWEN_DIR ?= build/fixed_slice_qwen
FIXED_SLICE_QWEN_TEST_DIR ?= build/fixed_slice_qwen_sim

fixed-slice-fixture:
	$(PYTHON) scripts/prepare_fixed_slice_mem.py tests/vectors/case_n1_k128 $(FIXED_SLICE_DIR)

lint-fixed-slice: fixed-slice-fixture
	$(VERILATOR) --lint-only -Wall --top-module tb_fixed_slice \
	  $(FIXED_SLICE_RTL) tests/tb_fixed_slice.sv

build-fixed-slice: fixed-slice-fixture
	@mkdir -p build
	$(VERILATOR) --cc --exe --build --trace -Wall \
	  --top-module tb_fixed_slice --Mdir $(FIXED_SLICE_TEST_DIR) \
	  $(FIXED_SLICE_RTL) tests/tb_fixed_slice.sv $(CURDIR)/tests/test_fixed_slice.cpp

test-fixed-slice: build-fixed-slice
	./$(FIXED_SLICE_TEST_DIR)/Vtb_fixed_slice

fixed-slice-qwen-inputs:
	@test -f $(FIXED_SLICE_QWEN_DIR)/weights.mem
	@test -f $(FIXED_SLICE_QWEN_DIR)/activation.mem
	@test -f $(FIXED_SLICE_QWEN_DIR)/expected.mem

lint-fixed-slice-qwen: fixed-slice-qwen-inputs
	$(VERILATOR) --lint-only -Wall --top-module tb_fixed_slice_qwen \
	  $(FIXED_SLICE_RTL) tests/tb_fixed_slice_qwen.sv

build-fixed-slice-qwen: fixed-slice-qwen-inputs
	@mkdir -p build
	$(VERILATOR) --cc --exe --build --trace -Wall \
	  --top-module tb_fixed_slice_qwen --Mdir $(FIXED_SLICE_QWEN_TEST_DIR) \
	  $(FIXED_SLICE_RTL) tests/tb_fixed_slice_qwen.sv $(CURDIR)/tests/test_fixed_slice_qwen.cpp

test-fixed-slice-qwen: build-fixed-slice-qwen
	./$(FIXED_SLICE_QWEN_TEST_DIR)/Vtb_fixed_slice_qwen
