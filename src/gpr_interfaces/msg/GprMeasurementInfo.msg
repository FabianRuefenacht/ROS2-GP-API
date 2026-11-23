
# Current GPR measurement information and acquisition settings.
# Published by gpr_api_node on /gpr/measurement_info.

# Time at which the wrapper retrieved the measurement information.
# frame_id is left empty because this is not spatial data.
std_msgs/Header header

# Measurement identification.
# Empty strings indicate unavailable information.
string measurement_name
string measurement_type

# Whether the current measurement contains recorded data.
bool has_data

# Acquisition settings.
# Expected modes: FIXED_STEP, TIMED, EXTERNAL.
string trigger_mode

# Expected resolutions: MAX_SPEED, MAX_DEPTH.
string resolution

# Measurement unit as reported by the GP API (e.g. METRIC).
string unit

# Time-triggered acquisition frequency in scans per second (Hz).
# Only valid when trigger_mode == TIMED.
# NaN indicates not applicable or unavailable.
float32 scan_frequency_hz

# Fixed-step acquisition parameter as reported by the GP API.
# Only valid when trigger_mode == FIXED_STEP.
# NaN indicates not applicable or unavailable.
float32 repetition_rate

# Whether the measurement information is currently available.
bool valid
