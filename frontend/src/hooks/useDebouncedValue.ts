import { useEffect, useState } from "react";

/** Delays updating the returned value until `value` has stopped changing
 * for `delayMs` — used for search inputs so we don't fire a request on
 * every keystroke. */
export function useDebouncedValue<T>(value: T, delayMs = 350): T {
  const [debounced, setDebounced] = useState(value);

  useEffect(() => {
    const timer = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timer);
  }, [value, delayMs]);

  return debounced;
}
