# -*- coding: utf-8 -*-
"""KoVir Tire stock watcher - Windows 10.
User signs in manually. The bot uses the site's visible stock refresh control,
checks the selected product card, and stops after one add-to-cart attempt.
It does not bypass CAPTCHA, OTP, queues, or payment security.
"""
import queue
import threading
import time
import tkinter as tk
from tkinter import ttk, messagebox
from datetime import datetime
from pathlib import Path
import re

URL = "https://kavirtire.ir/esale/products"
INTERVAL_SECONDS = 4
DEFAULT_SIZE = "175/60R13"
DEFAULT_MODEL = "KB2000"
DEFAULT_QUANTITY = 2
REFRESH_RE = re.compile(r"بروزرسانی\s*موجودی|به.?روزرسانی\s*موجودی|تازه.?سازی\s*موجودی|refresh", re.I)
ADD_RE = re.compile(
    r"افزودن\s*به\s*سبد(?:\s*خرید)?|اضافه\s*به\s*سبد(?:\s*خرید)?|"
    r"افزودن\s*به\s*خرید|اضافه\s*کردن\s*به\s*سبد|خرید\s*محصول|خرید|"
    r"add\s*to\s*cart|add\s*to\s*basket", re.I
)
UNAVAILABLE_RE = re.compile(
    r"اتمام\s*موجودی|ناموجود|موجود\s*نیست|فعلاً\s*موجود\s*نیست|"
    r"فعلا\s*موجود\s*نیست|عدم\s*موجودی|تمام\s*شد|اتمام\s*موجود|"
    r"به\s*زودی|در\s*حال\s*حاضر\s*موجود\s*نیست|out\s*of\s*stock|sold\s*out", re.I
)
SIZE_RE = re.compile(r"\b\d{3}\s*/\s*\d{2}\s*R\s*\d{2}\b", re.I)

