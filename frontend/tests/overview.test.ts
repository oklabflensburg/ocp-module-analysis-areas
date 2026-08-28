import { describe, expect, it } from 'vitest'
import { countAnalysisAreasByType, sortAnalysisAreasByName } from '../layer/app/utils/analysisAreaOverview'

const areas = [
  { name: 'Flensburg', area_type: 'MUNICIPALITY' },
  { name: 'Neustadt', area_type: 'DISTRICT' },
  { name: 'Altstadt', area_type: 'DISTRICT' },
  { name: 'Nordertor', area_type: 'QUARTER' }
]

describe('area overview behavior', () => {
  it('counts all existing area types without hard-coded production totals', () => {
    expect(countAnalysisAreasByType(areas, 'MUNICIPALITY')).toBe(1)
    expect(countAnalysisAreasByType(areas, 'DISTRICT')).toBe(2)
    expect(countAnalysisAreasByType(areas, 'QUARTER')).toBe(1)
  })

  it('sorts German display names', () => {
    expect(sortAnalysisAreasByName(areas.slice(1)).map(area => area.name))
      .toEqual(['Altstadt', 'Neustadt', 'Nordertor'])
  })
})
