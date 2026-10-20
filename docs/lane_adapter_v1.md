# 32-to-16 W4A8 lane adapter

`lane_adapter_32_to_16` converts one upstream 32-lane pair into two ordered
16-lane pairs. The upstream beat contains 128 bits of INT4 weights and 256
bits of INT8 activations; the two output halves are selected low first, then
high.

The adapter registers the complete input pair before producing output. It
does not accept a new pair until both output halves have been accepted. This
keeps the weight and activation payloads atomic and stable when either side
is stalled.

Metadata rules:

- `row_id` and `group_id` are copied to both halves.
- `group_first` is asserted only on the low half when the input beat is the
  first beat of a group.
- `group_last` is asserted only on the high half when the input beat is the
  last beat of a group.
- Reset drops any partially emitted pair and returns `in_ready` high.

The adapter changes the number of compute beats per 128-element group from
four to eight, but does not change logical `K`, physical `padded_K`, group
count, or the resulting partial sums.
