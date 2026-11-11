import type { ButtonHTMLAttributes, KeyboardEvent, ReactElement } from 'react';
import * as Tooltip from '@radix-ui/react-tooltip';
import { clsx, type ClassValue } from 'clsx';
import { twMerge } from 'tailwind-merge';

export const cn = (...values: ClassValue[]) => twMerge(clsx(values));

export function Tip({ label, children }: { label: string; children: ReactElement }) {
  return <Tooltip.Root><Tooltip.Trigger asChild>{children}</Tooltip.Trigger><Tooltip.Portal><Tooltip.Content className="tooltip" sideOffset={6}>{label}<Tooltip.Arrow /></Tooltip.Content></Tooltip.Portal></Tooltip.Root>;
}
export function IconButton({ label, children, ...props }: ButtonHTMLAttributes<HTMLButtonElement> & { label: string }) {
  return <Tip label={label}><button {...props} type="button" aria-label={label} className={cn('icon-button', props.className)}>{children}</button></Tip>;
}

export function handleRovingKeyDown<T extends string>(
  event: KeyboardEvent<HTMLElement>,
  ids: readonly T[],
  activeId: T,
  onSelect: (id: T) => void
) {
  const currentIndex = ids.indexOf(activeId);
  if (currentIndex === -1 || !ids.length) return;
  let nextIndex = -1;
  if (event.key === 'ArrowRight' || event.key === 'ArrowDown') {
    nextIndex = (currentIndex + 1) % ids.length;
  } else if (event.key === 'ArrowLeft' || event.key === 'ArrowUp') {
    nextIndex = (currentIndex - 1 + ids.length) % ids.length;
  } else if (event.key === 'Home') {
    nextIndex = 0;
  } else if (event.key === 'End') {
    nextIndex = ids.length - 1;
  }
  if (nextIndex === -1) return;
  event.preventDefault();
  const nextId = ids[nextIndex];
  onSelect(nextId);
  const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="tab"], [role="radio"]');
  buttons[nextIndex]?.focus();
}


