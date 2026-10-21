# UART board integration, 2026-10-21

Approved scope: seven-IO board wrapper, C24 UART constraints, full serial
simulation of N=16 K=2048, PDS compile through bitstream, passive board capture.
No commit or push. Existing LED-only bitstream remains available.

Decisions:
- Continue the existing checkout because it contains the approved UART files.
- Reference canonical root RTL from PDS rather than maintain duplicate UART RTL.
- Keep v1 binary protocol (no status/CRC fields). Board PASS includes capture
  overflow and expected count; receiver verifies every tuple against golden.
- Use asynchronous reset assertion, two-clock synchronized reset release.
- Verify board captures separately from simulation captures; source must be explicit.

Evidence so far:
- Board manual printed pp.39-40: FPGA_UART_TXD C24, CP2102.
- Supplied PG2L100H UART constraints: C24, LVCMOS33, 3.3 V.
- Baseline UART lint/unit/top lint passed in WSL.
- New test first failed because board wrapper was absent; wrapper implemented.
- Full 234-divisor serial test passed for depth256 and overflow depth255;
  each performs three reset reruns plus interrupted-frame reset recovery.
- Original fixture lint exposed missing connections to new runner event outputs;
  connected intentionally unused event wires in legacy wrappers/testbenches.

Completed:
- Fixed missing event-port connections in legacy callers; regressions pass.
- Fixed verify_board_mem.py legacy no-config inference: N=results/groups.
  Validated copies go to build/fixed_slice_board_verified, preserving K128 smoke.
- Complete regression: 17 phases PASS, build/reports/summary.json.
- Parser/receiver tests: 9 PASS, including explicit provenance, invalid/missing
  tags, fragmented input and recovery from interrupted frames.
- PDS top changed and saved: fixed_slice_qwen_uart_board_top.
- Compile, Synthesize, Device Map, Place & Route, Report Timing, bitstream PASS.
- Post-route setup slack 22.494 ns; worst hold (fast) 0.057 ns; no violations.
- 1126 LUT, 373 registers, 16 APM, 8 DRM, 7 IO; capture uses distributed RAM.
- New bitstream SHA256:
  718330d02168d8a9af8ed09f5d24bc70e69eaad67431faef7639c3c7382eef16.
- PDS moved previous LED-only bitstream into bak; copied it back after verifying
  git blob hash d46418a518bc31614cfba0ae9ba345d776098f86 matches HEAD.
- Only COM1 detected, no CP2102 USB serial currently present.

Final review: independent read-only reviewer found one receiver recovery issue:
an interrupted frame followed by a complete new frame caused an exception.
Fixed with FrameScanner resynchronization; three new tests observed failing
before implementation and then passing. Full 17-phase regression rerun PASS.
Review set aside physical reception (no CP2102), full-model inference (slice only),
and generated-report whitespace (tool output); these remain explicitly bounded.
Documentation was reviewed separately by the main agent.

Windows .venv-uart-win created and pyserial3.5 installed locally; capture CLI
and serial enumeration tested. Only COM1 is currently present.

Pending: actual board UART capture after connecting the USB-UART Type-C port.
No board capture has been claimed. No deferred minor code-review findings.
Last UI observation showed the Windows lock screen; stopped all further UI
input as required. PDS build/save had already completed before it locked.

Follow-up after unlock: JTAG scan identified PG2L100H ID0x00602899. New UART
bitstream programmed successfully via official cdt_cfg_shell, done=1,
status0x081ffca0 with CRC/auth/ID error flags all0. Log in
artifacts/uart_board/2026-10-21/program.log. Physical UART still not enumerated:
only COM1 and FTDI COM6/COM7. User unplugged only UART and these ports did not
change, confirming they belong to remaining downloader. Awaiting a data-cable
or USB-port change before real capture; full record in uart_board_capture_2026-10-21.md.

Final hardware follow-up, 2026-10-21: CP2102 driver installed by user. Live
enumeration confirms COM10, VID:PID 10C4:EA60, serial0001, PnP Ports status OK.
Opened COM10 passively at 115200 8N1 before each user-confirmed KEY0 reset.
Three actual board captures, run1/run2/run3: each 2057 bytes, 256 unique tags,
all row_id/group_id/partial_sum values match PDS expected.mem; exact row-major
group-major order. All three raw frames identical, SHA256
410f0086fa79888f974e245f9ac878eaad452fdd9ee3adc5eb3f62f484077cf0.
User confirmed LED1/LED2 on and LED3 off after every reset. No UART-inferred
LED or bitstream identity claim: protocol does not carry these fields.
Current bitstream hash rechecked against prior programming record, unchanged.
Evidence: artifacts/uart_board/2026-10-21/{run1,run2,run3}.{bin,json} and
verification_manifest.json. Raw data are Git-ignored and need separate handoff.
All originally pending actual board UART/reset checks now complete. No new RTL
changes, re-build, re-programming, commit or push during this capture session.
