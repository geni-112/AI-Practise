"""
LiteLLM + Huawei MaaS 部署凭证填写表单
填写完成后保存到 credential.skill 文件
"""
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import json
import os
import sys

SAVE_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "credential.skill")

FIELDS = [
    ("section", "── 华为云账号凭证 ──────────────────────────"),
    ("HUAWEI_AK",          "Access Key (AK)",              "",       False),
    ("HUAWEI_SK",          "Secret Key (SK)",              "",       True),
    ("HUAWEI_PROJECT",     "Project ID",                   "",       False),
    ("HUAWEI_REGION",      "Region",                       "ap-southeast-1", False),
    ("section", "── MaaS API ─────────────────────────────────"),
    ("HUAWEI_MAAS_API_BASE","MaaS API Base URL",
     "https://api-ap-southeast-1.modelarts-maas.com/openai/v1", False),
    ("HUAWEI_MAAS_API_KEY","MaaS API Key",                 "",       True),
    ("section", "── ECS 连接（已有ECS填写，新建可留空）────────"),
    ("ECS_PUBLIC_IP",      "ECS 公网 IP",                  "",       False),
    ("SSH_KEY",            "SSH 私钥路径",                  "",       False),
    ("SSH_USER",           "SSH 登录用户",                  "root",   False),
    ("section", "── 端口配置（默认值已填）────────────────────"),
    ("LITELLM_PORT",       "LiteLLM 端口",                 "4000",   False),
    ("MCP_PORT",           "MCP 端口",                     "8788",   False),
]

