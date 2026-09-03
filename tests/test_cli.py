from demo.cli import run_demo


def test_demo_full_purchase_with_explicit_token():
    out: list[str] = []
    inputs = iter(["CONFIRM mean I will answer", None])

    def fake_input(prompt=""):
        out.append(prompt)
        nxt = next(inputs)
        if nxt is None:
            raise RuntimeError("test must supply the token first")
        return nxt

    # First pass: capture the printed token, then confirm with it.
    transcript: list[str] = []

    def capture_print(*parts):
        transcript.append(" ".join(str(p) for p in parts))

    # Peek run: refuse once to learn the token, then confirm for real.
    first = run_demo(input_fn=fake_input, print_fn=capture_print)
    assert first["blocked_without_confirmation"] is True
    token_line = next(
        line for line in transcript if line.startswith("CONFIRMATION_TOKEN=")
    )
    token = token_line.split("=", 1)[1].strip()

    transcript2: list[str] = []
    second = run_demo(
        input_fn=lambda prompt="": token,
        print_fn=lambda *parts: transcript2.append(" ".join(str(p) for p in parts)),
    )
    assert second["order"]["status"] == "COMPLETED"
    assert second["order"]["order_id"].startswith("O-")
    assert second["repeat_order_same_id"] is True
