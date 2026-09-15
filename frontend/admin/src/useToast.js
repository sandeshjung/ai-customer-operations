import { useCallback, useRef, useState } from "react";

export function useToast() {
  const [toast, setToast] = useState({ message: "", kind: "", show: false });
  const timerRef = useRef(null);

  const showToast = useCallback((message, kind = "") => {
    clearTimeout(timerRef.current);
    setToast({ message, kind, show: true });
    timerRef.current = setTimeout(() => {
      setToast((t) => ({ ...t, show: false }));
    }, 3200);
  }, []);

  return { toast, showToast };
}
