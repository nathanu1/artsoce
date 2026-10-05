import { useEffect, useRef, type KeyboardEvent } from "react";

export interface TabItem<T extends string> {
  id: T;
  label: string;
}

/** Tabs with roving focus (arrow keys, Home and End) that control one tab panel. */
export function TabList<T extends string>({
  items,
  value,
  onChange,
  idPrefix,
  label,
  className = "",
  tabClassName,
  focusOnMount = false,
}: {
  items: TabItem<T>[];
  value: T;
  onChange: (id: T) => void;
  idPrefix: string;
  label: string;
  className?: string;
  tabClassName: (selected: boolean) => string;
  focusOnMount?: boolean;
}) {
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  useEffect(() => {
    if (focusOnMount) refs.current[items.findIndex((t) => t.id === value)]?.focus();
  }, []); // only when the list first appears
  const onKey = (e: KeyboardEvent, i: number) => {
    let j = -1;
    if (e.key === "ArrowRight") j = (i + 1) % items.length;
    else if (e.key === "ArrowLeft") j = (i - 1 + items.length) % items.length;
    else if (e.key === "Home") j = 0;
    else if (e.key === "End") j = items.length - 1;
    if (j < 0) return;
    e.preventDefault();
    onChange(items[j].id);
    refs.current[j]?.focus();
  };
  return (
    <div role="tablist" aria-label={label} className={className}>
      {items.map((t, i) => (
        <button
          key={t.id}
          ref={(el) => {
            refs.current[i] = el;
          }}
          type="button"
          role="tab"
          id={`${idPrefix}-tab-${t.id}`}
          aria-selected={value === t.id}
          aria-controls={`${idPrefix}-panel`}
          tabIndex={value === t.id ? 0 : -1}
          onClick={() => onChange(t.id)}
          onKeyDown={(e) => onKey(e, i)}
          className={tabClassName(value === t.id)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

/** Props for the panel a TabList controls. It is focusable so long pages can be scrolled with the keyboard. */
export const tabPanelProps = (idPrefix: string, value: string) => ({
  role: "tabpanel" as const,
  id: `${idPrefix}-panel`,
  "aria-labelledby": `${idPrefix}-tab-${value}`,
  tabIndex: 0,
});
