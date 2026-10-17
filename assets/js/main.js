(() => {
  const menuButton = document.querySelector(".menu-toggle");
  const nav = document.querySelector(".primary-nav");
  if (menuButton && nav) {
    menuButton.addEventListener("click", () => {
      const open = menuButton.getAttribute("aria-expanded") !== "true";
      menuButton.setAttribute("aria-expanded", String(open));
      nav.classList.toggle("open", open);
    });
    const closeMenu = () => {
      nav.classList.remove("open");
      menuButton.setAttribute("aria-expanded", "false");
    };
    nav.querySelectorAll("a").forEach(link => link.addEventListener("click", closeMenu));
    document.addEventListener("keydown", event => {
      if (event.key === "Escape" && menuButton.getAttribute("aria-expanded") === "true") {
        closeMenu();
        menuButton.focus();
      }
    });
  }

  const searchInput = document.getElementById("tool-search");
  const searchForm = document.getElementById("tool-search-form");
  const cards = Array.from(document.querySelectorAll(".tool-card"));
  const tabs = Array.from(document.querySelectorAll(".filter-tab"));
  const count = document.getElementById("results-count");
  const empty = document.getElementById("empty-state");
  const grid = document.getElementById("tool-grid");
  let activeCategory = "all";

  function applyFilters() {
    const query = (searchInput?.value || "").trim().toLowerCase();
    let visible = 0;
    cards.forEach(card => {
      const categories = (card.dataset.categories || "").split(/\s+/);
      const terms = (card.dataset.search || "") + " " + card.textContent;
      const matchesCategory = activeCategory === "all" || categories.includes(activeCategory);
      const matchesQuery = !query || terms.toLowerCase().includes(query);
      const show = matchesCategory && matchesQuery;
      card.hidden = !show;
      if (show) visible++;
    });
    if (count) count.textContent = query ? `${visible} matches` : `${visible} ${visible === 1 ? "tool" : "tools"}`;
    if (empty) empty.hidden = visible !== 0;
    if (grid) grid.hidden = visible === 0;
  }

  tabs.forEach(tab => tab.addEventListener("click", () => {
    activeCategory = tab.dataset.filter || "all";
    tabs.forEach(item => {
      const selected = item === tab;
      item.classList.toggle("active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    applyFilters();
  }));

  document.querySelectorAll(".category-card[data-category]").forEach(card => card.addEventListener("click", event => {
    const category = card.dataset.category;
    const matchingTab = tabs.find(tab => tab.dataset.filter === category);
    if (!matchingTab) return;
    event.preventDefault();
    activeCategory = category;
    tabs.forEach(tab => {
      const selected = tab === matchingTab;
      tab.classList.toggle("active", selected);
      tab.setAttribute("aria-pressed", String(selected));
    });
    applyFilters();
    document.getElementById("directory")?.scrollIntoView({ behavior: "smooth" });
  }));

  if (searchInput) searchInput.addEventListener("input", applyFilters);
  if (searchForm) searchForm.addEventListener("submit", event => {
    event.preventDefault();
    document.getElementById("directory")?.scrollIntoView({ behavior: "smooth" });
    applyFilters();
  });

  document.querySelectorAll("[data-query]").forEach(button => button.addEventListener("click", () => {
    if (searchInput) {
      searchInput.value = button.dataset.query || "";
      activeCategory = "all";
      tabs.forEach(item => {
        const selected = item.dataset.filter === "all";
        item.classList.toggle("active", selected);
        item.setAttribute("aria-pressed", String(selected));
      });
      applyFilters();
      document.getElementById("directory")?.scrollIntoView({ behavior: "smooth" });
      searchInput.focus({ preventScroll: true });
    }
  }));

  document.getElementById("clear-filters")?.addEventListener("click", () => {
    if (searchInput) searchInput.value = "";
    activeCategory = "all";
    tabs.forEach(item => {
      const selected = item.dataset.filter === "all";
      item.classList.toggle("active", selected);
      item.setAttribute("aria-pressed", String(selected));
    });
    applyFilters();
  });

  const contactForm = document.getElementById("contact-form");
  if (contactForm) {
    const status = document.getElementById("contact-status");
    const submit = contactForm.querySelector('button[type="submit"]');
    contactForm.addEventListener("submit", async event => {
      event.preventDefault();
      const endpoint = contactForm.action;
      if (contactForm.dataset.formConfigured !== "true" || endpoint.includes("REPLACE_WITH_FORM_ID")) {
        status.textContent = "The contact form is being connected. Please try again later.";
        status.dataset.state = "error";
        return;
      }
      if (contactForm.elements._gotcha?.value) return;
      submit.disabled = true;
      status.textContent = "Sending your message…";
      status.dataset.state = "";
      try {
        const response = await fetch(endpoint, { method: "POST", body: new FormData(contactForm), headers: { Accept: "application/json" } });
        if (!response.ok) throw new Error("Submission failed");
        contactForm.reset();
        status.textContent = "Thanks! Your message has been sent.";
        status.dataset.state = "success";
      } catch (_) {
        status.textContent = "We couldn't send your message. Please try again shortly.";
        status.dataset.state = "error";
      } finally { submit.disabled = false; }
    });
  }

  const year = document.getElementById("current-year");
  if (year) year.textContent = String(new Date().getFullYear());
  applyFilters();
})();
