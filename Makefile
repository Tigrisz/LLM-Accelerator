VERILATOR ?= verilator
PRIMITIVE_RTL = rtl/compute/int4_unpack.sv rtl/compute/mac_lane.sv tests/tb_compute_primitives.sv
CORE_RTL = rtl/compute/int4_unpack.sv rtl/compute/mac_lane.sv rtl/compute/group_acc.sv rtl/compute/gemv_core.sv
PYTHON ?= python3
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

.PHONY: test-compute lint
test-compute: test-primitives
	@set -e; for lanes in 16 32; do \
	  $(VERILATOR) --cc --exe --build --trace -Wall --top-module gemv_core \
	    -GLANES=$$lanes -CFLAGS "-DTEST_LANES=$$lanes" \
	    --Mdir build/core_$$lanes $(CORE_RTL) $(CURDIR)/tests/test_gemv_core.cpp; \
	  ./build/core_$$lanes/Vgemv_core; \
	done

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
	  --top-module tb_b_integration --Mdir $(INTEGRATION_DIR) \
	  $(CORE_RTL) $(B_RTL) tests/tb_b_integration.sv $(CURDIR)/tests/test_b_integration.cpp

test-integration: test-model build-integration
	$(PYTHON) scripts/verify_b_vectors.py --integration

lint-integration:
	$(VERILATOR) --lint-only -Wall --top-module tb_b_integration \
	  $(CORE_RTL) $(B_RTL) tests/tb_b_integration.sv
