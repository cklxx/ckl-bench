import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { TooltipProvider } from "@/components/ui/tooltip";
import { I18nProvider } from "@/lib/i18n";
import App from "./App";
import "./index.css";

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <I18nProvider>
      <TooltipProvider delayDuration={0}>
        <App />
      </TooltipProvider>
    </I18nProvider>
  </StrictMode>
);
