"""Shared data for make_pdf.py: the rendered original EasyEDA schematic, per-part bounding boxes, the block
definitions (which parts form one figure) and the 'what is this / what does it do' explanations (English)."""
import re

import content as C
import orig_render as O

PALETTE = ["#d9480f", "#1971c2", "#2f9e44", "#9c36b5", "#c2255c", "#0b7285", "#e67700", "#5f3dc4"]
ALIAS = {"G1": "G$1"}


def expand(spec):
    out = []
    for tok in [s.strip() for s in spec.split(",") if s.strip()]:
        m = re.fullmatch(r"([A-Za-z]+)(\d+)-([A-Za-z]+)(\d+)", tok)
        out += (["%s%d" % (m.group(1), i) for i in range(int(m.group(2)), int(m.group(4)) + 1)] if m else [tok])
    return out


body, wires, BB = O.render()


def bb(d):
    return BB.get(ALIAS.get(d, d))


ALL = []
for sh in C.SHEETS:
    for g in sh["groups"]:
        ALL += list(g["callouts"])
ALL += [
    ("C16,C17,C18", "10 uF capacitors on +5V, 5VBUCK and 5VBOOST next to U13.", "Decoupling of the input and output sides of the power mux."),
    ("R12", "100k pull-up to VCC on ST_P.", "Gives a 3.3 V logic level for the mux status signal read by the ESP32 (IO18)."),
    ("R16,R17", "10k I2C pull-ups to VCC on SCL and SDA.", "Pull-ups of the I2C bus used by the TCA9548A mux, PCF8574 and SHT40."),
    ("C84,C85", "100 nF and 10 uF capacitors on +24V.", "Decoupling of the +24V rail next to the alarm driver."),
    ("D7", "SS54 Schottky diode from 5VEXT to +5V.", "Lets external 5 V (J1 pin 4) supply the +5V rail without back-feeding."),
    ("C1,C2,C3,C4", "Decoupling capacitors 1 uF, 100 nF, 100 nF, 10 uF/50 V.",
     "Filter ripple/noise and hold up small transients on the +24V rail (paired with L1/L4)."),
    ("C78,C79", "100 nF and 10 uF capacitors on +5V.", "Decoupling of the +5V rail next to the fan driver."),
    ("C80,C81", "10 uF and 100 nF capacitors on +5VA.", "Decoupling of the analog +5VA rail after ferrite L6."),
    ("C65,C66,R77", "100 nF on +5V, 100 nF on RSTA, 10k pull-up on RSTA.", "Decoupling of the mux and a pull-up that keeps its RESET# pin high."),
    ("C14", "100 nF capacitor on VCC.", "Decoupling of the SHT40 sensor."),
    ("C15", "100 nF capacitor on VCC.", "Decoupling of the PCF8574."),
    ("C87", "100 nF capacitor on VCC.", "Decoupling of the RS-485 transceiver."),
    ("C33,C25", "10 uF and 100 nF capacitors on VCC.", "Decoupling of the LoRa module."),
    ("C32,C20", "10 uF and 100 nF capacitors on VCC.", "Decoupling of the ESP32-S3 module."),
    ("C34,C24", "10 uF and 100 nF capacitors on VCC.", "Decoupling of the CH340C."),
    ("C26", "100 nF capacitor on 3V3AON.", "Decoupling of the TPL5010."),
    ("C19", "100 nF capacitor on 3V3AON.", "Decoupling of the TPS3839 supervisor."),
    ("C27,C28", "100 nF capacitors on 3V3AON.", "Decoupling of the flip-flop and inverter in the latch circuit."),
    ("C35,R23,C39,C40", "+5V capacitor, PG pull-up and VCC output capacitors.",
     "Decoupling of the input/output of the 3.3 V buck; R23 is the pull-up on the PG pin."),
    ("C30,C38,C29", "100 nF / 10 uF capacitors on +5VA and VMID.", "Decoupling of the op-amp and of the VMID output."),
    ("C52,C46,C51,C56", "Decoupling capacitors on +5VA and VREF.", "Stabilize the reference/op-amp supply and the VREF pin."),
    ("C11,C12,C58", "10 uF / 100 nF capacitors on +5VA and VCC.", "Decoupling of AVDD and DVDD of the ADS1256."),
    ("R33", "0 ohm resistor between the input and the EN pin of U42.",
     "Ties EN to the input so the LDO is always enabled (can be removed if a separate EN is needed)."),
    ("C53", "10 uF capacitor on VREF_2V5 (output of U38).", "Reservoir/filter of the 2.5 V reference output."),
    ("C5,C6", "22 uF and 100 nF capacitors on VBAT.", "Decoupling of the TPS61175 input."),
]

