"""Common configuration for game tasks."""

import os
from dataclasses import dataclass
from typing import Optional


@dataclass
class GeneralTaskConfig:
    """Base configuration for game tasks."""
    
    # Global settings
    REMOTE_OUTPUT_DIR: str = os.environ.get("REMOTE_OUTPUT_DIR", "output")
    REMOTE_ROOT_DIR: str = os.environ.get("REMOTE_ROOT_DIR", r"C:\Users\User\Desktop")
    TASK_CATEGORY: str = os.environ.get("TASK_CATEGORY", "tasks")
    OS_TYPE: str = os.environ.get("OS_TYPE", "windows")

    # Task-specific (to be overridden)
    TASK_TAG: str = ""
    
    @property
    def task_description(self) -> str:
        """Task description for the agent."""
        return ""
    
    @property
    def task_dir(self) -> str:
        """Generate task directory based on task_tag."""
        return fr"{self.REMOTE_ROOT_DIR}\{self.TASK_CATEGORY}\{self.TASK_TAG}"
    
    @property
    def software_dir(self) -> str:
        """Generate software directory."""
        return fr"{self.task_dir}\software"
    
    @property
    def remote_output_dir(self) -> str:
        """Output directory."""
        return fr"{self.task_dir}\{self.REMOTE_OUTPUT_DIR}"
    
    @property
    def reference_dir(self) -> str:
        """Reference directory."""
        return fr"{self.task_dir}\reference"
    
    def to_metadata(self) -> dict:
        """Convert config to metadata dict for cua_bench Task."""
        return {
            "task_tag": self.TASK_TAG,
            "software_dir": self.software_dir,
            "remote_output_dir": self.remote_output_dir,
            "reference_dir": self.reference_dir,
        }
