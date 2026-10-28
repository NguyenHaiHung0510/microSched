export type BootstrapSession = {
  email: string; signed_in_at: string | null; expires_at: string; mimi_available: boolean
  private_until: string | null; private_locked_until: string | null; pin_is_set: boolean; pin_is_bootstrap: boolean
  offline_bootstrap?: boolean; principal?: string
}
