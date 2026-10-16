import assert from 'node:assert/strict'
import { test } from 'node:test'
import { initialAnalyticsRange } from './analyticsDateRange.js'
const now = new Date('2026-10-16T10:00:00Z')
for (const [label, query] of [
 ['missing', {}], ['invalid', { start: 'bad', end: 'bad' }],
 ['equal', { start: now.toISOString(), end: now.toISOString() }],
 ['reversed', { start: '2026-10-16T11:00Z', end: '2026-10-16T09:00Z' }],
]) {
 test(`${label} dates initialize a full one-hour window`, () => {
  const range = initialAnalyticsRange(query, now)
  assert.equal(range.defaulted, true)
  assert.equal(new Date(range.end) - new Date(range.start), 3600000)
 })
}
test('preserves a valid historical window', () => {
 const range = initialAnalyticsRange({ start: '2026-10-15T09:00Z', end: '2026-10-15T10:00Z' }, now)
 assert.equal(range.start, '2026-10-15T09:00:00.000Z')
 assert.equal(range.defaulted, false)
})
test('clamps a future end to now', () => {
 const range = initialAnalyticsRange({ start: '2026-10-16T09:00Z', end: '2026-10-16T11:00Z' }, now)
 assert.equal(range.end, now.toISOString())
})
