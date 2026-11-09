/* Delivery Center Estimator map. Local MapLibre, no CDN scripts. */
(function () {
  const FALLBACK_STYLE = {
    version: 8,
    sources: {},
    layers: [{ id: "background", type: "background", paint: { "background-color": "#16181d" } }],
  };
  const COUNTIES = { "06081": "San Mateo County" };
  const TORNADO_LIMIT = 8;

  const panel = document.getElementById("panel");
  const panelBody = document.getElementById("panel-body");
  const searchForm = document.getElementById("search-form");
  const searchInput = document.getElementById("search");
  const searchResults = document.getElementById("search-results");
  const compareToggle = document.getElementById("compare-toggle");
  const tip = document.getElementById("hover-tip");
  const note = document.getElementById("basemap-note");

  let bridge = null;
  let map = null;
  let mapReady = false;
  let usingFallback = false;
  let overlaysAdded = false;
  let payload = null;
  let byZip = new Map();
  let request = 0;
  let compareOn = false;
  let currentZip = null;
  let slotA = null;
  let slotB = null;
  let shown = null;
  let cashLens = "standalone";
  let tornadoAll = false;
  let hovered = null;
  const touched = new Set();
  let readyResolve = function () {};
  const ready = new Promise(function (resolve) { readyResolve = resolve; });

  window.dce = {
    ready: ready,
    selectZip: selectZip,
    compareZips: compareZips,
  };

  boot();

  function boot() {
    waitForBridge().then(function (chosen) {
      bridge = chosen;
      return bridge.bootstrap();
    }).then(function (body) {
      if (!body || body.ok === false) {
        renderError("Map", (body && body.error && body.error.message) || "The map data did not load.");
        readyResolve();
        return;
      }
      payload = body;
      byZip = new Map((body.zip_index || []).map(function (row) { return [row.zip, row]; }));
      initMap(body);
      bindChrome();
      renderEmpty();
    }).catch(function () {
      renderError("Map", "The map data did not load.");
      readyResolve();
    });
  }

  function waitForBridge() {
    return new Promise(function (resolve) {
      let done = false;
      function finish(next) {
        if (!done && next) { done = true; resolve(next); }
      }
      window.addEventListener("pywebviewready", function () { finish(nativeBridge()); });
      finish(nativeBridge());
      setTimeout(function () { finish(nativeBridge() || httpBridge()); }, 200);
    });
  }

  function nativeBridge() {
    if (!window.pywebview || !window.pywebview.api) return null;
    const api = window.pywebview.api;
    return {
      bootstrap: function () { return api.bootstrap(); },
      get_result: function (zip) { return api.get_result(zip); },
      compare: function (a, b) { return api.compare(a, b); },
    };
  }

  function httpBridge() {
    return {
      bootstrap: function () { return getJSON("/api/bootstrap"); },
      get_result: function (zip) { return getJSON("/api/result/" + zip); },
      compare: function (a, b) { return getJSON("/api/compare/" + a + "/" + b); },
    };
  }

  function getJSON(url) {
    return fetch(url).then(function (response) {
      if (!response.ok) throw new Error("request failed");
      return response.json();
    });
  }

  function initMap(body) {
    map = new maplibregl.Map({
      container: "map",
      style: body.basemap_style || FALLBACK_STYLE,
      center: [-122.15, 37.55],
      zoom: 9,
      attributionControl: true,
      fadeDuration: 0,
    });
    map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-left");
    map.on("style.load", function () { addOverlays(body); });
    let sawTiles = false;
    map.on("error", function (event) {
      const message = String((event && event.error && event.error.message) || "");
      if (!overlaysAdded && /style/i.test(message)) useFallback(body);
    });
    map.on("data", function (event) {
      if (event.sourceId === "openmaptiles" && event.isSourceLoaded) {
        sawTiles = true;
        note.hidden = true;
      }
    });
    setTimeout(function () {
      if (!sawTiles) note.hidden = false;
    }, 2800);
    map.on("click", onMapClick);
  }

  function useFallback(body) {
    if (usingFallback) return;
    usingFallback = true;
    note.hidden = false;
    map.setStyle(FALLBACK_STYLE);
  }

  function addOverlays(body) {
    if (map.getSource("zcta")) return;
    map.addSource("zcta", { type: "geojson", data: body.zcta, promoteId: "zip" });
    map.addLayer({
      id: "zcta-fill",
      type: "fill",
      source: "zcta",
      paint: {
        "fill-color": [
          "case",
          ["boolean", ["feature-state", "selected"], false], "#9db7ff",
          ["boolean", ["feature-state", "compare"], false], "#f0d7a4",
          "#ffffff",
        ],
        "fill-opacity": [
          "case",
          ["boolean", ["feature-state", "selected"], false], 0.45,
          ["boolean", ["feature-state", "compare"], false], 0.4,
          ["boolean", ["feature-state", "hover"], false], 0.22,
          [">", ["coalesce", ["feature-state", "catchment"], 0], 0],
          ["interpolate", ["linear"], ["coalesce", ["feature-state", "catchment"], 0], 0, 0.08, 1, 0.42],
          0.05,
        ],
      },
    });
    map.addLayer({
      id: "zcta-line",
      type: "line",
      source: "zcta",
      paint: {
        "line-color": [
          "case",
          ["boolean", ["feature-state", "selected"], false], "#f4f7ff",
          ["boolean", ["feature-state", "compare"], false], "#f0d7a4",
          ["boolean", ["feature-state", "hover"], false], "#ffffff",
          "rgba(255,255,255,0.38)",
        ],
        "line-width": [
          "case",
          ["boolean", ["feature-state", "selected"], false], 2,
          ["boolean", ["feature-state", "hover"], false], 1.2,
          0.7,
        ],
      },
    });
    map.addSource("centers", {
      type: "geojson",
      data: {
        type: "FeatureCollection",
        features: (body.centers || []).map(function (center) {
          return {
            type: "Feature",
            properties: { name: center.name, city: center.city, location_type: center.location_type },
            geometry: { type: "Point", coordinates: [center.lon, center.lat] },
          };
        }),
      },
    });
    map.addLayer({
      id: "centers",
      type: "circle",
      source: "centers",
      paint: {
        "circle-radius": 5.5,
        "circle-color": "#f4f5f7",
        "circle-stroke-width": 2,
        "circle-stroke-color": "#121417",
      },
    });
    map.on("mousemove", "zcta-fill", onZipMove);
    map.on("mouseleave", "zcta-fill", onZipLeave);
    fitZipBounds();
    overlaysAdded = true;
    mapReady = true;
    readyResolve();
  }

  function fitZipBounds() {
    const bounds = new maplibregl.LngLatBounds();
    let any = false;
    byZip.forEach(function (row) {
      if (row.lat == null || row.lon == null) return;
      bounds.extend([row.lon, row.lat]);
      any = true;
    });
    if (!any) return;
    map.fitBounds(bounds, { padding: { top: 90, right: 430, bottom: 48, left: 48 }, duration: 0 });
  }

  function bindChrome() {
    searchInput.addEventListener("input", renderSearch);
    searchInput.addEventListener("keydown", function (event) {
      if (event.key === "Enter") {
        event.preventDefault();
        const zip = firstMatch() || cleanZip(searchInput.value);
        if (zip) chooseZip(zip);
      }
      if (event.key === "Escape") closeSearch();
    });
    searchForm.addEventListener("submit", function (event) {
      event.preventDefault();
      const zip = firstMatch() || cleanZip(searchInput.value);
      if (zip) chooseZip(zip);
    });
    document.addEventListener("keydown", function (event) {
      if (event.key === "/" && document.activeElement !== searchInput) {
        event.preventDefault();
        searchInput.focus();
      }
    });
    compareToggle.addEventListener("click", function () {
      compareOn = !compareOn;
      compareToggle.setAttribute("aria-pressed", compareOn ? "true" : "false");
      panel.classList.toggle("compare", compareOn);
      if (compareOn) {
        slotA = currentZip;
        slotB = null;
        if (slotA) refreshCompare();
        else renderPickTwo();
      } else if (currentZip) selectZip(currentZip);
      else renderEmpty();
    });
  }

  function chooseZip(zip) {
    closeSearch();
    searchInput.value = zip;
    if (compareOn) {
      if (!slotA) slotA = zip;
      else if (zip !== slotA) slotB = zip;
      refreshCompare();
    } else {
      selectZip(zip);
    }
  }

  function renderSearch() {
    const query = searchInput.value.trim();
    const matches = query ? matchesFor(query).slice(0, 6) : [];
    searchResults.innerHTML = "";
    if (!matches.length) { searchResults.hidden = true; return; }
    matches.forEach(function (zip) {
      const item = document.createElement("li");
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = zip;
      button.addEventListener("click", function () { chooseZip(zip); });
      item.appendChild(button);
      searchResults.appendChild(item);
    });
    searchResults.hidden = false;
  }

  function matchesFor(query) {
    const found = [];
    byZip.forEach(function (_row, zip) {
      if (zip.indexOf(query) === 0) found.push(zip);
    });
    found.sort();
    return found;
  }

  function firstMatch() {
    const matches = matchesFor(searchInput.value.trim());
    return matches.length ? matches[0] : null;
  }

  function closeSearch() { searchResults.hidden = true; }

  function cleanZip(value) {
    const text = String(value || "").trim();
    return /^\d{5}$/.test(text) ? text : null;
  }

  function selectZip(zip) {
    const mine = ++request;
    compareOn = false;
    compareToggle.setAttribute("aria-pressed", "false");
    panel.classList.remove("compare");
    currentZip = zip;
    slotA = zip;
    slotB = null;
    panel.dataset.state = "loading";
    panel.dataset.zip = zip;
    renderSkeleton(zip);
    focusZip(zip);
    paintSingle(zip, []);
    return bridge.get_result(zip).then(function (response) {
      if (mine !== request) return response;
      if (!response || response.ok === false) {
        renderError(zip, response && response.error && response.error.message);
        return response;
      }
      shown = response.result;
      cashLens = "standalone";
      tornadoAll = false;
      renderDashboard(shown);
      const zips = (shown.catchment && shown.catchment.gravity && shown.catchment.gravity.zips) || [];
      paintSingle(zip, zips);
      return response;
    }).catch(function () {
      if (mine === request) renderError(zip, "The estimate did not finish.");
    });
  }

  function compareZips(a, b) {
    compareOn = true;
    compareToggle.setAttribute("aria-pressed", "true");
    panel.classList.add("compare");
    slotA = a;
    slotB = b;
    currentZip = a;
    return refreshCompare();
  }

  function refreshCompare() {
    const mine = ++request;
    panel.dataset.state = "loading";
    if (!slotA || !slotB) {
      paintCompare(slotA, slotB);
      renderWaiting(slotA);
      return Promise.resolve(null);
    }
    renderSkeletonCompare(slotA, slotB);
    paintCompare(slotA, slotB);
    focusZip(slotA);
    return bridge.compare(slotA, slotB).then(function (response) {
      if (mine !== request) return response;
      if (!response || response.ok === false) {
        renderError(slotA + " / " + slotB, response && response.error && response.error.message);
        return response;
      }
      renderCompare(response);
      return response;
    }).catch(function () {
      if (mine === request) renderError(slotA + " / " + slotB, "The comparison did not finish.");
    });
  }

  function onMapClick(event) {
    if (!mapReady) return;
    const centerHits = map.queryRenderedFeatures(event.point, { layers: ["centers"] });
    if (centerHits.length) {
      const props = centerHits[0].properties || {};
      showTip(event.point, (props.name || "Center") + (props.city ? " · " + props.city : ""));
      return;
    }
    if (!map.getLayer("zcta-fill")) return;
    const hits = map.queryRenderedFeatures(event.point, { layers: ["zcta-fill"] });
    if (!hits.length) return;
    const zip = hits[0].properties && hits[0].properties.zip;
    if (!zip) return;
    if (compareOn) {
      if (!slotA) slotA = zip;
      else if (zip !== slotA) slotB = zip;
      refreshCompare();
    } else {
      selectZip(zip);
    }
  }

  function onZipMove(event) {
    if (!event.features || !event.features.length) return;
    map.getCanvas().style.cursor = "pointer";
    const zip = event.features[0].properties.zip;
    if (hovered && hovered !== zip) setState(hovered, { hover: false });
    hovered = zip;
    setState(zip, { hover: true });
    showTip(event.point, zip);
  }

  function onZipLeave() {
    map.getCanvas().style.cursor = "";
    if (hovered) setState(hovered, { hover: false });
    hovered = null;
    tip.hidden = true;
  }

  function showTip(point, text) {
    tip.hidden = false;
    tip.textContent = text;
    tip.style.left = (point.x + 14) + "px";
    tip.style.top = (point.y + 14) + "px";
  }

  function focusZip(zip) {
    const row = byZip.get(zip);
    if (!map || !row || row.lat == null) return;
    map.easeTo({ center: [row.lon, row.lat], zoom: Math.max(map.getZoom(), 10.2), duration: 450 });
  }

  function setState(zip, state) {
    if (!map || !mapReady || !byZip.has(zip)) return;
    touched.add(zip);
    map.setFeatureState({ source: "zcta", id: zip }, state);
  }

  function clearPaint() {
    touched.forEach(function (zip) {
      setState(zip, { selected: false, compare: false, catchment: 0, hover: false });
    });
    touched.clear();
  }

  function paintSingle(zip, catchment) {
    clearPaint();
    setState(zip, { selected: true });
    (catchment || []).forEach(function (row) {
      if (row.zip_code === zip) return;
      setState(row.zip_code, { catchment: row.share || 0 });
    });
  }

  function paintCompare(a, b) {
    clearPaint();
    if (a) setState(a, { selected: true });
    if (b) setState(b, { compare: true });
  }

  function renderEmpty() {
    panel.dataset.state = "empty";
    const samples = ["94402", "94401", "94403", "94404"].filter(function (zip) { return byZip.has(zip); });
    panelBody.innerHTML =
      '<p class="eyebrow">Public data only</p>' +
      "<h1>Where should the next center go?</h1>" +
      '<p class="lede">Pick a ZIP. Cost per delivery, the catchment, and a 10-year cash flow show up here.</p>' +
      '<div class="chips">' + samples.map(function (zip) {
        return '<button type="button" data-zip="' + zip + '">' + zip + "</button>";
      }).join("") + "</div>";
    panelBody.querySelectorAll("[data-zip]").forEach(function (button) {
      button.addEventListener("click", function () { selectZip(button.getAttribute("data-zip")); });
    });
  }

  function renderPickTwo() {
    panel.dataset.state = "empty";
    panelBody.innerHTML =
      '<p class="eyebrow">Compare</p><h1>Pick two ZIPs</h1>' +
      '<p class="lede">Click a ZIP, then another. The better value is marked on each row.</p>';
  }

  function renderWaiting(zip) {
    panel.dataset.state = "loading";
    panelBody.innerHTML =
      '<p class="eyebrow">Compare</p><h1>' + esc(zip || "") + "</h1>" +
      '<p class="lede">Click a second ZIP.</p>';
  }

  function renderSkeleton(zip) {
    panelBody.innerHTML =
      '<p class="eyebrow">Estimating</p><h1>' + esc(zip) + "</h1>" +
      skeletonBlocks();
  }

  function renderSkeletonCompare(a, b) {
    panelBody.innerHTML =
      '<p class="eyebrow">Comparing</p><h1>' + esc(a) + " and " + esc(b) + "</h1>" +
      skeletonBlocks();
  }

  function skeletonBlocks() {
    return '<div class="skel tall w70"></div><div class="skel w90"></div><div class="skel"></div><div class="skel w40"></div><p class="loading">Running the catchment and the cash flow.</p>';
  }

  function renderError(title, message) {
    panel.dataset.state = "error";
    panelBody.innerHTML =
      '<p class="eyebrow">Could not estimate</p><h1>' + esc(title) + "</h1>" +
      "<p class=\"lede\">" + esc(message || "Try another ZIP.") + "</p>";
  }

  function renderDashboard(result) {
    panel.dataset.state = "ready";
    panel.dataset.zip = result.zip_code;
    const geo = result.geo || {};
    const county = COUNTIES[geo.county_fips] || ("County " + (geo.county_fips || ""));
    const standalone = result.dcf.standalone;
    const incremental = result.dcf.incremental;
    const years = result.dcf[cashLens].years;
    panelBody.innerHTML =
      '<p class="eyebrow">' + esc(county) + ", " + esc(geo.state || "") + "</p>" +
      "<h1>" + esc(result.zip_code) + "</h1>" +
      '<div class="hero"><div><span class="hero-num">' + usd(result.cost_per_delivery) + '</span><span class="hero-label">per delivery</span></div>' +
      '<div><span class="hero-num">' + count(result.estimated_annual_deliveries) + '</span><span class="hero-label">deliveries / year</span></div></div>' +
      "<h2>Cost drivers</h2>" + driversHtml(result.drivers) +
      '<h2>Cash flow</h2><div class="lenses">' +
      lensHtml("Standalone", standalone) + lensHtml("Incremental", incremental) + "</div>" +
      "<h2>Low / base / high</h2><div class=\"scenarios\">" +
      scenarioHtml("Low", result.scenarios.low) +
      scenarioHtml("Base", result.scenarios.base) +
      scenarioHtml("High", result.scenarios.high) + "</div>" +
      "<h2>NPV tornado</h2>" + tornadoSvg(result.tornado) +
      '<p class="scenario-sub">Standalone NPV. One driver at a time, largest swing first.</p>' +
      "<h2>10-year cash flow</h2>" +
      '<div class="lens-switch">' +
      lensButton("standalone", "Standalone") + lensButton("incremental", "Incremental") +
      "</div>" + cashTable(years) +
      "<h2>Nearby centers</h2><ul class=\"centers\">" + centersHtml(result.nearby_centers) + "</ul>" +
      '<p><button type="button" id="compare-this" class="text-button">Compare this ZIP</button></p>';
    panelBody.querySelectorAll("[data-lens]").forEach(function (button) {
      button.addEventListener("click", function () {
        cashLens = button.getAttribute("data-lens");
        renderDashboard(shown);
      });
    });
    const more = panelBody.querySelector("[data-tornado]");
    if (more) more.addEventListener("click", function () { tornadoAll = !tornadoAll; renderDashboard(shown); });
    document.getElementById("compare-this").addEventListener("click", function () {
      compareOn = true;
      compareToggle.setAttribute("aria-pressed", "true");
      panel.classList.add("compare");
      slotA = result.zip_code;
      slotB = null;
      refreshCompare();
    });
  }

  function lensButton(id, label) {
    return '<button type="button" data-lens="' + id + '" aria-pressed="' + (cashLens === id ? "true" : "false") + '">' + label + "</button>";
  }

  function driversHtml(drivers) {
    return (drivers || []).slice(0, 3).map(function (driver) {
      const width = Math.max(2, Math.round((driver.share || 0) * 100));
      return '<div class="driver"><div class="driver-top"><span>' + esc(driver.label || driver.name) +
        "</span><span>" + money(driver.usd) + " · " + Math.round((driver.share || 0) * 100) +
        '%</span></div><div class="track"><i style="width:' + width + '%"></i></div></div>';
    }).join("");
  }

  function lensHtml(title, lens) {
    return '<section class="lens"><h3>' + title + '</h3><p class="big">' + money(lens.npv) +
      '</p><p class="scenario-sub">' + pct(lens.irr) + " IRR</p><p class=\"scenario-sub\">" +
      years(lens.simple_payback_years) + " simple · " + years(lens.discounted_payback_years) +
      " discounted</p></section>";
  }

  function scenarioHtml(title, card) {
    if (!card) return "";
    return '<article class="scenario ' + esc(card.scenario_id) + '"><h3>' + title +
      '</h3><p class="scenario-npv">' + money(card.standalone.npv) +
      '</p><p class="scenario-sub">' + usd(card.cost_per_delivery) + " / delivery</p>" +
      '<p class="scenario-sub">' + pct(card.standalone.irr) + " IRR</p></article>";
  }

  function tornadoSvg(bars) {
    const all = bars || [];
    const rows = tornadoAll ? all : all.slice(0, TORNADO_LIMIT);
    if (!rows.length) return "";
    const values = [];
    all.forEach(function (bar) { values.push(bar.npv_low, bar.npv_high, bar.npv_base); });
    const min = Math.min.apply(null, values);
    const max = Math.max.apply(null, values);
    const span = max - min || 1;
    const width = 360;
    const labelW = 118;
    const rowH = 22;
    const plotW = width - labelW - 8;
    function x(value) { return labelW + ((value - min) / span) * plotW; }
    const base = rows[0].npv_base;
    let body = "";
    rows.forEach(function (bar, index) {
      const y = index * rowH + 4;
      const x0 = x(Math.min(bar.npv_low, base));
      const x1 = x(base);
      const x2 = x(Math.max(bar.npv_high, base));
      body += '<text x="0" y="' + (y + 12) + '">' + esc(bar.label || bar.driver) + "</text>";
      body += '<rect class="bar-low" x="' + x0 + '" y="' + y + '" width="' + Math.max(1, x1 - x0) + '" height="12"></rect>';
      body += '<rect class="bar-high" x="' + x1 + '" y="' + y + '" width="' + Math.max(1, x2 - x1) + '" height="12"></rect>';
    });
    body += '<line class="bar-base" x1="' + x(base) + '" x2="' + x(base) + '" y1="0" y2="' + (rows.length * rowH) + '"></line>';
    const extra = all.length > TORNADO_LIMIT
      ? '<p><button type="button" class="text-button" data-tornado="1">' +
        (tornadoAll ? "Show the largest swings" : "Show all " + all.length + " drivers") + "</button></p>"
      : "";
    return '<svg class="tornado" viewBox="0 0 ' + width + " " + (rows.length * rowH + 4) + '" role="img" aria-label="NPV tornado">' +
      body + "</svg>" + extra;
  }

  function cashTable(rows) {
    const body = (rows || []).map(function (row) {
      return "<tr><td>" + row.year + "</td><td>" + count(row.deliveries) + "</td><td>" +
        money(row.benefit) + "</td><td>" + money(row.opex) + '</td><td class="' +
        (row.fcf < 0 ? "neg" : "") + '">' + money(row.fcf) + "</td><td>" + money(row.cumulative_fcf) + "</td></tr>";
    }).join("");
    return '<div class="table-wrap"><table><thead><tr><th>Year</th><th>Deliveries</th><th>Benefit</th><th>OpEx</th><th>FCF</th><th>Cumulative</th></tr></thead><tbody>' +
      body + "</tbody></table></div>";
  }

  function centersHtml(centers) {
    return (centers || []).map(function (center) {
      const taken = center.deliveries_taken == null ? "" : count(center.deliveries_taken) + " / yr taken";
      return '<li class="center-row"><span>' + esc(center.name) + "<br><small>" + esc(center.city || "") +
        "</small></span><span>" + Number(center.distance_miles).toFixed(1) + " mi<br><small>" + taken + "</small></span></li>";
    }).join("");
  }

  function renderCompare(response) {
    panel.dataset.state = "ready";
    panel.dataset.zip = response.a.zip_code + "-" + response.b.zip_code;
    const head =
      '<div class="metric head"><span class="label">Metric</span><span class="value">' +
      esc(response.a.zip_code) + '</span><span class="value">' + esc(response.b.zip_code) + "</span></div>";
    const rows = (response.metrics || []).map(function (metric) {
      return '<div class="metric"><span class="label">' + esc(metric.label) + "</span>" +
        cell(metric, "a") + cell(metric, "b") + "</div>";
    }).join("");
    panelBody.innerHTML =
      '<p class="eyebrow">Compare</p><h1>' + esc(response.a.zip_code) + " vs " + esc(response.b.zip_code) +
      "</h1><p class=\"lede\">The marked value is the better one. Lower cost and faster payback win. Higher NPV, IRR, and volume win.</p>" +
      head + rows;
  }

  function cell(metric, side) {
    const winner = metric.winner === side ? "better" : (metric.winner === "tie" ? "" : "dim");
    return '<span class="value ' + winner + '">' + formatMetric(metric[side], metric.format) + "</span>";
  }

  function formatMetric(value, format) {
    if (format === "count") return count(value);
    if (format === "ratio") return pct(value);
    if (format === "years") return years(value);
    return money(value);
  }

  function money(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    const number = Number(value);
    const sign = number < 0 ? "−" : "";
    const abs = Math.abs(number);
    if (abs >= 1000000) return sign + "$" + (abs / 1000000).toFixed(2) + "M";
    return sign + "$" + Math.round(abs).toLocaleString("en-US");
  }

  function usd(value) { return money(value); }

  function count(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return Math.round(Number(value)).toLocaleString("en-US");
  }

  function pct(value) {
    if (value == null || Number.isNaN(Number(value))) return "—";
    return (Number(value) * 100).toFixed(1) + "%";
  }

  function years(value) {
    if (value == null || Number.isNaN(Number(value))) return "Never";
    return Number(value).toFixed(2) + " yr";
  }

  function esc(value) {
    return String(value == null ? "" : value).replace(/[&<>"']/g, function (char) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[char];
    });
  }
})();
