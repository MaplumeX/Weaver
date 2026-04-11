from agent.foundation.passages import split_into_passages


def test_split_into_passages_returns_offsets():
    text = "A" * 2000
    passages = split_into_passages(text, max_chars=500)
    assert passages
    assert passages[0]["start_char"] == 0
    assert passages[0]["end_char"] > passages[0]["start_char"]


def test_split_into_passages_supports_overlap_offsets():
    text = "A" * 60
    passages = split_into_passages(text, max_chars=20, overlap_chars=5)

    assert len(passages) == 3
    assert passages[0]["start_char"] == 0
    assert passages[1]["start_char"] == 15
    assert passages[1]["text"] == text[15:40]
    assert passages[2]["start_char"] == 35
