import "@fontsource-variable/inter";
import "@fontsource/jetbrains-mono/400.css";
import "@fontsource/jetbrains-mono/500.css";
import "./styles.css";

import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { lazy, StrictMode, Suspense } from "react";
import { createRoot } from "react-dom/client";
import { BrowserRouter, Route, Routes, useLocation } from "react-router-dom";

import { ApiError, isNetworkError } from "./api";
import { ErrorBoundary } from "./components/ErrorBoundary";
import { TopBar } from "./components/TopBar";
import { Home } from "./pages/Home";
import { NotFound } from "./pages/NotFound";
import { Progress } from "./pages/Progress";

// React Flow is most of the bundle; only the graph page needs it.
const Explore = lazy(() => import("./pages/Explore").then((m) => ({ default: m.Explore })));

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      // Connection trouble: keep retrying with backoff (the UI says "reconnecting"); React
      // Query also pauses while the browser is offline and resumes on reconnect. A 4xx will not
      // change on retry. Anything else gets one more try.
      retry: (failures, error) => {
        if (isNetworkError(error)) return true;
        if (error instanceof ApiError && error.status >= 400 && error.status < 500) return false;
        return failures < 1;
      },
      retryDelay: (attempt) => Math.min(1000 * 2 ** attempt, 10_000),
      refetchOnWindowFocus: false,
    },
  },
});

function App() {
  const location = useLocation();
  return (
    <>
      <TopBar />
      <main>
        <ErrorBoundary resetKey={location.pathname}>
          <Routes>
            <Route path="/" element={<Home />} />
            <Route path="/a/:id" element={<Progress />} />
            <Route
              path="/a/:id/explore"
              element={
                <Suspense fallback={<p className="canvas-message caption">Loading graph…</p>}>
                  <Explore />
                </Suspense>
              }
            />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </ErrorBoundary>
      </main>
    </>
  );
}

createRoot(document.getElementById("root")!).render(
  <StrictMode>
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <App />
      </BrowserRouter>
    </QueryClientProvider>
  </StrictMode>,
);
