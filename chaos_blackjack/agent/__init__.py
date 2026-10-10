"""Agent-player interface: JSON observations + command execution over GameController.

CLI: `python -m chaos_blackjack.agent --help`; protocol docs: AGENTS.md.
"""

from chaos_blackjack.agent.observation import OBS_SCHEMA, build_observation
from chaos_blackjack.agent.session import AgentSession

__all__ = ["AgentSession", "OBS_SCHEMA", "build_observation"]
