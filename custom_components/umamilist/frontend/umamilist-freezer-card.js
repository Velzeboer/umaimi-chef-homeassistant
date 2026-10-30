/*
 * Umaimi Chef freezer card for Home Assistant
 * Shows an Umaimi Chef inventory (a to-do entity of the Umaimi Chef integration) with each item's
 * best-before date: the freeze date plus its category's shelf life, soonest first. Tap an item to
 * check it off, the pencil to rename it, the bin to delete it, and add new items with a quantity and
 * freeze date. Checked-off items are listed most recently checked off first.
 *
 * type: custom:umamilist-freezer-card
 * entity: todo.freezer
 * title: Freezer          # optional
 * day_first: true         # optional, 31-12-2026 (true) vs 12/31/2026 (false)
 * show_checked: true      # optional, false hides checked-off items (shown at the bottom by default)
 * show_add: true          # optional, false hides the add-item form
 * show_edit: true         # optional, false hides the pencil (rename) button
 * show_delete: true       # optional, false hides the bin (delete) button
 * show_checkbox: true     # optional, false hides the check circles (tapping an item still checks it off)
 * show_dividers: false    # optional, true draws a grey line between items
 * show_count: true        # optional, false hides the number of items after the title
 * show_refresh: true      # optional, false hides the refresh button
 * show_category: true     # optional, false hides the category above the notes
 * sort_by_best_before: true # optional, false sorts by freeze date instead
 * row_padding: 8          # optional, space above and below each item (a number means px, e.g. 4)
 * date_size: 0.9em        # optional, size of the best-before date and time left (a number means px, e.g. 13)
 * date_color: black       # optional, one colour for all dates instead of colouring them by age
 * name_size: 1.1em        # optional, size of the item name (a number means px, e.g. 16)
 * name_color: black       # optional, colour of the item name (theme text colour by default)
 */

// Month names for a date typed in the name when adding, e.g. "Worst 5 mei 2026".
const MONTHS = {};
[
  ["jan", "january", "januari", "janv"], ["feb", "february", "februari", "febr"],
  ["mar", "march", "maart", "mrt"], ["apr", "april"], ["may", "mei"],
  ["jun", "june", "juni"], ["jul", "july", "juli"], ["aug", "august", "augustus"],
  ["sep", "sept", "september"], ["oct", "october", "okt", "oktober"],
  ["nov", "november"], ["dec", "december"],
].forEach((aliases, i) => aliases.forEach((a) => (MONTHS[a] = i + 1)));
const MONTH_ALT = Object.keys(MONTHS).sort((a, b) => b.length - a.length).join("|");

const PATTERNS = [
  [/\b(\d{4})[-/.](\d{1,2})[-/.](\d{1,2})\b/, (m) => [+m[1], +m[2], +m[3]]],
  [/\b(\d{1,2})[-/.](\d{1,2})[-/.](\d{4}|\d{2})\b/, (m, df) => {
    const y = +m[3] < 100 ? 2000 + +m[3] : +m[3];
    return df ? [y, +m[2], +m[1], [y, +m[1], +m[2]]] : [y, +m[1], +m[2], [y, +m[2], +m[1]]];
  }],
  [new RegExp(`\\b(\\d{1,2})\\.?\\s+(${MONTH_ALT})\\.?,?\\s+(\\d{4})\\b`, "i"), (m) => [+m[3], MONTHS[m[2].toLowerCase()], +m[1]]],
  [new RegExp(`\\b(${MONTH_ALT})\\.?\\s+(\\d{1,2}),?\\s+(\\d{4})\\b`, "i"), (m) => [+m[3], MONTHS[m[1].toLowerCase()], +m[2]]],
  [new RegExp(`\\b(${MONTH_ALT})\\.?\\s+(\\d{4})\\b`, "i"), (m) => [+m[2], MONTHS[m[1].toLowerCase()], 1]],
  [/\b(\d{1,2})[-/.](\d{4})\b/, (m) => [+m[2], +m[1], 1]],
];

function makeDate(y, m, d) {
  const dt = new Date(y, m - 1, d);
  return dt.getFullYear() === y && dt.getMonth() === m - 1 && dt.getDate() === d ? dt : null;
}

