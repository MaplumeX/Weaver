from agent.foundation.passages import split_into_passages


def test_split_into_passages_returns_offsets():
    text = "A" * 2000
    passages = split_into_passages(text, max_chars=500)
    assert passages
    assert passages[0]["start_char"] == 0
    assert passages[0]["end_char"] > passages[0]["start_char"]
