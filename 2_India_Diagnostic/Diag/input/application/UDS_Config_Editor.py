import json
import os
import tkinter as tk
from tkinter import ttk, filedialog, messagebox


# ---------------------------
# Helpers
# ---------------------------
def is_number(x):
    return isinstance(x, (int, float)) and not isinstance(x, bool)

def to_int(text: str) -> int:
    s = str(text).strip()
    if s == "":
        raise ValueError("Empty integer field")
    base = 16 if s.lower().startswith("0x") else 10
    return int(s, base)

def to_float(text: str) -> float:
    s = str(text).strip()
    if s == "":
        raise ValueError("Empty float field")
    return float(s)

def get_path(d: dict, path: str, default=None):
    cur = d
    for k in path.split("."):
        if not isinstance(cur, dict) or k not in cur:
            return default
        cur = cur[k]
    return cur

def set_path(d: dict, path: str, value):
    keys = path.split(".")
    cur = d
    for k in keys[:-1]:
        if k not in cur or not isinstance(cur[k], dict):
            cur[k] = {}
        cur = cur[k]
    cur[keys[-1]] = value

def flatten_dict(d: dict, base_path=""):
    """Return list of (path, value) for all leaf nodes under dict."""
    items = []
    for k, v in d.items():
        p = f"{base_path}.{k}" if base_path else k
        if isinstance(v, dict):
            items.extend(flatten_dict(v, p))
        else:
            items.append((p, v))
    return items

def pretty_group_title(path: str):
    # show last 1~2 segments for readability
    seg = path.split(".")
    return ".".join(seg[-2:]) if len(seg) >= 2 else seg[-1]


