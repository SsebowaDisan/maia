/**
 * ThemeProvider — wraps the app with dark/light mode support.
 *
 * Uses next-themes for system preference detection, localStorage persistence,
 * and the `dark` class on <html> for Tailwind dark mode.
 */
import { ThemeProvider as NextThemesProvider } from "next-themes";
import type { ReactNode } from "react";

type MaiaThemeProviderProps = {
  children: ReactNode;
};

function MaiaThemeProvider({ children }: MaiaThemeProviderProps) {
  return (
    <NextThemesProvider
      attribute="class"
      defaultTheme="system"
      enableSystem
      disableTransitionOnChange={false}
      storageKey="maia.theme"
    >
      {children}
    </NextThemesProvider>
  );
}

export { MaiaThemeProvider };
