import { Route, Routes } from "react-router-dom";
import { Landing } from "@/pages/Landing";
import { Product } from "@/pages/Product";
import { Pair } from "@/pages/Pair";

/** Top-level route table. Three routes per DESIGN_SYSTEM §5. */
export function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/product/:id" element={<Product />} />
      <Route path="/pair/:id" element={<Pair />} />
    </Routes>
  );
}