# ---------------------------
# App
# ---------------------------
class UDSConfigEditorDynamic(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("UDS Config Editor (Dynamic)")
        self.geometry("920x560")

        self.file_path = None
        self.data = None

        # vars: full_path -> (tkvar, type_tag)
        # type_tag in {"bool","int","float","str","json"}
        self.vars = {}

        top = ttk.Frame(self, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Select JSON Config File", command=self.open_json).pack(side="left")
        self.path_lbl = ttk.Label(top, text="(no file)")
        self.path_lbl.pack(side="left", padx=10)

        self.nb = ttk.Notebook(self)
        self.nb.pack(fill="both", expand=True, padx=8, pady=8)

        bottom = ttk.Frame(self, padding=8)
        bottom.pack(fill="x")
        ttk.Button(bottom, text="Update Config", command=self.save_json).pack(side="right")

    def open_json(self):
        fp = filedialog.askopenfilename(
            title="Open config.json",
            filetypes=[("JSON files", "*.json"), ("All files", "*.*")]
        )
        if not fp:
            return
        try:
            with open(fp, "r", encoding="utf-8") as f:
                self.data = json.load(f)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to read JSON:\n{e}")
            return

        self.file_path = fp
        self.path_lbl.config(text=fp)
        self.build_ui()

    def build_ui(self):
        # clear notebook
        for i in range(len(self.nb.tabs())):
            self.nb.forget(self.nb.tabs()[0])
        self.vars.clear()

        if not isinstance(self.data, dict):
            messagebox.showerror("Error", "Top-level JSON must be an object(dict).")
            return

        uds = self.data.get("uds", {})
        if not isinstance(uds, dict):
            messagebox.showerror("Error", "'uds' must be an object(dict).")
            return

        # 1) 탭 구성: uds 안의 dict 키들은 각자 탭, scalar 키들은 UDS(tab)로 모음
        scalar_paths = []
        dict_sections = []

        for k, v in uds.items():
            if isinstance(v, dict):
                dict_sections.append(k)
            else:
                scalar_paths.append((f"uds.{k}", v))

        # UDS(스칼라 모음) 탭
        uds_tab = self._new_scroll_tab("UDS")
        self._build_fields_in_tab(uds_tab, scalar_paths)

        # dict 섹션 탭들
        for sec in sorted(dict_sections):
            tab = self._new_scroll_tab(sec)
            leafs = flatten_dict(uds[sec], base_path=f"uds.{sec}")
            self._build_fields_in_tab(tab, leafs, add_group_separators=True)

    def _new_scroll_tab(self, name: str):
        outer = ttk.Frame(self.nb, padding=0)
        self.nb.add(outer, text=name)

        canvas = tk.Canvas(outer, borderwidth=0)
        scroll = ttk.Scrollbar(outer, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, padding=10)

        inner.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        # mouse wheel (windows)
        def _on_mousewheel(event):
            canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
        canvas.bind_all("<MouseWheel>", _on_mousewheel)

        return inner

    def _infer_type(self, value):
        if isinstance(value, bool):
            return "bool"
        if isinstance(value, int) and not isinstance(value, bool):
            return "int"
        if isinstance(value, float):
            return "float"
        # list/None 같은 것은 "json text"로 편집 가능하게 처리
        if isinstance(value, (list, type(None))):
            return "json"
        return "str"

    def _build_fields_in_tab(self, parent, path_value_list, add_group_separators=False):
        row = 0
        last_group = None

        for path, value in path_value_list:
            type_tag = self._infer_type(value)

            # 그룹 구분(중첩 경로 상위 1~2단) 표시
            if add_group_separators:
                seg = path.split(".")
                group = ".".join(seg[:-1])  # parent path
                if group != last_group:
                    ttk.Label(parent, text=group, font=("Segoe UI", 9, "bold")).grid(
                        row=row, column=0, columnspan=2, sticky="w", pady=(10, 4)
                    )
                    row += 1
                    last_group = group

            label = path.split(".")[-1]

            ttk.Label(parent, text=label, width=26).grid(row=row, column=0, sticky="w", pady=3)

            if type_tag == "bool":
                var = tk.BooleanVar(value=bool(value))
                ttk.Checkbutton(parent, variable=var).grid(row=row, column=1, sticky="w", pady=3)

            elif type_tag == "json":
                # list/None 같은 것은 JSON 문자열로 편집
                var = tk.StringVar(value=json.dumps(value, ensure_ascii=False))
                ent = ttk.Entry(parent, textvariable=var, width=70)
                ent.grid(row=row, column=1, sticky="we", pady=3)
                parent.grid_columnconfigure(1, weight=1)

            else:
                var = tk.StringVar(value=str(value))
                ent = ttk.Entry(parent, textvariable=var, width=70)
                ent.grid(row=row, column=1, sticky="we", pady=3)
                parent.grid_columnconfigure(1, weight=1)

            self.vars[path] = (var, type_tag)
            row += 1

    def save_json(self):
        if not self.data or not self.file_path:
            messagebox.showwarning("Warning", "No JSON file loaded.")
            return

        try:
            for path, (var, type_tag) in self.vars.items():
                raw = var.get() if hasattr(var, "get") else var

                if type_tag == "bool":
                    set_path(self.data, path, bool(var.get()))
                elif type_tag == "int":
                    set_path(self.data, path, to_int(raw))
                elif type_tag == "float":
                    set_path(self.data, path, to_float(raw))
                elif type_tag == "json":
                    # list/None 등 JSON 문자열로 입력받은 것을 다시 파싱
                    set_path(self.data, path, json.loads(raw))
                else:
                    set_path(self.data, path, str(raw).strip())

        except Exception as e:
            messagebox.showerror("Error", f"Invalid value:\n{e}")
            return

        try:
            bak = self.file_path + ".bak"
            if not os.path.exists(bak):
                with open(bak, "w", encoding="utf-8") as f:
                    json.dump(self.data, f, ensure_ascii=False, indent=2)

            with open(self.file_path, "w", encoding="utf-8") as f:
                json.dump(self.data, f, ensure_ascii=False, indent=2)

            messagebox.showinfo("Saved", f"Updated:\n{self.file_path}\nBackup:\n{bak}")
        except Exception as e:
            messagebox.showerror("Error", f"Failed to save:\n{e}")


if __name__ == "__main__":
    app = UDSConfigEditorDynamic()
    app.mainloop()
