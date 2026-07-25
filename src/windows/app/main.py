from textual.app import App
from src.windows.app.screens.menu import MenuScreen
from src.windows.app.screens.transmit import TransmitScreen
from src.windows.app.screens.receive import ReceiveScreen
from src.windows.app.screens.calibrate import CalibrateScreen

from src.windows.config import STYLES_DIR


class InfinityModemApp(App):
    CSS_PATH = [STYLES_DIR / "main.tcss",]
    
    BINDINGS = [("ctrl+q", "quit", "Quit")]

    SCREENS = {
        "menu": MenuScreen,
        "transmit": TransmitScreen,
        "receive": ReceiveScreen,
        "calibrate": CalibrateScreen,
    }

    def on_mount(self):
        self.push_screen(MenuScreen())
