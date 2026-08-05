"""처음 이 앱을 쓰는 사람(나 포함, 또는 앱을 전달받은 다른 사람)을 위한 단계별 초기 설정 마법사.

이 세션에서 실제로 겪었던 문제들을 반영해서 안내 문구를 넣었다:
- Gemini 무료 등급은 모델별로 하루 요청 한도가 있고(예: 20회), 모델에 따라 다르다.
- 특정 모델(gemini-2.5-flash 등)은 신규 사용자에게 더 이상 발급되지 않을 수 있다
  -> "-latest" 별칭을 쓰면 항상 살아있는 모델을 자동으로 가리켜서 안전하다.
- 티스토리 Open API는 종료됐고 로그인도 카카오계정 전용이라, 브라우저 자동화 +
  사용자 본인이 직접 로그인하는 방식으로만 동작한다. 비밀번호는 앱이 절대 다루지 않는다.
- 카테고리는 티스토리에 미리 만들어둔 이름과 "정확히" 같아야 자동 선택된다.
"""
import queue
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import ai_generator
import storage
import tistory_browser


class SetupWizard(tk.Toplevel):
    STEP_TITLES = [
        "환영합니다",
        "① Gemini API 키",
        "② 캠프 정보",
        "③ 티스토리 로그인",
        "④ 선택 사항",
        "완료",
    ]

    def __init__(self, parent, config_data: dict, fit_geometry, on_finish=None):
        super().__init__(parent)
        self.title("초기 설정 도우미")
        fit_geometry(self, 680, 620, min_w=560, min_h=520)
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        self.config_data = dict(config_data)
        self.on_finish = on_finish
        self.step = 0

        self.step_label_var = tk.StringVar()
        header = ttk.Frame(self)
        header.pack(fill="x", padx=16, pady=(14, 6))
        ttk.Label(header, textvariable=self.step_label_var, font=("Consolas", 13, "bold")).pack(
            anchor="w"
        )

        self.body = ttk.Frame(self)
        self.body.pack(fill="both", expand=True, padx=16, pady=6)

        nav = ttk.Frame(self)
        nav.pack(fill="x", padx=16, pady=(6, 14))
        self.back_btn = ttk.Button(nav, text="< 이전", command=self._go_back)
        self.back_btn.pack(side="left")
        self.next_btn = ttk.Button(nav, text="다음 >", command=self._go_next)
        self.next_btn.pack(side="right")
        ttk.Button(nav, text="나중에 하기", command=self.destroy).pack(side="right", padx=8)

        self._render_step()

    # ---------- 네비게이션 ----------
    def _go_next(self):
        if self.step < len(self.STEP_TITLES) - 1:
            self.step += 1
            self._render_step()

    def _go_back(self):
        if self.step > 0:
            self.step -= 1
            self._render_step()

    def _render_step(self):
        for child in self.body.winfo_children():
            child.destroy()
        self.step_label_var.set(
            f"{self.step + 1} / {len(self.STEP_TITLES)}  —  {self.STEP_TITLES[self.step]}"
        )
        self.back_btn.config(state="normal" if self.step > 0 else "disabled")
        self.next_btn.config(text="완료" if self.step == len(self.STEP_TITLES) - 1 else "다음 >")
        if self.step == len(self.STEP_TITLES) - 1:
            self.next_btn.config(command=self._finish)
        else:
            self.next_btn.config(command=self._go_next)

        builders = [
            self._build_intro,
            self._build_gemini,
            self._build_camp,
            self._build_tistory,
            self._build_optional,
            self._build_done,
        ]
        builders[self.step]()

    # ---------- 0. 환영 ----------
    def _build_intro(self):
        ttk.Label(
            self.body,
            text=(
                "플레이데이터 주간회고(WIL) 자동화 앱에 오신 걸 환영합니다.\n\n"
                "이 마법사는 5단계로 진행됩니다:\n"
                "  ① Gemini API 키 (AI 회고 생성용)\n"
                "  ② 캠프 정보 (기수, 시작일 — 몇 회차인지 자동 계산에 씁니다)\n"
                "  ③ 티스토리 로그인 (본인 블로그에 자동 업로드하려면 필요)\n"
                "  ④ 선택 사항 (대표이미지, 카테고리)\n\n"
                "이 앱을 다른 사람에게 전달받았거나, 새 컴퓨터에서 처음 켰다면\n"
                "'설정 > 초기 설정 도우미' 메뉴로 언제든 다시 열 수 있습니다.\n\n"
                "모든 값은 이 컴퓨터에만 저장되고(config.json), 어디로도 전송되지 않습니다."
            ),
            wraplength=560, justify="left",
        ).pack(anchor="w")

    # ---------- 1. Gemini ----------
    def _build_gemini(self):
        ttk.Label(
            self.body,
            text=(
                "1) https://aistudio.google.com/apikey 에서 Google 계정으로 무료 발급받으세요.\n"
                "   (신용카드 필요 없음, Claude와는 무관한 별도 서비스입니다)\n"
                "2) 아래에 붙여넣고 '키 테스트'로 실제로 동작하는지 확인하세요."
            ),
            wraplength=560, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self.body, text="API 키").pack(anchor="w")
        self.gemini_key_var = tk.StringVar(value=self.config_data.get("gemini_api_key", ""))
        ttk.Entry(self.body, textvariable=self.gemini_key_var, width=60, show="*").pack(
            anchor="w", pady=(2, 10)
        )

        ttk.Label(self.body, text="모델").pack(anchor="w")
        self.gemini_model_var = tk.StringVar(
            value=self.config_data.get("gemini_model", "gemini-flash-lite-latest")
        )
        ttk.Entry(self.body, textvariable=self.gemini_model_var, width=40).pack(anchor="w", pady=2)
        ttk.Label(
            self.body,
            text=(
                "기본값 그대로 두는 걸 추천합니다. '-latest' 별칭은 특정 모델이 없어지거나\n"
                "신규 발급이 막혀도 자동으로 살아있는 최신 모델을 가리켜서 안전합니다.\n"
                "무료 등급은 모델마다 하루 요청 한도가 있어서(수십 회 수준), 'flash-lite'\n"
                "계열이 일반 'flash'보다 한도가 넉넉한 편입니다."
            ),
            foreground="gray", justify="left", wraplength=560,
        ).pack(anchor="w", pady=(0, 10))

        ttk.Button(self.body, text="키 테스트", command=self._test_gemini_key).pack(anchor="w")
        self.gemini_test_status = tk.StringVar()
        ttk.Label(self.body, textvariable=self.gemini_test_status, foreground="gray").pack(
            anchor="w", pady=4
        )

    def _test_gemini_key(self):
        key = self.gemini_key_var.get().strip()
        model = self.gemini_model_var.get().strip() or "gemini-flash-lite-latest"
        if not key:
            messagebox.showwarning("안내", "API 키를 먼저 입력해주세요.")
            return
        self.gemini_test_status.set("테스트 중...")
        result_queue: "queue.Queue" = queue.Queue()

        def worker():
            try:
                from google import genai

                client = genai.Client(api_key=key)
                resp = client.models.generate_content(model=model, contents="ping")
                result_queue.put(("ok", (resp.text or "").strip()[:40]))
            except Exception as exc:  # noqa: BLE001
                result_queue.put(("error", str(exc)))

        threading.Thread(target=worker, daemon=True).start()
        self._poll(result_queue, self._on_gemini_test_done)

    def _on_gemini_test_done(self, status, payload):
        if status == "ok":
            self.gemini_test_status.set(f"✅ 정상 동작 확인 (응답: {payload})")
        else:
            hint = ""
            if "RESOURCE_EXHAUSTED" in str(payload) or "429" in str(payload):
                hint = "\n→ 오늘 무료 한도를 다 썼을 수 있습니다. 내일 다시 시도하거나 모델을 'gemini-flash-lite-latest'로 바꿔보세요."
            elif "NOT_FOUND" in str(payload) or "404" in str(payload):
                hint = "\n→ 이 모델이 더 이상 제공되지 않는 것 같습니다. 모델명을 'gemini-flash-lite-latest'로 바꿔보세요."
            self.gemini_test_status.set(f"❌ 실패: {str(payload)[:150]}{hint}")

    # ---------- 2. 캠프 정보 ----------
    def _build_camp(self):
        ttk.Label(
            self.body,
            text="제목이 '[캠프명] {기수}기 {회차}회차 회고' 형식으로 자동 조립되는 데 쓰입니다.",
            wraplength=560, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self.body, text="캠프명").pack(anchor="w")
        self.camp_name_var = tk.StringVar(
            value=self.config_data.get("camp_name", "SK 네트웍스 Family AI 캠프")
        )
        ttk.Entry(self.body, textvariable=self.camp_name_var, width=50).pack(anchor="w", pady=(2, 8))

        ttk.Label(self.body, text="기수").pack(anchor="w")
        self.camp_gisu_var = tk.StringVar(value=self.config_data.get("camp_gisu", "35"))
        ttk.Entry(self.body, textvariable=self.camp_gisu_var, width=20).pack(anchor="w", pady=(2, 8))

        ttk.Label(self.body, text="캠프 시작일 (YYYY-MM-DD)").pack(anchor="w")
        self.camp_start_var = tk.StringVar(
            value=self.config_data.get("camp_start_date", "2026-07-07")
        )
        ttk.Entry(self.body, textvariable=self.camp_start_var, width=20).pack(anchor="w", pady=(2, 4))
        ttk.Label(
            self.body,
            text="이 날짜가 속한 주(월~일)가 1회차가 됩니다. 이후 회차는 자동 계산됩니다.",
            foreground="gray",
        ).pack(anchor="w")

    # ---------- 3. 티스토리 ----------
    def _build_tistory(self):
        ttk.Label(
            self.body,
            text=(
                "티스토리 Open API는 종료됐고 로그인도 카카오계정 전용이라, 이 앱은 실제\n"
                "브라우저 창을 띄워 화면을 직접 조작하는 방식으로 동작합니다.\n"
                "비밀번호는 앱이 절대 다루지 않습니다 — 아래 버튼을 누르면 뜨는 브라우저\n"
                "창에서 본인이 직접 카카오 로그인을 완료하시면 됩니다."
            ),
            wraplength=560, justify="left",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self.body, text="블로그 이름").pack(anchor="w")
        self.blog_name_var = tk.StringVar(value=self.config_data.get("tistory_blog_name", ""))
        ttk.Entry(self.body, textvariable=self.blog_name_var, width=40).pack(anchor="w", pady=2)
        ttk.Label(
            self.body, text="예: myid.tistory.com 이면 'myid'만 입력", foreground="gray"
        ).pack(anchor="w", pady=(0, 10))

        ttk.Button(self.body, text="지금 로그인하기", command=self._start_tistory_login).pack(
            anchor="w"
        )
        self.tistory_login_status = tk.StringVar()
        ttk.Label(self.body, textvariable=self.tistory_login_status, foreground="gray").pack(
            anchor="w", pady=4
        )
        ttk.Label(
            self.body,
            text="건너뛰어도 됩니다 — 나중에 '설정 > API / 티스토리 설정'에서 언제든 로그인할 수 있습니다.",
            foreground="gray",
        ).pack(anchor="w", pady=(6, 0))

    def _start_tistory_login(self):
        blog_name = self.blog_name_var.get().strip()
        if not blog_name:
            messagebox.showwarning("안내", "블로그 이름을 먼저 입력해주세요.")
            return
        self.tistory_login_status.set("브라우저 창에서 로그인해주세요...")
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
            self.tistory_login_status.set(payload)
            self.after(150, lambda: self._poll_login(result_queue))
            return
        if kind == "error":
            self.tistory_login_status.set(f"❌ 실패: {payload}")
            return
        self.tistory_login_status.set("✅ 로그인 완료" if payload else "❌ 로그인 대기 시간 초과")

    # ---------- 4. 선택 사항 ----------
    def _build_optional(self):
        ttk.Label(
            self.body,
            text="둘 다 비워둬도 앱은 정상 동작합니다. 나중에 설정에서 바꿀 수 있습니다.",
            foreground="gray",
        ).pack(anchor="w", pady=(0, 10))

        ttk.Label(self.body, text="대표이미지 (매 글에 자동으로 들어갈 고정 썸네일)").pack(anchor="w")
        row1 = ttk.Frame(self.body)
        row1.pack(fill="x", pady=(2, 10))
        self.thumbnail_path_var = tk.StringVar(value=self.config_data.get("thumbnail_path", ""))
        ttk.Entry(row1, textvariable=self.thumbnail_path_var, width=45).pack(side="left")
        ttk.Button(row1, text="파일 선택", command=self._choose_thumbnail).pack(side="left", padx=6)

        ttk.Label(self.body, text="티스토리 카테고리").pack(anchor="w")
        self.category_var = tk.StringVar(value=self.config_data.get("tistory_category", ""))
        ttk.Entry(self.body, textvariable=self.category_var, width=30).pack(anchor="w", pady=(2, 4))
        ttk.Label(
            self.body,
            text="⚠ 티스토리에 이미 만들어둔 카테고리 이름과 '정확히' 같아야 자동으로 선택됩니다\n"
            "(다르면 조용히 무시되고 카테고리 없음으로 올라갑니다).",
            foreground="gray", justify="left",
        ).pack(anchor="w")

    def _choose_thumbnail(self):
        path = filedialog.askopenfilename(
            filetypes=[("이미지", "*.png *.jpg *.jpeg *.gif *.webp"), ("모든 파일", "*.*")]
        )
        if path:
            self.thumbnail_path_var.set(path)

    # ---------- 5. 완료 ----------
    def _build_done(self):
        lines = [
            f"캠프: {self.camp_name_var.get()} {self.camp_gisu_var.get()}기 (시작일 {self.camp_start_var.get()})",
            f"Gemini 모델: {self.gemini_model_var.get()}",
            f"API 키: {'입력됨' if self.gemini_key_var.get().strip() else '(비어있음)'}",
            f"티스토리 블로그: {self.blog_name_var.get() or '(비어있음)'}",
            f"카테고리: {self.category_var.get() or '(없음)'}",
            f"대표이미지: {self.thumbnail_path_var.get() or '(없음)'}",
        ]
        ttk.Label(
            self.body,
            text="아래 내용으로 저장됩니다. '완료'를 누르면 바로 앱을 쓸 수 있습니다.\n",
            wraplength=560, justify="left",
        ).pack(anchor="w")
        for line in lines:
            ttk.Label(self.body, text=f"· {line}", wraplength=560, justify="left").pack(
                anchor="w", pady=2
            )

    def _finish(self):
        self.config_data.update(
            {
                "gemini_api_key": self.gemini_key_var.get().strip(),
                "gemini_model": self.gemini_model_var.get().strip() or "gemini-flash-lite-latest",
                "camp_name": self.camp_name_var.get().strip() or "SK 네트웍스 Family AI 캠프",
                "camp_gisu": self.camp_gisu_var.get().strip() or "35",
                "camp_start_date": self.camp_start_var.get().strip() or "2026-07-07",
                "tistory_blog_name": self.blog_name_var.get().strip(),
                "thumbnail_path": self.thumbnail_path_var.get().strip(),
                "tistory_category": self.category_var.get().strip(),
            }
        )
        storage.save_config(self.config_data)
        if self.on_finish:
            self.on_finish(self.config_data)
        self.destroy()

    # ---------- 공용 폴링 ----------
    def _poll(self, result_queue: "queue.Queue", on_done):
        try:
            kind, payload = result_queue.get_nowait()
        except queue.Empty:
            self.after(150, lambda: self._poll(result_queue, on_done))
            return
        on_done(kind, payload)