class BotApp:
    def __init__(self, root):
        self.root = root
        self.root.title("ربات پایش موجودی کویر تایر")
        self.root.geometry("720x590")
        self.root.minsize(650, 530)
        self.commands = queue.Queue()
        self.events = queue.Queue()
        self.worker = None
        self.browser_ready = False
        self.products = []
        self.product_var = tk.StringVar()
        self.size_var = tk.StringVar(value=DEFAULT_SIZE)
        self.model_var = tk.StringVar(value=DEFAULT_MODEL)
        self.quantity_var = tk.IntVar(value=DEFAULT_QUANTITY)

        style = ttk.Style()
        try:
            style.theme_use("clam")
        except Exception:
            pass

        main = ttk.Frame(root, padding=12)
        main.pack(fill="both", expand=True)
        ttk.Label(main, text="پایش موجودی کویر تایر", font=("Tahoma", 18, "bold")).pack(anchor="e")
        ttk.Label(main, text="انتخاب از فهرست سایت یا افزودن دستی محصول", font=("Tahoma", 10)).pack(anchor="e", pady=(2, 10))

        group = ttk.LabelFrame(main, text="مشخصات محصول", padding=10)
        group.pack(fill="x")
        group.columnconfigure(1, weight=1)
        ttk.Label(group, text="محصولات استخراج‌شده از سایت:", font=("Tahoma", 9)).grid(row=0, column=2, sticky="e", padx=5, pady=5)
        self.product_combo = ttk.Combobox(group, textvariable=self.product_var, state="readonly", width=34)
        self.product_combo.grid(row=0, column=1, sticky="ew", padx=5, pady=5)
        self.product_combo.bind("<<ComboboxSelected>>", self.on_product_selected)
        self.fetch_btn = ttk.Button(group, text="دریافت / تازه‌سازی فهرست سایت", command=self.refresh_products)
        self.fetch_btn.grid(row=0, column=0, padx=5, pady=5)

        ttk.Label(group, text="سایز:", font=("Tahoma", 9)).grid(row=1, column=2, sticky="e", padx=5, pady=5)
        self.size_combo = ttk.Combobox(group, textvariable=self.size_var, state="readonly", values=[DEFAULT_SIZE], width=18)
        self.size_combo.grid(row=1, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(group, text="مدل / مشخصات:", font=("Tahoma", 9)).grid(row=2, column=2, sticky="e", padx=5, pady=5)
        self.model_combo = ttk.Combobox(group, textvariable=self.model_var, state="normal", width=24)
        self.model_combo.grid(row=2, column=1, sticky="w", padx=5, pady=5)
        ttk.Label(group, text="تعداد حلقه (۱ تا ۴):", font=("Tahoma", 9)).grid(row=3, column=2, sticky="e", padx=5, pady=5)
        self.qty_spin = ttk.Spinbox(group, from_=1, to=4, textvariable=self.quantity_var, width=5)
        self.qty_spin.grid(row=3, column=1, sticky="w", padx=5, pady=5)
        self.manual_btn = ttk.Button(group, text="افزودن محصول دستی به فهرست", command=self.add_manual_product)
        self.manual_btn.grid(row=4, column=1, sticky="w", padx=5, pady=8)

        self.status = tk.StringVar(value="ابتدا مرورگر را باز کنید.")
        ttk.Label(main, textvariable=self.status, foreground="#174f86", font=("Tahoma", 10, "bold"), wraplength=680).pack(fill="x", pady=(14, 8), anchor="e")

        buttons = ttk.Frame(main)
        buttons.pack(fill="x", pady=4)
        self.open_btn = ttk.Button(buttons, text="باز کردن مرورگر و ورود (۱)", command=self.open_browser)
        self.open_btn.pack(side="right", padx=4)
        self.start_btn = ttk.Button(buttons, text="شروع پایش (۲)", command=self.start_monitor, state="disabled")
        self.start_btn.pack(side="right", padx=4)
        self.stop_btn = ttk.Button(buttons, text="توقف", command=self.stop_monitor, state="disabled")
        self.stop_btn.pack(side="right", padx=4)

        ttk.Label(main, text="گزارش فعالیت", font=("Tahoma", 10, "bold")).pack(anchor="e", pady=(10, 2))
        self.log = tk.Text(main, height=10, wrap="word", font=("Tahoma", 9), state="disabled")
        self.log.pack(fill="both", expand=True, pady=4)
        ttk.Label(main, text="پس از باز شدن مرورگر وارد حساب شوید و صفحه محصولات را باز کنید. پس از افزودن به سبد، تعداد و سفارش را خودتان بررسی و پرداخت را دستی انجام دهید.", wraplength=680, font=("Tahoma", 8)).pack(anchor="e", pady=(5, 0))

        self.root.after(250, self.poll_events)
        self.root.protocol("WM_DELETE_WINDOW", self.close)

    def log_line(self, msg):
        stamp = datetime.now().strftime("%H:%M:%S")
        self.log.configure(state="normal")
        self.log.insert("end", f"[{stamp}] {msg}\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def open_browser(self):
        if self.worker and self.worker.is_alive():
            self.log_line("مرورگر از قبل فعال است.")
            return
        self.status.set("در حال آماده‌سازی مرورگر و دریافت فهرست محصولات...")
        self.open_btn.configure(state="disabled")
        self.worker = threading.Thread(target=self.browser_worker, daemon=True)
        self.worker.start()

    def refresh_products(self):
        if not self.browser_ready:
            self.log_line("برای دریافت فهرست، ابتدا مرورگر را باز کنید.")
            return
        self.commands.put("refresh_products")
        self.status.set("درخواست تازه‌سازی فهرست محصولات ارسال شد.")

    def on_product_selected(self, _event=None):
        selected = self.product_var.get()
        for p in self.products:
            if p["label"] == selected:
                self.size_var.set(p["size"])
                self.model_var.set(p["model"])
                break

    def add_manual_product(self):
        size = self.size_var.get().strip()
        model = self.model_var.get().strip()
        if not SIZE_RE.search(size):
            messagebox.showwarning("سایز نامعتبر", "سایز را با قالبی مانند 175/60R13 وارد کنید.")
            return
        if not model:
            messagebox.showwarning("مدل خالی است", "مدل یا مشخصات محصول را وارد کنید.")
            return
        self.add_product_option(size, model)
        self.log_line(f"محصول دستی اضافه شد: {size} | {model}")

    def add_product_option(self, size, model):
        label = f"{size} | {model}"
        if not any(p["label"] == label for p in self.products):
            self.products.append({"label": label, "size": size, "model": model})
            self.product_combo.configure(values=[p["label"] for p in self.products])
        self.product_var.set(label)
        self.size_var.set(size)
        self.model_var.set(model)

    def start_monitor(self):
        if not self.browser_ready:
            return
        try:
            qty = int(self.quantity_var.get())
            if qty < 1 or qty > 4:
                raise ValueError
        except Exception:
            messagebox.showwarning("تعداد نامعتبر", "تعداد حلقه باید بین ۱ تا ۴ باشد.")
            return
        size, model = self.size_var.get().strip(), self.model_var.get().strip()
        if not size or not model:
            messagebox.showwarning("مشخصات ناقص", "محصول و سایز را انتخاب کنید.")
            return
        self.commands.put(("start", size, model, qty))
        self.start_btn.configure(state="disabled")
        self.stop_btn.configure(state="normal")
        self.status.set(f"پایش {model} / {size} آغاز شد؛ بررسی هر ۴ ثانیه، بدون محدودیت ساعت.")

    def stop_monitor(self):
        self.commands.put("stop")
        self.stop_btn.configure(state="disabled")
        self.start_btn.configure(state="normal" if self.browser_ready else "disabled")
        self.status.set("توقف پایش درخواست شد.")

    def browser_worker(self):
        try:
            from playwright.sync_api import sync_playwright
            profile = Path.home() / "KoVirTireBotProfile"
            profile.mkdir(exist_ok=True)
            with sync_playwright() as p:
                context = p.chromium.launch_persistent_context(
                    user_data_dir=str(profile), headless=False,
                    viewport={"width": 1365, "height": 900}, locale="fa-IR",
                    args=["--start-maximized"])
                page = context.pages[0] if context.pages else context.new_page()
                page.goto(URL, wait_until="domcontentloaded", timeout=60000)
                self.events.put(("ready", "مرورگر باز شد. وارد حساب شوید و صفحه محصولات را آماده کنید."))
                self.events.put(("log", "در هر اجرای برنامه، فهرست محصولات از صفحه سایت دریافت می‌شود؛ در صورت نیاز دکمه تازه‌سازی را بزنید."))
                self.extract_products(page)
                monitoring = False
                last_check = 0.0
                while True:
                    try:
                        cmd = self.commands.get(timeout=0.25)
                        if cmd == "stop":
                            monitoring = False
                            self.events.put(("stopped", "پایش متوقف شد."))
                        elif cmd == "refresh_products":
                            self.extract_products(page)
                        elif isinstance(cmd, tuple) and cmd[0] == "start":
                            monitoring = True
                            selected = {"size": cmd[1], "model": cmd[2], "quantity": cmd[3]}
                            last_check = 0.0
                            self.events.put(("log", f"پایش فعال شد: {selected['model']} / {selected['size']} / تعداد {selected['quantity']}"))
                    except queue.Empty:
                        pass

                    if monitoring and time.monotonic() - last_check >= INTERVAL_SECONDS:
                        last_check = time.monotonic()
                        try:
                            refresh = page.get_by_text(REFRESH_RE)
                            refresh = refresh.filter(visible=True)
                            if refresh.count() == 0:
                                self.events.put(("log", "دکمه بروزرسانی موجودی پیدا نشد؛ صفحه محصولات را باز کنید."))
                                continue
                            refresh.first.click(timeout=3000)
                            page.wait_for_timeout(900)
                            card = find_product_card(page, selected["model"], selected["size"])
                            if card is None:
                                self.events.put(("log", "کارت محصول انتخاب‌شده پیدا نشد؛ مدل و سایز یا صفحه محصولات را بررسی کنید."))
                                continue
                            status = detect_card_status(card)
                            if status["available"]:
                                target = status["button"]
                                if target is None:
                                    self.events.put(("log", "نشانه موجودی دیده شد اما دکمه قابل کلیک شناسایی نشد."))
                                    continue
                                target.click(timeout=4000)
                                monitoring = False
                                self.events.put(("found", f"نشانه موجودی شناسایی شد و دکمه خرید کلیک شد. تعداد انتخابی: {selected['quantity']} حلقه. سبد و تعداد را بررسی کنید و پرداخت را دستی انجام دهید."))
                            else:
                                reason = status["reason"] or "نشانه خرید فعال پیدا نشد"
                                self.events.put(("log", f"هنوز قابل خرید تشخیص داده نشد ({reason})؛ موجودی تازه‌سازی شد."))
                        except Exception as e:
                            self.events.put(("log", f"خطای موقت صفحه: {str(e)[:180]}"))
        except Exception as e:
            self.events.put(("fatal", f"خطا در اجرای مرورگر: {e}"))

    def extract_products(self, page):
        try:
            found = page.evaluate("""() => {
              const sizeRe = /\\b\\d{3}\\s*\\/\\s*\\d{2}\\s*R\\s*\\d{2}\\b/i;
              const out = [];
              const seen = new Set();
              const controls = [...document.querySelectorAll('button,[role=button],input[type=button],input[type=submit]')];
              for (const el of controls) {
                let node = el;
                for (let i=0; i<9 && node; i++, node=node.parentElement) {
                  const txt = (node.innerText || node.textContent || '').replace(/\\s+/g,' ').trim();
                  const sm = txt.match(sizeRe);
                  if (sm && txt.length < 1800 && txt.length > 12) {
                    const model = txt.replace(sm[0], ' ').replace(/اتمام موجودی|ناموجود|افزودن به سبد خرید|افزودن به سبد|بروزرسانی موجودی/g,' ').replace(/\\s+/g,' ').trim().slice(0,90);
                    const size = sm[0].replace(/\\s+/g,'').toUpperCase();
                    const key = size+'|'+model;
                    if (!seen.has(key) && model) { seen.add(key); out.push({size, model}); }
                    break;
                  }
                }
              }
              return out;
            }""")
            clean = []
            for item in found:
                size = re.sub(r"\s+", "", item.get("size", "")).upper()
                model = re.sub(r"\s+", " ", item.get("model", "")).strip()
                if SIZE_RE.search(size) and model:
                    clean.append((size, model))
            self.events.put(("products", clean))
            self.events.put(("log", f"فهرست سایت بررسی شد؛ {len(clean)} مورد قابل استخراج پیدا شد."))
        except Exception as e:
            self.events.put(("log", f"دریافت فهرست محصولات ناموفق بود: {str(e)[:140]}"))

    def poll_events(self):
        try:
            while True:
                kind, msg = self.events.get_nowait()
                if kind == "products":
                    for size, model in msg:
                        self.add_product_option(size, model)
                    # Restore the requested default when present; otherwise retain first available item.
                    default = next((p for p in self.products if p["size"] == DEFAULT_SIZE), None)
                    if default:
                        self.product_var.set(default["label"])
                        self.size_var.set(default["size"])
                        self.model_var.set(default["model"])
                else:
                    self.log_line(msg)
                if kind == "ready":
                    self.browser_ready = True
                    self.open_btn.configure(state="normal")
                    self.start_btn.configure(state="normal")
                    self.status.set(msg)
                elif kind == "found":
                    self.status.set("موجودی شناسایی شد؛ برنامه برای بررسی سفارش متوقف شد.")
                    self.start_btn.configure(state="disabled")
                    self.stop_btn.configure(state="disabled")
                    messagebox.showinfo("موجودی شناسایی شد", msg)
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

    def close(self):
        self.commands.put("stop")
        self.root.destroy()


def find_product_card(page, model, size):
    # Locate a product by model and size, then return the smallest containing card.
    model_loc = page.get_by_text(model, exact=False)
    if model_loc.count() == 0:
        return None
    for idx in range(min(model_loc.count(), 20)):
        candidate = model_loc.nth(idx)
        for level in range(1, 10):
            ancestor = candidate.locator("xpath=" + "/.." * level)
            try:
                txt = ancestor.inner_text(timeout=700)
            except Exception:
                continue
            normalized = re.sub(r"\s+", "", txt).upper()
            if re.sub(r"\s+", "", size).upper() in normalized and model.lower() in txt.lower():
                if len(txt) < 2500:
                    return ancestor
    return None


def is_green_background(locator):
    try:
        color = locator.evaluate("el => getComputedStyle(el).backgroundColor")
        match = re.search(r"rgba?\((\d+),\s*(\d+),\s*(\d+)", color or "")
        if not match:
            return False
        r, g, b = map(int, match.groups())
        return g >= 90 and g > r * 1.20 and g > b * 1.10
    except Exception:
        return False


def detect_card_status(card):
    text = card.inner_text(timeout=1200)
    if UNAVAILABLE_RE.search(text):
        # Do not let a green decorative element override explicit out-of-stock text.
        unavailable = True
    else:
        unavailable = False
    controls = card.locator("button, [role=button], input[type=button], input[type=submit], a")
    candidates = []
    for i in range(min(controls.count(), 40)):
        el = controls.nth(i)
        try:
            if not el.is_visible():
                continue
            tag = el.evaluate("el => el.tagName.toLowerCase()")
            label = (el.inner_text(timeout=300) or el.get_attribute("value") or el.get_attribute("aria-label") or "").strip()
            disabled = el.is_disabled() if el.evaluate("el => 'disabled' in el") else False
            known_add = bool(ADD_RE.search(label))
            green = is_green_background(el)
            # Green + enabled is a secondary clue for sites that change button wording.
            if not disabled and (known_add or (tag != "a" and green and not UNAVAILABLE_RE.search(label))):
                candidates.append((el, label, known_add, green))
        except Exception:
            continue
    if unavailable and not any(known and green for _, _, known, green in candidates):
        return {"available": False, "button": None, "reason": "متن ناموجود/اتمام موجودی"}
    if candidates:
        # Prefer an explicit add-to-cart label; otherwise prefer a green enabled control.
        candidates.sort(key=lambda x: (x[2], x[3]), reverse=True)
        return {"available": True, "button": candidates[0][0], "reason": "متن خرید یا دکمه سبز و فعال"}
    return {"available": False, "button": None, "reason": "دکمه خرید فعال یا سبز پیدا نشد"}

if __name__ == "__main__":
    root = tk.Tk()
    app = BotApp(root)
    root.mainloop()
