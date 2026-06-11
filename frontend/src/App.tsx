import { useState } from "react";
import { Route, Routes, useLocation } from "react-router-dom";
import { WelcomeModal } from "@/components/WelcomeModal";
import { About } from "@/pages/About";
import { Standalone } from "@/pages/Standalone";
import { Compare } from "@/pages/Compare";
import { Pair } from "@/pages/Pair";
import { Trend } from "@/pages/Trend";
import { Showcase } from "@/pages/Showcase";

// Top-level route table. `/showcase` is bite-11.2's dev atom catalog.
// The welcome modal opens on fresh App mounts that land on Home ("/");
// in-app navigation between routes does NOT re-trigger it (the lazy
// initial state captures the entry pathname once).
export function App(): JSX.Element {
  const location = useLocation();
  const [welcomeOpen, setWelcomeOpen] = useState(() => location.pathname === "/");

  return (
    <>
      <WelcomeModal open={welcomeOpen} onClose={() => setWelcomeOpen(false)} />
      <Routes>
        <Route path="/" element={<About />} />
        <Route path="/standalone" element={<Standalone />} />
        <Route path="/standalone/:productId" element={<Standalone />} />
        <Route path="/compare" element={<Compare />} />
        <Route path="/pair" element={<Pair />} />
        <Route path="/trend" element={<Trend />} />
        <Route path="/showcase" element={<Showcase />} />
      </Routes>
    </>
  );
}
