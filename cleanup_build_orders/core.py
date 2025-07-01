"""Remove consumed stock from old build orders"""

from datetime import timedelta

from django.db.models import Q

from plugin import InvenTreePlugin

from plugin.mixins import ScheduleMixin, SettingsMixin

from . import PLUGIN_VERSION


class CleanupBuildOrders(ScheduleMixin, SettingsMixin, InvenTreePlugin):
    """CleanupBuildOrders - custom InvenTree plugin."""

    # Plugin metadata
    TITLE = "Cleanup Build Orders"
    NAME = "CleanupBuildOrders"
    SLUG = "cleanup-build-orders"
    DESCRIPTION = "Remove consumed stock from old build orders"
    VERSION = PLUGIN_VERSION

    # Additional project information
    AUTHOR = "Oliver Walters"
    WEBSITE = "https://github.com/SchrodingersGat/inventree-clean-builds"
    LICENSE = "MIT"

    # Optionally specify supported InvenTree versions
    # MIN_VERSION = '0.18.0'
    # MAX_VERSION = '2.0.0'

    # Scheduled tasks (from ScheduleMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/schedule/
    SCHEDULED_TASKS = {
        # Define your scheduled tasks here...
    }

    # Plugin settings (from SettingsMixin)
    # Ref: https://docs.inventree.org/en/latest/plugins/mixins/settings/
    SETTINGS = {
        # Define your plugin settings here...
        "CUSTOM_VALUE": {
            "name": "Custom Value",
            "description": "A custom value",
            "validator": int,
            "default": 42,
        }
    }

    def remove_old_items(self):
        """Remove stock items from old build orders.

        We remove from the database any stock items which have been consumed,
        with the following criteria:

        - The stock item is associated with a build order which has been completed
        - The associated build order is older than a specified threshold
        - The stock item is not installed in another assembly
        - The stock item does not have a serial number
        """

        from InvenTree.helpers import current_date
        from stock.models import StockItem

        items = StockItem.objects.all()

        # Exclude those items with a serial number
        items = items.filter(Q(serial=None) | Q(serial="")).distinct()

        # Exclude those items which are installed in another assembly
        items = items.filter(belongs_to=None)

        # Exclude those items which are not associated with a completed build order
        items = items.exclude(consumed_by__isnull=True)

        # Exclude orders which were completed "recently"

        # TODO: Use a setting for this
        threshold_days = 180

        threshold_date = current_date() - timedelta(days=threshold_days)

        items = items.filter(
            consumed_by__completion_date__lt=threshold_date,
        )

        N = items.count()

        print(f"Found {N} items to delete...")
