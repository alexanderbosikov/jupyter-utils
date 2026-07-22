from IPython.display import HTML, display

# Шрифт как у контента ноутбука (переменные темы JupyterLab, наследуются в экспорт).
_FONT = ("font-family: var(--jp-content-font-family, system-ui, sans-serif); "
         "font-size: var(--jp-content-font-size1, 14px);")

# Кнопка-переключатель кода (как в R Markdown). Inline-обработчики работают только при
# экспорте с отключённым sanitize (иначе JupyterLab вырежет <script>/onclick).
_CODE_TOGGLE_HTML = (
    '<button class="report-code-toggle" '
    "onclick=\"var h=document.body.classList.toggle('hide-code');"
    "this.textContent=h?'Показать код':'Скрыть код';\">Скрыть код</button>"
)

# Боковое оглавление: строится из заголовков markdown деревом по уровням; у веток с детьми
# каретка сворачивает/разворачивает вложенные пункты (в сайдбаре, не в теле ноутбука).
# Только в экспорте (body.jp-Notebook); в живом Lab body без этого класса — ничего не делает.
_TOC_JS = """
<script>
(function(){
  function build(){
    var body = document.body;
    if (!body.classList.contains('jp-Notebook')) return;
    if (document.querySelector('.report-toc')) return;
    var heads = document.querySelectorAll('.jp-MarkdownCell h1, .jp-MarkdownCell h2, .jp-MarkdownCell h3');
    if (!heads.length) return;

    // построить дерево по уровням заголовков
    var root = {children: [], level: 0};
    var stack = [root];
    heads.forEach(function(h, i){
      if (!h.id) h.id = 'report-toc-' + i;
      var lvl = parseInt(h.tagName[1], 10);
      var node = {h: h, level: lvl, children: []};
      while (stack.length > 1 && stack[stack.length - 1].level >= lvl) stack.pop();
      stack[stack.length - 1].children.push(node);
      stack.push(node);
    });

    function renderList(nodes){
      var ul = document.createElement('ul');
      nodes.forEach(function(n){
        var li = document.createElement('li');
        var row = document.createElement('div');
        row.className = 'toc-row';
        var caret = document.createElement('span');
        caret.className = 'toc-caret';
        if (n.children.length){
          caret.textContent = '▾';
          caret.addEventListener('click', function(e){
            e.stopPropagation();
            var c = li.classList.toggle('collapsed');
            caret.textContent = c ? '▸' : '▾';
          });
        } else {
          caret.classList.add('toc-caret-empty');
        }
        row.appendChild(caret);
        var a = document.createElement('a');
        a.href = '#' + n.h.id;
        a.textContent = n.h.textContent.replace(/\\u00b6$/, '').trim();
        row.appendChild(a);
        li.appendChild(row);
        if (n.children.length) li.appendChild(renderList(n.children));
        ul.appendChild(li);
      });
      return ul;
    }

    var nav = document.createElement('nav');
    nav.className = 'report-toc';
    nav.appendChild(renderList(root.children));
    body.appendChild(nav);

    var btn = document.createElement('button');
    btn.className = 'report-toc-toggle';
    btn.type = 'button';
    btn.textContent = '☰';
    btn.addEventListener('click', function(){
      var open = body.classList.toggle('toc-open');
      btn.textContent = open ? '✕' : '☰';
    });
    body.appendChild(btn);
    body.classList.add('toc-open');
  }
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', build);
  else build();
})();
</script>
"""


