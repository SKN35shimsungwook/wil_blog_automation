"""플레이데이터 주간회고(WIL) 자동화 데스크톱 앱.

공부 메모 -> AI 회고 생성 -> Markdown/HTML 미리보기 -> 티스토리 업로드 까지
한 화면에서 처리하는 Tkinter GUI.
"""
import queue
import threading
import tkinter as tk
from datetime import date
from tkinter import filedialog, messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import ai_generator
import code_files
import curriculum
import markdown_utils
import storage
import tistory_browser

REFLECTION_QUESTIONS = [
    "지난 일주일 동안 가장 인상 깊었던 배움은 무엇이었나요?",
    "그 배움까지 다가가는데 어떤 어려움이 있었나요?",
    "그 과정에서 나는 무엇을 깨달았고, 어떤 감정/생각이 들었나요?",
    "결과적으로, 현재 나의 상태는 어떤가요?",
    "이 상태에서 다음 한 주를 더 잘 보내려면 어떻게 해야 할까요?",
]


def fit_geometry(win, want_w: int, want_h: int, min_w: int = 400, min_h: int = 300):
    """화면 해상도보다 창이 커서 버튼이 화면 밖으로 잘리는 것을 방지.
    Tkinter의 geometry() 높이값에는 제목표시줄이 포함되지 않고(약 39px 추가),
    작업표시줄(약 48px)도 감안해야 해서 넉넉하게 여유를 두고 계산한다."""
    win.update_idletasks()
    screen_w = win.winfo_screenwidth()
    screen_h = win.winfo_screenheight()
    w = max(min(want_w, screen_w - 80), min_w)
    h = max(min(want_h, screen_h - 167), min_h)
    x = (screen_w - w) // 2
    y = 15
    geom = f"{w}x{h}+{x}+{y}"
    win.geometry(geom)
    # Windows가 창을 매핑하면서 초기 위치를 임의로 바꾸는 경우가 있어,
    # 창이 자리잡은 뒤 같은 위치를 강제로 한 번 더 지정한다.
    win.after(150, lambda: win.geometry(geom))


