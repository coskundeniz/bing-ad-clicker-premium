import json
import traceback
from typing import Optional

import customtkinter
from tkinter import filedialog

from config_reader import config
from logger import logger
from ad_clicker import main as ad_clicker_main
from run_ad_clicker import main as run_ad_clicker_main
from run_in_loop import main as run_in_loop_main


customtkinter.set_appearance_mode("dark")
customtkinter.set_default_color_theme("green")


class PathsFrame(customtkinter.CTkFrame):
    """Section for path inputs"""

    def __init__(self, master) -> None:
        super().__init__(master)

        self.grid_columnconfigure((0, 1, 2), weight=1)

        self.relative_width = master.winfo_screenwidth() // 100
        self.relative_height = master.winfo_screenheight() // 100

        self._title = customtkinter.CTkLabel(
            self, text="PATHS", height=30, fg_color="gray25", corner_radius=10
        )
        self._title.grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        self._query_file = self._add_path_input(
            row=1, label="Query file", default_value=config.paths.query_file
        )
        self._proxy_file = self._add_path_input(
            row=2, label="Proxy file", default_value=config.paths.proxy_file
        )
        self._user_agents = self._add_path_input(
            row=3, label="User agents", default_value=config.paths.user_agents
        )
        self._filtered_domains = self._add_path_input(
            row=4, label="Filtered domains", default_value=config.paths.filtered_domains
        )

    def open_file_dialog(self, textbox: customtkinter.CTkTextbox) -> None:
        """Open the file selection dialog

        :type textbox: customtkinter.CTkTextbox
        :param textbox: Related textbox widget
        """

        file_path = filedialog.askopenfilename(
            title="Select a file", filetypes=(("Text files", "*.txt"), ("All files", "*.*"))
        )

        # update the entry with the selected file path
        if file_path:
            textbox.delete("1.0", "end")
            textbox.insert("1.0", file_path)

    def get_paths(self) -> dict[str, str]:
        """Get selected path values

        :rtype: dict
        :returns: Dictionary of paths
        """

        return {
            "query_file": self._query_file.get("1.0", "end-1c"),
            "proxy_file": self._proxy_file.get("1.0", "end-1c"),
            "user_agents": self._user_agents.get("1.0", "end-1c"),
            "filtered_domains": self._filtered_domains.get("1.0", "end-1c"),
        }

    def _add_path_input(self, row: int, label: str, default_value: str) -> customtkinter.CTkTextbox:
        """Add input section to take path

        :type row: int
        :param row: Row index
        :type label: str
        :param label: Path field label
        :type default_value: str
        :param default_value: Config default value
        :rtype: customtkinter.CTkTextbox
        :returns: Textbox widget instance
        """

        path_label = customtkinter.CTkLabel(self, text=label)
        path_label.grid(row=row, column=0, padx=10, sticky="w")

        path_textbox = customtkinter.CTkTextbox(self, height=self.relative_height, corner_radius=10)
        path_textbox.grid(row=row, column=1, pady=5, sticky="ew")
        path_textbox.insert("1.0", default_value)

        open_file_button = customtkinter.CTkButton(
            self,
            text="Browse",
            height=self.relative_height * 3,
            command=lambda: self.open_file_dialog(path_textbox),
        )
        open_file_button.grid(row=row, column=2, padx=self.relative_width, pady=5, sticky="ew")

        return path_textbox


