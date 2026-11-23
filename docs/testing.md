# Validation and tests

This repository is a **master's-thesis research prototype**. Testing is intentionally limited to the core acquisition workflow.

## Software checks

- ROS 2 Humble build completed for `gpr_interfaces` and `gpr_ros2` on a Jetson (Ubuntu 22.04).
- All nine custom interfaces generated successfully; API and export nodes, six services, four topics and the export action were discoverable through ROS 2.
- Four lightweight HTTP-client tests passed: probe read, TIMED presets, start-line timestamp preservation and HTTP error handling.

## Physical GP8000 end-to-end validation — 23 November 2026

**Tested hardware:** Proceq GP8000, firmware **5.7.12**, GP API + Manual contract. **Mode:** `LINE_SCAN` / `TIMED`, 1 Hz, `MAX_SPEED`, `METRIC`.

Successful sequence: connect → start measurement → set presets → start line → stop line → raw export → stop measurement. The line-status topic reported **52 scans**, `finished=true` and `recording=false`. The export action returned `SUCCEEDED`, saved a **68,574-byte ZIP**, validated it and extracted a **84,096-byte SEG-Y** file together with JSON and CSV metadata.

The SEG-Y byte count is consistent with 52 traces if the file uses the previously observed GP8000 trace layout (3,600-byte file header, 240-byte trace header and 327 float32 samples per trace). This is a structural consistency check, not an independent trace-header validation.

After a code correction, the common launch again exposed both nodes, all six services, four topics and the export action; connected-device status reported `api_reachable=true` and `probe_connected=true`. The disconnected-probe HTTP-403 path was not independently retested after the correction.

## Not validated

- GP8100 and GP8800 device operation
- A complete `FIXED_STEP` measurement or `EXTERNAL` trigger mode
- Long-duration reliability and locked-iPad operation
- Absolute timing accuracy or synchronization between GP API and ROS host clocks

Additional validation belongs to the field-acquisition and data-analysis workflow, not an extensive production-style test suite.
