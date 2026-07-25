"""from src.windows.app.main import InfinityModemApp


if __name__ == "__main__":
    app = InfinityModemApp()
    app.run()
"""
from src.windows.modem.send import transmit_file


transmit_file("2kb.txt")