function findDate(text, dayFirst) {
  if (!text) return null;
  for (const [re, fn] of PATTERNS) {
    const m = text.match(re);
    if (!m) continue;
    const [y, mo, d, alt] = fn(m, dayFirst);
    const dt = makeDate(y, mo, d) || (alt ? makeDate(...alt) : null);
    if (dt) return { date: dt, match: m[0] };
  }
  return null;
}

// Shelf life for items without a category, or in one without a shelf life (same as the app).
const DEFAULT_SHELF_LIFE = 12;

// Like Java's plusMonths: 31 Jan + 1 month is 28/29 Feb, not 2/3 March.
function addMonths(date, n) {
  const d = new Date(date.getFullYear(), date.getMonth() + n, 1);
  const last = new Date(d.getFullYear(), d.getMonth() + 1, 0).getDate();
  d.setDate(Math.min(date.getDate(), last));
  return d;
}

const addDays = (date, n) => new Date(date.getFullYear(), date.getMonth(), date.getDate() + n);

// Date plus a number of quarter months, in calendar months where possible (9 of 12 months is
// exactly 9 months later), with the remaining quarters as part of the next month in days.
function addQuarterMonths(date, quarters) {
  const whole = addMonths(date, Math.floor(quarters / 4));
  const rest = quarters % 4;
  if (!rest) return whole;
  const monthDays = Math.round((addMonths(whole, 1) - whole) / 86400000);
  return new Date(whole.getFullYear(), whole.getMonth(), whole.getDate() + Math.round(monthDays * rest / 4));
}

// Time from today to the best-before date, for displays without colour: "3 mo", "1 yr 2 mo",
// "2 wk", "5 d", "today", and once it has passed "1 mo over".
function timeLeft(bestBefore) {
  if (!bestBefore) return "";
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  const over = bestBefore < today;
  const [from, to] = over ? [bestBefore, today] : [today, bestBefore];
  const months = (to.getFullYear() - from.getFullYear()) * 12 + to.getMonth() - from.getMonth()
    - (to.getDate() < from.getDate() ? 1 : 0);
  const days = Math.round((to - from) / 86400000);
  let label;
  if (months >= 12) label = `${Math.floor(months / 12)} yr${months % 12 ? ` ${months % 12} mo` : ""}`;
  else if (months >= 1) label = `${months} mo`;
  else if (days >= 7) label = `${Math.floor(days / 7)} wk`;
  else if (days === 0) return "today";
  else label = `${days} d`;
  return over ? `${label} over` : label;
}

// 0 = green, 1 = yellow, 2 = orange, 3 = red: yellow from half the shelf life, orange from three
// quarters, red once the best-before date is reached. Same as the Umaimi Chef app.
function ageLevel(frozen, months, days) {
  if (!frozen) return 0;
  const now = new Date();
  const today = new Date(now.getFullYear(), now.getMonth(), now.getDate());
  if (days) {
    if (addDays(frozen, days) <= today) return 3;
    if (addDays(frozen, Math.round(days * 0.75)) <= today) return 2;
    if (addDays(frozen, Math.round(days * 0.5)) <= today) return 1;
    return 0;
  }
  if (addMonths(frozen, months) <= today) return 3;
  if (addQuarterMonths(frozen, months * 3) <= today) return 2;
  if (addQuarterMonths(frozen, months * 2) <= today) return 1;
  return 0;
}

const esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) =>
  ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));

const pad = (n) => String(n).padStart(2, "0");
const norm = (s) => String(s ?? "").replace(/\s+/g, " ").trim().toLowerCase();
const isoDate = (s) => { if (!s) return null; const [y, m, d] = s.split("-").map(Number); return new Date(y, m - 1, d); };
const isoString = (date) => `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}`;

class UmamiListFreezerCard extends HTMLElement {
  static getStubConfig(hass) {
    const entity = Object.keys(hass.states).find((e) => hass.states[e].attributes?.umamilist) || "todo.freezer";
    return { entity, title: "Freezer" };
  }

