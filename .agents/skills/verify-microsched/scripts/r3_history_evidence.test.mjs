import {test} from 'node:test'
import assert from 'node:assert/strict'
import fs from 'node:fs/promises'
import {captureHistoryEvidence, recordHistoryFailure} from './r3_history_evidence.mjs'

test('private failure suppresses raw error and pixels; public failure still records useful evidence', async () => {
  const receipt = {}, raw = new Error('SYNTHETIC_PRIVATE_FAILURE_CANARY'), screenshots = []
  await recordHistoryFailure({sensitive:true,receipt,error:raw,capture:async()=>screenshots.push('private')})
  assert.equal(receipt.error, 'PRIVATE_CASE_FAILED_DETAILS_SUPPRESSED')
  assert.equal(JSON.stringify(receipt).includes('CANARY'), false)
  assert.deepEqual(screenshots, [])
  await recordHistoryFailure({sensitive:false,receipt:{},error:new Error('public diagnostic'),capture:async()=>screenshots.push('public')})
  assert.deepEqual(screenshots, ['public'])
})

test('private success screenshots require verified purge', async () => {
  let captured = 0
  await assert.rejects(captureHistoryEvidence({sensitive:true,privatePurged:false,capture:async()=>captured++}), /VERIFIED_PURGE/)
  assert.equal(captured, 0)
  await captureHistoryEvidence({sensitive:true,privatePurged:true,capture:async()=>captured++})
  assert.equal(captured, 1)
})

test('intentionally disabled private failure guard is caught, without saving private pixels/errors', async () => {
  const source = (await fs.readFile(new URL('./r3_history_evidence.mjs', import.meta.url),'utf8')).replace('if (sensitive) {', 'if (false) {')
  const unsafe = await import('data:text/javascript;base64,'+Buffer.from(source).toString('base64'))
  const receipt = {}; let pixelSinkCalls = 0
  await unsafe.recordHistoryFailure({sensitive:true,receipt,error:new Error('SYNTHETIC_PRIVATE_FAILURE_CANARY'),capture:async()=>pixelSinkCalls++})
  assert.throws(()=>assert.equal(receipt.error,'PRIVATE_CASE_FAILED_DETAILS_SUPPRESSED'))
  assert.equal(pixelSinkCalls, 1)
  // Deliberate violation stayed in memory; test output contains only this constant.
  console.log('Intended guard violation FAIL detected; original guard restored/PASS')
})
