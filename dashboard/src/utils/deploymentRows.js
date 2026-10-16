export function deploymentRows(builds, pipelines) {
	return [
		...builds.map((item) => ({ ...item, kind: 'Build', routeName: 'Deploy Candidate' })),
		...pipelines.map((item) => ({ ...item, kind: 'Pipeline', routeName: 'Release Pipeline' })),
	].sort((a, b) => b.creation.localeCompare(a.creation))
}
