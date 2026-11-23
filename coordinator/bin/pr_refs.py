import re

PR_REF_WORDS = ("refs", "ref", "fixes", "fix", "fixed", "closes", "close", "closed",
                "resolves", "resolve", "resolved")
PR_REF_WORD = re.compile(r"(?i)\b(?:" + "|".join(PR_REF_WORDS) + r")\b")
PR_REF_NUMBER = re.compile(r"(?:([A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+))?#(\d+)")
# A reference verb names the numbers in reference position: the list opens
# right after the verb, and the numbers in it are separated by a comma, `and`
# or `&`, or by nothing but spaces. A verb inside prose names nothing, so
# `a defect fix. It belongs with the gallery ticket (#82)` is not a reference
# to #82.
PR_REF_OPEN = re.compile(r"^[ \t]*:?[ \t]*$")
PR_REF_SEPARATOR = re.compile(r"^[ \t]*(?:,[ \t]*(?:(?:and|&)[ \t]*)?|(?:and|&)[ \t]*)?$")
FENCED_BLOCK = re.compile(r"(?s)```.*?```")


def same_repo(named, repo):
    """True when two `owner/name` names point at the same repository."""
    if not named or not repo:
        return False
    return named.lower().split("/")[-2:] == repo.lower().split("/")[-2:]


def reference_numbers(line, start):
    """The numbers a reference verb ending at `start` names, in order.

    The first number must follow the verb directly, and each later number
    must follow a list separator, so a verb inside prose names nothing.
    """
    numbers = []
    position, gap_pattern = start, PR_REF_OPEN
    for token in PR_REF_NUMBER.finditer(line, start):
        if not gap_pattern.match(line[position:token.start()]):
            break
        numbers.append((token.group(1), int(token.group(2))))
        position, gap_pattern = token.end(), PR_REF_SEPARATOR
    return numbers


def line_references(line, quoted=False):
    """The (named_repo, number) pairs a line's reference verbs name, in order.

    A verb inside a qualified reference is part of the repository name, not a
    verb: `Refs other/fix#12` names #12 in `other/fix` only. With `quoted`, a
    verb that follows a quote or a backtick is quoted text, not a reference.
    """
    qualified = [token.span() for token in PR_REF_NUMBER.finditer(line)]
    for match in PR_REF_WORD.finditer(line):
        if any(start <= match.start() < end for start, end in qualified):
            continue
        if quoted and match.start() and line[match.start() - 1] in "'\"`":
            continue
        for named_repo, token_number in reference_numbers(line, match.end()):
            yield named_repo, token_number


def references_issue(body, number, repo=None):
    """True when the body references issue `number` with a reference keyword.

    The keyword carries the numbers that follow it in reference position, so
    `Refs #160, #161` names both, and `owner/name#160` names the issue only
    when the repository is the one in play. A verb inside prose names
    nothing: `a defect fix. It belongs with the gallery ticket (#82)` is not
    a reference to #82.
    """
    for line in (body or "").splitlines():
        for named_repo, token_number in line_references(line):
            if token_number != number:
                continue
            if named_repo and repo and not same_repo(named_repo, repo):
                continue
            return True
    return False


def pr_ticket_refs(title, body, repo=None):
    """The issue numbers a pull request's title and body reference, in order.

    Fenced blocks and inline code spans are not references, and neither is a
    verb in quoted text. A qualified reference counts only for the repository
    in play, so `other/name#12` is skipped when `repo` is given.
    """
    text = (title or "") + "\n" + (body or "")
    text = FENCED_BLOCK.sub(" ", text)
    text = re.sub(r"`[^`\n]*`", " ", text)
    refs = []
    for line in text.splitlines():
        for named_repo, token_number in line_references(line, quoted=True):
            if named_repo and (repo is None or not same_repo(named_repo, repo)):
                continue
            number = str(token_number)
            if number not in refs:
                refs.append(number)
    return refs
