// Injected into every captured page: draws numbered callout boxes over
// selected elements so the documentation reader knows exactly where to look.
window.__annClear = () => {
  document.querySelectorAll(".__annBox,.__annTag").forEach((e) => e.remove());
};

window.__annStyle = () => {
  if (document.getElementById("__annStyle")) return;
  const st = document.createElement("style");
  st.id = "__annStyle";
  st.textContent = `
  .__annBox{position:absolute;z-index:2147483000;pointer-events:none;box-sizing:border-box;
    border:3px solid #E0630F;border-radius:10px;
    box-shadow:0 0 0 3px rgba(224,99,15,.20), 0 0 0 1px rgba(0,0,0,.06) inset;}
  .__annBox.blue{border-color:#1E6FD9;box-shadow:0 0 0 3px rgba(30,111,217,.20)}
  .__annBox.green{border-color:#0E8A5F;box-shadow:0 0 0 3px rgba(14,138,95,.20)}
  .__annTag{position:absolute;z-index:2147483001;pointer-events:none;
    display:flex;align-items:center;gap:7px;background:#E0630F;color:#fff;
    font:700 16px/1 "Segoe UI",system-ui,sans-serif;padding:7px 14px 7px 7px;
    border-radius:999px;box-shadow:0 3px 10px rgba(0,0,0,.28);white-space:nowrap}
  .__annTag.blue{background:#1E6FD9}
  .__annTag.green{background:#0E8A5F}
  .__annTag i{display:inline-flex;width:24px;height:24px;border-radius:50%;background:#fff;
    color:#E0630F;align-items:center;justify-content:center;font-style:normal;
    font:800 14px/1 "Segoe UI",system-ui,sans-serif}
  .__annTag.blue i{color:#1E6FD9}
  .__annTag.green i{color:#0E8A5F}
  `;
  document.head.appendChild(st);
};

// specs: [{sel, n, label, color, pad, place}]
//   place: "above" (default) | "below" | "inside" | "right"
window.__ann = (specs) => {
  window.__annStyle();
  const docW = document.documentElement.scrollWidth;
  for (const s of specs) {
    const el = document.querySelector(s.sel);
    if (!el) { console.warn("__ann: no match for", s.sel); continue; }
    const r = el.getBoundingClientRect();
    if (r.width === 0 && r.height === 0) { console.warn("__ann: zero-size", s.sel); continue; }
    const pad = s.pad === undefined ? 5 : s.pad;
    const color = s.color || "";
    const top = r.top + window.scrollY - pad;
    const left = r.left + window.scrollX - pad;
    const w = r.width + pad * 2;
    const h = r.height + pad * 2;

    const box = document.createElement("div");
    box.className = "__annBox " + color;
    box.style.cssText = `top:${top}px;left:${left}px;width:${w}px;height:${h}px`;
    document.body.appendChild(box);

    if (!s.label && !s.n) continue;
    const tag = document.createElement("div");
    tag.className = "__annTag " + color;
    tag.innerHTML = `<i>${s.n ?? ""}</i><span></span>`;
    tag.querySelector("span").textContent = s.label || "";
    document.body.appendChild(tag);

    // Number-only badge: a compact disc pinned to the box corner, used where
    // the panel is too narrow for a text tag without covering the UI.
    if (!s.label) {
      const bw = tag.offsetWidth, bh = tag.offsetHeight;
      tag.style.cssText =
        `top:${top - bh / 2 + 4}px;left:${Math.max(2, left - bw / 2 + 4)}px;padding:7px`;
      continue;
    }

    const tw = tag.offsetWidth, th = tag.offsetHeight;
    let ty, tx;
    const place = s.place || (top - th - 6 < window.scrollY + 2 ? "inside" : "above");
    if (place === "below") { ty = top + h + 6; tx = left; }
    else if (place === "inside") { ty = top + 6; tx = left + 6; }
    else if (place === "right") { ty = top + 6; tx = left + w + 8; }
    else { ty = top - th - 6; tx = left; }
    if (tx + tw > docW - 6) tx = docW - tw - 6;
    if (tx < 4) tx = 4;
    tag.style.cssText = `top:${ty}px;left:${tx}px`;
  }
  return true;
};

// Union bounding box of the given selectors plus every callout drawn so far,
// in page coordinates. Used to crop the screenshot down to the region that
// actually matters (a dialog or a side drawer, instead of the dimmed page).
window.__cropBox = (sels) => {
  const rects = [];
  const add = (e) => {
    const r = e.getBoundingClientRect();
    if (r.width > 1 && r.height > 1) {
      rects.push([r.left + scrollX, r.top + scrollY, r.right + scrollX, r.bottom + scrollY]);
    }
  };
  // Use leaf descendants, not the container itself: a side drawer keeps full
  // viewport height even when its content stops a third of the way down.
  const addContent = (el) => {
    const leaves = el.querySelectorAll("*");
    if (!leaves.length) return add(el);
    let any = false;
    leaves.forEach((e) => {
      if (e.children.length) return;
      const cs = getComputedStyle(e);
      if (cs.display === "none" || cs.visibility === "hidden") return;
      any = true;
      add(e);
    });
    if (!any) add(el);
    const r = el.getBoundingClientRect();  // keep the container's own width
    rects.push([r.left + scrollX, r.top + scrollY, r.right + scrollX, r.top + scrollY + 2]);
  };
  (sels || []).forEach((s) => document.querySelectorAll(s).forEach(addContent));
  document.querySelectorAll(".__annBox,.__annTag").forEach(add);
  if (!rects.length) return null;
  return {
    left: Math.min(...rects.map((r) => r[0])),
    top: Math.min(...rects.map((r) => r[1])),
    right: Math.max(...rects.map((r) => r[2])),
    bottom: Math.max(...rects.map((r) => r[3])),
  };
};

// Bottom-most pixel that carries content. Container elements stretch to fill
// the viewport, so only leaf elements (and the callouts) are considered.
window.__contentBottom = () => {
  let max = 0;
  document.querySelectorAll("body *").forEach((e) => {
    if (e.children.length) return;
    const cs = getComputedStyle(e);
    if (cs.display === "none" || cs.visibility === "hidden" || cs.opacity === "0") return;
    if (e.closest('[aria-hidden="true"]')) return;
    const r = e.getBoundingClientRect();
    if (r.width < 2 || r.height < 2) return;
    // Closed drawers are parked off to the side but keep their full height.
    if (r.right < 2 || r.left > innerWidth - 2) return;
    max = Math.max(max, r.bottom + scrollY);
  });
  document.querySelectorAll(".__annBox,.__annTag").forEach((e) => {
    const r = e.getBoundingClientRect();
    max = Math.max(max, r.bottom + scrollY);
  });
  return Math.ceil(max);
};
