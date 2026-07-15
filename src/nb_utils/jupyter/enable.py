def enable():
    from IPython import get_ipython

    ipy = get_ipython()
    if ipy is None:
        return  # обычный python-скрипт: магики и itables не нужны

    try:
        from nb_utils.jupyter.magics import register_magics
        register_magics()
    except Exception as e:
        print(f"⚠️ nb_utils: не удалось зарегистрировать магики: {e!r}")

    # itables рендерит HTML — включаем только в notebook-ядре, не в консольном IPython
    if type(ipy).__name__ != "ZMQInteractiveShell":
        return
    try:
        import itables
        itables.init_notebook_mode(all_interactive=True)
    except Exception as e:
        print(f"⚠️ nb_utils: не удалось включить itables: {e!r}")
