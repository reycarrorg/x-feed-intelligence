## 2024-05-24 - Interactive Element Focus UX
**Learning:** Using `:focus` instead of `:focus-visible` on buttons causes the focus ring to persistently display after mouse clicks, creating visual noise for mouse users.
**Action:** Always prefer `:focus-visible` over `:focus` for interactive elements like buttons to maintain keyboard accessibility while improving mouse UX, and ensure buttons have basic micro-interactions (`cursor: pointer`, `:hover`, `:active`) and transitions for a smooth feel.
