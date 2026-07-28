## 2024-05-25 - Unnecessary list re-renders from shared state
**Learning:** In `TasksScreen.tsx`, the `quickTitle` state for the "Quick add" input lives in the same component as the task list. Because `TaskCard` is not memoized, every keystroke in the input triggers a re-render of all up to 100 `TaskCard` components, causing input lag.
**Action:** Always memoize list item components (like `TaskCard`) when their parent contains unrelated rapidly-changing state (like text inputs), or extract the input into its own component.
