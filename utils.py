import os
import sys
import json
import random
import shutil
from datetime import datetime
from enum import Enum
from pathlib import Path
from time import sleep
from typing import Optional

try:
    import pyautogui
    import requests
    import openpyxl
    import undetected_chromedriver
    from openpyxl.styles import Alignment, Font

except ImportError:
    packages_path = Path.cwd() / "env" / "Lib" / "site-packages"
    sys.path.insert(0, f"{packages_path}")

    import pyautogui
    import requests
    import openpyxl
    import undetected_chromedriver
    from openpyxl.styles import Alignment, Font

from config_reader import config
from geolocation_db import GeolocationDB
from logger import logger
from proxy import install_plugin


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


class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"
    BOTH = "BOTH"


def get_random_user_agent_string() -> str:
    """Get random user agent

    :rtype: str
    :returns: User agent string
    """

    user_agents = _get_user_agents(config.paths.user_agents)

    user_agent_string = random.choice(user_agents)

    logger.debug(f"user_agent: {user_agent_string}")

    return user_agent_string


def _get_user_agents(user_agent_file: Path) -> list[str]:
    """Get user agents from file

    :type user_agent_file: Path
    :param user_agent_file: File containing user agents
    :rtype: list
    :returns: List of user agents
    """

    filepath = Path(user_agent_file)

    if not filepath.exists():
        raise SystemExit(f"Couldn't find user agents file: {filepath}")

    with open(filepath, encoding="utf-8") as useragentfile:
        user_agents = [
            user_agent.strip().replace("'", "").replace('"', "")
            for user_agent in useragentfile.read().splitlines()
        ]

    return user_agents


