# Manuals Inbox — drop equipment manuals here for processing

Upload the source equipment PDFs here (via GitHub web UI or git) so they can
be processed into `settings_reference.py` (the Settings Reference tab's
knowledge base).

## What to upload
- **ComAp InteliGen / InteliSys NT** Global Guide (setpoints reference)
- **ComAp InteliConfig** configuration tool manual
- **Leroy-Somer D550** Installation & Maintenance manual (already processed ✓)

## How to upload via GitHub
1. Open this folder on the branch on github.com
2. Click **Add file → Upload files**
3. Drag in the PDFs (≤ 25 MB each via browser)
4. Commit to the working branch

## Size limits
| Method | Per-file limit |
|---|---|
| Browser drag-drop | 25 MB |
| Git push | 100 MB (warns at 50 MB) |
| Git LFS | 2 GB |

## After processing
These files are working inputs, not app data. **Delete them once the info has
been extracted** into `settings_reference.py` to keep the repo lean — the
extracted knowledge lives in code, not in committed binaries.

> If a manual exceeds 25 MB, either: split the PDF, push via git CLI, or just
> attach it directly in the Claude chat (PDFs and markdown summaries both work).