class SettingsDialog(tk.Toplevel):
    def __init__(self, parent, config: dict, on_save):
        super().__init__(parent)
        self.title("설정")
        fit_geometry(self, 580, 640, min_w=480, min_h=400)
        self.resizable(True, True)
        self.config_data = dict(config)
        self.on_save = on_save

        pad = {"padx": 10, "pady": 4}

        ai_frame = ttk.LabelFrame(self, text="AI 회고 생성 (Gemini API)")
        ai_frame.pack(fill="x", **pad)

        ttk.Label(ai_frame, text="API 키").grid(row=0, column=0, sticky="w", **pad)
        self.api_key_var = tk.StringVar(value=self.config_data.get("gemini_api_key", ""))
        ttk.Entry(ai_frame, textvariable=self.api_key_var, width=45, show="*").grid(
            row=0, column=1, **pad
        )

        ttk.Label(ai_frame, text="모델").grid(row=1, column=0, sticky="w", **pad)
        self.model_var = tk.StringVar(
            value=self.config_data.get("gemini_model", "gemini-flash-latest")
        )
        ttk.Entry(ai_frame, textvariable=self.model_var, width=45).grid(row=1, column=1, **pad)

        ttk.Label(
            self,
            text="aistudio.google.com/apikey 에서 발급받은 키를 입력하세요. (무료 등급 제공)",
            foreground="gray",
        ).pack(anchor="w", padx=14)

        title_frame = ttk.LabelFrame(self, text="제목 형식")
        title_frame.pack(fill="x", **pad)

        ttk.Label(title_frame, text="캠프명").grid(row=0, column=0, sticky="w", **pad)
        self.camp_name_var = tk.StringVar(
            value=self.config_data.get("camp_name", "SK 네트웍스 Family AI 캠프")
        )
        ttk.Entry(title_frame, textvariable=self.camp_name_var, width=45).grid(
            row=0, column=1, **pad
        )

        ttk.Label(title_frame, text="기수").grid(row=1, column=0, sticky="w", **pad)
        self.camp_gisu_var = tk.StringVar(value=self.config_data.get("camp_gisu", "35"))
        ttk.Entry(title_frame, textvariable=self.camp_gisu_var, width=45).grid(
            row=1, column=1, **pad
        )

        ttk.Label(title_frame, text="캠프 시작일").grid(row=2, column=0, sticky="w", **pad)
        self.camp_start_var = tk.StringVar(
            value=self.config_data.get("camp_start_date", "2026-07-07")
        )
        ttk.Entry(title_frame, textvariable=self.camp_start_var, width=45).grid(
            row=2, column=1, **pad
        )
        ttk.Label(
            title_frame, text="YYYY-MM-DD. 이 날짜가 속한 주(월~일)를 1주차로 계산합니다.",
            foreground="gray",
        ).grid(row=3, column=1, sticky="w", padx=10)

        ttk.Label(
            title_frame,
            text="제목은 항상 '[캠프명] {기수}기 {주차}주차 회고' 형식으로 자동 조립됩니다.\n"
            "주차는 메인 화면에서 지정(자동 제안됨)합니다.",
            foreground="gray",
            justify="left",
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 6))

        tistory_frame = ttk.LabelFrame(self, text="티스토리 자동 업로드 (브라우저 자동화)")
        tistory_frame.pack(fill="x", **pad)

        ttk.Label(tistory_frame, text="블로그 이름").grid(row=0, column=0, sticky="w", **pad)
        self.blog_name_var = tk.StringVar(value=self.config_data.get("tistory_blog_name", ""))
        ttk.Entry(tistory_frame, textvariable=self.blog_name_var, width=45).grid(
            row=0, column=1, **pad
        )
        ttk.Label(
            tistory_frame, text="예: myid.tistory.com 이면 'myid'만 입력", foreground="gray"
        ).grid(row=1, column=1, sticky="w", padx=10)

        ttk.Label(
            tistory_frame,
            text=(
                "티스토리 Open API는 종료되었고 로그인도 카카오계정 전용이라,\n"
                "브라우저 창을 직접 띄워 화면을 자동 조작하는 방식으로 동작합니다.\n"
                "아래 버튼을 누르면 브라우저가 열리며, 그 창에서 직접 카카오 로그인을 "
                "완료해주세요.\n(비밀번호는 앱이 아닌 브라우저 화면에 본인이 직접 입력합니다)"
            ),
            foreground="gray",
            justify="left",
            wraplength=480,
        ).grid(row=2, column=0, columnspan=2, sticky="w", padx=10, pady=(4, 8))

        self.login_status_var = tk.StringVar(value="")
        ttk.Button(
            tistory_frame, text="티스토리 로그인 / 세션 갱신", command=self._start_login
        ).grid(row=3, column=0, sticky="w", **pad)
        ttk.Label(tistory_frame, textvariable=self.login_status_var, foreground="gray").grid(
            row=3, column=1, sticky="w", padx=10
        )

        btn_frame = ttk.Frame(self)
        btn_frame.pack(fill="x", pady=12)
        ttk.Button(btn_frame, text="저장", command=self._save).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side="right")

    def _start_login(self):
        blog_name = self.blog_name_var.get().strip()
        if not blog_name:
            messagebox.showwarning("안내", "블로그 이름을 먼저 입력해주세요.")
            return

        result_queue: "queue.Queue" = queue.Queue()

        def worker():
            try:
                ok = tistory_browser.ensure_login(
                    blog_name, on_status=lambda msg: result_queue.put(("status", msg))
                )
                result_queue.put(("done", ok))
            except Exception as exc:  # noqa: BLE001
                result_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_login(result_queue)

    def _poll_login(self, result_queue: "queue.Queue"):
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll_login(result_queue))
            return

        if kind == "status":
            self.login_status_var.set(payload)
            self.after(150, lambda: self._poll_login(result_queue))
            return
        if kind == "error":
            self.login_status_var.set("로그인 실패")
            messagebox.showerror("실패", payload)
            return

        if payload:
            self.login_status_var.set("로그인 세션이 저장되었습니다.")
        else:
            self.login_status_var.set("로그인 대기 시간이 초과되었습니다.")

    def _save(self):
        self.config_data.update(
            {
                "gemini_api_key": self.api_key_var.get().strip(),
                "gemini_model": self.model_var.get().strip() or "gemini-flash-latest",
                "tistory_blog_name": self.blog_name_var.get().strip(),
                "camp_name": self.camp_name_var.get().strip() or "SK 네트웍스 Family AI 캠프",
                "camp_gisu": self.camp_gisu_var.get().strip() or "35",
                "camp_start_date": self.camp_start_var.get().strip() or "2026-07-07",
            }
        )
        storage.save_config(self.config_data)
        self.on_save(self.config_data)
        self.destroy()


class WilApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("플레이데이터 주간회고(WIL) 자동화")
        fit_geometry(self, 1280, 800, min_w=900, min_h=600)

        self.config_data = storage.load_config()
        self.history = storage.load_history()
        self.result_queue: "queue.Queue" = queue.Queue()
        self.last_data = None
        self.busy = False

        self._build_menu()
        self._build_layout()
        self._build_statusbar()

    # ---------- UI 구성 ----------
    def _build_menu(self):
        menubar = tk.Menu(self)
        file_menu = tk.Menu(menubar, tearoff=0)
        file_menu.add_command(label="메모 파일 불러오기...", command=self.load_notes_from_file)
        file_menu.add_separator()
        file_menu.add_command(label="종료", command=self.destroy)
        menubar.add_cascade(label="파일", menu=file_menu)

        settings_menu = tk.Menu(menubar, tearoff=0)
        settings_menu.add_command(label="API / 티스토리 설정...", command=self.open_settings)
        menubar.add_cascade(label="설정", menu=settings_menu)

        self.config(menu=menubar)

    def _build_layout(self):
        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=8)

        left = ttk.Frame(main)
        main.add(left, weight=1)

        header = ttk.Frame(left)
        header.pack(fill="x", pady=(0, 6))
        ttk.Label(header, text="주차").pack(side="left")
        self.week_var = tk.IntVar(value=self._suggested_week())
        week_spin = ttk.Spinbox(
            header, from_=1, to=99, width=5, textvariable=self.week_var,
            command=self._on_week_changed,
        )
        week_spin.pack(side="left", padx=(4, 16))
        week_spin.bind("<FocusOut>", lambda e: self._on_week_changed())
        week_spin.bind("<Return>", lambda e: self._on_week_changed())
        self.title_preview_var = tk.StringVar()
        ttk.Label(header, textvariable=self.title_preview_var, foreground="gray").pack(
            side="left"
        )

        left_notebook = ttk.Notebook(left)
        left_notebook.pack(fill="both", expand=True)

        notes_tab = ttk.Frame(left_notebook)
        left_notebook.add(notes_tab, text="공부 메모")
        ttk.Label(notes_tab, text="이번 주 공부 메모 (자유 형식으로 편하게)").pack(
            anchor="w", padx=4, pady=(4, 4)
        )
        self.notes_text = ScrolledText(notes_tab, wrap="word", font=("Consolas", 11))
        self.notes_text.pack(fill="both", expand=True, padx=4, pady=(0, 4))
        self.notes_text.insert(
            "1.0",
            "예)\n8월 4일\nPython / Selenium\n- WebDriverWait 사용법\n\n문제: NoSuchElementException\n해결: WebDriverWait로 대기 후 접근하니 해결됨",
        )

        reflect_tab = ttk.Frame(left_notebook)
        left_notebook.add(reflect_tab, text="성찰 질문")

        reflect_canvas = tk.Canvas(reflect_tab, highlightthickness=0)
        reflect_scrollbar = ttk.Scrollbar(
            reflect_tab, orient="vertical", command=reflect_canvas.yview
        )
        reflect_inner = ttk.Frame(reflect_canvas)
        reflect_inner.bind(
            "<Configure>",
            lambda e: reflect_canvas.configure(scrollregion=reflect_canvas.bbox("all")),
        )
        reflect_canvas.create_window((0, 0), window=reflect_inner, anchor="nw")
        reflect_canvas.configure(yscrollcommand=reflect_scrollbar.set)
        reflect_canvas.pack(side="left", fill="both", expand=True)
        reflect_scrollbar.pack(side="right", fill="y")

        self.reflection_texts = []
        for q in REFLECTION_QUESTIONS:
            ttk.Label(reflect_inner, text=q, wraplength=500, justify="left").pack(
                anchor="w", padx=6, pady=(10, 2)
            )
            t = tk.Text(reflect_inner, height=3, wrap="word", font=("Consolas", 10))
            t.pack(fill="x", padx=6)
            self.reflection_texts.append(t)
        ttk.Label(
            reflect_inner,
            text="비워두면 공부 메모만으로 성찰 부분을 추론합니다.",
            foreground="gray",
        ).pack(anchor="w", padx=6, pady=(10, 4))

        code_tab = ttk.Frame(left_notebook)
        left_notebook.add(code_tab, text="코드 파일")
        ttk.Label(
            code_tab,
            text="이번 주 관련 .py / .ipynb 파일을 첨부하면, 관련 코드를 그대로 인용해서 배치합니다.",
            wraplength=520, justify="left",
        ).pack(anchor="w", padx=6, pady=(10, 6))
        self.code_file_paths: list = []
        self.code_listbox = tk.Listbox(code_tab, height=8)
        self.code_listbox.pack(fill="both", expand=True, padx=6, pady=4)
        code_btn_row = ttk.Frame(code_tab)
        code_btn_row.pack(fill="x", padx=6, pady=(0, 8))
        ttk.Button(code_btn_row, text="파일 첨부", command=self._attach_code_files).pack(
            side="left"
        )
        ttk.Button(code_btn_row, text="선택 제거", command=self._remove_code_file).pack(
            side="left", padx=6
        )

        ttk.Button(left, text="파일에서 불러오기", command=self.load_notes_from_file).pack(
            anchor="e", pady=6
        )

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", pady=(4, 0))
        self.generate_btn = ttk.Button(
            btn_row, text="① AI 회고 생성", command=lambda: self.run_generate(regenerate=False)
        )
        self.generate_btn.pack(side="left", padx=(0, 6))
        self.regenerate_btn = ttk.Button(
            btn_row, text="다시 생성", command=lambda: self.run_generate(regenerate=True)
        )
        self.regenerate_btn.pack(side="left", padx=6)
        ttk.Button(btn_row, text="복사", command=self.copy_markdown).pack(side="left", padx=6)
        ttk.Button(btn_row, text="Markdown 저장", command=self.save_markdown).pack(
            side="left", padx=6
        )
        ttk.Button(btn_row, text="HTML 저장", command=self.save_html).pack(side="left", padx=6)
        self.upload_btn = ttk.Button(
            btn_row, text="② 티스토리 업로드", command=self.upload_to_tistory
        )
        self.upload_btn.pack(side="left", padx=6)

        right = ttk.Frame(main)
        main.add(right, weight=1)

        self.notebook = ttk.Notebook(right)
        self.notebook.pack(fill="both", expand=True)

        self.preview_text = ScrolledText(self.notebook, wrap="word", font=("Consolas", 11))
        self.notebook.add(self.preview_text, text="미리보기 (Markdown)")

        self.html_text = ScrolledText(self.notebook, wrap="word", font=("Consolas", 10))
        self.notebook.add(self.html_text, text="HTML")

        meta_tab = ttk.Frame(self.notebook)
        self.notebook.add(meta_tab, text="제목 추천 / 태그")

        ttk.Label(meta_tab, text="게시할 제목 (고정 형식, 자동 생성됨)").pack(
            anchor="w", padx=8, pady=(8, 0)
        )
        self.title_var = tk.StringVar()
        ttk.Entry(meta_tab, textvariable=self.title_var, font=("Consolas", 11)).pack(
            fill="x", padx=8, pady=4
        )
        ttk.Label(
            meta_tab,
            text="설정의 캠프명/기수 + 왼쪽 상단 '주차'로 자동 조립됩니다. 필요하면 직접 수정 가능.",
            foreground="gray",
        ).pack(anchor="w", padx=8)

        ttk.Label(meta_tab, text="태그").pack(anchor="w", padx=8, pady=(12, 0))
        self.tags_var = tk.StringVar()
        ttk.Entry(meta_tab, textvariable=self.tags_var).pack(fill="x", padx=8, pady=4)
        ttk.Label(meta_tab, text="쉼표(,)로 구분", foreground="gray").pack(anchor="w", padx=8)

        ttk.Label(meta_tab, text="AI 부제 아이디어 (참고용, 더블클릭하면 복사)").pack(
            anchor="w", padx=8, pady=(12, 0)
        )
        self.title_listbox = tk.Listbox(meta_tab, height=6)
        self.title_listbox.pack(fill="x", padx=8, pady=4)
        self.title_listbox.bind("<Double-Button-1>", self._select_title_from_list)

        insight_tab = ttk.Frame(self.notebook)
        self.notebook.add(insight_tab, text="성장 인사이트")
        self.insight_text = ScrolledText(insight_tab, wrap="word", font=("Consolas", 10))
        self.insight_text.pack(fill="both", expand=True, padx=8, pady=8)
        self._refresh_insight_tab()

        self._on_week_changed()

    def _build_statusbar(self):
        self.status_var = tk.StringVar(value="준비 완료")
        bar = ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken")
        bar.pack(fill="x", side="bottom")

    # ---------- 동작 ----------
    def open_settings(self):
        SettingsDialog(self, self.config_data, on_save=self._on_settings_saved)

    def _on_settings_saved(self, new_config: dict):
        self.config_data = new_config
        self._on_week_changed()
        self.set_status("설정을 저장했습니다.")

    def set_status(self, text: str):
        self.status_var.set(text)

    def _camp_start_date(self) -> date:
        try:
            return date.fromisoformat(self.config_data.get("camp_start_date", "2026-07-07"))
        except ValueError:
            return date(2026, 7, 7)

    def _suggested_week(self) -> int:
        return curriculum.suggested_week_number(date.today(), self._camp_start_date())

    def _compute_title(self) -> str:
        camp_name = self.config_data.get("camp_name", "SK 네트웍스 Family AI 캠프")
        gisu = self.config_data.get("camp_gisu", "35")
        try:
            week = int(self.week_var.get())
        except (tk.TclError, ValueError):
            week = self._suggested_week()
        return f"[{camp_name}] {gisu}기 {week}주차 회고"

    def _on_week_changed(self):
        computed = self._compute_title()
        self.title_preview_var.set(f"제목: {computed}")
        self.title_var.set(computed)
        if self.last_data:
            self._refresh_preview()

    def _current_week_topic(self) -> str:
        try:
            week = int(self.week_var.get())
        except (tk.TclError, ValueError):
            week = self._suggested_week()
        return curriculum.topics_for_week(week, self._camp_start_date())

    def _reflection_block(self) -> str:
        blocks = []
        for question, widget in zip(REFLECTION_QUESTIONS, self.reflection_texts):
            answer = widget.get("1.0", "end").strip()
            if answer:
                blocks.append(f"Q: {question}\nA: {answer}")
        return "\n\n".join(blocks)

    def load_notes_from_file(self):
        path = filedialog.askopenfilename(
            filetypes=[("텍스트/마크다운", "*.txt *.md"), ("모든 파일", "*.*")]
        )
        if not path:
            return
        with open(path, encoding="utf-8", errors="ignore") as f:
            content = f.read()
        self.notes_text.delete("1.0", "end")
        self.notes_text.insert("1.0", content)
        self.set_status(f"메모 불러옴: {path}")

    def _attach_code_files(self):
        paths = filedialog.askopenfilenames(
            filetypes=[("Python / Jupyter", "*.py *.ipynb"), ("모든 파일", "*.*")]
        )
        for p in paths:
            if p not in self.code_file_paths:
                self.code_file_paths.append(p)
                self.code_listbox.insert("end", p)
        if paths:
            self.set_status(f"코드 파일 {len(paths)}개 첨부됨")

    def _remove_code_file(self):
        selection = list(self.code_listbox.curselection())
        for index in reversed(selection):
            self.code_listbox.delete(index)
            del self.code_file_paths[index]

    def run_generate(self, regenerate: bool):
        if self.busy:
            return
        notes = self.notes_text.get("1.0", "end").strip()
        if not notes:
            messagebox.showwarning("안내", "공부 메모를 먼저 입력해주세요.")
            return
        if not self.config_data.get("gemini_api_key"):
            messagebox.showwarning("안내", "설정에서 Gemini API 키를 먼저 입력해주세요.")
            return

        self.busy = True
        self.generate_btn.config(state="disabled")
        self.regenerate_btn.config(state="disabled")
        self.set_status("AI가 회고를 작성 중입니다... (수 초 정도 소요)")

        reflection_block = self._reflection_block()
        curriculum_topic = self._current_week_topic()
        code_context = code_files.extract_code_context(self.code_file_paths)

        def worker():
            try:
                data = ai_generator.generate_wil(
                    api_key=self.config_data["gemini_api_key"],
                    model=self.config_data.get("gemini_model", "gemini-flash-latest"),
                    notes=notes,
                    history=self.history,
                    regenerate=regenerate,
                    reflection_answers=reflection_block,
                    curriculum_topic=curriculum_topic,
                    code_context=code_context,
                )
                self.result_queue.put(("ok", data))
            except Exception as exc:  # noqa: BLE001
                self.result_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self.after(150, self._poll_generate_result)

    def _poll_generate_result(self):
        try:
            status, payload = self.result_queue.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_generate_result)
            return

        self.busy = False
        self.generate_btn.config(state="normal")
        self.regenerate_btn.config(state="normal")

        if status == "error":
            self.set_status("생성 실패")
            messagebox.showerror("생성 실패", payload)
            return

        self.last_data = payload
        self._apply_generated_data(payload)
        self.set_status("회고 생성 완료")

    def _apply_generated_data(self, data: dict):
        titles = data.get("title_suggestions", [])
        self.title_listbox.delete(0, "end")
        for t in titles:
            self.title_listbox.insert("end", t)
        self.title_var.set(self._compute_title())
        self.tags_var.set(", ".join(data.get("tags", [])))

        self._refresh_preview()

        self.history = storage.load_history()
        storage.append_history_entry(
            {
                "date": date.today().isoformat(),
                "title": self.title_var.get(),
                "tags": data.get("tags", []),
                "one_line_summary": data.get("one_line_summary", ""),
            }
        )
        self.history = storage.load_history()
        self._refresh_insight_tab()

    def _select_title_from_list(self, _event):
        selection = self.title_listbox.curselection()
        if not selection:
            return
        text = self.title_listbox.get(selection[0])
        self.clipboard_clear()
        self.clipboard_append(text)
        self.set_status(f"부제 아이디어를 클립보드에 복사했습니다: {text}")

    def _current_markdown_body(self) -> str:
        return self.last_data.get("markdown_body", "") if self.last_data else ""

    def _refresh_preview(self):
        title = self.title_var.get().strip() or "이번 주 주간회고"
        assembled = markdown_utils.assemble_markdown(title, self._current_markdown_body())
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", assembled)
        self._refresh_html_preview()

    def _body_only_html(self) -> str:
        """티스토리 업로드용. 제목은 에디터의 별도 제목칸에 들어가므로, 본문 HTML에
        제목(H1)을 또 넣으면 중복된다 -> markdown_body만 변환해서 반환한다."""
        return markdown_utils.markdown_to_html(self._current_markdown_body())

    def _refresh_html_preview(self):
        current_md = self.preview_text.get("1.0", "end")
        html = markdown_utils.markdown_to_html(current_md)
        self.html_text.delete("1.0", "end")
        self.html_text.insert("1.0", html)

    def _refresh_insight_tab(self):
        self.insight_text.delete("1.0", "end")
        if not self.history:
            self.insight_text.insert("1.0", "아직 저장된 회고 이력이 없습니다. 첫 회고를 생성해보세요!")
            return

        tag_counter: dict[str, int] = {}
        for entry in self.history:
            for tag in entry.get("tags", []):
                tag_counter[tag] = tag_counter.get(tag, 0) + 1
        ranked = sorted(tag_counter.items(), key=lambda kv: kv[1], reverse=True)

        lines = [f"누적 회고 수: {len(self.history)}주\n"]
        lines.append("가장 많이 다룬 기술 태그 Top 5:")
        for tag, count in ranked[:5]:
            lines.append(f"  - {tag} ({count}회)")

        if len(self.history) >= 2:
            prev_tags = set(self.history[-2].get("tags", []))
            curr_tags = set(self.history[-1].get("tags", []))
            new_tags = curr_tags - prev_tags
            if new_tags:
                lines.append(f"\n지난주 대비 새로 등장한 태그: {', '.join(sorted(new_tags))}")

        lines.append("\n최근 회고 한 줄 요약:")
        for entry in self.history[-5:]:
            lines.append(f"  - {entry.get('date')}: {entry.get('one_line_summary', '')}")

        self.insight_text.insert("1.0", "\n".join(lines))

    def copy_markdown(self):
        content = self.preview_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("안내", "먼저 회고를 생성해주세요.")
            return
        self.clipboard_clear()
        self.clipboard_append(content)
        self.set_status("클립보드에 마크다운을 복사했습니다.")

    def save_markdown(self):
        content = self.preview_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("안내", "먼저 회고를 생성해주세요.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".md",
            initialfile=markdown_utils.default_filename("WIL", "md"),
            filetypes=[("Markdown", "*.md")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        self.set_status(f"Markdown 저장 완료: {path}")

    def save_html(self):
        self._refresh_html_preview()
        content = self.html_text.get("1.0", "end").strip()
        if not content:
            messagebox.showwarning("안내", "먼저 회고를 생성해주세요.")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".html",
            initialfile=markdown_utils.default_filename("WIL", "html"),
            filetypes=[("HTML", "*.html")],
        )
        if not path:
            return
        with open(path, "w", encoding="utf-8") as f:
            f.write(content + "\n")
        self.set_status(f"HTML 저장 완료: {path}")

    def upload_to_tistory(self):
        if not self.last_data:
            messagebox.showwarning("안내", "먼저 회고를 생성해주세요.")
            return
        blog_name = self.config_data.get("tistory_blog_name")
        if not blog_name:
            messagebox.showwarning("안내", "설정에서 티스토리 블로그 이름을 먼저 등록해주세요.")
            return

        title = self.title_var.get().strip() or "이번 주 주간회고"
        tags = [t.strip() for t in self.tags_var.get().split(",") if t.strip()]
        html_content = self._body_only_html()

        confirm = ConfirmUploadDialog(self, title=title, blog=blog_name)
        self.wait_window(confirm)
        if not confirm.confirmed:
            return

        progress = UploadProgressDialog(self)

        def worker():
            try:
                result = tistory_browser.post_to_tistory(
                    blog_name=blog_name,
                    title=title,
                    html_content=html_content,
                    tags=tags,
                    visibility_label=confirm.visibility_var.get(),
                    on_status=lambda msg: progress.result_queue.put(("status", msg)),
                    should_cancel=lambda: progress.cancelled,
                )
                progress.result_queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                progress.result_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_upload(progress)

    def _poll_upload(self, progress: "UploadProgressDialog"):
        if not progress.winfo_exists():
            return
        try:
            kind, payload = progress.result_queue.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll_upload(progress))
            return

        if kind == "status":
            progress.set_status(payload)
            self.after(150, lambda: self._poll_upload(progress))
            return

        progress.destroy()

        if kind == "error":
            self.set_status("티스토리 업로드 실패")
            messagebox.showerror("업로드 실패", payload)
            return

        url = payload.get("url")
        if not url:
            self.set_status("티스토리 업로드가 취소되었거나 결과를 확인하지 못했습니다.")
            return

        self.set_status(f"티스토리 업로드 완료: {url}")
        messagebox.showinfo("업로드 완료", f"티스토리에 게시되었습니다.\n{url}")


