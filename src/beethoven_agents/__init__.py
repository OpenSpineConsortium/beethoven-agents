"""beethoven-agents: the nested agentic framework of the Beethoven engine.

The substrate image and its managed settings, the PreToolUse guard baked into it, the accounts and
the super-master lease (decision D4), and the orchestration of masters, satellites and `claude -p`
steps on the grid. Code here is written and proven to beethoven-qa's definition of done, with the
pinned copy at vendor/beethoven-qa. Beethoven runs Claude Code and is not an Anthropic product.
"""

__all__ = ["__version__"]

# Integer-style versions (1.0.0), never fractional; 0.0.0 while the framework is a skeleton.
__version__ = "0.0.0"
