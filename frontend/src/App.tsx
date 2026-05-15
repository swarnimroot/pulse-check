import { Route, Routes } from "react-router-dom";
import { About } from "@/pages/About";
import { Standalone } from "@/pages/Standalone";
import { Compare } from "@/pages/Compare";
import { Pair } from "@/pages/Pair";
import { Showcase } from "@/pages/Showcase";

// Top-level route table. `/showcase` is bite-11.2's dev atom catalog.
export function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<About />} />
      <Route path="/standalone/:productId" element={<Standalone />} />
      <Route path="/compare" element={<Compare />} />
      <Route path="/pair" element={<Pair />} />
      <Route path="/showcase" element={<Showcase />} />
    </Routes>
  );
}