class UploadProgressDialog(tk.Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.title("티스토리 업로드 진행 중")
        self.geometry("460x140")
        self.resizable(False, False)
        self.result_queue: "queue.Queue" = queue.Queue()
        self.cancelled = False
        self.protocol("WM_DELETE_WINDOW", self._cancel)

        self.status_var = tk.StringVar(value="브라우저를 여는 중입니다...")
        ttk.Label(self, textvariable=self.status_var, wraplength=420, justify="left").pack(
            padx=16, pady=20, fill="both", expand=True
        )
        ttk.Button(self, text="취소", command=self._cancel).pack(pady=(0, 12))

    def set_status(self, text: str):
        self.status_var.set(text)

    def _cancel(self):
        self.cancelled = True
        self.status_var.set("취소 중... 브라우저 창을 확인해주세요.")


class ConfirmUploadDialog(tk.Toplevel):
    def __init__(self, parent, title: str, blog: str):
        super().__init__(parent)
        self.title("티스토리 업로드 확인")
        self.geometry("420x220")
        self.resizable(False, False)
        self.confirmed = False

        ttk.Label(self, text=f"'{blog}.tistory.com' 블로그에 아래 글을 게시할까요?", wraplength=380).pack(
            padx=14, pady=(16, 6), anchor="w"
        )
        ttk.Label(self, text=f"제목: {title}", wraplength=380, foreground="gray").pack(
            padx=14, anchor="w"
        )

        ttk.Label(self, text="공개 범위").pack(padx=14, pady=(16, 0), anchor="w")
        self.visibility_var = tk.StringVar(value="비공개")
        ttk.Combobox(
            self,
            textvariable=self.visibility_var,
            values=["비공개", "공개(보호)", "공개"],
            state="readonly",
        ).pack(padx=14, pady=4, anchor="w")

        btn_frame = ttk.Frame(self)
        btn_frame.pack(side="bottom", fill="x", pady=14)
        ttk.Button(btn_frame, text="취소", command=self.destroy).pack(side="right", padx=10)
        ttk.Button(btn_frame, text="게시", command=self._confirm).pack(side="right")

    def _confirm(self):
        self.confirmed = True
        self.destroy()


if __name__ == "__main__":
    app = WilApp()
    app.mainloop()
