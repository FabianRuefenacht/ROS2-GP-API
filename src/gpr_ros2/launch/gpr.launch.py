
"""Launch the GP API control and export nodes."""

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description():
    """Create the GP API launch description."""

    package_name = "gpr_ros2"

    package_share = get_package_share_directory(package_name)

    default_config = os.path.join(
        package_share,
        "config",
        "gpr_params_live.yaml",
    )

    config_file = LaunchConfiguration("config_file")

    return LaunchDescription([
        DeclareLaunchArgument(
            "config_file",
            default_value=default_config,
            description="Path to the GP API parameter file.",
        ),

        Node(
            package=package_name,
            executable="api_node",
            name="gpr_api_node",
            output="screen",
            parameters=[config_file],
        ),

        Node(
            package=package_name,
            executable="export_node",
            name="gpr_export_node",
            output="screen",
            parameters=[config_file],
        ),
    ])
