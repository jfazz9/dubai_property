from scripts.notifications import attention_beep


def test_attention_beep_can_be_disabled():
    assert attention_beep(enabled=False) is None
