// alpha.92: drag and drop for the Karaoke host that does NOT use the browser's own drag events
// (the Windows app window can swallow those). It follows the mouse/pen/finger itself:
//   press on a row, move a few pixels -> a chip follows the pointer; rows marked data-drop-singer="<id>" light up under it;
//   let go over one -> onDrop(payload, singerId). Let go anywhere else -> nothing happens.
import { useCallback, useEffect, useRef, useState } from "react";

export const MOVE_BEFORE_DRAG = 6;     // pixels, so a normal click is never mistaken for a drag
export const EDGE = 48;                // pixels from the top/bottom of the list where it scrolls by itself
export const SCROLL_STEP = 14;

// which singer row (if any) is under this point
export const singerAt = (x, y, doc = document) => {
  const el = doc.elementFromPoint(x, y);
  const row = el && el.closest ? el.closest("[data-drop-singer]") : null;
  return row ? { id: row.getAttribute("data-drop-singer"), index: parseInt(row.getAttribute("data-drop-index"), 10) } : null;
};

export const edgeScroll = (box, y) => {      // how far to scroll the list for a pointer at height y (negative = up)
  if (!box) return 0;
  const r = box.getBoundingClientRect();
  if (y < r.top + EDGE) return -SCROLL_STEP;
  if (y > r.bottom - EDGE) return SCROLL_STEP;
  return 0;
};

export function usePointerDrag(onDrop, listSelector = "[data-drop-list]") {
  const [drag, setDrag] = useState(null);                 // { label, x, y, overId } while dragging
  const st = useRef({ start: null, active: false, payload: null, label: "", overId: null, raf: 0, y: 0 });
  const cb = useRef(onDrop); cb.current = onDrop;

  const finish = useCallback((drop) => {
    const s = st.current;
    window.removeEventListener("pointermove", s.move); window.removeEventListener("pointerup", s.up); window.removeEventListener("pointercancel", s.cancel);
    cancelAnimationFrame(s.raf);
    const was = s.active, over = s.overId, payload = s.payload;
    s.start = null; s.active = false; s.overId = null; s.payload = null;
    setDrag(null);
    if (was && drop && over != null) cb.current(payload, over);
  }, []);

  const startDrag = useCallback((e, payload, label) => {
    if (e.button !== undefined && e.button !== 0) return;            // left button / touch / pen only
    if (e.target.closest && e.target.closest("button, input, a")) return;   // buttons on the row still click normally
    const s = st.current;
    s.start = { x: e.clientX, y: e.clientY }; s.payload = payload; s.label = label; s.active = false; s.overId = null; s.y = e.clientY;
    s.move = (ev) => {
      if (!s.start) return;
      s.y = ev.clientY;
      if (!s.active) {
        if (Math.hypot(ev.clientX - s.start.x, ev.clientY - s.start.y) < MOVE_BEFORE_DRAG) return;
        s.active = true;
        const tick = () => {                                        // keep the list scrolling while the pointer sits at an edge
          if (!s.active) return;
          const box = document.querySelector(listSelector);
          const d = edgeScroll(box, s.y);
          if (d && box) box.scrollTop += d;
          s.raf = requestAnimationFrame(tick);
        };
        s.raf = requestAnimationFrame(tick);
      }
      const over = singerAt(ev.clientX, ev.clientY);
      s.overId = over ? over.id : null;
      setDrag({ label: s.label, x: ev.clientX, y: ev.clientY, overId: s.overId });
    };
    s.up = () => finish(true);
    s.cancel = () => finish(false);
    window.addEventListener("pointermove", s.move); window.addEventListener("pointerup", s.up); window.addEventListener("pointercancel", s.cancel);
  }, [finish, listSelector]);

  useEffect(() => () => finish(false), [finish]);                    // leaving the screen mid-drag drops nothing
  return { drag, startDrag };
}
