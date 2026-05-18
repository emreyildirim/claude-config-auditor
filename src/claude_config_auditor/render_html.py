"""Public entry point for the HTML report renderer.

The implementation lives in the `_html` package alongside its CSS,
template, and section renderers. This module exists so the public
import path stays stable:

    from claude_config_auditor.render_html import render_html
"""

from claude_config_auditor._html import render_html

__all__ = ["render_html"]
