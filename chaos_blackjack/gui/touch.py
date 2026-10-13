"""Translate finger gestures into logical taps and pixel scrolls."""
import pygame

TOUCH_SCROLL = pygame.event.custom_type()
FINGER_EVENTS = (pygame.FINGERDOWN, pygame.FINGERMOTION, pygame.FINGERUP)


class TouchInput:
    """Keep drags out of button click handlers and suppress SDL mouse duplicates."""

    def __init__(self):
        self.reset()

    def reset(self):
        self.fingers = set()
        self.active = None
        self.scene = None
        self.dragging = False

    def translate(self, event, size, to_canvas, scene):
        finger = (event.touch_id, event.finger_id)
        physical = (event.x * size[0], event.y * size[1])
        pos = to_canvas(physical)
        if event.type == pygame.FINGERDOWN:
            self.fingers.add(finger)
            if len(self.fingers) != 1:
                self.active = None  # A multi-finger gesture must never select a row.
                return []
            self.active, self.scene = finger, scene
            self.origin, self.anchor, self.previous = physical, pos, pos
            self.dragging = False
            return []
        if event.type == pygame.FINGERUP:
            self.fingers.discard(finger)
        if finger != self.active:
            return []
        if scene is not self.scene:
            self.active = None
            return []
        # Threshold is in window pixels, so it remains usable on a small phone.
        distance = (physical[0] - self.origin[0]) ** 2 + (physical[1] - self.origin[1]) ** 2
        self.dragging = self.dragging or distance >= 8 ** 2
        events = []
        if self.dragging:
            delta = self.previous[1] - pos[1]
            if delta:
                events.append(pygame.event.Event(TOUCH_SCROLL, pos=self.anchor, dy=delta))
        elif event.type == pygame.FINGERUP:
            events = [pygame.event.Event(pygame.MOUSEMOTION, pos=pos, rel=(0, 0), buttons=(0, 0, 0)),
                      pygame.event.Event(pygame.MOUSEBUTTONDOWN, pos=self.anchor, button=1),
                      pygame.event.Event(pygame.MOUSEBUTTONUP, pos=pos, button=1)]
        self.previous = pos
        if event.type == pygame.FINGERUP:
            self.active = None
        return events
