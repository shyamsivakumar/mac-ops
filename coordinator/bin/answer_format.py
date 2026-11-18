"""The answer format for a question to Shyam, so the text lives only once.

The board's Needs-you cards turn this format into buttons, so the builder,
the reviewer and the gate brief all carry the same wording.
"""

ANSWER_FORMAT = (
    "When a turn ends by asking Shyam a question, put the question on one line, "
    "then 2 to 4 options as lines `1. <option>`, `2. <option>` and so on, and "
    "end with the line `(Recommended: <option text word for word>)`."
)