  setConfig(config) {
    if (!config.entity) throw new Error("Please set an entity (todo.…)");
    this._config = { title: "Freezer", day_first: true, show_checked: true, show_add: true,
      show_edit: true, show_delete: true, show_checkbox: true, show_category: true,
      sort_by_best_before: true, show_count: true, show_refresh: true, ...config };
    if (!this.shadowRoot) this._build();
    this.shadowRoot.querySelector("form.add-form").hidden = !this._config.show_add;
    this.shadowRoot.querySelector(".list").classList.toggle("dividers", !!this._config.show_dividers);
    this.shadowRoot.querySelector(".refresh").hidden = !this._config.show_refresh;
    this._setVar("--freezer-date-size", this._config.date_size);
    this._setVar("--freezer-name-size", this._config.name_size);
    this._setVar("--freezer-name-color", this._config.name_color);
    this._setVar("--freezer-row-padding", this._config.row_padding);
    this._renderList();
  }

  // Sizes given as a plain number are in px.
  _setVar(name, value) {
    if (value == null || value === "") this.style.removeProperty(name);
    else this.style.setProperty(name, typeof value === "number" ? `${value}px` : value);
  }

  // The integration puts the whole list in the entity's `items` attribute; Home Assistant hands
  // the card a new state object whenever it changes.
  set hass(hass) {
    this._hass = hass;
    this.shadowRoot?.querySelector("ha-card").classList.toggle("dark", !!hass.themes?.darkMode);
    const st = hass.states[this._config?.entity];
    if (st === this._state) return;
    this._state = st;
    if (!st) this._showError({ message: `Entity ${this._config.entity} not found` });
    else if (!st.attributes.umamilist) this._showError({ message: `${this._config.entity} isn't an Umaimi Chef inventory. Set up the Umaimi Chef integration and use one of its inventories.` });
    else this._showError(null);
    this._renderList();
  }

  get _items() { return this._state?.attributes?.items || []; }

  getCardSize() { return 2 + Math.min(this._items.length, 10); }

  _fmt(date) {
    const d = pad(date.getDate()), m = pad(date.getMonth() + 1), y = date.getFullYear();
    return this._config.day_first ? `${d}-${m}-${y}` : `${m}/${d}/${y}`;
  }

