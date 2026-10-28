"""Independent lane1-only ForceRx transformation; preserves the frozen v39 code."""
from build_raw10 import replace
import force_rx


def capture(text):
    text=force_rx.capture(text)
    text=replace(text,'(READY_GATE==5U?3U:0U)','2U')
    text=replace(text,'(READY_GATE==5U?force:0U)','CSI_PMCR_FRXMDL1')
    return text


def hal(text,treatment):
    if not treatment:raise ValueError('Lane1-only builder must request its treatment')
    return replace(text,'  /* Remove the force */\n  CLEAR_REG(csi_instance->PMCR);',
                   '  /* Independent lane1-only treatment: release data lane0\n'
                   '   * immediately; retain only FRXMDL1 until both STOP flags\n'
                   '   * are observed stable100us. Keep the control IRQ policy. */\n'
                   '  WRITE_REG(csi_instance->PMCR,CSI_PMCR_FRXMDL1);')
