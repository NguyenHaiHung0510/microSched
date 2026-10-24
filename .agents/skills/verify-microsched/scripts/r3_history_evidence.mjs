/** Failure evidence never persists private surfaces or error-rendered private values. */
export async function captureHistoryEvidence({sensitive, privatePurged, capture}) {
  if (sensitive && !privatePurged) throw new Error('PRIVATE_SCREENSHOT_REQUIRES_VERIFIED_PURGE')
  await capture()
}

export async function recordHistoryFailure({sensitive, receipt, error, capture}) {
  receipt.status = 'FAIL'
  if (sensitive) {
    receipt.error = 'PRIVATE_CASE_FAILED_DETAILS_SUPPRESSED'
    receipt.failure_screenshot = 'OMITTED_PRIVATE_CASE'
    return
  }
  receipt.error = String(error)
  await capture().catch(() => {})
}
