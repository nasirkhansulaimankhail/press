def execute():
	"""Keep the local catalog's reviewed provider eligibility unchanged.

	An empty provider list already means unrestricted eligibility. Copying the
	upstream provider list would restrict custom local providers on existing plans.
	"""
