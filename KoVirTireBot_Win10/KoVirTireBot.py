# -*- coding: utf-8 -*-
"""
KoVir Tire stock watcher (Windows 10)
Monitors only Special KB2000 / 175/60R13.
Uses the site's visible "بروزرسانی موجودی" control every 4 seconds.
It does NOT bypass CAPTCHA, OTP, queues, or payment security.
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
import os
from pathlib import Path
import re
import sys

URL = "https://kavirtire.ir/esale/products"
PRODUCT = "Special KB2000"
SIZE = "175/60R13"
REFRESH_TEXT = "بروزرسانی موجودی"
ADD_TEXT = "افزودن به سبد خرید"
SOLD_OUT_WORDS = ("اتمام موجودی", "ناموجود", "عدم موجودی", "موجود نیست", "فعلاً موجود نیست", "اتمام", "ناموجودی")
BUY_WORDS = ("افزودن", "اضافه", "سبد", "خرید", "ثبت سفارش")
INTERVAL_SECONDS = 4

class BotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ربات پایش موجودی کویر تایر")
        self.root.geometry("620x470")
        self.root.minsize(560, 420)
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.worker = None
        self.running = False
        self.browser_ready = False
        self.preference_file = Path.home() / "KoVirTireBotProfile" / "hide_welcome_message.txt"
        self.hide_welcome_message = self.preference_file.exists()
        self.welcome_dialog = None

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        main = ttk.Frame(root, padding=16)
        main.pack(fill="both", expand=True)

        ttk.Label(main, text="پایش موجودی کویر تایر", font=("Tahoma", 17, "bold")).pack(anchor="e")
        ttk.Label(main, text="محصول هدف: KB2000  |  سایز پیش‌فرض: 175/60R13",
                  font=("Tahoma", 10)).pack(anchor="e", pady=(8, 2))
        ttk.Label(main, text="تعداد موردنظر: ۲ حلقه  |  فاصله بررسی: هر ۴ ثانیه",
                  font=("Tahoma", 10)).pack(anchor="e")

        self.status = tk.StringVar(value="مرورگر هنوز باز نشده است.")
        ttk.Label(main, textvariable=self.status, font=("Tahoma", 11, "bold"),
                  foreground="#174f86", wraplength=570).pack(fill="x", pady=14)

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=4)
        self.open_btn = ttk.Button(buttons, text="۱) باز کردن مرورگر و ورود", command=self.open_browser)
        self.open_btn.pack(side="right", padx=4)
        self.start_btn = ttk.Button(buttons, text="۲) شروع پایش", command=self.start_monitor, state="disabled")
        self.start_btn.pack(side="right", padx=4)
        self.stop_btn = ttk.Button(buttons, text="توقف", command=self.stop_monitor, state="disabled")
        self.stop_btn.pack(side="right", padx=4)

        ttk.Separator(main).pack(fill="x", pady=12)
        ttk.Label(main, text="گزارش فعالیت", font=("Tahoma", 10, "bold")).pack(anchor="e")
        self.log = tk.Text(main, height=12, wrap="word", font=("Consolas", 9), state="disabled")
        self.log.pack(fill="both", expand=True, pady=6)

        note = ("با اجرای برنامه، مرورگر و صفحه محصولات خودکار باز و فهرست یک‌بار به‌روزرسانی می‌شود؛ سپس وارد حساب شوید. "
                "پایش هر زمان که خودتان شروع کنید، هر ۴ ثانیه انجام می‌شود. "
                "پس از افزودن به سبد، برنامه متوقف می‌شود تا تعداد ۲ حلقه و سفارش را خودتان بررسی کنید.")
        ttk.Label(main, text=note, wraplength=575, font=("Tahoma", 8)).pack(anchor="e", pady=(4, 0))

        self.root.after(250, self.poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)
        self.root.after(500, self.open_browser)

    def log_line(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def open_browser(self):
        if self.worker and self.worker.is_alive():
            self.log_line("مرورگر/ربات از قبل فعال است.")
            return
        self.status.set("در حال آماده‌سازی مرورگر...")
        self.open_btn.configure(state="disabled")
        self.worker = threading.Thread(target=self.browser_worker, daemon=True)
        self.worker.start()

    def start_monitor(self):
        if not self.browser_ready:
            return
        self.commands.put("start")
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status.set("پایش درخواست شد؛ وضعیت صفحه بررسی می‌شود.")

    def stop_monitor(self):
        self.commands.put("stop")
        self.stop_btn.configure(state="disabled")
        self.start_btn.configure(state="normal" if self.browser_ready else "disabled")
        self.status.set("توقف پایش درخواست شد.")

    def browser_worker(self):
        try:
            # In a PyInstaller onedir build, Chromium is bundled beside the app.
            # _MEIPASS points to the internal application directory.
            if getattr(sys, "frozen", False):
                bundled_browsers = Path(sys._MEIPASS) / "pw-browsers"
                os.environ["PLAYWRIGHT_BROWSERS_PATH"] = str(bundled_browsers)
            from playwright.sync_api import sync_playwright
            profile = Path.home() / "KoVirTireBotProfile"
            profile.mkdir(exist_ok=True)
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile),
                    headless=False,
                    viewport={"width": 1365, "height": 900},
                    locale="fa-IR",
                    args=["--start-maximized"]
                )
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                try:
                    click_stock_refresh(page, timeout=5000)
                    page.wait_for_timeout(1000)
                    self.events.put(("log", "فهرست محصولات در شروع برنامه به‌روزرسانی شد."))
                except Exception as refresh_error:
                    self.events.put(("log", f"به‌روزرسانی اولیه انجام نشد؛ بعداً دوباره تلاش می‌شود: {str(refresh_error)[:120]}"))
                self.events.put(("ready", "سایز و مشخصات لاستیک خود را انتخاب کنید و وارد حساب کاربری خود در سایت کویرتایر بشوید و وارد صفحه خرید بشوید سپس دکمه پایش را بزنید."))
                monitoring = False
                last_check = 0.0
                while True:
                    try:
                        cmd = self.commands.get(timeout=0.25)
                        if cmd == "start":
                            monitoring = True
                            last_check = 0.0
                            self.events.put(("log", "پایش فعال شد."))
                        elif cmd == "stop":
                            monitoring = False
                            self.events.put(("stopped", "پایش متوقف شد."))
                    except queue.Empty:
                        pass

                    if monitoring and (time.monotonic() - last_check >= INTERVAL_SECONDS):
                        last_check = time.monotonic()
                        try:
                            # Do not refresh the whole page: click the page's own stock-update control.
                            click_stock_refresh(page, timeout=2500)
                            page.wait_for_timeout(900)
                            card = find_product_card(page)
                            if card is None:
                                self.events.put(("log", "کارت محصول KB2000 با سایز 175/60R13 پیدا نشد؛ صفحه محصولات و فیلترها را بررسی کنید."))
                                continue
                            candidate, reason = find_active_purchase_control(card)
                            if candidate is not None:
                                candidate.click(timeout=4000)
                                monitoring = False
                                self.events.put(("found", f"کنترل خرید فعال شناسایی شد ({reason}) و کلیک انجام شد. اکنون تعداد و اطلاعات سفارش را بررسی کنید."))
                            else:
                                self.events.put(("log", f"هنوز دکمه خرید فعال تشخیص داده نشد؛ {reason}"))
                        except Exception as e:
                            self.events.put(("log", f"خطای موقت صفحه: {str(e)[:180]}"))
                # unreachable
        except Exception as e:
            self.events.put(("fatal", f"خطا در اجرای مرورگر: {e}"))

    def poll_events(self):
        try:
            while True:
                kind, msg = self.events.get_nowait()
                self.log_line(msg)
                if kind == "ready":
                    self.browser_ready = True
                    self.open_btn.configure(state="normal")
                    self.start_btn.configure(state="normal")
                    self.status.set(msg)
                    if not self.hide_welcome_message:
                        self.show_welcome_dialog()
                elif kind == "found":
                    self.running = False
                    self.status.set("موجودی پیدا شد؛ برنامه برای بررسی سفارش متوقف شد.")
                    self.start_btn.configure(state="disabled")
                    self.stop_btn.configure(state="disabled")
                    messagebox.showinfo("موجود شد", msg)
                elif kind == "stopped":
                    self.status.set(msg)
                    self.start_btn.configure(state="normal" if self.browser_ready else "disabled")
                    self.stop_btn.configure(state="disabled")
                elif kind == "fatal":
                    self.status.set(msg)
                    self.open_btn.configure(state="normal")
                    messagebox.showerror("خطا", msg)
        except queue.Empty:
            pass
        self.root.after(250, self.poll_events)

    def show_welcome_dialog(self):
        if self.welcome_dialog is not None and self.welcome_dialog.winfo_exists():
            return
        win = tk.Toplevel(self.root)
        self.welcome_dialog = win
        win.title("راهنمای شروع")
        win.transient(self.root)
        win.grab_set()
        win.resizable(False, False)
        win.geometry("510x230")
        frame = ttk.Frame(win, padding=18)
        frame.pack(fill="both", expand=True)
        message = ("سایز و مشخصات لاستیک خود را انتخاب کنید و وارد حساب کاربری خود "
                   "در سایت کویرتایر بشوید و وارد صفحه خرید بشوید سپس دکمه پایش را بزنید")
        ttk.Label(frame, text=message, justify="right", anchor="e",
                  wraplength=460, font=("Tahoma", 11)).pack(fill="x", pady=(4, 18))
        dont_show = tk.BooleanVar(value=False)
        ttk.Checkbutton(frame, text="دیگر این پیام را نشان نده", variable=dont_show).pack(anchor="e", pady=(0, 16))

        def dismiss():
            if dont_show.get():
                try:
                    self.preference_file.parent.mkdir(parents=True, exist_ok=True)
                    self.preference_file.write_text("1", encoding="utf-8")
                    self.hide_welcome_message = True
                except Exception as e:
                    self.log_line(f"ذخیره تنظیم نمایش پیام انجام نشد: {str(e)[:100]}")
            win.grab_release()
            win.destroy()
            self.welcome_dialog = None

        ttk.Button(frame, text="متوجه شدم", command=dismiss).pack(anchor="center")
        win.protocol("WM_DELETE_WINDOW", dismiss)
        win.update_idletasks()
        x = self.root.winfo_rootx() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry(f"+{max(0, x)}+{max(0, y)}")

    def close(self):
        self.commands.put("stop")
        if self.welcome_dialog is not None:
            try:
                self.welcome_dialog.destroy()
            except Exception:
                pass
        self.root.destroy()


def click_stock_refresh(page, timeout=2500):
    patterns = [
        re.compile(r"بروزرسانی\s*موجودی|به.?روزرسانی\s*موجودی|تازه.?سازی\s*موجودی", re.I),
        re.compile(r"بروزرسانی|به.?روزرسانی|تازه.?سازی", re.I),
    ]
    for pattern in patterns:
        loc = page.get_by_text(pattern, exact=False)
        for i in range(min(loc.count(), 8)):
            item = loc.nth(i)
            try:
                if item.is_visible() and item.is_enabled():
                    item.click(timeout=timeout)
                    return
            except Exception:
                continue
    raise RuntimeError("دکمه به‌روزرسانی موجودی پیدا نشد")


def normalize_text(value):
    return re.sub(r"\s+", " ", (value or "").replace("\u200c", " ").strip()).casefold()


def find_product_card(page):
    model = page.get_by_text(re.compile(r"KB\s*2000|KB2000|Special\s*KB2000", re.I), exact=False)
    for i in range(min(model.count(), 10)):
        item = model.nth(i)
        try:
            if not item.is_visible():
                continue
        except Exception:
            continue
        for level in range(1, 10):
            ancestor = item.locator("xpath=" + "/.." * level)
            try:
                txt = normalize_text(ancestor.inner_text(timeout=700)).replace(" ", "")
            except Exception:
                continue
            if "175/60R13" in txt:
                try:
                    if ancestor.locator("button, a, [role='button'], input[type='button'], input[type='submit']").count():
                        return ancestor
                except Exception:
                    pass
                return ancestor
    return None


def find_active_purchase_control(card):
    selector = "button, a, [role='button'], input[type='button'], input[type='submit']"
    controls = card.locator(selector)
    for i in range(min(controls.count(), 30)):
        el = controls.nth(i)
        try:
            if not el.is_visible():
                continue
            text = normalize_text(el.inner_text(timeout=500))
            if not text:
                text = normalize_text(el.get_attribute("value") or el.get_attribute("aria-label") or "")
            aria_disabled = (el.get_attribute("aria-disabled") or "").lower() == "true"
            disabled_attr = el.get_attribute("disabled") is not None
            cls = normalize_text(el.get_attribute("class") or "")
            if aria_disabled or disabled_attr or any(x in cls for x in ("disabled", "unavailable", "sold-out")):
                continue
            if any(normalize_text(word) in text for word in SOLD_OUT_WORDS):
                continue
            if any(normalize_text(word) in text for word in BUY_WORDS):
                if el.is_enabled():
                    return el, f"متن دکمه: {text[:55]}"
            # Unknown wording: only accept a real enabled button with pointer cursor
            # and a non-neutral background. Color alone is never sufficient.
            state = el.evaluate("""e => {
                const s=getComputedStyle(e), r=e.getBoundingClientRect();
                return {disabled:!!e.disabled, pointer:s.cursor==='pointer',
                        bg:s.backgroundColor.replace(/\\s/g,''), opacity:Number(s.opacity||1),
                        visible:r.width>2 && r.height>2, tag:e.tagName.toLowerCase()};
            }""")
            neutral = state["bg"] in ("rgba(0,0,0,0)", "transparent", "rgb(255,255,255)", "rgb(248,249,250)", "rgb(245,245,245)")
            if (state["tag"] == "button" and not state["disabled"] and state["visible"]
                    and state["opacity"] >= 0.65 and state["pointer"] and not neutral):
                return el, "دکمه فعال با متن جدید و ظاهر تعاملی"
        except Exception:
            continue
    return None, "کنترل‌های موجود غیرفعال‌اند یا متن ناموجودی دارند"

if __name__ == "__main__":
    root = tk.Tk()
    app = BotApp(root)
    root.mainloop()
