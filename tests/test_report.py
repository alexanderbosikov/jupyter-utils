from nb_utils.report import _report_css


def test_scoped_to_export_only():
    css = _report_css()
    # селектор только для экспорта nbconvert, не для живого Lab
    assert "body.jp-Notebook" in css
    assert "max-width: 60rem" in css
    assert "margin-left: auto" in css


def test_max_width_none_omits_column_width():
    css = _report_css(max_width=None)
    assert "max-width: 60rem" not in css


def test_center_and_breaks_toggle():
    # в не-wide режиме центрирование колонки = margin на самом теле
    css = _report_css(center=False, avoid_breaks=False, wide_plots=False)
    assert "margin-left: auto" not in css
    assert "break-inside" not in css


def test_wide_plots_full_width():
    # графики (вывод с img) вне колонки, таблицы (без img) — в колонке
    css = _report_css(wide_plots=True)
    assert ":has(img) { max-width: none" in css
    assert ":not(:has(img))" in css

    off = _report_css(wide_plots=False)
    assert ":has(img)" not in off
    # без wide_plots ширина навешивается на само тело
    assert "body.jp-Notebook { max-width: 60rem" in off


def test_code_toggle_css():
    css = _report_css(code_toggle=True)
    assert "hide-code" in css and "report-code-toggle" in css
    assert "hide-code" not in _report_css(code_toggle=False)


def test_toc_css():
    css = _report_css(toc=True)
    assert ".report-toc" in css and "toc-open" in css
    # сайдбар сдвигает контент через padding-left тела
    assert "padding-left: calc(16rem" in css
    # дерево со сворачиваемыми ветками
    assert "toc-caret" in css and "li.collapsed > ul" in css
    assert ".report-toc" not in _report_css(toc=False)


def test_report_style_includes_toc_script(monkeypatch):
    import nb_utils.report as r
    shown = []
    monkeypatch.setattr(r, "display", lambda obj: shown.append(obj.data))
    r.report_style(toc=True)
    # дерево оглавления строится JS'ом с каретками
    assert "report-toc" in shown[0] and "<script>" in shown[0] and "renderList" in shown[0]
    shown.clear()
    r.report_style(toc=False)
    assert "<script>" not in shown[0]


def test_fonts_use_jp_variables():
    css = _report_css(toc=True, code_toggle=True)
    # инъектированные блоки берут шрифт из переменных темы ноутбука
    assert "--jp-content-font-family" in css
    assert "--jp-content-font-size1" in css


def test_report_style_includes_button(monkeypatch):
    import nb_utils.report as r
    shown = []
    monkeypatch.setattr(r, "display", lambda obj: shown.append(obj.data))
    r.report_style(code_toggle=True)
    assert "report-code-toggle" in shown[0] and "<button" in shown[0]
    shown.clear()
    r.report_style(code_toggle=False)
    assert "<button" not in shown[0]
