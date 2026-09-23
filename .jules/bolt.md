## 2026-07-29 - Memoize TaskCard for smoother list updates
**Learning:** Wrapping complex components rendered in lists with React.memo prevents performance bottlenecks where changes to a sibling state element (like an input field causing parent re-render) unexpectedly trigger unneeded re-renders on the list elements.
**Action:** Always verify if high-frequency state updates like input changes share a parent component with lists of unoptimized components, and use React.memo to isolate unchanged items.
## 2026-08-02 - Memoize list items in React mapping loops
**Learning:** For React components rendering lists using `.map()`, rendering inline JSX with handlers created in the parent scope causes all list items to re-render when the parent's state updates, even if the individual items haven't changed.
**Action:** Extract list items into separate components, wrap them in `React.memo`, and use `useCallback` on any handler functions passed down from the parent to ensure stable prop references and prevent unnecessary re-renders.
## 2026-09-23 - Unsafe SQLAlchemy Count Optimization
**Learning:** The optimization `stmt.with_only_columns(func.count())` creates an unfiltered statement missing the `FROM` clause when used on the specific SQLAlchemy version in this repository, making it an unsafe pattern here.
**Action:** Do not use `with_only_columns(func.count())` to optimize count queries in this codebase.
