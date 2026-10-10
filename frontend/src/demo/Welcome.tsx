import { Binoculars, Flask, Notebook as NotebookIcon, UserCircle, X } from "@phosphor-icons/react";
import { motion, useReducedMotion } from "motion/react";
import { useState } from "react";
import { viewHref } from "../lib/route";
import { Button, IconButton } from "../components/ui";

const KEY = "smallville-demo-welcome";

function seen(): boolean {
  try {
    return window.localStorage.getItem(KEY) === "1";
  } catch {
    return false;
  }
}

/** A first look at what the recording is and what to try. Shown until dismissed. */
export function Welcome() {
  const [open, setOpen] = useState(() => !seen());
  const reduce = useReducedMotion();
  if (!open) return null;
  const close = () => {
    setOpen(false);
    try {
      window.localStorage.setItem(KEY, "1");
    } catch {
      /* private window: show it again next time */
    }
  };
  const tips = [
    { icon: UserCircle, text: "Click a resident to see what they are doing, their plan for the day and what they wish for." },
    { icon: NotebookIcon, text: "Press N for the notebook: requests, collected motifs, residents and the Town Pulse." },
    { icon: Binoculars, text: "Press L to look around, or use the moments above the town to jump to a chat, a gift or a build." },
    { icon: Flask, text: "Open the Research Inspector for memories, retrieval scores, plans, reflections and every model call." },
  ];
  return (
    <motion.section
      initial={reduce ? false : { y: 16, opacity: 0 }}
      animate={{ y: 0, opacity: 1 }}
      className="pointer-events-auto panel absolute inset-x-3 bottom-3 p-4 sm:inset-x-auto sm:bottom-20 sm:left-4 sm:w-[380px]"
      aria-labelledby="welcome-title"
    >
      <div className="flex items-start gap-2">
        <h2 id="welcome-title" className="flex-1 font-display text-lg font-bold leading-snug">
          A recorded morning in Smallville
        </h2>
        <IconButton label="Close" icon={X} onClick={close} className="size-9" />
      </div>
      <p className="mt-1 text-sm text-[var(--muted)]">
        Three residents live their day from 7 AM to 1 PM while a player chats, gives a gift, builds in the Town Square and grants a wish. It was recorded with the mock model and plays back here
        without any server or model.
      </p>
      <ul className="mt-3 space-y-2">
        {tips.map(({ icon: Icon, text }) => (
          <li key={text} className="flex gap-2.5 text-sm">
            <Icon size={20} weight="fill" color="#f2792b" aria-hidden="true" className="mt-0.5 shrink-0" />
            <span>{text}</span>
          </li>
        ))}
      </ul>
      <div className="mt-4 flex flex-wrap items-center gap-2">
        <Button tone="primary" onClick={close}>
          Start Exploring
        </Button>
        <a href={viewHref("inspector")} className="inline-flex min-h-10 items-center rounded-full px-4 font-display text-[15px] font-semibold transition-colors hover:bg-[var(--panel-2)]">
          Open the Inspector
        </a>
      </div>
      <p className="mt-3 text-xs text-[var(--muted)]">
        To play it yourself, with a free local model:{" "}
        <code className="rounded bg-[var(--panel-2)] px-1" translate="no">
          ga play --config configs/town_ollama.yaml
        </code>
      </p>
    </motion.section>
  );
}
