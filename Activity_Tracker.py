"""
Activity Tracker Desktop Application
Tracks user activities and provides pop-up insights/reminders

Usage:
    python activity_tracker.py       # run app
    python activity_tracker.py test  # run unit tests
"""

import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import psutil
import json
import time
import threading
import datetime
import os
import sys
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional
import logging
import unittest

# Optional Windows-only imports (guarded)
try:
    import win32gui
    import win32process
    _HAS_WIN32 = True
except Exception:
    _HAS_WIN32 = False

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('activity_tracker.log'),
        logging.StreamHandler()
    ]
)


@dataclass
class ActivityData:
    """Data class for storing activity information"""
    app_name: str
    window_title: str
    start_time: float
    duration: float = 0.0


class ActivityTracker:
    """Main activity tracking engine"""

    def __init__(self, data_file: str = "activity_data.json"):
        self.activities = defaultdict(float)  # app_name -> total_seconds
        self.current_activity: Optional[str] = None
        self.last_check_time = time.time()
        self.idle_time = 0.0
        self.active_time = 0.0
        self.session_start = time.time()
        self.daily_logs: List[Dict] = []
        self.is_tracking = True
        self.data_file = data_file
        self.load_data()

    def get_active_window(self) -> Optional[tuple]:
        """Get the currently active window information (Windows only)."""
        if not _HAS_WIN32:
            logging.debug("win32 not available; active window detection disabled.")
            return None

        try:
            window = win32gui.GetForegroundWindow()
            if not window:
                return None
            pid = win32process.GetWindowThreadProcessId(window)[1]
            if pid:
                process = psutil.Process(pid)
                app_name = process.name()
                window_title = win32gui.GetWindowText(window)
                return app_name, window_title
        except Exception as e:
            logging.error(f"Error getting active window: {e}")
        return None

    def track_activity(self):
        """Track current activity and update statistics."""
        current_time = time.time()
        time_delta = current_time - self.last_check_time
        if time_delta < 0:
            time_delta = 0

        window_info = self.get_active_window()

        if window_info:
            app_name, window_title = window_info
            self.activities[app_name] += time_delta
            self.active_time += time_delta

            # Log activity change
            if self.current_activity != app_name:
                self.daily_logs.append({
                    'timestamp': datetime.datetime.now().isoformat(),
                    'app_name': app_name,
                    'window_title': window_title,
                    'action': 'switched_to'
                })
                self.current_activity = app_name
        else:
            # No active window determined -> treat as idle
            self.idle_time += time_delta

        self.last_check_time = current_time
        # Save occasionally — keep file IO light
        if int(current_time) % 10 == 0:
            self.save_data()

    def get_statistics(self) -> Dict:
        """Get current activity statistics."""
        total_time = max(1.0, time.time() - self.session_start)
        return {
            'total_time': total_time,
            'active_time': self.active_time,
            'idle_time': self.idle_time,
            'activities': dict(self.activities),
            'top_apps': self.get_top_apps(5)
        }

    def get_top_apps(self, n=5) -> List[tuple]:
        """Get top n most used applications."""
        sorted_apps = sorted(self.activities.items(), key=lambda x: x[1], reverse=True)
        return sorted_apps[:n]

    def save_data(self):
        """Save activity data to file."""
        try:
            data = {
                'activities': dict(self.activities),
                'idle_time': self.idle_time,
                'active_time': self.active_time,
                'session_start': self.session_start,
                'daily_logs': self.daily_logs[-1000:]  # Keep last 1000 entries
            }
            with open(self.data_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving data: {e}")

    def load_data(self):
        """Load activity data from file."""
        try:
            if os.path.exists(self.data_file):
                with open(self.data_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    self.activities = defaultdict(float, data.get('activities', {}))
                    self.idle_time = data.get('idle_time', 0.0)
                    self.active_time = data.get('active_time', 0.0)
                    self.daily_logs = data.get('daily_logs', [])
                    self.session_start = data.get('session_start', self.session_start)
                    logging.info("Loaded previous activity data.")
        except Exception as e:
            logging.error(f"Error loading data: {e}")

    def clear_data(self):
        """Clear all activity data."""
        self.activities.clear()
        self.idle_time = 0.0
        self.active_time = 0.0
        self.session_start = time.time()
        self.daily_logs.clear()
        self.save_data()


class SettingsManager:
    """Manages application settings."""

    def __init__(self, settings_file: str = "settings.json"):
        self.settings_file = settings_file
        self.default_settings = {
            'reminders_enabled': True,
            'break_reminder_enabled': True,
            'break_interval': 30,  # minutes
            'app_usage_warnings': True,
            'entertainment_threshold': 2.0,  # hours
            'idle_warning_enabled': True,
            'idle_threshold': 15,  # minutes
            'tracking_interval': 5,  # seconds
            'popup_interval': 30  # minutes
        }
        self.settings = self.load_settings()

    def load_settings(self) -> Dict:
        """Load settings from file, merging with defaults."""
        try:
            if os.path.exists(self.settings_file):
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    loaded = json.load(f)
                    merged = self.default_settings.copy()
                    merged.update(loaded)
                    logging.info("Settings loaded and merged with defaults.")
                    return merged
        except Exception as e:
            logging.error(f"Error loading settings: {e}")
        return self.default_settings.copy()

    def save_settings(self):
        """Save settings to file."""
        try:
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(self.settings, f, indent=2)
        except Exception as e:
            logging.error(f"Error saving settings: {e}")

    def get_setting(self, key: str):
        """Get a specific setting value."""
        return self.settings.get(key, self.default_settings.get(key))

    def set_setting(self, key: str, value):
        """Set a specific setting value."""
        self.settings[key] = value
        self.save_settings()


class PopupManager:
    """Manages pop-up notifications."""
    def __init__(self, tracker: ActivityTracker, settings: SettingsManager):
        self.tracker = tracker
        self.settings = settings
        # next_break_time is the earliest timestamp at which we can show the next break reminder
        self.next_break_time = 0.0

        # entertainment app keywords (lowercase substrings)
        self.entertainment_keywords = ['chrome', 'firefox', 'discord', 'steam', 'spotify', 'youtube', 'netflix', 'edge']

    def show_simple_popup(self, title: str, message: str, kind: str = "info"):
        """
        Show a simple messagebox popup. Using tkinter messagebox is much safer from background threads
        than constructing a Toplevel root for every popup. It still may block the thread doing the call.
        """
        try:
            if kind == "info":
                messagebox.showinfo(title, message)
            elif kind == "warning":
                messagebox.showwarning(title, message)
            elif kind == "error":
                messagebox.showerror(title, message)
            else:
                messagebox.showinfo(title, message)
        except Exception as e:
            logging.error(f"Error showing popup: {e}")

    def snooze_break(self, seconds: int = 300):
        """Snooze the next break reminder for `seconds`."""
        self.next_break_time = time.time() + seconds

    def check_and_show_reminders(self):
        """Check conditions and show appropriate reminders."""
        if not self.settings.get_setting('reminders_enabled'):
            return

        stats = self.tracker.get_statistics()

        # Break reminders
        if self.settings.get_setting('break_reminder_enabled'):
            work_minutes = stats['active_time'] / 60.0
            break_interval = float(self.settings.get_setting('break_interval'))

            if work_minutes >= break_interval and time.time() >= self.next_break_time:
                # Show popup
                msg = (f"You've been active for {work_minutes:.0f} minutes. "
                       "Time for a short break to rest your eyes and stretch!")
                # Present simple popup with an option to snooze
                # We'll show a warning and then offer snooze via a second dialog.
                try:
                    # primary popup
                    self.show_simple_popup("Break Reminder", msg, kind="info")
                    # ask if user wants to snooze (Yes => snooze 5 min)
                    if messagebox.askyesno("Snooze?", "Snooze break reminder for 5 minutes?"):
                        self.snooze_break(300)
                    else:
                        # schedule next after the break interval
                        self.next_break_time = time.time() + break_interval * 60.0
                except Exception as e:
                    logging.error(f"Error during break reminder flow: {e}")

        # App usage warnings
        if self.settings.get_setting('app_usage_warnings'):
            threshold_hours = float(self.settings.get_setting('entertainment_threshold'))
            for app, duration_seconds in stats['activities'].items():
                duration_hours = duration_seconds / 3600.0
                app_l = app.lower()
                if any(keyword in app_l for keyword in self.entertainment_keywords):
                    if duration_hours > threshold_hours:
                        self.show_simple_popup(
                            "Usage Alert",
                            f"You've spent {duration_hours:.1f} hours on {app} today. Consider focusing on productive tasks.",
                            kind="warning"
                        )

        # Idle warning
        if self.settings.get_setting('idle_warning_enabled'):
            idle_minutes = stats['idle_time'] / 60.0
            idle_threshold = float(self.settings.get_setting('idle_threshold'))
            if idle_minutes > idle_threshold:
                self.show_simple_popup(
                    "Idle Alert",
                    f"You've been idle for {idle_minutes:.0f} minutes. Ready to get back to work?",
                    kind="info"
                )


class MainApplication:
    """Main GUI application"""

    def __init__(self):
        self.root = tk.Tk()
        self.root.title("Activity Tracker")
        self.root.geometry("900x650")

        # Initialize components
        self.settings = SettingsManager()
        self.tracker = ActivityTracker()
        self.popup_manager = PopupManager(self.tracker, self.settings)

        # Setup GUI
        self.setup_gui()

        # Start tracking
        self.tracking_thread = None
        self.start_tracking()

        # Schedule pop-ups (in background thread)
        self.schedule_popups()

    def setup_gui(self):
        """Setup the main GUI."""
        # Create notebook for tabs
        notebook = ttk.Notebook(self.root)
        notebook.pack(fill='both', expand=True)

        # Dashboard tab
        self.dashboard_frame = ttk.Frame(notebook)
        notebook.add(self.dashboard_frame, text="Dashboard")
        self.setup_dashboard()

        # Settings tab
        self.settings_frame = ttk.Frame(notebook)
        notebook.add(self.settings_frame, text="Settings")
        self.setup_settings()

        # Logs tab
        self.logs_frame = ttk.Frame(notebook)
        notebook.add(self.logs_frame, text="Activity Logs")
        self.setup_logs()

        # Control buttons
        control_frame = ttk.Frame(self.root)
        control_frame.pack(pady=10)

        self.toggle_button = tk.Button(control_frame, text="Pause Tracking",
                                       command=self.toggle_tracking, width=15)
        self.toggle_button.pack(side=tk.LEFT, padx=5)

        clear_button = tk.Button(control_frame, text="Clear Data",
                                 command=self.clear_data, width=15)
        clear_button.pack(side=tk.LEFT, padx=5)

        exit_button = tk.Button(control_frame, text="Exit",
                                command=self.exit_app, width=15)
        exit_button.pack(side=tk.LEFT, padx=5)

    def setup_dashboard(self):
        """Setup dashboard tab."""
        stats_label = tk.Label(self.dashboard_frame, text="Activity Statistics",
                               font=("Arial", 14, "bold"))
        stats_label.pack(pady=10)

        self.stats_text = scrolledtext.ScrolledText(self.dashboard_frame,
                                                    height=18, width=100)
        self.stats_text.pack(padx=10, pady=10)

        refresh_button = tk.Button(self.dashboard_frame, text="Refresh Stats",
                                   command=self.update_dashboard)
        refresh_button.pack(pady=5)

        self.update_dashboard()

    def setup_settings(self):
        """Setup settings tab."""
        settings_label = tk.Label(self.settings_frame, text="Application Settings",
                                  font=("Arial", 14, "bold"))
        settings_label.grid(row=0, column=0, columnspan=3, pady=10, sticky='w')

        # Reminders enabled
        self.reminders_var = tk.BooleanVar(value=self.settings.get_setting('reminders_enabled'))
        reminders_check = tk.Checkbutton(self.settings_frame, text="Enable Reminders",
                                         variable=self.reminders_var)
        reminders_check.grid(row=1, column=0, sticky='w', padx=20, pady=5)

        # Break reminder
        self.break_var = tk.BooleanVar(value=self.settings.get_setting('break_reminder_enabled'))
        break_check = tk.Checkbutton(self.settings_frame, text="Enable Break Reminders",
                                     variable=self.break_var)
        break_check.grid(row=2, column=0, sticky='w', padx=20, pady=5)

        tk.Label(self.settings_frame, text="Break Interval (minutes):").grid(
            row=2, column=1, sticky='w', padx=10)
        self.break_interval = tk.Spinbox(self.settings_frame, from_=10, to=120,
                                         width=8)
        self.break_interval.delete(0, tk.END)
        self.break_interval.insert(0, str(self.settings.get_setting('break_interval')))
        self.break_interval.grid(row=2, column=2, padx=10)

        # App usage warnings
        self.app_warnings_var = tk.BooleanVar(value=self.settings.get_setting('app_usage_warnings'))
        app_check = tk.Checkbutton(self.settings_frame, text="Enable App Usage Warnings",
                                   variable=self.app_warnings_var)
        app_check.grid(row=3, column=0, sticky='w', padx=20, pady=5)

        tk.Label(self.settings_frame, text="Entertainment Threshold (hours):").grid(
            row=3, column=1, sticky='w', padx=10)
        self.entertainment_threshold = tk.Spinbox(self.settings_frame, from_=0.5, to=24,
                                                 increment=0.5, width=8)
        self.entertainment_threshold.delete(0, tk.END)
        self.entertainment_threshold.insert(0, str(self.settings.get_setting('entertainment_threshold')))
        self.entertainment_threshold.grid(row=3, column=2, padx=10)

        # Idle warning
        self.idle_var = tk.BooleanVar(value=self.settings.get_setting('idle_warning_enabled'))
        idle_check = tk.Checkbutton(self.settings_frame, text="Enable Idle Warnings",
                                    variable=self.idle_var)
        idle_check.grid(row=4, column=0, sticky='w', padx=20, pady=5)

        tk.Label(self.settings_frame, text="Idle Threshold (minutes):").grid(
            row=4, column=1, sticky='w', padx=10)
        self.idle_threshold = tk.Spinbox(self.settings_frame, from_=5, to=60,
                                         width=8)
        self.idle_threshold.delete(0, tk.END)
        self.idle_threshold.insert(0, str(self.settings.get_setting('idle_threshold')))
        self.idle_threshold.grid(row=4, column=2, padx=10)

        # Tracking interval
        tk.Label(self.settings_frame, text="Tracking Interval (seconds):").grid(
            row=5, column=0, sticky='w', padx=20, pady=5)
        self.tracking_interval = tk.Spinbox(self.settings_frame, from_=1, to=30,
                                           width=8)
        self.tracking_interval.delete(0, tk.END)
        self.tracking_interval.insert(0, str(self.settings.get_setting('tracking_interval')))
        self.tracking_interval.grid(row=5, column=1, padx=10)

        # Popup interval
        tk.Label(self.settings_frame, text="Popup Check Interval (minutes):").grid(
            row=6, column=0, sticky='w', padx=20, pady=5)
        self.popup_interval = tk.Spinbox(self.settings_frame, from_=1, to=120,
                                        width=8)
        self.popup_interval.delete(0, tk.END)
        self.popup_interval.insert(0, str(self.settings.get_setting('popup_interval')))
        self.popup_interval.grid(row=6, column=1, padx=10)

        # Save button
        save_button = tk.Button(self.settings_frame, text="Save Settings",
                                command=self.save_settings, width=20)
        save_button.grid(row=7, column=0, columnspan=3, pady=20)

    def setup_logs(self):
        """Setup activity logs tab."""
        logs_label = tk.Label(self.logs_frame, text="Activity Logs",
                              font=("Arial", 14, "bold"))
        logs_label.pack(pady=10)

        self.logs_text = scrolledtext.ScrolledText(self.logs_frame,
                                                   height=22, width=100)
        self.logs_text.pack(padx=10, pady=10)

        button_frame = tk.Frame(self.logs_frame)
        button_frame.pack(pady=5)

        refresh_logs_button = tk.Button(button_frame, text="Refresh Logs",
                                        command=self.update_logs)
        refresh_logs_button.pack(side=tk.LEFT, padx=5)

        export_button = tk.Button(button_frame, text="Export Logs",
                                  command=self.export_logs)
        export_button.pack(side=tk.LEFT, padx=5)

        self.update_logs()

    def update_dashboard(self):
        """Update dashboard statistics."""
        stats = self.tracker.get_statistics()

        self.stats_text.delete(1.0, tk.END)

        text = f"Session Statistics\n{'='*60}\n\n"
        text += f"Total Session Time: {self.format_duration(stats['total_time'])}\n"
        text += f"Active Time: {self.format_duration(stats['active_time'])}\n"
        text += f"Idle Time: {self.format_duration(stats['idle_time'])}\n"

        if stats['total_time'] > 0:
            productivity = (stats['active_time'] / stats['total_time']) * 100
            text += f"Productivity: {productivity:.1f}%\n"

        text += f"\n{'='*60}\n"
        text += "Top Applications\n"
        text += f"{'='*60}\n\n"

        for i, (app, duration) in enumerate(stats['top_apps'], 1):
            text += f"{i}. {app}: {self.format_duration(duration)}\n"

        self.stats_text.insert(1.0, text)

    def update_logs(self):
        """Update activity logs display."""
        self.logs_text.delete(1.0, tk.END)

        logs = list(self.tracker.daily_logs[-50:])
        logs.reverse()  # Most recent first

        for log in logs:
            timestamp = log.get('timestamp', '')
            app_name = log.get('app_name', '')
            window_title = log.get('window_title', '')[:60]
            action = log.get('action', 'unknown')

            text = f"[{timestamp}] {action}: {app_name} - {window_title}\n"
            self.logs_text.insert(tk.END, text)

    def export_logs(self):
        """Export logs to a file."""
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"activity_logs_{timestamp}.json"

        try:
            with open(filename, 'w', encoding='utf-8') as f:
                json.dump({
                    'logs': self.tracker.daily_logs,
                    'statistics': self.tracker.get_statistics(),
                    'export_time': datetime.datetime.now().isoformat()
                }, f, indent=2)
            messagebox.showinfo("Export Successful", f"Logs exported to {filename}")
        except Exception as e:
            messagebox.showerror("Export Failed", f"Error exporting logs: {e}")

    def format_duration(self, seconds):
        """Format duration in seconds to readable string."""
        seconds = int(seconds)
        hours = seconds // 3600
        minutes = (seconds % 3600) // 60
        secs = seconds % 60

        if hours > 0:
            return f"{hours}h {minutes}m {secs}s"
        elif minutes > 0:
            return f"{minutes}m {secs}s"
        else:
            return f"{secs}s"

    def save_settings(self):
        """Save settings from GUI."""
        try:
            self.settings.set_setting('reminders_enabled', self.reminders_var.get())
            self.settings.set_setting('break_reminder_enabled', self.break_var.get())
            self.settings.set_setting('break_interval', int(self.break_interval.get()))
            self.settings.set_setting('app_usage_warnings', self.app_warnings_var.get())
            self.settings.set_setting('entertainment_threshold', float(self.entertainment_threshold.get()))
            self.settings.set_setting('idle_warning_enabled', self.idle_var.get())
            self.settings.set_setting('idle_threshold', int(self.idle_threshold.get()))
            self.settings.set_setting('tracking_interval', int(self.tracking_interval.get()))
            self.settings.set_setting('popup_interval', int(self.popup_interval.get()))

            messagebox.showinfo("Settings Saved", "Settings have been saved successfully!")
        except Exception as e:
            logging.error(f"Error saving GUI settings: {e}")
            messagebox.showerror("Error", f"Could not save settings: {e}")

    def start_tracking(self):
        """Start the activity tracking thread."""
        if self.tracking_thread is None or not self.tracking_thread.is_alive():
            self.tracker.is_tracking = True
            self.tracking_thread = threading.Thread(target=self.tracking_loop, daemon=True)
            self.tracking_thread.start()
            logging.info("Tracking started")

    def tracking_loop(self):
        """Main tracking loop."""
        while self.tracker.is_tracking:
            try:
                self.tracker.track_activity()
                time.sleep(self.settings.get_setting('tracking_interval'))
            except Exception as e:
                logging.error(f"Error in tracking loop: {e}")
                time.sleep(1)

    def schedule_popups(self):
        """Schedule periodic popup checks in separate thread."""
        def popup_check():
            while True:
                try:
                    if self.tracker.is_tracking:
                        self.popup_manager.check_and_show_reminders()
                    time.sleep(max(1, int(self.settings.get_setting('popup_interval')) * 60))
                except Exception as e:
                    logging.error(f"Error in popup scheduler: {e}")
                    time.sleep(5)

        popup_thread = threading.Thread(target=popup_check, daemon=True)
        popup_thread.start()

    def toggle_tracking(self):
        """Toggle tracking on/off."""
        if self.tracker.is_tracking:
            self.tracker.is_tracking = False
            self.toggle_button.config(text="Resume Tracking")
            logging.info("Tracking paused")
        else:
            self.start_tracking()
            self.toggle_button.config(text="Pause Tracking")

    def clear_data(self):
        """Clear all tracking data."""
        if messagebox.askyesno("Clear Data", "Are you sure you want to clear all activity data?"):
            self.tracker.clear_data()
            self.update_dashboard()
            self.update_logs()
            messagebox.showinfo("Data Cleared", "All activity data has been cleared.")

    def exit_app(self):
        """Exit the application."""
        if messagebox.askyesno("Exit", "Are you sure you want to exit?"):
            self.tracker.is_tracking = False
            self.tracker.save_data()
            try:
                self.root.destroy()
            except Exception:
                pass
            sys.exit(0)

    def run(self):
        """Run the main application."""
        self.root.protocol("WM_DELETE_WINDOW", self.exit_app)

        # Auto-update dashboard every 30 seconds
        def auto_update():
            try:
                self.update_dashboard()
                self.root.after(30000, auto_update)
            except Exception as e:
                logging.error(f"Error in auto_update: {e}")
        auto_update()

        # Start Tk mainloop
        self.root.mainloop()


# Unit tests
class TestActivityTracker(unittest.TestCase):
    """Unit tests for ActivityTracker"""

    def setUp(self):
        # Use a temporary data file for tests to avoid clobbering real data
        self.tracker = ActivityTracker(data_file="test_activity_data.json")

    def tearDown(self):
        try:
            os.remove("test_activity_data.json")
        except Exception:
            pass

    def test_initialization(self):
        self.assertIsNotNone(self.tracker.activities)
        self.assertEqual(self.tracker.idle_time, 0.0)
        self.assertTrue(self.tracker.is_tracking)

    def test_statistics(self):
        stats = self.tracker.get_statistics()
        self.assertIn('total_time', stats)
        self.assertIn('active_time', stats)
        self.assertIn('idle_time', stats)
        self.assertIn('activities', stats)

    def test_clear_data(self):
        self.tracker.activities['test.exe'] = 100
        self.tracker.clear_data()
        self.assertEqual(len(self.tracker.activities), 0)
        self.assertEqual(self.tracker.idle_time, 0.0)


class TestSettingsManager(unittest.TestCase):
    """Unit tests for SettingsManager"""

    def setUp(self):
        # Use a temporary settings file for tests
        self.settings_file = "test_settings.json"
        if os.path.exists(self.settings_file):
            os.remove(self.settings_file)
        self.settings = SettingsManager(settings_file=self.settings_file)

    def tearDown(self):
        try:
            os.remove(self.settings_file)
        except Exception:
            pass

    def test_default_settings(self):
        self.assertTrue(self.settings.get_setting('reminders_enabled'))
        self.assertEqual(self.settings.get_setting('break_interval'), 30)

    def test_set_get_setting(self):
        self.settings.set_setting('test_key', 'test_value')
        self.assertEqual(self.settings.get_setting('test_key'), 'test_value')


def run_tests():
    """Run unit tests"""
    unittest.main(argv=[''], exit=False)


if __name__ == "__main__":
    # Check if running tests
    if len(sys.argv) > 1 and sys.argv[1] == 'test':
        run_tests()
    else:
        # Run the main application
        try:
            app = MainApplication()
            app.run()
        except Exception as e:
            logging.error(f"Application error: {e}")
            try:
                messagebox.showerror("Application Error", f"An error occurred: {e}")
            except Exception:
                pass
            sys.exit(1)
