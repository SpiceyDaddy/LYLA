import json
import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, scrolledtext, ttk
import webbrowser

from src.conversation_manager import ConversationManager
from src.lyla_core.text_pipeline import LocalModelError
from src.memory import MindMemory, SoulMemory, handle_memory_command
from src.voicebox_client import VoiceboxClient, VoiceboxError

VOICEBOX_DOWNLOAD_URL = "https://github.com/jamiepine/voicebox/releases/latest"
APP_SETTINGS_PATH = Path.home() / ".lyla-ai" / "desktop.json"


def load_settings() -> dict[str, str]:
    if not APP_SETTINGS_PATH.exists():
        return {"voicebox_profile": "", "voicebox_app": ""}
    try:
        settings = json.loads(APP_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            f"Could not read LYLA desktop settings at {APP_SETTINGS_PATH}: {exc}"
        ) from exc
    return {
        "voicebox_profile": str(settings.get("voicebox_profile", "")),
        "voicebox_app": str(settings.get("voicebox_app", "")),
    }


def save_settings(settings: dict[str, str]) -> None:
    try:
        APP_SETTINGS_PATH.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = APP_SETTINGS_PATH.with_suffix(".json.tmp")
        temporary_path.write_text(
            json.dumps(settings, indent=2),
            encoding="utf-8",
        )
        temporary_path.replace(APP_SETTINGS_PATH)
    except OSError as exc:
        raise RuntimeError(
            f"Could not save LYLA desktop settings at {APP_SETTINGS_PATH}: {exc}"
        ) from exc


