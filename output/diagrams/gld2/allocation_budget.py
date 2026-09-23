"""Auditable nominal power-allocation scenario. No measured/max-load claim."""
from pathlib import Path
import json
from power_budget import B, SOURCES

HERE=Path(__file__).resolve().parent

def calculate_allocation():
    # Approximate readings of manufacturer typical efficiency curves.
    eta24, eta33 = .92, .93
    digital = dict(ESP32=.0917, LoRa=.119, ADS=.0009, SHT40=.000320,
                   PCF8574=.000100, RS485=.000700, USB=.004)
    # Seven 10k and three 100k pullups: simultaneous-low allocation envelope.
    # LED off. This is an allowance, not the claimed DC logic state.
    digital_pullups = 7*3.3/10000 + 3*3.3/100000
    digital_A = sum(digital.values()) + digital_pullups
    digital_W = digital_A*3.3
    digital_input_W = digital_W/eta33
    vref_A = 2.5/(18500*7.68/8 + 22)
    adc_input_allowance_A = .000035
    module_switch_IQ_A = .000008  # datasheet3.6V benchmark applied as estimate
    buck_V=B['buck_V']
    rail_V=buck_V
    # Solve the DC voltage drop and load current together. Current through a
    # series switch is conserved; its power loss is not a fictitious extra load.
    for _ in range(40):
        module_rows=[]
        for s in B['sensors']:
            ic_A=.000050+.000210+.000100+adc_input_allowance_A/8
            module_V=(rail_V-.089*ic_A)/(1+.089*(1/s['ohms']+1/20000))
            electronics_A=ic_A+module_V/20000
            heater_A=module_V/s['ohms']
            out_A=heater_A+electronics_A
            module_rows.append(dict(model=s['model'],module_V=module_V,
              heater_A=heater_A,heater_W=module_V*heater_A,
              analog_A=electronics_A,electronics_A=electronics_A+module_switch_IQ_A,
              electronics_W=module_V*electronics_A+rail_V*module_switch_IQ_A,
              switch_loss_W=out_A*out_A*.089,header_A=out_A+module_switch_IQ_A))
        vmid_A=(rail_V/2)/(49.9+10000/8)
        analog_A=.007+2*.0015+.000650+rail_V/20000+vmid_A+vref_A
        mux_A=.000030+rail_V/10000
        main5_A=sum(r['header_A'] for r in module_rows)+analog_A+digital_input_W/rail_V+mux_A
        rail_V=buck_V-main5_A*.040
    module_analog_A=module_rows[0]['analog_A']
    module_extra_W=sum(r['electronics_W'] for r in module_rows)
    heater_W=sum(r['heater_W'] for r in module_rows)
    module_loss_W=sum(r['switch_loss_W'] for r in module_rows)
    modules_W=heater_W+module_extra_W+module_loss_W
    main5_W=main5_A*rail_V
    selector_loss_W=main5_A*main5_A*.040
    # Static AON upper references plus all three10k pullup branches.
    aon_A=50e-9+10e-6+.5e-6+.5e-6+3*3.3/10000
    aon_input_A=aon_A+25e-9 # light-load LDO ground-current reference
    aon_input_W=buck_V*aon_input_A # includes diode+LDO loss from buck source
    bias_A=buck_V/119100+buck_V/20990+1.32e-6
    bias_W=bias_A*buck_V
    buck_output_W=main5_W+selector_loss_W+aon_input_W+bias_W
    buck_input_W=buck_output_W/eta24
    gate_W=24*(24-12)/100000
    total_W=buck_input_W+gate_W
    losses=dict(main_buck=buck_input_W-buck_output_W,
                digital_buck=digital_input_W-digital_W,
                selector=selector_loss_W,module_switches=module_loss_W,
                aon_path=aon_input_W-aon_A*3.3)
    groups=[
      dict(title='Eight MQ heaters',W=heater_W,detail='Eight heaters; calculated path drops'),
      dict(title='Module electronics',W=module_extra_W,detail='8 x DAC, INA333, buffer and passives'),
      dict(title='ESP32',W=digital['ESP32']*3.3,detail='3.3 V / 91.7 mA; RF off reference'),
      dict(title='LoRa radio',W=digital['LoRa']*3.3,detail='3.3 V / 119 mA; TX reference'),
      dict(title='ADS and analog reference',W=analog_A*rail_V+digital['ADS']*3.3,detail='ADC, ADR03, OPA320 and VMID'),
      dict(title='Other digital loads',W=(digital_A-digital['ESP32']-digital['LoRa']-digital['ADS'])*3.3+mux_A*rail_V,
           detail='SHT40, PCF, USB, RS485, mux, pullups'),
      dict(title='AON and board bias',W=aon_A*3.3+bias_W+gate_W,detail='Supervision, dividers and gate bias'),
      dict(title='Conversion and switch loss',W=sum(losses.values()),detail='Two converters, selector, switches, LDO'),
    ]
    for g in groups:g['equivalent_24V_A']=g['W']/24
    assert abs(sum(g['W'] for g in groups)-total_W)<1e-10
    assert abs(sum(r['header_A'] for r in module_rows)*rail_V-modules_W)<1e-10
    return dict(scenario='24V-only nominal allocation, all8heaters, LoRaTX, ESP RFoff, RS485RX, USBactive, SHT heateroff, LEDoff, alarmoff; no battery or5VEXT contribution',
      eta24=eta24,eta33=eta33,buck_V=buck_V,rail_V=rail_V,heater_W=heater_W,digital=digital,digital_pullups_A=digital_pullups,
      digital_A=digital_A,digital_W=digital_W,digital_input_A=digital_input_W/rail_V,
      vmid_A=vmid_A,vref_A=vref_A,analog_A=analog_A,module_analog_A=module_analog_A,
      modules=module_rows,modules_A=modules_W/rail_V,mux_A=mux_A,main5_A=main5_A,
      main5_W=main5_W,aon_A=aon_A,aon_input_A=aon_input_A,bias_A=bias_A,
      buck_output_A=buck_output_W/buck_V,buck_input_A=buck_input_W/24,
      groups=groups,losses=losses,total_W=total_W,total_A=total_W/24,
      source_capacity_A=5,source_capacity_W=120,remaining_A=5-total_W/24,
      remaining_W=120-total_W,alarm_included_A=0,
      exclusions=['Unidentified active alarm and inrush','Input fuse/filter/FET/wiring ohmic losses',
                  'Unmodelled signal-switching, memory/I/O and leakage currents','Heater warm-up and fitted-vendor variation'])

