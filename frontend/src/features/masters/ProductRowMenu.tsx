import { useLayoutEffect, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { Pencil, Trash2 } from 'lucide-react';

export default function ProductRowMenu({ x, y, label, onEdit, onEditCell, onDelete, onClose }: {
  x: number; y: number; label: string;
  onEdit: () => void; onEditCell?: () => void; onDelete: () => void; onClose: () => void;
}) {
  const menu = useRef<HTMLDivElement>(null);
  const [position, setPosition] = useState({ left: x, top: y });

  useLayoutEffect(() => {
    const element = menu.current!;
    const bounds = element.getBoundingClientRect();
    setPosition({ left: Math.max(8, Math.min(x, window.innerWidth - bounds.width - 8)),
      top: Math.max(8, Math.min(y, window.innerHeight - bounds.height - 8)) });
    const previousFocus = document.activeElement as HTMLElement | null;
    element.querySelector<HTMLButtonElement>('[role="menuitem"]:not([disabled])')?.focus({ preventScroll: true });
    const outside = (event: PointerEvent) => {
      if (!menu.current?.contains(event.target as Node)) onClose();
    };
    const dismiss = () => onClose();
    document.addEventListener('pointerdown', outside, true);
    window.addEventListener('scroll', dismiss, true);
    window.addEventListener('resize', dismiss);
    return () => {
      document.removeEventListener('pointerdown', outside, true);
      window.removeEventListener('scroll', dismiss, true);
      window.removeEventListener('resize', dismiss);
      if (element.contains(document.activeElement)) previousFocus?.focus({ preventScroll: true });
    };
  }, [x, y, onClose]);

  return createPortal(<div ref={menu} role="menu" aria-label={`Actions for ${label}`}
    className="fixed z-[70] w-60 max-w-[calc(100vw-16px)] rounded-xl border border-gray-200 bg-white p-1.5 shadow-xl text-sm text-slate-700"
    style={position} onContextMenu={event => event.preventDefault()} onKeyDown={event => {
      if (event.key === 'Escape') { event.preventDefault(); onClose(); }
      if (event.key === 'Tab') onClose();
      const items = Array.from(menu.current?.querySelectorAll<HTMLButtonElement>('[role="menuitem"]:not([disabled])') ?? []);
      const index = items.indexOf(document.activeElement as HTMLButtonElement);
      const next = event.key === 'ArrowDown' ? (index + 1) % items.length
        : event.key === 'ArrowUp' ? (index + items.length - 1) % items.length
        : event.key === 'Home' ? 0 : event.key === 'End' ? items.length - 1 : -1;
      if (next >= 0) { event.preventDefault(); items[next]?.focus({ preventScroll: true }); }
    }}>
    <div className="truncate px-3 py-2 text-xs text-slate-500" title={label}>{label}</div>
    <button type="button" role="menuitem" disabled={!onEditCell}
      className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-slate-50 focus:bg-slate-100 focus:outline-none disabled:text-slate-300 disabled:cursor-default"
      onClick={onEditCell}><Pencil size={15}/>Edit cell</button>
    <button type="button" role="menuitem" className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left hover:bg-slate-50 focus:bg-slate-100 focus:outline-none"
      onClick={onEdit}><Pencil size={15}/>Edit row…</button>
    <div role="separator" className="my-1 border-t border-gray-100"/>
    <button type="button" role="menuitem" className="flex w-full items-center gap-2 rounded-lg px-3 py-2 text-left text-red-600 hover:bg-red-50 focus:bg-red-50 focus:outline-none"
      onClick={onDelete}><Trash2 size={15}/>Delete row…</button>
  </div>, document.body);
}
