"""Catalogue generation helpers.

`fence_for` exists because of a bug whose symptom was a whole track vanishing from
the rendered catalogue while sitting perfectly intact in the source file. That is
the worst kind: the data was fine, the generator was fine in isolation, and the
only place it went wrong was the interaction between them.
"""

from __future__ import annotations

import pytest

from framework.forge import docs

TICK = chr(96)
F3 = TICK * 3
F4 = TICK * 4
F5 = TICK * 5


# --- fence_for --------------------------------------------------------------
#
# THE BUG: the lyrics block wrapped arbitrary file content in exactly three
# backticks. Five imported sheets carried a stray closing fence left over from
# their original harvest, so the inner fence closed the outer block early, the rest
# of the body escaped into the page as raw markdown, and the intended closer opened
# a block that never ended — swallowing every track after it.

def test_plain_body_gets_the_normal_fence():
    assert docs.fence_for("just some lyrics\nand more") == F3
    assert docs.fence_for("") == F3


def test_a_body_containing_a_fence_gets_a_longer_one():
    body = f"a line\n{F3}\nanother line"
    fence = docs.fence_for(body)
    assert fence == F4
    assert len(fence) > 3


def test_the_fence_outgrows_the_longest_one_inside():
    body = f"a\n{F3}\nb\n{F5}\nc\n{F4}\nd"
    assert docs.fence_for(body) == TICK * 6


def test_indented_fences_are_counted_too():
    """A fence indented in the source still closes a block when rendered."""
    body = f"a line\n   {F4}\nmore"
    assert docs.fence_for(body) == F5


def test_inline_code_does_not_inflate_the_fence():
    """A metadata line like `WH-002` starts with a backtick but is not a fence.

    Counting it would pad every block for no reason — and a probe that made this
    mistake reported healthy pages as unbalanced while chasing this very bug.
    """
    body = f"{TICK}WH-002{TICK} era pre-standard\nsome lyrics"
    assert docs.fence_for(body) == F3


@pytest.mark.parametrize("body", [
    "no fences at all",
    f"{F3}\ncontents\n{F3}",          # balanced pair inside
    f"trailing orphan\n{F3}",          # the real-world case: one stray closer
    f"{F3}\nunclosed opener",
])
def test_the_wrapped_block_always_survives_its_contents(body):
    """The invariant that matters: no line of the body can terminate the wrapper."""
    fence = docs.fence_for(body)
    for line in body.split("\n"):
        stripped = line.strip()
        if stripped.startswith(TICK * 3):
            run = len(stripped) - len(stripped.lstrip(TICK))
            assert run < len(fence), (
                f"a body fence of {run} backticks would close a wrapper of "
                f"{len(fence)}"
            )
