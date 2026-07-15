import { Button } from "@/components/ui/button";
import { Moon, Sun } from "lucide-react";
import { useEffect, useState } from "react";
import { useT } from "@/lib/i18n";

export function ThemeToggle() {
  const t = useT();
  const [theme, setTheme] = useState<"light" | "dark">(() => {
    if (typeof window === "undefined") return "light";
    const stored = localStorage.getItem("ckl-bench-theme") as
      | "light"
      | "dark"
      | null;
    if (stored) return stored;
    return window.matchMedia("(prefers-color-scheme: dark)").matches
      ? "dark"
      : "light";
  });

  useEffect(() => {
    const root = document.documentElement;
    root.classList.toggle("dark", theme === "dark");
    localStorage.setItem("ckl-bench-theme", theme);
  }, [theme]);

  return (
    <Button
      variant="ghost"
      size="icon"
      onClick={() => setTheme(theme === "light" ? "dark" : "light")}
      aria-label={t("theme.toggle")}
    >
      {theme === "light" ? <Moon size={16} /> : <Sun size={16} />}
    </Button>
  );
}
