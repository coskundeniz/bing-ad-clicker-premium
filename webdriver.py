import os
import random
import shutil
import sys
from pathlib import Path
from time import sleep
from typing import Optional

try:
    import pyautogui
    import requests
    import undetected_chromedriver

except ImportError:
    packages_path = Path.cwd() / "env" / "Lib" / "site-packages"
    sys.path.insert(0, f"{packages_path}")

    import pyautogui
    import requests
    import undetected_chromedriver

from config_reader import config
from geolocation_db import GeolocationDB
from logger import logger
from proxy import install_plugin
from utils import get_location, get_locale_language, get_random_sleep


IS_POSIX = sys.platform.startswith(("cygwin", "linux"))


class CustomChrome(undetected_chromedriver.Chrome):
    """Modified Chrome implementation"""

    def quit(self):

        try:
            # logger.debug("Terminating the browser")
            os.kill(self.browser_pid, 15)
            if IS_POSIX:
                os.waitpid(self.browser_pid, 0)
            else:
                sleep(0.05)
        except (AttributeError, ChildProcessError, RuntimeError, OSError):
            pass
        except TimeoutError as e:
            logger.debug(e, exc_info=True)
        except Exception:
            pass

        if hasattr(self, "service") and getattr(self.service, "process", None):
            # logger.debug("Stopping webdriver service")
            self.service.stop()

        try:
            if self.reactor:
                # logger.debug("Shutting down Reactor")
                self.reactor.event.set()
        except Exception:
            pass

        if (
            hasattr(self, "keep_user_data_dir")
            and hasattr(self, "user_data_dir")
            and not self.keep_user_data_dir
        ):
            for _ in range(5):
                try:
                    shutil.rmtree(self.user_data_dir, ignore_errors=False)
                except FileNotFoundError:
                    pass
                except (RuntimeError, OSError, PermissionError) as e:
                    logger.debug(
                        "When removing the temp profile, a %s occured: %s\nretrying..."
                        % (e.__class__.__name__, e)
                    )
                else:
                    # logger.debug("successfully removed %s" % self.user_data_dir)
                    break

                sleep(0.1)

        # dereference patcher, so patcher can start cleaning up as well.
        # this must come last, otherwise it will throw 'in use' errors
        self.patcher = None

    def __del__(self):
        try:
            self.service.process.kill()
        except Exception:  # noqa
            pass

        try:
            self.quit()
        except OSError:
            pass

    @classmethod
    def _ensure_close(cls, self):
        # needs to be a classmethod so finalize can find the reference
        if (
            hasattr(self, "service")
            and hasattr(self.service, "process")
            and hasattr(self.service.process, "kill")
        ):
            self.service.process.kill()

            if IS_POSIX:
                try:
                    # prevent zombie processes
                    os.waitpid(self.service.process.pid, 0)
                except ChildProcessError:
                    pass
                except Exception:
                    pass
            else:
                sleep(0.05)