  _build() {
    const root = this.attachShadow({ mode: "open" });
    const today = new Date();
    root.innerHTML = `
      <style>
        ha-card { padding: 12px 12px 8px; }
        .head { display:flex; align-items:center; gap:8px; font-size:1.2em; font-weight:500; padding:4px 4px 10px; }
        .head ha-icon { color: var(--primary-color); }
        .head .title { flex: 1; }
        .head .bblabel { font-size:.65em; font-weight:400; color: var(--secondary-text-color); white-space:nowrap; }
        .hbtn { background:none; border:none; cursor:pointer; padding:4px; color: var(--secondary-text-color);
                border-radius:50%; line-height:0; }
        .hbtn:hover { color: var(--primary-color); }
        .hbtn ha-icon { color: inherit; --mdc-icon-size: 20px; }
        .hbtn.spin ha-icon { animation: spin 1s linear infinite; }
        @keyframes spin { to { transform: rotate(360deg); } }
        form[hidden] { display:none; }
        form { display:flex; gap:6px; margin-bottom:10px; flex-wrap:wrap; }
        input { font: inherit; padding:8px 10px; border-radius:8px; border:1px solid var(--divider-color);
                background: var(--card-background-color); color: var(--primary-text-color); }
        input[name=itemName] { flex: 1 1 140px; min-width: 0; }
        input[name=qty] { flex: 0 1 70px; min-width: 50px; }
        input[name=frozen] { flex: 0 0 auto; }
        button.add { font: inherit; padding:8px 14px; border:none; border-radius:8px; cursor:pointer;
                     background: var(--primary-color); color: var(--text-primary-color, #fff); }
        .row { display:flex; align-items:center; gap:10px; padding: var(--freezer-row-padding, 8px) 6px; border-radius:10px; }
        .row:hover { background: var(--secondary-background-color); }
        .dividers .row { border-radius: 0; }
        .dividers .row:not(:first-child) { border-top: 1px solid var(--divider-color); }
        /* The date lines up with the item name (baseline), not with the middle of the row. */
        .main { flex:1; min-width:0; display:flex; align-items:center; gap:10px; cursor:pointer; align-self: baseline; }
        .main .text { min-width:0; align-self: baseline; }
        .main ha-icon { color: var(--primary-color); flex: 0 0 auto; }
        .name { font-size: var(--freezer-name-size, 1em); color: var(--freezer-name-color, inherit); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .notes { font-size:.8em; color: var(--secondary-text-color); white-space:nowrap; overflow:hidden; text-overflow:ellipsis; }
        .when { align-self: baseline; text-align:right; font-size: var(--freezer-date-size, .9em); color: var(--secondary-text-color); white-space:nowrap; }
        /* Age colours match the app: green, yellow, orange, red (half, three quarters and all of the
           shelf life), lighter in dark mode. */
        .when.l0 { color: #2e7d32; }
        .when.l1 { color: #7a5f00; }
        .when.l2 { color: #a85100; }
        .when.l3 { color: #b71c1c; font-weight:500; }
        .dark .when.l0 { color: #81c784; }
        .dark .when.l1 { color: #ffd54f; }
        .dark .when.l2 { color: #ffb74d; }
        .dark .when.l3 { color: #ff8a80; }
        .done .name { text-decoration: line-through; }
        .done .name, .done .notes, .done .when { color: var(--secondary-text-color); font-weight: normal; }
        .act { background:none; border:none; cursor:pointer; color: var(--secondary-text-color); padding:4px; }
        .act + .act { margin-left: -8px; }
        .edit:hover, .save:hover { color: var(--primary-color); }
        .del:hover { color: var(--error-color, #c62828); }
        form.editing { flex:1; min-width:0; margin:0; flex-wrap:nowrap; align-items:center; }
        form.editing input { flex: 1 1 auto; min-width:0; padding:6px 8px; }
        .empty, .err { color: var(--secondary-text-color); padding: 8px 6px; font-size:.9em; }
        .err { color: var(--error-color); }
        dialog { border:none; border-radius:16px; padding:20px 20px 12px; max-width:320px;
                 background: var(--card-background-color); color: var(--primary-text-color);
                 box-shadow: 0 8px 24px rgba(0,0,0,.3); }
        dialog::backdrop { background: rgba(0,0,0,.4); }
        dialog h3 { margin:0 0 8px; font-size:1.2em; font-weight:500; }
        dialog p { margin:0 0 16px; color: var(--secondary-text-color); }
        dialog .btns { display:flex; justify-content:flex-end; gap:4px; }
        dialog button { font: inherit; background:none; border:none; cursor:pointer; padding:8px 12px;
                        border-radius:8px; color: var(--primary-color); font-weight:500; }
        dialog button:hover { background: var(--secondary-background-color); }
      </style>
      <ha-card>
        <div class="head"><ha-icon icon="mdi:snowflake"></ha-icon><span class="title"></span>
          <span class="bblabel">Best before</span>
          <button class="hbtn refresh" type="button" title="Refresh"><ha-icon icon="mdi:refresh"></ha-icon></button></div>
        <form class="add-form">
          <input name="itemName" placeholder="Add item…" autocomplete="off" required>
          <input name="qty" placeholder="Qty" autocomplete="off">
          <input name="frozen" type="date" value="${today.getFullYear()}-${pad(today.getMonth() + 1)}-${pad(today.getDate())}">
          <button class="add" type="submit">Add</button>
        </form>
        <div class="err" hidden></div>
        <div class="list"></div>
      </ha-card>
      <dialog class="dup">
        <h3>Already in list</h3>
        <p>There's already an item with this name, quantity and date in the freezer.</p>
        <form method="dialog" class="btns">
          <button value="cancel">Cancel</button>
          <button value="add">Add</button>
        </form>
      </dialog>`;
    root.querySelector("form.add-form").addEventListener("submit", (ev) => {
      ev.preventDefault();
      this._add().catch((err) => this._showError(err));
    });
    root.querySelector(".refresh").addEventListener("click", () => this._refresh());
    const list = root.querySelector(".list");
    list.addEventListener("click", (ev) => {
      const btn = ev.target.closest("button");
      const main = ev.target.closest(".main");
      if (btn?.classList.contains("del")) this._remove(btn.dataset.uid, btn.dataset.name);
      else if (btn?.classList.contains("edit")) this._startEdit(btn.dataset.uid);
      else if (btn?.classList.contains("cancel")) this._endEdit();
      else if (main) this._toggle(main.dataset.uid);
    });
    list.addEventListener("submit", (ev) => {
      ev.preventDefault();
      this._saveEdit(ev.target.elements.summary.value).catch((err) => this._showError(err));
    });
    list.addEventListener("keydown", (ev) => { if (ev.key === "Escape") this._endEdit(); });
  }

