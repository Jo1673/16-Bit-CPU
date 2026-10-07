# Initial block-level timing budget; replace with actual integration constraints.
# 20 MHz target is NOT a measured result. Units: ns and library capacitance units.
current_design cpu16_core
create_clock -name core_clock -period 50.0 [get_ports clk]
set_clock_uncertainty 0.5 [get_clocks core_clock]
set_clock_transition 0.2 [get_clocks core_clock]
set non_clock_inputs [lsearch -inline -all -not -exact [all_inputs] [get_ports clk]]
set_input_delay -max 10.0 -clock core_clock $non_clock_inputs
set_input_delay -min 1.0 -clock core_clock $non_clock_inputs
set_output_delay -max 10.0 -clock core_clock [all_outputs]
set_output_delay -min 1.0 -clock core_clock [all_outputs]
set_input_transition 0.2 $non_clock_inputs
set_load 0.02 [all_outputs]
# rst_n is synchronous and stays timed. No blanket reset false path.
# Ready/data must come from the same clock domain or a separately verified bridge.