class CredentialForm(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("LiteLLM + Huawei MaaS 部署凭证")
        self.resizable(False, False)
        self.configure(bg="#1e1e2e")

        # Try to center window
        self.update_idletasks()
        w, h = 620, 680
        x = (self.winfo_screenwidth() - w) // 2
        y = (self.winfo_screenheight() - h) // 2
        self.geometry(f"{w}x{h}+{x}+{y}")

        self.entries = {}
        self._build_ui()
        self._load_existing()

    def _build_ui(self):
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("TFrame", background="#1e1e2e")
        style.configure("TLabel", background="#1e1e2e", foreground="#cdd6f4",
                        font=("Consolas", 10))
        style.configure("Section.TLabel", background="#1e1e2e", foreground="#89b4fa",
                        font=("Consolas", 9, "bold"))
        style.configure("TEntry", fieldbackground="#313244", foreground="#cdd6f4",
                        insertcolor="#cdd6f4", font=("Consolas", 10))
        style.configure("Save.TButton", font=("Consolas", 11, "bold"),
                        background="#a6e3a1", foreground="#1e1e2e")
        style.map("Save.TButton", background=[("active", "#94e2d5")])

        # Header
        hdr = tk.Label(self, text="🚀  部署凭证配置",
                       bg="#181825", fg="#cba6f7",
                       font=("Consolas", 14, "bold"), pady=10)
        hdr.pack(fill="x")

        # Scroll canvas
        canvas = tk.Canvas(self, bg="#1e1e2e", highlightthickness=0)
        scroll = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=scroll.set)
        scroll.pack(side="right", fill="y")
        canvas.pack(side="left", fill="both", expand=True)

        frame = ttk.Frame(canvas)
        canvas_win = canvas.create_window((0, 0), window=frame, anchor="nw")

        def on_frame_configure(event):
            canvas.configure(scrollregion=canvas.bbox("all"))
        def on_canvas_configure(event):
            canvas.itemconfig(canvas_win, width=event.width)

        frame.bind("<Configure>", on_frame_configure)
        canvas.bind("<Configure>", on_canvas_configure)
        canvas.bind_all("<MouseWheel>",
                        lambda e: canvas.yview_scroll(-1*(e.delta//120), "units"))

        pad = {"padx": 18, "pady": 3}

        for item in FIELDS:
            if item[0] == "section":
                lbl = ttk.Label(frame, text=item[1], style="Section.TLabel")
                lbl.pack(anchor="w", padx=18, pady=(12, 2))
                sep = tk.Frame(frame, bg="#45475a", height=1)
                sep.pack(fill="x", padx=18, pady=(0, 4))
                continue

            key, label, default, secret = item
            row = ttk.Frame(frame)
            row.pack(fill="x", **pad)

            lbl = ttk.Label(row, text=f"{label}:", width=26, anchor="e")
            lbl.pack(side="left")

            if key == "SSH_KEY":
                sub = ttk.Frame(row)
                sub.pack(side="left", fill="x", expand=True)
                var = tk.StringVar(value=default)
                ent = ttk.Entry(sub, textvariable=var, width=32)
                ent.pack(side="left", fill="x", expand=True)
                btn = tk.Button(sub, text="…", bg="#45475a", fg="#cdd6f4",
                                font=("Consolas", 9), relief="flat",
                                command=lambda v=var: self._browse_key(v))
                btn.pack(side="left", padx=(4, 0))
                self.entries[key] = var
            else:
                show = "*" if secret else ""
                var = tk.StringVar(value=default)
                ent = ttk.Entry(row, textvariable=var, show=show, width=40)
                ent.pack(side="left", fill="x", expand=True)
                if secret:
                    eye_var = tk.BooleanVar(value=False)
                    def toggle(e=ent, v=eye_var):
                        v.set(not v.get())
                        e.config(show="" if v.get() else "*")
                    eye = tk.Button(row, text="👁", bg="#1e1e2e", fg="#585b70",
                                    font=("Consolas", 9), relief="flat",
                                    command=toggle)
                    eye.pack(side="left", padx=(4, 0))
                self.entries[key] = var

        # Buttons
        btn_frame = tk.Frame(self, bg="#181825", pady=12)
        btn_frame.pack(fill="x", side="bottom")

        save_btn = ttk.Button(btn_frame, text="  💾  保存 credential.skill  ",
                              style="Save.TButton", command=self._save)
        save_btn.pack(side="left", padx=20)

        cancel_btn = tk.Button(btn_frame, text="取消", bg="#45475a", fg="#cdd6f4",
                               font=("Consolas", 10), relief="flat",
                               command=self.destroy)
        cancel_btn.pack(side="left")

        self.status_lbl = tk.Label(btn_frame, text="", bg="#181825",
                                   fg="#a6e3a1", font=("Consolas", 9))
        self.status_lbl.pack(side="left", padx=12)

    def _browse_key(self, var):
        path = filedialog.askopenfilename(
            title="选择 SSH 私钥文件",
            initialdir=os.path.expanduser("~/.ssh"),
            filetypes=[("All files", "*.*"), ("PEM key", "*.pem")],
        )
        if path:
            var.set(path)

    def _load_existing(self):
        if os.path.exists(SAVE_PATH):
            try:
                with open(SAVE_PATH, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for k, v in data.items():
                    if k in self.entries:
                        self.entries[k].set(v)
                self.status_lbl.config(text=f"已加载: {SAVE_PATH}", fg="#89b4fa")
            except Exception:
                pass

    def _save(self):
        data = {k: v.get().strip() for k, v in self.entries.items()}

        # Validate required fields
        required = ["HUAWEI_AK", "HUAWEI_SK", "HUAWEI_PROJECT",
                    "HUAWEI_MAAS_API_BASE", "HUAWEI_MAAS_API_KEY"]
        missing = [k for k in required if not data.get(k)]
        if missing:
            messagebox.showwarning("缺少必填项",
                                   "以下字段为必填:\n\n" + "\n".join(missing))
            return

        try:
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            os.chmod(SAVE_PATH, 0o600)
        except Exception as e:
            messagebox.showerror("保存失败", str(e))
            return

        self.status_lbl.config(text=f"✓ 已保存: {SAVE_PATH}", fg="#a6e3a1")
        messagebox.showinfo("保存成功",
                            f"凭证已保存至:\n{SAVE_PATH}\n\n"
                            "文件权限已设为 600（仅当前用户可读）。\n"
                            "后续部署将自动加载此文件。")
        self.destroy()


if __name__ == "__main__":
    app = CredentialForm()
    app.mainloop()
