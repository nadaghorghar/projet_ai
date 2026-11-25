export interface LabParameter {
  code: string;
  name_printed: string;
  value: number | null;
  unit: string | null;
  reference?: {
    min: number | null;
    max: number | null;
    origin?: string;
  } | null;
  status: string;
  reason?: string | null;
  confidence?: number | null;
  marked_deviation?: boolean;
  prior?: {
    note?: string | null;
    comparable?: boolean;
  } | null;
  evidence?: {
    raw_text?: string;
    page?: number | null;
  } | null;
}

export interface RawNutritionHighlight {
  title?: string;
  subtitle?: string;
  image_key?: string;
}

export interface ResolvedFoodCard {
  title: string;
  subtitle: string;
  imageKey: string;
  imageUrl: string;
}

export interface ParameterSummaryStats {
  total: number;
  normalCount: number;
  attentionCount: number;
  otherCount: number;
  anomalyParams: LabParameter[];
  allParams: LabParameter[];
}

export interface LoadingStageInfo {
  stageIndex: number;
  progressPercent: number;
  activeMessage: string;
}

export const LOADING_MESSAGES: readonly string[] = [
  'Lecture de votre document…',
  'Identification des paramètres biologiques…',
  'Vérification des valeurs de référence…',
  'Préparation de vos explications…'
];

export const FOOD_IMAGE_MAP: Readonly<Record<string, string>> = {
  almonds_walnuts: 'assets/foods/almonds_walnuts.jpg',
  walnuts: 'assets/foods/walnuts.jpg',
  pumpkin_seeds: 'assets/foods/pumpkin_seeds.jpg',
  spinach: 'assets/foods/spinach.jpg',
  lentils_chickpeas: 'assets/foods/lentils_chickpeas.jpg',
  fish: 'assets/foods/fish.jpg',
  fruits: 'assets/foods/fruits.jpg',
  whole_grains: 'assets/foods/whole_grains.jpg',
  vegetables: 'assets/foods/vegetables.jpg',
  dairy_yogurt: 'assets/foods/dairy_yogurt.jpg',
  eggs_protein: 'assets/foods/eggs_protein.jpg',
  avocado_olive_oil: 'assets/foods/avocado_olive_oil.jpg',
  dark_chocolate: 'assets/foods/dark_chocolate.jpg',
  hydration_water: 'assets/foods/hydration_water.jpg'
};

const FOOD_SEMANTIC_STEMS: ReadonlyArray<readonly [string, readonly string[]]> = [
  ['walnuts', ['cerneau', 'noix de grenoble', 'noix']],
  ['almonds_walnuts', ['amand', 'noisett', 'oleagineu', 'pistach', 'cajou']],
  ['pumpkin_seeds', ['courge', 'graine', 'sesame', 'tournesol', 'chia', 'lin']],
  ['spinach', ['epinard', 'bette', 'feuille verte', 'cresson', 'roquette', 'mache']],
  ['lentils_chickpeas', ['lentill', 'chiche', 'haricot sec', 'haricots', 'legumineus', 'pois', 'feve']],
  ['fish', ['poisson', 'saumon', 'sardine', 'maquereau', 'hareng', 'truite', 'thon', 'merlu', 'cabillaud']],
  ['fruits', ['fruit', 'orange', 'agrume', 'pomme', 'kiwi', 'baie', 'fraise', 'banane', 'citron', 'myrtille']],
  ['whole_grains', ['cereal', 'complet', 'avoine', 'quinoa', 'riz', 'pain', 'seigle', 'ble', 'sarrasin']],
  ['vegetables', ['legume', 'brocoli', 'carotte', 'poivron', 'courgette', 'tomate', 'haricot vert', 'chou']],
  ['dairy_yogurt', ['produit laitier', 'produits laitiers', 'laitier', 'yaourt', 'fromage', 'kefir', 'lait']],
  ['eggs_protein', ['oeuf', 'volaille', 'poulet', 'dinde', 'viande maigre', 'proteine']],
  ['avocado_olive_oil', ['avocat', 'huile d olive', 'olive', 'colza', 'lipide vegeta']],
  ['dark_chocolate', ['chocolat', 'cacao']],
  ['hydration_water', ['eau', 'hydrat', 'infusion', 'tisane', 'boisson']]
];

export function stripAccents(value: string): string {
  return (value || '')
    .normalize('NFKD')
    .replace(/[\u0300-\u036f]/g, '')
    .toLowerCase()
    .trim();
}

export function isPlaceholderLabel(text: unknown): boolean {
  const clean = String(text || '').trim();
  if (!clean) return true;
  return /\b\d+\s*[àa-]\s*\d+\s+(?:rep[eè]res?|actions?|questions?|conseils?|exemples?|phrases?)\b/i.test(clean);
}

function matchesSemanticStem(normalizedText: string, stem: string): boolean {
  if (stem.includes(' ')) {
    return normalizedText.includes(stem);
  }
  const escaped = stem.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
  return new RegExp(`\\b${escaped}\\w*`, 'i').test(normalizedText);
}

