// Run: node --test tests/horizontal_navigation.test.cjs
// The shipped controller runs against DOM doubles; these are not visual tests.
const { test } = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const vm = require("node:vm");
const source = fs.readFileSync(path.join(__dirname, "../static/js/navigation.js"), "utf8");

function browser(mobile = false) {
    let document;
    class Element {
        constructor(parent = null) {
            this.parent = parent;
            this.events = {};
            this.attributes = new Map();
            this.open = false;
            this.hidden = false;
            this.style = {};
            this.classList = { add() {} };
        }
        addEventListener(name, callback) { this.events[name] = callback; }
        dispatch(name, event = {}) { this.events[name]?.(event); }
        setAttribute(name, value) { this.attributes.set(name, value); }
        getAttribute(name) { return this.attributes.get(name); }
        contains(target) {
            for (let node = target; node; node = node.parent) if (node === this) return true;
            return false;
        }
        closest(selector) {
            for (let node = this; node; node = node.parent) {
                if (selector === "a" && node.isLink) return node;
                if (selector === ".nav-dropdown" && node.isGroup) return node;
            }
            return null;
        }
        focus() { document.activeElement = this; document.dispatch("focusin", { target: this }); }
    }
    const nav = new Element();
    const toggle = new Element();
    const dashboard = new Element(nav);
    dashboard.isLink = true;
    const groups = Array.from({ length: 3 }, () => {
        const group = new Element(nav);
        group.isGroup = true;
        group.summary = new Element(group);
        group.panel = new Element(group);
        group.bounds = { left: 100, right: 336 };
        group.panel.getBoundingClientRect = () => group.bounds;
        group.links = Array.from({ length: 3 }, () => { const a = new Element(group); a.isLink = true; return a; });
        group.querySelector = (selector) => selector === "summary" ? group.summary : group.panel;
        group.querySelectorAll = () => group.links;
        return group;
    });
    nav.querySelectorAll = () => groups;
    nav.querySelector = () => dashboard;
    document = new Element();
    document.body = new Element();
    document.documentElement = { clientWidth: 1000 };
    document.getElementById = () => nav;
    document.querySelector = () => toggle;
    const media = new Element();
    media.matches = mobile;
    const window = new Element();
    window.matchMedia = () => media;
    vm.runInNewContext(source, { document, window });
    function click(element) {
        element.dispatch("click", { target: element, preventDefault() {} });
        document.dispatch("click", { target: element });
    }
    function key(element, key) {
        let prevented = false;
        const event = { key, target: element, preventDefault() { prevented = true; } };
        element.closest(".nav-dropdown")?.dispatch("keydown", event);
        document.dispatch("keydown", event);
        return prevented;
    }
    return { document, window, nav, toggle, dashboard, groups, media, click, key, Element };
}

test("category click toggles a menu and keeps at most one open", () => {
    const b = browser();
    assert.equal(b.nav.hidden, false);
    b.click(b.groups[0].summary);
    assert.equal(b.groups[0].open, true);
    assert.equal(b.groups[0].summary.getAttribute("aria-expanded"), "true");
    b.click(b.groups[1].summary);
    assert.equal(b.groups[0].open, false);
    assert.equal(b.groups[0].summary.getAttribute("aria-expanded"), "false");
    assert.equal(b.groups[1].open, true);
    b.click(b.groups[1].summary);
    assert.equal(b.groups[1].open, false);
});

test("outside click and dashboard click close dropdowns", () => {
    const b = browser();
    b.click(b.groups[0].summary);
    b.click(new b.Element());
    assert.ok(b.groups.every(g => !g.open));
    b.click(b.groups[0].summary);
    b.click(b.dashboard);
    assert.ok(b.groups.every(g => !g.open));
});

