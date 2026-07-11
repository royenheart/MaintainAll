from __future__ import annotations

from MaintainAll.tui.panes import ThinkingBlock, ThinkingBodyScroll


def test_thinking_block_keeps_brackets_in_buffer():
    """LLM streams often contain JSON/markdown ``[…]``; buffer must keep growing."""
    block = ThinkingBlock(phase="assess", block_id="t1")
    block.append_text("hello ")
    block.append_text('["ok"]')
    block.append_text(" world")
    assert block._body_text == 'hello ["ok"] world'
    block.finish()
    assert block._body_text == 'hello ["ok"] world'
    assert block._finished is True


def test_thinking_block_compose_uses_scroll_static():
    block = ThinkingBlock(phase="react", block_id="t2")
    children = list(block.compose())
    assert len(children) == 2
    body = children[1]
    assert isinstance(body, ThinkingBodyScroll)
    # Must not override watch_scroll_y — that breaks the scrollbar thumb.
    assert "watch_scroll_y" not in ThinkingBodyScroll.__dict__
    assert "watch_scroll_y" not in __import__(
        "MaintainAll.tui.panes", fromlist=["ChatStream"]
    ).ChatStream.__dict__
