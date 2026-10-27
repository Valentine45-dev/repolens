import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { StrictMode } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes } from "react-router-dom";

import { ApiError } from "./api";
import { TopBar } from "./components/TopBar";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import { Progress } from "./pages/Progress";

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // A 4xx (unknown snapshot, bad id) will not change on retry; network trouble might.
      retry: (failures, error) =>
        failures < 1 && !(error instanceof ApiError && error.status >= 400 && error.status < 500),
      refetchOnWindowFocus: false,
    },
  },
});

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <TopBar />
        <main>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/a/:id" element={<Progress />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </main>
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
