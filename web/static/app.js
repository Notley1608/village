(function () {
  "use strict";

  /* ----- toast flash messages ----- */
  var toasts = document.querySelector(".toasts");
  if (toasts) {
    var items = toasts.querySelectorAll(".toast");
    items.forEach(function (t, i) {
      setTimeout(function () {
        t.classList.add("hide");
        setTimeout(function () { t.remove(); }, 300);
      }, 3600 + i * 200);
    });
  }

  /* ----- inline confirm hooks ------ */
  document.querySelectorAll("form[data-confirm]").forEach(function (f) {
    f.addEventListener("submit", function (e) {
      if (!window.confirm(f.getAttribute("data-confirm"))) e.preventDefault();
    });
  });

  /* ----- small markdown renderer (safe subset) ----- */
  function esc(s) {
    return s
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function inline(s) {
    return s
      .replace(/`([^`]+)`/g, "<code>$1</code>")
      .replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>")
      .replace(/\*([^*]+)\*/g, "<em>$1</em>")
      .replace(/\[([^\]]+)\]\((https?:\/\/[^)\s]+)\)/g, '<a href="$2" rel="noopener noreferrer" target="_blank">$1</a>');
  }

  function renderMD(md) {
    var lines = md.replace(/\r\n?/g, "\n").split("\n");
    var html = [], i = 0, list = null;

    function closeList() {
      if (list) { html.push(list === "ul" ? "</ul>" : "</ol>"); list = null; }
    }
    function pushParagraph(body) {
      if (/<ul>|<ol>/.test(body) || html.length && html[html.length - 1].indexOf("<li>") !== -1) {
        html.push(body);
        return;
      }
      html.push("<p>" + body + "</p>");
    }

    while (i < lines.length) {
      var line = lines[i].trim();
      if (!line) { i++; closeList(); continue; }

      var h = line.match(/^(#{1,3})\s+(.*)$/);
      if (h) { closeList(); html.push("<h" + h[1].length + ">" + inline(esc(h[2])) + "</h" + h[1].length + ">"); i++; continue; }

      if (line === "---") { closeList(); html.push("<hr>"); i++; continue; }

      var ul = line.match(/^[-*]\s+(.*)$/);
      var ol = line.match(/^\d+\.\s+(.*)$/);
      if (ul || ol) {
        var kind = ul ? "ul" : "ol";
        if (list !== kind) { closeList(); list = kind; html.push(list === "ul" ? "<ul>" : "<ol>"); }
        html.push("<li>" + inline(esc((ul || ol)[1])) + "</li>");
        i++; continue;
      }
      closeList();
      pushParagraph(inline(esc(line)));
      i++;
    }
    closeList();
    return html.join("\n");
  }

  /* ----- draft editor tabs ----- */
  document.querySelectorAll("[data-editor]").forEach(function (editor) {
    var source = editor.querySelector("textarea.source");
    var preview = editor.querySelector(".preview");
    var tabs = editor.querySelectorAll(".tab");

    tabs.forEach(function (tab) {
      tab.addEventListener("click", function () {
        tabs.forEach(function (t) { t.classList.remove("active"); });
        tab.classList.add("active");
        var pane = source.closest(".pane");
        var isEdit = tab.getAttribute("data-tab") === "edit";
        source.closest(".pane").style.display = isEdit ? "" : "none";
        preview.closest(".pane").style.display = isEdit ? "none" : "";
        if (!isEdit) preview.innerHTML = renderMD(source.value || "");
      });
    });
  });
})();