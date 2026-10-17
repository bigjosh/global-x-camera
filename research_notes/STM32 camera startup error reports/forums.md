# STM32N6 CSI D-PHY forum reports

Research date: October 17, 2026. Read-only public-source review; no hardware activity or outreach. Explicit publication dates take precedence over the forums' inconsistent relative-age labels. Scope: reported D-PHY control/state-sequence errors, especially `0x8000`, rather than every camera bring-up problem.

## Has anyone reported our error on comparable hardware?

### Takeaway

Yes: an ST forum contains exact `0x8000` callbacks on an STM32N6570-DK, and another reports a CSI line callback on a Nucleo plus the closely related VD66GY camera. Neither establishes the same electrical cause as our good-frame startup event.

### Cited Findings

- **Exact error class:** STM32N6570-DK/IMX335 user Kamurasi-Jordan-Arthur reported `0x8000`, October 31, 2025. ST employee Ch_JE's November 3 reply associates nonblocking startup synchronization errors with camera-after-CSI initialization; it does not guarantee benign ECTRL behavior universally. — [Full thread](https://community.st.com/stm32-mcus-embedded-software-32/dcmipp-silient-failure-158741)
- **Closest board/sensor family:** *Still getting CSI LineError DataLane=1 when interfacing and STEVAL-66GYMAI1 with a nucelo N657 board*, posted by **whoami**, April 12, 2026. The reporter gets no real image data. **FBL, ST Technical Moderator**, replied April 15 that the attached project did not compile and recommended reducing it to a minimal camera example, treating integration as the leading suspect. The fetched page contains only that one reply and no confirmed fix. The HTML text does not expose a hexadecimal error code; the attached screenshot was not inspected, so do not claim this report proves `0x8000`. `DataLane=1` is a callback value, not proof of physical lane 1: our HAL uses enum 1 for physical lane 0. — [Full thread](https://community.st.com/stm32-mcus-products-25/still-getting-csi-lineerror-datalane-1-when-interfacing-and-steval-66gymai1-with-a-nucelo-n657-board-164672)
- The reporter's same-day request for reference code links back to the above unresolved thread; it is not an independent reproduction or solution. — [Follow-up request](https://community.st.com/edge-ai-134/interfacing-a-camera-with-nucelo-n657-164677)

### Inferences

- Startup timing and image integrity must be evaluated separately; the linked reports do not establish our electrical cause.
- A line callback alone is insufficient to compare physical lane, exact error, timing or corruption. The Nucleo report lacks those details. — [Nucleo report](https://community.st.com/stm32-mcus-products-25/still-getting-csi-lineerror-datalane-1-when-interfacing-and-steval-66gymai1-with-a-nucelo-n657-board-164672)

### Gaps

- No first-hand public report located specifically names CAM-6G3-073CLR, VD56G3 revision 0x3110 and a single pre-exposure ECTRLDL1F with intact first-frame payload.
- No source found gives an exact wave transition or universal ignore policy for that configuration.

## Which reported fixes are confirmed, and which are different problems?

### Takeaway

There are reporter-confirmed improvements, but they address different failure modes. None is a demonstrated cure for our repeatable startup-only lane error.

### Cited Findings

- **XS9950 transmitter clock mode:** zhangzyem reported N6 lane-control interrupts July 8, 2025, then successful reception with transmitter non-continuous clock July 10. Another participant suggested LP/HS and bitrate checks; staff status was unverified. The author's April 28, 2026 universal clock-mode speculation is unsupported. The page remains unresolved. Direct retrieval timed out; search returned the original post and four dated replies. — [Indexed Chinese thread](https://shequ.stmicroelectronics.cn/thread-835197-1-1.html)
- **IMX219 lane/rate configuration:** **EmbeddedChris**, August 26, 2025, reported both lane-control flags immediately on stream enable and no image after adapting the IMX335 driver. **KDJEM.1, ST Employee**, September 15, recommended the IMX219's two-lane clock configuration and 912 Mbps D-PHY setting. This response is marked accepted, but the visible replies contain no reporter measurement establishing that the flags disappeared. It is a configuration recommendation for a different sensor, not a general N6 ECTRL workaround. — [Full thread](https://community.st.com/stm32-mcus-products-25/stm32n6-imx219-camera-156159)
- **Missing IRQ/RIF, not startup ECTRL:** In *STM32N6 CSI-2: No frame lock*, **edenraf** reported no frames and supposedly no errors with a Sony 12 MP continuous-clock, one-lane setup. On June 26, 2026, the author confirmed that enabling CSI global interrupts and DCMIPP RIF made capture work. The raw status `0x76101000` printed earlier actually includes bit 12 under our RM interpretation, despite the author's zero-errors description; do not treat the author's interpretation as authoritative register decoding. The fix establishes image capture, not elimination of our particular startup event. — [Full thread](https://community.st.com/stm32-mcus-products-25/stm32n6-csi-2-no-frame-lock-166099)
- **Continuous-clock counterexample:** **abhinav-singh**, June 9, 2026, reported an AR0144CS gated-clock failure while saying a Sony IMX708 continuous-clock setup on the same N657 receiver captured full frames. **edenraf** later confirmed the separate IRQ/RIF fix on June 26. This contradicts treating the Chinese reporter's speculation as a general continuous-clock prohibition. — [Related clock-mode discussion](https://community.st.com/stm32-mcus-products-25/stm32n6-dcmipp-csi-2-d-phy-does-it-support-non-continuous-gated-clock-clock-lane-never-locks-actclf-0-with-a-streaming-sensor-165957)
- The IMX335 author's June 24, 2026 resolution concerns RIF, memory and throughput; no before/after lane trace is supplied. — [Resolution reply](https://community.st.com/stm32-mcus-embedded-software-32/dcmipp-silient-failure-158741)

### Inferences

- A fix that restores images does not automatically clear a startup flag. The cited threads often mix peripheral initialization, memory routing and PHY errors.
- Our existing non-continuous-clock experiment is the relevant local test; the XS9950 anecdote is not a reason to claim that change will fix our sensor. — [XS9950 report](https://shequ.stmicroelectronics.cn/thread-835197-1-1.html)

### Gaps

- None of these reports includes a first-exposure timestamp, cumulative raw error history and payload CRC/ECC evidence comparable to our harness.
- No public confirmed fix was located for a recurring but non-corrupting VD56G3/N6 startup ECTRL flag.

## Is startup sequencing or a documentation defect discussed publicly?

### Takeaway

The strongest direct startup advice is Ch_JE's forum response above. Separate ST documentation corrections exist, but they should not be promoted into an explanation for our event.

### Cited Findings

- **DLD register wording:** **pyven-dr**, August 3, 2026, asked why RM0486 described DLD opposite to the HAL setting. **FBL, ST Technical Moderator**, replied August 6 that HAL's DLD=1 was intentional and that the RM wording should be clarified; ST filed internal ticket **CDM0064937**. This is a vendor-confirmed documentation issue, not a confirmed ECTRL cause. Avoid blindly changing DLD to zero based on the old description. — [ST clarification](https://community.st.com/stm32-mcus-products-25/csi-pfcr-dld-bit-description-contradicts-hal-implementation-167440)
- ST's CubeMX 6.14.x errata documents omitted CSI clock and interrupt initialization in generated N6 projects and identifies issue **203685** as fixed in 6.14.1. This helps explain some no-capture examples; it does not describe an unavoidable startup lane-state error. — [Official CubeMX errata](https://wiki.st.com/stm32mcu/wiki/STM32CubeMX_errata_6.14.x)

### Inferences

- Changing receiver-enable timing must preserve the first frame and active diagnostics; suppression alone is not a repair.

### Gaps

- This forum-focused review did not recover an application-note procedure promising elimination of the exact event. The parallel official-document review should establish the current RM, errata and AN6211 coverage.
- No external contact was made; internal ticket CDM0064937 is reported by ST publicly, not accessible here for independent status checking.
