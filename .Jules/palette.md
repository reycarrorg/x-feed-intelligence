## 2024-05-19 - Focus vs Focus-Visible
**Learning:** Using purely `:focus` creates sticky outlines when users click buttons with their mouse, leading to confusing visual feedback. `focus-visible` ensures focus rings only appear for keyboard navigation, honoring both mouse and keyboard users gracefully.
**Action:** Always prefer `:focus-visible` over `:focus` for interactive elements unless we specifically want the focus ring on click (which is rare).
