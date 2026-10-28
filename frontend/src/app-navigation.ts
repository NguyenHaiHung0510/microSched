import { Activity, Bot, CalendarDays, ListTodo, NotebookPen } from 'lucide-react'
export type AppScreen = 'tasks' | 'notes' | 'calendar' | 'tracker' | 'mimi'
export const APP_SCREENS = [
  {id:'tasks',label:'Task',icon:ListTodo},
  {id:'notes',label:'Ghi chú',icon:NotebookPen},
  {id:'calendar',label:'Lịch',icon:CalendarDays},
  {id:'tracker',label:'Theo dõi',icon:Activity},
  {id:'mimi',label:'Mimi',icon:Bot},
] as const
