"""'What is this / what does it do' explanations (English) for the GLD V4 main-PCB schematic figures.

Every explanation is derived from the EasyEDA netlist and the part numbers. Anything the netlist alone cannot
prove is worded as 'to be confirmed'.
"""

SHEETS = [
    dict(groups=[
        dict(callouts=[
            ("J1", "Power connector, 2x3 pins (J1).",
             "The only power entry from outside: pin 6 = 24V+, pin 5 = 24V-, pin 4 = 5VEXT (external 5 V), pins 3 and 1 = GND, "
             "pin 2 = battery input (goes to F2)."),
            ("F1", "Resettable PTC fuse MINISMDC260F/16-2 (2.6 A hold).",
             "Opens on a short circuit or overload on the 24 V line and recovers by itself. Note: the /16 suffix in the part "
             "number usually means a 16 V voltage rating - to be confirmed against the datasheet because this line is 24 V."),
            ("D1", "TVS diode SMBJ33A (33 V standoff).",
             "Clips voltage surges/transients between the 24 V line after F1 and 24V-, so the circuitry behind it is not damaged."),
            ("L1", "Common-mode choke ACM7060-301-2PL (4 pins).",
             "Suppresses common-mode noise on the 24V+ / 24V- pair. Winding 1-4 carries 24V+, winding 2-3 carries the return side "
             "(24V- to GND)."),
            ("L4", "Ferrite bead MPZ2012S101A (100 ohm @ 100 MHz).",
             "High-frequency noise filter in series with the +24V line before it enters the internal rail."),
        ]),
        dict(callouts=[
            ("Q3", "P-channel MOSFET SI7465DP (source on +24V, drain toward the buck input).",
             "Passes +24V to the 5 V converter. Its source is on the +24V side and its drain on the load side; this orientation "
             "should be verified if the part is meant to provide reverse-polarity protection."),
            ("D2,R26", "12 V zener (LBZT52C12) and a 100k resistor to GND.",
             "R26 pulls the gate to GND so Q3 turns on. D2 limits the gate-source voltage of Q3 to 12 V so the gate is not "
             "damaged by 24 V."),
        ]),
        dict(callouts=[
            ("F2", "PTC fuse MINISMDC260F/16-2.", "Overcurrent protection for the battery input at J1 pin 2."),
            ("Q2,R1", "P-MOSFET AO4407 with a 100k gate resistor to GND.",
             "Passes the battery to net VBAT_IN. R1 turns Q2 on through the gate to GND. The source-on-battery orientation "
             "should be verified if the part is meant to provide reverse-polarity protection."),
            ("U14", "Load switch TPS22964C (VIN = VBAT_IN, VOUT = VBAT, ON = ENA).",
             "Connects/disconnects the battery to the whole VBAT rail (boost converters) according to the ENA signal from the "
             "power-latch circuit."),
            ("C5,C6", "22 uF and 100 nF capacitors on VBAT.", "Decoupling on the load-switch output."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("U36", "Synchronous buck IC LMR51450 (VIN up to 36 V).",
             "Step-down converter from 24 V to 5VBUCK. EN is tied to VIN (always on); the PG (power good) pin goes to the ESP32 "
             "as signal PG24."),
            ("U40", "4.7 uH inductor (GSSM06304R7M2AU).", "Buck energy-storage inductor between the SW node and 5VBUCK."),
            ("C59,C60,C61", "Input capacitors 10 uF/50 V x2 + 100 nF.", "Supply the pulsed input current of the buck."),
            ("C72,C73,C17", "Output capacitors 33 uF x2 + 10 uF.", "Smooth the 5VBUCK output voltage."),
            ("R27,R86", "FB voltage divider 100k / 19.1k.",
             "Sets the output: 0.8 V x (1 + 100/19.1) = about 5.0 V (calculated from the resistor values)."),
            ("R87,C70", "1k resistor in series with a 33 pF capacitor on FB.", "Feed-forward network for stability / transient response."),
            ("C69", "100 nF BOOT-SW capacitor.", "Bootstrap for the internal high-side MOSFET driver."),
            ("R25", "100k pull-up to VCC on PG24.", "Gives a 3.3 V logic level for the power-good signal read by the ESP32 (IO47)."),
        ]),
        dict(callouts=[
            ("U13", "Power mux TPS2116 (VIN1 = 5VBUCK, VIN2 = 5VBOOST, VOUT = +5V).",
             "Automatically selects the 5 V source with priority on 5VBUCK (MODE is tied to 5VBUCK) and switches to 5VBOOST when "
             "5VBUCK is lost. The ST pin goes to the ESP32 as ST_P (source status)."),
            ("R13,R14", "16k / 4.99k divider on PR1.", "Sets the voltage threshold at which 5VBUCK is considered valid before the mux gives it priority."),
            ("C16,C79,C78,C65", "10 uF and 100 nF capacitors on +5V.", "Decoupling of the +5V rail."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("U1", "Boost converter TPS61175 (VIN = VBAT).",
             "Boosts the battery voltage to about 24 V. Enabled by the EN_BOOST signal from the ESP32 (IO15)."),
            ("L5,D12", "10 uH inductor and SK36 Schottky diode.", "Boost inductor and rectifier diode from the SW node to the boost output."),
            ("D13", "SS54 Schottky diode from the boost output to +24V.",
             "ORs the boost output onto the +24V rail without back-feeding into the boost converter."),
            ("R3,R2", "FB divider 187k / 10k.", "Sets the output to about 1.229 V x (1 + 187/10) = 24 V (calculated from the resistor values)."),
            ("R4,R5", "100k pull-down and 1k series resistor on EN.", "Keep the boost off while EN_BOOST is inactive; the 1k limits current from the GPIO."),
            ("R6,R7,C7,C8", "82k FREQ resistor, 10k/22 nF COMP network, 47 nF soft-start.",
             "Set the switching frequency, loop compensation and soft-start."),
            ("C9,C10", "Output capacitors 22 uF/35 V and 10 uF/50 V.", "Boost output filter."),
        ]),
        dict(callouts=[
            ("U41", "Boost converter TPS61088 (VIN = VBAT, VOUT = 5VBOOST, EN = ENA).",
             "Generates 5 V from the battery. Active when the ENA signal from the power-latch circuit is high."),
            ("L2", "2.2 uH inductor.", "Boost inductor between VBAT and the SW node."),
            ("R90,R89", "FB divider 189k / 56k.", "Sets the output to about 1.204 V x (1 + 189/56) = 5.3 V (calculated from the resistor values)."),
            ("R34", "255k resistor on FSW.", "Sets the switching frequency."),
            ("R30", "100k resistor on ILIM.", "Sets the peak current limit."),
            ("C74,C75,C31", "Internal VCC capacitor, soft-start capacitor and bootstrap capacitor.", "Support parts for the IC."),
            ("R40,C76,C77", "COMP compensation network.", "Stabilizes the boost control loop."),
            ("C64,C67,C68,C71,C18,C36,C37", "VBAT input and 5VBOOST output capacitors.", "Decoupling on the input and output sides of the boost."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("U43", "Buck TPS62162 (VIN = +5V, EN = +5V, VOS = VCC).",
             "Steps +5V down to 3.3 V (fixed-voltage version, FB to GND). Always on because EN is tied to +5V."),
            ("L3", "2.2 uH inductor.", "Buck inductor from the SW node to VCC."),
            ("C32,C33,C34,C39,C40", "10 uF / 22 uF capacitors on VCC.", "Bulk capacitors of the 3.3 V output."),
            ("C14,C15,C20,C24,C25,C58,C87", "100 nF capacitors on VCC.", "Decoupling close to each 3.3 V IC."),
            ("R23", "100k pull-up on PG.", "PG is not connected to any other component in this netlist (pull-up only)."),
        ]),
        dict(callouts=[
            ("D3,D10", "Dual diode BAT54C (common cathode).",
             "D3 ORs VBAT_IN and 5VBUCK; D10 ORs 5VEXT and VBUS (USB). The result is the net that feeds the LDO input."),
            ("U42", "LDO TPS7A0233 (3.3 V, very low quiescent current).",
             "Converts the available source into 3V3AON. EN is pulled to the input through R33 (0 ohm), so it is always enabled."),
            ("C62,C63,C19,C26,C27,C28", "22 uF and 100 nF input/output capacitors.", "Decoupling of the LDO and the 3V3AON rail."),
        ]),
        dict(callouts=[
            ("U46", "Nano-power timer TPL5010.",
             "Generates periodic WAKE pulses and works as a watchdog: DONE from the ESP32 (IO17) signals that the firmware is "
             "still alive, RSTn goes to RST (ESP32 reset)."),
            ("R35,R36,R92,R37,R38,R39", "43k / 56k / 33k resistors to GND with three 0 ohm jumpers.",
             "Select the TPL5010 timer interval through the DELAY/M_RST pin (one 0 ohm jumper is fitted for the chosen interval)."),
            ("U15", "Open-drain inverter SN74LVC1G06.", "Turns WAKE from U46 into a pull-down on net PRE (R15 pull-up to 3V3AON)."),
            ("U51", "D flip-flop SN74AUP1G74 (CLK to GND, Q = ENA).",
             "Used as a latch: PRE low sets ENA, CLR low from the ESP32 (IO16) clears ENA. ENA controls U14 (load switch) and "
             "U41 (5 V boost)."),
            ("U16", "Voltage supervisor TPS3839K33 (threshold variant for a 3.3 V rail).", "RESET# output is connected to net PRE; supervises 3V3AON."),
            ("R15,R21,R22", "10k pull-ups to 3V3AON on PRE, CLR and the flip-flop D input.", "Keep the default logic levels."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("U49", "Module ESP32-S3-WROOM-1U-N16R8 (external antenna, 16 MB flash, 8 MB PSRAM).",
             "The brain of the GLD: reads the ADC (SPI_CS/DRDY/ADC_RST/PDOWN), controls the LoRa radio "
             "(LORA_SS/RST/BUSY/DIO1/TXEN/RXEN), I2C (SDA/SCL), RS-485 (TX2/RX2/DIR), alarm, fan, LED and boost, and reads "
             "BATMON, PG24, ST_P and CFG."),
            ("SW1,R18", "CFG button with a 10k pull-up.", "Configuration button: pulls CFG to GND when pressed."),
            ("R19,C21", "10k pull-up and 100 nF on IO0.", "Keep IO0 high (normal boot); Q1 pulls it low in download mode."),
            ("R20,C22", "10k pull-up and 100 nF on EN/RST.", "RC reset circuit for the ESP32; also driven by the TPL5010."),
            ("R32,R24,C23", "200k / 100k divider to BATMON with 100 nF.",
             "Scales VBAT_IN down so the ESP32 ADC (IO4) can read it safely; the 1/3 ratio matches the firmware formula 'avg x 3'."),
        ]),
        dict(callouts=[
            ("USB1", "Micro-USB connector.", "Programming and serial port to the PC; VBUS also feeds the 3V3AON source OR-ing (3.3 V rail)."),
            ("D4,D5,D11", "ESD protection on D-, D+ and VBUS.", "Protects the USB lines from electrostatic discharge."),
            ("U48", "USB-UART bridge CH340C (VCC 3.3 V).", "Translates USB to the ESP32 UART0 (TXD/RXD)."),
            ("Q1", "Dual NPN with resistors, UMH3N.", "Classic auto-reset circuit: DTR/RTS from the CH340 drive IO0 and RST of the ESP32 during upload."),
            ("R96", "470 ohm resistor.", "Series resistor on the TXD line from the ESP32 to RXD of the CH340C."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("U35", "Delta-sigma ADC ADS1256 (8 channels, 24 bit).",
             "Converts the AI0-AI7 voltages to digital data. AVDD = +5VA, DVDD = VCC, VREFP = VREF, VREFN and AINCOM = GND. "
             "Controlled over SPI (CS, SCLK, DIN, DOUT) + DRDY."),
            ("U39,C45,C57", "4-pin SMD crystal with two 20 pF capacitors.", "ADC clock source (8 MHz according to the U39 label on the schematic)."),
            ("R8,R9,R10", "22 ohm series resistors on MISO, MOSI, SCK.", "Damp ringing/EMI on the SPI lines to the ADC."),
            ("R73,R75", "10k pull-ups on RESET and SYNC/PDWN.", "Keep the ADC active by default; the ESP32 can pull them low (ADC_RST, PDOWN)."),
        ]),
        dict(callouts=[
            ("U38", "Voltage reference ADR03 (2.5 V).", "Precision VREF source for the ADC (VIN = +5VA)."),
            ("R76,C54,C55", "1k resistor and 2x 100 nF.", "Low-pass filter of the reference noise before the buffer."),
            ("U2", "Op-amp OPA320 as a buffer (voltage follower).", "Buffers VREF so it is stiff against the load and the switching current of the ADC."),
            ("R74,C56,C51", "22 ohm resistor, 22 uF tantalum, 100 nF.", "Isolation and reservoir capacitors on the ADC VREFP pin."),
        ]),
        dict(callouts=[
            ("L6", "60 ohm ferrite bead.", "Separates digital noise from the analog +5VA rail."),
            ("C11,C80,C12,C30,C46,C52,C81", "10 uF and 100 nF capacitors on +5VA.", "Decoupling for the ADC, op-amps and reference."),
        ]),
        dict(callouts=[
            ("R28,R29,C13", "10k / 10k divider and 100 nF.", "Creates half of +5VA (about 2.5 V)."),
            ("U3", "Op-amp OPA320 as a buffer.", "Buffers the mid-voltage into a low-impedance VMID source."),
            ("R11,C29,C38", "49.9 ohm resistor and capacitors.",
             "Isolate the buffer output and keep it stable with capacitive loads; VMID goes to pin 8 of every sensor connector."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("H1,H2,H3,H4,H5,H6,H7,H8", "Sensor module connectors (H1..H8).",
             "Each connector carries: pin 2 = +5V (module/heater supply), pin 8 = VMID (bias), pin 3 = AINx (analog signal to "
             "the ADC), pins 4/6 = SCLx/SDAx (I2C channel from the mux), pin 7 = ENx (module enable), pins 1/5 = GND. "
             "The heater switch and sensor load resistor are not on this board (assumed to be on the sensor module; to be confirmed)."),
        ]),
        dict(callouts=[
            ("R65,R66,R67,R68,R69,R70,R71,R72,C41,C42,C43,C44,C47,C48,C49,C50",
             "49.9 ohm series resistor and 100 nF capacitor to GND on every channel.",
             "About 32 kHz low-pass (calculated) that suppresses noise and protects the ADC inputs; AINx from the connector "
             "becomes AIx at the ADS1256."),
        ]),
        dict(callouts=[
            ("U33", "I2C multiplexer TCA9548A (8 channels).",
             "Splits the main I2C bus into eight channels SDA0-7/SCL0-7 toward the modules; RESET# is held high by R77."),
            ("U12", "I/O expander PCF8574.", "Outputs P0-P7 become EN0-EN7 to enable the sensor modules one by one."),
            ("U44", "Temperature/humidity sensor SHT40.", "Measures temperature and humidity inside the board on the main I2C bus."),
            ("R16,R17", "10k I2C pull-ups to VCC.", "Pull-ups for SDA and SCL."),
            ("R77,C66", "10k pull-up and 100 nF on RSTA.", "Keep the mux from being reset unless intended."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("U45", "LoRa module E22-900MM22S (SX126x class, 900 MHz).",
             "Interface: SPI (SPI_MISO/MOSI/SCK + LORA_SS), LORA_RST, LORA_BUSY, DIO1, and TXEN/RXEN for the TX/RX switch. "
             "Supplied from VCC (3.3 V)."),
            ("G1", "U.FL antenna connector.", "Connection point of the antenna cable to the ANT pin of the LoRa module."),
        ]),
    ]),
    dict(groups=[
        dict(callouts=[
            ("Q4", "N-MOSFET AO3400A as a low-side switch.", "Turns on the load at J2 when ALARM is high; its source goes to GND."),
            ("R94,R41", "100 ohm gate resistor and 100k pull-down.", "R94 limits the gate charging current; R41 keeps Q4 off while the GPIO is not yet active."),
            ("D8", "SS14 flyback diode.", "Clamps the inductive spike of the load at J2 to +24V."),
            ("J2", "Alarm load connector (pin 1 = +24V, pin 2 = Q4 drain).", "Connection point of the 24 V alarm load (load type to be confirmed)."),
        ]),
        dict(callouts=[
            ("Q5", "N-MOSFET AO3400A as a low-side switch.", "Turns on the fan at J3 when DC_FAN is high."),
            ("R42,R43", "100 ohm gate resistor and 100k pull-down.", "Gate current limiter and default-off holder."),
            ("D9", "SS14 flyback diode.", "Clamps the inductive spike of the fan to +5V."),
            ("J3", "Fan connector (pin 1 = +5V, pin 2 = Q5 drain).", "Connection point of the 5 V fan."),
        ]),
        dict(callouts=[
            ("LED1,R31", "0603 LED (19-217/BHC-ZL1M2RY/3T) with a 1k resistor.",
             "Lights when the ESP32 pulls the LED pin (IO6) to GND; anode to VCC (active-low)."),
        ]),
        dict(callouts=[
            ("U47", "RS-485 transceiver THVD1410 (3.3 V).",
             "Converts the TX2/RX2 UART of the ESP32 into the differential A/B signal; direction is controlled by DIR "
             "(drives RE# and DE together)."),
            ("D6", "TVS SM712 (asymmetric, made for RS-485).", "Protects pins A/B against surges and ESD."),
            ("J4", "RS-485 connector (A, B).", "Bus connection terminal. There is no 120 ohm termination or bias resistor on this schematic."),
        ]),
    ]),
]

PROTECTION_ROWS = [
    ("F1", "MINISMDC260F/16-2", "In series with 24V+ after J1", "Overcurrent on the 24 V line (PTC)"),
    ("D1", "SMBJ33A", "After F1, to 24V-", "Voltage surges on the 24 V line (TVS)"),
    ("L1", "ACM7060-301-2PL", "In series with 24V+ and return", "Common-mode noise"),
    ("L4", "MPZ2012S101AT000", "In series with +24V", "High-frequency noise (ferrite)"),
    ("D2 / R26", "LBZT52C12T1G / 100k", "Gate of Q3", "12 V Vgs limit for Q3"),
    ("Q3", "SI7465DP-T1-GE3", "+24V to buck input", "High-side switch (orientation to be verified)"),
    ("F2", "MINISMDC260F/16-2", "In series with battery input J1.2", "Battery overcurrent (PTC)"),
    ("Q2 / R1", "AO4407 / 100k", "Battery to VBAT_IN", "High-side switch (orientation to be verified)"),
    ("D7 / D13", "SS54", "5VEXT to +5V; boost to +24V", "Reverse-current blocking (OR-ing)"),
    ("D3 / D10", "BAT54C", "Source of U42 (3V3AON)", "OR-ing of battery / 5VBUCK / 5VEXT / VBUS"),
    ("D8 / D9", "SS14", "Loads J2 and J3", "Flyback for inductive loads"),
    ("D4 / D5 / D11", "LESD5D5.0CT1G", "D-, D+, VBUS", "USB ESD"),
    ("D6", "SM712", "RS-485 A/B", "RS-485 line TVS"),
    ("L6", "GZ1005D600TF", "+5V to +5VA", "Noise isolation of the analog supply"),
]

GROUNDING_NOTES = [
    "The whole circuit uses a single GND net. There is no separate AGND or chassis ground net in this netlist; the AGND/PGND/DGND pins of all ICs go into net GND.",
    "The 24 V return (J1 pin 5, 24V-) enters GND through a winding of common-mode choke L1 (pin 2 to pin 3). J1 pins 1 and 3 also go directly to GND.",
    "The analog supply +5VA is separated from +5V by ferrite bead L6; analog and digital ground are joined at GND.",
    "The shell/EP pads of USB1 and the GND pads of the module/antenna connector (G1) are connected to GND.",
    "A single connection point to chassis ground or PE is not drawn on the source schematic (to be confirmed against the enclosure/ATEX design).",
]
