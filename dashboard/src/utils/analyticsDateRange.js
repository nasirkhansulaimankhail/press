export function initialAnalyticsRange(query, now = new Date()) {
	const start = query.start ? new Date(query.start) : new Date(NaN)
	const requestedEnd = query.end ? new Date(query.end) : new Date(NaN)
	const end = new Date(Math.min(requestedEnd.getTime(), now.getTime()))
	if (Number.isFinite(start.getTime()) && Number.isFinite(end.getTime()) && start < end) {
		return { start: start.toISOString(), end: end.toISOString(), defaulted: false }
	}
	return {
		start: new Date(now.getTime() - 60 * 60 * 1000).toISOString(),
		end: now.toISOString(), defaulted: true,
	}
}
