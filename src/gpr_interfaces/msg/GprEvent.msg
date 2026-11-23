
# Event generated during API-controlled GPR acquisition.
# Published by gpr_api_node on /gpr/measurement_events.
#
# Events should be recorded together with other sensor topics
# in a ROS 2 bag for subsequent synchronization analysis.

# ROS timestamp at which the wrapper registered the event.
# frame_id is left empty because this is not spatial data.
std_msgs/Header header

# Event types.
uint8 MEASUREMENT_STARTED=1
uint8 MEASUREMENT_STOPPED=2
uint8 LINE_STARTED=3
uint8 LINE_STOPPED=4
uint8 LINE_PAUSED=5
uint8 LINE_RESUMED=6
uint8 EXPORT_STARTED=7
uint8 EXPORT_COMPLETED=8
uint8 ERROR=9

# Event identification.
uint8 event_type

# Measurement and line identification.
# Empty measurement_name or zero line_index indicates unavailable data.
string measurement_name
uint32 line_index

# Result of the corresponding API operation.
bool success

# Time information from the ROS clock.
# request_start and response_received bracket the HTTP operation.
builtin_interfaces/Time request_start
builtin_interfaces/Time response_received

# Timestamp reported by the GP API, if available.
# Stored as Unix epoch milliseconds, matching clientStartTimestamp.
# Zero indicates that no valid API timestamp was provided.
int64 api_timestamp_ms

# Whether api_timestamp_ms contains a valid timestamp.
bool has_api_timestamp

# Optional event description or error message.
string message
