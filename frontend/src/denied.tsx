import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { DeniedPage } from '@/HomePage'
import './index.css'

createRoot(document.getElementById('root')!).render(<StrictMode><DeniedPage /></StrictMode>)
