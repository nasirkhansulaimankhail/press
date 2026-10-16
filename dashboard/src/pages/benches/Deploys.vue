<script setup lang="ts">
import {
	Badge,
	Button,
	createDocumentResource,
	createListResource,
	Select,
	Tooltip,
} from 'frappe-ui'
import { computed, defineAsyncComponent, h } from 'vue'
import { toast } from 'vue-sonner'
import Scrollbar from '@/components/common/Scrollbar.vue'
import { renderDialog } from '@/utils/components'
import { date, duration } from '@/utils/format'
import { pollReleasePipelineValidationStatus } from '@/utils/pollReleasePipeline'
import { deploymentRows } from '@/utils/deploymentRows'

interface Props {
	name?: string
}
const props = defineProps<Props>()

const group = createDocumentResource({
	doctype: 'Release Group',
	name: props.name,
	auto: true,
})

const deployBuilds = createListResource({
	doctype: 'Deploy Candidate Build',
	fields: ['name', 'status', 'creation', 'build_duration', 'owner'],
	filters: {
		group: props.name,
	},
	orderBy: 'creation desc',
	auto: true,
})

const pipelines = createListResource({
	doctype: 'Release Pipeline',
	fields: ['name', 'status', 'creation', 'owner'],
	filters: {
		release_group: props.name,
	},
	orderBy: 'creation desc',
	auto: true,
})

const badgeThemes = {
	Running: 'blue',
	Success: 'green',
	Failure: 'red',
	Pending: 'yellow',
	Preparing: 'yellow',
	Retrying: 'yellow',
	'Partial Success': 'yellow',
}

const statusOptions = [
	'',
	'Draft',
	'Scheduled',
	'Pending',
	'Preparing',
	'Running',
	'Retrying',
	'Partial Success',
	'Success',
	'Failure',
]

const deployments = computed(() =>
	deploymentRows(deployBuilds.data || [], pipelines.data || []),
)

function refreshDeployments() {
	deployBuilds.reload()
	pipelines.reload()
}

const handleStatusChange = (status: string) => {
	for (const resource of [deployBuilds, pipelines]) {
		if (status) resource.filters.status = status
		else delete resource.filters.status
		resource.reload()
	}
}

function loadMoreDeployments() {
	if (deployBuilds.hasNextPage) deployBuilds.next()
	if (pipelines.hasNextPage) pipelines.next()
}

function handleDeploy() {
	if (group.doc?.deploy_information?.deploy_in_progress) {
		return toast.error('Deploy is in progress. Please wait for it to complete.')
	}

	const UpdateReleaseGroupDialog = defineAsyncComponent(
		() => import('@/components/group/UpdateReleaseGroupDialog.vue'),
	)

	renderDialog(
		h(UpdateReleaseGroupDialog, {
			bench: group.name,
			lastDeploy: true,
			onSuccess(candidate: string) {
				group.doc.deploy_information.has_running_release_pipeline = true
				group.doc.deploy_information.update_available = false
				if (candidate) {
					group.doc.deploy_information.last_deploy = { name: candidate }
				}
				pollReleasePipelineValidationStatus(group)
				pipelines.reload()
				deployBuilds.reload()
			},
		}),
	)
}
</script>

<template>
	<div class="flex items-center gap-2 mb-3">
		<Select
			:options="statusOptions"
			@update:modelValue="handleStatusChange"
			placeholder="Select Status"
			class="max-w-[130px] mr-auto"
		/>

		<Button @click="refreshDeployments">
			<lucide-refresh-ccw class="size-4" />
		</Button>

		<Button @click="handleDeploy">
			<template #prefix> <LucideRocket class="size-4" /></template>
			Deploy
		</Button>
	</div>

	<Scrollbar class="h-[calc(100dvh-300px)] md:h-[calc(100dvh-230px)]">
		<div class="table w-full [&_.table-cell]:p-2">
			<div
				class="bg-surface-gray-2  text-ink-gray-4  sticky top-0 z-10 table-header-group"
			>
				<div class="table-row" role="row">
					<div class="rounded-l table-cell">Deploy</div>
					<div class="table-cell">Status</div>

					<div class="table-cell">Type</div>
					<div class="table-cell">Duration</div>
					<div class="table-cell rounded-r">Deployed By</div>
				</div>
			</div>

			<div class="h-3 invisible">a</div>

			<div class="table-row-group">
				<router-link
					v-for="item in deployments"
					:key="`${item.routeName}:${item.name}`"
					class="hover:bg-surface-gray-1 table-row *:border-b"
					:to="{ name: item.routeName, params: { id: item.name, name } }"
					role="row"
				>
					<div class="whitespace-nowrap table-cell hover:rounded-l" role="cell">
						Deploy on {{ date(item.creation) }}
					</div>

					<div class="table-cell" role="cell">
						<Badge :label="item.status" :theme="badgeThemes[item.status]">
							<template #suffix v-if="item.addressable_notification">
								<Tooltip text="Attention required!">
									<LucideAlertCircle class="size-3" />
								</Tooltip>
							</template>
						</Badge>
					</div>

					<div class="table-cell" role="cell">{{ item.kind }}</div>
					<div class="table-cell" role="cell">
						{{ item.build_duration == null ? '—' : duration(item.build_duration) }}
					</div>
					<div class="table-cell hover:rounded-r" role="cell">{{ item.owner }}</div>
				</router-link>
			</div>
		</div>
	</Scrollbar>

	<div class="w-full flex">
		<Button
			v-if="deployBuilds.hasNextPage || pipelines.hasNextPage"
			class="ml-auto mt-3"
			@click="loadMoreDeployments"
		>
			Load more
		</Button>
	</div>
</template>
