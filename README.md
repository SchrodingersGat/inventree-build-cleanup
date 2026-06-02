[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![PyPI](https://img.shields.io/pypi/v/inventree-build-cleanup)](https://pypi.org/project/inventree-build-cleanup/)
![PEP](https://github.com/SchrodingersGat/inventree-build-cleanup/actions/workflows/ci.yaml/badge.svg)


# CleanupBuildOrders

An [InvenTree](https://inventree.org) plugin that removes consumed stock records from old, completed build orders.

Over time, InvenTree accumulates stock items that were consumed during the build process. These records are useful for traceability while a build is active or recently completed, but become unnecessary clutter after a sufficient period has passed. This plugin automatically identifies and deletes those stale records on a weekly schedule.

## How It Works

Each week the plugin queries for stock items that meet **all** of the following criteria:

- The item has no serial number
- The item is not installed in another assembly
- The item is associated with a completed (non-active) build order
- The build order's completion date is older than the configured threshold

Deletion is gated behind an explicit confirmation step — the plugin will **never** delete anything unless the **Confirm Deletion** setting has been manually enabled. On each scheduled run without confirmation, the plugin sends a notification listing the items that would be deleted, so administrators can review before approving.

## Installation

### InvenTree Plugin Manager

Search for `cleanup-build-orders` in the InvenTree plugin manager and install directly from there.

### Command Line

```bash
pip install cleanup-build-orders
```

## Settings

### Build Cleanup Period

| | |
|---|---|
| Key | `STOCK_DELETE_PERIOD` |
| Type | Integer (months) |
| Default | `24` |
| Minimum | `6` |

How far back to look when identifying old stock records. Any consumed stock item belonging to a build order completed more than this many months ago is eligible for deletion.

### Confirm Deletion

| | |
|---|---|
| Key | `CONFIRM_DELETE` |
| Type | Boolean |
| Default | `False` |

Acts as a one-shot authorisation gate. When set to `True`, the next scheduled run will proceed with deletion. The setting is **automatically reset to `False`** immediately before the deletion loop runs, so each deletion run requires a fresh manual confirmation.

When this setting is `False` (the default), the scheduled task skips deletion and instead sends a notification summarising the items that are pending removal.

### Notification Owner

| | |
|---|---|
| Key | `NOTIFY_OWNER` |
| Type | Owner (User or Group) |
| Default | *(not set)* |

The user or group to notify when items are pending deletion. Accepts an InvenTree *Owner*, which can be either a single user or a user group — if a group is chosen, every member receives the notification email listing the eligible stock items, grouped by build order.

If no owner is configured, the notification is sent to all active superuser accounts instead.

## Usage

1. Install the plugin and enable it in InvenTree.
2. Configure the **Build Cleanup Period** to match your data retention policy.
3. Optionally set a **Notification Group** so the right team members receive the daily digest.
4. Each week the plugin will log how many items are eligible and send a notification email.
5. Review the email. When ready to delete, enable **Confirm Deletion** in the plugin settings.
6. The next scheduled run (within 7 days) will perform the deletion and reset the confirmation flag.
