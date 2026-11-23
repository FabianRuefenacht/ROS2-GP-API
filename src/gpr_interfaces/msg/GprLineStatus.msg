
# Current GPR measurement line status.
# Published by gpr_api_node on /gpr/line_status.

# Time at which the wrapper retrieved the line information.
# frame_id is left empty because this is not spatial data.
std_msgs/Header header

# Measurement identification.
# Empty string indicates unavailable information.
string measurement_name

# Line identification.
# Index as reported by the GP API.
uint32 line_index

# Line acquisition state.
# started remains true after a line has been stopped.
bool started
bool finished

# True when the line has started but has not yet finished.
bool recording

# Number of acquired A-scans in the current line.
uint32 scan_count

# Measurement length as reported by the GP API, in metres.
# For TIMED acquisition, this is not necessarily the travelled distance.
float32 reported_length_m

# Whether the line information is currently available.
bool valid
