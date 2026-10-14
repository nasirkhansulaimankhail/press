# UniVentures Press source preservation

Captured 15 October 2026. This fork preserves deployed source without upgrading it or changing production remotes. Snapshot branches retain their original upstream parents, tracked changes and untracked source backup files, byte for byte. File modes and SHA256 values were verified before push.

This branch adds documentation to the Press production snapshot.

| Host | Snapshot branch | Upstream base | Snapshot commit | Changed paths |
| --- | --- | --- | --- | --- |
| press | `preserve/2026-10-15/press` | `4189e8ef3537` | `36e35036964b` | 95 |

Machine-readable file hashes and provenance are in `preservation/snapshots.json`. Clean Agent hosts point directly at their deployed base commit.

## Preservation scope

Includes all Git-tracked modifications/deletions and all untracked files reported by Git at capture time, including adjacent historical source backups. The production repositories were only read. Files ignored by Git, databases, credentials, site configuration, certificates, containers, Code Server runtime caches and host configuration are not included. These require protected backups through the separate pre-upgrade process. This source snapshot is not a complete production backup.

## Future work

Keep snapshot branches as historical records. Extract suitable business behavior into a custom Frappe app and maintain focused integration commits in these forks. Resolve upstream compatibility and complete isolated staging before creating any deployable upgrade release. No deployment or update automation was enabled for preservation.
