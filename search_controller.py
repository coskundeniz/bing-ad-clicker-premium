import sys
import json
import random
from datetime import datetime
from time import sleep
from threading import Thread
from typing import Optional, Union

import selenium
from selenium.webdriver import ActionChains
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import (
    TimeoutException,
    NoSuchElementException,
    StaleElementReferenceException,
)

import hooks
from clicklogs_db import ClickLogsDB
from config_reader import config
from logger import logger
from stats import SearchStats
from utils import Direction, add_cookies, solve_recaptcha, get_random_sleep


AdList = list[tuple[selenium.webdriver.remote.webelement.WebElement, str, str, str]]
NonAdList = list[selenium.webdriver.remote.webelement.WebElement]
AllLinks = list[Union[AdList, NonAdList]]


class SearchController:
    """Search controller for ad clicker

    :type driver: selenium.webdriver
    :param driver: Selenium Chrome webdriver instance
    :type query: str
    :param query: Search query
    :type country_code: str
    :param country_code: Country code for the proxy IP
    """

    URL = "https://www.bing.com"

    SEARCH_INPUT = (By.NAME, "q")
    RESULTS_CONTAINER = (By.ID, "b_results")
    COOKIE_DIALOG_CONTAINER = (By.ID, "bnp_cookie_banner")
    COOKIE_DIALOG_BUTTON = (By.ID, "bnp_btn_accept")
    TOP_ADS_CONTAINER = (By.CSS_SELECTOR, "li.b_adTop")
    BOTTOM_ADS_CONTAINER = (By.CSS_SELECTOR, "li.b_adBottom")
    AD_RESULTS = (By.CSS_SELECTOR, "h2 > a:last-child")
    AD_CANON_LINK = (By.XPATH, "./../following-sibling::div//div[@class='b_adurl']")
    AD_CANON_LINK_2 = (By.XPATH, "./../../following-sibling::div//div[@class='b_adurl']")
    AD_CANON_LINK_3 = (By.XPATH, "./..//div[@class='b_adurl']")
    AD_CANON_LINK_4 = (By.XPATH, "./../..//div[@class='b_adurl']")
    NON_AD_LINKS = (By.CSS_SELECTOR, "li.b_algo")
    NON_AD_LINK_ELEMENT = (By.CSS_SELECTOR, "div.b_title h2 a")
    NON_AD_LINK_ELEMENT_2 = (By.CSS_SELECTOR, "div.b_algoheader a")
    NON_AD_LINK_ELEMENT_3 = (By.CSS_SELECTOR, "a.tilk")
    SHOPPING_ADS_CONTAINER = (By.CSS_SELECTOR, "div.b_cards2")
    SHOPPING_ADS_CONTAINER_2 = (By.CSS_SELECTOR, "div.pa_item")
    SHOPPING_AD_ELEMENT_CONTAINER = (By.CSS_SELECTOR, "li.pa_item")
    SHOPPING_AD_ELEMENT = (By.TAG_NAME, "a")
    SHOPPING_AD_TITLE_1 = (By.TAG_NAME, "h3")
    SHOPPING_AD_TITLE_2 = (By.CSS_SELECTOR, "div.pa_title")
    SHOPPING_AD_CANON_LINK_1 = (By.CSS_SELECTOR, "div.pa_url")
    SHOPPING_AD_CANON_LINK_2 = (By.CSS_SELECTOR, "div.b_attribution")
    RECAPTCHA = (By.ID, "recaptcha")

    def __init__(
        self, driver: selenium.webdriver, query: str, country_code: Optional[str] = None
    ) -> None:
        self._driver = driver
        self._search_query, self._filter_words = self._process_query(query)
        self._exclude_list = None
        self._random_mouse_enabled = config.behavior.random_mouse
        self._use_custom_cookies = config.behavior.custom_cookies
        self._twocaptcha_apikey = config.behavior.twocaptcha_apikey
        self._max_scroll_limit = config.behavior.max_scroll_limit
        self._hooks_enabled = config.behavior.hooks_enabled

        self._ad_page_min_wait = config.behavior.ad_page_min_wait
        self._ad_page_max_wait = config.behavior.ad_page_max_wait
        self._nonad_page_min_wait = config.behavior.nonad_page_min_wait
        self._nonad_page_max_wait = config.behavior.nonad_page_max_wait

        self._stats = SearchStats()

        if config.behavior.excludes:
            self._exclude_list = [item.strip() for item in config.behavior.excludes.split(",")]
            logger.debug(f"Words to be excluded: {self._exclude_list}")

        if country_code:
            self._set_start_url(country_code)

        self._clicklogs_db_client = ClickLogsDB()

        self._load()

    def search_for_ads(
        self, non_ad_domains: Optional[list[str]] = None
    ) -> tuple[AdList, NonAdList]:
        """Start search for the given query and return ads if any

        Also, get non-ad links including domains given.

        :type non_ad_domains: list
        :param non_ad_domains: List of domains to select for non-ad links
        :rtype: tuple
        :returns: Tuple of [(ad, ad_link, ad_title), non_ad_links]
        """

        if self._use_custom_cookies:
            self._driver.delete_all_cookies()
            add_cookies(self._driver)

            for cookie in self._driver.get_cookies():
                logger.debug(cookie)

        self._check_captcha()
        self._close_cookie_dialog()

        logger.info(f"Starting search for '{self._search_query}'")
        sleep(get_random_sleep(1, 3))

        try:
            search_input_box = self._driver.find_element(*self.SEARCH_INPUT)
            search_input_box.send_keys(self._search_query, Keys.ENTER)

        except NoSuchElementException:
            # self._check_captcha()
            self._close_cookie_dialog()

            search_input_box = self._driver.find_element(*self.SEARCH_INPUT)
            search_input_box.send_keys(self._search_query, Keys.ENTER)

        # wait 3 to 5 seconds before checking if results were loaded
        sleep(get_random_sleep(3, 5))

        if self._hooks_enabled:
            hooks.after_query_sent_hook(self._driver, self._search_query)

        ad_links = []
        non_ad_links = []
        shopping_ad_links = []

        try:
            wait = WebDriverWait(self._driver, timeout=5)
            results_loaded = wait.until(EC.presence_of_element_located(self.RESULTS_CONTAINER))

            if results_loaded:
                if self._hooks_enabled:
                    hooks.results_ready_hook(self._driver)

                self._make_random_scrolls()
                self._make_random_mouse_movements()

                if config.behavior.check_shopping_ads:
                    shopping_ad_links = self._get_shopping_ad_links()

                ad_links = self._get_ad_links()
                non_ad_links = self._get_non_ad_links(non_ad_domains)

        except TimeoutException:
            logger.error("Timed out waiting for results!")
            self.end_search()

        return (ad_links, non_ad_links, shopping_ad_links)

    def click_shopping_ads(self, shopping_ads: AdList) -> None:
        """Click shopping ads if there are any

        :type ads: AdList
        :param ads: List of (ad, ad_link, ad_title, ad_canon_link) tuples
        """

        platform = sys.platform

        control_command_key = Keys.COMMAND if platform.endswith("darwin") else Keys.CONTROL

        # store the ID of the original window
        original_window_handle = self._driver.current_window_handle

        for ad in shopping_ads:
            try:
                ad_link_element = ad[0]
                ad_link = ad[1]
                ad_title = ad[2].replace("\n", " ")
                ad_canon_link = ad[3]
                logger.info(f"Clicking to [{ad_title}]({ad_link}) | {ad_canon_link}...")

                # open link in a different tab
                actions = ActionChains(self._driver)
                actions.move_to_element(ad_link_element)
                actions.key_down(control_command_key)
                actions.click()
                actions.key_up(control_command_key)
                actions.perform()
                sleep(get_random_sleep(0.5, 1))

                if len(self._driver.window_handles) != 2:
                    logger.debug("Couldn't click to shopping ad! Trying again...")

                    actions = ActionChains(self._driver)
                    actions.move_to_element(ad_link_element)
                    actions.key_down(control_command_key)
                    actions.click()
                    actions.key_up(control_command_key)
                    actions.perform()
                    sleep(get_random_sleep(0.5, 1))

                else:
                    logger.debug("Opened link in new a tab. Switching to tab...")

                for window_handle in self._driver.window_handles:
                    if window_handle != original_window_handle:
                        self._driver.switch_to.window(window_handle)

                        click_time = datetime.now().strftime("%H:%M:%S")

                        # wait a little before starting random actions
                        sleep(get_random_sleep(3, 6))

                        logger.debug(f"Current url on new tab: {self._driver.current_url}")

                        random_scroll_thread = Thread(target=self._make_random_scrolls)
                        random_scroll_thread.start()
                        random_mouse_thread = Thread(target=self._make_random_mouse_movements)
                        random_mouse_thread.start()

                        wait_time = random.choice(
                            range(self._ad_page_min_wait, self._ad_page_max_wait)
                        )
                        logger.debug(f"Waiting {wait_time} seconds on shopping ad page...")

                        self._stats.shopping_ads_clicked += 1
                        self._clicklogs_db_client.save_click(
                            site_url="/".join(self._driver.current_url.split("/", maxsplit=3)[:3]),
                            category="Shopping",
                            query=self._search_query,
                            click_time=click_time,
                        )

                        sleep(wait_time)

                        random_scroll_thread.join(timeout=float(self._ad_page_max_wait))
                        random_mouse_thread.join(timeout=float(self._ad_page_max_wait))

                        self._driver.close()
                        break

                # go back to original window
                self._driver.switch_to.window(original_window_handle)
                sleep(get_random_sleep(1, 1.5))

            except Exception:
                logger.debug(f"Failed to click ad element [{ad_title}]!")

    def click_links(self, links: AllLinks) -> None:
        """Click links

        :type links: AllLinks
        :param links: List of [(ad, ad_link, ad_title), non_ad_links]
        """

        platform = sys.platform

        control_command_key = Keys.COMMAND if platform.endswith("darwin") else Keys.CONTROL

        # store the ID of the original window
        original_window_handle = self._driver.current_window_handle

        for link in links:
            is_ad_element = isinstance(link, tuple)

            try:
                if is_ad_element:
                    link_element = link[0]
                    link_url = link[1]
                    ad_title = link[2]
                    canon_link = link[3]

                    if self._hooks_enabled:
                        hooks.before_ad_click_hook(self._driver)

                    logger.info(f"Clicking to [{ad_title}]({link_url}) | '{canon_link}'...")
                else:
                    link_element = link
                    link_url = link_element.get_attribute("href")

                    logger.info(f"Clicking to [{link_url}]...")

                # scroll the page to avoid elements remain outside of the view
                self._driver.execute_script("arguments[0].scrollIntoView(true);", link_element)
                sleep(get_random_sleep(0.5, 1))

                # open link in a different tab
                actions = ActionChains(self._driver)
                actions.move_to_element(link_element)
                actions.key_down(control_command_key)
                actions.click()
                actions.key_up(control_command_key)
                actions.perform()
                sleep(get_random_sleep(0.5, 1))

                if len(self._driver.window_handles) != 2:
                    logger.debug("Couldn't click! Scrolling element into view...")

                    self._driver.execute_script("arguments[0].scrollIntoView(true);", link_element)

                    actions = ActionChains(self._driver)
                    actions.move_to_element(link_element)
                    actions.key_down(control_command_key)
                    actions.click()
                    actions.key_up(control_command_key)
                    actions.perform()
                    sleep(get_random_sleep(0.5, 1))

                else:
                    logger.debug("Opened link in a new tab. Switching to tab...")

                for window_handle in self._driver.window_handles:
                    if window_handle != original_window_handle:
                        self._driver.switch_to.window(window_handle)

                        click_time = datetime.now().strftime("%H:%M:%S")

                        # wait a little before starting random actions
                        sleep(get_random_sleep(3, 6))

                        logger.debug(f"Current url on new tab: {self._driver.current_url}")

                        if self._hooks_enabled:
                            hooks.after_ad_click_hook(self._driver)

                        random_scroll_thread = Thread(target=self._make_random_scrolls)
                        random_scroll_thread.start()
                        random_mouse_thread = Thread(target=self._make_random_mouse_movements)
                        random_mouse_thread.start()

                        if is_ad_element:
                            wait_time = random.choice(
                                range(self._ad_page_min_wait, self._ad_page_max_wait)
                            )
                            logger.debug(f"Waiting {wait_time} seconds on ad page...")

                            self._stats.ads_clicked += 1
                            self._clicklogs_db_client.save_click(
                                site_url=canon_link,
                                category="Ad",
                                query=self._search_query,
                                click_time=click_time,
                            )

                            sleep(wait_time)
                        else:
                            wait_time = random.choice(
                                range(self._nonad_page_min_wait, self._nonad_page_max_wait)
                            )
                            logger.debug(f"Waiting {wait_time} seconds on non-ad page...")

                            self._stats.non_ads_clicked += 1
                            self._clicklogs_db_client.save_click(
                                site_url=self._driver.current_url,
                                category="Non-ad",
                                query=self._search_query,
                                click_time=click_time,
                            )

                            sleep(wait_time)

                        random_scroll_thread.join(
                            timeout=float(max(self._ad_page_max_wait, self._nonad_page_max_wait))
                        )
                        random_mouse_thread.join(
                            timeout=float(max(self._ad_page_max_wait, self._nonad_page_max_wait))
                        )

                        self._driver.close()
                        break

                # go back to original window
                self._driver.switch_to.window(original_window_handle)
                sleep(get_random_sleep(1, 1.5))

            except StaleElementReferenceException:
                logger.debug(
                    f"Ad element [{ad_title if is_ad_element else link_url}] has changed. Skipping scroll into view..."
                )

    def end_search(self) -> None:
        """Close the browser.

        Delete cookies and cache before closing.
        """

        if self._driver:
            try:
                self._delete_cache_and_cookies()
                self._driver.quit()

            except Exception as exp:
                logger.debug(exp)

            self._driver = None

    def _load(self) -> None:
        """Load Google main page"""

        self._driver.get(self.URL)

    def _get_shopping_ad_links(self) -> AdList:
        """Extract shopping ad links to click if exists

        :rtype: AdList
        :returns: List of (ad, ad_link, ad_title, ad_canon_link) tuples
        """

        ads = []

        try:
            logger.info("Checking shopping ads...")

            s_ads_container = self._driver.find_element(*self.TOP_ADS_CONTAINER)
            shopping_ads = s_ads_container.find_elements(*self.SHOPPING_ADS_CONTAINER)

            if shopping_ads:
                for shopping_ad in shopping_ads[:5]:
                    ad = shopping_ad.find_element(*self.SHOPPING_AD_ELEMENT_CONTAINER)
                    shopping_ad_element = ad.find_element(*self.SHOPPING_AD_ELEMENT)
                    shopping_ad_link = shopping_ad_element.get_attribute("href")
                    shopping_ad_title = (
                        ad.find_element(*self.SHOPPING_AD_TITLE_1).text.strip().replace("\n", " ")
                    )
                    shopping_ad_canon_link = ad.find_element(*self.SHOPPING_AD_CANON_LINK_1).text

                    ad_fields = (
                        shopping_ad_element,
                        shopping_ad_link,
                        shopping_ad_title,
                        shopping_ad_canon_link,
                    )
                    logger.debug(ad_fields)

                    ads.append(ad_fields)
            else:
                # try with different selector
                shopping_ads = self._driver.find_elements(*self.SHOPPING_ADS_CONTAINER_2)

                for shopping_ad in shopping_ads[:5]:
                    shopping_ad_element = shopping_ad.find_element(*self.SHOPPING_AD_ELEMENT)
                    shopping_ad_link = shopping_ad_element.get_attribute("href")
                    shopping_ad_title = (
                        shopping_ad_element.find_element(*self.SHOPPING_AD_TITLE_2)
                        .text.strip()
                        .replace("\n", " ")
                    )
                    shopping_ad_canon_link = shopping_ad.find_element(
                        *self.SHOPPING_AD_CANON_LINK_2
                    ).text

                    ad_fields = (
                        shopping_ad_element,
                        shopping_ad_link,
                        shopping_ad_title,
                        shopping_ad_canon_link,
                    )
                    logger.debug(ad_fields)

                    ads.append(ad_fields)

            self._stats.shopping_ads_found = len(ads)

            if not ads:
                return []

            # if there are filter words given, filter results accordingly
            filtered_ads = []

            if self._filter_words:
                for ad in ads:
                    ad_link = ad[1]
                    ad_title = ad[2].replace("\n", " ")
                    ad_canon_link = ad[3].lower()

                    for word in self._filter_words:
                        if word in ad_canon_link or word in ad_title.lower():
                            if ad not in filtered_ads:
                                logger.debug(f"Filtering [{ad_title}]: {ad_link} | {ad_canon_link}")
                                self._stats.num_filtered_shopping_ads += 1
                                filtered_ads.append(ad)
            else:
                filtered_ads = ads

            shopping_ad_links = []

            for ad in filtered_ads:
                ad_link = ad[1]
                ad_title = ad[2].replace("\n", " ")
                ad_canon_link = ad[3].lower()
                logger.debug(f"Ad title: {ad_title}, Ad link: {ad_link} | {ad_canon_link}")

                if self._exclude_list:
                    for exclude_item in self._exclude_list:
                        if (
                            exclude_item in ad_canon_link
                            or exclude_item.lower() in ad_title.lower()
                        ):
                            logger.debug(f"Excluding [{ad_title}]: {ad_link} | {ad_canon_link}")
                            self._stats.num_excluded_shopping_ads += 1
                            break
                    else:
                        logger.info("======= Found a Shopping Ad =======")
                        shopping_ad_links.append((ad[0], ad_link, ad_title, ad_canon_link))
                else:
                    logger.info("======= Found a Shopping Ad =======")
                    shopping_ad_links.append((ad[0], ad_link, ad_title, ad_canon_link))

            return shopping_ad_links

        except NoSuchElementException:
            logger.info("No shopping ads are shown!")

        return ads

    def _get_ad_links(self) -> AdList:
        """Extract ad links to click

        :rtype: AdList
        :returns: List of (ad, ad_link, ad_title, canon_link) tuples
        """

        logger.info("Getting ad links...")

        ads = []

        scroll_count = 0

        logger.debug(f"Max scroll limit: {self._max_scroll_limit}")

        while not self._is_scroll_at_the_end():
            try:
                top_ads_containers = self._driver.find_elements(*self.TOP_ADS_CONTAINER)
                for ad_container in top_ads_containers:
                    ads.extend(ad_container.find_elements(*self.AD_RESULTS))

            except NoSuchElementException:
                logger.debug("Could not found top ads!")

            try:
                bottom_ads_containers = self._driver.find_elements(*self.BOTTOM_ADS_CONTAINER)
                for ad_container in bottom_ads_containers:
                    ads.extend(ad_container.find_elements(*self.AD_RESULTS))

            except NoSuchElementException:
                logger.debug("Could not found bottom ads!")

            if self._max_scroll_limit > 0:
                if scroll_count == self._max_scroll_limit:
                    logger.debug("Reached to max scroll limit! Ending scroll...")
                    break

            self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
            sleep(get_random_sleep(2, 2.5))

            scroll_count += 1

        if not ads:
            return []

        # clean non-ad links and duplicates
        cleaned_ads = []
        links = []

        for ad in ads:
            ad_link = ad.get_attribute("href")

            if ad_link not in links:
                links.append(ad_link)
                cleaned_ads.append(ad)

        self._stats.ads_found = len(cleaned_ads)

        # if there are filter words given, filter results accordingly
        filtered_ads = []

        if self._filter_words:
            for ad in cleaned_ads:
                ad_title = ad.text.strip().lower()
                ad_link = ad.get_attribute("href")

                try:
                    canon_link_element = ad.find_element(*self.AD_CANON_LINK)
                except NoSuchElementException:
                    logger.debug("Checking with second alternative canonical link selector...")

                    try:
                        canon_link_element = ad.find_element(*self.AD_CANON_LINK_2)
                    except NoSuchElementException:
                        logger.debug("Checking with third alternative canonical link selector...")

                        try:
                            canon_link_element = ad.find_element(*self.AD_CANON_LINK_3)
                        except NoSuchElementException:
                            logger.debug(
                                "Checking with fourth alternative canonical link selector..."
                            )
                            try:
                                canon_link_element = ad.find_element(*self.AD_CANON_LINK_4)
                            except Exception:
                                logger.debug("Skipping...")
                                continue

                canon_link = canon_link_element.text.strip()

                logger.debug(f"canonical_link: '{canon_link}'")

                for word in self._filter_words:
                    if word in canon_link or word in ad_title:
                        if ad not in filtered_ads:
                            logger.debug(f"Filtering [{ad_title}]: {ad_link} | '{canon_link}'")
                            self._stats.num_filtered_ads += 1
                            filtered_ads.append(ad)
        else:
            filtered_ads = cleaned_ads

        ad_links = []

        for ad in filtered_ads:
            ad_link = ad.get_attribute("href")
            ad_title = ad.text.strip()

            try:
                canon_link_element = ad.find_element(*self.AD_CANON_LINK)
            except NoSuchElementException:
                logger.debug("Checking with second alternative canonical link selector...")

                try:
                    canon_link_element = ad.find_element(*self.AD_CANON_LINK_2)
                except NoSuchElementException:
                    logger.debug("Checking with third alternative canonical link selector...")

                    try:
                        canon_link_element = ad.find_element(*self.AD_CANON_LINK_3)
                    except NoSuchElementException:
                        logger.debug("Checking with fourth alternative canonical link selector...")
                        try:
                            canon_link_element = ad.find_element(*self.AD_CANON_LINK_4)
                        except Exception:
                            logger.debug("Skipping...")
                            continue

            canon_link = canon_link_element.text.strip()
            logger.debug(f"Ad title: {ad_title}, Ad link: {ad_link} | '{canon_link}'")

            if self._exclude_list:
                for exclude_item in self._exclude_list:
                    if exclude_item in canon_link or exclude_item.lower() in ad_title.lower():
                        logger.debug(f"Excluding [{ad_title}]: {ad_link} | '{canon_link}'")
                        self._stats.num_excluded_ads += 1
                        break
                else:
                    logger.info("======= Found an Ad =======")
                    ad_links.append((ad, ad_link, ad_title, canon_link))
            else:
                logger.info("======= Found an Ad =======")
                ad_links.append((ad, ad_link, ad_title, canon_link))

        return ad_links

    def _get_non_ad_links(self, non_ad_domains: Optional[list[str]] = None) -> NonAdList:
        """Extract non-ad link elements

        :type non_ad_domains: list
        :param non_ad_domains: List of domains to select for non-ad links
        :rtype: NonAdList
        :returns: List of non-ad link elements
        """

        logger.info("Getting non-ad links...")

        # go to top of the page
        self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.HOME)

        all_links = self._driver.find_elements(*self.NON_AD_LINKS)

        logger.debug(f"Number of non-ad links: {len(all_links)}")

        self._stats.non_ads_found = len(all_links)

        non_ad_links = []

        for link in all_links:
            try:
                link_element = link.find_element(*self.NON_AD_LINK_ELEMENT)
            except NoSuchElementException:
                logger.debug("Checking with second alternative non-ad selector...")

                try:
                    link_element = link.find_element(*self.NON_AD_LINK_ELEMENT_2)
                except NoSuchElementException:
                    logger.debug("Checking with third alternative non-ad selector...")

                    try:
                        link_element = link.find_element(*self.NON_AD_LINK_ELEMENT_3)
                    except NoSuchElementException:
                        logger.debug(
                            "Couldn't found non-ad link element in "
                            f"[{link.get_attribute('outerHTML')}]! Skipping..."
                        )
                        continue

            link_url = link_element.get_attribute("href")

            if non_ad_domains:
                logger.debug(f"Evaluating [{link_url}] to add as non-ad link...")

                for domain in non_ad_domains:
                    if domain in link_url:
                        logger.debug(f"Adding [{link_url}] to non-ad links")
                        self._stats.num_filtered_non_ads += 1
                        non_ad_links.append(link_element)
                        break
            else:
                logger.debug(f"Adding [{link_url}] to non-ad links")
                non_ad_links.append(link_element)

        logger.info(f"Found {len(non_ad_links)} non-ad links")

        # if there is no domain to filter, randomly select 3 links
        if not non_ad_domains and len(non_ad_links) > 3:
            logger.info("Randomly selecting 3 from non-ad links...")
            non_ad_links = random.sample(non_ad_links, k=3)

        return non_ad_links

    def _close_cookie_dialog(self) -> None:
        """If cookie dialog is opened, close it by accepting"""

        logger.debug("Waiting for cookie dialog...")

        sleep(get_random_sleep(3, 3.5))

        try:
            cookie_dialog = self._driver.find_element(*self.COOKIE_DIALOG_CONTAINER)
            accept_button = cookie_dialog.find_element(*self.COOKIE_DIALOG_BUTTON)

            logger.info("Closing cookie dialog by accepting...")
            accept_button.click()
            sleep(get_random_sleep(1, 1.5))

        except NoSuchElementException:
            logger.debug("No cookie dialog found! Continue with search...")

    def _is_scroll_at_the_end(self) -> bool:
        """Check if scroll is at the end

        :rtype: bool
        :returns: Whether the scrollbar was reached to end or not
        """

        page_height = self._driver.execute_script("return document.body.scrollHeight;")
        total_scrolled_height = self._driver.execute_script(
            "return window.pageYOffset + window.innerHeight;"
        )

        return page_height - 1 <= total_scrolled_height

    def _delete_cache_and_cookies(self) -> None:
        """Delete browser cache, storage, and cookies"""

        logger.debug("Deleting browser cache and cookies...")

        try:
            self._driver.delete_all_cookies()

            self._driver.execute_cdp_cmd("Network.clearBrowserCache", {})
            self._driver.execute_cdp_cmd("Network.clearBrowserCookies", {})
            self._driver.execute_script("window.localStorage.clear();")
            self._driver.execute_script("window.sessionStorage.clear();")

        except Exception as exp:
            if "not connected to DevTools" in str(exp):
                logger.debug("Incognito mode is active. No need to delete cache. Skipping...")

    def _set_start_url(self, country_code: str) -> None:
        """Set start url according to country code of the proxy IP

        :type country_code: str
        :param country_code: Country code for the proxy IP
        """

        with open("domain_mapping.json", "r") as domains_file:
            domains = json.load(domains_file)

        country_domain = domains.get(country_code, "www.google.com")
        self.URL = f"https://{country_domain}"

        logger.debug(f"Start url was set to {self.URL}")

    def _make_random_scrolls(self) -> None:
        """Make random scrolls on page"""

        logger.debug("Making random scrolls...")

        directions = [Direction.DOWN]
        directions += random.choices(
            [Direction.UP] * 5 + [Direction.DOWN] * 5, k=random.choice(range(1, 5))
        )

        logger.debug(f"Direction choices: {[d.value for d in directions]}")

        for direction in directions:
            if direction == Direction.DOWN and not self._is_scroll_at_the_end():
                self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_DOWN)
            elif direction == Direction.UP:
                self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.PAGE_UP)

            sleep(get_random_sleep(1, 3))

        self._driver.find_element(By.TAG_NAME, "body").send_keys(Keys.HOME)

    def _make_random_mouse_movements(self) -> None:
        """Make random mouse movements"""

        if self._random_mouse_enabled:
            import pyautogui

            logger.debug("Making random mouse movements...")

            screen_width, screen_height = pyautogui.size()
            pyautogui.moveTo(screen_width / 2 - 300, screen_height / 2 - 200)

            logger.debug(pyautogui.position())

            ease_methods = [pyautogui.easeInQuad, pyautogui.easeOutQuad, pyautogui.easeInOutQuad]

            logger.debug("Going LEFT and DOWN...")

            pyautogui.move(
                -random.choice(range(200, 300)),
                random.choice(range(250, 450)),
                1,
                random.choice(ease_methods),
            )

            logger.debug(pyautogui.position())

            for _ in range(1, random.choice(range(3, 7))):
                direction = random.choice(list(Direction))
                ease_method = random.choice(ease_methods)

                logger.debug(f"Going {direction.value}...")

                if direction == Direction.LEFT:
                    pyautogui.move(-(random.choice(range(100, 200))), 0, 0.5, ease_method)

                elif direction == Direction.RIGHT:
                    pyautogui.move(random.choice(range(200, 400)), 0, 0.3, ease_method)

                elif direction == Direction.UP:
                    pyautogui.move(0, -(random.choice(range(100, 200))), 1, ease_method)
                    pyautogui.scroll(random.choice(range(1, 7)))

                elif direction == Direction.DOWN:
                    pyautogui.move(0, random.choice(range(150, 300)), 0.7, ease_method)
                    pyautogui.scroll(-random.choice(range(1, 7)))

                else:
                    pyautogui.move(
                        random.choice(range(100, 200)),
                        random.choice(range(150, 250)),
                        1,
                        ease_method,
                    )

                logger.debug(pyautogui.position())

    def _check_captcha(self) -> None:
        """Check if captcha exists and solve it if 2captcha is used, otherwise exit"""

        sleep(get_random_sleep(2, 2.5))

        try:
            captcha = self._driver.find_element(*self.RECAPTCHA)

            if captcha:
                logger.error("Captcha was shown.")

                if self._hooks_enabled:
                    hooks.captcha_seen_hook(self._driver)

                self._stats.captcha_seen = True

                if not self._twocaptcha_apikey:
                    logger.info("Please try with a different proxy or enable 2captcha service.")
                    logger.info(self.stats)
                    raise SystemExit()

                cookies = ";".join(
                    [f"{cookie['name']}:{cookie['value']}" for cookie in self._driver.get_cookies()]
                )

                logger.debug(f"Cookies: {cookies}")

                sitekey = captcha.get_attribute("data-sitekey")
                data_s = captcha.get_attribute("data-s")

                logger.debug(f"data-sitekey: {sitekey}, data-s: {data_s}")

                response_code = solve_recaptcha(
                    apikey=self._twocaptcha_apikey,
                    sitekey=sitekey,
                    current_url=self._driver.current_url,
                    data_s=data_s,
                    cookies=cookies,
                )

                if response_code:
                    logger.info("Captcha was solved.")

                    self._stats.captcha_solved = True

                    captcha_redirect_url = (
                        f"{self._driver.current_url}&g-recaptcha-response={response_code}"
                    )
                    self._driver.get(captcha_redirect_url)

                    sleep(get_random_sleep(2, 2.5))

                else:
                    logger.info("Please try with a different proxy.")

                    self._driver.quit()

                    raise SystemExit()

        except NoSuchElementException:
            logger.debug("No captcha seen. Continue to search...")

    def set_browser_id(self, browser_id: Optional[int] = None) -> None:
        """Set browser id in stats if multiple browsers are used

        :type browser_id: int
        :param browser_id: Browser id to separate instances in log for multiprocess runs
        """

        self._stats.browser_id = browser_id

    @staticmethod
    def _process_query(query: str) -> tuple[str, list[str]]:
        """Extract search query and filter words from the query input

        Query and filter words are splitted with "@" character. Multiple
        filter words can be used by separating with "#" character.

        e.g. wireless keyboard@amazon#ebay
             bluetooth headphones @ sony # amazon  #bose

        :type query: str
        :param query: Query string with optional filter words
        :rtype tuple
        :returns: Search query and list of filter words if any
        """

        search_query = query.split("@")[0].strip()

        filter_words = []

        if "@" in query:
            filter_words = [word.strip().lower() for word in query.split("@")[1].split("#")]

        if filter_words:
            logger.debug(f"Filter words: {filter_words}")

        return (search_query, filter_words)

    @property
    def stats(self) -> SearchStats:
        """Return search statistics data

        :rtype: SearchStats
        :returns: Search statistics data
        """

        return self._stats
