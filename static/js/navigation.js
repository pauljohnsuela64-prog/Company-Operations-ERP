(() => {
    "use strict";
    const nav = document.getElementById("erp-navigation");
    if (!nav) return;
    const toggle = document.querySelector(".navigation-toggle");
    const groups = [...nav.querySelectorAll(".nav-dropdown")];
    const mobile = window.matchMedia("(max-width: 767.98px)");
    let expanded = false;

    const trigger = (group) => group.querySelector("summary");
    const links = (group) => [...group.querySelectorAll(".dropdown-link")];
    const closeGroups = (except = null) => {
        groups.forEach((group) => {
            if (group === except) return;
            group.open = false;
            trigger(group).setAttribute("aria-expanded", "false");
        });
    };
    const openGroup = (group, enabled) => {
        closeGroups();
        group.open = enabled;
        trigger(group).setAttribute("aria-expanded", String(enabled));
        const panel = group.querySelector(".dropdown-panel");
        panel.style.transform = "";
        if (enabled && !mobile.matches) {
            // A category may wrap on tablets. Clamp its menu to the viewport
            // rather than assuming the final category is at the right edge.
            const bounds = panel.getBoundingClientRect();
            const width = document.documentElement.clientWidth;
            const offset = Math.max(16 - bounds.left, Math.min(0, width - 16 - bounds.right));
            panel.style.transform = `translateX(${offset}px)`;
        }
    };
    const setExpanded = (enabled, restoreFocus = false) => {
        expanded = mobile.matches && enabled;
        nav.hidden = mobile.matches && !expanded;
        toggle.setAttribute("aria-expanded", String(expanded));
        toggle.setAttribute("aria-label", expanded ? "Close navigation" : "Open navigation");
        if (!expanded) closeGroups();
        if (restoreFocus && mobile.matches) toggle.focus();
    };

    groups.forEach((group) => {
        const summary = trigger(group);
        summary.setAttribute("aria-expanded", "false");
        summary.addEventListener("click", (event) => {
            event.preventDefault();
            openGroup(group, !group.open);
        });
        group.addEventListener("keydown", (event) => {
            const items = links(group);
            const index = items.indexOf(document.activeElement);
            let next;
            if (event.key === "ArrowDown") next = index < 0 ? 0 : (index + 1) % items.length;
            else if (event.key === "ArrowUp") next = index < 0 ? items.length - 1 : (index - 1 + items.length) % items.length;
            else if (index >= 0 && event.key === "Home") next = 0;
            else if (index >= 0 && event.key === "End") next = items.length - 1;
            if (next !== undefined && items.length) {
                event.preventDefault();
                openGroup(group, true);
                items[next].focus();
            }
        });
    });
    toggle.addEventListener("click", () => setExpanded(!expanded));
    document.addEventListener("click", (event) => {
        if (!nav.contains(event.target) && !toggle.contains(event.target)) setExpanded(false);
        else if (nav.contains(event.target) && !event.target.closest(".nav-dropdown")) closeGroups();
        if (nav.contains(event.target) && event.target.closest("a")) setExpanded(false, true);
    });
    document.addEventListener("focusin", (event) => {
        groups.forEach((group) => {
            if (group.open && !group.contains(event.target)) {
                group.open = false;
                trigger(group).setAttribute("aria-expanded", "false");
            }
        });
        // Leaving the mobile panel by Tab closes it without pulling focus back.
        if (!nav.contains(event.target) && !toggle.contains(event.target)) setExpanded(false);
    });
    document.addEventListener("keydown", (event) => {
        if (event.key !== "Escape") return;
        const group = groups.find((item) => item.open);
        if (group) {
            event.preventDefault();
            closeGroups();
            trigger(group).focus();
        } else if (expanded) {
            event.preventDefault();
            setExpanded(false, true);
        }
    });
    mobile.addEventListener("change", () => {
        const inside = nav.contains(document.activeElement);
        const onToggle = document.activeElement === toggle;
        setExpanded(false, inside);
        if (!mobile.matches && onToggle) nav.querySelector("a").focus();
    });
    window.addEventListener("resize", () => {
        const focusedGroup = groups.find((group) => group.open && group.contains(document.activeElement));
        closeGroups();
        if (focusedGroup) trigger(focusedGroup).focus();
    });
    document.body.classList.add("navigation-ready");
    setExpanded(false);
})();