def get_location(geolocation_db_client: GeolocationDB, proxy: str) -> tuple[float, float, str, str]:
    """Get latitude, longitude, country code, and timezone of ip address

    :type geolocation_db_client: GeolocationDB
    :param geolocation_db_client: GeolocationDB instance
    :type proxy: str
    :param proxy: Proxy to get geolocation
    :rtype: tuple
    :returns: (latitude, longitude, country_code, timezone) tuple for the given proxy IP
    """

    proxies_header = {"http": f"http://{proxy}", "https": f"http://{proxy}"}

    ip_address = ""

    if config.webdriver.auth:
        for cycle in range(2):
            try:
                response = requests.get("https://api.ipify.org", proxies=proxies_header, timeout=5)
                ip_address = response.text

                if not ip_address:
                    raise Exception("Failed with https://api.ipify.org")

                break

            except Exception as exp:
                logger.debug(exp)

                try:
                    logger.debug("Trying with ipv4.webshare.io...")
                    response = requests.get(
                        "https://ipv4.webshare.io/", proxies=proxies_header, timeout=5
                    )
                    ip_address = response.text

                    if not ip_address:
                        raise Exception("Failed with https://ipv4.webshare.io")

                    break

                except Exception as exp:
                    logger.debug(exp)

                    try:
                        logger.debug("Trying with ipconfig.io...")
                        response = requests.get(
                            "https://ipconfig.io/json", proxies=proxies_header, timeout=5
                        )
                        ip_address = response.json().get("ip")

                        if not ip_address:
                            raise Exception("Failed with https://ipconfig.io/json")

                        break

                    except Exception as exp:
                        logger.debug(exp)

                        if cycle == 1:
                            break

                        logger.info("Request will be resend after 60 seconds")
                        sleep(60)

            sleep(get_random_sleep(0.5, 1))
    else:
        ip_address = proxy.split(":")[0]

    if not ip_address:
        logger.info(f"Couldn't verify IP address for {proxy}!")
        logger.debug("Geolocation won't be set")
        return (None, None, None, None)

    logger.info(f"Connecting with IP: {ip_address}")

    db_result = geolocation_db_client.query_geolocation(ip_address)

    latitude = None
    longitude = None
    country_code = None
    timezone = None

    if db_result:
        latitude, longitude, country_code = db_result
        logger.debug(f"Cached latitude and longitude for {ip_address}: ({latitude}, {longitude})")
        logger.debug(f"Cached country code for {ip_address}: {country_code}")

        if not country_code:
            try:
                response = requests.get(f"https://ipapi.co/{ip_address}/json/", timeout=5)
                country_code = response.json().get("country_code")
                timezone = response.json().get("timezone")
                logger.debug(f"Country code for {ip_address}: {country_code}")

            except Exception:
                try:
                    response = requests.get(
                        "https://ifconfig.co/json", proxies=proxies_header, timeout=5
                    )
                    country_code = response.json().get("country_iso")
                    timezone = response.json().get("time_zone")
                except Exception:
                    logger.debug(f"Couldn't find country code for {ip_address}!")

        return (float(latitude), float(longitude), country_code, timezone)

    else:
        retry_count = 0
        max_retry_count = 5
        sleep_seconds = 5

        while retry_count < max_retry_count:
            try:
                response = requests.get(f"https://ipapi.co/{ip_address}/json/", timeout=5)
                latitude, longitude, country_code, timezone = (
                    response.json().get("latitude"),
                    response.json().get("longitude"),
                    response.json().get("country_code"),
                    response.json().get("timezone"),
                )

                if not (latitude and longitude and country_code):
                    raise Exception("Failed with https://ipapi.co")

                break
            except Exception as exp:
                logger.debug(exp)
                logger.debug("Continue with ifconfig.co")

                try:
                    response = requests.get(
                        "https://ifconfig.co/json", proxies=proxies_header, timeout=5
                    )
                    latitude, longitude, country_code, timezone = (
                        response.json().get("latitude"),
                        response.json().get("longitude"),
                        response.json().get("country_iso"),
                        response.json().get("time_zone"),
                    )

                    if not (latitude and longitude and country_code):
                        raise Exception("Failed with https://ifconfig.co/json")

                    break
                except Exception as exp:
                    logger.debug(exp)
                    logger.debug("Continue with ipconfig.io")

                    try:
                        response = requests.get(
                            "https://ipconfig.io/json", proxies=proxies_header, timeout=5
                        )
                        latitude, longitude, country_code, timezone = (
                            response.json().get("latitude"),
                            response.json().get("longitude"),
                            response.json().get("country_iso"),
                            response.json().get("time_zone"),
                        )

                        if not (latitude and longitude and country_code):
                            raise Exception("Failed with https://ipconfig.io/json")

                        break
                    except Exception as exp:
                        logger.debug(exp)
                        logger.error(
                            f"Couldn't find latitude and longitude for {ip_address}! "
                            f"Retrying after {sleep_seconds} seconds..."
                        )

                        retry_count += 1
                        sleep(sleep_seconds)
                        sleep_seconds *= 2

            sleep(0.5)

        if latitude and longitude and country_code:
            logger.debug(f"Latitude and longitude for {ip_address}: ({latitude}, {longitude})")
            logger.debug(f"Country code for {ip_address}: {country_code}")

            geolocation_db_client.save_geolocation(ip_address, latitude, longitude, country_code)

            return (latitude, longitude, country_code, timezone)
        else:
            logger.error(f"Couldn't find latitude, longitude, and country_code for {ip_address}!")
            return (None, None, None, None)


