from collections.abc import Callable
import tkinter as tk


class RoundedButton(tk.Canvas):
	def __init__(
		self,
		parent: tk.Misc,
		text: str,
		command: Callable[[], None],
		width: int,
		canvas_background: str,
		background: str,
		foreground: str,
		hover_background: str,
		disabled_background: str,
		disabled_foreground: str,
		state: str = "normal",
	) -> None:
		self.button_text = text
		self.command = command
		self.button_width = width
		self.button_height = 38
		self.button_background = background
		self.button_foreground = foreground
		self.hover_background = hover_background
		self.disabled_background = disabled_background
		self.disabled_foreground = disabled_foreground
		self.disabled = state == "disabled"
		self.hovered = False
		super().__init__(
			parent,
			width=width,
			height=self.button_height,
			background=canvas_background,
			borderwidth=0,
			highlightthickness=0,
			relief="flat",
			takefocus=True,
			cursor="hand2",
		)
		self.bind("<Enter>", self._on_enter)
		self.bind("<Leave>", self._on_leave)
		self.bind("<ButtonRelease-1>", self._on_click)
		self.bind("<Return>", self._on_key)
		self.bind("<space>", self._on_key)
		self.bind("<FocusIn>", self._on_enter)
		self.bind("<FocusOut>", self._on_leave)
		self._draw()

	def configure(self, cnf=None, **kwargs):
		if cnf is not None:
			if isinstance(cnf, dict):
				kwargs = {**cnf, **kwargs}
			else:
				return super().configure(cnf, **kwargs)

		text = kwargs.pop("text", None)
		state = kwargs.pop("state", None)
		button_background = kwargs.pop("background", None)
		button_foreground = kwargs.pop("foreground", None)
		hover_background = kwargs.pop("hover_background", None)
		disabled_background = kwargs.pop("disabled_background", None)
		disabled_foreground = kwargs.pop("disabled_foreground", None)
		canvas_background = kwargs.pop("canvas_background", None)

		if text is not None:
			self.button_text = text
		if button_background is not None:
			self.button_background = button_background
		if button_foreground is not None:
			self.button_foreground = button_foreground
		if hover_background is not None:
			self.hover_background = hover_background
		if disabled_background is not None:
			self.disabled_background = disabled_background
		if disabled_foreground is not None:
			self.disabled_foreground = disabled_foreground
		if canvas_background is not None:
			kwargs["background"] = canvas_background
		if state is not None:
			self.disabled = state == "disabled"
			super().configure(cursor="arrow" if self.disabled else "hand2")
		if kwargs:
			super().configure(**kwargs)
		self._draw()

	def _draw(self) -> None:
		self.delete("all")
		width = self.button_width
		height = self.button_height
		radius = min(10, height // 2, width // 2)
		if self.disabled:
			background = self.disabled_background
			foreground = self.disabled_foreground
		elif self.hovered:
			background = self.hover_background
			foreground = self.button_foreground
		else:
			background = self.button_background
			foreground = self.button_foreground
		self.create_rectangle(radius, 0, width - radius, height, fill=background, outline="")
		self.create_rectangle(0, radius, width, height - radius, fill=background, outline="")
		for left, top in (
			(0, 0),
			(width - 2 * radius, 0),
			(0, height - 2 * radius),
			(width - 2 * radius, height - 2 * radius),
		):
			self.create_oval(
				left,
				top,
				left + 2 * radius,
				top + 2 * radius,
				fill=background,
				outline="",
			)
		self.create_text(
			width // 2,
			height // 2,
			text=self.button_text,
			fill=foreground,
			font=("Arimo", 10, "bold"),
		)

	def _on_enter(self, _event: tk.Event) -> None:
		self.hovered = not self.disabled
		self._draw()

	def _on_leave(self, _event: tk.Event) -> None:
		self.hovered = False
		self._draw()

	def _on_click(self, event: tk.Event) -> str:
		if not self.disabled and 0 <= event.x <= self.button_width and 0 <= event.y <= self.button_height:
			self.command()
		return "break"

	def _on_key(self, _event: tk.Event) -> str:
		if not self.disabled:
			self.command()
		return "break"
