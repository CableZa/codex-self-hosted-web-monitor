import { useEffect, useState } from "react";

function matchesInitialShape(value: unknown, initialValue: unknown) {
  if (initialValue === null || initialValue === undefined) return true;
  if (Array.isArray(initialValue)) return Array.isArray(value);
  if (typeof initialValue === "object") return value !== null && typeof value === "object" && !Array.isArray(value);
  return typeof value === typeof initialValue;
}

export function useLocalPreference<T>(
  key: string,
  initialValue: T,
  isValid?: (value: unknown) => value is T,
) {
  const [value, setValue] = useState<T>(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (!stored) return initialValue;
      const parsed = JSON.parse(stored) as unknown;
      const acceptsValue = isValid || ((candidate: unknown): candidate is T => matchesInitialShape(candidate, initialValue));
      return acceptsValue(parsed) ? parsed : initialValue;
    } catch {
      return initialValue;
    }
  });

  useEffect(() => {
    try {
      window.localStorage.setItem(key, JSON.stringify(value));
    } catch {
      // Local preferences should never block the dashboard.
    }
  }, [key, value]);

  return [value, setValue] as const;
}
