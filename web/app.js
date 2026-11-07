"use strict";

const REPO = "khs324630-cmyk/Master";
const KEY_STORE = "market-alert-vapid";
const RATING_KO = {
  "extreme fear": "극단적 공포",
  fear: "공포",
  neutral: "중립",
  greed: "탐욕",
  "extreme greed": "극단적 탐욕",
};

const $ = (id) => document.getElementById(id);
const fmt = (n, d = 2) => n.toLocaleString("en-US", { minimumFractionDigits: d, maximumFractionDigits: d });

// ------------------------------------------------------------ 대시보드

function sparkline(el, points, { threshold, color } = {}) {
  if (!points || points.length < 2) {
    el.innerHTML = "";
    return;
  }
  const vals = points.map((p) => p.v);
  let min = Math.min(...vals);
  let max = Math.max(...vals);
  if (threshold != null) {
    min = Math.min(min, threshold);
    max = Math.max(max, threshold);
  }
  const pad = (max - min) * 0.08 || 1;
  min -= pad;
  max += pad;
  const W = 300;
  const H = 56;
  const x = (i) => (i / (points.length - 1)) * W;
  const y = (v) => H - ((v - min) / (max - min)) * H;
  const d = points.map((p, i) => `${i ? "L" : "M"}${x(i).toFixed(1)},${y(p.v).toFixed(1)}`).join("");
  const last = points[points.length - 1];
  const th =
    threshold != null
      ? `<line x1="0" x2="${W}" y1="${y(threshold)}" y2="${y(threshold)}" stroke="var(--down)" stroke-dasharray="3 3" stroke-width="1" vector-effect="non-scaling-stroke" opacity="0.7"/>`
      : "";
  el.innerHTML = `<svg viewBox="0 0 ${W} ${H}" preserveAspectRatio="none" role="img" aria-label="최근 ${points.length}일 추이">
    ${th}
    <path d="${d}" fill="none" stroke="${color || "var(--accent)"}" stroke-width="2" vector-effect="non-scaling-stroke" stroke-linejoin="round"/>
    <circle cx="${x(points.length - 1)}" cy="${y(last.v)}" r="3" fill="${color || "var(--accent)"}"/>
  </svg>`;
}

function render(data) {
  const t = data.thresholds || { drop: -5, fng: 20 };
  const updated = new Date(data.updated_at);
  $("updated").textContent = `업데이트 ${updated.toLocaleString("ko-KR", {
    month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit",
  })}`;

  // S&P 500
  $("sp-rule").textContent = `${t.drop}% 이하 알림`;
  const sp = data.sp500;
  if (sp) {
    const down = sp.pct < 0;
    $("sp-price").textContent = fmt(sp.price);
    $("sp-pct").textContent = `${sp.pct >= 0 ? "+" : ""}${sp.pct.toFixed(2)}%`;
    $("sp-pct").className = `delta ${down ? "down" : "up"}`;
    $("sp-sub").textContent = `전일 종가 ${fmt(sp.prev)} · ${sp.session} 기준`;
    $("sp-rule").classList.toggle("hit", sp.pct <= t.drop);
    sparkline($("sp-spark"), sp.history, { color: down ? "var(--down)" : "var(--up)" });
  } else {
    $("sp-sub").innerHTML = `<span class="err">데이터를 가져오지 못했습니다.</span>`;
  }

  // Fear & Greed
  $("fg-rule").textContent = `${t.fng} 이하 알림`;
  const fg = data.fng;
  if (fg) {
    $("fg-score").textContent = Math.round(fg.score);
    $("fg-rating").textContent = RATING_KO[fg.rating] || fg.rating;
    const tone = fg.score <= 45 ? "var(--fear)" : fg.score >= 55 ? "var(--greed)" : "var(--neutral)";
    $("fg-rating").style.color = tone;
    $("fg-mark").style.left = `${Math.max(0, Math.min(100, fg.score))}%`;
    $("fg-rule").classList.toggle("hit", fg.score <= t.fng);
    sparkline($("fg-spark"), fg.history, { threshold: t.fng, color: tone });
  } else {
    $("fg-rating").innerHTML = `<span class="err">데이터를 가져오지 못했습니다.</span>`;
  }

  // 최근 알림
  const log = (data.alerts || []).slice().reverse();
  if (log.length) {
    $("log").innerHTML = log
      .map((a) => `<li>${escapeHtml(a.title)}<time>${new Date(a.t).toLocaleString("ko-KR")}</time></li>`)
      .join("");
  }
}

function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
}

async function loadData() {
  try {
    const res = await fetch(`data.json?t=${Date.now()}`, { cache: "no-store" });
    if (!res.ok) throw new Error(res.status);
    render(await res.json());
  } catch (e) {
    $("updated").textContent = "아직 데이터가 없습니다. GitHub Actions가 처음 실행되면 표시됩니다.";
  }
}