def create_webdriver(
    proxy: str, user_agent: Optional[str] = None, plugin_folder_name: Optional[str] = None
) -> tuple[undetected_chromedriver.Chrome, Optional[str]]:
    """Create Selenium Chrome webdriver instance

    :type proxy: str
    :param proxy: Proxy to use in ip:port or user:pass@host:port format
    :type user_agent: str
    :param user_agent: User agent string
    :type plugin_folder_name: str
    :param plugin_folder_name: Plugin folder name for proxy
    :rtype: tuple
    :returns: (undetected_chromedriver.Chrome, country_code) pair
    """

    geolocation_db_client = GeolocationDB()

    chrome_options = undetected_chromedriver.ChromeOptions()
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-infobars")
    chrome_options.add_argument("--disable-popup-blocking")
    chrome_options.add_argument("--disable-notifications")
    chrome_options.add_argument("--ignore-ssl-errors")
    chrome_options.add_argument("--ignore-certificate-errors")
    chrome_options.add_argument("--disable-translate")
    chrome_options.add_argument("--deny-permission-prompts")
    chrome_options.add_argument("--no-first-run")
    chrome_options.add_argument("--no-service-autorun")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-cache")
    chrome_options.add_argument("--disable-application-cache")
    chrome_options.add_argument("--media-cache-size=0")
    chrome_options.add_argument("--disk-cache-size=0")
    chrome_options.add_argument("--disable-breakpad")
    chrome_options.add_argument("--disable-renderer-backgrounding")
    chrome_options.add_argument(f"--user-agent={user_agent}")

    optimization_features = [
        "OptimizationGuideModelDownloading",
        "OptimizationHintsFetching",
        "OptimizationTargetPrediction",
        "OptimizationHints",
        "Translate",
        "DownloadBubble",
        "DownloadBubbleV2",
    ]
    chrome_options.add_argument(f"--disable-features={','.join(optimization_features)}")

    # disable WebRTC IP tracking
    webrtc_preferences = {
        "webrtc.ip_handling_policy": "disable_non_proxied_udp",
        "webrtc.multiple_routes_enabled": False,
        "webrtc.nonproxied_udp_enabled": False,
    }
    chrome_options.add_experimental_option("prefs", webrtc_preferences)

    if config.webdriver.incognito:
        chrome_options.add_argument("--incognito")

    if not config.webdriver.window_size:
        logger.debug("Maximizing window...")
        chrome_options.add_argument("--start-maximized")

    country_code = None

    multi_browser_flag_file = Path(".MULTI_BROWSERS_IN_USE")
    multi_procs_enabled = multi_browser_flag_file.exists()
    driver_exe_path = None

    if multi_procs_enabled:
        driver_exe_path = _get_driver_exe_path()

    if proxy:
        logger.info(f"Using proxy: {proxy}")

        if config.webdriver.auth:
            if "@" not in proxy or proxy.count(":") != 2:
                raise ValueError(
                    "Invalid proxy format! Should be in 'username:password@host:port' format"
                )

            username, password = proxy.split("@")[0].split(":")
            host, port = proxy.split("@")[1].split(":")

            install_plugin(chrome_options, host, int(port), username, password, plugin_folder_name)
            sleep(2)

        else:
            chrome_options.add_argument(f"--proxy-server={proxy}")

        # get location of the proxy IP
        lat, long, country_code, timezone = get_location(geolocation_db_client, proxy)

        if config.webdriver.language_from_proxy:
            lang = get_locale_language(country_code)
            chrome_options.add_experimental_option("prefs", {"intl.accept_languages": str(lang)})
            chrome_options.add_argument(f"--lang={lang[:2]}")

        driver = CustomChrome(
            driver_executable_path=(
                driver_exe_path if multi_procs_enabled and Path(driver_exe_path).exists() else None
            ),
            options=chrome_options,
            user_multi_procs=multi_procs_enabled,
            use_subprocess=False,
        )

        accuracy = 95

        # set geolocation and timezone of the browser according to IP address
        if lat and long:
            driver.execute_cdp_cmd(
                "Emulation.setGeolocationOverride",
                {"latitude": lat, "longitude": long, "accuracy": accuracy},
            )

            if not timezone:
                response = requests.get(f"http://timezonefinder.michelfe.it/api/0_{long}_{lat}")

                if response.status_code == 200:
                    timezone = response.json()["tz_name"]

            driver.execute_cdp_cmd("Emulation.setTimezoneOverride", {"timezoneId": timezone})

            logger.debug(
                f"Timezone of {proxy.split('@')[1] if config.webdriver.auth else proxy}: {timezone}"
            )

    else:
        driver = CustomChrome(
            driver_executable_path=(
                driver_exe_path if multi_procs_enabled and Path(driver_exe_path).exists() else None
            ),
            options=chrome_options,
            user_multi_procs=multi_procs_enabled,
            use_subprocess=False,
        )

    if config.webdriver.window_size:
        width, height = config.webdriver.window_size.split(",")
        logger.debug(f"Setting window size as {width}x{height} px")
        driver.set_window_size(width, height)

    if config.webdriver.shift_windows:
        # get screen size
        screen_width, screen_height = pyautogui.size()

        window_position = driver.get_window_position()
        x, y = window_position["x"], window_position["y"]

        random_x_offset = random.choice(range(150, 300))
        random_y_offset = random.choice(range(75, 150))

        if config.webdriver.window_size:
            new_width = int(width) - random_x_offset
            new_height = int(height) - random_y_offset
        else:
            new_width = int(screen_width * 2 / 3) - random_x_offset
            new_height = int(screen_height * 2 / 3) - random_y_offset

        # set the window size and position
        driver.set_window_size(new_width, new_height)

        new_x = min(x + random_x_offset, screen_width - new_width)
        new_y = min(y + random_y_offset, screen_height - new_height)

        logger.debug(f"Setting window position as ({new_x},{new_y})...")

        driver.set_window_position(new_x, new_y)
        sleep(get_random_sleep(0.1, 0.5))

    return (driver, country_code) if config.webdriver.country_domain else (driver, None)


def _get_driver_exe_path() -> str:
    """Get the path for the chromedriver executable to avoid downloading and patching each time

    :rtype: str
    :returns: Absoulute path of the chromedriver executable
    """

    platform = sys.platform
    prefix = "undetected"
    exe_name = "chromedriver%s"

    if platform.endswith("win32"):
        exe_name %= ".exe"
    if platform.endswith(("linux", "linux2")):
        exe_name %= ""
    if platform.endswith("darwin"):
        exe_name %= ""

    if platform.endswith("win32"):
        dirpath = "~/appdata/roaming/undetected_chromedriver"
    elif "LAMBDA_TASK_ROOT" in os.environ:
        dirpath = "/tmp/undetected_chromedriver"
    elif platform.startswith(("linux", "linux2")):
        dirpath = "~/.local/share/undetected_chromedriver"
    elif platform.endswith("darwin"):
        dirpath = "~/Library/Application Support/undetected_chromedriver"
    else:
        dirpath = "~/.undetected_chromedriver"

    driver_exe_folder = os.path.abspath(os.path.expanduser(dirpath))
    driver_exe_path = os.path.join(driver_exe_folder, "_".join([prefix, exe_name]))

    return driver_exe_path
