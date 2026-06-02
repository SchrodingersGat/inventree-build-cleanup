"""Remove consumed stock from old build orders"""

import structlog

from dateutil.relativedelta import relativedelta

from django.core.validators import MinValueValidator
from django.db.models import Q

from plugin import InvenTreePlugin

from plugin.mixins import ScheduleMixin, SettingsMixin

from . import PLUGIN_VERSION


logger = structlog.get_logger("inventree")


class CleanupBuildOrders(ScheduleMixin, SettingsMixin, InvenTreePlugin):
    """CleanupBuildOrders - custom InvenTree plugin."""

    # Plugin metadata
    TITLE = "Cleanup Build Orders"
    NAME = "Cleanup Build Orders"
    SLUG = "cleanup-build-orders"
    DESCRIPTION = "Remove consumed stock from old build orders"
    VERSION = PLUGIN_VERSION

    # Additional project information
    AUTHOR = "Oliver Walters"
    WEBSITE = "https://github.com/SchrodingersGat/inventree-clean-builds"
    LICENSE = "MIT"

    MIN_VERSION = "0.18.0"
    MONTHS_DEFAULT = 24

    # Scheduled tasks (from ScheduleMixin)
    SCHEDULED_TASKS = {
        "remove_old_items": {
            "func": "remove_old_items",
            "schedule": "W",
        }
    }

    # Plugin settings (from SettingsMixin)
    SETTINGS = {
        "STOCK_DELETE_PERIOD": {
            "name": "Build Cleanup Period",
            "description": "How long to keep build order stock consumption records before deletion",
            "validator": [int, MinValueValidator(6)],
            "default": MONTHS_DEFAULT,
            "units": "months",
        },
        "CONFIRM_DELETE": {
            "name": "Confirm Deletion",
            "description": "Enable to allow deletion on the next scheduled run. Automatically reset to False after each run.",
            "default": False,
            "validator": bool,
        },
        "NOTIFY_OWNER": {
            "name": "Notification Owner",
            "description": "User or group to notify when items are pending deletion. If not set, all active superusers are notified.",
            "model": "users.owner",
            "default": "",
            "required": False,
        },
    }

    def _get_notification_targets(self):
        """Return a list of User instances to notify about pending deletions."""
        from django.contrib.auth import get_user_model
        from users.models import Owner

        owner_id = self.get_setting("NOTIFY_OWNER")

        if owner_id:
            try:
                owner = Owner.objects.get(pk=owner_id)
                return [o.owner for o in owner.get_related_owners(include_group=False)]
            except Owner.DoesNotExist:
                logger.warning("CleanupBuildOrders: Notification owner %s not found", owner_id)

        return list(get_user_model().objects.filter(is_superuser=True, is_active=True))

    def _notify_pending_deletion(self, items, threshold_date, N):
        """Send a notification that stock items are pending deletion."""
        from common.notifications import trigger_notification
        from InvenTree.helpers_model import construct_absolute_url

        build_map = {}
        for item in items.select_related("consumed_by", "part"):
            build = item.consumed_by
            if build.pk not in build_map:
                build_map[build.pk] = {
                    "build": build,
                    "build_url": construct_absolute_url(build.get_absolute_url()),
                    "items": [],
                }
            build_map[build.pk]["items"].append({
                "item": item,
                "item_url": construct_absolute_url(item.get_absolute_url()),
            })

        context = {
            "name": "Old Build Order Stock Items",
            "message": f"{N} stock items from old build orders are scheduled for deletion",
            "build_groups": list(build_map.values()),
            "threshold_date": threshold_date,
            "template": {
                "html": "email/old_build_items.html",
                "subject": f"[InvenTree] {N} old build stock items pending deletion",
            },
        }

        targets = self._get_notification_targets()

        if not targets:
            logger.warning("CleanupBuildOrders: No notification targets found")
            return

        trigger_notification(
            items.first(),
            "cleanup_build_orders.pending_deletion",
            targets=targets,
            context=context,
            check_recent=False,
        )

    def remove_old_items(self):
        """Remove stock items from old build orders.

        We remove from the database any stock items which have been consumed,
        with the following criteria:

        - The stock item is associated with a build order which has been completed
        - The associated build order is older than a specified threshold
        - The stock item is not installed in another assembly
        - The stock item does not have a serial number
        """

        from build.status_codes import BuildStatusGroups
        from InvenTree.helpers import current_date
        from stock.models import StockItem

        items = StockItem.objects.all()

        # Exclude those items with a serial number
        items = items.filter(Q(serial=None) | Q(serial="")).distinct()

        # Exclude those items which are installed in another assembly
        items = items.filter(belongs_to=None)

        # Exclude those items which are not associated with a completed build order
        items = items.exclude(consumed_by__isnull=True)

        # Exclude active build orders
        items = items.exclude(consumed_by__status__in=BuildStatusGroups.ACTIVE_CODES)
        items = items.exclude(consumed_by__completion_date__isnull=True)

        # Exclude orders which were completed "recently"
        threshold_months = int(
            self.get_setting("STOCK_DELETE_PERIOD", backup_value=self.MONTHS_DEFAULT)
        )

        threshold_date = current_date() - relativedelta(months=threshold_months)

        items = items.filter(
            consumed_by__completion_date__lt=threshold_date,
        )

        N = items.count()

        if N == 0:
            logger.info("CleanupBuildOrders: No items eligible for deletion")
            return

        logger.info("CleanupBuildOrders: %s items eligible for deletion", N)

        if not self.get_setting("CONFIRM_DELETE"):
            logger.info("CleanupBuildOrders: CONFIRM_DELETE not set - skipping deletion")
            self._notify_pending_deletion(items, threshold_date, N)
            return

        # Reset the confirmation flag immediately so deletion only runs once
        self.set_setting("CONFIRM_DELETE", False)

        logger.warning("CleanupBuildOrders: Deleting %s items", N)

        M = 0

        # Delete the items
        # Notes:
        #  - The items are deleted individually to ensure that any FK relationships are observed
        #  - This may be slow for large datasets, but is necessary to avoid integrity errors
        #  - If the task fails due to timeout, the other items will be deleted next time
        for item in items:
            # Ensure we have the latest data
            item.refresh_from_db()

            # Double check that all of our criteria are still met before deletion
            if item.serial not in [None, ""]:
                continue

            # Item should not be installed in another assembly
            if item.belongs_to:
                continue

            # Item should be associated with a completed build order
            if not item.consumed_by:
                continue

            # Item should not be associated with an active build order
            if item.consumed_by.status in BuildStatusGroups.ACTIVE_CODES:
                continue

            # Item should be associated with a build order which was completed before the threshold date
            if item.consumed_by.completion_date is None:
                continue

            # Item should not be associated with a build order which was completed "recently"
            if item.consumed_by.completion_date >= threshold_date:
                continue

            item.delete()
            M += 1

        logger.warning("CleanupBuildOrders: Deleted %s items", M)
