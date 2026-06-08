import React from "react";
import ReactDOM from "react-dom/client";
import { QueryClientProvider } from "@tanstack/react-query";
import { queryClient } from "./app/queryClient";
import { TerminalShell } from "./shell/TerminalShell";
import "./styles/tokens.css";
import "./styles/base.css";
import "./styles/shell.css";
import "./styles/tables.css";
import "./styles/forms.css";

ReactDOM.createRoot(document.getElementById("root")!).render(
  <React.StrictMode>
    <QueryClientProvider client={queryClient}>
      <TerminalShell />
    </QueryClientProvider>
  </React.StrictMode>
);
