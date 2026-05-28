/* ================================================================
   main.js — PRism 웹 UI 공통 스크립트
   ================================================================ */

/* ── 헬퍼: 섹션 표시/숨김 ───────────────────────────────────────── */

function showSection(id) {
  document.getElementById(id)?.classList.remove("hidden");
}

function hideSection(id) {
  document.getElementById(id)?.classList.add("hidden");
}

/* ── 헬퍼: 버튼 로딩 상태 ──────────────────────────────────────── */

function setLoading(btn, isLoading, loadingText = "처리 중...") {
  if (!btn) return;
  btn.disabled = isLoading;
  if (isLoading) {
    btn.dataset.originalText = btn.textContent;
    btn.textContent = loadingText;
  } else {
    btn.textContent = btn.dataset.originalText ?? btn.textContent;
  }
}

/* ── 헬퍼: 에러 표시 ─────────────────────────────────────────────── */

function showError(msg) {
  const box = document.getElementById("error-box");
  if (!box) return;
  box.textContent = "오류: " + msg;
  box.classList.remove("hidden");
  box.scrollIntoView({ behavior: "smooth", block: "center" });
}

function hideError() {
  document.getElementById("error-box")?.classList.add("hidden");
}

/* ── 헬퍼: JSON API 호출 ─────────────────────────────────────────── */

async function apiFetch(path, body) {
  const res = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok || data.error) throw new Error(data.error ?? `HTTP ${res.status}`);
  return data;
}

/* ── 헬퍼: 수정 계획 섹션 채우기 ─────────────────────────────────── */

function fillFixPlan(data) {
  const summaryEl = document.getElementById("fix-plan-summary");
  const filesEl   = document.getElementById("fix-plan-files");
  if (summaryEl) summaryEl.textContent = data.summary;
  if (filesEl) {
    filesEl.innerHTML = data.affected_files.length
      ? data.affected_files.map(f => `<div class="file-item">📄 ${f}</div>`).join("")
      : "<p class='hint'>수정할 파일이 없습니다.</p>";
  }
}

/* ================================================================
   index.html — 탭 전환
   ================================================================ */

document.querySelectorAll(".tab-btn").forEach(btn => {
  btn.addEventListener("click", () => {
    const target = btn.dataset.tab;

    // 탭 버튼 활성화 상태 전환
    document.querySelectorAll(".tab-btn").forEach(b => {
      b.classList.remove("active");
      b.setAttribute("aria-selected", "false");
    });
    btn.classList.add("active");
    btn.setAttribute("aria-selected", "true");

    // 탭 패널 표시 전환
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.add("hidden"));
    const panel = document.getElementById("tab-" + target);
    if (panel) {
      panel.classList.remove("hidden");
      // 탭 전환 시 패널 내부 스피너 항상 숨김 상태로 초기화
      panel.querySelectorAll(".loading").forEach(el => { el.style.display = "none"; });
    }
  });
});

/* ── index.html — 레포 리뷰 폼 ────────────────────────────────── */

document.getElementById("review-form")?.addEventListener("submit", function () {
  const btn     = document.getElementById("submit-btn");
  const loading = document.getElementById("loading");
  const form    = this;

  setLoading(btn, true, "분석 중...");
  form.style.display = "none";
  if (loading) loading.style.display = "block";
});

/* ── index.html — PR 리뷰 폼 ──────────────────────────────────── */

document.getElementById("pr-review-form")?.addEventListener("submit", function () {
  const btn  = document.getElementById("pr-submit-btn");
  const form = this;

  setLoading(btn, true, "리뷰 중...");
  form.style.display = "none";
  const prSpinner = document.getElementById("pr-review-loading");
  if (prSpinner) prSpinner.style.display = "block";
});

/* ================================================================
   review_result.html — 리뷰 결과 페이지
   세션이 없는 페이지에서는 이하 코드가 실행되지 않음
   ================================================================ */

const sessionId = document.body.dataset.sessionId;
if (sessionId) initReviewResultPage();

function initReviewResultPage() {
  const btnFix      = document.getElementById("btn-fix");
  const btnReviewOnly = document.getElementById("btn-review-only");
  const btnApprove  = document.getElementById("btn-approve");
  const btnReject   = document.getElementById("btn-reject");
  const btnReplan   = document.getElementById("btn-replan");
  const btnSubmitFb = document.getElementById("btn-submit-feedback");
  const btnCancelFb = document.getElementById("btn-cancel-feedback");

  /* ── 🔧 코드 수정 요청 ─────────────────────────────────────── */
  btnFix?.addEventListener("click", async () => {
    hideError();
    hideSection("action-section");
    showSection("fix-loading");
    try {
      const data = await apiFetch("/api/fix-plan", { session_id: sessionId });
      fillFixPlan(data);
      hideSection("fix-loading");
      showSection("fix-plan-section");
    } catch (err) {
      hideSection("fix-loading");
      showSection("action-section");
      showError(err.message);
    }
  });

  /* ── 📄 리뷰만 볼게요 ──────────────────────────────────────── */
  btnReviewOnly?.addEventListener("click", async () => {
    setLoading(btnReviewOnly, true);
    try {
      await apiFetch("/api/close-session", { session_id: sessionId });
    } finally {
      location.href = "/";
    }
  });

  /* ── ✅ 승인 (PR 생성) ─────────────────────────────────────── */
  btnApprove?.addEventListener("click", async () => {
    hideError();
    hideSection("fix-plan-section");
    showSection("pr-loading");
    try {
      const data = await apiFetch("/api/create-pr", { session_id: sessionId });
      const link = document.getElementById("pr-result-link");
      if (link) link.href = data.pr_url;
      hideSection("pr-loading");
      showSection("pr-result-section");
      document.getElementById("pr-result-section")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      hideSection("pr-loading");
      showSection("fix-plan-section");
      showError(err.message);
    }
  });

  /* ── ❌ 거절 ────────────────────────────────────────────────── */
  btnReject?.addEventListener("click", async () => {
    setLoading(btnReject, true);
    try {
      await apiFetch("/api/close-session", { session_id: sessionId });
    } finally {
      location.href = "/";
    }
  });

  /* ── 🔄 다시 계획해줘 ──────────────────────────────────────── */
  btnReplan?.addEventListener("click", () => {
    const input = document.getElementById("feedback-input");
    if (input) input.value = "";
    showSection("feedback-section");
    document.getElementById("feedback-section")
      ?.scrollIntoView({ behavior: "smooth", block: "start" });
  });

  /* ── 피드백 취소 ───────────────────────────────────────────── */
  btnCancelFb?.addEventListener("click", () => {
    hideSection("feedback-section");
    const input = document.getElementById("feedback-input");
    if (input) input.value = "";
  });

  /* ── 피드백 제출 → 재계획 ─────────────────────────────────── */
  btnSubmitFb?.addEventListener("click", async () => {
    const feedback = document.getElementById("feedback-input")?.value.trim();
    if (!feedback) {
      showError("피드백을 입력해 주세요.");
      return;
    }
    hideError();
    hideSection("feedback-section");
    hideSection("fix-plan-section");
    showSection("fix-loading");
    try {
      const data = await apiFetch("/api/replan", { session_id: sessionId, feedback });
      fillFixPlan(data);
      hideSection("fix-loading");
      showSection("fix-plan-section");
      document.getElementById("fix-plan-section")
        ?.scrollIntoView({ behavior: "smooth", block: "start" });
    } catch (err) {
      hideSection("fix-loading");
      showSection("fix-plan-section");
      showError(err.message);
    }
  });
}
