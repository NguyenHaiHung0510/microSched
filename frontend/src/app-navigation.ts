import { Activity, Bot, CalendarDays, Leaf, ListTodo, NotebookPen } from 'lucide-react'
export type AppScreen = 'tasks' | 'migarden' | 'notes' | 'calendar' | 'tracker' | 'mimi'
export const APP_SCREENS = [
  {id:'tasks',label:'Task',icon:ListTodo},
  {id:'migarden',label:'miGarden',icon:Leaf},
  {id:'notes',label:'Ghi chú',icon:NotebookPen},
  {id:'calendar',label:'Lịch',icon:CalendarDays},
  {id:'tracker',label:'Theo dõi',icon:Activity},
  {id:'mimi',label:'Mimi',icon:Bot},
] as const

export function quickScreens(gardenAvailable: boolean, desktop: boolean) {
  return APP_SCREENS.filter(({id}) => id === 'migarden' ? gardenAvailable : id !== 'tasks' || !gardenAvailable || desktop)
}
