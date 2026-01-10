"""
Video-Creator AI Agents Package

This package contains workflow agents for automated video creation
from presentation materials.
"""

from agents.narrator import narrate
from agents.video_creator import PresenterVideoCreaterWorkflow

__all__ = [
    "narrate",
    "PresenterVideoCreaterWorkflow",
]

