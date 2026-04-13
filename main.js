document.getElementById("review-form")?.addEventListener("submit", function () {
  const btn = document.getElementById("submit-btn");
  const loading = document.getElementById("loading");
  const form = document.getElementById("review-form");

  btn.disabled = true;
  btn.textContent = "분석 중...";
  form.style.display = "none";
  loading.style.display = "block";
});
