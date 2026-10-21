// 画面イメージ用の共通動作(AIは呼ばない)
// ・.chips / .cards 内のボタンを選択状態にする(data-multi="true" なら複数選択)
// ・#go を押すと、用意してあるサンプル結果(#result)を表示する
// ・[data-act="print"] で印刷、[data-act="copy"] で結果の文章をコピー
document.addEventListener("click", e => {
  const opt = e.target.closest(".chip, .card");
  if (opt) {
    const group = opt.parentElement;
    if (group.dataset.multi !== "true") {
      group.querySelectorAll("[aria-pressed]").forEach(b => b.setAttribute("aria-pressed", "false"));
      opt.setAttribute("aria-pressed", "true");
    } else {
      opt.setAttribute("aria-pressed", opt.getAttribute("aria-pressed") === "true" ? "false" : "true");
    }
    return;
  }
  if (e.target.closest("#go")) {
    const r = document.getElementById("result");
    r.classList.add("show");
    r.scrollIntoView({behavior: "smooth", block: "start"});
    return;
  }
  const act = e.target.closest("[data-act]");
  if (!act) return;
  if (act.dataset.act === "print") window.print();
  if (act.dataset.act === "copy") {
    const text = document.querySelector("#result .paper").innerText;
    navigator.clipboard?.writeText(text).then(() => {
      const label = act.querySelector("span");
      const old = label.textContent;
      label.textContent = "コピーしました";
      setTimeout(() => label.textContent = old, 1500);
    }).catch(() => {});
  }
  if (act.dataset.act === "mock") alert("画面イメージのため、この機能はまだ動きません。");
});
