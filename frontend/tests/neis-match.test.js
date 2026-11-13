import { test } from 'node:test';
import assert from 'node:assert/strict';
import { createServer } from 'vite';

test('같은 학교명을 지역 교육청 코드로 구분하고 불명확한 결과는 자동 선택하지 않는다', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } });
  try {
    const { resolveMealSchool } = await server.ssrLoadModule('/src/neis-match.ts');
    const seoul = { id: 'B10:1234567', name: '중앙고등학교', region: '고등학교', address: '서울특별시 종로구' };
    const gyeonggi = { id: 'J10:2345678', name: '중앙고등학교', region: '고등학교', address: '경기도 성남시' };
    assert.equal(resolveMealSchool({ name: '중앙고등학교', region: '경기도' }, [seoul, gyeonggi]), gyeonggi);
    assert.equal(resolveMealSchool({ name: '중앙고등학교', region: '서울' }, [gyeonggi]), null);
    assert.equal(resolveMealSchool({ name: '중앙고등학교', region: '' }, [seoul, gyeonggi]), null);
    assert.equal(resolveMealSchool({ name: '중앙고등학교', region: '서울' }, [seoul, { ...seoul, id: 'B10:3456789' }]), null);
    assert.equal(resolveMealSchool({ name: '중앙 고등학교', region: '서울특별시' }, [seoul]), seoul);
    assert.equal(resolveMealSchool({ name: '중앙고등학교', region: '서울' }, [{ ...seoul, name: '중앙여자고등학교' }]), null);
    const jeonbuk = { ...seoul, id: 'P10:1234567' };
    assert.equal(resolveMealSchool({ name: '중앙고등학교', region: '전북특별자치도' }, [jeonbuk]), jeonbuk);
  } finally {
    await server.close();
  }
});
