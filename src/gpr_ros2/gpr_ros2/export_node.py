"""ROS 2 action server for downloading raw GP API exports as ZIP archives.

The export is initiated by POST /measurement/export/raw. This node saves
and optionally extracts the resulting archive without modifying SEG-Y data.
"""

from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
import re
import threading
import uuid
from urllib.parse import unquote
import zipfile

import httpx
import rclpy
from rclpy.action import ActionServer, CancelResponse, GoalResponse
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node

from gpr_interfaces.action import ExportRaw
from .api_client import GprApiClient
from .exceptions import GprApiError


class ExportCancelled(Exception):
    """Raised when a ROS action goal is cancelled during export."""


class GprExportNode(Node):
    """Download GP raw exports through the /gpr/export_raw action."""

    def __init__(self) -> None:
        super().__init__("gpr_export_node")
        self.declare_parameter("ipad_host", "")
        self.declare_parameter("ipad_port", 9000)
        self.declare_parameter("request_timeout_s", 10.0)
        self.declare_parameter("export_timeout_s", 300.0)
        self.declare_parameter("export_directory", "~/gpr_data/raw")

        host = str(self.get_parameter("ipad_host").value).strip()
        if not host:
            raise ValueError("ipad_host must be set via ROS parameters")

        self.api = GprApiClient(
            host=host,
            port=int(self.get_parameter("ipad_port").value),
            timeout=float(self.get_parameter("request_timeout_s").value),
            export_timeout=float(self.get_parameter("export_timeout_s").value),
        )
        self._busy = threading.Lock()
        self._action = ActionServer(
            self,
            ExportRaw,
            "/gpr/export_raw",
            execute_callback=self._execute,
            goal_callback=self._accept_goal,
            cancel_callback=self._accept_cancel,
            callback_group=ReentrantCallbackGroup(),
        )
        self.get_logger().info("Raw export action ready")

    def _accept_goal(self, goal_request):
        # A second goal is rejected while an export is in progress.
        if self._busy.locked():
            self.get_logger().warning("An export is already running")
            return GoalResponse.REJECT
        return GoalResponse.ACCEPT

    @staticmethod
    def _accept_cancel(goal_handle):
        return CancelResponse.ACCEPT

    @staticmethod
    def _filename_from_headers(headers) -> str:
        """Extract a safe basename from Content-Disposition, if present."""
        header = headers.get("content-disposition", "")
        match = re.search(r"filename\*\s*=\s*UTF-8''([^;]+)", header, re.I)
        if match:
            proposed = unquote(match.group(1).strip().strip('"'))
        else:
            match = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;]+))', header, re.I)
            proposed = (match.group(1) or match.group(2)).strip() if match else ""
        proposed = proposed.replace("\\", "/").split("/")[-1]
        proposed = re.sub(r"[^A-Za-z0-9_.-]", "_", proposed).strip("._")
        if not proposed.lower().endswith(".zip"):
            proposed = ""
        if not proposed:
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            proposed = f"gpr_raw_{stamp}.zip"
        return proposed

    @staticmethod
    def _validate_archive(archive_path: Path) -> None:
        """Reject corrupt ZIPs and unsafe extraction names."""
        with zipfile.ZipFile(archive_path) as archive:
            if not archive.infolist():
                raise ValueError("Downloaded ZIP archive is empty")
            for item in archive.infolist():
                normalized = item.filename.replace("\\", "/")
                member = PurePosixPath(normalized)
                if (
                    member.is_absolute()
                    or ".." in member.parts
                    or normalized.startswith("/")
                    or re.match(r"^[A-Za-z]:", normalized)
                    or (item.external_attr >> 16) & 0o170000 == 0o120000
                ):
                    raise ValueError(f"Unsafe ZIP member: {item.filename}")
            invalid = archive.testzip()
            if invalid is not None:
                raise ValueError(f"Corrupt ZIP member: {invalid}")

    @staticmethod
    def _feedback(goal_handle, stage: str, downloaded: int = 0, total: int = 0):
        feedback = ExportRaw.Feedback()
        feedback.stage = stage
        feedback.bytes_downloaded = downloaded
        feedback.total_bytes = total
        feedback.progress_percent = (
            100.0 * downloaded / total if total > 0 else -1.0
        )
        goal_handle.publish_feedback(feedback)

    @staticmethod
    def _check_cancel(goal_handle):
        if goal_handle.is_cancel_requested:
            raise ExportCancelled("Export cancelled by the action client")

    def _execute(self, goal_handle):
        result = ExportRaw.Result()
        # Re-check here, as goal callbacks can race before execution begins.
        if not self._busy.acquire(blocking=False):
            result.error_code = "EXPORT_BUSY"
            result.message = "Another export is in progress"
            goal_handle.abort()
            return result

        temporary = None
        archive_path = None
        try:
            requested = goal_handle.request
            directory_text = requested.output_directory.strip() or str(
                self.get_parameter("export_directory").value
            ).strip()
            if not directory_text:
                raise ValueError("An export directory is required")
            directory = Path(directory_text).expanduser()
            if not directory.is_absolute():
                raise ValueError("output_directory must be an absolute path")
            directory.mkdir(parents=True, exist_ok=True)
            self._check_cancel(goal_handle)
            self._feedback(goal_handle, "REQUESTING")

            with self.api.stream_raw_export() as response:
                filename = self._filename_from_headers(response.headers)
                archive_path = directory / filename
                if archive_path.exists() and not requested.overwrite:
                    raise FileExistsError(f"Archive already exists: {archive_path}")

                temporary = directory / f".{filename}.{uuid.uuid4().hex}.part"
                declared_length = response.headers.get("content-length", "")
                total = int(declared_length) if declared_length.isdigit() else 0
                downloaded = 0
                self._feedback(goal_handle, "DOWNLOADING", 0, total)
                with temporary.open("xb") as output:
                    for chunk in response.iter_bytes(chunk_size=1024 * 256):
                        self._check_cancel(goal_handle)
                        if not chunk:
                            continue
                        output.write(chunk)
                        downloaded += len(chunk)
                        self._feedback(goal_handle, "DOWNLOADING", downloaded, total)

            self._check_cancel(goal_handle)
            if total and downloaded != total:
                raise ValueError(
                    f"Incomplete response: expected {total} bytes, got {downloaded}"
                )
            self._feedback(goal_handle, "VALIDATING", downloaded, total)
            self._validate_archive(temporary)
            self._check_cancel(goal_handle)

            extracted = ""
            if requested.extract_archive:
                extracted_path = directory / archive_path.stem
                if extracted_path.exists():
                    # Avoid silently mixing results of different exports.
                    raise FileExistsError(
                        f"Extraction directory already exists: {extracted_path}"
                    )
                self._feedback(goal_handle, "EXTRACTING", downloaded, total)
                extracted_path.mkdir()
                try:
                    with zipfile.ZipFile(temporary) as archive:
                        for member in archive.infolist():
                            self._check_cancel(goal_handle)
                            archive.extract(member, extracted_path)
                except Exception:
                    # Do not remove user data outside our newly created folder.
                    import shutil
                    shutil.rmtree(extracted_path)
                    raise
                extracted = str(extracted_path)

            self._check_cancel(goal_handle)
            if archive_path.exists() and not requested.overwrite:
                raise FileExistsError(f"Archive already exists: {archive_path}")
            temporary.replace(archive_path)
            temporary = None

            result.success = True
            result.archive_path = str(archive_path)
            result.extracted_directory = extracted
            result.archive_size_bytes = downloaded
            result.message = "Raw export completed"
            goal_handle.succeed()
            self.get_logger().info(f"Saved raw export: {archive_path}")
        except ExportCancelled as exc:
            result.error_code = "CANCELLED"
            result.message = str(exc)
            goal_handle.canceled()
        except Exception as exc:
            result.error_code = (
                exc.error_code if isinstance(exc, GprApiError) else "EXPORT_ERROR"
            )
            result.message = str(exc)
            goal_handle.abort()
            self.get_logger().error(f"Raw export failed: {exc}")
        finally:
            if temporary is not None:
                temporary.unlink(missing_ok=True)
            self._busy.release()
        return result

    def destroy_node(self):
        self._action.destroy()
        self.api.close()
        super().destroy_node()


def main(args=None):
    rclpy.init(args=args)
    node = GprExportNode()
    executor = MultiThreadedExecutor(num_threads=2)
    try:
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
