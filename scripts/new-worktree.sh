#!/bin/bash
# new-worktree.sh — create a parallel Claude Code worktree for PQA
#
# Usage:
#   ./scripts/new-worktree.sh <branch-name>
#
# Example:
#   ./scripts/new-worktree.sh fix-recovery-calc
#
# Creates a new branch + worktree at ../PQA-worktrees/<branch-name>/
# Each worktree is fully isolated — safe to run a separate Claude session there.
# When done, merge/PR as normal, then: git worktree remove ../PQA-worktrees/<branch>

set -e

BRANCH="${1}"

if [ -z "$BRANCH" ]; then
  echo "Usage: ./scripts/new-worktree.sh <branch-name>"
  exit 1
fi

REPO_ROOT="$(git rev-parse --show-toplevel)"
WORKTREE_DIR="$(dirname "$REPO_ROOT")/PQA-worktrees/$BRANCH"

if [ -d "$WORKTREE_DIR" ]; then
  echo "Worktree already exists at: $WORKTREE_DIR"
  exit 1
fi

git worktree add -b "$BRANCH" "$WORKTREE_DIR"

echo ""
echo "Worktree created at: $WORKTREE_DIR"
echo "Branch: $BRANCH"
echo ""
echo "To open a parallel Claude session there:"
echo "  cd $WORKTREE_DIR && claude"
echo ""
echo "To remove when done:"
echo "  git worktree remove $WORKTREE_DIR"