// ------------------------------------------------------------ 웹 푸시

const b64url = {
  encode(buf) {
    let s = "";
    for (const b of new Uint8Array(buf)) s += String.fromCharCode(b);
    return btoa(s).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
  },
  decode(str) {
    const s = atob(str.replace(/-/g, "+").replace(/_/g, "/") + "===".slice((str.length + 3) % 4));
    return Uint8Array.from(s, (c) => c.charCodeAt(0));
  },
};

function storage(action, value) {
  try {
    if (action === "get") return JSON.parse(localStorage.getItem(KEY_STORE) || "null");
    if (action === "set") localStorage.setItem(KEY_STORE, JSON.stringify(value));
    if (action === "del") localStorage.removeItem(KEY_STORE);
  } catch {
    return null;
  }
  return null;
}

// 이 기기 전용 VAPID 키 쌍. 개인키는 GitHub Secret(PUSH_CONFIG)에만 들어갑니다.
async function getKeys() {
  const saved = storage("get");
  if (saved && saved.d && saved.pub) return saved;
  const pair = await crypto.subtle.generateKey({ name: "ECDSA", namedCurve: "P-256" }, true, ["sign"]);
  const pub = b64url.encode(await crypto.subtle.exportKey("raw", pair.publicKey));
  const { d } = await crypto.subtle.exportKey("jwk", pair.privateKey);
  const keys = { d, pub };
  storage("set", keys);
  return keys;
}

const isIOS = () => /iphone|ipad|ipod/i.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
const isStandalone = () => window.matchMedia("(display-mode: standalone)").matches || navigator.standalone === true;
const pushSupported = () => "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;

function show(tplId) {
  const area = $("push-area");
  area.innerHTML = "";
  area.appendChild($(tplId).content.cloneNode(true));
}

function message(html) {
  $("push-area").innerHTML = `<p>${html}</p>`;
}

async function renderPush() {
  if (!pushSupported()) {
    if (isIOS() && !isStandalone()) return show("tpl-install");
    return message("이 브라우저는 웹 푸시를 지원하지 않습니다. iOS 16.4 이상에서 홈 화면에 추가한 앱으로 열어주세요.");
  }
  if (isIOS() && !isStandalone()) return show("tpl-install");
  if (Notification.permission === "denied") {
    return message("알림이 차단되어 있습니다. 설정 → 알림 → 마켓 알림에서 허용해 주세요.");
  }

  const reg = await navigator.serviceWorker.ready;
  const sub = await reg.pushManager.getSubscription();
  const keys = storage("get");
  if (!sub || !keys) {
    show("tpl-off");
    $("btn-enable").onclick = enablePush;
    return;
  }

  show("tpl-on");
  const config = JSON.stringify({ subscription: sub.toJSON(), vapid_private_key: keys.d });
  $("cfg").value = config;
  $("secret-link").href = `https://github.com/${REPO}/settings/secrets/actions/new`;
  $("btn-copy").onclick = async () => {
    try {
      await navigator.clipboard.writeText(config);
    } catch {
      $("cfg-details").open = true;
      $("cfg").select();
      document.execCommand("copy");
    }
    $("btn-copy").textContent = "복사됨 ✓";
    setTimeout(() => ($("btn-copy").textContent = "연결 코드 복사"), 2000);
  };
  $("btn-preview").onclick = () =>
    reg.showNotification("알림 미리보기", {
      body: "이 기기에서 알림이 이렇게 표시됩니다.",
      icon: "icons/icon-192.png",
    });
  $("btn-reset").onclick = async () => {
    if (!confirm("새 연결 코드를 만들면 GitHub의 PUSH_CONFIG도 새 코드로 바꿔야 합니다. 계속할까요?")) return;
    await sub.unsubscribe();
    storage("del");
    renderPush();
  };
}

async function enablePush() {
  const btn = $("btn-enable");
  btn.disabled = true;
  btn.textContent = "설정 중…";
  try {
    const perm = await Notification.requestPermission();
    if (perm !== "granted") throw new Error("알림 권한이 허용되지 않았습니다.");
    const reg = await navigator.serviceWorker.ready;
    const keys = await getKeys();
    const old = await reg.pushManager.getSubscription();
    if (old) await old.unsubscribe();
    await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: b64url.decode(keys.pub),
    });
    await renderPush();
    const det = $("cfg-details");
    if (det) det.open = true;
  } catch (e) {
    btn.disabled = false;
    btn.textContent = "알림 켜기";
    alert(`알림을 켜지 못했습니다: ${e.message || e}`);
  }
}

// ------------------------------------------------------------ 시작

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("sw.js").catch(() => {});
}
loadData();
renderPush().catch((e) => message(`알림 상태를 확인하지 못했습니다: ${escapeHtml(e.message || e)}`));
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") loadData();
});
