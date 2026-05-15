def attention_beep(enabled=True, repeats=3):
    if not enabled:
        return

    try:
        import winsound

        for _ in range(repeats):
            winsound.Beep(1200, 250)
            winsound.Beep(800, 250)
    except Exception:
        print("\a\a\a", end="", flush=True)
