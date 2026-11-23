#!/usr/bin/env python3
"""Minimal ROS 2 example: acquire a timed GP line and export raw data.

Start both GPR nodes with gpr.launch.py before running this script.
Connection settings are read by the nodes from gpr_params_live.yaml.
"""

import argparse
import time

import rclpy
from rclpy.action import ActionClient
from rclpy.node import Node
from std_srvs.srv import Trigger

from gpr_interfaces.action import ExportRaw
from gpr_interfaces.srv import Connect, SetPresets, StartLine, StartMeasurement


class GprExample(Node):
    """Small synchronous example built on the public ROS 2 interfaces."""

    def __init__(self):
        super().__init__("gpr_example")

    def call(self, name, service_type, request):
        """Call one ROS 2 service and fail if its response is unsuccessful."""
        client = self.create_client(service_type, name)
        if not client.wait_for_service(timeout_sec=10.0):
            raise RuntimeError(f"Service unavailable: {name}")
        future = client.call_async(request)
        rclpy.spin_until_future_complete(self, future)
        response = future.result()
        if response is None:
            raise RuntimeError(f"No response from {name}: {future.exception()}")
        if not response.success:
            raise RuntimeError(f"{name}: {response.message}")
        print(f"{name}: {response.message}")
        return response

    def export(self):
        """Export and optionally extract the raw measurement archive."""
        client = ActionClient(self, ExportRaw, "/gpr/export_raw")
        if not client.wait_for_server(timeout_sec=10.0):
            raise RuntimeError("Export action unavailable")

        goal = ExportRaw.Goal()
        goal.output_directory = ""  # Use export_directory in gpr_params_live.yaml.
        goal.extract_archive = True
        goal.overwrite = False

        def feedback(message):
            update = message.feedback
            if update.stage != "DOWNLOADING":
                print(f"Export: {update.stage}")

        future = client.send_goal_async(goal, feedback_callback=feedback)
        rclpy.spin_until_future_complete(self, future)
        handle = future.result()
        if handle is None or not handle.accepted:
            raise RuntimeError("Export goal rejected")
        result_future = handle.get_result_async()
        rclpy.spin_until_future_complete(self, result_future)
        wrapped = result_future.result()
        if wrapped is None or not wrapped.result.success:
            detail = wrapped.result.message if wrapped else "No action result"
            raise RuntimeError(f"Export failed: {detail}")
        print(f"Archive: {wrapped.result.archive_path}")
        print(f"Extracted: {wrapped.result.extracted_directory}")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--duration", type=float, default=10.0,
                        help="Recording duration in seconds (default: 10)")
    parser.add_argument("--frequency", type=float, default=1.0,
                        help="TIMED scan frequency in Hz (default: 1)")
    parser.add_argument("--name", default="ROS2_GP8000_Example",
                        help="Measurement name")
    args = parser.parse_args()
    if args.duration <= 0 or args.frequency <= 0:
        parser.error("--duration and --frequency must be positive")

    rclpy.init()
    node = GprExample()
    line_open = False
    try:
        # Empty request fields use probe_serial and probe_ip from the node YAML.
        node.call("/gpr/connect", Connect, Connect.Request())

        measurement = StartMeasurement.Request()
        measurement.measurement_name = args.name
        measurement.measurement_type = "LINE_SCAN"
        node.call("/gpr/start_measurement", StartMeasurement, measurement)

        presets = SetPresets.Request()
        presets.trigger_mode = "TIMED"
        presets.resolution = "MAX_SPEED"
        presets.unit = "METRIC"
        presets.scan_frequency_hz = args.frequency
        presets.repetition_rate = 0.0  # Not used for TIMED mode.
        node.call("/gpr/set_presets", SetPresets, presets)

        started = node.call("/gpr/start_line", StartLine, StartLine.Request())
        line_open = True
        print(f"Line {started.line_index}, API timestamp: "
              f"{started.client_start_timestamp_ms} ms")
        time.sleep(args.duration)

        node.call("/gpr/stop_line", Trigger, Trigger.Request())
        line_open = False
        node.export()  # Export before closing the measurement.
        node.call("/gpr/stop_measurement", Trigger, Trigger.Request())
        print("Measurement completed")
    except (RuntimeError, KeyboardInterrupt) as exc:
        print(f"Stopped: {exc}")
        if line_open:
            try:
                node.call("/gpr/stop_line", Trigger, Trigger.Request())
            except Exception as stop_error:
                print(f"Could not stop line: {stop_error}")
        print("Check GP app state; measurement is left open for manual recovery/export.")
        raise SystemExit(1)
    finally:
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
