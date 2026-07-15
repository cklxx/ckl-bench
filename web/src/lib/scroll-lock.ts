/**
 * Shared scroll lock with reference counting.
 *
 * Multiple sheets can be open at once (e.g. pack detail → case editor
 * stacked on top). Each sheet calls lockScroll() on open and unlockScroll()
 * on close. The body stays locked until the LAST sheet closes, so the
 * background never leaks scroll while any panel is open.
 */
let locks = 0;
let original = "";

export function lockScroll(): void {
  if (typeof document === "undefined") return;
  if (locks === 0) {
    original = document.body.style.overflow;
    document.body.style.overflow = "hidden";
  }
  locks++;
}

export function unlockScroll(): void {
  if (typeof document === "undefined") return;
  locks = Math.max(0, locks - 1);
  if (locks === 0) {
    document.body.style.overflow = original;
  }
}
