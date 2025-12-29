import json
import os
import threading
import requests

from kivy.app import App
from kivy.lang import Builder
from kivy.clock import Clock
from kivy.properties import StringProperty, ListProperty
from kivy.uix.boxlayout import BoxLayout

KV = r"""
<RootUI>:
    orientation: "vertical"
    padding: dp(10)
    spacing: dp(10)

    BoxLayout:
        size_hint_y: None
        height: dp(44)
        spacing: dp(8)

        Button:
            text: "Chat"
            on_release: root.show_screen("chat")
        Button:
            text: "Settings"
            on_release: root.show_screen("settings")

    ScreenManager:
        id: sm

        Screen:
            name: "chat"
            BoxLayout:
                orientation: "vertical"
                spacing: dp(8)

                Label:
                    size_hint_y: None
                    height: dp(24)
                    text: root.status_text
                    halign: "left"
                    valign: "middle"
                    text_size: self.size

                ScrollView:
                    do_scroll_x: False
                    BoxLayout:
                        id: chat_box
                        orientation: "vertical"
                        size_hint_y: None
                        height: self.minimum_height
                        spacing: dp(8)

                BoxLayout:
                    size_hint_y: None
                    height: dp(52)
                    spacing: dp(8)

                    TextInput:
                        id: user_input
                        hint_text: "Type a message..."
                        multiline: False
                        on_text_validate: root.on_send()
                    Button:
                        text: "Send"
                        size_hint_x: None
                        width: dp(90)
                        on_release: root.on_send()

        Screen:
            name: "settings"
            BoxLayout:
                orientation: "vertical"
                spacing: dp(10)

                Label:
                    size_hint_y: None
                    height: dp(24)
                    text: "NVIDIA / NIM Settings"
                    bold: True

                TextInput:
                    id: base_url
                    hint_text: "Base URL (e.g. https://integrate.api.nvidia.com/v1 OR http://192.168.1.10:8000/v1)"
                    multiline: False
                    text: root.base_url

                TextInput:
                    id: api_key
                    hint_text: "API Key (will be stored locally on device)"
                    multiline: False
                    password: True
                    text: root.api_key

                BoxLayout:
                    size_hint_y: None
                    height: dp(44)
                    spacing: dp(8)

                    Button:
                        text: "Load models"
                        on_release: root.load_models()
                    Spinner:
                        id: model_spinner
                        text: root.model_name if root.model_name else "Select model"
                        values: root.models
                        on_text: root.set_model(self.text)

                Label:
                    size_hint_y: None
                    height: dp(24)
                    text: "System prompt (persona)"
                    halign: "left"
                    valign: "middle"
                    text_size: self.size

                TextInput:
                    id: system_prompt
                    hint_text: "Example: You are a warm, playful companion. Keep responses respectful and non-explicit."
                    text: root.system_prompt
                    multiline: True
                    size_hint_y: 0.5

                BoxLayout:
                    size_hint_y: None
                    height: dp(48)
                    spacing: dp(8)

                    Button:
                        text: "Save"
                        on_release: root.save_settings()
                    Button:
                        text: "Test /v1/health/ready"
                        on_release: root.test_health()
"""

CONFIG_FILE = "nim_chat_config.json"


