<template>
  <div class="grid gap-1" aria-label="Administrative Gebietsgrenzen">
    <p class="pb-1 text-[11px] font-bold uppercase tracking-wide text-slate-500">Gebietsgrenzen</p>
    <label
      v-for="item in areaLayers"
      :key="item.type"
      class="flex min-h-10 cursor-pointer items-center justify-between gap-3 rounded-lg px-2 py-1 text-sm font-semibold text-slate-700 hover:bg-slate-50"
    >
      <span class="flex items-center gap-2">
        <span class="size-2.5 rounded-full" :style="{ backgroundColor: areas.visibility[item.type] ? item.activeColor : '#cbd5e1' }" aria-hidden="true" />
        {{ item.label }}
      </span>
      <input v-model="areas.visibility[item.type]" type="checkbox" class="size-4 accent-[#154d73]" :aria-label="`${item.label} anzeigen`">
    </label>
  </div>
</template>

<script setup lang="ts">
import { useAnalysisAreasStore } from '../stores/analysisAreas'

const areas = useAnalysisAreasStore()
const areaLayers = [
  { type: 'MUNICIPALITY' as const, label: 'Gemeinde', activeColor: '#1d4ed8' },
  { type: 'DISTRICT' as const, label: 'Stadtteile', activeColor: '#15803d' },
  { type: 'QUARTER' as const, label: 'Quartiere', activeColor: '#b45309' }
]
</script>