def open_voicebox_application(configured_path: str = "") -> None:
    candidates = []
    if configured_path.strip():
        candidates.append(Path(configured_path.strip()).expanduser())

    for folder in (
        Path(os.environ.get("APPDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
        Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft" / "Windows" / "Start Menu" / "Programs",
    ):
        if folder.is_dir():
            candidates.extend(folder.glob("**/*Voicebox*.lnk"))
            candidates.extend(folder.glob("**/*Voicebox*.exe"))

    for candidate in candidates:
        if candidate.is_file():
            try:
                os.startfile(str(candidate))
                return
            except OSError as exc:
                raise RuntimeError(
                    f"Could not open the Voicebox application at {candidate}: {exc}"
                ) from exc

    try:
        webbrowser.open(VOICEBOX_DOWNLOAD_URL)
    except OSError as exc:
        raise RuntimeError(
            "Voicebox was not found. Install it from "
            f"{VOICEBOX_DOWNLOAD_URL}. You can set its application path in LYLA's settings."
        ) from exc
    raise FileNotFoundError(
        "Voicebox was not found. The Voicebox download page has been opened. "
        "Install Voicebox, then use its shortcut or choose its executable in Settings."
    )


class LylaDesktopApp:
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("LYLA")
        self.root.geometry("760x640")
        self.root.minsize(560, 420)

        self.events: queue.Queue[tuple[str, str]] = queue.Queue()
        self.soul = SoulMemory()
        self.mind = MindMemory()
        self.conversation = ConversationManager(soul=self.soul, mind=self.mind)
        self.settings = load_settings()
        self.last_reply = ""
        self.busy = False

        self._build_ui()
        self.root.after(100, self._process_events)
        self._append_message(
            "LYLA",
            "Hey, James. Type whenever you're ready. Your recent context stays "
            "in this session; save long-term notes explicitly with /remember.",
        )

    def _build_ui(self) -> None:
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(1, weight=1)

        toolbar = ttk.Frame(self.root, padding=(12, 10))
        toolbar.grid(row=0, column=0, sticky="ew")
        ttk.Label(toolbar, text="LYLA", font=("Segoe UI", 18, "bold")).pack(
            side=tk.LEFT
        )
        ttk.Button(toolbar, text="Voice settings", command=self._open_settings).pack(
            side=tk.RIGHT, padx=(6, 0)
        )
        ttk.Button(toolbar, text="Open Voicebox", command=self._open_voicebox).pack(
            side=tk.RIGHT
        )

        self.transcript = scrolledtext.ScrolledText(
            self.root,
            wrap=tk.WORD,
            state=tk.DISABLED,
            font=("Segoe UI", 11),
            padx=12,
            pady=10,
        )
        self.transcript.grid(row=1, column=0, sticky="nsew", padx=12)

        composer = ttk.Frame(self.root, padding=12)
        composer.grid(row=2, column=0, sticky="ew")
        composer.columnconfigure(0, weight=1)
        self.message_entry = tk.Text(
            composer,
            height=3,
            wrap=tk.WORD,
            font=("Segoe UI", 11),
        )
        self.message_entry.grid(row=0, column=0, sticky="ew")
        self.message_entry.bind("<Control-Return>", self._send_from_shortcut)
        buttons = ttk.Frame(composer)
        buttons.grid(row=0, column=1, padx=(8, 0), sticky="ns")
        self.send_button = ttk.Button(buttons, text="Send", command=self._send)
        self.send_button.pack(fill=tk.X)
        self.speak_button = ttk.Button(
            buttons,
            text="Speak latest",
            command=self._speak_latest,
            state=tk.DISABLED,
        )
        self.speak_button.pack(fill=tk.X, pady=(6, 0))

        self.status = tk.StringVar(value="Text chat ready. Voice replies are optional.")
        ttk.Label(self.root, textvariable=self.status, anchor=tk.W, padding=(12, 4)).grid(
            row=3, column=0, sticky="ew"
        )

    def _append_message(self, speaker: str, text: str) -> None:
        self.transcript.configure(state=tk.NORMAL)
        self.transcript.insert(tk.END, f"{speaker}\n{text}\n\n")
        self.transcript.configure(state=tk.DISABLED)
        self.transcript.see(tk.END)

    def _send_from_shortcut(self, _event):
        self._send()
        return "break"

    def _send(self) -> None:
        if self.busy:
            return
        message = self.message_entry.get("1.0", tk.END).strip()
        if not message:
            return
        self.message_entry.delete("1.0", tk.END)
        self._append_message("You", message)

        command_reply = handle_memory_command(message, self.soul, self.mind)
        if command_reply is not None:
            self._display_reply(command_reply)
            return

        self.busy = True
        self.send_button.configure(state=tk.DISABLED)
        self.status.set("LYLA is thinking locally...")
        threading.Thread(
            target=self._generate_reply,
            args=(message,),
            daemon=True,
        ).start()

    def _generate_reply(self, message: str) -> None:
        try:
            reply, _ = self.conversation.ask(message)
            self.events.put(("reply", reply))
        except LocalModelError as exc:
            self.events.put(("error", str(exc)))
        except Exception as exc:
            self.events.put(("error", f"LYLA could not respond: {exc}"))

    def _display_reply(self, reply: str) -> None:
        self.last_reply = reply
        self._append_message("LYLA", reply)
        self.speak_button.configure(state=tk.NORMAL)
        self.status.set("Ready. Replies are text-first; use Speak latest if you want audio.")

    def _process_events(self) -> None:
        while True:
            try:
                kind, text = self.events.get_nowait()
            except queue.Empty:
                break
            if kind == "reply":
                self.busy = False
                self.send_button.configure(state=tk.NORMAL)
                self._display_reply(text)
            elif kind == "status":
                self.status.set(text)
            elif kind == "speak_done":
                self.busy = False
                self.send_button.configure(state=tk.NORMAL)
                if self.last_reply:
                    self.speak_button.configure(state=tk.NORMAL)
            else:
                self.busy = False
                self.send_button.configure(state=tk.NORMAL)
                if self.last_reply:
                    self.speak_button.configure(state=tk.NORMAL)
                self._append_message("LYLA", text)
                self.status.set("Text chat remains available. Try another message or a memory command.")
        self.root.after(100, self._process_events)

    def _open_settings(self) -> None:
        window = tk.Toplevel(self.root)
        window.title("LYLA Voice Settings")
        window.resizable(False, False)
        window.transient(self.root)
        window.grab_set()
        frame = ttk.Frame(window, padding=16)
        frame.grid(row=0, column=0, sticky="nsew")
        frame.columnconfigure(1, weight=1)

        ttk.Label(frame, text="Voicebox profile").grid(row=0, column=0, sticky="w")
        profile_var = tk.StringVar(value=self.settings["voicebox_profile"])
        ttk.Entry(frame, textvariable=profile_var, width=36).grid(
            row=0, column=1, sticky="ew", padx=(10, 0)
        )
        ttk.Label(
            frame,
            text="Optional profile name or ID from Voicebox. Leave blank to use its default.",
            wraplength=420,
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(4, 12))

        ttk.Label(frame, text="Voicebox app path").grid(row=2, column=0, sticky="w")
        app_var = tk.StringVar(value=self.settings["voicebox_app"])
        ttk.Entry(frame, textvariable=app_var, width=36).grid(
            row=2, column=1, sticky="ew", padx=(10, 0)
        )
        ttk.Button(
            frame,
            text="Browse",
            command=lambda: self._choose_voicebox_app(app_var),
        ).grid(row=2, column=2, padx=(6, 0))
        ttk.Label(
            frame,
            text="Voicebox must be installed and open for the Speak button to work.",
            wraplength=420,
        ).grid(row=3, column=0, columnspan=3, sticky="w", pady=(4, 12))

        controls = ttk.Frame(frame)
        controls.grid(row=4, column=0, columnspan=3, sticky="e")
        ttk.Button(
            controls,
            text="Test connection",
            command=lambda: self._test_voicebox(profile_var.get()),
        ).pack(side=tk.LEFT, padx=(0, 8))
        ttk.Button(
            controls,
            text="Save",
            command=lambda: self._save_settings(profile_var, app_var, window),
        ).pack(side=tk.LEFT)

    def _choose_voicebox_app(self, app_var: tk.StringVar) -> None:
        path = filedialog.askopenfilename(
            title="Select Voicebox",
            filetypes=[
                ("Voicebox application", "*.exe;*.lnk"),
                ("All files", "*.*"),
            ],
        )
        if path:
            app_var.set(path)

    def _save_settings(
        self,
        profile_var: tk.StringVar,
        app_var: tk.StringVar,
        window: tk.Toplevel,
    ) -> None:
        self.settings = {
            "voicebox_profile": profile_var.get().strip(),
            "voicebox_app": app_var.get().strip(),
        }
        try:
            save_settings(self.settings)
        except RuntimeError as exc:
            messagebox.showerror("Settings could not be saved", str(exc), parent=window)
            return
        messagebox.showinfo("LYLA", "Voice settings saved on this computer.", parent=window)
        window.destroy()

    def _test_voicebox(self, profile: str) -> None:
        client = VoiceboxClient(profile=profile)
        threading.Thread(
            target=self._check_voicebox,
            args=(client,),
            daemon=True,
        ).start()

    def _check_voicebox(self, client: VoiceboxClient) -> None:
        try:
            client.check_connection()
            self.events.put(("status", "Connected to the local Voicebox API."))
        except (VoiceboxError, ValueError) as exc:
            self.events.put(("error", str(exc)))

    def _open_voicebox(self) -> None:
        try:
            open_voicebox_application(self.settings["voicebox_app"])
            self.status.set("Opened Voicebox. Configure your voice there.")
        except FileNotFoundError as exc:
            messagebox.showinfo("Voicebox", str(exc))
        except RuntimeError as exc:
            messagebox.showerror("Could not open Voicebox", str(exc))

    def _speak_latest(self) -> None:
        if not self.last_reply or self.busy:
            return
        self.busy = True
        self.speak_button.configure(state=tk.DISABLED)
        self.status.set("Sending reply to Voicebox...")
        client = VoiceboxClient(profile=self.settings["voicebox_profile"])
        threading.Thread(
            target=self._send_speech,
            args=(client, self.last_reply),
            daemon=True,
        ).start()

    def _send_speech(self, client: VoiceboxClient, text: str) -> None:
        try:
            result = client.speak(text)
            self.events.put(("status", result))
        except (VoiceboxError, ValueError) as exc:
            self.events.put(("error", str(exc)))
        finally:
            self.events.put(("speak_done", ""))


def main() -> None:
    try:
        root = tk.Tk()
        LylaDesktopApp(root)
    except Exception as exc:
        messagebox.showerror("LYLA could not start", str(exc))
        return
    root.mainloop()


if __name__ == "__main__":
    main()
