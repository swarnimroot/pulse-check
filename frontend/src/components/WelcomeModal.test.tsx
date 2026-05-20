import { describe, expect, it, vi } from "vitest";
import { fireEvent, render, screen } from "@testing-library/react";
import { WelcomeModal } from "./WelcomeModal";

describe("WelcomeModal", () => {
  it("renders the dialog with title when open=true", () => {
    render(<WelcomeModal open={true} onClose={() => {}} />);
    expect(screen.getByRole("dialog")).toBeInTheDocument();
    expect(screen.getByText("At a glance")).toBeInTheDocument();
  });

  it("renders nothing when open=false", () => {
    const { container } = render(<WelcomeModal open={false} onClose={() => {}} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("calls onClose when the X button is clicked", () => {
    const onClose = vi.fn();
    render(<WelcomeModal open={true} onClose={onClose} />);
    fireEvent.click(screen.getByLabelText("Close welcome"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when the Got it button is clicked", () => {
    const onClose = vi.fn();
    render(<WelcomeModal open={true} onClose={onClose} />);
    fireEvent.click(screen.getByText("Got it"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when Escape is pressed", () => {
    const onClose = vi.fn();
    render(<WelcomeModal open={true} onClose={onClose} />);
    fireEvent.keyDown(document, { key: "Escape" });
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("calls onClose when the backdrop is clicked", () => {
    const onClose = vi.fn();
    render(<WelcomeModal open={true} onClose={onClose} />);
    fireEvent.click(screen.getByRole("dialog"));
    expect(onClose).toHaveBeenCalledOnce();
  });

  it("does NOT call onClose when inner content is clicked (stopPropagation)", () => {
    const onClose = vi.fn();
    render(<WelcomeModal open={true} onClose={onClose} />);
    fireEvent.click(screen.getByText("At a glance"));
    expect(onClose).not.toHaveBeenCalled();
  });

  it("renders all three section eyebrows + the per-function use-case rows", () => {
    render(<WelcomeModal open={true} onClose={() => {}} />);
    expect(screen.getByText("The problem")).toBeInTheDocument();
    expect(screen.getByText("What this does")).toBeInTheDocument();
    expect(screen.getByText("Who uses it")).toBeInTheDocument();
    expect(screen.getByText("How each function uses it")).toBeInTheDocument();
    expect(screen.getByText(/Spot emerging quality issues per SKU/)).toBeInTheDocument();
    expect(screen.getByText(/Pull genuine talking points/)).toBeInTheDocument();
    expect(screen.getByText(/Surface thermal/)).toBeInTheDocument();
    expect(screen.getByText(/Head-to-head leverage/)).toBeInTheDocument();
  });
});
