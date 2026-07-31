## 2026-07-29 - Memoize TaskCard for smoother list updates
**Learning:** Wrapping complex components rendered in lists with React.memo prevents performance bottlenecks where changes to a sibling state element (like an input field causing parent re-render) unexpectedly trigger unneeded re-renders on the list elements.
**Action:** Always verify if high-frequency state updates like input changes share a parent component with lists of unoptimized components, and use React.memo to isolate unchanged items.
