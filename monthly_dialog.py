"""월간 종합 회고 생성/업로드 창.

한 달 동안 발행한 주간회고들을 history.json에서 모아 링크와 함께 종합하고,
월간 성찰 질문(객관식+기타 하이브리드)을 거쳐 하나의 월간 회고 글로 만든다.
"""
import queue
import threading
import tkinter as tk
from datetime import date
from tkinter import messagebox, ttk
from tkinter.scrolledtext import ScrolledText

import ai_generator
import curriculum
import markdown_utils
import storage
import tistory_browser

MONTHLY_QUESTIONS = [
    "이번 달 가장 크게 성장했다고 느끼는 부분은?",
    "이번 달 가장 기억에 남는 트러블슈팅이나 프로젝트는?",
    "이번 달을 스스로 평가한다면? (만족도, 아쉬운 점)",
    "다음 달에는 무엇에 집중하고 싶나요?",
]


class MonthlyReviewDialog(tk.Toplevel):
    def __init__(self, parent, config_data: dict, fit_geometry):
        super().__init__(parent)
        self.title("월간 종합 회고")
        fit_geometry(self, 1000, 720, min_w=760, min_h=520)
        self.config_data = config_data
        self.last_data = None
        self.week_entries: list = []
        self.title_value = ""
        self.busy = False
        self.uploading = False

        self._build_layout()
        self._load_default_month()

    def _camp_start_date(self) -> date:
        try:
            return date.fromisoformat(self.config_data.get("camp_start_date", "2026-07-07"))
        except ValueError:
            return date(2026, 7, 7)

    # ---------- UI ----------
    def _build_layout(self):
        top = ttk.Frame(self)
        top.pack(fill="x", padx=8, pady=8)
        ttk.Label(top, text="연-월 (YYYY-MM)").pack(side="left")
        self.month_var = tk.StringVar()
        ttk.Entry(top, textvariable=self.month_var, width=10).pack(side="left", padx=6)
        ttk.Button(top, text="이 달 목록 불러오기", command=self._load_month_entries).pack(
            side="left", padx=6
        )
        self.title_preview_var = tk.StringVar()
        ttk.Label(top, textvariable=self.title_preview_var, foreground="gray").pack(
            side="left", padx=10
        )

        main = ttk.PanedWindow(self, orient="horizontal")
        main.pack(fill="both", expand=True, padx=8, pady=(0, 8))

        left = ttk.Frame(main)
        main.add(left, weight=1)

        ttk.Label(left, text="이번 달 회고 목록").pack(anchor="w")
        self.entries_listbox = tk.Listbox(left, height=6)
        self.entries_listbox.pack(fill="x", pady=4)

        reflect_canvas = tk.Canvas(left, highlightthickness=0)
        reflect_scrollbar = ttk.Scrollbar(left, orient="vertical", command=reflect_canvas.yview)
        reflect_inner = ttk.Frame(reflect_canvas)
        reflect_inner.bind(
            "<Configure>",
            lambda e: reflect_canvas.configure(scrollregion=reflect_canvas.bbox("all")),
        )
        reflect_canvas.create_window((0, 0), window=reflect_inner, anchor="nw")
        reflect_canvas.configure(yscrollcommand=reflect_scrollbar.set)
        reflect_canvas.pack(side="left", fill="both", expand=True, pady=(8, 0))
        reflect_scrollbar.pack(side="right", fill="y")

        self.reflection_texts = []
        self.reflection_choice_vars = []
        self.reflection_option_frames = []
        for q in MONTHLY_QUESTIONS:
            ttk.Label(reflect_inner, text=q, wraplength=440, justify="left").pack(
                anchor="w", pady=(10, 2)
            )
            opt_frame = ttk.Frame(reflect_inner)
            opt_frame.pack(anchor="w", fill="x")
            self.reflection_option_frames.append(opt_frame)
            self.reflection_choice_vars.append(tk.StringVar(value=""))
            t = tk.Text(reflect_inner, height=2, wrap="word", font=("Consolas", 10))
            t.pack(fill="x", pady=(2, 0))
            self.reflection_texts.append(t)
        ttk.Label(
            reflect_inner,
            text="직접 입력이 선택지보다 우선합니다.",
            foreground="gray",
        ).pack(anchor="w", pady=(8, 4))

        btn_row = ttk.Frame(left)
        btn_row.pack(fill="x", pady=8)
        self.options_btn = ttk.Button(btn_row, text="① 선택지 생성", command=self._generate_options)
        self.options_btn.pack(side="left")
        self.review_btn = ttk.Button(btn_row, text="② 월간 회고 생성", command=self._generate_review)
        self.review_btn.pack(side="left", padx=6)
        self.upload_btn = ttk.Button(btn_row, text="③ 티스토리 업로드", command=self._upload)
        self.upload_btn.pack(side="left", padx=6)

        right = ttk.Frame(main)
        main.add(right, weight=1)
        ttk.Label(right, text="미리보기 (Markdown)").pack(anchor="w")
        self.preview_text = ScrolledText(right, wrap="word", font=("Consolas", 11))
        self.preview_text.pack(fill="both", expand=True)

        self.status_var = tk.StringVar(value="준비 완료")
        ttk.Label(self, textvariable=self.status_var, anchor="w", relief="sunken").pack(
            fill="x", side="bottom"
        )

    # ---------- 데이터 ----------
    def _load_default_month(self):
        today = date.today()
        self.month_var.set(f"{today.year:04d}-{today.month:02d}")
        self._load_month_entries()

    @staticmethod
    def _normalize_month_key(raw: str) -> str:
        """'2026-7'처럼 0을 안 채워 입력해도 '2026-07'과 매칭되도록 정규화한다."""
        raw = raw.strip()
        try:
            year_str, month_str = raw.split("-")
            return f"{int(year_str):04d}-{int(month_str):02d}"
        except (ValueError, AttributeError):
            return raw

    def _load_month_entries(self):
        month_key = self._normalize_month_key(self.month_var.get())
        self.month_var.set(month_key)
        history = storage.load_history()
        start = self._camp_start_date()
        self.week_entries = [
            h
            for h in history
            if isinstance(h.get("week"), int)
            and curriculum.month_key_for_week(h["week"], start) == month_key
        ]
        self.week_entries.sort(key=lambda h: h["week"])

        self.entries_listbox.delete(0, "end")
        for e in self.week_entries:
            url = e.get("url") or "(미업로드)"
            self.entries_listbox.insert("end", f"{e['week']}회차 - {e.get('title', '')} - {url}")

        gisu = self.config_data.get("camp_gisu", "35")
        camp_name = self.config_data.get("camp_name", "SK 네트웍스 Family AI 캠프")
        try:
            month_num = int(month_key.split("-")[1])
        except (IndexError, ValueError):
            month_num = 0
        self.title_value = f"[{camp_name}] {gisu}기 {month_num}월종합회고록"
        self.title_preview_var.set(f"제목: {self.title_value}")

        missing = [e for e in self.week_entries if not e.get("url")]
        if not self.week_entries:
            self.status_var.set("이 달에 저장된 회고가 없습니다.")
        elif missing:
            self.status_var.set(
                f"{len(self.week_entries)}개 회고 로드됨 (이 중 {len(missing)}개는 아직 "
                "업로드 안 되어 링크 없이 진행됩니다)"
            )
        else:
            self.status_var.set(f"{len(self.week_entries)}개 회고 로드됨")

    def _week_summaries_text(self) -> str:
        lines = []
        for e in self.week_entries:
            url = e.get("url", "")
            tags = ", ".join(e.get("tags", []))
            link_part = f"({url})" if url else "(미업로드)"
            lines.append(
                f"- {e['week']}회차 [{e.get('title', '')}]{link_part}: "
                f"{e.get('one_line_summary', '')} (태그: {tags})"
            )
        return "\n".join(lines)

    def _reflection_block(self) -> str:
        blocks = []
        for i, q in enumerate(MONTHLY_QUESTIONS):
            custom = self.reflection_texts[i].get("1.0", "end").strip()
            choice = self.reflection_choice_vars[i].get() if i < len(self.reflection_choice_vars) else ""
            answer = custom or choice
            if answer:
                blocks.append(f"Q: {q}\nA: {answer}")
        return "\n\n".join(blocks)

    def _apply_reflection_options(self, options: list):
        for i, opts in enumerate(options):
            if i >= len(self.reflection_option_frames):
                break
            container = self.reflection_option_frames[i]
            for child in container.winfo_children():
                child.destroy()
            var = self.reflection_choice_vars[i]
            for opt in opts:
                ttk.Radiobutton(container, text=opt, value=opt, variable=var).pack(anchor="w")

    # ---------- 액션 ----------
    def _generate_options(self):
        if self.busy:
            return
        if not self.week_entries:
            messagebox.showwarning("안내", "먼저 '이 달 목록 불러오기'를 눌러주세요.")
            return
        if not self.config_data.get("gemini_api_key"):
            messagebox.showwarning("안내", "설정에서 Gemini API 키를 먼저 입력해주세요.")
            return
        summaries = self._week_summaries_text()
        self.busy = True
        self.options_btn.config(state="disabled")
        self.review_btn.config(state="disabled")
        self.status_var.set("월간 성찰 선택지를 만드는 중...")
        result_queue: "queue.Queue" = queue.Queue()

        def worker():
            try:
                options = ai_generator.generate_monthly_reflection_options(
                    api_key=self.config_data["gemini_api_key"],
                    model=self.config_data.get("gemini_model", "gemini-flash-lite-latest"),
                    week_summaries=summaries,
                    monthly_questions=MONTHLY_QUESTIONS,
                )
                result_queue.put(("ok", options))
            except Exception as exc:  # noqa: BLE001
                result_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_simple(result_queue, self._on_options_done)

    def _on_options_done(self, status, payload):
        self.busy = False
        self.options_btn.config(state="normal")
        self.review_btn.config(state="normal")
        if status == "error":
            self.status_var.set("선택지 생성 실패")
            messagebox.showerror("실패", payload)
            return
        self._apply_reflection_options(payload)
        self.status_var.set("선택지 생성 완료")

    def _generate_review(self):
        if self.busy:
            return
        if not self.week_entries:
            messagebox.showwarning("안내", "먼저 '이 달 목록 불러오기'를 눌러주세요.")
            return
        if not self.config_data.get("gemini_api_key"):
            messagebox.showwarning("안내", "설정에서 Gemini API 키를 먼저 입력해주세요.")
            return
        summaries = self._week_summaries_text()
        reflection = self._reflection_block()
        self.busy = True
        self.options_btn.config(state="disabled")
        self.review_btn.config(state="disabled")
        self.status_var.set("월간 종합 회고를 생성하는 중...")
        result_queue: "queue.Queue" = queue.Queue()

        def worker():
            try:
                data = ai_generator.generate_monthly_review(
                    api_key=self.config_data["gemini_api_key"],
                    model=self.config_data.get("gemini_model", "gemini-flash-lite-latest"),
                    week_summaries=summaries,
                    reflection_answers=reflection,
                )
                result_queue.put(("ok", data))
            except Exception as exc:  # noqa: BLE001
                result_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_simple(result_queue, self._on_review_done)

    def _on_review_done(self, status, payload):
        self.busy = False
        self.options_btn.config(state="normal")
        self.review_btn.config(state="normal")
        if status == "error":
            self.status_var.set("생성 실패")
            messagebox.showerror("생성 실패", payload)
            return
        self.last_data = payload
        assembled = markdown_utils.assemble_markdown(self.title_value, payload["markdown_body"])
        self.preview_text.delete("1.0", "end")
        self.preview_text.insert("1.0", assembled)
        self.status_var.set("월간 회고 생성 완료")

    def _upload(self):
        if self.uploading:
            return
        if not self.last_data:
            messagebox.showwarning("안내", "먼저 월간 회고를 생성해주세요.")
            return
        blog_name = self.config_data.get("tistory_blog_name")
        if not blog_name:
            messagebox.showwarning("안내", "설정에서 티스토리 블로그 이름을 먼저 등록해주세요.")
            return

        html_content = markdown_utils.markdown_to_html(self.last_data["markdown_body"])
        tags = self.last_data.get("tags", [])

        self.uploading = True
        self.upload_btn.config(state="disabled")
        if not messagebox.askyesno(
            "업로드 확인",
            f"'{blog_name}.tistory.com'에 아래 제목으로 게시할까요? (기본값: 비공개)\n\n{self.title_value}",
        ):
            self.uploading = False
            self.upload_btn.config(state="normal")
            return

        self.status_var.set("업로드 중...")
        result_queue: "queue.Queue" = queue.Queue()

        def worker():
            try:
                result = tistory_browser.post_to_tistory(
                    blog_name=blog_name,
                    title=self.title_value,
                    html_content=html_content,
                    tags=tags,
                    visibility_label="비공개",
                    on_status=lambda msg: result_queue.put(("status", msg)),
                    should_cancel=lambda: False,
                    thumbnail_path=self.config_data.get("thumbnail_path", ""),
                    category=self.config_data.get("tistory_category", ""),
                )
                result_queue.put(("done", result))
            except Exception as exc:  # noqa: BLE001
                result_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll_upload(result_queue)

    def _on_upload_done(self, status, payload):
        self.uploading = False
        self.upload_btn.config(state="normal")
        if status == "error":
            self.status_var.set("업로드 실패")
            messagebox.showerror("실패", payload)
            return
        url = payload.get("url")
        self.status_var.set(f"업로드 완료: {url}")
        messagebox.showinfo("완료", f"게시되었습니다.\n{url}")

    # ---------- 폴링 ----------
    def _poll_simple(self, result_queue: "queue.Queue", on_done):
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll_simple(result_queue, on_done))
            return
        on_done(kind, payload)

    def _poll_upload(self, result_queue: "queue.Queue"):
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll_upload(result_queue))
            return
        if kind == "status":
            self.status_var.set(payload)
            self.after(150, lambda: self._poll_upload(result_queue))
            return
        self._on_upload_done(kind, payload)
