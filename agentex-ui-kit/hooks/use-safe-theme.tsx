import { useTheme } from "next-themes";

export function useSafeTheme(): "dark" | "light" {
  const { resolvedTheme } = useTheme();
  return resolvedTheme === "dark" ? "dark" : "light";
}
