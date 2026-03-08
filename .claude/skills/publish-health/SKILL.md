---
name: publish-health
description: Detect new or updated markdown files in the health outputs directory and push them to the GitHub Pages repo.
disable-model-invocation: true
user-invocable: true
allowed-tools:
  - Bash
  - Read
  - Glob
  - Grep
  - Edit
  - Write
---

Publish new or updated markdown files from the health outputs directory to the GitHub repo.

## Steps

1. Change to the outputs directory: `/Users/oleizerov/Documents/private/health/outputs/`

2. Run `git status` to detect new untracked markdown files and modified markdown files.

3. If there are no changes, inform the user that everything is up to date and stop.

4. If the `index.md` file exists, check whether any NEW markdown files (not yet listed) need to be added to the index. If so, update `index.md` to include links to the new files, following the existing format:
   - Numbered documents (`01-*.md` through `10-*.md`) go under `## Documents`
   - Other markdown files (like spikes) go under `## Spikes`

5. Stage all new and modified `.md` files plus `index.md` (if changed) and `_config.yml` (if changed):
   ```
   git add *.md _config.yml
   ```

6. Create a commit with a descriptive message summarizing what was added or updated.

7. Push to origin main:
   ```
   git push origin main
   ```

8. Report to the user:
   - Which files were added or updated
   - The commit hash
   - Remind them the site is at: https://olegleyz.github.io/health-product-analysis/