function findSemanticFoodKey(
  title: string,
  subtitle: string,
  usedKeys: Set<string>,
  failedKeys: Set<string>
): string | null {
  const normTitle = stripAccents(title);
  const normBoth = stripAccents(`${title} ${subtitle}`);

  for (const text of [normTitle, normBoth]) {
    for (const [key, stems] of FOOD_SEMANTIC_STEMS) {
      if (usedKeys.has(key) || failedKeys.has(key) || !FOOD_IMAGE_MAP[key]) continue;
      if (stems.some((stem) => matchesSemanticStem(text, stem))) {
        return key;
      }
    }
  }
  return null;
}

/**
 * Resolves nutrition highlights into visual cards.
 * Guarantees:
 * 1. Every returned card has a real, pertinent, loaded image URL.
 * 2. No image is ever reused across multiple cards.
 * 3. Any card lacking a unique pertinent image (or whose image failed to load) is excluded.
 */
export function resolveNutritionHighlights(
  highlights: readonly RawNutritionHighlight[] | null | undefined,
  failedKeys: ReadonlySet<string> = new Set<string>()
): ResolvedFoodCard[] {
  if (!Array.isArray(highlights) || !highlights.length) {
    return [];
  }

  const usedKeys = new Set<string>();
  const failed = new Set<string>(failedKeys);
  const result: ResolvedFoodCard[] = [];

  for (const item of highlights) {
    const title = String(item?.title || '').trim();
    const subtitle = String(item?.subtitle || '').trim();
    if (!title || !subtitle || isPlaceholderLabel(title) || isPlaceholderLabel(subtitle)) {
      continue;
    }

    const rawKey = String(item?.image_key || '').trim();
    if (rawKey && rawKey !== 'neutral' && failed.has(rawKey)) {
      continue;
    }

    let chosenKey: string | null = null;

    // Prefer explicit backend image_key when it is valid, unused, non-neutral, and matches title semantics (or no better semantic override)
    if (
      rawKey &&
      rawKey !== 'neutral' &&
      FOOD_IMAGE_MAP[rawKey] &&
      !usedKeys.has(rawKey)
    ) {
      const semanticOverride = findSemanticFoodKey(title, '', usedKeys, failed);
      // If title explicitly refers to e.g. "Noix" while backend sent "almonds_walnuts", prefer "walnuts"
      if (semanticOverride && semanticOverride !== rawKey) {
        chosenKey = semanticOverride;
      } else {
        chosenKey = rawKey;
      }
    } else {
      chosenKey = findSemanticFoodKey(title, subtitle, usedKeys, failed);
    }

    if (!chosenKey || !FOOD_IMAGE_MAP[chosenKey] || usedKeys.has(chosenKey) || failed.has(chosenKey)) {
      continue;
    }

    usedKeys.add(chosenKey);
    result.push({
      title,
      subtitle,
      imageKey: chosenKey,
      imageUrl: FOOD_IMAGE_MAP[chosenKey]
    });
  }

  return result;
}

export function isRawCode(code: string | null | undefined): boolean {
  return String(code || '').startsWith('RAW_');
}

export function formatDisplayCode(code: string | null | undefined): string {
  const clean = String(code || '').trim();
  if (!clean || isRawCode(clean)) {
    return '';
  }
  return clean;
}

export function summarizeParameters(parameters: readonly LabParameter[] | null | undefined): ParameterSummaryStats {
  const allParams = Array.isArray(parameters) ? [...parameters] : [];
  const anomalyParams = allParams.filter(
    (p) => p.status === 'below_reference' || p.status === 'above_reference'
  );
  const normalCount = allParams.filter((p) => p.status === 'within_reference').length;
  const attentionCount = anomalyParams.length;
  const otherCount = allParams.length - normalCount - attentionCount;

  return {
    total: allParams.length,
    normalCount,
    attentionCount,
    otherCount,
    anomalyParams,
    allParams
  };
}

export function computeLoadingStage(
  task: {
    status?: string;
    document?: { extraction_method?: string | null } | null;
    parameters?: unknown[] | null;
    explanations?: unknown | null;
  } | null | undefined,
  elapsedSeconds: number
): LoadingStageInfo {
  const status = task?.status || 'received';
  if (status === 'done') {
    return {
      stageIndex: 4,
      progressPercent: 100,
      activeMessage: LOADING_MESSAGES[3]
    };
  }

  let stageIndex = 0;
  if (task?.explanations) {
    stageIndex = 3;
  } else if (Array.isArray(task?.parameters) && task.parameters.length > 0) {
    stageIndex = 2;
  } else if (task?.document?.extraction_method) {
    stageIndex = 1;
  } else if (status === 'processing') {
    // Backend runs extraction + identification + validation + generation inside background task
    // Advance stages gracefully with elapsed time without ever faking 100% completion
    if (elapsedSeconds >= 8) {
      stageIndex = 3;
    } else if (elapsedSeconds >= 5) {
      stageIndex = 2;
    } else if (elapsedSeconds >= 2) {
      stageIndex = 1;
    }
  }

  const stageBaseProgress = [18, 42, 66, 82];
  const base = stageBaseProgress[stageIndex] ?? 18;
  // Smooth subtle increment capped strictly at 88% while backend is still processing
  const bonus = stageIndex === 3 ? Math.min(6, Math.floor(Math.max(0, elapsedSeconds - 8) / 3)) : 0;
  const progressPercent = Math.min(88, base + bonus);

  return {
    stageIndex,
    progressPercent,
    activeMessage: LOADING_MESSAGES[stageIndex] ?? LOADING_MESSAGES[0]
  };
}
