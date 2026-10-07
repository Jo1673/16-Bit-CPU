# Physical implementation and tapeout handoff

**This package is ready to enter your core RTL-to-GDS flow. It is not a foundry-
approved tapeout submission.** The included verification covers the CPU RTL and
generic synthesis. There is no routed CPU16 GDS in this delivery.

## 1. Run functional checks first

From this project directory:

```bash
make lint      # Verilator -Wall
make test      # ~190 differential RTL runs against the reference model
make reset     # directed reset test
make gate      # the same programs on the synthesized netlist, ports only
make mutate    # 61 injected RTL faults must all be caught
```

Keep the results with the exact RTL revision you implement. Do not substitute
the testbench or Python model for synthesizable RTL. Only `rtl/*.v` enters ORFS.

## 2. Install into your existing ORFS repository

```bash
bash install_into_orfs.sh "$HOME/OpenROAD-flow-scripts"
cd "$HOME/OpenROAD-flow-scripts/flow"
util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu16_core/config.mk
```

This follows the [ORFS design configuration workflow](https://openroad-flow-scripts.readthedocs.io/en/latest/user/AddingNewDesign.html)
and [Docker shell workflow](https://openroad-flow-scripts.readthedocs.io/en/latest/user/DockerShell.html).
The top module is `cpu16_core`, platform `sky130hd`, starting utilization 35%,
placement density 0.55, square core, 5 µm core margin. These are starting settings,
not measured optimum values. Adjust them using the actual routing/power results.

The config explicitly sets PLATFORM. Its paths resolve from the config file's
location, avoiding the prior project's dependence on a manually chosen
DESIGN_HOME. If you see “PLATFORM variable not set,” check the config exists
at the given path **inside the container** and that you ran make from `flow`.
Do not invoke the project root Makefile expecting it to execute ORFS.

Inside an existing ORFS shell instead:

```bash
make DESIGN_CONFIG=designs/sky130hd/cpu16_core/config.mk
```

To inspect the result:

```bash
util/docker_shell make DESIGN_CONFIG=designs/sky130hd/cpu16_core/config.mk gui_final
```

ORFS organizes generated layout/netlists under `results`, logs under `logs`,
and checks under `reports`; see its [flow tutorial](https://openroad-flow-scripts.readthedocs.io/en/latest/tutorials/FlowTutorial.html).
Your design's directories are:

```text
flow/results/sky130hd/cpu16_core/base/
flow/reports/sky130hd/cpu16_core/base/
flow/logs/sky130hd/cpu16_core/base/
```

Expect final-stage files such as `6_final.gds`, `6_final.odb`, `6_final.v`,
`6_final.def`, `6_final.sdc`, and `6_final.spef`, depending on flow version.
Check the actual directory rather than assuming every named file exists.

From the CPU16 project, collect results for review with:

```bash
python3 tools/collect_orfs.py "$HOME/OpenROAD-flow-scripts" -o cpu16_orfs_results.zip
```

This bundles available results, reports, logs, source/config snapshots, hashes,
and the ORFS commit. It does not declare the reports passing.

## 3. Understand and replace the timing assumptions

The SDC sets a 50 ns clock (20 MHz), 0.5 ns uncertainty, 0.2 ns clock/input
transition, 1 ns minimum and 10 ns maximum input/output delays, and 0.02 units
of output capacitance. In the intended Sky130 library context capacitance is
typically expressed in pF; confirm units in the actual Liberty/STA setup.
These values are provisional budgets for a block, not measurements of your
board, SRAM, or harness. See [ORFS variables](https://openroad-flow-scripts.readthedocs.io/en/latest/user/FlowVariables.html)
for supported flow configuration.

Every non-clock input, including synchronous reset and ready signals, is timed.
There is no blanket false path on reset and no multicycle exception concealing
paths. A multicycle controller still contains register paths that operate on
every clock edge. Only add exceptions when the real circuit protocol justifies
them and they have been reviewed.

Before claiming timing closure, replace the I/O delays, loads, transition and
clock uncertainty with the actual integration contract. Check setup and hold
at required process/voltage/temperature corners, with extracted parasitics,
clock latency/skew, clock gating rules if applicable, and no unintentionally
unconstrained paths. Review slew, capacitance, and fanout violations as well.

## 4. Complete the chip around the core

The exact files depend on the selected shuttle. A core alone is not a standalone
chip: it needs memory, program loading, power, reset, a clock source, and a way
to observe results. Do not directly treat core ports as bond pads.

| Decision | Required implementation |
|---|---|
| Shuttle/foundry and supported PDK revision | Use its official harness and submission flow |
| Available I/O and host connection | A wrapper/bridge that fits its pin budget |
| Program storage | ROM or loadable memory, with a defined boot procedure |
| Data memory size | Approved SRAM macro or deliberately budgeted smaller storage |
| Clock/reset origin | Clock-domain/reset handling with verified timing |
| Power and I/O voltages | Approved pads/harness, ESD, power connections, isolation/level shifting where needed |
| Manufacturing/debug strategy | Test access and coverage acceptable for the project/shuttle |

This package intentionally does not guess an SRAM macro name, a pad cell,
an unknown harness pinout, or a currently available shuttle allocation. Those
choices are necessary before generating a valid submission top level.

## 5. Required release evidence

| Gate | Current delivery | Evidence to close it |
|---|---|---|
| CPU RTL simulation | Passed; see STATUS.md | Retain logs for released RTL |
| Lint and generic synthesis | Passed | Re-run on final integration RTL |
| Generic gate-level simulation | Passed: every program, four memory modes | Repeat on the Sky130-mapped and post-route netlists with the same testbench |
| Mutation analysis | Passed: every injected fault caught | Re-run after any RTL change |
| Core Sky130 place and route | Not run here | Successful flow logs and layout/netlists |
| Timing closure | Not measured | Setup/hold reports at required corners and I/O budgets |
| Memory/boot/harness integration | Not supplied | Integrated top-level simulation and physical results |
| DRC | Not run | Clean required decks or approved waivers |
| LVS | Not run | Extracted layout matches final schematic/netlist |
| Antenna/density/fill | Not run | Required clean reports and correct fill process |
| Power integrity | Not run | Power-grid connectivity, IR-drop/EM review as required |
| Clock/reset/CDC integration review | Core is single-clock | Review the actual surrounding design |
| Test/observability plan | Not finalized | Approved means to exercise and observe fabricated chip |
| Shuttle submission checks | Not run | Current harness/precheck acceptance |
| Final release archive | Source package supplied | Approved GDS/netlist/configs/reports with reproducible revisions |

The SkyWater PDK distinguishes [design-rule verification](https://skywater-pdk.readthedocs.io/en/main/verification/drc.html)
from [layout-versus-schematic verification](https://skywater-pdk.readthedocs.io/en/main/verification/lvs.html).
A router's internal DRC count is not a replacement for all required signoff
checks. A successful GDS export is not an LVS result.

Use the shuttle's approved DRC/LVS decks and setup for the final integrated top.
There is no universally valid Magic/Netgen command without knowing that PDK,
cell library, power-net naming, and harness. Treat a missing report as missing
evidence, never as zero violations.

## 6. Freeze the reproducible release

Record your ORFS git revision, container image digest, Yosys/OpenROAD versions,
PDK revision, RTL/config hashes, and submission harness revision. Archive the
final GDS with its matching netlist, timing constraints, extracted parasitics,
and signoff reports. A later source edit invalidates the correspondence unless
the affected flow stages and verification are rerun.

The remaining project-specific information needed to finish the submission is
the exact shuttle/harness, its I/O budget, and your memory/boot plan. Once those
are chosen, adapt the wrapper and constraints, implement the full top level,
and close the gates above before sending it to fabrication.
