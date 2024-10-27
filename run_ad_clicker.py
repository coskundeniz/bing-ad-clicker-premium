import random
import traceback
import subprocess
from concurrent.futures import ProcessPoolExecutor, wait
from itertools import cycle
from pathlib import Path
from time import sleep
from typing import Optional

from adb import adb_controller
from logger import logger
from config_reader import config
from proxy import get_proxies
from utils import get_queries


def start_tool(
    browser_id: int, query: str, proxy: str, start_timeout: float, device_id: Optional[str] = None
) -> None:
    """Start the tool

    :type browser_id: int
    :param browser_id: Browser id to separate instances in log for multiprocess runs
    :type query: str
    :param query: Search query
    :type proxy: str
    :param proxy: Proxy to use in ip:port or user:pass@host:port format
    :type start_timeout: float
    :param start_timeout: Start timeout to avoid race condition in driver patching
    :type device_id: str
    :param device_id: Android device ID to assign
    """

    sleep(start_timeout)

    command = ["python", "ad_clicker.py"]
    command.extend(["-q", query, "-p", proxy, "--id", str(browser_id)])

    if device_id:
        command.extend(["-d", device_id])

    subprocess.run(command)


def main() -> None:

    multi_browser_flag_file = Path(".MULTI_BROWSERS_IN_USE")
    multi_browser_flag_file.unlink(missing_ok=True)

    MAX_WORKERS = config.behavior.browser_count

    if MAX_WORKERS > 1:
        logger.debug(f"Creating {multi_browser_flag_file} flag file...")
        multi_browser_flag_file.touch()

    if config.paths.query_file:
        queries = get_queries()

        if config.behavior.multiprocess_style == 1:
            random.shuffle(queries)

        query = cycle(queries) if len(queries) <= MAX_WORKERS else iter(queries)
    else:
        raise SystemExit("Missing query_file parameter!")

    if config.paths.proxy_file:
        proxies = get_proxies()
        random.shuffle(proxies)
        proxy = cycle(proxies) if len(proxies) <= MAX_WORKERS else iter(proxies)
    else:
        raise SystemExit("Missing proxy_file parameter!")

    if config.behavior.send_to_android:
        adb_controller.get_connected_devices()
        devices = adb_controller.devices
        random.shuffle(devices)
        device_ids = devices + [None] * (MAX_WORKERS - len(devices))
    else:
        device_ids = [None] * MAX_WORKERS

    logger.info(f"Running with {MAX_WORKERS} browser{'s' if MAX_WORKERS > 1 else ''}...")

    # 1st way - different query on each browser (default)
    if config.behavior.multiprocess_style == 1:
        with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
            futures = [
                executor.submit(
                    start_tool,
                    i,
                    next(query),
                    next(proxy),
                    start_timeout=i * 0.5,
                    device_id=device_ids[i - 1],
                )
                for i in range(1, MAX_WORKERS + 1)
            ]

            # wait for all tasks to complete
            _, _ = wait(futures)

    # 2nd way - same query on each browser
    elif config.behavior.multiprocess_style == 2:
        for query in queries:
            proxies = get_proxies()
            random.shuffle(proxies)
            proxy = cycle(proxies)

            if config.behavior.send_to_android:
                devices = adb_controller.devices
                random.shuffle(devices)
                device_ids = devices + [None] * (MAX_WORKERS - len(devices))

            with ProcessPoolExecutor(max_workers=MAX_WORKERS) as executor:
                futures = [
                    executor.submit(
                        start_tool,
                        i,
                        query,
                        next(proxy),
                        start_timeout=i * 0.5,
                        device_id=device_ids[i - 1],
                    )
                    for i in range(1, MAX_WORKERS + 1)
                ]

                # wait for all tasks to complete
                _, _ = wait(futures)

    else:
        logger.error("Invalid multiprocess style!")


if __name__ == "__main__":
    try:
        main()

    except Exception as exp:
        logger.error("Exception occurred. See the details in the log file.")

        message = str(exp).split("\n")[0]
        logger.debug(f"Exception: {message}")
        details = traceback.format_tb(exp.__traceback__)
        logger.debug(f"Exception details: \n{''.join(details)}")

        logger.debug(f"Exception cause: {exp.__cause__}") if exp.__cause__ else None
