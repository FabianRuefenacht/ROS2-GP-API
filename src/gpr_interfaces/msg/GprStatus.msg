
# GP8000 / GP8100 / GP8800 device and API status.
# All fields describe the most recently polled state.

# Time at which the wrapper completed the status query.
# frame_id is left empty because this is not spatial data.
std_msgs/Header header

# Communication status.
bool api_reachable
bool probe_connected

# Device information.
# Empty strings indicate unavailable information.
string device_name
string serial_number
string firmware_version
string hardware_revision

# Battery information.
# battery_percentage = -1 indicates unavailable information.
# Values from 0 to 100 represent percent.
int16 battery_percentage
string battery_health

# API contract information.
# Empty strings indicate unavailable information.
string contract_name
string contract_expiration_date

# Current GP application screen (e.g. HOME, MEASUREMENT, OTHER).
# Empty string indicates unavailable information.
string app_screen

# Most recent communication or API error.
# Empty string indicates no current reported error.
string last_error