  _showError(err) {
    const el = this.shadowRoot?.querySelector(".err");
    if (!el) return;
    el.hidden = !err;
    el.textContent = err ? `Error: ${err.message || err}` : "";
  }

  _parsed() {
    const byBestBefore = this._config.sort_by_best_before;
    return this._items.map((it) => {
      const date = isoDate(it.frozen_on);
      // A fridge's categories keep for days instead of months.
      const days = it.shelf_life_days || null;
      const months = it.shelf_life_months || DEFAULT_SHELF_LIFE;
      return { uid: it.uid, name: it.name, qty: it.quantity, notes: it.notes, category: it.category,
        done: it.checked, checkedAt: it.checked_at || 0, date, months, days,
        bestBefore: date ? (days ? addDays(date, days) : addMonths(date, months)) : null, key: this._key(it.name, it.quantity, date) };
    }).sort((a, b) => {
      if (a.done !== b.done) return a.done ? 1 : -1;
      if (a.done && a.checkedAt !== b.checkedAt) return b.checkedAt - a.checkedAt;
      const ka = byBestBefore ? a.bestBefore : a.date, kb = byBestBefore ? b.bestBefore : b.date;
      if (!ka !== !kb) return ka ? -1 : 1;
      if (ka && kb && ka - kb) return ka - kb;
      if (a.date && b.date && a.date - b.date) return a.date - b.date;
      return a.name.localeCompare(b.name);
    });
  }

  // Identifies "the same item" for the duplicate check: name, quantity and freeze date.
  _key(name, qty, date) {
    return `${norm(name)}|${norm(qty)}|${date ? isoString(date) : ""}`;
  }

  _confirmDuplicate() {
    const dialog = this.shadowRoot.querySelector("dialog.dup");
    return new Promise((resolve) => {
      dialog.returnValue = "";
      dialog.addEventListener("close", () => resolve(dialog.returnValue === "add"), { once: true });
      dialog.showModal();
    });
  }

  _row(it) {
    const done = it.done;
    const level = ageLevel(it.date, it.months, it.days);
    const color = !done && this._config.date_color;
    const sub = [this._config.show_category && it.category, it.notes].filter(Boolean).join(" · ");
    if (it.uid === this._editing) return this._editRow(it, done);
    return `
      <div class="row ${done ? "done" : ""}">
        <div class="main" data-uid="${esc(it.uid)}">
          ${this._config.show_checkbox ? `<ha-icon icon="${done ? "mdi:check-circle" : "mdi:checkbox-blank-circle-outline"}"></ha-icon>` : ""}
          <div class="text">
            <div class="name">${esc(it.name)}${it.qty ? ` (${esc(it.qty)})` : ""}</div>
            ${sub ? `<div class="notes">${esc(sub)}</div>` : ""}
          </div>
        </div>
        <div class="when ${color || done ? "" : `l${level}`}"${color ? ` style="color:${esc(color)}"` : ""}>${it.bestBefore ? `${esc(this._fmt(it.bestBefore))}<br>${esc(timeLeft(it.bestBefore))}` : "no date"}</div>
        ${this._config.show_edit ? `<button class="act edit" title="Edit" data-uid="${esc(it.uid)}">
          <ha-icon icon="mdi:pencil-outline"></ha-icon>
        </button>` : ""}
        ${this._config.show_delete ? `<button class="act del" title="Delete" data-uid="${esc(it.uid)}" data-name="${esc(it.name)}">
          <ha-icon icon="mdi:trash-can-outline"></ha-icon>
        </button>` : ""}
      </div>`;
  }

  // Editing from the card changes the name; the rest is edited in the app.
  _editRow(it, done) {
    return `
      <div class="row ${done ? "done" : ""}">
        <form class="editing">
          <ha-icon icon="mdi:pencil-outline" style="color: var(--primary-color)"></ha-icon>
          <input name="summary" value="${esc(it.name)}" autocomplete="off" required>
          <button class="act save" type="submit" title="Save"><ha-icon icon="mdi:check"></ha-icon></button>
          <button class="act cancel" type="button" title="Cancel"><ha-icon icon="mdi:close"></ha-icon></button>
        </form>
      </div>`;
  }

