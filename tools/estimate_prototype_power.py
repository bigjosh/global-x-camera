"""Illustrative energy model; assumptions and sources: docs/power/power-cost-comparison.md.

Not a measured budget or a worst-case bound. All powers are watts, currents
amperes, durations seconds, and energies joules. Run with Python 3; no packages.
"""

from dataclasses import dataclass
from math import ceil


@dataclass(frozen=True)
class Phase:
    name: str
    seconds: float
    core_w: float
    main_a: float
    aon_a: float
    analog_a: float
    nor_a: float
    nand_a: float
    camera_active: bool = False


PHASES = (
    Phase("Capture", 0.100, .085, .002, .00045, .005, .010, .0001, True),
    Phase("Save/readback", 0.750, .055, .002, .00045, .005, .001, .020),
    Phase("Shutdown", 0.010, .010, .0005, .0001, .0003, .0001, .0001),
)
CAMERA_ACTIVE_A = (.0085, .057, .0228)  # IO, digital core, analog
CAMERA_RESET_A = (.000013, .0021, .000038)


def battery_power(phase, architecture, debugger_a=0, aux_efficiency=.90,
                  ltc5_efficiency=.88, ltc3_efficiency=.86, power_led_enabled=True):
    """Return battery power and its input-referred components, without double counting."""
    custom = architecture == "custom"
    five_volts = architecture == "5V"
    bus_v = 5.0 if five_volts else 3.3
    ltc_efficiency = ltc5_efficiency if five_volts else ltc3_efficiency
    core_efficiency = .83 if five_volts else .86
    # AON is an independent input-fed LDO on the Nucleo. The custom case
    # budgets efficient conversion but still needs a compliant sequencing design.
    main = bus_v * phase.main_a
    aon = (1.8 / .90 if custom else bus_v) * phase.aon_a
    low_voltage_a = phase.analog_a + phase.nor_a + phase.nand_a
    if not custom:
        low_voltage_a += .000168  # Six TSZ122 buffer channels, typical.
    memory_analog = (1.8 / .90 if custom else 3.3) * low_voltage_a
    if custom:
        if phase.camera_active:
            io_a, core_a, analog_a = CAMERA_ACTIVE_A
            camera = 1.8 * (io_a + core_a) / .90 + 3.3 * analog_a + .002
        else:
            camera = 0.0  # Proposed complete gating after readout.
    else:
        currents = CAMERA_ACTIVE_A if phase.camera_active else CAMERA_RESET_A
        camera = 3.3 * sum(currents) + .002  # Oscillator/regulator allowance.
    ethernet = 0 if custom else 3.3 * .0032  # Firmware General Power-Down.
    # Input-side equivalent allowances, not device-characterized currents.
    misc_aux = .002
    regulator_overhead = .0005 if custom else .001
    power_led = 0 if custom or not power_led_enabled else bus_v * max(bus_v - 2.0, 0) / 820
    aux_conversion = aux_efficiency if five_volts else 1.0
    bus_components = {
        "MCU core": phase.core_w / core_efficiency,
        "Main IO + AON": main + aon,
        "1.8V loads": memory_analog / aux_conversion,
        "Camera": camera / aux_conversion,
        "Ethernet": ethernet / aux_conversion,
        "Other": misc_aux / aux_conversion + regulator_overhead + power_led,
        "ST-LINK": bus_v * debugger_a,
    }
    components = {key: value / ltc_efficiency for key, value in bus_components.items()}
    return sum(components.values()), components


def cycle(architecture, debugger_a=0, **kwargs):
    energy = 0.0
    components = {}
    powers = []
    for phase in PHASES:
        power, terms = battery_power(phase, architecture, debugger_a, **kwargs)
        powers.append(power)
        energy += power * phase.seconds
        for key, value in terms.items():
            components[key] = components.get(key, 0.0) + value * phase.seconds
    return energy, powers, components


def main():
    configurations = (
        ("Stock 5V (illustrative 30mA debugger)", "5V", .030),
        ("5V, debugger isolated", "5V", 0),
        ("Modified 3.3V, debugger isolated", "3V3", 0),
        ("Custom 3.3V", "custom", 0),
    )
    duration = sum(phase.seconds for phase in PHASES)
    for label, architecture, debugger_a in configurations:
        energy, powers, components = cycle(architecture, debugger_a)
        print(label)
        print(f"  Energy: {energy:.6f} J; average: {energy/duration:.6f} W")
        print("  Phase W: " + ", ".join(f"{p:.6f}" for p in powers))
        print("  Components mJ: " + ", ".join(f"{k}={v*1000:.3f}" for k, v in components.items()))
    stock, _, _ = cycle("5V", .030)
    isolated, _, _ = cycle("5V")
    modified, _, _ = cycle("3V3")
    custom, _, _ = cycle("custom")
    print(f"5V excess over modified: {100*(isolated/modified-1):.2f}%")
    print(f"Modified saving versus isolated 5V: {100*(1-modified/isolated):.2f}%")
    print(f"Modified saving versus stock: {100*(1-modified/stock):.2f}%")
    print(f"Custom saving versus stock: {100*(1-custom/stock):.2f}%")
    print(f"Custom saving versus modified: {100*(1-custom/modified):.2f}%")
    lean5 = cycle("5V", power_led_enabled=False)[0]
    lean3 = cycle("3V3", power_led_enabled=False)[0]
    print(f"No debugger or power LED: 5V={lean5:.6f}J 3.3V={lean3:.6f}J")
    print(f"Conversion change saving with LEDs absent: {100*(1-lean3/lean5):.2f}%")
    for current in (.015, .030, .050):
        print(f"Debugger sensitivity {current*1000:.0f}mA: {cycle('5V', current)[0]:.6f} J")
    # Illustrative converter sensitivity, not confidence limits. Vary the
    # unverified AUX efficiency and the LTC 3.3V efficiency relative to 5V.
    penalties = []
    for aux_efficiency in (.85, .90, .95):
        for ltc5_efficiency in (.85, .88, .92):
            for efficiency_delta in (.01, .02, .04):
                kwargs = dict(aux_efficiency=aux_efficiency,
                              ltc5_efficiency=ltc5_efficiency,
                              ltc3_efficiency=ltc5_efficiency-efficiency_delta)
                e5 = cycle("5V", **kwargs)[0]
                e3 = cycle("3V3", **kwargs)[0]
                penalties.append(100*(e5/e3-1))
    print(f"5V excess sensitivity: {min(penalties):.2f}% to {max(penalties):.2f}%")
    payload = 1124 * 1364 * 10 // 8
    pages = ceil(payload / 2048)
    for clock_hz in (100_000_000, 50_000_000):
        transfer_s = pages * 2048 * 8 / (4 * clock_hz)
        save_s = pages * 600e-6 + transfer_s
        readback_s = pages * 70e-6 + transfer_s
        print(f"NAND {clock_hz/1e6:.0f}MHz, {payload} bytes, {pages} pages: "
              f"save={save_s*1000:.3f}ms readback={readback_s*1000:.3f}ms "
              f"total={(save_s+readback_s)*1000:.3f}ms")


if __name__ == "__main__":
    main()
