#!/usr/bin/env python3
"""
Battery Saver - Automatic Low Power Mode Manager for macOS
Copyright (c) 2025 Daniel
Licensed under the MIT License
"""

import rumps
import subprocess
import json
import os
from typing import Dict, Any, Optional
import time

try:
    import AppKit  # type: ignore
    info = AppKit.NSBundle.mainBundle().infoDictionary()
    if info is not None:
        info["LSUIElement"] = "1"
    else:
        # If running as a script, we can still try to set the activation policy
        from AppKit import NSApplication, NSApplicationActivationPolicyAccessory
        NSApplication.sharedApplication().setActivationPolicy_(NSApplicationActivationPolicyAccessory)
except Exception:
    # Non-fatal: if AppKit unavailable (e.g., tests), fall back to default behavior.
    pass


class BatterySaver(rumps.App):
    """Menu bar app to automatically enable Low Power Mode at specified battery levels."""

    def __init__(self):
        self.icon_path = os.path.join(
            os.path.dirname(os.path.abspath(__file__)),
            "assets",
            "icons",
            "battery_optimizer_menubar.png"
        )
        super(BatterySaver, self).__init__(
            "Battery Optimizer",
            title="",
            icon=self.icon_path if os.path.exists(self.icon_path) else None,
            template=False,
            quit_button=None
        )

        self.config_path = os.path.join(
            os.path.expanduser("~"),
            ".battery_saver_config.json"
        )

        # Load configuration
        self.config = self.load_config()
        self.threshold = self.config.get("threshold", 80)  # Ceiling
        self.floor_threshold = self.config.get("floor_threshold", 20) # Floor
        self.floor_enabled = self.config.get("floor_enabled", True)
        self.ceiling_enabled = self.config.get("ceiling_enabled", True)
        
        self.notification_shown = False
        self.last_battery_level = 100

        # Build Ceiling Threshold submenu
        self.threshold_menu = rumps.MenuItem(f"Ceiling Threshold: {self.threshold}%")
        self.build_threshold_submenu()
        
        # Build Floor Threshold submenu
        self.floor_menu = rumps.MenuItem(f"Floor Threshold: {self.floor_threshold}%")
        self.build_floor_submenu()

        # Dynamic toggle item for Ceiling
        self.ceiling_toggle_item = rumps.MenuItem(
            "Disable Ceiling" if self.ceiling_enabled else "Enable Ceiling", 
            callback=self.toggle_ceiling
        )

        # Dynamic toggle item for Floor
        self.floor_toggle_item = rumps.MenuItem(
            "Disable Floor" if self.floor_enabled else "Enable Floor", 
            callback=self.toggle_charging_floor
        )

        self.menu = [
            self.threshold_menu,
            self.floor_menu,
            rumps.separator,
            self.ceiling_toggle_item,
            self.floor_toggle_item,
            rumps.separator,
            rumps.MenuItem("Force Enable Charging", callback=self.force_enable_charging),
            rumps.separator,
            rumps.MenuItem("About", callback=self.show_about),
            rumps.separator,
            rumps.MenuItem("Quit", callback=self.quit_app)
        ]

        # Start monitoring
        self.timer = rumps.Timer(self.check_battery, 30)  # Check every 30 seconds
        self.timer.start()

        # Initial check
        self.update_icon()

    def load_config(self) -> Dict[str, Any]:
        """Load configuration from JSON file."""
        default_config = {
            "threshold": 80,
            "floor_threshold": 20,
            "floor_enabled": True,
            "ceiling_enabled": True,
            "notifications": True
        }

        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, 'r') as f:
                    return {**default_config, **json.load(f)}
            except Exception as e:
                print(f"Error loading config: {e}")
                return default_config
        return default_config

    def save_config(self):
        """Save configuration to JSON file."""
        try:
            with open(self.config_path, 'w') as f:
                json.dump({
                    "threshold": self.threshold,
                    "floor_threshold": self.floor_threshold,
                    "floor_enabled": self.floor_enabled,
                    "ceiling_enabled": self.ceiling_enabled,
                    "notifications": self.config.get("notifications", True)
                }, f, indent=2)
        except Exception as e:
            print(f"Error saving config: {e}")

    def get_battery_level(self) -> Optional[int]:
        """Get current battery percentage."""
        try:
            result = subprocess.run(
                ['pmset', '-g', 'batt'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                for line in result.stdout.split('\n'):
                    if '%' in line:
                        percentage_str = line.split('\t')[-1].split(';')[0].strip()
                        if '%' in percentage_str:
                            return int(percentage_str.replace('%', ''))
            return None
        except Exception as e:
            print(f"Error getting battery level: {e}")
            return None

    def is_on_battery(self) -> bool:
        """Check if Mac is running on battery power."""
        try:
            result = subprocess.run(
                ['pmset', '-g', 'batt'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                return 'Battery Power' in result.stdout
            return False
        except Exception as e:
            print(f"Error checking power source: {e}")
            return False

    def get_power_mode(self) -> Optional[int]:
        """Get current power mode (0=off, 1=on for low power mode)."""
        try:
            result = subprocess.run(
                ['pmset', '-g', 'custom'],
                capture_output=True,
                text=True,
                timeout=5
            )

            if result.returncode == 0:
                in_battery_section = False
                for line in result.stdout.split('\n'):
                    if 'Battery Power:' in line:
                        in_battery_section = True
                    elif 'AC Power:' in line:
                        in_battery_section = False
                    elif in_battery_section and 'lowpowermode' in line.lower():
                        parts = line.strip().split()
                        if len(parts) >= 2:
                            return int(parts[-1])
            return None
        except Exception as e:
            print(f"Error getting power mode: {e}")
            return None

    def set_power_mode(self, mode: int) -> bool:
        """Set low power mode."""
        try:
            result = subprocess.run(
                ['sudo', '-n', 'pmset', '-b', 'lowpowermode', str(mode)],
                capture_output=True,
                text=True,
                timeout=5
            )
            if result.returncode == 0:
                return True

            script = f'do shell script "pmset -b lowpowermode {mode}" with administrator privileges'
            result = subprocess.run(['osascript', '-e', script], capture_output=True, text=True, timeout=30)
            return result.returncode == 0
        except Exception as e:
            print(f"Error setting power mode: {e}")
            return False

    def check_battery(self, _) -> None:
        """Timer callback to check battery level."""
        battery_level = self.get_battery_level()
        if battery_level is None:
            return

        self.last_battery_level = battery_level
        self.update_icon()

        on_batt = self.is_on_battery()

        # Floor Logic (LPM)
        if self.floor_enabled and on_batt:
            if battery_level <= self.floor_threshold:
                if self.get_power_mode() != 1:
                    if self.set_power_mode(1) and not self.notification_shown:
                        rumps.notification(title="Battery Saver", subtitle=f"Battery at Floor ({battery_level}%)", message="Low Power Mode enabled")
                        self.notification_shown = True
            else:
                self.notification_shown = False
        
        # Ceiling Logic (Charging Cap)
        if self.ceiling_enabled and not on_batt:
            if battery_level >= self.threshold:
                # Use the battery utility to stop charging
                subprocess.run(['/usr/local/bin/battery', 'charging', 'off'], capture_output=True)

    def update_icon(self) -> None:
        """Update menu bar icon."""
        self.title = ""
        if os.path.exists(self.icon_path):
            self.icon = self.icon_path
        else:
            self.title = "🔋"

    def build_threshold_submenu(self):
        """Build ceiling threshold slider."""
        try: self.threshold_menu.clear()
        except: pass
        for percent in range(5, 100, 5):
            label = f"{'✓ ' if percent == self.threshold else '  '}{percent}%"
            self.threshold_menu.add(rumps.MenuItem(label, callback=self.change_threshold))

    def build_floor_submenu(self):
        """Build floor threshold slider."""
        try: self.floor_menu.clear()
        except: pass
        for percent in range(5, 100, 5):
            label = f"{'✓ ' if percent == self.floor_threshold else '  '}{percent}%"
            self.floor_menu.add(rumps.MenuItem(label, callback=self.change_floor_threshold))

    def change_threshold(self, sender):
        """Handle ceiling threshold change."""
        label = sender.title.replace("✓", "").replace(" ", "").replace("%", "")
        try:
            self.threshold = int(label)
            self.save_config()
            self.threshold_menu.title = f"Ceiling Threshold: {self.threshold}%"
            self.build_threshold_submenu()
            self._keep_menu_open()
        except ValueError: pass

    def change_floor_threshold(self, sender):
        """Handle floor threshold change."""
        label = sender.title.replace("✓", "").replace(" ", "").replace("%", "")
        try:
            self.floor_threshold = int(label)
            self.save_config()
            self.floor_menu.title = f"Floor Threshold: {self.floor_threshold}%"
            self.build_floor_submenu()
            self._keep_menu_open()
        except ValueError: pass

    def toggle_ceiling(self, sender) -> None:
        """Toggle the Ceiling cap."""
        self.ceiling_enabled = not self.ceiling_enabled
        if not self.ceiling_enabled:
            # Re-enable charging if we just disabled the cap
            subprocess.run(['/usr/local/bin/battery', 'charging', 'on'], capture_output=True)
        
        self.save_config()
        self.ceiling_toggle_item.title = "Disable Ceiling" if self.ceiling_enabled else "Enable Ceiling"
        self._keep_menu_open()

    def toggle_charging_floor(self, sender) -> None:
        """Toggle the Charging Floor (LPM)."""
        self.floor_enabled = not self.floor_enabled
        if not self.floor_enabled:
            self.set_power_mode(0)
            
        self.save_config()
        self.floor_toggle_item.title = "Disable Floor" if self.floor_enabled else "Enable Floor"
        self._keep_menu_open()

    def _keep_menu_open(self):
        """Hack to keep menu open by re-triggering it."""
        try:
            # This triggers the menu to stay/reappear on next event loop
            import AppKit
            NSApplication = AppKit.NSApplication.sharedApplication()
            event = AppKit.NSEvent.mouseEventWithType_location_modifierFlags_timestamp_windowNumber_context_eventNumber_clickCount_pressure_(
                AppKit.NSLeftMouseDown, (0, 0), 0, 0, 0, None, 0, 1, 1.0
            )
            # This is a complex way to simulate keeping it open, 
            # but for now simple state update is usually enough.
            pass
        except: pass

    def force_enable_charging(self, sender) -> None:
        """Force enable charging."""
        try:
            result = subprocess.run(['/usr/local/bin/battery', 'charging', 'on'], capture_output=True, text=True, timeout=10)
            if "smc" in result.stdout.lower():
                rumps.notification(title="Battery Saver", subtitle="Charging Forced ON", message="SMC charging re-enabled")
            self.update_icon()
        except Exception as e:
            rumps.alert(title="Error", message=f"Failed: {e}")
    @rumps.clicked("About")
    def show_about(self, _) -> None:
        """Show about information."""
        rumps.alert(
            title="BatesAI Battery Optimizer",
            message=f"Automatic Power Manager\n\nVersion: 1.0.3\nBuilt upon Battery Toolkit (github.com/actuallymentor/battery)\n\n© 2025 Daniel Alan Bates"
        )

    @rumps.clicked("Quit")
    def quit_app(self, _) -> None:
        """Quit the application."""
        rumps.quit_application()


if __name__ == "__main__":
    BatterySaver().run()
