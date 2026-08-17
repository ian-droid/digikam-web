(() => {
  "use strict";

  const LS_ALBUM_EXPAND = "digikam_web_album_expand";
  const LS_DATE_EXPAND = "digikam_web_date_expand";
  const LS_VIEW = "digikam_web_view";
  const LS_TAG_EXPAND = "digikam_web_tag_expand";
  const LS_TAG_MODE = "digikam_web_tag_mode";

  // Thumbnail geometry follows CSS variables (responsive on mobile)
  const PAGE_SIZE = 60;
  const MAX_DOM = 120;
  const OVERSCAN_ROWS = 2;

  function cellMetrics() {
    const cs = getComputedStyle(document.documentElement);
    const cellW = parseFloat(cs.getPropertyValue("--cell-w")) || 160;
    const imgH = parseFloat(cs.getPropertyValue("--cell-h-img")) || 160;
    const metaH = parseFloat(cs.getPropertyValue("--cell-meta")) || 26;
    const gap = parseFloat(cs.getPropertyValue("--cell-gap")) || 12;
    // gap may be in rem if browser returns full value - parseFloat handles "0.75rem" as 0.75
    // Convert rem gap approximately
    let gapPx = gap;
    const rawGap = (cs.getPropertyValue("--cell-gap") || "").trim();
    if (rawGap.endsWith("rem")) {
      const rootFs = parseFloat(getComputedStyle(document.documentElement).fontSize) || 16;
      gapPx = gap * rootFs;
    }
    return {
      cellW,
      cellH: imgH + metaH,
      gap: gapPx,
    };
  }

  const state = {
    view: "albums", // albums | dates
    currentAlbumId: null,
    dateFilter: null, // { year, month?, day? }
    tagId: null,
    buffer: [],       // all fetched image metadata (lightweight)
    total: 0,
    nextOffset: 0,    // next API offset
    hasMore: false,
    sort: "date",
    loading: false,
    windowStart: 0,   // first buffer index currently in the DOM window
  };

  const $ = (sel) => document.querySelector(sel);
  const albumTreeEl = $("#album-tree");
  const dateTreeEl = $("#date-tree");
  const panelAlbums = $("#panel-albums");
  const panelDates = $("#panel-dates");
  const panelTags = $("#panel-tags");
  const tagTreeEl = $("#tag-tree");
  const tagModeSelect = $("#tag-mode-select");
  const gridEl = $("#image-grid");
  const titleEl = $("#album-title");
  const countEl = $("#image-count");
  const sortSelect = $("#sort-select");
  const sidebarToggle = $("#sidebar-toggle");
  const sidebarEl = $("#sidebar");
  const sidebarBackdrop = $("#sidebar-backdrop");

  function isMobileLayout() {
    return window.matchMedia("(max-width: 900px)").matches;
  }

  function setSidebarOpen(open) {
    document.body.classList.toggle("sidebar-open", open);
    if (sidebarToggle) {
      sidebarToggle.setAttribute("aria-expanded", open ? "true" : "false");
      sidebarToggle.setAttribute("aria-label", open ? "Close navigation" : "Open navigation");
    }
    if (sidebarBackdrop) sidebarBackdrop.hidden = !open;
  }

  function closeSidebarIfMobile() {
    if (isMobileLayout()) setSidebarOpen(false);
  }

  if (sidebarToggle) {
    sidebarToggle.addEventListener("click", () => {
      setSidebarOpen(!document.body.classList.contains("sidebar-open"));
    });
  }
  if (sidebarBackdrop) {
    sidebarBackdrop.addEventListener("click", () => setSidebarOpen(false));
  }
  const lightbox = $("#lightbox");
  const lbImg = $("#lb-img");
  const lbCaption = $("#lb-caption");
  const lbClose = $("#lb-close");

  function loadExpandMap(key) {
    try {
      return JSON.parse(localStorage.getItem(key) || "{}") || {};
    } catch {
      return {};
    }
  }

  function saveExpandMap(key, map) {
    try {
      localStorage.setItem(key, JSON.stringify(map));
    } catch (_) {}
  }

  function isExpanded(map, id, defaultExpanded = false) {
    if (Object.prototype.hasOwnProperty.call(map, id)) return !!map[id];
    return defaultExpanded;
  }

  // ---------- View tabs ----------
  function setView(view) {
    state.view = view;
    localStorage.setItem(LS_VIEW, view);
    document.querySelectorAll(".view-tab").forEach((t) => {
      t.classList.toggle("active", t.dataset.view === view);
    });
    panelAlbums.hidden = view !== "albums";
    panelDates.hidden = view !== "dates";
    if (panelTags) panelTags.hidden = view !== "tags";
    if (view === "dates" && dateTreeEl && !dateTreeEl.dataset.loaded) {
      loadDates();
    }
    if (view === "tags" && tagTreeEl && !tagTreeEl.dataset.loaded) {
      loadTags();
    }
  }

  document.querySelectorAll(".view-tab").forEach((tab) => {
    tab.addEventListener("click", () => setView(tab.dataset.view));
  });

  // ---------- Album tree ----------
  async function loadAlbums() {
    albumTreeEl.innerHTML = `<div class="loading">Loading albums…</div>`;
    try {
      const res = await fetch("/api/albums", { credentials: "same-origin" });
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const data = await res.json();
      renderAlbumTree(data.albums || []);
    } catch (err) {
      albumTreeEl.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
      console.error("loadAlbums", err);
    }
  }

  function renderAlbumTree(nodes) {
    albumTreeEl.innerHTML = "";
    if (!nodes.length) {
      albumTreeEl.innerHTML = `<div class="loading">No albums found</div>`;
      return;
    }
    const expandMap = loadExpandMap(LS_ALBUM_EXPAND);
    const frag = document.createDocumentFragment();
    nodes.forEach((node) => renderAlbumNode(node, frag, 0, expandMap));
    albumTreeEl.appendChild(frag);
  }

  function renderAlbumNode(node, parent, depth, expandMap) {
    const hasChildren = node.children && node.children.length > 0;
    const nodeKey = node.id || `path-${node.relativePath}`;
    const el = document.createElement("div");
    el.className = "album-item";
    el.style.setProperty("--depth", depth);
    el.dataset.id = node.digikam_id || "";
    el.dataset.key = nodeKey;

    const twisty = document.createElement("span");
    twisty.className = "twisty";
    const expanded = hasChildren && isExpanded(expandMap, nodeKey, false);
    twisty.textContent = hasChildren ? (expanded ? "▾" : "▸") : " ";
    el.appendChild(twisty);

    const name = document.createElement("span");
    name.textContent = node.name || "(unnamed)";
    el.appendChild(name);

    if (node.image_count) {
      const cnt = document.createElement("span");
      cnt.className = "count";
      cnt.textContent = node.image_count;
      el.appendChild(cnt);
    }

    if (node.digikam_id) {
      el.addEventListener("click", (e) => {
        e.stopPropagation();
        state.dateFilter = null;
        selectAlbum(node.digikam_id, node.name);
        document.querySelectorAll(".album-item.active").forEach((a) => a.classList.remove("active"));
        el.classList.add("active");
      });
    }

    parent.appendChild(el);

    if (hasChildren) {
      const childWrap = document.createElement("div");
      childWrap.className = "album-children";
      childWrap.style.display = expanded ? "" : "none";
      node.children.forEach((c) => renderAlbumNode(c, childWrap, depth + 1, expandMap));
      parent.appendChild(childWrap);

      twisty.style.cursor = "pointer";
      twisty.addEventListener("click", (e) => {
        e.stopPropagation();
        const nowHidden = childWrap.style.display !== "none";
        childWrap.style.display = nowHidden ? "none" : "";
        twisty.textContent = nowHidden ? "▸" : "▾";
        const map = loadExpandMap(LS_ALBUM_EXPAND);
        map[nodeKey] = !nowHidden;
        saveExpandMap(LS_ALBUM_EXPAND, map);
      });
    }
  }

  // ---------- Date tree ----------
  async function loadDates() {
    dateTreeEl.innerHTML = `<div class="loading">Loading dates…</div>`;
    try {
      const res = await fetch("/api/dates", { credentials: "same-origin" });
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const data = await res.json();
      renderDateTree(data.dates || []);
      dateTreeEl.dataset.loaded = "1";
    } catch (err) {
      dateTreeEl.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
      console.error("loadDates", err);
    }
  }

  function renderDateTree(years) {
    dateTreeEl.innerHTML = "";
    if (!years.length) {
      dateTreeEl.innerHTML = `<div class="loading">No dated photos found</div>`;
      return;
    }
    const expandMap = loadExpandMap(LS_DATE_EXPAND);
    const frag = document.createDocumentFragment();
    years.forEach((y) => renderYearNode(y, frag, expandMap));
    dateTreeEl.appendChild(frag);
  }

  function renderYearNode(y, parent, expandMap) {
    const key = `y-${y.year}`;
    const hasChildren = y.months && y.months.length > 0;
    const expanded = hasChildren && isExpanded(expandMap, key, false);

    const el = document.createElement("div");
    el.className = "album-item";
    el.style.setProperty("--depth", 0);

    const twisty = document.createElement("span");
    twisty.className = "twisty";
    twisty.textContent = hasChildren ? (expanded ? "▾" : "▸") : " ";
    el.appendChild(twisty);

    const name = document.createElement("span");
    name.textContent = y.year;
    el.appendChild(name);

    const cnt = document.createElement("span");
    cnt.className = "count";
    cnt.textContent = y.count;
    el.appendChild(cnt);

    el.addEventListener("click", (e) => {
      e.stopPropagation();
      selectDate({ year: y.year }, y.year);
      document.querySelectorAll("#date-tree .album-item.active").forEach((a) => a.classList.remove("active"));
      el.classList.add("active");
    });

    parent.appendChild(el);

    if (hasChildren) {
      const childWrap = document.createElement("div");
      childWrap.className = "album-children";
      childWrap.style.display = expanded ? "" : "none";
      y.months.forEach((m) => renderMonthNode(y.year, m, childWrap, expandMap));
      parent.appendChild(childWrap);

      twisty.style.cursor = "pointer";
      twisty.addEventListener("click", (e) => {
        e.stopPropagation();
        const nowHidden = childWrap.style.display !== "none";
        childWrap.style.display = nowHidden ? "none" : "";
        twisty.textContent = nowHidden ? "▸" : "▾";
        const map = loadExpandMap(LS_DATE_EXPAND);
        map[key] = !nowHidden;
        saveExpandMap(LS_DATE_EXPAND, map);
      });
    }
  }

  function renderMonthNode(year, m, parent, expandMap) {
    const key = `y-${year}-m-${m.month}`;
    const hasChildren = m.days && m.days.length > 0;
    const expanded = hasChildren && isExpanded(expandMap, key, false);
    const label = m.label || m.month;

    const el = document.createElement("div");
    el.className = "album-item";
    el.style.setProperty("--depth", 1);

    const twisty = document.createElement("span");
    twisty.className = "twisty";
    twisty.textContent = hasChildren ? (expanded ? "▾" : "▸") : " ";
    el.appendChild(twisty);

    const name = document.createElement("span");
    name.textContent = label;
    el.appendChild(name);

    const cnt = document.createElement("span");
    cnt.className = "count";
    cnt.textContent = m.count;
    el.appendChild(cnt);

    el.addEventListener("click", (e) => {
      e.stopPropagation();
      selectDate({ year, month: m.month }, `${year} / ${label}`);
      document.querySelectorAll("#date-tree .album-item.active").forEach((a) => a.classList.remove("active"));
      el.classList.add("active");
    });

    parent.appendChild(el);

    if (hasChildren) {
      const childWrap = document.createElement("div");
      childWrap.className = "album-children";
      childWrap.style.display = expanded ? "" : "none";
      m.days.forEach((d) => renderDayNode(year, m.month, label, d, childWrap));
      parent.appendChild(childWrap);

      twisty.style.cursor = "pointer";
      twisty.addEventListener("click", (e) => {
        e.stopPropagation();
        const nowHidden = childWrap.style.display !== "none";
        childWrap.style.display = nowHidden ? "none" : "";
        twisty.textContent = nowHidden ? "▸" : "▾";
        const map = loadExpandMap(LS_DATE_EXPAND);
        map[key] = !nowHidden;
        saveExpandMap(LS_DATE_EXPAND, map);
      });
    }
  }

  function renderDayNode(year, month, monthLabel, d, parent) {
    const el = document.createElement("div");
    el.className = "album-item";
    el.style.setProperty("--depth", 2);

    const twisty = document.createElement("span");
    twisty.className = "twisty";
    twisty.textContent = " ";
    el.appendChild(twisty);

    const name = document.createElement("span");
    const dayNum = String(parseInt(d.day, 10));
    name.textContent = dayNum;
    el.appendChild(name);

    const cnt = document.createElement("span");
    cnt.className = "count";
    cnt.textContent = d.count;
    el.appendChild(cnt);

    el.addEventListener("click", (e) => {
      e.stopPropagation();
      selectDate(
        { year, month, day: d.day },
        `${year} / ${monthLabel} / ${dayNum}`
      );
      document.querySelectorAll("#date-tree .album-item.active").forEach((a) => a.classList.remove("active"));
      el.classList.add("active");
    });

    parent.appendChild(el);
  }

  // ---------- Tags tree ----------
  function currentTagMode() {
    if (tagModeSelect) return tagModeSelect.value === "people" ? "people" : "all";
    return localStorage.getItem(LS_TAG_MODE) || "all";
  }

  async function loadTags() {
    if (!tagTreeEl) return;
    tagTreeEl.innerHTML = `<div class="loading">Loading tags…</div>`;
    const peopleOnly = currentTagMode() === "people";
    try {
      const res = await fetch(`/api/tags?people_only=${peopleOnly ? "true" : "false"}`, {
        credentials: "same-origin",
      });
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) {
        let detail = res.statusText;
        try {
          const body = await res.json();
          detail = body.detail || detail;
        } catch (_) {}
        throw new Error(detail);
      }
      const data = await res.json();
      renderTagTree(data.tags || []);
      tagTreeEl.dataset.loaded = "1";
    } catch (err) {
      tagTreeEl.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
      console.error("loadTags", err);
    }
  }

  function renderTagTree(nodes) {
    tagTreeEl.innerHTML = "";
    if (!nodes.length) {
      tagTreeEl.innerHTML = `<div class="loading">${
        currentTagMode() === "people"
          ? "No people tags found (DigiKam TagProperties person/face flags)"
          : "No tags found"
      }</div>`;
      return;
    }
    const expandMap = loadExpandMap(LS_TAG_EXPAND);
    const frag = document.createDocumentFragment();
    nodes.forEach((node) => renderTagNode(node, frag, 0, expandMap));
    tagTreeEl.appendChild(frag);
  }

  function renderTagNode(node, parent, depth, expandMap) {
    const hasChildren = node.children && node.children.length > 0;
    const nodeKey = `tag-${node.id}`;
    const el = document.createElement("div");
    el.className = "album-item";
    if (node.is_person) el.classList.add("tag-person");
    el.style.setProperty("--depth", depth);
    el.dataset.id = String(node.id);

    const twisty = document.createElement("span");
    twisty.className = "twisty";
    const expanded = hasChildren && isExpanded(expandMap, nodeKey, false);
    twisty.textContent = hasChildren ? (expanded ? "▾" : "▸") : " ";
    el.appendChild(twisty);

    const name = document.createElement("span");
    name.textContent = node.name || "(unnamed)";
    el.appendChild(name);

    if (node.is_person) {
      const badge = document.createElement("span");
      badge.className = "count";
      badge.textContent = "person";
      el.appendChild(badge);
    }

    el.addEventListener("click", (e) => {
      e.stopPropagation();
      selectTag(node.id, node.name);
      document.querySelectorAll("#tag-tree .album-item.active").forEach((a) => a.classList.remove("active"));
      el.classList.add("active");
    });

    parent.appendChild(el);

    if (hasChildren) {
      const childWrap = document.createElement("div");
      childWrap.className = "album-children";
      childWrap.style.display = expanded ? "" : "none";
      node.children.forEach((c) => renderTagNode(c, childWrap, depth + 1, expandMap));
      parent.appendChild(childWrap);

      twisty.style.cursor = "pointer";
      twisty.addEventListener("click", (e) => {
        e.stopPropagation();
        const nowHidden = childWrap.style.display !== "none";
        childWrap.style.display = nowHidden ? "none" : "";
        twisty.textContent = nowHidden ? "▸" : "▾";
        const map = loadExpandMap(LS_TAG_EXPAND);
        map[nodeKey] = !nowHidden;
        saveExpandMap(LS_TAG_EXPAND, map);
      });
    }
  }

  async function selectTag(tagId, name) {
    state.currentAlbumId = null;
    state.dateFilter = null;
    state.tagId = tagId;
    resetGridState();
    titleEl.textContent = name || `Tag ${tagId}`;
    gridEl.innerHTML = `<div class="loading">Loading…</div>`;
    closeSidebarIfMobile();
    await loadImages();
  }

  // ---------- Image loading (fixed size + sliding window) ----------
  function gridCols() {
    const { cellW, gap } = cellMetrics();
    const pad = 16;
    const w = Math.max(cellW, gridEl.clientWidth - pad);
    return Math.max(1, Math.floor((w + gap) / (cellW + gap)));
  }

  function cardStrideY() {
    const { cellH, gap } = cellMetrics();
    return cellH + gap;
  }

  function resetGridState() {
    state.buffer = [];
    state.total = 0;
    state.nextOffset = 0;
    state.hasMore = false;
    state.fetchStarted = false;
    state.windowStart = 0;
  }

  async function selectAlbum(albumId, name) {
    state.currentAlbumId = albumId;
    state.dateFilter = null;
    state.tagId = null;
    resetGridState();
    titleEl.textContent = name || `Album ${albumId}`;
    gridEl.innerHTML = `<div class="loading">Loading…</div>`;
    closeSidebarIfMobile();
    await loadImages();
  }

  async function selectDate(filter, label) {
    state.currentAlbumId = null;
    state.dateFilter = filter;
    state.tagId = null;
    resetGridState();
    titleEl.textContent = label;
    gridEl.innerHTML = `<div class="loading">Loading…</div>`;
    closeSidebarIfMobile();
    await loadImages();
  }

  function buildListUrl(offset, limit) {
    if (state.dateFilter) {
      const q = new URLSearchParams({
        offset: String(offset),
        limit: String(limit),
        sort: state.sort,
      });
      if (state.dateFilter.year) q.set("year", state.dateFilter.year);
      if (state.dateFilter.month) q.set("month", state.dateFilter.month);
      if (state.dateFilter.day) q.set("day", state.dateFilter.day);
      return `/api/dates/images?${q}`;
    }
    if (state.tagId != null) {
      return `/api/tags/${state.tagId}/images?offset=${offset}&limit=${limit}&sort=${state.sort}`;
    }
    return `/api/albums/${state.currentAlbumId}/images?offset=${offset}&limit=${limit}&sort=${state.sort}`;
  }

  async function loadImages() {
    if (state.loading) return;
    if (!state.currentAlbumId && !state.dateFilter && state.tagId == null) return;
    // After the first response, only continue while the API reports more pages
    if (state.fetchStarted && !state.hasMore) return;

    state.loading = true;
    state.fetchStarted = true;
    try {
      const res = await fetch(buildListUrl(state.nextOffset, PAGE_SIZE), {
        credentials: "same-origin",
      });
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) throw new Error("Failed to load images");
      const data = await res.json();

      state.total = data.total;
      state.hasMore = !!data.has_more;
      state.nextOffset += (data.images || []).length;
      state.buffer.push(...(data.images || []));

      countEl.textContent = `${state.total} item${state.total === 1 ? "" : "s"}`;

      if (!state.buffer.length) {
        gridEl.innerHTML = `<div class="placeholder">No photos in this selection.</div>`;
      } else {
        // Keep window near the end after append so scroll-down feels continuous
        ensureWindowForScroll();
        renderWindow();
      }
    } catch (err) {
      if (!state.buffer.length) {
        gridEl.innerHTML = `<div class="placeholder">Error: ${err.message}</div>`;
      }
    } finally {
      state.loading = false;
    }
  }

  function ensureWindowForScroll() {
    const cols = gridCols();
    const rowH = cardStrideY();
    const scrollTop = gridEl.scrollTop;
    const viewH = gridEl.clientHeight;

    const firstVisibleRow = Math.max(0, Math.floor(scrollTop / rowH) - OVERSCAN_ROWS);
    const visibleRows = Math.ceil(viewH / rowH) + OVERSCAN_ROWS * 2;
    let start = firstVisibleRow * cols;
    let end = start + visibleRows * cols;

    // Clamp to buffer; prefer showing the latest pages when just loaded
    if (end > state.buffer.length) {
      end = state.buffer.length;
      start = Math.max(0, end - MAX_DOM);
    }
    start = Math.max(0, Math.min(start, Math.max(0, state.buffer.length - 1)));
    end = Math.min(state.buffer.length, Math.max(start + 1, start + MAX_DOM));
    // Align start to column boundary for cleaner grid
    start = start - (start % cols);

    state.windowStart = start;
  }

  function renderWindow() {
    if (!state.buffer.length) return;

    const cols = gridCols();
    const rowH = cardStrideY();
    const totalRows = Math.ceil(state.buffer.length / cols);
    // If we know total catalog size and have all? use buffer length for sizer;
    // estimated full height uses total when hasMore so scrollbar grows gradually
    const knownCount = state.hasMore ? Math.max(state.buffer.length, state.nextOffset) : state.buffer.length;
    const sizerRows = Math.ceil(Math.max(knownCount, state.buffer.length) / cols);
    const totalHeight = sizerRows * rowH;

    let start = state.windowStart;
    start = Math.max(0, start - (start % cols));
    let end = Math.min(state.buffer.length, start + MAX_DOM);
    // expand end to fill rows
    end = Math.min(state.buffer.length, start + Math.ceil((end - start) / cols) * cols);

    const topRows = Math.floor(start / cols);
    const topPad = topRows * rowH;

    let sizer = gridEl.querySelector(".grid-sizer");
    let windowEl = gridEl.querySelector(".grid-window");
    if (!sizer) {
      gridEl.innerHTML = "";
      sizer = document.createElement("div");
      sizer.className = "grid-sizer";
      windowEl = document.createElement("div");
      windowEl.className = "grid-window";
      sizer.appendChild(windowEl);
      gridEl.appendChild(sizer);
    }

    sizer.style.height = `${totalHeight}px`;
    windowEl.style.top = `${topPad}px`;
    windowEl.innerHTML = "";

    const frag = document.createDocumentFragment();
    for (let i = start; i < end; i++) {
      frag.appendChild(createThumbCard(state.buffer[i]));
    }
    windowEl.appendChild(frag);

    state.windowStart = start;
  }

  function mediaKindFromName(name) {
    const n = (name || "").toLowerCase();
    if (/\.(mp4|mov|m4v|avi|mkv|webm|wmv|mpg|mpeg|3gp|mts|m2ts)$/.test(n)) return "video";
    if (/\.(jpe?g|png|gif|webp|tiff?|bmp)$/.test(n)) return "image";
    return "other";
  }

  function createThumbCard(img) {
    const card = document.createElement("div");
    card.className = "thumb-card";
    card.dataset.id = img.id;
    const kind = mediaKindFromName(img.name);
    if (kind !== "image") card.classList.add("thumb-nonimage", `thumb-${kind}`);

    const image = document.createElement("img");
    image.loading = "lazy";
    image.alt = img.name || "";
    const { cellW } = cellMetrics();
    image.width = Math.round(cellW);
    image.height = Math.round(cellW);
    const thumbSize = Math.min(320, Math.max(160, Math.round(cellW * 2)));
    image.src = `/api/images/${img.id}/thumb?size=${thumbSize}`;
    image.onerror = () => {
      image.style.background = "#333";
      image.alt = "No preview";
    };

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = img.name || `#${img.id}`;

    card.appendChild(image);
    if (kind === "video") {
      const badge = document.createElement("span");
      badge.className = "media-badge";
      badge.textContent = "VIDEO";
      card.appendChild(badge);
    } else if (kind === "other") {
      const badge = document.createElement("span");
      badge.className = "media-badge";
      badge.textContent = "FILE";
      card.appendChild(badge);
    }
    if (img.has_geo) {
      const geo = document.createElement("span");
      geo.className = "geo-badge";
      geo.title = "Has GPS location";
      geo.setAttribute("aria-label", "Has GPS location");
      geo.textContent = "🌐";
      card.appendChild(geo);
    }
    card.appendChild(meta);
    card.addEventListener("click", () => openLightbox(img));
    return card;
  }

  function onGridScroll() {
    if (!state.buffer.length) return;

    ensureWindowForScroll();
    renderWindow();

    const nearBottom =
      gridEl.scrollTop + gridEl.clientHeight >= gridEl.scrollHeight - 300;
    if (nearBottom && state.hasMore && !state.loading) {
      loadImages();
    }
  }

  // ---------- Lightbox + EXIF dialog ----------
  const lbInfo = $("#lb-info");
  const lbGeo = $("#lb-geo");
  const lbMapProvider = $("#lb-map-provider");
  const lbMapOpen = $("#lb-map-open");
  const exifDialog = $("#exif-dialog");
  const exifBody = $("#exif-dialog-body");
  const exifBackdrop = $("#exif-backdrop");
  const exifDialogClose = $("#exif-dialog-close");
  let lbCurrentId = null;
  let lbExifLoadedFor = null;
  let lbExifData = null;       // cached EXIF payload for current image
  let lbExifLoading = null;    // in-flight Promise for preload

  function openLightbox(img) {
    lbCurrentId = img.id;
    lbExifLoadedFor = null;
    lbExifData = null;
    lbExifLoading = null;
    // /file returns original for stills, placeholder image for video/unsupported
    lbImg.src = `/api/images/${img.id}/file`;
    const kind = mediaKindFromName(img.name);
    let caption = img.name || "";
    if (kind === "video") caption += " (video — preview not available)";
    else if (kind === "other") caption += " (no image preview)";
    lbCaption.textContent = caption;
    lightbox.hidden = false;
    closeExifDialog();
    hideToolbarGeo();
    // Preload EXIF/META while viewing; panel still opens only on ℹ
    const openedId = img.id;
    const gridHasGeo = !!img.has_geo;
    preloadExif(openedId).then((data) => {
      if (lbCurrentId !== openedId) return;
      updateToolbarGeo(data ? data.geo : null, gridHasGeo);
    }).catch(() => {
      if (lbCurrentId === openedId && gridHasGeo) {
        updateToolbarGeo(null, true);
      }
    });
  }

  function closeLightbox() {
    lightbox.hidden = true;
    lbImg.src = "";
    lbCurrentId = null;
    lbExifData = null;
    lbExifLoading = null;
    hideToolbarGeo();
    closeExifDialog();
  }

  function openExifDialog() {
    if (!lbCurrentId) return;
    exifDialog.hidden = false;
    if (lbExifLoadedFor === lbCurrentId && lbExifData) {
      renderExif(lbExifData);
      return;
    }
    // Still loading or failed — ensure fetch and show result when ready
    exifBody.innerHTML = `<div class="loading">Loading…</div>`;
    preloadExif(lbCurrentId).then((data) => {
      if (lbCurrentId == null) return;
      if (data) renderExif(data);
    });
  }

  function closeExifDialog() {
    if (exifDialog) exifDialog.hidden = true;
  }

  function preloadExif(imageId) {
    if (lbExifLoadedFor === imageId && lbExifData) {
      return Promise.resolve(lbExifData);
    }
    if (lbExifLoading && lbExifLoadedFor === imageId) {
      return lbExifLoading;
    }
    const id = imageId;
    lbExifLoading = (async () => {
      try {
        const res = await fetch(`/api/images/${id}/exif`, { credentials: "same-origin" });
        if (res.status === 401) {
          window.location.href = "/login";
          return null;
        }
        if (!res.ok) throw new Error("Failed to load metadata");
        const data = await res.json();
        // Ignore if user already moved to another image
        if (lbCurrentId !== id) return null;
        lbExifLoadedFor = id;
        lbExifData = data;
        return data;
      } catch (err) {
        if (lbCurrentId === id) {
          lbExifData = null;
          lbExifLoadedFor = null;
          // Only show error if the dialog is open
          if (exifDialog && !exifDialog.hidden) {
            exifBody.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
          }
        }
        return null;
      } finally {
        if (lbCurrentId === id) lbExifLoading = null;
      }
    })();
    return lbExifLoading;
  }


  // Map 🌐 → popup-like window (~1/2 screen width × 1/2 height)
  if (lbMapOpen) {
    lbMapOpen.addEventListener("click", (e) => {
      const url = lbMapOpen.getAttribute("href");
      if (!url || url === "#" || url === "null") {
        e.preventDefault();
        return;
      }
      e.preventDefault();
      const w = Math.max(400, Math.floor(window.screen.availWidth / 2));
      const h = Math.max(300, Math.floor(window.screen.availHeight / 2));
      const left = Math.max(0, Math.floor((window.screen.availWidth - w) / 2));
      const top = Math.max(0, Math.floor((window.screen.availHeight - h) / 2));
      const features = [
        `width=${w}`,
        `height=${h}`,
        `left=${left}`,
        `top=${top}`,
        "scrollbars=yes",
        "resizable=yes",
        "menubar=no",
        "toolbar=no",
        "location=yes",
        "status=no",
      ].join(",");
      const win = window.open(url, "digikam_web_map", features);
      if (win) {
        try { win.opener = null; } catch (_) {}
        try { win.focus(); } catch (_) {}
      } else {
        // Popup blocked — fall back to new tab
        window.open(url, "_blank", "noopener,noreferrer");
      }
    });
  }

  function hideToolbarGeo() {
    if (lbGeo) {
      lbGeo.hidden = true;
      lbGeo.setAttribute("hidden", "");
    }
    if (lbMapOpen) {
      lbMapOpen.removeAttribute("href");
      lbMapOpen.title = "";
    }
  }

  function updateToolbarGeo(geo, forceShow) {
    if (!lbGeo || !lbMapProvider || !lbMapOpen) {
      console.warn("Toolbar geo elements missing from DOM");
      return;
    }
    // Accept lat/lon or latitude/longitude
    let lat = geo && (geo.lat != null ? geo.lat : geo.latitude);
    let lon = geo && (geo.lon != null ? geo.lon : geo.longitude);
    lat = lat != null ? Number(lat) : NaN;
    lon = lon != null ? Number(lon) : NaN;
    const hasCoords = Number.isFinite(lat) && Number.isFinite(lon);

    if (!hasCoords && !forceShow) {
      hideToolbarGeo();
      return;
    }

    const tip = hasCoords
      ? `${lat.toFixed(6)}, ${lon.toFixed(6)}`
      : "GPS present (coordinates unavailable)";
    lbMapOpen.title = tip;
    lbMapOpen.setAttribute("aria-label", `Open in map (${tip})`);

    const applyHref = () => {
      if (!hasCoords) {
        lbMapOpen.removeAttribute("href");
        return;
      }
      const opt = lbMapProvider.selectedOptions[0];
      const urlTpl = opt ? opt.dataset.url : "";
      const zoom = (typeof mapDefaultZoom !== "undefined" && mapDefaultZoom) ? mapDefaultZoom : "15";
      lbMapOpen.href = buildMapUrl(urlTpl, lat, lon, zoom);
    };

    // Reveal immediately so the control is visible even while templates load
    lbGeo.hidden = false;
    lbGeo.removeAttribute("hidden");

    ensureMapTemplates()
      .then((templates) => {
        const list = templates && templates.length
          ? templates
          : [
              { id: "google", name: "Google Maps", url: "https://www.google.com/maps?q={lat},{lon}" },
              { id: "osm", name: "OpenStreetMap", url: "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}" },
            ];
        const prev = lbMapProvider.value;
        lbMapProvider.innerHTML = "";
        list.forEach((tpl) => {
          const opt = document.createElement("option");
          opt.value = tpl.id;
          opt.textContent = tpl.name;
          opt.dataset.url = tpl.url;
          lbMapProvider.appendChild(opt);
        });
        if (prev && [...lbMapProvider.options].some((o) => o.value === prev)) {
          lbMapProvider.value = prev;
        }
        applyHref();
        lbGeo.hidden = false;
        lbGeo.removeAttribute("hidden");
      })
      .catch((err) => {
        console.warn("map templates", err);
        applyHref();
        lbGeo.hidden = false;
        lbGeo.removeAttribute("hidden");
      });

    lbMapProvider.onchange = applyHref;
  }

  let mapLinkTemplates = null;
  let mapDefaultZoom = "15";

  async function ensureMapTemplates() {
    if (mapLinkTemplates) return mapLinkTemplates;
    try {
      const res = await fetch("/api/config/map-links", { credentials: "same-origin" });
      if (!res.ok) throw new Error("map-links");
      const data = await res.json();
      mapLinkTemplates = data.templates || [];
      mapDefaultZoom = data.default_zoom || "15";
    } catch {
      mapLinkTemplates = [
        { id: "google", name: "Google Maps", url: "https://www.google.com/maps?q={lat},{lon}" },
        { id: "osm", name: "OpenStreetMap", url: "https://www.openstreetmap.org/?mlat={lat}&mlon={lon}#map={zoom}/{lat}/{lon}" },
      ];
    }
    return mapLinkTemplates;
  }

  function buildMapUrl(template, lat, lon, zoom) {
    return String(template || "")
      .split("{lat}").join(String(lat))
      .split("{lon}").join(String(lon))
      .split("{zoom}").join(String(zoom || mapDefaultZoom));
  }

  function renderExif(data) {
    const sections = data.sections || [];
    // Geo / map controls live in the lightbox toolbar (updateToolbarGeo)
    if (!sections.length) {
      exifBody.innerHTML = `<div class="loading">No metadata in DigiKam database for this image.</div>`;
      return;
    }
    const frag = document.createDocumentFragment();

    sections.forEach((sec) => {
      const box = document.createElement("div");
      box.className = "lb-exif-section";
      const h = document.createElement("h4");
      h.textContent = sec.title;
      box.appendChild(h);
      (sec.fields || []).forEach((f) => {
        const row = document.createElement("div");
        row.className = "lb-exif-row";
        const k = document.createElement("span");
        k.className = "k";
        k.textContent = f.label;
        const v = document.createElement("span");
        v.className = "v";
        v.textContent = f.value;
        row.appendChild(k);
        row.appendChild(v);
        box.appendChild(row);
      });
      frag.appendChild(box);
    });
    exifBody.innerHTML = "";
    exifBody.appendChild(frag);
  }

  if (lbInfo) {
    lbInfo.addEventListener("click", (e) => {
      e.stopPropagation();
      openExifDialog();
    });
  }
  if (exifDialogClose) {
    exifDialogClose.addEventListener("click", (e) => {
      e.stopPropagation();
      closeExifDialog();
    });
  }
  if (exifBackdrop) {
    exifBackdrop.addEventListener("click", () => closeExifDialog());
  }

  lbClose.addEventListener("click", (e) => {
    e.stopPropagation();
    closeLightbox();
  });
  lightbox.addEventListener("click", (e) => {
    if (e.target === lightbox || e.target.classList.contains("lb-stage")) {
      closeLightbox();
    }
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") {
      if (exifDialog && !exifDialog.hidden) {
        closeExifDialog();
      } else if (!lightbox.hidden) {
        closeLightbox();
      }
    }
  });

  // ---------- Controls ----------
  sortSelect.addEventListener("change", () => {
    state.sort = sortSelect.value;
    if (state.currentAlbumId || state.dateFilter || state.tagId != null) {
      resetGridState();
      gridEl.innerHTML = `<div class="loading">Loading…</div>`;
      loadImages();
    }
  });

  gridEl.addEventListener("scroll", onGridScroll, { passive: true });

  // Recompute columns / window on resize
  let resizeTimer = null;
  window.addEventListener("resize", () => {
    clearTimeout(resizeTimer);
    resizeTimer = setTimeout(() => {
      if (state.buffer.length) {
        ensureWindowForScroll();
        renderWindow();
      }
    }, 100);
  });

  if (tagModeSelect) {
    const savedMode = localStorage.getItem(LS_TAG_MODE) || "all";
    tagModeSelect.value = savedMode === "people" ? "people" : "all";
    tagModeSelect.addEventListener("change", () => {
      localStorage.setItem(LS_TAG_MODE, tagModeSelect.value);
      if (tagTreeEl) {
        delete tagTreeEl.dataset.loaded;
      }
      loadTags();
    });
  }

  // Boot
  const savedView = localStorage.getItem(LS_VIEW) || "albums";
  setView(savedView);
  loadAlbums();
  if (savedView === "dates") loadDates();
  if (savedView === "tags") loadTags();
})();