  _startEdit(uid) {
    this._editing = uid;
    this._renderList();
    const input = this.shadowRoot.querySelector("form.editing input");
    if (input) { input.focus(); input.select(); }
  }

  _endEdit() {
    this._editing = null;
    this._renderList();
  }

  async _saveEdit(summary) {
    const uid = this._editing;
    const it = this._items.find((i) => i.uid === uid);
    const name = summary.trim();
    if (it && name && name !== it.name) await this._call("todo", "update_item", { item: uid, rename: name });
    this._endEdit();
  }

  async _refresh() {
    const btn = this.shadowRoot.querySelector(".refresh");
    btn.classList.add("spin");
    try {
      this._showError(null);
      await this._hass.callService("homeassistant", "update_entity", { entity_id: this._config.entity });
    } catch (err) {
      this._showError(err);
    } finally {
      btn.classList.remove("spin");
    }
  }

  _renderList() {
    if (!this.shadowRoot) return;
    if (this._editing && !this._items.some((i) => i.uid === this._editing)) this._editing = null;
    // Live updates re-render the list; keep whatever is being typed in the edit field.
    const field = this.shadowRoot.querySelector("form.editing input");
    const draft = field && { value: field.value, start: field.selectionStart, end: field.selectionEnd };
    const items = this._parsed();
    // One list: checked-off items are already sorted to the bottom.
    const shown = this._config.show_checked ? items : items.filter((i) => !i.done);
    const open = items.filter((i) => !i.done);
    let html = open.length ? "" : `<div class="empty">The freezer is empty.</div>`;
    html += shown.map((i) => this._row(i)).join("");
    this.shadowRoot.querySelector(".list").innerHTML = html;
    const next = this.shadowRoot.querySelector("form.editing input");
    if (draft && next) { next.value = draft.value; next.focus(); next.setSelectionRange(draft.start, draft.end); }
    this.shadowRoot.querySelector(".title").textContent =
      this._config.show_count ? `${this._config.title} (${open.length})` : this._config.title;
  }

  async _call(domain, service, data) {
    try {
      this._showError(null);
      await this._hass.callService(domain, service, data, { entity_id: this._config.entity });
    } catch (err) {
      this._showError(err);
      throw err;
    }
  }

  async _toggle(uid) {
    const it = this._items.find((i) => i.uid === uid);
    if (!it) return;
    await this._call("todo", "update_item", { item: uid, status: it.checked ? "needs_action" : "completed" });
  }

  async _remove(uid, name) {
    if (!confirm(`Delete "${name}" from the freezer list?`)) return;
    await this._call("todo", "remove_item", { item: uid });
  }

  async _add() {
    const form = this.shadowRoot.querySelector("form.add-form");
    // Not `elements.item`: that's HTMLFormControlsCollection.item(), not the input.
    let name = form.elements.itemName.value.trim();
    if (!name) return;
    const qty = form.elements.qty.value.trim();
    // A date typed in the name ("Worst 05-05-2025") wins over the date field, and leaves the name.
    const inName = findDate(name, this._config.day_first);
    if (inName) name = name.replace(inName.match, "").replace(/\(\s*\)/g, "").trim() || name;
    const date = inName ? inName.date : isoDate(form.elements.frozen.value) || new Date();

    const dup = this._parsed().some((i) => !i.done && i.key === this._key(name, qty, date));
    if (dup && !(await this._confirmDuplicate())) return;

    // The category last used for this name is filled in by the integration.
    await this._call("umamilist", "add_item", { name, ...(qty ? { quantity: qty } : {}), frozen_on: isoString(date) });
    form.elements.itemName.value = "";
    form.elements.qty.value = "";
  }
}

// The integration loads this card itself; an older copy added by hand as a resource mustn't clash with it.
if (!customElements.get("umamilist-freezer-card")) customElements.define("umamilist-freezer-card", UmamiListFreezerCard);
window.customCards = window.customCards || [];
if (!window.customCards.some((c) => c.type === "umamilist-freezer-card")) window.customCards.push({
  type: "umamilist-freezer-card",
  name: "Umaimi Chef freezer card",
  description: "Umaimi Chef inventory (freezer, pantry…) with best-before dates by category, with quantities and add / check off / delete.",
});
