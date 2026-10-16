import assert from 'node:assert/strict'
import { test } from 'node:test'
import { deploymentRows } from './deploymentRows.js'

test('shows current and historical builds without a date cutoff', () => {
	const builds = [
		{ name: 'running', status: 'Running', creation: '2026-10-16 14:10:13' },
		{ name: 'previous', status: 'Success', creation: '2026-09-12 22:33:29' },
		{ name: 'old', status: 'Success', creation: '2025-01-01 00:00:00' },
	]
	assert.deepEqual(deploymentRows(builds, []).map((row) => row.name), ['running', 'previous', 'old'])
	assert.equal(builds[0].routeName, undefined)
})

test('orders mixed deployment formats and preserves their detail routes', () => {
	const rows = deploymentRows(
		[{ name: 'same', creation: '2026-10-16 14:10:13' }],
		[{ name: 'same', creation: '2026-10-17 10:00:00' }],
	)
	assert.deepEqual(rows.map((row) => [row.kind, row.routeName]), [
		['Pipeline', 'Release Pipeline'], ['Build', 'Deploy Candidate'],
	])
})

test('handles either format being absent', () => {
	assert.deepEqual(deploymentRows([], []), [])
	assert.equal(deploymentRows([], [{ name: 'new', creation: '2026-10-16' }]).length, 1)
})