class RootUI(BoxLayout):
    status_text = StringProperty("Ready.")
    base_url = StringProperty("https://integrate.api.nvidia.com/v1")
    api_key = StringProperty("")
    model_name = StringProperty("")
    system_prompt = StringProperty("You are a friendly assistant.")
    models = ListProperty([])

    def __init__(self, **kwargs):
        super().__init__(**kwargs)
        self.messages = []  # conversation memory (role/content)
        self.load_settings_from_disk()

    def show_screen(self, name):
        self.ids.sm.current = name

    def add_chat_bubble(self, role, content):
        # simple “bubble”
        bubble = Builder.load_string(f"""
Label:
    size_hint_y: None
    height: self.texture_size[1] + dp(14)
    text_size: self.width, None
    halign: "left"
    valign: "top"
    padding: dp(10), dp(7)
    canvas.before:
        Color:
            rgba: (0.2,0.2,0.2,1) if "{role}"=="user" else (0.15,0.15,0.25,1)
        RoundedRectangle:
            pos: self.pos
            size: self.size
            radius: [10]
    text: "{'[You]' if role=='user' else '[AI]'} " + {json.dumps(content)}
""")
        self.ids.chat_box.add_widget(bubble)
        Clock.schedule_once(lambda *_: self.scroll_to_bottom(), 0)

    def scroll_to_bottom(self):
        # force scroll to bottom
        sv = self.ids.sm.get_screen("chat").children[0].children[1]
        sv.scroll_y = 0

    def set_model(self, text):
        if text and text != "Select model":
            self.model_name = text

    def save_settings(self):
        self.base_url = self.ids.base_url.text.strip()
        self.api_key = self.ids.api_key.text.strip()
        self.system_prompt = self.ids.system_prompt.text
        data = {
            "base_url": self.base_url,
            "api_key": self.api_key,
            "model_name": self.model_name,
            "system_prompt": self.system_prompt,
        }
        with open(CONFIG_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        self.status_text = "Saved settings."

    def load_settings_from_disk(self):
        if os.path.exists(CONFIG_FILE):
            try:
                with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.base_url = data.get("base_url", self.base_url)
                self.api_key = data.get("api_key", "")
                self.model_name = data.get("model_name", "")
                self.system_prompt = data.get("system_prompt", self.system_prompt)
                self.status_text = "Loaded saved settings."
            except Exception as e:
                self.status_text = f"Config load failed: {e}"

    def _headers(self):
        # NVIDIA NIM is OpenAI-compatible; use Bearer token header. :contentReference[oaicite:2]{index=2}
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        return headers

    def load_models(self):
        self.save_settings()
        self.status_text = "Loading models..."
        threading.Thread(target=self._load_models_worker, daemon=True).start()

    def _load_models_worker(self):
        try:
            r = requests.get(f"{self.base_url}/models", headers=self._headers(), timeout=30)
            r.raise_for_status()
            data = r.json()
            # OpenAI-style: {"data": [{"id": "..."}]}
            model_ids = [m.get("id") for m in data.get("data", []) if m.get("id")]
            if not model_ids:
                raise RuntimeError("No models returned from /v1/models")
            Clock.schedule_once(lambda *_: self._set_models_ui(model_ids), 0)
        except Exception as e:
            Clock.schedule_once(lambda *_: self._set_status(f"Load models failed: {e}"), 0)

    def _set_models_ui(self, model_ids):
        self.models = model_ids
        if self.model_name and self.model_name in model_ids:
            pass
        else:
            self.model_name = model_ids[0]
        self.status_text = f"Loaded {len(model_ids)} models."

    def test_health(self):
        self.save_settings()
        self.status_text = "Testing health..."
        threading.Thread(target=self._health_worker, daemon=True).start()

    def _health_worker(self):
        try:
            # NIM for LLMs exposes /v1/health/ready. :contentReference[oaicite:3]{index=3}
            r = requests.get(f"{self.base_url}/health/ready", headers=self._headers(), timeout=15)
            r.raise_for_status()
            Clock.schedule_once(lambda *_: self._set_status("Health OK."), 0)
        except Exception as e:
            Clock.schedule_once(lambda *_: self._set_status(f"Health failed: {e}"), 0)

    def _set_status(self, text):
        self.status_text = text

    def on_send(self):
        self.save_settings()
        text = self.ids.user_input.text.strip()
        if not text:
            return
        if not self.model_name:
            self.status_text = "Pick/load a model first (Settings → Load models)."
            return

        self.ids.user_input.text = ""
        self.add_chat_bubble("user", text)
        self.status_text = "Thinking..."

        self.messages.append({"role": "user", "content": text})
        threading.Thread(target=self._chat_worker, daemon=True).start()

    def _chat_worker(self):
        try:
            payload = {
                "model": self.model_name,
                "messages": [{"role": "system", "content": self.system_prompt}] + self.messages,
                "temperature": 0.7,
                "max_tokens": 512,
                "stream": False
            }
            # OpenAI-compatible endpoint: POST /v1/chat/completions. :contentReference[oaicite:4]{index=4}
            r = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self._headers(),
                json=payload,
                timeout=60
            )
            r.raise_for_status()
            data = r.json()
            reply = data["choices"][0]["message"]["content"]
            self.messages.append({"role": "assistant", "content": reply})
            Clock.schedule_once(lambda *_: self._show_ai_reply(reply), 0)
        except Exception as e:
            Clock.schedule_once(lambda *_: self._set_status(f"Send failed: {e}"), 0)

    def _show_ai_reply(self, reply):
        self.add_chat_bubble("assistant", reply)
        self.status_text = "Ready."


class NimChatApp(App):
    def build(self):
        Builder.load_string(KV)
        return RootUI()


if __name__ == "__main__":
    NimChatApp().run()
