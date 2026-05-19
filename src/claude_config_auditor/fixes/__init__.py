"""Phase 2 fix-mode infrastructure.

This package holds the proposal data model, the approval loop, and the
applier. Concrete fix types (CLAUDE.md archiving, agent-description
rewrites) live in their own modules and produce Proposal objects that
this layer renders, prompts on, and applies.
"""

from claude_config_auditor.fixes.flow import (
    Proposal,
    apply_proposals,
    run_fix_flow,
)

__all__ = ["Proposal", "apply_proposals", "run_fix_flow"]
