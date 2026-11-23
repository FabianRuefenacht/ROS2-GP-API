from glob import glob
import os
from setuptools import find_packages, setup

package_name = "gpr_ros2"

setup(
    name=package_name,
    version="0.1.0",
    packages=find_packages(exclude=["test"]),
    data_files=[
        (
            "share/ament_index/resource_index/packages",
            ["resource/" + package_name]
        ),
        (
            "share/" + package_name,
            ["package.xml"],
        ),
        (
            os.path.join("share", package_name, "launch"),
            glob("launch/*.launch.py"),
        ),
        (
            os.path.join("share", package_name, "config"),
            glob("config/*.yaml"),
        ),
    ],
    install_requires=["setuptools"],
    zip_safe=True,
    maintainer="Fabian Rüfenacht",
    maintainer_email="114218235+FabianRuefenacht@users.noreply.github.com",
    description=(
        "ROS 2 wrapper for the Screening Eagle GP API, "
        "supporting remote GPR control and data export."
    ),
    license="MIT",
    tests_require=["pytest"],
    
    entry_points={
        "console_scripts": [
            "api_node = gpr_ros2.api_node:main",
            "export_node = gpr_ros2.export_node:main",
        ],
    },

)