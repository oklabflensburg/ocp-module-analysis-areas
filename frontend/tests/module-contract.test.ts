import { existsSync, readFileSync, readdirSync, statSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('..', import.meta.url))
const definition = JSON.parse(readFileSync(`${root}/module.json`, 'utf8'))
const source = (path: string) => readFileSync(`${root}/${path}`, 'utf8')
const layerSources = (directory = `${root}/layer`): string[] => readdirSync(directory)
  .flatMap(entry => {
    const path = `${directory}/${entry}`
    return statSync(path).isDirectory() ? layerSources(path) : /\.(?:vue|[cm]?[jt]s)$/.test(path) ? [path] : []
  })

describe('Analysis Areas frontend module contract', () => {
  it('preserves identity, routes, navigation and map contributions', () => {
    expect(definition).toMatchObject({
      schemaVersion: 1,
      id: 'analysis-areas',
      version: '1.0.0',
      backendModuleId: 'analysis-areas',
      layer: 'layer',
      compatibility: { sdk: '>=1.4.0 <2.0.0' }
    })
    expect(definition.publicContributions.routes.map((route: { path: string }) => route.path))
      .toEqual(['/gebiete', '/gebiete/:slug'])
    expect(definition.publicContributions.ui).toEqual(expect.arrayContaining([
      expect.objectContaining({ id: 'analysis-areas.primary-navigation', to: '/gebiete' }),
      expect.objectContaining({ id: 'analysis-areas.map-runtime', slot: 'map.controls' }),
      expect.objectContaining({ id: 'analysis-areas.map-layers', slot: 'map.layers' }),
      expect.objectContaining({ id: 'analysis-areas.map-selection', slot: 'map.selection' })
    ]))
    expect(definition.publicContributions.map.sources.map((item: { id: string }) => item.id))
      .toEqual(['analysis-areas.data'])
    expect(definition.publicContributions.map.layers).toHaveLength(10)
  })

  it('preserves detail, statistics, POI, OSM, map and SEO behavior', () => {
    const detail = source('layer/app/pages/gebiete/[slug].vue')
    for (const value of [
      'api.bySlug(slug)', 'api.analyticsBySlug(slug)', 'api.comparisonBySlug(slug)',
      'api.polygonsBySlug(slug)', 'api.statisticsBySlug(slug)',
      "api.statisticSeriesBySlug(slug, 'population')", '<AreaStatistics',
      'areaPoiMapLink(area.slug, item.category)', "path: '/karte'", 'useAnalysisAreaSeo'
    ]) expect(detail).toContain(value)
    expect(detail).toContain('Externe Quellen')
    expect(detail).toContain('OpenStreetMap')
    expect(detail).toContain("import AnalysisAreaDetailMap from '../../components/analysis/AnalysisAreaDetailMap.vue'")
    expect(detail).toContain("route.query['social-preview'] === '1'")
    expect(detail).toContain("route.query.map !== '0'")
    expect(detail).toContain('<AnalysisAreaDetailMap v-if="previewMap" :area="area" @ready="mapReady = true" />')
    expect(detail).toContain("const previewReady = computed(() => !previewMap.value || mapReady.value)")
  })

  it('packages the module-owned detail map without a Host component fallback', () => {
    const detailMapPath = 'layer/app/components/analysis/AnalysisAreaDetailMap.vue'
    expect(existsSync(`${root}/${detailMapPath}`)).toBe(true)
    expect(existsSync(`${root}/host-compatibility/app/components/analysis/AnalysisAreaDetailMap.vue`)).toBe(false)
    const detailMap = source(detailMapPath)
    expect(detailMap).toContain("import('maplibre-gl')")
    expect(detailMap).toContain('useMapStylePort()')
    expect(detailMap).toContain('useModuleHttp()')
    expect(detailMap).toContain("emit('ready')")
    expect(detailMap).toContain('onMounted(async () =>')
    expect(detailMap).toContain('onBeforeUnmount(() =>')
    expect(detailMap).toContain('resizeObserver?.disconnect()')
    expect(detailMap).toContain('map.value?.remove()')
    expect(detailMap).not.toContain('resolveComponent')
  })

  it('declares every direct runtime import and rejects private Host imports', () => {
    const packageDefinition = JSON.parse(source('package.json'))
    expect(packageDefinition.dependencies).toMatchObject({ 'maplibre-gl': '6.4.1' })
    for (const path of layerSources()) {
      const contents = readFileSync(path, 'utf8')
      expect(contents, path).not.toMatch(/from\s+['"](?:~\/|@\/)(?:stores|utils|types|composables)\//)
    }
  })

  it('keeps the map runtime isolated from MapCanvas', () => {
    const runtime = source('layer/app/components/AnalysisAreasMapRuntime.vue')
    const store = source('layer/app/stores/analysisAreas.ts')
    expect(runtime).toContain("moduleId: 'analysis-areas'")
    expect(runtime).toContain("context.interactions.register")
    expect(runtime).toContain("context.featureInfo.register")
    expect(runtime).toContain('context.selection.registerPresentation')
    expect(runtime).toContain('context.selection.reveal()')
    expect(runtime).toContain("route.query.gebiet")
    expect(runtime).toContain("setData(areas.featureCollection)")
    expect(runtime).not.toContain('useMapStore')
    expect(store).toContain('useModuleHttp')
    expect(store).toContain('useMapFilterPort')
    expect(store).not.toContain("from '~/")
    expect(source('layer/app/components/AnalysisAreaCard.vue')).toContain('useMapSelectionPort')
    expect(source('layer/app/components/analysis/ExternalSourceLink.vue')).toContain('OcpProviderIcon')
  })
})
