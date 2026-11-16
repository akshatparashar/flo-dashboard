import "@fontsource-variable/instrument-sans";
import "@fontsource-variable/bodoni-moda";
import "./styles/tokens.css";
import "./styles/app.css";

import { useGSAP } from "@gsap/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import gsap from "gsap";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter } from "react-router-dom";
import App from "./App";

gsap.registerPlugin(useGSAP);

const queryClient = new QueryClient();

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