test("Escape closes a dropdown and returns focus to its category", () => {
    const b = browser();
    b.click(b.groups[0].summary);
    b.groups[0].links[0].focus();
    assert.equal(b.key(b.groups[0].links[0], "Escape"), true);
    assert.equal(b.groups[0].open, false);
    assert.equal(b.document.activeElement, b.groups[0].summary);
});

test("arrows, Home and End navigate dropdown links without hijacking Tab", () => {
    const b = browser();
    const g = b.groups[0];
    g.summary.focus();
    b.key(g.summary, "ArrowDown");
    assert.equal(b.document.activeElement, g.links[0]);
    b.key(g.links[0], "ArrowUp");
    assert.equal(b.document.activeElement, g.links[2]);
    b.key(g.links[2], "Home");
    assert.equal(b.document.activeElement, g.links[0]);
    b.key(g.links[0], "End");
    assert.equal(b.document.activeElement, g.links[2]);
    assert.equal(b.key(g.links[2], "Tab"), false);
    b.toggle.focus();
    assert.equal(g.open, false);
});

test("mobile toggle shows navigation; Escape closes menu then panel", () => {
    const b = browser(true);
    assert.equal(b.nav.hidden, true);
    b.click(b.toggle);
    assert.equal(b.nav.hidden, false);
    assert.equal(b.toggle.getAttribute("aria-expanded"), "true");
    b.click(b.groups[0].summary);
    b.key(b.groups[0].summary, "Escape");
    assert.equal(b.nav.hidden, false);
    b.key(b.groups[0].summary, "Escape");
    assert.equal(b.nav.hidden, true);
    assert.equal(b.document.activeElement, b.toggle);
});

test("mobile link activation and outside focus close panel", () => {
    const b = browser(true);
    b.click(b.toggle);
    b.click(b.groups[0].summary);
    b.click(b.groups[0].links[0]);
    assert.equal(b.nav.hidden, true);
    assert.equal(b.document.activeElement, b.toggle);
    b.click(b.toggle);
    new b.Element().focus();
    assert.equal(b.nav.hidden, true);
});

test("breakpoint changes keep navigation visibility and focus valid", () => {
    const b = browser();
    b.groups[0].summary.focus();
    b.media.matches = true;
    b.media.dispatch("change");
    assert.equal(b.nav.hidden, true);
    assert.equal(b.document.activeElement, b.toggle);
    b.media.matches = false;
    b.media.dispatch("change");
    assert.equal(b.nav.hidden, false);
    assert.equal(b.document.activeElement, b.dashboard);
});

test("desktop menus clamp at either viewport edge and reset for mobile", () => {
    const b = browser();
    const g = b.groups[0];
    g.bounds = { left: 900, right: 1136 };
    b.click(g.summary);
    assert.equal(g.panel.style.transform, "translateX(-152px)");
    b.window.dispatch("resize");
    assert.equal(g.open, false);
    g.bounds = { left: -80, right: 156 };
    b.click(g.summary);
    assert.equal(g.panel.style.transform, "translateX(96px)");
    b.media.matches = true;
    b.media.dispatch("change");
    b.click(b.toggle);
    b.click(g.summary);
    assert.equal(g.panel.style.transform, "");
});

test("controller is harmless on pages without navigation", () => {
    assert.doesNotThrow(() => vm.runInNewContext(source, { document: { getElementById: () => null } }));
});

test("resizing closes a focused dropdown without leaving focus in hidden links", () => {
    const b = browser();
    const g = b.groups[0];
    b.click(g.summary);
    g.links[1].focus();
    b.window.dispatch("resize");
    assert.equal(g.open, false);
    assert.equal(b.document.activeElement, g.summary);
});

test("mobile outside click and repeated toggle clicks close the panel", () => {
    const b = browser(true);
    b.click(b.toggle);
    b.click(new b.Element());
    assert.equal(b.nav.hidden, true);
    b.click(b.toggle);
    b.click(b.toggle);
    assert.equal(b.nav.hidden, true);
    assert.equal(b.toggle.getAttribute("aria-expanded"), "false");
});
