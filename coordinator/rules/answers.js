// The rules that bind an answer to the alarm it was given for.
//
// The panel is a Herdr mod, which a test cannot import, so the rules live
// here in a module with no imports: the panel uses it, and a probe runs
// it. An answer that was never bound to a cause acknowledges nothing, so
// an alarm that Shyam never answered is never silenced.
//
// A "cause" is the alarm's cause as the board showed it when the answer
// was started. A "shown" cause is the one the board shows now.

/** Return the cause an answer carries: the one it was bound to, or none. */
export const answerCause = (draft, shown) => (draft?.cause ?? "");

/** Return True when an answer must be dropped before it is sent.

    An answer for a keyed alarm (one that shows a cause) must be bound to
    the cause it was given for. An answer that was never bound, or that
    was bound to another cause, belongs to an alarm that is not the one
    on the board now, so it is dropped rather than sent. */
export const isStale = (draft, shown) => Boolean(shown) && (!draft?.cause || draft.cause !== shown);

/** Return the text and the cause a reopened reply carries.

    The text and the cause are restored together. A draft with text but
    no cause, and typing text whose cause was not kept, cannot be bound
    to the alarm that is on the board now, so their text is not restored
    and the reply starts empty against the cause the panel shows. */
export const restored = (draft, typed, saved, shown) => {
  let text = typed ?? (draft?.kind === "reply" ? draft.text : "");
  let bound = shown;
  if (draft?.kind === "reply") {
    if (draft.cause) {
      bound = draft.cause;
    } else if (shown) {
      // A keyed alarm with a draft that carries no cause: the text
      // cannot be bound to the alarm that is on the board now, so it is
      // not restored. An ordinary decision has no cause and keeps its
      // text.
      text = "";
    }
  } else if (typed !== undefined) {
    if (saved === undefined) {
      if (shown) {
        // Typing text whose cause was not kept cannot be bound to the
        // alarm that is on the board now, so it is not restored. An
        // ordinary decision has no cause and keeps its text.
        text = "";
      }
    } else {
      bound = saved;
    }
  }
  return { text, bound };
};

export const decisionLine = ({ id, q, text }) => `- ${id} (${q}): ${text.replace(/\s+/g, " ").trim()}`;

export const decisionsMessage = (answers) => `Decisions:\n${answers.map(decisionLine).join("\n")}`;

export const boardAnswer = (id, request, items, decided) => {
  const ask = items.find((a) => a.id === id);
  if (!ask) return { dropped: "The decision is gone." };
  if (decided[id]) return { dropped: "The decision was already answered." };
  if (request.title !== ask.text || (request.cause ?? "") !== ask.cause) return { dropped: "The decision changed after the card showed it." };
  const choice = ask.choices.find((c) => c.kind === "option" && c.text === request.label);
  if (!choice) return { dropped: "The decision no longer offers that option." };
  return { answer: { id, q: ask.text, cause: ask.cause, text: choice.text } };
};
