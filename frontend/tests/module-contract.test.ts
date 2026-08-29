import { readFileSync } from 'node:fs'
import { fileURLToPath } from 'node:url'
import { describe, expect, it } from 'vitest'

const root = fileURLToPath(new URL('..', import.meta.url))
const definition = JSON.parse(readFileSync(`${root}/module.json`, 'utf8'))
const source = (path: string) => readFileSync(`${root}/${path}`, 'utf8')

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
