# Temperature-read-before-configuration diagnostic

This v28 RAW8 trial inserts the documented standby temperature-read command immediately after BOOT reaches SW_STANDBY. It requires command acknowledgement, verifies the standby state and reads the temperature result before continuing the unchanged calibrated v24 image configuration. All waits are bounded; no calibration, OTP or undocumented bias register is modified.

The added operation took **1.83712 ms**, measured between external events 236 and 237. START completed at 20.09376 ms after NRST, the first exposure strobe began at **25.39168 ms**, and the first complete frame reached RAM at **47.24816 ms**. START-to-first-strobe remained **5.29792 ms**. Thus this tested attempt to prepare any shared analog circuitry before START added latency without shortening the observed sensor startup interval. It is not retained in the normal capture profile.

The root bench controller personally viewed a discernible LED panel. Firmware/host image-integrity statistics matched and the three measured rails passed discharge/restoration checks. The usual startup D-PHY state-sequence flag remained; no recorded CRC/ECC error appeared. The disabled-after-first-error interrupt remains a qualification limitation.

The archive retains unchanged timing, result and digital-trace files, programming/readback identities, manifests and exact source hashes. Identical source objects are referenced from the earlier v17-v24 archive. Images, full NOR content, analog streams and Saleae sessions are omitted. Visual inspection is a separate root-controller assertion; original pending-inspection fields are preserved in the raw result.
