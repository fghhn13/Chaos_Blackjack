"""Core package — avoid eager `GameLoop` import to prevent circular imports."""

from chaos_blackjack.core.game_state import Card, GamePhase, GameState


def __getattr__(name: str):
    if name == "GameLoop":
        from chaos_blackjack.core.game_loop import GameLoop

        return GameLoop
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = ["Card", "GamePhase", "GameState", "GameLoop"]