class WebdriverFrame(customtkinter.CTkFrame):
    """Section for webdriver inputs"""

    def __init__(self, master) -> None:
        super().__init__(master)

        self.grid_columnconfigure((0, 1, 2), weight=1)

        self.relative_width = master.winfo_screenwidth() // 100
        self.relative_height = master.winfo_screenheight() // 100

        self._title = customtkinter.CTkLabel(
            self, text="WEBDRIVER", height=30, fg_color="gray25", corner_radius=10
        )
        self._title.grid(row=0, column=0, columnspan=3, padx=10, pady=10, sticky="ew")

        self._proxy_input = self._add_input_field(row=1, label="Proxy")
        self._window_size_input = self._add_input_field(
            row=2, label="Window size", default_value=config.webdriver.window_size
        )

        self._auth_value = self._add_checkbox(
            row=3, column=0, label="Proxy Auth", enabled=config.webdriver.auth
        )
        self._incognito_value = self._add_checkbox(
            row=3, column=1, label="Incognito", enabled=config.webdriver.incognito
        )
        self._shift_windows_value = self._add_checkbox(
            row=3, column=2, label="Shift windows", enabled=config.webdriver.shift_windows
        )
        self._country_domain_value = self._add_checkbox(
            row=4, column=0, label="Country Domain", enabled=config.webdriver.country_domain
        )
        self._language_from_proxy = self._add_checkbox(
            row=4,
            column=1,
            label="Language From Proxy",
            enabled=config.webdriver.language_from_proxy,
        )
        self._ss_on_exception_value = self._add_checkbox(
            row=4, column=2, label="SS on Exception", enabled=config.webdriver.ss_on_exception
        )

    def get_webdriver_config(self) -> dict[str, str]:
        """Get webdriver config values

        :rtype: dict
        :returns: Dictionary of webdriver config values
        """

        return {
            "proxy": self._proxy_input.get("1.0", "end-1c"),
            "auth": self._auth_value.get(),
            "incognito": self._incognito_value.get(),
            "country_domain": self._country_domain_value.get(),
            "language_from_proxy": self._language_from_proxy.get(),
            "ss_on_exception": self._ss_on_exception_value.get(),
            "window_size": self._window_size_input.get("1.0", "end-1c"),
            "shift_windows": self._shift_windows_value.get(),
        }

    def _add_input_field(
        self, row: int, label: str, default_value: Optional[str] = None
    ) -> customtkinter.CTkTextbox:
        """Add input field

        :type row: int
        :param row: Row index
        :type label: str
        :param label: Input field label
        :type default_value: str
        :param default_value: Config default value
        :rtype: customtkinter.CTkTextbox
        :returns: Textbox widget instance
        """

        input_label = customtkinter.CTkLabel(self, text=label)
        input_label.grid(row=row, column=0, padx=10, sticky="w")

        input_textbox = customtkinter.CTkTextbox(
            self, height=self.relative_height, corner_radius=10
        )
        input_textbox.grid(row=row, column=1, columnspan=2, padx=10, pady=5, sticky="ew")

        if default_value:
            input_textbox.insert("1.0", default_value)

        return input_textbox

    def _add_checkbox(
        self, row: int, column: int, label: str, enabled: Optional[bool] = False
    ) -> customtkinter.CTkTextbox:
        """Add checkbox field for bool values

        :type row: int
        :param row: Row index
        :type column: int
        :param column: Column index
        :type label: str
        :param label: Checkbox label
        :type enabled: bool
        :param enabled: Whether checkbox is selected by default
        :rtype: customtkinter.BooleanVar
        :returns: Checkbox value variable
        """

        checkbox_value = customtkinter.BooleanVar()
        checkbox = customtkinter.CTkCheckBox(
            self,
            text=label,
            height=self.relative_height * 3,
            variable=checkbox_value,
        )
        checkbox.grid(row=row, column=column, padx=10, pady=5, sticky="w")

        if enabled:
            checkbox.select()

        return checkbox_value


