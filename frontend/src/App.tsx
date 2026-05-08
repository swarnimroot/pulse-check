import { Route, Routes } from "react-router-dom";
import { Landing } from "@/pages/Landing";
import { Product } from "@/pages/Product";
import { Pair } from "@/pages/Pair";
import { Showcase } from "@/pages/Showcase";

/** Top-level route table. `/showcase` is bite-11.2's visual-confirm surface. */
export function App(): JSX.Element {
  return (
    <Routes>
      <Route path="/" element={<Landing />} />
      <Route path="/showcase" element={<Showcase />} />
      <Route path="/product/:id" element={<Product />} />
      <Route path="/pair/:id" element={<Pair />} />
    </Routes>
  );
}
