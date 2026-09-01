import { describe, expect, it } from 'vitest'
import { areaPoiMapLink } from '../layer/app/utils/areaPoiMapLink'

describe('module-owned area POI navigation', () => {
  it('preserves the public map query contract', () => {
    expect(areaPoiMapLink('altstadt-15630273', 'restaurant')).toEqual({
      path: '/karte',
      query: {
        gebiet: 'altstadt-15630273',
        poi: 'restaurant'
      }
    })
  })
})
