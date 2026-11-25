import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {
  FOOD_IMAGE_MAP,
  LOADING_MESSAGES,
  computeLoadingStage,
  formatDisplayCode,
  resolveNutritionHighlights,
  summarizeParameters
} from './labmind-view.utils.ts';

test('All FOOD_IMAGE_MAP entries exist on disk in frontend/public/', () => {
  const publicDir = path.resolve(process.cwd(), 'frontend/public');
  for (const [key, relPath] of Object.entries(FOOD_IMAGE_MAP)) {
    const absPath = path.join(publicDir, relPath);
    assert.ok(fs.existsSync(absPath), `Missing food asset for ${key}: ${absPath}`);
  }
});

test('resolveNutritionHighlights assigns unique real images and filters unmapped/duplicate items', () => {
  const resolved = resolveNutritionHighlights([
    { title: 'Amandes', subtitle: 'Oléagineux riches en magnésium.', image_key: 'almonds_walnuts' },
    { title: 'Noix', subtitle: 'Cerneaux sources de minéraux.', image_key: 'almonds_walnuts' },
    { title: 'Épinards', subtitle: 'Légumes verts riches en folates.', image_key: 'spinach' },
    { title: 'Produits laitiers', subtitle: 'Yaourt nature source de calcium.', image_key: 'neutral' },
    { title: 'Eau minérale', subtitle: 'Hydratation quotidienne.', image_key: 'neutral' },
    { title: 'Amandes grillées', subtitle: 'Doublon d’oléagineux déjà affiché.', image_key: 'almonds_walnuts' },
    { title: 'Aliment mystère inconnu', subtitle: 'Sans correspondance visuelle.', image_key: 'neutral' }
  ]);

  assert.equal(resolved.length, 5);
  assert.equal(resolved[0].imageKey, 'almonds_walnuts');
  assert.equal(resolved[1].imageKey, 'walnuts');
  assert.equal(resolved[2].imageKey, 'spinach');
  assert.equal(resolved[3].imageKey, 'dairy_yogurt');
  assert.equal(resolved[4].imageKey, 'hydration_water');

  // Strictly unique image URLs
  const uniqueUrls = new Set(resolved.map((c) => c.imageUrl));
  assert.equal(uniqueUrls.size, resolved.length);
});

test('resolveNutritionHighlights drops cards whose images fail to load', () => {
  const failed = new Set(['spinach']);
  const resolved = resolveNutritionHighlights(
    [
      { title: 'Épinards', subtitle: 'Légumes verts.', image_key: 'spinach' },
      { title: 'Poissons gras', subtitle: 'Saumon et sardines.', image_key: 'fish' }
    ],
    failed
  );
  assert.equal(resolved.length, 1);
  assert.equal(resolved[0].title, 'Poissons gras');
});

test('summarizeParameters keeps ALL parameters including TCMH, CCMH, and RAW_* unrecognized ones', () => {
  const stats = summarizeParameters([
    { code: 'TCMH', name_printed: 'TCMH', value: 30, unit: 'pg', status: 'within_reference' },
    { code: 'CCMH', name_printed: 'CCMH', value: 34, unit: 'g/dL', status: 'within_reference' },
    { code: 'MG', name_printed: 'Magnésium', value: 17.39, unit: 'mg/L', status: 'below_reference' },
    { code: 'RAW_CRP', name_printed: 'Protéine C Réactive', value: 12.4, unit: 'mg/L', status: 'above_reference' },
    { code: 'RAW_TSH', name_printed: 'TSH ultrasensible', value: 2.15, unit: 'mUI/L', status: 'within_reference' }
  ]);

  assert.equal(stats.total, 5);
  assert.equal(stats.normalCount, 3);
  assert.equal(stats.attentionCount, 2);
  assert.equal(stats.otherCount, 0);
  assert.equal(stats.anomalyParams.length, 2);
  assert.equal(stats.allParams.length, 5);
  assert.equal(formatDisplayCode('RAW_CRP'), '');
  assert.equal(formatDisplayCode('TCMH'), 'TCMH');
});

test('computeLoadingStage uses the 4 simple messages and never hits 100% before done', () => {
  assert.equal(LOADING_MESSAGES.length, 4);
  const early = computeLoadingStage({ status: 'received' }, 0);
  assert.equal(early.stageIndex, 0);
  assert.equal(early.activeMessage, 'Lecture de votre document…');
  assert.ok(early.progressPercent < 100);

  const mid = computeLoadingStage({ status: 'processing', parameters: [{ code: 'HGB' }] }, 3);
  assert.equal(mid.stageIndex, 2);
  assert.equal(mid.activeMessage, 'Vérification des valeurs de référence…');
  assert.ok(mid.progressPercent < 100);

  const longWait = computeLoadingStage({ status: 'processing' }, 60);
  assert.equal(longWait.stageIndex, 3);
  assert.equal(longWait.activeMessage, 'Préparation de vos explications…');
  assert.ok(longWait.progressPercent <= 88, 'Must never simulate 100% before backend finishes');

  const done = computeLoadingStage({ status: 'done' }, 15);
  assert.equal(done.progressPercent, 100);
});