def _report_css(max_width="60rem", center=True, avoid_breaks=True, padding="2rem 1.5rem",
                wide_plots=True, code_toggle=True, toc=True):
    col = []
    if max_width:
        col.append(f"max-width: {max_width};")
    if center:
        col.append("margin-left: auto; margin-right: auto;")
    col_rules = " ".join(col)

    if wide_plots:
        # тело на всю ширину; колонка — только на текст/код/табличные выводы, а графики
        # (вывод с <img>) занимают всю ширину. Центрирование естественное, без breakout-хака.
        css = f"body.jp-Notebook {{ padding: {padding}; }}\n" if padding else ""
        css += (
            "body.jp-Notebook .jp-MarkdownCell, "
            "body.jp-Notebook .jp-Cell-inputWrapper, "
            f"body.jp-Notebook .jp-OutputArea-child:not(:has(img)) {{ {col_rules} }}\n"
        )
        css += "body.jp-Notebook .jp-OutputArea-child:has(img) { max-width: none; }\n"
        css += (
            "body.jp-Notebook .jp-OutputArea-child img { display: block; "
            "margin-left: auto; margin-right: auto; max-width: 100%; height: auto; }\n"
        )
    else:
        col2 = list(col)
        if padding:
            col2.append(f"padding: {padding};")
        css = f"body.jp-Notebook {{ {' '.join(col2)} }}\n"
        css += "body.jp-Notebook img { max-width: 100%; height: auto; }\n"

    # убираем gutter от In[]/Out[]-подписей: чище для отчёта и не сбивает центрирование
    css += (
        "body.jp-Notebook .jp-InputPrompt, "
        "body.jp-Notebook .jp-OutputPrompt { display: none; }\n"
    )

    if code_toggle:
        css += (
            "button.report-code-toggle { display: none; }\n"
            "body.jp-Notebook button.report-code-toggle { display: inline-block; "
            "position: fixed; top: 1rem; right: 1rem; z-index: 999; padding: .4rem .8rem; "
            f"{_FONT} cursor: pointer; background: #f5f5f5; color: #333; "
            "border: 1px solid #ccc; border-radius: 6px; }\n"
            "body.jp-Notebook.hide-code .jp-CodeCell .jp-Cell-inputWrapper { display: none; }\n"
        )

    if toc:
        # сайдбар сдвигает контент через padding-left тела → графики (max-width:100%)
        # ужимаются автоматически. По умолчанию открыт, сворачивается в бургер.
        # Внутри — дерево заголовков со сворачиваемыми ветками (каретка ▾/▸).
        css += (
            "body.jp-Notebook .report-toc { position: fixed; top: 0; left: 0; width: 16rem; "
            "height: 100vh; overflow-y: auto; box-sizing: border-box; padding: 3.5rem 1rem 1rem; "
            f"{_FONT} background: #fafafa; border-right: 1px solid #ddd; z-index: 1000; "
            "transform: translateX(-100%); transition: transform .2s ease; }\n"
            "body.jp-Notebook.toc-open .report-toc { transform: translateX(0); }\n"
            "body.jp-Notebook.toc-open { padding-left: calc(16rem + 2rem); }\n"
            "body.jp-Notebook .report-toc ul { list-style: none; margin: 0; padding: 0; }\n"
            "body.jp-Notebook .report-toc ul ul { padding-left: .9rem; }\n"
            "body.jp-Notebook .report-toc li.collapsed > ul { display: none; }\n"
            "body.jp-Notebook .report-toc .toc-row { display: flex; align-items: baseline; }\n"
            "body.jp-Notebook .report-toc .toc-caret { flex: 0 0 1em; width: 1em; cursor: pointer; "
            "color: #999; font-size: .8em; user-select: none; }\n"
            "body.jp-Notebook .report-toc .toc-caret-empty { cursor: default; }\n"
            "body.jp-Notebook .report-toc a { display: block; padding: .2rem 0; color: #333; "
            "text-decoration: none; }\n"
            "body.jp-Notebook .report-toc a:hover { color: #06c; }\n"
            "button.report-toc-toggle { display: none; }\n"
            "body.jp-Notebook button.report-toc-toggle { display: inline-block; position: fixed; "
            "top: 1rem; left: 1rem; z-index: 1001; width: 2rem; height: 2rem; line-height: 1; "
            f"{_FONT} cursor: pointer; background: #f5f5f5; color: #333; "
            "border: 1px solid #ccc; border-radius: 6px; }\n"
            "body.jp-Notebook { scroll-behavior: smooth; }\n"
            "@media print { body.jp-Notebook .report-toc, body.jp-Notebook .report-toc-toggle "
            "{ display: none; } body.jp-Notebook.toc-open { padding-left: 0; } }\n"
        )

    if avoid_breaks:
        css += (
            "@media print { body.jp-Notebook :is(.jp-Cell, .jp-OutputArea-child, "
            "table, pre, img) { break-inside: avoid; page-break-inside: avoid; } }\n"
        )
    return css


def report_style(max_width="60rem", center=True, avoid_breaks=True, padding="2rem 1.5rem",
                 wide_plots=True, code_toggle=True, toc=True):
    """Оформление ноутбука для HTML/PDF-экспорта: колонка контента + опции.

    Отображает <style>/<script>/кнопки сразу как side effect (через display), поэтому вызов
    можно ставить в любом месте ячейки. Селектор `body.jp-Notebook` применяет всё ТОЛЬКО к
    экспорту nbconvert (HTML/WebPDF): там body получает класс jp-Notebook, а в живом
    JupyterLab этого класса на body нет — вид рабочего ноутбука не меняется.

    ВАЖНО: экспортируй через File → Save and Export As → HTML с «Disable sanitize», иначе
    JupyterLab вырежет <style>/<script>/кнопки из вывода.

    - max_width: ширина колонки текста/кода/таблиц (None — не ограничивать).
    - center: центрировать колонку.
    - wide_plots: графики (вывод с <img>) на всю ширину контент-области.
    - code_toggle: кнопка справа сверху — скрыть/показать весь код (как в R Markdown).
    - toc: боковое оглавление из заголовков markdown в виде дерева; каретки ▾/▸ сворачивают
      ветки, бургер слева сворачивает сайдбар (при показе он ужимает контент). Только в HTML.
    - avoid_breaks: в PDF не рвать ячейки/таблицы/код/картинки между страницами.
    - padding: внутренние отступы контента.

    Шрифт кнопок/оглавления берётся из --jp-content-font-* (совпадает с текстом ноутбука).
    """
    css = _report_css(max_width, center, avoid_breaks, padding, wide_plots, code_toggle, toc)
    html = f"<style>\n{css}</style>"
    if code_toggle:
        html += _CODE_TOGGLE_HTML
    if toc:
        html += _TOC_JS
    display(HTML(html))
