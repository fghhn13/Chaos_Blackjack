"""Modal conversation banner: one worker, no click-through, explicit dismissal."""

from collections.abc import Callable
from concurrent.futures import Future

import pygame

from chaos_blackjack.ai.interaction import UNAVAILABLE_REPLY, ask_chaos
from chaos_blackjack.contracts.chaos_interaction import PokeOutcome, PokeReply, PokeRequest
from chaos_blackjack.contracts.llm import LLMBackend
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.widgets import Button, wrap_text
from chaos_blackjack.gui.worker import start_worker


def _reply_worker(llm: LLMBackend, request: PokeRequest, future: Future[PokeReply]) -> None:
    try:
        reply = ask_chaos(llm, request)
    except Exception:
        reply = PokeReply(UNAVAILABLE_REPLY, ok=False)
    future.set_result(reply)


@register_scene("chaos_poke")
class ChaosPokeScene(Scene):
    transparent = True

    def on_enter(self, *, request: PokeRequest, llm: LLMBackend,
                 on_reply: Callable[[PokeOutcome], None], **params) -> None:
        self.request = request
        self.on_reply = on_reply
        self.reply: PokeReply | None = None
        self.elapsed = 0.0
        self._closed = self._dismissed = False
        self._confirm_pending = False
        self.box = pygame.Rect(0, 0, 720, 300)
        self.box.center = (LOGICAL_SIZE[0] // 2, LOGICAL_SIZE[1] // 2)
        self.continue_button = Button(
            self.app.assets, (self.box.centerx - 90, self.box.bottom - 64, 180, 46),
            "Continue", self._dismiss, enabled=False, hotkey=pygame.K_RETURN,
        )
        self._future: Future[PokeReply] | None = Future()
        start_worker(_reply_worker, (llm, request, self._future), name="chaos-poke")

    def on_exit(self) -> None:
        self._closed = True
        self._future = None

    def on_resume(self, result=None) -> None:
        self._confirm_pending = False

    def _dismiss(self) -> None:
        if self._closed or self._dismissed or self.reply is None:
            return
        self._dismissed = True
        self.on_reply(PokeOutcome(self.request, self.reply))
        self.app.scenes.pop()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self._closed or self._dismissed or self._confirm_pending:
            return
        if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
            if self.reply is not None:
                self._dismiss()
            else:
                self._confirm_pending = True
                self.app.scenes.push(
                    "confirm", message="Return to the main menu? This run will be lost.",
                    on_confirm=lambda: self.app.scenes.reset("home"),
                )
            return
        # All events stop here; avatar clicks cannot reach the table/shop.
        self.continue_button.handle_event(event)

    def update(self, dt: float) -> None:
        if self._closed:
            return
        self.elapsed += dt
        if self._future is not None and self._future.done():
            self.reply = self._future.result()
            self._future = None
            self.continue_button.enabled = True

    def draw(self, surface: pygame.Surface) -> None:
        a = self.app.assets
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 155))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, theme.PANEL, self.box, border_radius=14)
        pygame.draw.rect(surface, theme.CHAOS_MAGENTA, self.box, 2, border_radius=14)
        title = a.font(theme.FONT_HEADING, role="display").render("Chaos AI", True, theme.CHAOS_MAGENTA)
        surface.blit(title, title.get_rect(midtop=(self.box.centerx, self.box.y + 18)))
        if self.reply is None:
            text = a.font(theme.FONT_BODY).render("Chaos is thinking...", True, theme.TEXT)
            surface.blit(text, text.get_rect(center=(self.box.centerx, self.box.centery - 12)))
            active = int(self.elapsed / .25) % 3
            for i in range(3):
                pygame.draw.circle(surface, theme.CHAOS_MAGENTA if i == active else theme.CHAOS_PURPLE,
                                   (self.box.centerx + (i - 1) * 18, self.box.centery + 20),
                                   5 if i == active else 3)
            note = a.font(theme.FONT_SMALL).render("Esc: leave the table", True, theme.TEXT_MUTED)
            surface.blit(note, note.get_rect(midbottom=(self.box.centerx, self.box.bottom - 24)))
        else:
            font = a.font(theme.FONT_BODY)
            y = self.box.y + 66
            max_lines = max(1, (self.continue_button.rect.top - 16 - y) // font.get_linesize())
            lines = wrap_text(font, self.reply.text, self.box.w - 64, max_lines=max_lines)
            for line in lines:
                surface.blit(font.render(line, True, theme.IVORY), (self.box.x + 32, y))
                y += font.get_linesize()
            self.continue_button.draw(surface)
