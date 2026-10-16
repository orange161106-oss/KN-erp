import { useLayoutEffect, useRef, type ReactNode } from 'react';

/** Keep wide tables reachable without scrolling to their last row. */
export default function HorizontalTableScroll({ children, label }: { children: ReactNode; label: string }) {
  const scrollbarRef = useRef<HTMLDivElement>(null);
  const spacerRef = useRef<HTMLDivElement>(null);
  const viewportRef = useRef<HTMLDivElement>(null);
  const syncingRef = useRef<HTMLDivElement | null>(null);

  const syncScroll = (source: HTMLDivElement, target: HTMLDivElement | null) => {
    // Ignore the mirrored event instead of interrupting native smooth scrolling.
    if (syncingRef.current === source) {
      syncingRef.current = null;
      return;
    }
    if (target && target.scrollLeft !== source.scrollLeft) {
      syncingRef.current = target;
      target.scrollLeft = source.scrollLeft;
    }
  };

  useLayoutEffect(() => {
    const scrollbar = scrollbarRef.current;
    const spacer = spacerRef.current;
    const viewport = viewportRef.current;
    if (!scrollbar || !spacer || !viewport) return;

    const measure = () => {
      // Include the viewport border so both scrollbars have the same range.
      spacer.style.width = `${scrollbar.clientWidth + viewport.scrollWidth - viewport.clientWidth}px`;
      scrollbar.scrollLeft = viewport.scrollLeft;
    };
    measure();
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(measure);
    observer.observe(viewport);
    if (viewport.firstElementChild) observer.observe(viewport.firstElementChild);
    return () => observer.disconnect();
  }, [children]);

  return (
    <div className="min-w-0">
      <div ref={scrollbarRef} role="region" aria-label={`${label} horizontal scroll`} tabIndex={0}
        className="sticky top-0 z-20 h-[18px] overflow-x-scroll overflow-y-hidden bg-white print:hidden"
        onScroll={event => syncScroll(event.currentTarget, viewportRef.current)}>
        <div ref={spacerRef} className="h-px" />
      </div>
      <div ref={viewportRef} className="overflow-x-auto rounded-lg border border-gray-100 bg-white shadow-xs"
        onScroll={event => syncScroll(event.currentTarget, scrollbarRef.current)}>
        {children}
      </div>
    </div>
  );
}
