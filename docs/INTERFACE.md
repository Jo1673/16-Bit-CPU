# Connecting memories

All signals belong to the rising-edge `clk` domain. `rst_n` is active-low,
synchronous reset. Hold it low across at least one clock edge after power-up;
the tests use several edges. Deassert reset synchronously and meet its timing.

| Port | Direction relative to CPU | Width | Meaning |
|---|---|---|---|
| clk | in | 1 | Clock |
| rst_n | in | 1 | Synchronous active-low reset |
| imem_addr | out | 16 | Instruction word address |
| imem_valid | out | 1 | Instruction read requested |
| imem_rdata | in | 16 | Instruction/extension word |
| imem_ready | in | 1 | Instruction response valid this edge |
| dmem_addr | out | 16 | Data word address |
| dmem_wdata | out | 16 | Data to store |
| dmem_valid | out | 1 | Data transaction requested |
| dmem_we | out | 1 | Store when 1; load when 0 |
| dmem_rdata | in | 16 | Load result |
| dmem_ready | in | 1 | Transaction completes this edge |
| halted | out | 1 | HALT executed |

There are 88 signal bits total, before power connections. These are core ports,
not an 88-pin package definition. A small shuttle usually needs a wrapper,
local memories, and a narrower host interface.

## Transaction rules

1. Completion occurs only on a rising edge with `valid && ready && rst_n`.
2. The CPU holds address, write direction, and write data stable while waiting.
3. The responder supplies read data by the completing edge. It may assert ready
   continuously for a combinational memory, or only when its response is ready. Read data
   need only be valid **on the completing edge**: the regression drives random garbage on
   `imem_rdata`/`dmem_rdata` whenever ready is low, and ready may be high without valid.
4. A store commits **once**, at completion. Do not write on every cycle of
   `dmem_we`; that signal stays high throughout a stalled store.
5. Reset cancels an uncompleted request. The responder/bridge must also cancel
   it so that a stale acknowledgment or deferred store cannot affect the reboot.
6. Address and data outside a valid request are unspecified for the responder.
   After HALT both valid outputs and dmem_we are low.

Reset gates request outputs immediately but changes architectural registers
only at the clock edge. A short reset pulse that misses all clock edges does
not reset the CPU. Avoid asynchronous reset glitches from an external pin.

### Example: combinational simulation memory

The complete model is in `tb/tb_cpu16.sv`. Its essential wiring is:

```verilog
assign imem_ready = 1'b1;
assign imem_rdata = imem[imem_addr];
assign dmem_ready = 1'b1;
assign dmem_rdata = dmem[dmem_addr];
always @(posedge clk)
    if (rst_n && dmem_valid && dmem_ready && dmem_we)
        dmem[dmem_addr] <= dmem_wdata;
```

The regression (`tb/tb_cpu16.sv`) exercises four responders: `MODE=0` the model above with
ready always high; `1` random ready with garbage data while not ready; `2` the registered
one-cycle SRAM bridge described next; `3` long bursty waits. With ready always high the instruction
timing in `ISA.md` holds cycle-for-cycle and is checked exactly.

This is a simulation example, not a supplied SRAM macro. Do not synthesize the
testbench's 65,536-word arrays and assume they will turn into a suitable SRAM.

### Example: one-cycle synchronous SRAM

Use a controller that captures a new valid request, issues the SRAM access,
then presents ready with the returned data on the following cycle. The CPU
holds its request until that response. The controller must track an in-flight
transaction; a valid held high during a wait is not a sequence of new requests.

Do not tie ready high on a one-cycle-latency RAM unless the data is already
available at the accepting edge. Otherwise the CPU consumes the preceding
read result. Ready/valid solves latency; it does not solve clock-domain crossing.
An off-chip or differently clocked memory requires its own verified bridge.

## Memory map and boot

Reset fetches instruction word zero. The integrator supplies ROM, preloaded RAM,
or a host loader that finishes loading memory before releasing reset. This
delivery uses external memory models and includes no hardware loader.

Addresses are words: data address 1 denotes the next 16-bit word, not its high
byte. If a host uses byte addresses, its controller must define the conversion
and byte order. Raw words in the `.hex` file do not prescribe serial or byte
transport endianness. No memory error/timeout signal is implemented; a responder
that never raises ready stalls the CPU until reset.