R = lambda a, b: ["R%d" % i for i in range(a, b + 1)]
Cc = lambda *n: ["C%d" % i for i in n]
BLOCKS = [
    ("24 VDC input, input protection and 5 V rail (buck)",
     "The 24 VDC path from the connector to the 24 V to 5 V buck (U36).",
     ["F1", "D1", "L1", "L4", "D2", "Q3", "R26", "U36", "U40", "R25", "R27", "R86", "R87"] + Cc(1, 2, 3, 4, 59, 60, 61, 69, 70, 72, 73)),
    ("Power connector J1, battery input and external 5 V",
     "Power connector, battery input protection and switch, and the external 5 V path.",
     ["J1", "F2", "Q2", "R1", "D7"]),
    ("Input protection (battery load switch)", "Battery load switch to the VBAT rail.", ["U14"]),
    ("5 V rail (power-path mux)", "Selects the 5 V source between 5VBUCK and 5VBOOST.",
     ["U13", "R12", "R13", "R14"] + Cc(16, 17, 18)),
    ("5 V rail (battery boost to 24 V)", "Boosts the battery to about 24 V as a backup of the +24V rail.",
     ["U1", "L5", "D12", "D13"] + R(2, 7) + Cc(5, 6, 7, 8, 9, 10)),
    ("5 V rail (battery boost to 5 V)", "Boosts the battery to 5VBOOST.",
     ["U41", "L2", "R30", "R34", "R40", "R89", "R90"] + Cc(31, 36, 37, 64, 67, 68, 71, 74, 75, 76, 77)),
    ("3.3 V rail (5 V to 3.3 V buck)", "Buck that generates the 3.3 V VCC rail.", ["U43", "L3", "R23"] + Cc(35, 39, 40)),
    ("3.3 V rail (always-on LDO)", "The 3V3AON LDO and its source selection.", ["U42", "D3", "D10", "R33", "C62", "C63"]),
    ("3.3 V rail (TPL5010 timer)", "Nano-power timer/watchdog and its interval selector.",
     ["U46", "R35", "R36", "R37", "R38", "R39", "R92", "C26"]),
    ("3.3 V rail (ENA latch)", "ENA latch flip-flop and open-drain inverter.", ["U51", "U15", "R21", "R22", "C27", "C28"]),
    ("3.3 V rail (supervisor)", "Voltage supervisor of 3V3AON.", ["U16", "R15", "C19"]),
    ("ESP32-S3", "Main microcontroller with reset, boot, LED and I2C pull-ups.",
     ["U49", "R16", "R17", "R18", "R19", "R20", "R24", "R31", "R32", "SW1", "LED1"] + Cc(20, 21, 22, 23, 32)),
    ("ESP32-S3 (USB and programming)", "USB connector, ESD protection, CH340C and auto-reset.",
     ["USB1", "D4", "D5", "D11", "U48", "Q1", "R96", "C24", "C34"]),
    ("ADC", "ADS1256 with its input filters, clock and decoupling.",
     ["U35", "U39", "R8", "R9", "R10", "R73", "R75"] + R(65, 72) + Cc(11, 12, 41, 42, 43, 44, 45, 47, 48, 49, 50, 57, 58)),
    ("ADC (voltage reference)", "2.5 V reference and VREF buffer.",
     ["U38", "U2", "R74", "R76"] + Cc(46, 51, 52, 53, 54, 55, 56)),
    ("MQ sensor analog circuitry (+5VA)", "Analog +5VA supply filter.", ["L6", "C80", "C81"]),
    ("MQ sensor analog circuitry (VMID)", "Generator of the VMID bias of about 2.5 V.", ["U3", "R11", "R28", "R29"] + Cc(13, 29, 30, 38)),
    ("MQ heater supply and sensor (one connector)", "One sensor module connector as an example of every pin function.", ["H2"]),
    ("MQ heater supply and sensor (eight connectors)", "The eight sensor module connectors H1-H8.", ["H%d" % i for i in range(1, 9)]),
    ("Sensor interface (I2C mux)", "I2C multiplexer for the eight sensor modules.", ["U33", "R77", "C65", "C66"]),
    ("Sensor interface (enable expander)", "I/O expander that enables the sensor modules.", ["U12", "C15"]),
    ("Temperature and humidity sensor", "Environment sensor inside the board.", ["U44", "C14"]),
    ("LoRa", "LoRa module and antenna connector.", ["U45", "G1", "C25", "C33"]),
    ("Fan driver", "5 V fan driver.", ["J3", "Q5", "R42", "R43", "D9", "C78", "C79"]),
    ("LED / buzzer driver (alarm)", "24 V alarm output driver.", ["J2", "Q4", "R94", "R41", "D8", "C84", "C85"]),
    ("RS-485 / Modbus", "RS-485 transceiver, TVS protection and connector.", ["U47", "D6", "J4", "C87"]),
]


def callouts_for(parts):
    left, co = list(parts), []
    for spec, apa, fungsi in ALL:
        ds = [d for d in expand(spec) if d in left]
        if ds:
            co.append(dict(parts=ds, apa=apa, fungsi=fungsi))
            left = [d for d in left if d not in ds]
    return co, left
