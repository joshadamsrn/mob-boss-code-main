# Quick Actions

These macOS `.command` files can be double-clicked in Finder to run common Git tasks for this repo.

Suggested first-time order on a new machine:

1. Run `Set Git Identity.command`
2. Run `Trust GitHub SSH Host.command`
3. Run `Commit and Push.app` or `Commit and Push.command`

Notes:

- `.command` files open in Terminal when double-clicked.
- `Commit and Push.app` is a clickable Finder app icon that auto-generates a simple timestamp commit message and pushes the current branch.
- `Commit and Push.command` stages all repo changes with `git add -A`.
- The push target is the current Git branch.
