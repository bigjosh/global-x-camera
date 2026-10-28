"""Shared, offline description of the RAW capture's PD12 observations."""
EVENTS = {
    1: "receiver_entry",
    2: "first_strobe_irq_observed",
    3: "first_frame_complete_irq_observed",
    4: "sd_initialization_begin",
    5: "sd_initialization_complete",
    6: "first_payload_submission",
    7: "padded_payload_ready",
    8: "full_slot_commit_complete",
    9: "sd_deinitialization_complete",
    10: "pre_standby_wfi",
}
LEGACY_PROTOCOL = dict(pin="PD12", idle_level=0, nominal_cpu_hz=400000000,
    pulse_high_cycles_per_id=200, nominal_high_us_per_id=.5,
    events={str(k):v for k,v in EVENTS.items()})
PHASE_PROTOCOL = dict(schema=2,pin="PD12",idle_level=0,nominal_cpu_hz=400000000,
    pulse_high_cycles_per_id=800,nominal_high_us_per_id=2.,
    pulse_width_tolerance_us=.4,events={str(k):v for k,v in EVENTS.items()})
APPROVED_PROTOCOLS=(LEGACY_PROTOCOL,PHASE_PROTOCOL)
# Sensor and storage phases overlap. They must not be sorted into one serial
# 1..10 list; the cold SD init can begin before the first STROBE interrupt.
PRECEDENCE = ((1,2),(2,3),(1,4),(4,5),(5,6),(6,7),(3,7),(7,8),(8,9),(9,10))
