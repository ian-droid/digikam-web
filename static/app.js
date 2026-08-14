(() => {
  "use strict";

  const LS_ALBUM_EXPAND = "digikam_web_album_expand";
  const LS_DATE_EXPAND = "digikam_web_date_expand";
  const LS_VIEW = "digikam_web_view";

  // Fixed thumbnail geometry (must match CSS)
  const CELL_W = 160;
  const CELL_H = 160 + 26; // image + caption row
  const GAP = 12;          // 0.75rem
  const PAGE_SIZE = 60;    // API page size
  const MAX_DOM = 120;     // sliding window: max cards mounted in the DOM
  const OVERSCAN_ROWS = 2;

  const state = {
    view: "albums", // albums | dates
    currentAlbumId: null,
    dateFilter: null, // { year, month?, day? }
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
  const gridEl = $("#image-grid");
  const titleEl = $("#album-title");
  const countEl = $("#image-count");
  const sortSelect = $("#sort-select");
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
    if (view === "dates" && !dateTreeEl.dataset.loaded) {
      loadDates();
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

  // ---------- Image loading (fixed size + sliding window) ----------
  function gridCols() {
    const pad = 32; // approx horizontal padding
    const w = Math.max(CELL_W, gridEl.clientWidth - pad);
    return Math.max(1, Math.floor((w + GAP) / (CELL_W + GAP)));
  }

  function cardStrideY() {
    return CELL_H + GAP;
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
    resetGridState();
    titleEl.textContent = name || `Album ${albumId}`;
    gridEl.innerHTML = `<div class="loading">Loading…</div>`;
    await loadImages();
  }

  async function selectDate(filter, label) {
    state.currentAlbumId = null;
    state.dateFilter = filter;
    resetGridState();
    titleEl.textContent = label;
    gridEl.innerHTML = `<div class="loading">Loading…</div>`;
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
    return `/api/albums/${state.currentAlbumId}/images?offset=${offset}&limit=${limit}&sort=${state.sort}`;
  }

  async function loadImages() {
    if (state.loading) return;
    if (!state.currentAlbumId && !state.dateFilter) return;
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

  function createThumbCard(img) {
    const card = document.createElement("div");
    card.className = "thumb-card";
    card.dataset.id = img.id;

    const image = document.createElement("img");
    image.loading = "lazy";
    image.alt = img.name || "";
    image.width = 160;
    image.height = 160;
    image.src = `/api/images/${img.id}/thumb?size=320`;
    image.onerror = () => {
      image.style.background = "#333";
      image.alt = "No preview";
    };

    const meta = document.createElement("div");
    meta.className = "meta";
    meta.textContent = img.name || `#${img.id}`;

    card.appendChild(image);
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
  const exifDialog = $("#exif-dialog");
  const exifBody = $("#exif-dialog-body");
  const exifBackdrop = $("#exif-backdrop");
  const exifDialogClose = $("#exif-dialog-close");
  let lbCurrentId = null;
  let lbExifLoadedFor = null;

  function openLightbox(img) {
    lbCurrentId = img.id;
    lbExifLoadedFor = null;
    lbImg.src = `/api/images/${img.id}/file`;
    lbCaption.textContent = img.name || "";
    lightbox.hidden = false;
    closeExifDialog();
  }

  function closeLightbox() {
    lightbox.hidden = true;
    lbImg.src = "";
    lbCurrentId = null;
    closeExifDialog();
  }

  function openExifDialog() {
    if (!lbCurrentId) return;
    exifDialog.hidden = false;
    if (lbExifLoadedFor !== lbCurrentId) {
      loadExif(lbCurrentId);
    }
  }

  function closeExifDialog() {
    if (exifDialog) exifDialog.hidden = true;
  }

  async function loadExif(imageId) {
    exifBody.innerHTML = `<div class="loading">Loading…</div>`;
    try {
      const res = await fetch(`/api/images/${imageId}/exif`, { credentials: "same-origin" });
      if (res.status === 401) {
        window.location.href = "/login";
        return;
      }
      if (!res.ok) throw new Error("Failed to load metadata");
      const data = await res.json();
      lbExifLoadedFor = imageId;
      renderExif(data);
    } catch (err) {
      exifBody.innerHTML = `<div class="loading">Error: ${err.message}</div>`;
    }
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
    const geo = data.geo;
    if (!sections.length && !geo) {
      exifBody.innerHTML = `<div class="loading">No metadata in DigiKam database for this image.</div>`;
      return;
    }
    const frag = document.createDocumentFragment();

    if (geo && geo.lat != null && geo.lon != null) {
      const box = document.createElement("div");
      box.className = "lb-exif-section map-links-section";
      const h = document.createElement("h4");
      h.textContent = "Open in map";
      box.appendChild(h);

      const row = document.createElement("div");
      row.className = "map-links-row";

      const select = document.createElement("select");
      select.id = "map-provider-select";
      select.className = "map-provider-select";

      const openBtn = document.createElement("a");
      openBtn.className = "btn map-open-btn";
      openBtn.target = "_blank";
      openBtn.rel = "noopener noreferrer";
      openBtn.textContent = "Open";

      const updateHref = () => {
        const tpl = select.selectedOptions[0];
        const urlTpl = tpl ? tpl.dataset.url : "";
        openBtn.href = buildMapUrl(urlTpl, geo.lat, geo.lon, mapDefaultZoom);
      };

      ensureMapTemplates().then((templates) => {
        select.innerHTML = "";
        templates.forEach((t) => {
          const opt = document.createElement("option");
          opt.value = t.id;
          opt.textContent = t.name;
          opt.dataset.url = t.url;
          select.appendChild(opt);
        });
        updateHref();
      });

      select.addEventListener("change", updateHref);
      row.appendChild(select);
      row.appendChild(openBtn);

      const coords = document.createElement("div");
      coords.className = "map-coords muted";
      coords.textContent = `${Number(geo.lat).toFixed(6)}, ${Number(geo.lon).toFixed(6)}`;
      box.appendChild(row);
      box.appendChild(coords);
      frag.appendChild(box);
    }

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
    if (state.currentAlbumId || state.dateFilter) {
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

  // Boot
  const savedView = localStorage.getItem(LS_VIEW) || "albums";
  setView(savedView);
  loadAlbums();
  if (savedView === "dates") loadDates();
})();