A=calculate_allocation()

def export_allocation():
    (HERE/'allocation-calculations.json').write_text(json.dumps(A,indent=2)+'\n',encoding='utf8')
    notes='''# GLD2 power allocation - calculation basis

The nine-page diagram is an engineering reference allocation, not a measured load, a complete maximum-load calculation, or a PSU/PCB approval. The schematic buck set point is 4.98848 V. Solving load current and typical switch drops together gives a main rail of 4.92973 V and module rails of 4.914-4.916 V. These are estimates, not precision measurements. Series-switch current is conserved and its loss is included once. No schematic or firmware was changed. The external 5 V source and paths are omitted from the diagram as requested.

## Scenario

External 24 V supplies the board. All eight heaters use datasheet room-temperature resistance references evaluated at their calculated module voltages. Battery contribution is zero; its 4.2 V label identifies the reference source, while 0 A means no contribution in this case. It is not a leakage specification. ESP uses the 91.7 mA, 240 MHz RF-off benchmark; LoRa uses 119 mA TX. SHT measures with its heater off, RS485 receives, CH340 is active, status LED and alarm are off. USB power is excluded from attribution: all AON power is charged to 24 V even if attached USB would share it.

The diagram uses calculated local currents. Page9 separately expresses each load's watts as equivalent24V source current. Conversion losses form one separate branch, preventing double counting. Subtotals at different voltages are never added as amperes.

## Inputs and assumptions

- LMR51450: approximate92% from TI Figure7-1,24V-to5V near1.5A,500kHz. Schematic RT is open, matching500kHz default. TPS62162: approximate93% from TI Figure12,5V-to3.3V near0.22A. These curve readings are estimates for reference circuits, not guaranteed actual-board efficiencies. Converter bias is already included in curve efficiency; do not add it twice.
- Heater model: see power_budget.py and power-sources.json for eight resistance values, tolerances and reference vendors. MQ7 is budgeted at continuous5V for this supplied fixed-supply module; this does not implement the manufacturer's low/high heating cycle. Fitted makers and hot resistance are unverified.
- Module: INA333 50 uA + MCP4725 210 uA + XBLW LM321 100 uA, plus a local 10k/10k divider (about 245.7-245.8 uA). Datasheet no-load benchmarks are estimates at the calculated supply point, not fitted-board maxima. DAC benchmark: code 000h. TPS22919 uses 8 uA at 3.6 V as a small-current estimate and its 5 V typical on-resistance of 89 milliohms for conduction loss. One selected ADS input receives a 35 uA allocation, divided over modules for budgeting; it is not eight simultaneous ADC currents.
- VMID: eight 20k||20k module sensing paths plus the motherboard 49.9-ohm resistor. As sensor resistance approaches zero, current = (main rail / 2) / (49.9 + 10000 / 8), about 1.8962 mA. Delivered VMID is about 2.3702 V after the shared resistor, versus 2.4649 V unloaded. This is a passive-load bound, not an invented gas resistance.
- ADS: AVDD 7 mA and DVDD 0.9 mA at PGA 1 / buffer off are 7.68 MHz references applied to the schematic 8 MHz as estimates. VREF impedance of 18.5 kilohms is scaled inversely with clock, including the 22-ohm series resistor. Two OPA320 use 1.5 mA each (5.5 V benchmark applied at the calculated rail); ADR03 uses 650 uA. VMID divider adds main-rail voltage / 20k, about 246.5 uA.
- PCF8574 uses the NXP100uA table maximum at6V as a budgeting allowance at3.3V; fitted vendor unknown. TCA uses30uA table maximum at5.5V as allowance at5V. These are deliberate cross-condition approximations, not exact3.3V/5V guarantees.
- Digital pullup envelope: seven10k and three100k resistors at3.3V, all low as an allocation allowance. AON: three10k branches at3.3V plus static watchdog/inverter/latch/supervisor upper reference currents. These simultaneous-low envelopes are not normal logic-state claims. AON LDO ground current uses25nA light-load typical reference.
- TPS2116 uses40mohm typical conduction resistance and1.32uA bias. Board bias includes100k+19.1k feedback and16k+4.99k priority divider.24V gate/zener branch uses(24-12)/100k.
- Input fuse/filter/FET/wiring ohmic losses, unmodelled switching and I/O/memory activity, leakage, startup, thermal variation and alarm-on demand remain outside this reference subtotal. No unsupported numeric allowance is silently inserted. The remaining PSU capacity is provisional, not usable current through any particular PCB path.

## Reproduction and source ledger

Run `python output/diagrams/gld2/allocation_budget.py`. `allocation-calculations.json` stores unrounded values, local-rail totals, losses and the eight24V-equivalent allocations. `power-calculations.json` retains underlying independent datasheet reference cases. Sources below are supporting files, not extra PDF pages.

'''
    notes+='\n'.join(f'- [{p}]({u}) - {loc}' for _,p,loc,u in SOURCES)
    (HERE/'CALCULATION-NOTES.md').write_text(notes+'\n',encoding='utf8')

if __name__=='__main__':
    export_allocation()
    print(json.dumps(A,indent=2))
