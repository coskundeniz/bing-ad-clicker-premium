import subprocess

from logger import logger


class ADBController:

    def __init__(self):

        self.devices = []

    def get_connected_devices(self) -> None:
        """Retrieve the list of connected devices"""

        try:
            command = ["adb", "devices"]
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode != 0:
                raise Exception(f"Failed to list devices: {result.stderr}")

            # parse the output to get device ids
            for line in result.stdout.splitlines()[1:]:
                if line:
                    device_id = line.split()[0]
                    self.devices.append(device_id)

            if not self.devices:
                raise SystemExit("No device was found! Please connect at least 1 device.")

            for device in self.devices:
                logger.debug(f"Android device: {device}")

        except Exception as exp:
            raise Exception(f"An error occurred while running: '{' '.join(command)}'") from exp

    @staticmethod
    def open_url(url: str, device_id: str) -> None:
        """Open URL on the phone

        :type url: str
        :param url: URL to open on connected device
        :type device_id: str
        :param device_id: Connected device's ID
        """

        try:
            command = [
                "adb",
                "-s",
                device_id,
                "shell",
                "am",
                "start",
                "-n",
                "com.android.chrome/com.google.android.apps.chrome.Main",
                "-a",
                "android.intent.action.VIEW",
                "-d",
                url,
            ]
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode == 0:
                logger.info(f"URL[{url}] was successfully opened on device[{device_id}]")
            else:
                logger.error(f"Error opening URL: {result.stderr}")

        except Exception as exp:
            raise Exception(f"An error occurred while running: '{' '.join(command)}'") from exp

    @staticmethod
    def send_keyevent(keycode: int) -> None:
        """Send the key event via adb shell

        :type keycode: int
        :param keycode: Integer value for the key to be send
        """

        try:
            command = ["adb", "shell", "input", "keyevent", str(keycode)]
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode == 0:
                logger.debug(f"Key event[{keycode}] was successfully sent.")
            else:
                logger.error(f"Couldn't send key event: {result.stderr}")

        except Exception as exp:
            raise Exception(f"An error occurred while running: '{' '.join(command)}'") from exp

    @staticmethod
    def send_swipe(x1: int, y1: int, x2: int, y2: int, duration: int) -> None:
        """Swipe the screen via adb shell

        :type x1: int
        :param x1: Starting x coordinate
        :type y1: int
        :param y1: Starting y coordinate
        :type x2: int
        :param x2: Ending x coordinate
        :type y2: int
        :param y2: Ending y coordinate
        :type duration: int
        :param duration: Duration of the swipe in milliseconds
        """

        try:
            command = [
                "adb",
                "shell",
                "input",
                "swipe",
                str(x1),
                str(y1),
                str(x2),
                str(y2),
                str(duration),
            ]
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode != 0:
                logger.error(f"Error during swipe: {result.stderr}")

        except Exception as exp:
            raise Exception(f"An error occurred while running: '{' '.join(command)}'") from exp

    @staticmethod
    def close_browser() -> None:
        """Close the browser via adb shell"""

        try:
            BACK_KEYCODE = 4
            command = ["adb", "shell", "input", "keyevent", str(BACK_KEYCODE)]
            result = subprocess.run(command, capture_output=True, text=True)

            if result.returncode == 0:
                logger.debug(f"Back key event was successfully sent.")
            else:
                logger.error(f"Couldn't send key event: {result.stderr}")

        except Exception as exp:
            raise Exception(f"An error occurred while running: '{' '.join(command)}'") from exp


adb_controller = ADBController()