class BehaviorFrame(customtkinter.CTkFrame):
    """Section for behavior inputs"""

    def __init__(self, master) -> None:
        super().__init__(master)

        self.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        self.relative_width = master.winfo_screenwidth() // 100
        self.relative_height = master.winfo_screenheight() // 100

        self._title = customtkinter.CTkLabel(
            self, text="BEHAVIOR", height=30, fg_color="gray25", corner_radius=10
        )
        self._title.grid(row=0, column=0, columnspan=6, padx=10, pady=10, sticky="ew")

        self._query_input = self._add_input_field(
            row=1, column=0, label="Query", default_value=config.behavior.query
        )
        self._2captcha_apikey_input = self._add_input_field(
            row=1,
            column=3,
            label="2captcha API Key",
            default_value=config.behavior.twocaptcha_apikey,
        )

        self._ad_page_min_wait_input = self._add_input_field(
            row=2,
            column=0,
            label="Ad page min wait",
            default_value=config.behavior.ad_page_min_wait,
        )
        self._ad_page_max_wait_input = self._add_input_field(
            row=2,
            column=3,
            label="Ad page max wait",
            default_value=config.behavior.ad_page_max_wait,
        )

        self._nonad_page_min_wait_input = self._add_input_field(
            row=3,
            column=0,
            label="Non-ad page min wait",
            default_value=config.behavior.nonad_page_min_wait,
        )
        self._nonad_page_max_wait_input = self._add_input_field(
            row=3,
            column=3,
            label="Non-ad page max wait",
            default_value=config.behavior.nonad_page_max_wait,
        )

        self._running_interval_start_input = self._add_input_field(
            row=4,
            column=0,
            label="Running interval start",
            default_value=config.behavior.running_interval_start,
        )
        self._running_interval_end_input = self._add_input_field(
            row=4,
            column=3,
            label="Running interval end",
            default_value=config.behavior.running_interval_end,
        )

        self._max_scroll_limit_input = self._add_input_field(
            row=5,
            column=0,
            label="Max scroll limit",
            default_value=str(config.behavior.max_scroll_limit),
        )
        self._click_order_input = self._add_input_field(
            row=5, column=3, label="Click order", default_value=config.behavior.click_order
        )

        self._browser_count_input = self._add_input_field(
            row=6, column=0, label="Browser count", default_value=config.behavior.browser_count
        )
        self._multiprocess_style_input = self._add_input_field(
            row=6,
            column=3,
            label="Multiprocess style",
            default_value=config.behavior.multiprocess_style,
        )

        self._loop_wait_time_input = self._add_input_field(
            row=7, column=0, label="Loop wait time", default_value=config.behavior.loop_wait_time
        )

        excludes_label = customtkinter.CTkLabel(self, text="Excludes")
        excludes_label.grid(row=8, column=0, padx=10, sticky="w")

        self._excludes_input = customtkinter.CTkTextbox(
            self, height=self.relative_height, corner_radius=10
        )
        self._excludes_input.grid(row=8, column=1, columnspan=5, padx=10, pady=5, sticky="ew")
        self._excludes_input.insert("1.0", config.behavior.excludes)

        self._check_shopping_ads_value = self._add_checkbox(
            row=9, column=0, label="Check shopping ads", enabled=config.behavior.check_shopping_ads
        )
        self._random_mouse_value = self._add_checkbox(
            row=9, column=1, label="Random mouse", enabled=config.behavior.random_mouse
        )
        self._custom_cookies_value = self._add_checkbox(
            row=9, column=2, label="Custom cookies", enabled=config.behavior.custom_cookies
        )
        self._hooks_enabled_value = self._add_checkbox(
            row=9, column=3, label="Hooks enabled", enabled=config.behavior.hooks_enabled
        )
        self._telegram_enabled_value = self._add_checkbox(
            row=9, column=4, label="Telegram enabled", enabled=config.behavior.telegram_enabled
        )

    def get_behavior_config(self) -> dict[str, str]:
        """Get behavior config values

        :rtype: dict
        :returns: Dictionary of behavior config values
        """

        return {
            "query": self._query_input.get("1.0", "end-1c"),
            "ad_page_min_wait": int(self._ad_page_min_wait_input.get("1.0", "end-1c")),
            "ad_page_max_wait": int(self._ad_page_max_wait_input.get("1.0", "end-1c")),
            "nonad_page_min_wait": int(self._nonad_page_min_wait_input.get("1.0", "end-1c")),
            "nonad_page_max_wait": int(self._nonad_page_max_wait_input.get("1.0", "end-1c")),
            "max_scroll_limit": int(self._max_scroll_limit_input.get("1.0", "end-1c")),
            "check_shopping_ads": self._check_shopping_ads_value.get(),
            "excludes": self._excludes_input.get("1.0", "end-1c"),
            "random_mouse": self._random_mouse_value.get(),
            "custom_cookies": self._custom_cookies_value.get(),
            "click_order": int(self._click_order_input.get("1.0", "end-1c")),
            "browser_count": int(self._browser_count_input.get("1.0", "end-1c")),
            "multiprocess_style": int(self._multiprocess_style_input.get("1.0", "end-1c")),
            "loop_wait_time": int(self._loop_wait_time_input.get("1.0", "end-1c")),
            "running_interval_start": self._running_interval_start_input.get("1.0", "end-1c"),
            "running_interval_end": self._running_interval_end_input.get("1.0", "end-1c"),
            "2captcha_apikey": self._2captcha_apikey_input.get("1.0", "end-1c"),
            "hooks_enabled": self._hooks_enabled_value.get(),
            "telegram_enabled": self._telegram_enabled_value.get(),
        }

    def _add_input_field(
        self, row: int, column: int, label: str, default_value: Optional[str] = None
    ) -> customtkinter.CTkTextbox:
        """Add input field

        :type row: int
        :param row: Row index
        :type column: int
        :param column: Column index
        :type label: str
        :param label: Input field label
        :type default_value: str
        :param default_value: Config default value
        :rtype: customtkinter.CTkTextbox
        :returns: Textbox widget instance
        """

        input_label = customtkinter.CTkLabel(self, text=label)
        input_label.grid(row=row, column=column, padx=10, sticky="w")

        input_textbox = customtkinter.CTkTextbox(
            self, height=self.relative_height, corner_radius=10
        )
        input_textbox.grid(row=row, column=column + 1, columnspan=2, padx=10, pady=5, sticky="ew")

        if default_value:
            input_textbox.insert("1.0", default_value)

        return input_textbox

    def _add_checkbox(
        self, row: int, column: int, label: str, enabled: Optional[bool] = False
    ) -> customtkinter.CTkTextbox:
        """Add checkbox field for bool values

        :type row: int
        :param row: Row index
        :type column: int
        :param column: Column index
        :type label: str
        :param label: Checkbox label
        :type enabled: bool
        :param enabled: Whether checkbox is selected by default
        :rtype: customtkinter.BooleanVar
        :returns: Checkbox value variable
        """

        checkbox_value = customtkinter.BooleanVar()
        checkbox = customtkinter.CTkCheckBox(
            self,
            text=label,
            height=self.relative_height * 3,
            variable=checkbox_value,
        )
        checkbox.grid(row=row, column=column, padx=10, pady=5, sticky="w")

        if enabled:
            checkbox.select()

        return checkbox_value


