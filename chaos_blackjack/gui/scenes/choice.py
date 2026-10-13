"""Choice dialog — answer the controller's pending question (app/choice.py).

    app.scenes.push("choice", controller=ctrl, on_change=callback)

One dialog for every question a command can ask (a core, which permanent to
replace, an item's target): it draws `view.choice`, sends `choose <option>` or
`cancel`, and closes once nothing is pending. It knows nothing about the
table that asked. Number keys pick an option; Esc cancels when allowed.
"""

from __future__ import annotations

from collections.abc import Callable

import pygame

from chaos_blackjack.app.controller import ActionError, GameController
from chaos_blackjack.gui import theme
from chaos_blackjack.gui.scene import Scene, register_scene
from chaos_blackjack.gui.settings import LOGICAL_SIZE
from chaos_blackjack.gui.texts import BAD
from chaos_blackjack.gui.widgets import Button, WidgetGroup, fit_text, wrap_text

W, H = LOGICAL_SIZE
BOX_W = 760
OPTION_H, OPTION_GAP = 76, 12
ICON = 48


@register_scene("choice")
class ChoiceScene(Scene):
    transparent = True

    def on_enter(self, controller: GameController | None = None,
                 on_change: Callable[[], None] | None = None, **params) -> None:
        assert controller is not None
        self.controller = controller
        self.on_change = on_change
        self.message: tuple[str, theme.Color] | None = None
        self._build()

    def _build(self) -> None:
        a = self.app.assets
        self.choice = self.controller.view().choice
        if self.choice is None:
            return
        options = self.choice.options
        height = 150 + len(options) * (OPTION_H + OPTION_GAP) + (70 if self.choice.cancellable else 10)
        self.box = pygame.Rect(0, 0, BOX_W, min(H - 60, height))
        self.box.center = (W // 2, H // 2)
        self.option_rects: list[pygame.Rect] = []
        buttons: list[Button] = []
        y = self.box.y + 110
        for i, option in enumerate(options):
            rect = pygame.Rect(self.box.x + 32, y, self.box.w - 64, OPTION_H)
            self.option_rects.append(rect)
            buttons.append(Button(a, (rect.right - 150, rect.y + (OPTION_H - 44) // 2, 136, 44), "Choose",
                                  self._chooser(option.id), font_size=theme.FONT_BODY,
                                  hotkey=pygame.K_1 + i if i < 9 else None))
            y += OPTION_H + OPTION_GAP
        if self.choice.cancellable:
            buttons.append(Button(a, (self.box.centerx - 90, self.box.bottom - 64, 180, 48), "Cancel",
                                  self._cancel, style="ghost", hotkey=pygame.K_ESCAPE, font_size=theme.FONT_BODY))
        self.ui = WidgetGroup(*buttons, keyboard=True)

    def _chooser(self, option: str) -> Callable[[], None]:
        return lambda: self._run(lambda: self.controller.choose(option))

    def _cancel(self) -> None:
        self._run(self.controller.cancel_choice)

    def _run(self, command: Callable[[], None]) -> None:
        try:
            command()
        except ActionError as e:
            self.message = (str(e), BAD)
        if self.on_change is not None:
            self.on_change()
        if self.controller.view().choice is None:
            self.app.scenes.pop()
        else:  # nothing applied, or the answer asked a new question
            self._build()

    def handle_event(self, event: pygame.event.Event) -> None:
        if self.choice is not None:
            self.ui.handle_event(event)

    def update(self, dt: float) -> None:
        if self.choice is None:  # answered elsewhere (e.g. a resumed save)
            self.app.scenes.pop()

    def draw(self, surface: pygame.Surface) -> None:
        if self.choice is None:
            return
        a = self.app.assets
        shade = pygame.Surface(LOGICAL_SIZE, pygame.SRCALPHA)
        shade.fill((0, 0, 0, 170))
        surface.blit(shade, (0, 0))
        pygame.draw.rect(surface, theme.PANEL, self.box, border_radius=14)
        pygame.draw.rect(surface, theme.GOLD_DIM, self.box, 2, border_radius=14)
        title = a.font(theme.FONT_HEADING, role="display").render("Choose", True, theme.GOLD)
        surface.blit(title, (self.box.x + 32, self.box.y + 18))
        body = a.font(theme.FONT_BODY)
        for i, line in enumerate(wrap_text(body, self.choice.prompt, self.box.w - 64, max_lines=2)):
            surface.blit(body.render(line, True, theme.TEXT), (self.box.x + 32, self.box.y + 62 + i * body.get_linesize()))
        name_font, tiny = a.font(theme.FONT_BODY, bold=True), a.font(theme.FONT_TINY)
        for rect, option in zip(self.option_rects, self.choice.options):
            pygame.draw.rect(surface, theme.DARK, rect, border_radius=10)
            row = self.controller.product(option.id)  # a product option is framed in its group's colour
            edge = theme.GROUP_COLORS.get(row.group, theme.GOLD_DIM) if row is not None else theme.GOLD_DIM
            pygame.draw.rect(surface, edge, rect, 2 if row is not None else 1, border_radius=10)
            x = rect.x + 14
            if a.has_file(option.id) or option.id in a.manifest:
                surface.blit(a.image(option.id, (ICON, ICON)), (x, rect.y + (OPTION_H - ICON) // 2))
                x += ICON + 12
            width = rect.right - 170 - x
            surface.blit(name_font.render(fit_text(name_font, option.label, width), True, theme.IVORY), (x, rect.y + 10))
            for j, line in enumerate(wrap_text(tiny, option.description, width, max_lines=2)):
                surface.blit(tiny.render(line, True, theme.TEXT_MUTED), (x, rect.y + 36 + j * tiny.get_linesize()))
        if self.message is not None:
            text, color = self.message
            img = a.font(theme.FONT_SMALL).render(text, True, color)
            surface.blit(img, img.get_rect(midbottom=(self.box.centerx, self.box.bottom - (70 if self.choice.cancellable else 8))))
        self.ui.draw(surface)
