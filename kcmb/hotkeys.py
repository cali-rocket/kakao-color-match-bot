import keyboard


class HotkeyState:
    def __init__(self):
        self.armed = False
        self.should_quit = False

    def toggle(self):
        self.armed = not self.armed
        print(f"[hotkey] armed = {self.armed}")

    def quit(self):
        self.should_quit = True
        print("[hotkey] quit")


def install(state: HotkeyState):
    keyboard.add_hotkey("f8", state.toggle)
    keyboard.add_hotkey("f9", state.quit)
    return state