class ActionButtonsFrame(customtkinter.CTkFrame):
    """Section for action buttons"""

    def __init__(self, master) -> None:
        super().__init__(master)

        self.grid_columnconfigure((0, 1, 2, 3, 4, 5), weight=1)

        self.relative_width = master.winfo_screenwidth() // 100
        self.relative_height = master.winfo_screenheight() // 100

        self.save_button = customtkinter.CTkButton(
            self,
            text="Save Configuration",
            height=self.relative_height * 3,
            command=master.save_button_callback,
        )
        self.save_button.grid(row=3, column=0, columnspan=6, padx=10, pady=(20, 5), sticky="ew")

        self.run_button_1 = customtkinter.CTkButton(
            self,
            text="Run ad_clicker.py",
            height=self.relative_height * 3,
            command=master.ad_clicker_script,
        )
        self.run_button_1.grid(row=4, column=0, columnspan=3, padx=10, pady=5, sticky="ew")

        self.run_button_2 = customtkinter.CTkButton(
            self,
            text="Run run_ad_clicker.py",
            height=self.relative_height * 3,
            command=master.run_ad_clicker_script,
        )
        self.run_button_2.grid(row=4, column=3, columnspan=3, padx=10, pady=5, sticky="ew")

        self.run_button_3 = customtkinter.CTkButton(
            self,
            text="Run run_in_loop.py",
            height=self.relative_height * 3,
            command=master.run_in_loop_script,
        )
        self.run_button_3.grid(row=5, column=0, columnspan=6, padx=10, pady=5, sticky="ew")


class ConfigGUI(customtkinter.CTk):
    """UI for the configuration and run"""

    def __init__(self) -> None:
        super().__init__()

        self.title("Bing Ads Clicker Premium")
        self.geometry("1500x920")

        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=1)

        self.paths_frame = PathsFrame(self)
        self.paths_frame.grid(row=0, column=0, padx=10, sticky="nsew")

        self.webdriver_frame = WebdriverFrame(self)
        self.webdriver_frame.grid(row=0, column=1, padx=10, sticky="nsew")

        self.behavior_frame = BehaviorFrame(self)
        self.behavior_frame.grid(row=1, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

        self.action_buttons_frame = ActionButtonsFrame(self)
        self.action_buttons_frame.grid(row=2, column=0, columnspan=2, padx=10, pady=10, sticky="ew")

    def save_button_callback(self) -> None:
        """Save configuration to config.json file"""

        logger.info("Saving configuration...")

        config_data = {
            "paths": self.paths_frame.get_paths(),
            "webdriver": self.webdriver_frame.get_webdriver_config(),
            "behavior": self.behavior_frame.get_behavior_config(),
        }

        logger.debug(json.dumps(config_data, indent=4))

        with open("config.json", "w", encoding="utf-8") as config_file:
            json.dump(config_data, config_file, indent=4)

        logger.info("Configuration was saved successfully.")

        config.read_parameters()

    def ad_clicker_script(self):
        """Run the ad_clicker.py script"""

        self.close_config_ui()
        ad_clicker_main()

    def run_ad_clicker_script(self):
        """Run the run_ad_clicker.py script"""

        self.close_config_ui()
        run_ad_clicker_main()

    def run_in_loop_script(self):
        """Run the run_in_loop.py script"""

        self.close_config_ui()
        run_in_loop_main()

    def open_config_ui(self) -> None:
        """Open the gui"""

        logger.debug("Opening config ui...")

        self.mainloop()

    def close_config_ui(self) -> None:
        """Close the gui"""

        logger.debug("Closing config ui...")

        self.destroy()


if __name__ == "__main__":
    try:
        config_gui = ConfigGUI()
        config_gui.open_config_ui()

    except Exception as exp:
        logger.error("Exception occurred. See the details in the log file.")

        message = str(exp).split("\n")[0]
        logger.debug(f"Exception: {message}")
        details = traceback.format_tb(exp.__traceback__)
        logger.debug(f"Exception details: \n{''.join(details)}")

        logger.debug(f"Exception cause: {exp.__cause__}") if exp.__cause__ else None