def get_queries() -> list[str]:
    """Get queries from file

    :rtype: list
    :returns: List of queries
    """

    filepath = Path(config.paths.query_file)

    if not filepath.exists():
        raise SystemExit(f"Couldn't find queries file: {filepath}")

    with open(filepath, encoding="utf-8") as queryfile:
        queries = [
            query.strip().replace("'", "").replace('"', "")
            for query in queryfile.read().splitlines()
        ]

    return queries


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

        else:
            chrome_options.add_argument(f"--proxy-server={proxy}")

        # get location of the proxy IP
        lat, long, country_code, timezone = get_location(geolocation_db_client, proxy)

        if config.webdriver.language_from_proxy:
            lang = _get_locale_language(country_code)
            chrome_options.add_experimental_option("prefs", {"intl.accept_languages": str(lang)})
            chrome_options.add_argument(f"--lang={lang[:2]}")

        driver = CustomChrome(
            driver_executable_path=(
                driver_exe_path if multi_procs_enabled and Path(driver_exe_path).exists() else None
            ),
            options=chrome_options,
            user_multi_procs=multi_procs_enabled,
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


def get_domains() -> list[str]:
    """Get domains from file

    :rtype: list
    :returns: List of domains
    """

    filepath = Path(config.paths.filtered_domains)

    if not filepath.exists():
        raise SystemExit(f"Couldn't find domains file: {filepath}")

    with open(filepath, encoding="utf-8") as domainsfile:
        domains = [
            domain.strip().replace("'", "").replace('"', "")
            for domain in domainsfile.read().splitlines()
        ]

    logger.debug(f"Domains: {domains}")

    return domains


def add_cookies(driver: undetected_chromedriver.Chrome) -> None:
    """Add cookies from cookies.txt file

    :type driver: undetected_chromedriver.Chrome
    :param driver: Selenium Chrome webdriver instance
    """

    filepath = Path.cwd() / "cookies.txt"

    if not filepath.exists():
        raise SystemExit("Missing cookies.txt file!")

    logger.info(f"Adding cookies from {filepath}")

    with open(filepath, encoding="utf-8") as cookie_file:
        try:
            cookies = json.loads(cookie_file.read())
        except Exception:
            logger.error("Failed to read cookies file. Check format and try again.")
            raise SystemExit()

    for cookie in cookies:
        if cookie["sameSite"] == "strict":
            cookie["sameSite"] = "Strict"
        elif cookie["sameSite"] == "lax":
            cookie["sameSite"] = "Lax"
        else:
            cookie["sameSite"] = "None" if cookie["secure"] else "Lax"

        driver.add_cookie(cookie)


def solve_recaptcha(
    apikey: str,
    sitekey: str,
    current_url: str,
    data_s: str,
    cookies: Optional[str] = None,
) -> Optional[str]:
    """Solve the recaptcha using the 2captcha service

    :type apikey: str
    :param apikey: API key for the 2captcha service
    :type sitekey: str
    :param sitekey: data-sitekey attribute value of the recaptcha element
    :type current_url: str
    :param current_url: Url that is showing the captcha
    :type data_s: str
    :param data_s: data-s attribute of the captcha element
    :type cookies: str
    :param cookies: Cookies to send 2captcha service
    :rtype: str
    :returns: Response code obtained from the service or None
    """

    logger.info("Trying to solve captcha...")

    api_url = "http://2captcha.com/in.php"
    params = {
        "key": apikey,
        "method": "userrecaptcha",
        "googlekey": sitekey,
        "pageurl": current_url,
        "data-s": data_s,
    }

    if cookies:
        params["cookies"] = cookies

    max_retry_count = 10
    request_retry_count = 0

    while request_retry_count < max_retry_count:
        response = requests.get(api_url, params=params)

        logger.debug(f"Response: {response.text}")

        error_to_exit, error_to_continue, error_to_break = _check_error(response.text)

        if error_to_exit:
            raise SystemExit()

        elif error_to_break:
            request_id = response.text.split("|")[1]
            logger.debug(f"request_id: {request_id}")
            break

        elif error_to_continue:
            request_retry_count += 1
            continue

    sleep(15)

    # check if the CAPTCHA has been solved
    response_api_url = "http://2captcha.com/res.php"
    params = {"key": apikey, "action": "get", "id": request_id}

    response_retry_count = 0
    captcha_response = None

    while response_retry_count < max_retry_count:
        response = requests.get(response_api_url, params=params)

        logger.debug(f"Response: {response.text}")

        error_to_exit, error_to_continue, error_to_break = _check_error(
            response.text, request_type="res_php"
        )

        if error_to_exit:
            raise SystemExit()

        elif error_to_continue:
            response_retry_count += 1
            continue

        elif error_to_break:
            if "CAPCHA_NOT_READY" not in response.text:
                captcha_response = response.text.split("|")[1]
                return captcha_response

    if not captcha_response:
        logger.error("Failed to solve captcha!")

    return captcha_response


def take_screenshot(driver: undetected_chromedriver.Chrome) -> None:
    """Save screenshot during exception

    :type driver: undetected_chromedriver.Chrome
    :param driver: Selenium Chrome webdriver instance
    """

    now = datetime.now().strftime("%d-%m-%Y_%H:%M:%S")
    filename = f"exception_ss_{now}.png"

    if driver:
        driver.save_screenshot(filename)
        sleep(get_random_sleep(1, 1.5))
        logger.info(f"Saved screenshot during exception as {filename}")


def generate_click_report(click_results: list[tuple[str, str, str]], report_date: str) -> None:
    """Update results file with new rows

    :type click_results: list
    :param click_results: List of (site_url, clicks, category, click_time, query) tuples for the given date
    :type report_date: str
    :param report_date: Date to query clicks
    """

    click_report_file = Path(f"click_report_{report_date}.xlsx")

    workbook = openpyxl.Workbook()
    sheet = workbook.active

    sheet.row_dimensions[1].height = 20

    # add header
    sheet["A1"] = "URL"
    sheet["B1"] = "Query"
    sheet["C1"] = "Clicks"
    sheet["D1"] = "Time"
    sheet["E1"] = "Category"

    bold_font = Font(bold=True)
    center_align = Alignment(horizontal="center", vertical="center")

    for cell in ("A1", "B1", "C1", "D1", "E1"):
        sheet[cell].font = bold_font
        sheet[cell].alignment = center_align

    # adjust column widths
    sheet.column_dimensions["A"].width = 80
    sheet.column_dimensions["B"].width = 25
    sheet.column_dimensions["C"].width = 15
    sheet.column_dimensions["D"].width = 20
    sheet.column_dimensions["E"].width = 15

    for result in click_results:
        url, click_count, category, click_time, query = result
        sheet.append((url, query, click_count, f"{report_date} {click_time}", category))

    for column_letter in ("B", "C", "D", "E"):
        sheet.column_dimensions[column_letter].alignment = center_align

    workbook.save(click_report_file)

    logger.info(f"Results were written to {click_report_file}")


def get_random_sleep(start: int, end: int) -> float:
    """Generate a random number from the given range

    :type start: int
    :pram start: Start value
    :type end: int
    :pram end: End value
    :rtype: float
    :returns: Randomly selected number rounded to 2 decimals
    """

    return round(random.uniform(start, end), 2)


def _check_error(response_text: str, request_type: str = "in_php") -> tuple[bool, bool, bool]:
    """Check errors returned from requests to in.php or res.php endpoints

    :type response_text: str
    :param response_text: Response returned from the request
    :request_type: str
    :param request_type: Request type to differentiate error groups
    :rtype: tuple
    :returns: Flags for exit, continue, and break
    """

    logger.debug("Checking error code...")

    error_to_exit, error_to_continue, error_to_break = False, False, False

    if request_type == "in_php":
        if "ERROR_WRONG_USER_KEY" in response_text or "ERROR_KEY_DOES_NOT_EXIST" in response_text:
            logger.error("Invalid API key. Please check your 2captcha API key.")
            error_to_exit = True

        elif "ERROR_ZERO_BALANCE" in response_text:
            logger.error("You don't have funds on your account. Please load your account.")
            error_to_exit = True

        elif "ERROR_NO_SLOT_AVAILABLE" in response_text:
            logger.error(
                "The queue of your captchas that are not distributed to workers is too long."
            )
            logger.info("Waiting 5 seconds before sending new request...")
            sleep(5)

            error_to_continue = True

        elif "IP_BANNED" in response_text:
            logger.error(
                "Your IP address is banned due to many frequent attempts to access the server"
            )
            error_to_exit = True

        elif "ERROR_GOOGLEKEY" in response_text:
            logger.error("Blank or malformed sitekey.")
            error_to_exit = True

        else:
            logger.debug(response_text)
            error_to_break = True

    elif request_type == "res_php":
        if "ERROR_WRONG_USER_KEY" in response_text or "ERROR_KEY_DOES_NOT_EXIST" in response_text:
            logger.error("Invalid API key. Please check your 2captcha API key.")
            error_to_exit = True

        elif "ERROR_CAPTCHA_UNSOLVABLE" in response_text:
            logger.error("Unable to solve the captcha.")
            error_to_exit = True

        elif "CAPCHA_NOT_READY" in response_text:
            logger.info("Waiting 5 seconds before checking response again...")
            sleep(5)

            error_to_continue = True

        else:
            logger.debug(response_text)
            error_to_break = True

    else:
        logger.error(f"Wrong request type: {request_type}")

    return (error_to_exit, error_to_continue, error_to_break)


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


def _get_locale_language(country_code: str) -> str:
    """Get locale language for the given country code

    :type country_code: str
    :param country_code: Country code for proxy IP
    :rtype: str
    :returns: Locale language for the given country code
    """

    logger.debug(f"Getting locale language for {country_code}...")

    with open("country_to_locale.json", "r") as locales_file:
        locales = json.load(locales_file)

    locale_language = locales.get(country_code, ["en"])

    logger.debug(f"Locale language code for {country_code}: {locale_language[0]}")

    return locale_language
