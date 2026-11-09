"""Use metadata from the installed webrtcvad-wheels distribution."""

from PyInstaller.utils.hooks import copy_metadata


datas = copy_metadata("webrtcvad-wheels")
