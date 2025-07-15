"""Remove consumed stock from old build orders"""

import structlog

from datetime import timedelta

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
            "schedule": "D",
        }
    }

    # Plugin settings (from SettingsMixin)
    SETTINGS = {
        "STOCK_DELETE_PERIOD": {
            "name": "Stock Delete Period",
            "description": "How long to keep stock history records before deletion",
            "validator": [int, MinValueValidator(6)],
            "default": MONTHS_DEFAULT,
            "units": "months",
        },
    }

    def remove_old_items(self, dry_run: bool = False):
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
        threshold_days = threshold_months * 30

        threshold_date = current_date() - timedelta(days=threshold_days)

        items = items.filter(
            consumed_by__completion_date__lt=threshold_date,
        )

        N = items.count()
        M = 0

        logger.warning("CleanupBuildOrders: Deleting %s items", N)

        if dry_run:
            logger.info("CleanupBuildOrders: Dry run - not deleting items")
            return

        # Delete the items
        # Notes:
        #  - The items are deleted individually to ensure that any FK relationships are observed
        #  - This may be slow for large datasets, but is necessary to avoid integrity errors
        #  - If the task fails due to timeout, the other items will be deleted next time
        for item in items:
            item.refresh_from_db()  # Ensure we have the latest data
            item.delete()
            M += 1

        logger.warning("CleanupBuildOrders: Deleted %s items", M)
