"use strict";
/* Progressive enhancement: replaces native <select> popups with a styled
   dropdown. The native select stays in the DOM as the source of truth —
   app.js keeps reading .value and listening to "change" untouched. */
(() => {
  const closeAll = () => document.querySelectorAll(".sel-shell.open").forEach(s => s._close());

  const enhance = (sel) => {
    if (sel.dataset.enhanced) return;
    sel.dataset.enhanced = "1";
    sel.classList.add("sel-native");

    const shell = document.createElement("div");
    shell.className = "sel-shell";
    sel.insertAdjacentElement("afterend", shell);

    const btn = document.createElement("button");
    btn.type = "button";
    btn.className = "sel-btn";
    const label = document.createElement("span");
    label.className = "sel-label";
    btn.appendChild(label);

    const menu = document.createElement("div");
    menu.className = "sel-menu";
    menu.hidden = true;
    shell.append(btn, menu);

    const rebuild = () => {
      menu.replaceChildren();
      [...sel.options].forEach((opt) => {
        const item = document.createElement("button");
        item.type = "button";
        item.className = "sel-opt" + (opt.value === sel.value ? " active" : "");
        item.textContent = opt.textContent;
        item.disabled = opt.disabled;
        item.addEventListener("click", () => {
          if (sel.value !== opt.value) {
            sel.value = opt.value;
            sel.dispatchEvent(new Event("change", { bubbles: true }));
          }
          close();
          sync();
        });
        menu.appendChild(item);
      });
    };
    const sync = () => {
      label.textContent = sel.selectedOptions[0]?.textContent ?? "";
      btn.disabled = sel.disabled;
      if (!menu.hidden) [...menu.children].forEach((item, i) => item.classList.toggle("active", sel.options[i]?.value === sel.value));
    };
    const open = () => { closeAll(); rebuild(); menu.hidden = false; shell.classList.add("open"); };
    const close = () => { menu.hidden = true; shell.classList.remove("open"); };
    shell._close = close;

    btn.addEventListener("click", (e) => { e.stopPropagation(); e.preventDefault(); menu.hidden ? open() : close(); });
    btn.addEventListener("keydown", (e) => {
      if (e.key === "Escape") { close(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      e.preventDefault();
      const next = Math.max(0, Math.min(sel.options.length - 1, sel.selectedIndex + (e.key === "ArrowDown" ? 1 : -1)));
      if (next !== sel.selectedIndex) {
        sel.selectedIndex = next;
        sel.dispatchEvent(new Event("change", { bubbles: true }));
        sync();
        if (!menu.hidden) rebuild();
      }
    });
    menu.addEventListener("click", (e) => e.stopPropagation());

    // options rebuilt via innerHTML / disabled toggled by app.js
    new MutationObserver(() => { if (!menu.hidden) rebuild(); sync(); }).observe(sel, { childList: true, attributes: true, subtree: true });
    // programmatic .value writes emit no event — cheap periodic sync
    setInterval(sync, 500);
    sync();
  };

  document.addEventListener("click", closeAll);
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") closeAll(); });

  const scan = (root) => { if (root.querySelectorAll) root.querySelectorAll("select").forEach(enhance); };
  scan(document);
  new MutationObserver((muts) => muts.forEach((m) => m.addedNodes.forEach((n) => {
    if (n.nodeType !== 1) return;
    if (n.tagName === "SELECT") enhance(n); else scan(n);
  }))).observe(document.body, { childList: true, subtree: true });
})();
