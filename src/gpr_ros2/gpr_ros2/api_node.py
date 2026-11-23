"""ROS 2 services and status topics for the Screening Eagle GP API.

This synchronous prototype uses one executor thread. HTTP operations can block
callbacks until they finish; no automatic retries are performed for commands.
"""

import math
from typing import Callable

import rclpy
from rclpy.node import Node
from std_srvs.srv import Trigger

from gpr_interfaces.msg import (
    GprEvent,
    GprLineStatus,
    GprMeasurementInfo,
    GprStatus,
)
from gpr_interfaces.srv import Connect, SetPresets, StartLine, StartMeasurement

from .api_client import GprApiClient
from .exceptions import GprApiError, GprHttpError


class GprApiNode(Node):
    """Expose the GP application HTTP API through ROS 2 interfaces."""

    def __init__(self) -> None:
        super().__init__("gpr_api_node")

        self.declare_parameter("ipad_host", "")
        self.declare_parameter("probe_ip", "")
        self.declare_parameter("probe_serial", "")
        self.declare_parameter("ipad_port", 9000)
        self.declare_parameter("request_timeout_s", 10.0)
        self.declare_parameter("status_period_s", 2.0)

        host = str(self.get_parameter("ipad_host").value).strip()
        if not host:
            raise ValueError("ipad_host must be set via ROS parameters")
        port = self.get_parameter("ipad_port").value
        timeout = self.get_parameter("request_timeout_s").value
        period = float(self.get_parameter("status_period_s").value)
        if not math.isfinite(period) or period <= 0:
            raise ValueError("status_period_s must be a positive finite number")

        self.api = GprApiClient(host=host, port=port, timeout=timeout)
        self._measurement_name = ""
        self._line_index = 0
        self._paused = False
        self._last_screen = ""
        self._last_error = ""

        self.status_pub = self.create_publisher(GprStatus, "/gpr/status", 10)
        self.info_pub = self.create_publisher(
            GprMeasurementInfo, "/gpr/measurement_info", 10
        )
        self.line_pub = self.create_publisher(GprLineStatus, "/gpr/line_status", 10)
        self.event_pub = self.create_publisher(
            GprEvent, "/gpr/measurement_events", 10
        )

        self.create_service(Connect, "/gpr/connect", self._connect)
        self.create_service(
            StartMeasurement, "/gpr/start_measurement", self._start_measurement
        )
        self.create_service(SetPresets, "/gpr/set_presets", self._set_presets)
        self.create_service(StartLine, "/gpr/start_line", self._start_line)
        self.create_service(Trigger, "/gpr/stop_line", self._stop_line)
        self.create_service(Trigger, "/gpr/stop_measurement", self._stop_measurement)

        self.create_timer(period, self._poll_status)
        self.get_logger().info(f"GP API node ready (iPad: {host}:{port})")

    def _now(self):
        return self.get_clock().now().to_msg()

    def _event(
        self,
        event_type: int,
        success: bool,
        message: str,
        request_start,
        response_received,
        api_timestamp_ms: int = 0,
    ) -> None:
        event = GprEvent()
        event.header.stamp = response_received
        event.event_type = event_type
        event.measurement_name = self._measurement_name
        event.line_index = self._line_index
        event.success = success
        event.request_start = request_start
        event.response_received = response_received
        event.api_timestamp_ms = api_timestamp_ms
        event.has_api_timestamp = api_timestamp_ms > 0
        event.message = message
        self.event_pub.publish(event)

    @staticmethod
    def _error_text(exc: Exception) -> tuple[str, str]:
        if isinstance(exc, GprApiError):
            return exc.error_code, str(exc)
        return "INTERNAL_ERROR", str(exc)

    def _execute(
        self,
        response,
        operation: Callable[[], None],
        label: str,
        event_type: int | None = None,
    ):
        started = self._now()
        try:
            operation()
            response.success = True
            response.message = f"{label} successful"
            self._last_error = ""
        except Exception as exc:
            code, message = self._error_text(exc)
            response.success = False
            response.message = message
            self._last_error = f"{code}: {message}"
            self.get_logger().error(f"{label}: {self._last_error}")
            if hasattr(response, "error_code"):
                response.error_code = code
        if event_type is not None:
            self._event(
                event_type if response.success else GprEvent.ERROR,
                response.success,
                response.message,
                started,
                self._now(),
            )
        return response

    def _connect(self, request, response):
        def operation():
            # Explicit service values override the configured defaults.
            probe_serial = (
                request.serial_number.strip()
                or str(self.get_parameter("probe_serial").value).strip()
            )
            probe_ip = (
                request.ip_address.strip()
                or str(self.get_parameter("probe_ip").value).strip()
            )
            if not probe_serial or not probe_ip:
                raise ValueError(
                    "Probe serial and IP are required; set probe_serial/probe_ip "
                    "parameters or pass both in the Connect request"
                )
            
            try:
                probe_status = self.api.get_probe()
            except GprHttpError as exc:
                if (
                    exc.status_code == 403
                    and "[NOT_CONNECTED_TO_PROBE]" in str(exc)
                ):
                    probe_status = {"connected": False}
                else:
                    raise

            if probe_status.get("connected"):
                current = probe_status.get("probe") or {}
                serial = current.get("serialNumber", "")

                if serial != probe_serial:
                    raise ValueError(f"Another probe is connected: {serial}")
            else:
                # The GP API requires both the probe serial number and IP.
                self.api.connect_probe(probe_serial, probe_ip)

            verified = self.api.get_probe()
            serial = (verified.get("probe") or {}).get("serialNumber", "")
            if not verified.get("connected") or serial != probe_serial:
                raise RuntimeError("Connected probe could not be verified")
            response.connected_serial_number = serial

        return self._execute(response, operation, "Connect probe")

    def _start_measurement(self, request, response):
        def operation():
            requested_type = request.measurement_type or "LINE_SCAN"
            self.api.start_measurement(request.measurement_name, requested_type)
            info = self.api.get_measurement_info()
            measurement = info.get("measurement") or {}
            actual_name = str(measurement.get("name", ""))
            actual_type = str(measurement.get("type", ""))
            if actual_name != request.measurement_name or actual_type != requested_type:
                raise RuntimeError(
                    f"Measurement verification failed: {actual_name} ({actual_type})"
                )
            self._measurement_name = actual_name
            self._line_index = 0
            self._paused = False
            response.measurement_name = actual_name
            response.measurement_type = actual_type

        return self._execute(
            response, operation, "Start measurement", GprEvent.MEASUREMENT_STARTED
        )

    def _set_presets(self, request, response):
        def operation():
            mode = request.trigger_mode
            scan_frequency = (
                float(request.scan_frequency_hz) if mode == "TIMED" else None
            )
            repetition_rate = (
                float(request.repetition_rate) if mode == "FIXED_STEP" else None
            )
            self.api.set_presets(
                mode=mode,
                resolution=request.resolution,
                unit=request.unit,
                scan_frequency_hz=scan_frequency,
                repetition_rate=repetition_rate,
            )
            info = self.api.get_measurement_info()
            presets = (info.get("settings") or {}).get("presets") or {}
            if (
                presets.get("mode") != mode
                or presets.get("resolution") != request.resolution
                or presets.get("unit") != request.unit
            ):
                raise RuntimeError("Preset verification failed")
            key = "scanFrequency" if mode == "TIMED" else "repetitionRate"
            expected = scan_frequency if mode == "TIMED" else repetition_rate
            actual = presets.get(key)
            if actual is None or not math.isclose(
                float(actual), expected, rel_tol=1e-5, abs_tol=1e-6
            ):
                raise RuntimeError(f"Preset verification failed: {key}")
            response.trigger_mode = str(presets["mode"])
            response.resolution = str(presets["resolution"])
            response.unit = str(presets["unit"])
            response.scan_frequency_hz = (
                float(presets["scanFrequency"]) if mode == "TIMED" else math.nan
            )
            response.repetition_rate = (
                float(presets["repetitionRate"])
                if mode == "FIXED_STEP" else math.nan
            )

        return self._execute(response, operation, "Set presets")

    def _start_line(self, request, response):
        started = self._now()
        api_timestamp = 0
        try:
            result = self.api.start_line()
            status = self.api.get_line_status()
            if not status.get("started") or status.get("finished"):
                raise RuntimeError("Line start could not be verified")
            api_timestamp = int(result.get("clientStartTimestamp") or 0)
            if api_timestamp <= 0:
                raise RuntimeError("No valid line start timestamp was returned")
            self._line_index = int(status.get("index") or 0)
            self._paused = False
            response.line_index = self._line_index
            response.client_start_timestamp_ms = api_timestamp
            response.has_api_timestamp = True
            response.success = True
            response.message = "Start line successful"
            self._last_error = ""
        except Exception as exc:
            response.error_code, response.message = self._error_text(exc)
            self._last_error = f"{response.error_code}: {response.message}"
            self.get_logger().error(f"Start line: {self._last_error}")
        self._event(
            GprEvent.LINE_STARTED if response.success else GprEvent.ERROR,
            response.success,
            response.message,
            started,
            self._now(),
            api_timestamp,
        )
        return response

    def _stop_line(self, request, response):
        def operation():
            self.api.stop_line()
            status = self.api.get_line_status()
            if not status.get("finished"):
                raise RuntimeError("Line stop could not be verified")
            self._line_index = int(status.get("index") or self._line_index)
            self._paused = False

        return self._execute(response, operation, "Stop line", GprEvent.LINE_STOPPED)

    def _stop_measurement(self, request, response):
        def operation():
            self.api.stop_measurement()
            screen = self.api.get_screen().get("screen", "")
            if screen != "HOME":
                raise RuntimeError(f"Expected HOME after stop, got {screen!r}")
            self._paused = False

        return self._execute(
            response, operation, "Stop measurement", GprEvent.MEASUREMENT_STOPPED
        )

    def _poll_status(self) -> None:
        stamp = self._now()
        status = GprStatus()
        status.header.stamp = stamp
        status.battery_percentage = -1
        try:
            screen = self.api.get_screen()
            probe = self.api.get_probe()
            self._last_screen = str(screen.get("screen", ""))
            status.api_reachable = True
            self._last_error = ""
            status.app_screen = self._last_screen
            status.probe_connected = bool(probe.get("connected", False))
            details = probe.get("probe") or {}
            contract = probe.get("contract") or {}
            status.device_name = str(details.get("name", ""))
            status.serial_number = str(details.get("serialNumber", ""))
            status.firmware_version = str(details.get("firmware", ""))
            status.hardware_revision = str(details.get("hardwareRevision", ""))
            battery = details.get("batteryStatus")
            if isinstance(battery, int) and not isinstance(battery, bool):
                status.battery_percentage = battery
            status.battery_health = str(details.get("batteryHealth", ""))
            status.contract_name = str(contract.get("tierName", ""))
            status.contract_expiration_date = str(contract.get("expirationDate", ""))
            if self._last_screen == "MEASUREMENT":
                self._publish_measurement(stamp)
        except GprApiError as exc:
            self._last_error = f"{exc.error_code}: {exc}"
        except Exception as exc:
            self._last_error = f"INTERNAL_ERROR: {exc}"
        status.last_error = self._last_error
        self.status_pub.publish(status)

    def _publish_measurement(self, stamp) -> None:
        try:
            info = self.api.get_measurement_info()
            measurement = info.get("measurement") or {}
            presets = (info.get("settings") or {}).get("presets") or {}
            msg = GprMeasurementInfo()
            msg.header.stamp = stamp
            msg.measurement_name = str(measurement.get("name", ""))
            msg.measurement_type = str(measurement.get("type", ""))
            msg.has_data = bool(measurement.get("hasData", False))
            msg.trigger_mode = str(presets.get("mode", ""))
            msg.resolution = str(presets.get("resolution", ""))
            msg.unit = str(presets.get("unit", ""))
            msg.scan_frequency_hz = float(presets.get("scanFrequency", math.nan))
            msg.repetition_rate = float(presets.get("repetitionRate", math.nan))
            msg.valid = bool(msg.measurement_name)
            self.info_pub.publish(msg)
            if msg.valid:
                self._measurement_name = msg.measurement_name

            line = self.api.get_line_status()
            line_msg = GprLineStatus()
            line_msg.header.stamp = stamp
            line_msg.measurement_name = msg.measurement_name
            line_msg.line_index = int(line.get("index") or 0)
            line_msg.started = bool(line.get("started", False))
            line_msg.finished = bool(line.get("finished", False))
            # The API does not expose pause state; this flag is best-effort.
            line_msg.recording = (
                line_msg.started and not line_msg.finished and not self._paused
            )
            line_msg.scan_count = int(line.get("scans") or 0)
            # This is the GP API's reported length, not robot odometry.
            line_msg.reported_length_m = float(line.get("length") or 0.0)
            line_msg.valid = True
            self.line_pub.publish(line_msg)
            self._line_index = line_msg.line_index
        except GprApiError as exc:
            self._last_error = f"{exc.error_code}: {exc}"

    def destroy_node(self):
        self.api.close()
        return super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = None
    try:
        node = GprApiNode()
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        if node is not None:
            node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == "__main__":
    main()
