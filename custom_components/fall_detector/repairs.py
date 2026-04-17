"""Repair issues for Fall Detector."""
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import logging

from homeassistant.core import HomeAssistant
from homeassistant.helpers import issue_registry as ir

from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)


def create_addon_unreachable_issue(hass: HomeAssistant) -> None:
    """Create a repair issue when the add-on is unreachable."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        "addon_unreachable",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.ERROR,
        translation_key="addon_unreachable",
        translation_placeholders={},
    )


def remove_addon_unreachable_issue(hass: HomeAssistant) -> None:
    """Remove the add-on unreachable repair issue."""
    ir.async_delete_issue(hass, DOMAIN, "addon_unreachable")


def create_camera_stream_stale_issue(
    hass: HomeAssistant, camera_name: str,
) -> None:
    """Create a repair issue when a camera stream is stale."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"camera_stale_{camera_name}",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="camera_stream_stale",
        translation_placeholders={"camera": camera_name},
    )


def remove_camera_stream_stale_issue(
    hass: HomeAssistant, camera_name: str,
) -> None:
    """Remove the camera stream stale repair issue."""
    ir.async_delete_issue(hass, DOMAIN, f"camera_stale_{camera_name}")


def create_high_false_positive_issue(
    hass: HomeAssistant, camera_name: str, rate: float,
) -> None:
    """Create a repair issue for high false positive rate."""
    ir.async_create_issue(
        hass,
        DOMAIN,
        f"high_false_positive_{camera_name}",
        is_fixable=False,
        is_persistent=True,
        severity=ir.IssueSeverity.WARNING,
        translation_key="high_false_positive_rate",
        translation_placeholders={
            "camera": camera_name,
            "rate": f"{rate:.0%}",
        },
    )
