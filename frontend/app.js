/**
 * Sinematica AI Studio — Main Frontend SPA Application Logic
 */

let currentStoryboard = null;
let storyPartContinuationRequested = false;
let currentJobId = null;
let pollTimer = null;
let selectedRefFiles = [];
let selectedAffiliateProductFiles = [];
const MAX_STORYBOARD_REFERENCE_IMAGES = 7;
let selectedRenderClips = []; // ordered {job_id, filename, label} picked from Gallery for Auto Render
const selectedHistoryIndexes = new Set();
let gallerySeoContexts = new Map();
let storyboardImportMode = 'new';
let storyboardImportController = null;

function getUgcConversionBrief() {
  const value = id => document.getElementById(id)?.value?.trim?.() || '';
  return {
    enabled: Boolean(value('ugcAudience') || value('ugcConversionHook') || value('ugcProblem')),
    audience: value('ugcAudience'), objective: value('ugcObjective') || 'product_click',
    why_now: value('ugcWhyNow'), awareness_level: value('ugcAwareness') || 'problem_aware',
    hook_type: value('ugcHookType') || 'problem', hook: value('ugcConversionHook'),
    angle: value('ugcAngle'), problem: value('ugcProblem'), agitate: value('ugcAgitate'),
    solution: value('ugcSolution'), proof: value('ugcProof'), cta: value('ugcConversionCta'),
    test_variable: value('ugcTestVariable') || 'hook', variant_count: Number(value('ugcVariantCount') || 3),
  };
}

function auditUgcConversionBrief(brief) {
  const required = [['audience', 'audiens'], ['hook', 'hook'], ['problem', 'problem'], ['solution', 'solution'], ['proof', 'proof'], ['cta', 'CTA']];
  const missing = required.filter(([key]) => !brief[key]).map(([, label]) => label);
  return { ready: brief.enabled && !missing.length, missing };
}

function calculateUgcFunnelMetrics(values) {
  const rate = (part, whole) => whole > 0 ? Number((part / whole * 100).toFixed(2)) : null;
  return {
    hookRate: rate(values.threeSecond, values.impressions),
    holdRate: rate(values.completed, values.threeSecond),
    ctr: rate(values.clicks, values.impressions),
    cvr: rate(values.purchases, values.clicks),
    roas: values.spend > 0 ? Number((values.revenue / values.spend).toFixed(2)) : null,
  };
}

function getYoutubeBlueprintInput() {
  const value = id => document.getElementById(id)?.value?.trim?.() || '';
  return {
    format: value('ytFormat'), market: value('ytMarket'), language: value('ytLanguage'),
    microNiche: value('ytMicroNiche'), audience: value('ytAudience'), promise: value('ytPromise'),
    demand: value('ytDemand'), gap: value('ytGap'), angle: value('ytAngle'), hook: value('ytHook'),
    openLoop: value('ytOpenLoop'), payoff: value('ytPayoff'), brand: value('ytBrand'),
    colors: value('ytColors'), font: value('ytFont'), mainKeyword: value('ytMainKeyword'),
    relevantKeywords: value('ytRelevantKeywords'), longTail: value('ytLongTail'), sources: value('ytSources'),
    editorialThesis: value('ytEditorialThesis'), contentMoat: value('ytContentMoat'),
    fleetGovernance: value('ytFleetGovernance'), productionCost: value('ytProductionCost'),
    aiDisclosure: value('ytAiDisclosure'), humanContribution: value('ytHumanContribution'),
    localizationQa: value('ytLocalizationQa'), audioQa: value('ytAudioQa'),
    continuityLedger: value('ytContinuityLedger'), loopLedger: value('ytLoopLedger'), riskRegister: value('ytRiskRegister'),
    gates: ['Evidence', 'Originality', 'Rights', 'Promise', 'Technical'].filter(name => document.getElementById(`ytGate${name}`)?.checked),
  };
}

function diagnoseYoutubeMetrics({ ctr, hookRetention, avd, endRetention, shape, trafficSource = 'unknown', newViewers = null, returningViewers = null, revenue = null, hours = null, cost = null }) {
  const notes = [];
  if (ctr != null && hookRetention != null) {
    if (ctr < 4 && hookRetention >= 60) notes.push('Packaging lemah tetapi isi awal relatif menahan: uji judul/thumbnail, jangan ubah seluruh video sekaligus.');
    if (ctr >= 6 && hookRetention < 50) notes.push('Klik ada tetapi pembuka tidak memenuhi janji: selaraskan judul/thumbnail dengan kalimat dan visual pertama.');
  }
  if (shape === 'early_drop') notes.push('Drop awal: audit promise mismatch, bumper, basa-basi, kualitas VO, dan visual pertama.');
  if (shape === 'gradual') notes.push('Penurunan gradual: audit repetisi, kepadatan informasi, variasi pacing, serta visual/audio yang terlalu seragam.');
  if (shape === 'mid_dip') notes.push('Dip tengah: cocokkan timestamp dengan naskah; ringkas segmen, beri konteks/metafora, atau pindahkan bukti lebih awal.');
  if (shape === 'spike') notes.push('Spike adalah sinyal rewatch: tandai timestamp dan hipotesiskan elemen penyebab sebelum direplikasi.');
  if (shape === 'stable') notes.push('Retensi relatif stabil: pertahankan struktur dan uji satu variabel packaging atau topik berikutnya.');
  if (avd != null && endRetention != null && avd > 0 && endRetention < avd * .5) notes.push('Akhir turun jauh: kurangi sinyal penutupan dan hubungkan payoff langsung ke video lanjutan yang relevan.');
  if (trafficSource === 'search') notes.push('Search dominan: nilai kecocokan intent dan apakah video mengubah pencari baru menjadi returning viewer; jangan bandingkan CTR mentah dengan Browse.');
  if (trafficSource === 'browse' || trafficSource === 'suggested') notes.push('Traffic rekomendasi: audit kombinasi packaging, kepuasan setelah klik, dan kedekatan topik dengan katalog—bukan thumbnail secara terpisah.');
  if (newViewers != null && returningViewers != null) {
    if (newViewers > returningViewers * 4) notes.push('Akuisisi kuat tetapi audiens kembali relatif kecil: bangun seri, format berulang yang bernilai, dan next-view bridge yang relevan.');
    else if (returningViewers > newViewers * 2) notes.push('Loyalitas kuat tetapi jangkauan baru terbatas: uji topik masuk, angle, dan packaging untuk audiens yang belum mengenal channel.');
    else notes.push('Komposisi new/returning viewer relatif seimbang; tandai video mana yang berfungsi sebagai acquisition dan mana yang membangun loyalty.');
  }
  if (revenue != null && hours != null && hours > 0) notes.push(`Revenue per production hour: ${(revenue / hours).toFixed(2)}. Bandingkan dengan biaya dan performa katalog, bukan RPM saja.`);
  if (revenue != null && cost != null) notes.push(`Contribution video sebelum overhead: ${(revenue - cost).toFixed(2)}.`);
  return notes.length ? notes : ['Data belum cukup untuk diagnosis. Isi metrik dan bentuk grafik dari YouTube Studio.'];
}

const CONTENT_UNIVERSE_PROFILES = {
  toddler: { label: 'Balita 2–4', subjects: ['tebak bunyi di rumah', 'warna yang hilang dari taman', 'rutinitas tidur si kecil', 'gerak dan berhenti bersama hewan', 'lima benda untuk dihitung'], voice: 'kalimat sangat pendek, pengulangan hangat, satu instruksi per beat', pacing: 'shot tenang dan mudah dibaca; beri jeda nyata untuk menjawab', guard: 'tokoh non-manusia yang ramah, konflik sangat ringan, tanpa bahaya tiruan atau CTA manipulatif', children: true },
  early_child: { label: 'Anak awal 5–7', subjects: ['tim penolong hewan kecil', 'detektif pola yang hilang', 'hari pertama teman baru', 'benih ajaib yang perlu dirawat', 'belajar jujur setelah kesalahan kecil'], voice: 'jelas, konkret, suportif, dialog bergiliran', pacing: 'aksi sebab-akibat sederhana dan partisipasi anak', guard: 'resolusi aman, koreksi lembut, tanpa mempermalukan atau menakut-nakuti', children: true },
  older_child: { label: 'Anak besar 8–10', subjects: ['misteri perpustakaan sekolah', 'ekspedisi sains sungai', 'persahabatan setelah salah paham', 'penyelamatan habitat hewan', 'klub penemu barang bekas'], voice: 'cerdas namun mudah diikuti, humor dan rasa ingin tahu', pacing: 'petunjuk bertahap, percobaan, konsekuensi, payoff jelas', guard: 'tanpa instruksi berbahaya; kerja sama dan pemikiran kritis', children: true },
  preteen: { label: 'Praremaja 11–13', subjects: ['rahasia proyek kelas', 'teman yang berubah setelah viral', 'kompetisi yang menguji integritas', 'misteri sejarah lingkungan', 'belajar menetapkan batas pertemanan'], voice: 'menghormati kecerdasan audiens, tidak menggurui', pacing: 'konflik sosial ringan dengan pilihan dan konsekuensi', guard: 'hindari body shaming, romantisasi bullying, dan tekanan sosial berbahaya', children: true },
  teen: { label: 'Remaja 14–17', subjects: ['persahabatan yang retak karena unggahan', 'tekanan memilih masa depan', 'identitas di balik akun anonim', 'gagal lalu mencoba kembali', 'keluarga yang tak memahami impian'], voice: 'jujur, luwes, tidak memaksakan slang', pacing: 'emosi dekat, ruang hening, visual digital dan dunia nyata', guard: 'tanpa glorifikasi self-harm, tantangan berbahaya, eksploitasi seksual, atau klaim kesehatan', children: false },
  genz_young: { label: 'Gen Z muda 18–24', subjects: ['pekerjaan pertama yang tak sesuai bayangan', 'pertemanan delapan tahun yang mendadak sunyi', 'biaya hidup dan mimpi merantau', 'hubungan tanpa kepastian', 'eksperimen lepas media sosial'], voice: 'conversational, sadar diri, spesifik, tidak sok gaul', pacing: 'cold open kuat, detail keseharian, micro-reveal', guard: 'hindari diagnosis mental dan janji finansial tanpa sumber', children: false },
  genz_adult: { label: 'Gen Z dewasa 25–29', subjects: ['quarter-life reset', 'menikah atau mengejar karier', 'pulang setelah gagal di kota', 'teman yang tumbuh ke arah berbeda', 'membangun hidup tanpa peta lama'], voice: 'intim, reflektif, merakyat', pacing: 'dialog natural, gestur kecil, payoff emosional', guard: 'konflik dewasa tanpa manipulasi atau stereotip generasi', children: false },
  millennial: { label: 'Milenial 30–44', subjects: ['drama rumah tangga realistis', 'sandwich generation', 'konflik pekerjaan dan keluarga', 'rumah pertama dan tekanan finansial', 'pernikahan setelah masa romantis', 'parenting tanpa kehilangan identitas', 'nostalgia 1990–2000-an', 'burnout dan memulai ulang hidup', 'kisah bisnis kecil', 'dokumenter perubahan teknologi', 'renovasi dan kehidupan rumah', 'true story keputusan finansial', 'misteri keluarga dan warisan'], voice: 'hangat, membumi, panggilan keluarga yang luwes', pacing: 'drama situasional, konsekuensi nyata, close-up emosi seperlunya', guard: 'klaim finansial/kesehatan harus bersumber; jangan mengeksploitasi penderitaan', children: false },
  genx: { label: 'Gen X 45–59', subjects: ['karier kedua setelah PHK', 'anak dewasa meninggalkan rumah', 'warisan yang memecah saudara', 'menjaga orang tua sambil bekerja', 'profesi lama yang mulai hilang'], voice: 'tenang, jelas, berbobot tanpa menggurui', pacing: 'lebih lapang, bukti dan konteks diberi waktu', guard: 'hindari ageism dan solusi hidup yang terlalu sederhana', children: false },
  senior: { label: 'Senior 60+', subjects: ['dua cangkir teh setiap sore', 'surat lama untuk cucu', 'resep keluarga dan cerita di baliknya', 'persahabatan yang ditemukan kembali', 'kampung yang berubah setelah puluhan tahun'], voice: 'jelas, hangat, tempo nyaman, istilah sederhana', pacing: 'shot lebih panjang, wajah dan tindakan mudah dibaca, subtitle besar', guard: 'kontras tinggi, audio bersih; hindari infantilization, fear marketing, serta nasihat medis tanpa ahli', children: false },
  family: { label: 'Keluarga lintas generasi', subjects: ['cucu mengajari nenek teknologi', 'resep lama menyatukan tiga generasi', 'rumah warisan menyimpan surat', 'bertukar pekerjaan sehari', 'lagu lama membuka rahasia keluarga'], voice: 'setiap generasi punya cara bicara berbeda namun saling menghormati', pacing: 'parallel action dan reaksi antargenerasi yang jelas', guard: 'hindari stereotip usia; konflik ditutup dengan pemahaman, bukan ceramah', children: false },
};

const STORY_CONFLICTS = {
  toddler: ['benda favorit hilang', 'belum memahami giliran', 'takut mencoba hal aman', 'rutinitas berubah'],
  early_child: ['salah paham dengan teman', 'gagal pada percobaan pertama', 'harus berkata jujur', 'belajar meminta bantuan'],
  older_child: ['petunjuk saling bertentangan', 'kerja tim tidak kompak', 'pilihan adil yang sulit', 'kesalahan perlu diperbaiki'],
  preteen: ['tekanan kelompok', 'batas pertemanan', 'takut dianggap berbeda', 'integritas saat berkompetisi'],
  teen: ['tekanan masa depan', 'konflik pertemanan digital', 'ekspektasi keluarga', 'identitas dan penerimaan diri'],
  genz_young: ['pekerjaan pertama mengecewakan', 'biaya hidup meningkat', 'hubungan tanpa kepastian', 'pertemanan menjauh'],
  genz_adult: ['karier atau hubungan', 'pulang setelah gagal', 'takut tertinggal', 'memulai ulang tanpa dukungan'],
  millennial: ['orang tua sakit dan biaya sekolah anak', 'kehilangan pekerjaan diam-diam', 'konflik pembagian tanggung jawab', 'utang rumah tersembunyi', 'menunda impian pribadi', 'bisnis kecil hampir tutup', 'saudara berebut warisan'],
  genx: ['PHK dan karier kedua', 'anak dewasa meninggalkan rumah', 'merawat orang tua', 'warisan memecah saudara'],
  senior: ['kesepian setelah kehilangan pasangan', 'hubungan renggang dengan anak', 'kampung berubah', 'rahasia lama ditemukan'],
  family: ['nilai lama bertemu kebiasaan baru', 'rumah warisan diperebutkan', 'salah paham tiga generasi', 'tradisi keluarga hampir hilang'],
  general: ['keinginan terhalang pilihan sulit', 'rahasia mengubah hubungan', 'kesalahan memunculkan konsekuensi', 'kesempatan kedua datang terlambat']
};

const usedDracinCombinations = new Set();
function generateDracinThemeOptions(count = 8) {
  const leads = ['pemilik warung yang diremehkan', 'perawat kontrak yang pendiam', 'arsitek muda dari kampung', 'ayah tunggal pengemudi malam', 'pengacara bantuan hukum', 'penjahit rumahan', 'mantan atlet yang jatuh miskin', 'karyawan gudang yang jujur', 'janda pemilik toko bunga', 'guru honorer'];
  const triggers = ['menemukan surat wasiat yang sengaja disembunyikan', 'dituduh mencuri di depan keluarga besar', 'harus menggantikan saudara pada sebuah pernikahan', 'menolong orang asing saat kecelakaan', 'menerima pesan dari seseorang yang dianggap meninggal', 'menang lelang rumah masa kecilnya', 'menemukan bayi dengan liontin keluarga', 'dipaksa menandatangani utang yang bukan miliknya'];
  const secrets = ['ternyata pewaris perusahaan saingan', 'menyimpan bukti korupsi keluarga terpandang', 'adalah cinta pertama sang direktur', 'mempunyai saudara kembar yang mengambil identitasnya', 'diam-diam pemegang saham mayoritas', 'merupakan anak yang tertukar dua puluh tahun lalu', 'pernah menyelamatkan tokoh berkuasa saat kecil', 'memegang rekaman yang dapat membalikkan seluruh perkara'];
  const stakes = ['sebelum pesta pernikahan dimulai', 'ketika perusahaan berada di ambang bangkrut', 'di tengah perebutan hak asuh', 'saat kampung mereka akan digusur', 'menjelang pembacaan warisan', 'ketika skandal itu disiarkan langsung', 'sebelum kontrak pernikahan berakhir', 'pada malam reuni keluarga'];
  const tones = ['romansa perlahan', 'misteri keluarga', 'balas dendam elegan', 'drama kelas sosial', 'pengorbanan orang tua', 'second-chance romance', 'thriller korporat', 'melodrama merakyat'];
  const shuffle = items => {
    const result = [...items];
    for (let index = result.length - 1; index > 0; index--) {
      const swapIndex = Math.floor(Math.random() * (index + 1));
      [result[index], result[swapIndex]] = [result[swapIndex], result[index]];
    }
    return result;
  };
  const shuffled = {
    leads: shuffle(leads), triggers: shuffle(triggers), secrets: shuffle(secrets),
    stakes: shuffle(stakes), tones: shuffle(tones)
  };
  const results = [];
  for (let index = 0; index < Math.min(count, 8); index++) {
    let theme = `${shuffled.leads[index]} ${shuffled.triggers[index]}; ${shuffled.secrets[index]} ${shuffled.stakes[index]}. Nada: ${shuffled.tones[index]}.`;
    if (usedDracinCombinations.has(theme)) {
      const nextSecret = shuffled.secrets[(index + 1) % shuffled.secrets.length];
      const nextStake = shuffled.stakes[(index + 2) % shuffled.stakes.length];
      theme = `${shuffled.leads[index]} ${shuffled.triggers[index]}; ${nextSecret} ${nextStake}. Nada: ${shuffled.tones[index]}.`;
    }
    usedDracinCombinations.add(theme);
    results.push(theme.charAt(0).toUpperCase() + theme.slice(1));
  }
  if (usedDracinCombinations.size > 80) [...usedDracinCombinations].slice(0, 40).forEach(item => usedDracinCombinations.delete(item));
  return results;
}

let selectedUniverseIdea = null;
function buildContentUniverse(input) {
  const profile = CONTENT_UNIVERSE_PROFILES[input.audience] || CONTENT_UNIVERSE_PROFILES.millennial;
  const emotion = { belonging: 'merasa dipahami', curiosity: 'penasaran', hope: 'harapan', comfort: 'ketenangan', confidence: 'percaya diri', nostalgia: 'nostalgia', laughter: 'tawa' }[input.emotion] || 'penasaran';
  const goal = { entertain: 'menghibur', learn: 'memberi pemahaman praktis', relax: 'menenangkan', reflect: 'mengajak merenung', solve: 'memberi jalan keluar', connect: 'memantik percakapan bersama' }[input.goal] || 'menghibur';
  return Array.from({ length: 10 }, (_, index) => {
    const subject = profile.subjects[index % profile.subjects.length];
    const variant = Math.floor(index / profile.subjects.length) + 1;
    const context = input.context ? ` dalam konteks ${input.context}` : '';
    const title = `${subject.charAt(0).toUpperCase()}${subject.slice(1)}${variant > 1 ? ` — Sudut ${variant}` : ''}`;
    const hook = index % 2 === 0 ? `Satu hal kecil hari itu mengubah cara mereka melihat ${subject}.` : `Tak seorang pun menyangka masalah ${subject} dimulai dari keputusan sederhana.`;
    return { id: `universe-${index + 1}`, title, audience: profile.label, premise: `${title}${context}. Cerita dirancang untuk ${goal} dan meninggalkan rasa ${emotion}, dengan konflik yang relevan bagi ${profile.label} serta akhir yang benar-benar membayar janji pembuka.`, hook, arc: `Keseharian → gangguan spesifik → pilihan → konsekuensi → bukti/perubahan → payoff ${emotion}.`, voice: profile.voice, direction: `${profile.pacing}. Kamera bergerak karena perhatian tokoh dan makna adegan; ambience sesuai lokasi, foley hanya pada aksi penting.`, guard: profile.guard, language: input.language, country: input.country, genre: input.genre, format: input.format, complexity: input.complexity, children: profile.children };
  });
}

// Groups terminal log lines into a small set of colors: error/warning (from backend level),
// success (completion messages), profile (Chrome worker actions), or default system info.
function logLineCategory(l) {
  if (l.level === 'error') return 'error';
  if (l.level === 'warning') return 'warning';
  if (/✅|🎬|selesai 100%/.test(l.message)) return 'success';
  if (l.profile && l.profile !== 'System') return 'profile';
  return 'info';
}

document.addEventListener('DOMContentLoaded', () => {
  initSidebarToggle();
  initNavigation();
  initStatusPolling();
  initFleetTestPrompt();
  initDropzone();
  relocateStoryTargetingControls();
  initStoryboardForm();
  initGallery();
  initSettingsModal();
  initSeoKitModal();
  initStoryboardHistoryModal();
  initStoryboardImportModal();
  renderHistoryTab();
  initCustomAlertModal();
  loadLastStoryboard();
  initAspectRatioDefault();
  initFinishingLookPicker();
  restoreLastJobExecution();
});

function initSidebarToggle() {
  const sidebar = document.querySelector('.sidebar');
  const toggle = document.getElementById('sidebarToggleBtn');
  if (!sidebar || !toggle) return;

  const storageKey = 'sinematica_sidebar_collapsed';
  const navItems = [...sidebar.querySelectorAll('.nav-item')];
  navItems.forEach(item => {
    const labelNode = item.cloneNode(true);
    labelNode.querySelectorAll('.nav-icon, .badge-count').forEach(node => node.remove());
    const label = labelNode.textContent.replace(/\s+/g, ' ').trim();
    if (label) item.dataset.sidebarLabel = label;
  });

  const applyState = collapsed => {
    const desktop = window.matchMedia('(min-width: 851px)').matches;
    const active = desktop && collapsed;
    sidebar.classList.toggle('sidebar-collapsed', active);
    toggle.setAttribute('aria-expanded', String(!active));
    toggle.setAttribute('aria-label', active ? 'Expand sidebar' : 'Minimize sidebar');
    toggle.title = active ? 'Expand sidebar' : 'Minimize sidebar';
    toggle.querySelector('span').textContent = active ? '›' : '‹';
    navItems.forEach(item => {
      item.title = active ? (item.dataset.sidebarLabel || '') : '';
    });
  };

  let preferredCollapsed = localStorage.getItem(storageKey) === 'true';
  applyState(preferredCollapsed);
  toggle.addEventListener('click', () => {
    preferredCollapsed = !sidebar.classList.contains('sidebar-collapsed');
    localStorage.setItem(storageKey, String(preferredCollapsed));
    applyState(preferredCollapsed);
  });
  window.addEventListener('resize', () => applyState(preferredCollapsed));
}

/**
 * Keep audience and theme choices close to the story inputs. Moving the existing
 * nodes preserves every ID, value, and event listener used by storyboard generation.
 */
function relocateStoryTargetingControls() {
  const destination = document.getElementById('storyTargetingControls');
  if (!destination) return;

  const affiliateGroup = document.getElementById('chkAffiliateMode')?.closest('.form-group');
  const aspectGroup = document.getElementById('aspectSelect')?.closest('.form-group');
  if (affiliateGroup && aspectGroup) {
    const primaryRow = document.createElement('div');
    primaryRow.className = 'affiliate-aspect-row';
    primaryRow.append(affiliateGroup, aspectGroup);
    destination.appendChild(primaryRow);
  }

  const targetRow = document.querySelector('.story-target-row');
  if (targetRow) destination.appendChild(targetRow);

  ['dracinThemeSelect'].forEach((controlId) => {
    const control = document.getElementById(controlId);
    const group = control?.closest('.form-group');
    if (group) destination.appendChild(group);
  });

  const productionColumn = document.getElementById('productionParametersColumn');
  const durationBadge = document.getElementById('totalDurationLabel');
  if (productionColumn && durationBadge) {
    durationBadge.style.marginBottom = '0';
    durationBadge.style.marginTop = '0';
    durationBadge.style.flexWrap = 'nowrap';
    durationBadge.style.whiteSpace = 'nowrap';
    durationBadge.style.justifyContent = 'flex-start';
    durationBadge.style.fontSize = '12px';
    productionColumn.appendChild(durationBadge);
  }
}

const FINISHING_LOOK_OPTIONS = {
  vibe: {
    // The generated vibe sheet contains four tall panels in a 2:1 canvas.
    // Render it as a 4x2 surface and crop the vertical centre to avoid stretching faces.
    selectId: 'visualVibeSelect', sprite: '/assets/style-previews/vibe-sprite.png?v=3', columns: 4, rows: 1,
    backgroundSize: '400% auto', cropY: '50%',
    items: [
      { value: 'none', label: 'Auto AI', neutral: true },
      { value: 'pro_cinematic', label: 'Pro Cinematic', spriteIndex: 0 },
      { value: 'clean_commercial', label: 'Clean Commercial', spriteIndex: 1 },
      { value: 'documentary', label: 'Documentary', spriteIndex: 2 },
      { value: 'sci_fi', label: 'Sci-Fi', spriteIndex: 3 },
      { value: 'ugc_natural', label: 'UGC Natural', sprite: '/assets/style-previews/vibe-social-drama-sprite.png?v=1', columns: 4, rows: 1, backgroundSize: '400% auto', cropY: '50%', spriteIndex: 0 },
      { value: 'korean_drama', label: 'Drama Korea', sprite: '/assets/style-previews/vibe-social-drama-sprite.png?v=1', columns: 4, rows: 1, backgroundSize: '400% auto', cropY: '50%', spriteIndex: 1 },
      { value: 'microdrama', label: 'Microdrama', sprite: '/assets/style-previews/vibe-social-drama-sprite.png?v=1', columns: 4, rows: 1, backgroundSize: '400% auto', cropY: '50%', spriteIndex: 2 },
      { value: 'kids_colorful', label: 'Kids Colorful', sprite: '/assets/style-previews/vibe-social-drama-sprite.png?v=1', columns: 4, rows: 1, backgroundSize: '400% auto', cropY: '50%', spriteIndex: 3 },
      { value: 'cozy_lifestyle', label: 'Cozy Lifestyle', sprite: '/assets/style-previews/vibe-premium-mood-sprite.png?v=1', columns: 3, rows: 1, backgroundSize: '300% auto', cropY: '50%', spriteIndex: 0 },
      { value: 'luxury_premium', label: 'Luxury Premium', sprite: '/assets/style-previews/vibe-premium-mood-sprite.png?v=1', columns: 3, rows: 1, backgroundSize: '300% auto', cropY: '50%', spriteIndex: 1 },
      { value: 'dark_thriller', label: 'Dark Thriller', sprite: '/assets/style-previews/vibe-premium-mood-sprite.png?v=1', columns: 3, rows: 1, backgroundSize: '300% auto', cropY: '50%', spriteIndex: 2 }
    ]
  },
  lighting: {
    selectId: 'lightingStyleSelect', sprite: '/assets/style-previews/lighting-sprite.png', columns: 4, rows: 2,
    items: [
      { value: 'none', label: 'Auto', spriteIndex: 7 },
      { value: 'soft_light', label: 'Soft Light', spriteIndex: 0 },
      { value: 'golden_hour', label: 'Golden Hour', spriteIndex: 1 },
      { value: 'volumetric', label: 'Volumetric', spriteIndex: 2 },
      { value: 'chiaroscuro', label: 'Chiaroscuro', spriteIndex: 3 },
      { value: 'low_key', label: 'Low Key', spriteIndex: 4 },
      { value: 'backlight', label: 'Backlight', spriteIndex: 5 },
      { value: 'rainy', label: 'Rainy', spriteIndex: 6 }
    ]
  },
  color: {
    selectId: 'colorPaletteSelect', sprite: '/assets/style-previews/color-sprite.png', columns: 4, rows: 2,
    items: [
      { value: 'none', label: 'Auto', spriteIndex: 7 },
      { value: 'warm', label: 'Warm', spriteIndex: 0 },
      { value: 'cool', label: 'Cool', spriteIndex: 1 },
      { value: 'vibrant', label: 'Vibrant', spriteIndex: 2 },
      { value: 'pastel', label: 'Pastel', spriteIndex: 3 },
      { value: 'earthy', label: 'Earthy', spriteIndex: 4 },
      { value: 'complementary', label: 'Complementary', spriteIndex: 5 },
      { value: 'teal_orange', label: 'Teal–Orange', spriteIndex: 6 }
    ]
  }
};

function finishSpritePosition(index, columns, rows, cropY = null) {
  const column = index % columns;
  const row = Math.floor(index / columns);
  const x = columns === 1 ? 0 : (column / (columns - 1)) * 100;
  const y = cropY ?? (rows === 1 ? 0 : (row / (rows - 1)) * 100);
  const yCss = typeof y === 'number' ? `${y}%` : String(y);
  return `${x}% ${yCss}`;
}

function initFinishingLookPicker() {
  const grid = document.getElementById('finishingLookCardGrid');
  if (!grid) return;
  let activeTab = 'vibe';

  const render = () => {
    const config = FINISHING_LOOK_OPTIONS[activeTab];
    const select = document.getElementById(config.selectId);
    grid.dataset.finishGrid = activeTab;
    grid.innerHTML = config.items.map(item => {
      const active = select?.value === item.value;
      const columns = item.columns || config.columns;
      const rows = item.rows || config.rows;
      const cropY = item.cropY || config.cropY;
      const sprite = item.sprite || config.sprite;
      const backgroundSize = item.backgroundSize || config.backgroundSize || `${columns * 100}% ${rows * 100}%`;
      const imageStyle = item.neutral
        ? 'background:radial-gradient(circle at 50% 45%,#475569 0 13%,#1e293b 14% 38%,#0f172a 39%);'
        : `background-image:url('${sprite}');background-size:${backgroundSize};background-position:${finishSpritePosition(item.spriteIndex, columns, rows, cropY)};`;
      return `<button type="button" class="finish-preview-card${active ? ' active' : ''}" data-finish-value="${item.value}" title="${item.label}">
        <span class="finish-preview-image" style="${imageStyle}"></span>
        <span class="finish-preview-label">${item.label}</span><span class="finish-preview-check">✓</span>
      </button>`;
    }).join('');
    grid.querySelectorAll('.finish-preview-card').forEach(card => {
      card.addEventListener('click', () => {
        if (select) {
          select.value = card.dataset.finishValue;
          select.dispatchEvent(new Event('change'));
        }
        render();
      });
    });
  };

  document.querySelectorAll('.finish-picker-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      activeTab = tab.dataset.finishTab;
      document.querySelectorAll('.finish-picker-tab').forEach(item => item.classList.toggle('active', item === tab));
      render();
    });
  });
  Object.values(FINISHING_LOOK_OPTIONS).forEach(config => {
    document.getElementById(config.selectId)?.addEventListener('change', render);
  });
  render();
}

function initAspectRatioDefault() {
  const select = document.getElementById('aspectSelect');
  if (!select) return;
  localStorage.removeItem('sinematica_default_aspect_ratio');
  select.value = 'portrait';
}

// Toast Notifications Helper
function showToast(message, type = 'info', title = '') {
  const container = document.getElementById('toastContainer');
  if (!container) return;

  const toast = document.createElement('div');
  toast.className = `toast toast-item toast-${type}`;

  const icons = {
    info: '💡',
    success: '✅',
    warning: '⚠️',
    error: '❌'
  };

  toast.innerHTML = `
    <div style="font-size: 18px;">${icons[type] || '✨'}</div>
    <div style="flex: 1;">
      ${title ? `<div style="font-weight: bold; font-size: 13px; margin-bottom: 2px;">${title}</div>` : ''}
      <div style="font-size: 12px; color: var(--text-secondary);">${message}</div>
    </div>
  `;

  container.appendChild(toast);

  setTimeout(() => {
    toast.style.opacity = '0';
    toast.style.transform = 'translateX(20px)';
    setTimeout(() => toast.remove(), 300);
  }, 4000);
}

// Custom Alert Modal Helper
function showCustomAlert(message, title = 'Informasi Studio', icon = '✨') {
  const modal = document.getElementById('customAlertModal');
  const titleEl = document.getElementById('customAlertTitle');
  const msgEl = document.getElementById('customAlertMsg');
  const iconEl = document.getElementById('customAlertIcon');

  if (!modal) return;
  titleEl.textContent = title;
  msgEl.textContent = message;
  iconEl.textContent = icon;

  modal.classList.add('active');
}

function initCustomAlertModal() {
  const modal = document.getElementById('customAlertModal');
  const okBtn = document.getElementById('customAlertOkBtn');
  if (okBtn && modal) {
    okBtn.addEventListener('click', () => modal.classList.remove('active'));
  }
}

function storyboardImportPrompt() {
  const sceneCount = Math.max(1, parseInt(document.getElementById('externalAiSceneCount')?.value, 10)
    || parseInt(document.getElementById('sceneCountInput')?.value, 10) || 6);
  const language = document.getElementById('targetLanguageInput')?.value || 'Indonesia';
  const durationMode = document.getElementById('durationPerSceneSelect')?.value || 'auto';
  const visualStyle = document.getElementById('visualStyleSelect')?.value || 'live_action';
  const visualVibe = document.getElementById('visualVibeSelect')?.value || 'none';
  const lightingStyle = document.getElementById('lightingStyleSelect')?.value || 'none';
  const colorPalette = document.getElementById('colorPaletteSelect')?.value || 'none';
  const modalIdea = document.getElementById('externalAiStoryIdea')?.value.trim();
  const premise = modalIdea || (document.getElementById('premiseInput') || document.getElementById('themeInput'))?.value.trim();
  const durationRule = durationMode === 'auto'
    ? 'Setiap scene memakai duration 4, 6, 8, atau 10 detik sesuai kebutuhan dramatis.'
    : `Setiap scene WAJIB memakai duration ${durationMode} detik.`;

  return `Anda adalah penulis storyboard film profesional. Buat storyboard berdasarkan naskah/ide di bawah ini.

NASKAH / IDE:
${premise || '[TEMPEL ATAU TULIS NASKAH CERITA DI SINI]'}

ATURAN MUTLAK:
- Buat TEPAT ${sceneCount} scene, bernomor 1 sampai ${sceneCount}. Jangan kurang atau lebih.
- ${durationRule}
- visual_style WAJIB "${visualStyle}" dan medium visual ini harus identik di setiap karakter dan scene.
- Gunakan visual_vibe "${visualVibe}", lighting_style "${lightingStyle}", dan color_palette "${colorPalette}" secara konsisten tanpa mengganti medium utama.
- time_range harus berurutan dan berkesinambungan tanpa jeda.
- Dialog, action_summary, text_overlay, dan narration_id wajib dalam bahasa ${language}.
- prompt_for_flow wajib berupa prompt video sinematik terperinci dalam bahasa Inggris.
- Karakter, pakaian, wajah, properti, lokasi, dan alur harus konsisten.
- characters_in_scene hanya boleh menggunakan id yang terdaftar pada characters.
- start_state scene berikutnya harus melanjutkan end_state scene sebelumnya.
- text_overlay maksimal 6 kata.
- Jangan gunakan komentar, trailing comma, atau string yang tidak ditutup.

OUTPUT WAJIB JSON VALID SAJA.
JANGAN memakai markdown atau blok kode. JANGAN memberi penjelasan sebelum atau sesudah JSON.
Pastikan hasil dapat diproses langsung oleh JSON.parse(). Gunakan format persis berikut:

{
  "film_title": "Judul film",
  "genre_style": "Gaya visual dan suasana",
  "art_direction": "Arahan visual keseluruhan",
  "visual_style": "${visualStyle}",
  "visual_vibe": "${visualVibe}",
  "lighting_style": "${lightingStyle}",
  "color_palette": "${colorPalette}",
  "character_seed": 123456,
  "consistent_characters": "Ringkasan konsistensi semua karakter",
  "characters": [
    {
      "id": 1,
      "name": "Nama karakter",
      "seed": 123456,
      "description": "Deskripsi wajah, usia, tubuh, rambut, dan pakaian",
      "visual_signature": "Ciri visual permanen yang unik"
    }
  ],
  "scenes": [
    {
      "scene_number": 1,
      "time_range": "00:00-00:08",
      "duration": 8,
      "title": "Judul pendek adegan",
      "action_summary": "Aksi konkret yang terjadi",
      "shot_type": "Medium Shot",
      "camera_movement": "Slow push-in",
      "lighting_mood": "Soft cinematic lighting",
      "characters_in_scene": [1],
      "dialogue": [{"speaker_id": 1, "line": "Dialog karakter", "screen_position": "center"}],
      "start_state": "Keadaan lengkap pada awal adegan",
      "end_state": "Keadaan lengkap pada akhir adegan",
      "prompt_for_flow": "Detailed English cinematic video prompt...",
      "text_overlay": "Teks pendek",
      "narration_id": "Narasi bahasa ${language}",
      "narration_en": "English narration",
      "affiliate_scene": false
    }
  ]
}`;
}

function parseImportedStoryboard(raw) {
  let text = String(raw || '').trim();
  if (text.startsWith('```')) {
    text = text.replace(/^```(?:json)?\s*/i, '').replace(/\s*```$/, '').trim();
  }
  const storyboard = JSON.parse(text);
  if (!storyboard || Array.isArray(storyboard) || typeof storyboard !== 'object') {
    throw new Error('Root JSON harus berupa object storyboard.');
  }
  if (!String(storyboard.film_title || '').trim()) throw new Error('Field film_title wajib diisi.');
  if (!Array.isArray(storyboard.characters) || !storyboard.characters.length) {
    throw new Error('Field characters wajib berupa array dan minimal berisi satu karakter.');
  }
  if (!Array.isArray(storyboard.scenes) || !storyboard.scenes.length) {
    throw new Error('Field scenes wajib berupa array dan tidak boleh kosong.');
  }

  const expectedCount = Math.max(1, parseInt(document.getElementById('externalAiSceneCount')?.value, 10)
    || parseInt(document.getElementById('sceneCountInput')?.value, 10) || storyboard.scenes.length);
  if (storyboard.scenes.length !== expectedCount) {
    throw new Error(`Jumlah scene ${storyboard.scenes.length}, tetapi pengaturan aplikasi meminta tepat ${expectedCount} scene.`);
  }
  const characterIds = new Set(storyboard.characters.map(char => String(char.id)));
  const required = ['title', 'action_summary', 'prompt_for_flow', 'duration'];
  storyboard.scenes.forEach((scene, index) => {
    const number = index + 1;
    if (!scene || typeof scene !== 'object') throw new Error(`Scene ${number} bukan object yang valid.`);
    if (Number(scene.scene_number) !== number) throw new Error(`scene_number harus berurutan. Posisi ${number} berisi ${scene.scene_number}.`);
    required.forEach(field => {
      if (scene[field] === undefined || scene[field] === null || scene[field] === '') {
        throw new Error(`Scene ${number}: field ${field} wajib diisi.`);
      }
    });
    if (![4, 6, 8, 10].includes(Number(scene.duration))) {
      throw new Error(`Scene ${number}: duration harus 4, 6, 8, atau 10 detik.`);
    }
    if (!Array.isArray(scene.characters_in_scene)) scene.characters_in_scene = [];
    const unknownId = scene.characters_in_scene.find(id => !characterIds.has(String(id)));
    if (unknownId !== undefined) throw new Error(`Scene ${number}: karakter ID ${unknownId} tidak terdaftar.`);
    if (!Array.isArray(scene.dialogue)) scene.dialogue = [];
  });
  return storyboard;
}

function storyboardRevisionPrompt(storyboard) {
  const sceneCount = Array.isArray(storyboard?.scenes) ? storyboard.scenes.length : 0;
  const language = storyboard?.target_lang || 'sesuai bahasa pada JSON';
  const country = storyboard?.target_country || 'sesuai negara pada JSON';
  return `Anda adalah editor storyboard film profesional. Perbaiki storyboard JSON di bawah agar lebih kuat, detail, sinematik, konsisten, dan siap dipakai di Google Flow.

ATURAN MUTLAK:
- Kembalikan HANYA satu object JSON valid, dimulai { dan diakhiri }. Jangan gunakan markdown, penjelasan, atau komentar.
- Pertahankan TEPAT ${sceneCount} scene dan scene_number berurutan 1 sampai ${sceneCount}.
- Pertahankan durasi setiap scene. Nilai duration hanya boleh 4, 6, 8, atau 10.
- Pertahankan ID, seed, identitas, wajah, pakaian, dan visual_signature karakter agar konsisten.
- Semua dialogue, narration_id, text_overlay, judul film, dan judul scene wajib menggunakan bahasa ${language}.
- Sesuaikan nama, budaya, wajah, pakaian, dan lingkungan dengan target negara ${country}, kecuali identitas cerita memang meminta lain.
- prompt_for_flow wajib berupa prompt video sinematik terperinci dalam bahasa Inggris dan konsisten dengan visual_style, visual_vibe, lighting_style, color_palette, aspect_ratio, serta kontinuitas scene.
- Jangan menghapus field yang sudah ada. Boleh memperbaiki film_title, genre_style, art_direction, consistent_characters, action_summary, shot_type, camera_movement, lighting_mood, dialogue, start_state, end_state, prompt_for_flow, text_overlay, dan narasi.
- characters_in_scene dan speaker_id hanya boleh memakai ID karakter yang terdaftar di characters.
- Audit logika seluruh cerita: perbaiki kontradiksi hubungan, peran, motivasi, kepemilikan, bukti, dan urutan pengungkapan tanpa mengubah premis utama atau menambah karakter penting baru.
- Setiap scene harus mempunyai satu fungsi dramatik utama, satu aksi utama, maksimal dua aksi pendukung, reaksi emosional yang terlihat, dan final frame yang kuat.
- time_range harus dihitung ulang secara kumulatif dari duration tanpa jeda atau tumpang tindih. scene_count harus sama dengan jumlah scene aktual.
- Setiap speaker_id wajib hadir di characters_in_scene. Karakter yang tidak tercantum tidak boleh terlihat, berbicara, atau melakukan aksi penting.
- Dialog harus alami dan muat dalam durasi (scene 10 detik maksimal sekitar 18–22 kata total). Dialog di prompt_for_flow harus sama persis dengan dialogue.line dan tetap dalam bahasa ${language}.
- Hanya speaker aktif yang menggerakkan bibir; karakter lain bereaksi tanpa lip movement. Jangan menumpuk dialog dan narration_id bila waktunya tidak cukup.
- Gunakan maksimal satu gerakan kamera utama yang realistis per scene. Pertahankan screen direction, posisi kiri/kanan, dan eyeline antarscene.
- text_overlay hanya panduan editing 2–5 kata dan tidak boleh diminta dirender di prompt_for_flow. Larang subtitle, caption, watermark, logo, dan automatically generated on-screen text.
- Pertahankan seluruh metadata teknis yang ada. Jika raw_response tidak dapat diperbarui dengan aman, jadikan string kosong.
- Pastikan JSON dapat diparse langsung oleh JSON.parse: gunakan tanda kutip ganda dan jangan beri trailing comma.

STANDAR SETIAP prompt_for_flow (satu paragraf Inggris 130–220 kata):
1. Durasi, medium/style, aspect composition, lokasi, waktu, dan atmosfer.
2. Semua karakter yang terlihat beserta ciri fisik, pakaian, aksesori, skala, posisi awal, dan properti.
3. Urutan aksi yang realistis terhadap waktu: opening hook, aksi/dialog utama, reaksi, lalu final continuity frame.
4. Dialog lisan bahasa ${language} harus identik dengan field dialogue; natural pronunciation, accurate lip-sync, clean dialogue audio, subtle room tone/SFX.
5. Shot type, lens/framing/depth of field, satu camera movement, lighting, palette, ekspresi, gesture, dan body language.
6. Untuk scene setelah scene pertama, awali dengan Continue seamlessly/directly from the previous scene dan sebutkan continuity anchor konkret.
7. Akhiri dengan final frame yang sama secara faktual dengan end_state serta negative constraints relevan: no extra main characters, no duplicates, no identity drift, no face swapping, no age/wardrobe/hairstyle changes, no deformed hands, no extra fingers, no broken anatomy, no floating/disappearing/morphing props, no teleportation, no random cuts, no sudden zoom, no flicker, no background warping, no incorrect lip movement, no subtitles/captions/watermark/logo/generated text.

Sebelum mengeluarkan JSON, audit diam-diam: jumlah dan urutan scene, timeline, ID dan speaker, dialog, logika, properti, continuity, bahasa, style, aspect ratio, serta sintaks JSON.

STORYBOARD JSON SAAT INI:
${JSON.stringify(storyboard || {}, null, 2)}`;
}

function initStoryboardImportModal() {
  const modal = document.getElementById('importStoryboardModal');
  const openBtn = document.getElementById('openImportStoryboardBtn');
  if (!modal || !openBtn) return;
  const promptArea = document.getElementById('externalAiPromptTemplate');
  const ideaInput = document.getElementById('externalAiStoryIdea');
  const countInput = document.getElementById('externalAiSceneCount');
  const copyBtn = document.getElementById('copyExternalAiPromptBtn');
  const jsonArea = document.getElementById('importStoryboardJsonInput');
  const message = document.getElementById('importStoryboardValidationMsg');
  const modalTitle = document.getElementById('importStoryboardModalTitle');
  const modalSubtitle = document.getElementById('importStoryboardModalSubtitle');
  const confirmBtn = document.getElementById('confirmImportStoryboardBtn');
  const close = () => modal.classList.remove('active');

  const openNewImport = () => {
    storyboardImportMode = 'new';
    ideaInput.value = (document.getElementById('premiseInput') || document.getElementById('themeInput'))?.value.trim() || '';
    countInput.value = Math.max(1, parseInt(document.getElementById('sceneCountInput')?.value, 10) || 6);
    promptArea.value = storyboardImportPrompt();
    jsonArea.value = '';
    if (modalTitle) modalTitle.textContent = '📥 Import Storyboard dari AI Lain';
    if (modalSubtitle) modalSubtitle.textContent = 'Salin prompt, kirim ke AI pilihanmu, lalu tempel hasil JSON-nya di bawah.';
    if (confirmBtn) confirmBtn.textContent = '✅ Validasi & Import';
    message.textContent = '';
    modal.classList.add('active');
  };
  const openReplaceImport = storyboard => {
    storyboardImportMode = 'replace';
    ideaInput.value = storyboard?.premise || storyboard?.film_title || '';
    countInput.value = Math.max(1, storyboard?.scenes?.length || 1);
    promptArea.value = storyboardRevisionPrompt(storyboard);
    jsonArea.value = '';
    if (modalTitle) modalTitle.textContent = '♻️ Perbaiki & Replace Scene Master';
    if (modalSubtitle) modalSubtitle.textContent = 'Copy JSON ke Gemini/GPT, perbaiki di sana, lalu tempel hasil lengkapnya untuk mengganti storyboard aktif.';
    if (confirmBtn) confirmBtn.textContent = '♻️ Validasi & Replace';
    message.style.color = 'var(--text-secondary)';
    message.textContent = `Menunggu JSON revisi lengkap dengan tepat ${countInput.value} scene.`;
    modal.classList.add('active');
  };
  storyboardImportController = { openNewImport, openReplaceImport };
  openBtn.addEventListener('click', openNewImport);
  document.getElementById('closeImportStoryboardBtn')?.addEventListener('click', close);
  document.getElementById('cancelImportStoryboardBtn')?.addEventListener('click', close);
  modal.addEventListener('click', event => { if (event.target === modal) close(); });

  const refreshPrompt = () => {
    promptArea.value = storyboardImportMode === 'replace' ? storyboardRevisionPrompt(currentStoryboard) : storyboardImportPrompt();
  };
  ideaInput?.addEventListener('input', refreshPrompt);
  countInput?.addEventListener('input', refreshPrompt);

  copyBtn?.addEventListener('click', async () => {
    try {
      refreshPrompt();
      await navigator.clipboard.writeText(promptArea.value);
      showToast('Template prompt berhasil disalin. Tempel ke AI pilihanmu.', 'success');
    } catch (_) {
      promptArea.select();
      document.execCommand('copy');
      showToast('Template prompt berhasil disalin.', 'success');
    }
    copyBtn.textContent = '✅ Berhasil Disalin';
    copyBtn.style.background = 'linear-gradient(135deg, #10b981, #22c55e)';
    copyBtn.style.borderColor = '#6ee7b7';
    copyBtn.style.color = '#ffffff';
    clearTimeout(copyBtn._copySuccessTimer);
    copyBtn._copySuccessTimer = setTimeout(() => {
      copyBtn.textContent = '📋 Copy Prompt';
      copyBtn.style.background = '';
      copyBtn.style.borderColor = 'var(--neon-cyan)';
      copyBtn.style.color = 'var(--neon-cyan)';
    }, 1800);
  });

  confirmBtn?.addEventListener('click', () => {
    try {
      const storyboard = parseImportedStoryboard(jsonArea.value);
      const previous = storyboardImportMode === 'replace' ? currentStoryboard : null;
      storyboard.aspect_ratio = previous?.aspect_ratio || document.getElementById('aspectSelect')?.value || 'portrait';
      storyboard.scene_count = storyboard.scenes.length;
      storyboard.target_lang = previous?.target_lang || document.getElementById('targetLanguageInput')?.value || 'Indonesia';
      storyboard.target_country = previous?.target_country || document.getElementById('targetCountryInput')?.value || '';
      storyboard.duration_mode = previous?.duration_mode || document.getElementById('durationPerSceneSelect')?.value || 'auto';
      // The user's studio selection is authoritative; an external AI may not change medium.
      storyboard.visual_style = previous?.visual_style || document.getElementById('visualStyleSelect')?.value || 'live_action';
      storyboard.visual_vibe = previous?.visual_vibe || document.getElementById('visualVibeSelect')?.value || 'none';
      storyboard.lighting_style = previous?.lighting_style || document.getElementById('lightingStyleSelect')?.value || 'none';
      storyboard.color_palette = previous?.color_palette || document.getElementById('colorPaletteSelect')?.value || 'none';
      if (previous?.character_references && !storyboard.character_references) storyboard.character_references = previous.character_references;
      if (previous?.affiliate_product && !storyboard.affiliate_product) storyboard.affiliate_product = previous.affiliate_product;
      storyboard.premise = ideaInput?.value.trim()
        || (document.getElementById('premiseInput') || document.getElementById('themeInput'))?.value.trim()
        || storyboard.premise || '';
      storyboard.generated_via = storyboardImportMode === 'replace' ? 'external_ai_revision' : (storyboard.generated_via || 'external_ai_import');
      currentStoryboard = storyboard;
      saveStoryboardToHistory(storyboard);
      renderStoryboardResult(storyboard);
      message.style.color = '#34d399';
      message.textContent = `Valid: ${storyboard.scenes.length} scene siap digunakan.`;
      const wasReplace = storyboardImportMode === 'replace';
      showToast(wasReplace ? `Scene Master berhasil diganti dengan revisi ${storyboard.scenes.length} scene.` : `Storyboard ${storyboard.scenes.length} scene berhasil di-import ke Scene Master.`, 'success');
      close();
      if (!wasReplace) document.querySelector('.nav-item[data-tab="tab-history"]')?.click();
    } catch (error) {
      message.style.color = '#fb7185';
      message.textContent = `JSON belum valid: ${error.message}`;
    }
  });
}

// Custom Confirm Modal Helper (Replaces native browser confirm popup)
function showCustomConfirm(title, message, confirmBtnText = 'Ya, Hapus', icon = '🗑️', onConfirm = null) {
  const modal = document.getElementById('customConfirmModal');
  if (!modal) return;

  document.getElementById('customConfirmTitle').textContent = title;
  document.getElementById('customConfirmMsg').textContent = message;
  document.getElementById('customConfirmIcon').textContent = icon;

  const actionBtn = document.getElementById('customConfirmActionBtn');
  const cancelBtn = document.getElementById('customConfirmCancelBtn');
  actionBtn.textContent = confirmBtnText;

  modal.classList.add('active');

  const cleanup = () => {
    modal.classList.remove('active');
    actionBtn.onclick = null;
    cancelBtn.onclick = null;
  };

  actionBtn.onclick = () => {
    cleanup();
    if (typeof onConfirm === 'function') onConfirm();
  };

  cancelBtn.onclick = () => {
    cleanup();
  };
}

// Custom Prompt Modal Helper (Replaces native browser prompt popup)
function showCustomPrompt(title, label, defaultValue = '', onSave = null) {
  const modal = document.getElementById('customPromptModal');
  if (!modal) return;

  document.getElementById('customPromptTitle').textContent = title;
  document.getElementById('customPromptLabel').textContent = label;
  const inputEl = document.getElementById('customPromptInput');
  inputEl.value = defaultValue;

  modal.classList.add('active');
  setTimeout(() => inputEl.focus(), 100);

  const saveBtn = document.getElementById('customPromptSaveBtn');
  const cancelBtn = document.getElementById('customPromptCancelBtn');

  const cleanup = () => {
    modal.classList.remove('active');
    saveBtn.onclick = null;
    cancelBtn.onclick = null;
  };

  saveBtn.onclick = () => {
    const val = inputEl.value.trim();
    cleanup();
    if (val && typeof onSave === 'function') onSave(val);
  };

  cancelBtn.onclick = () => {
    cleanup();
  };
}

// Cute AI Loading Overlay Helper
function showCuteAiLoading(title = '🤖 Gemini AI Memuat Ide...', message = 'Sedang meracik alur cerita sinematik...') {
  const modal = document.getElementById('aiCuteLoadingModal');
  const titleEl = document.getElementById('aiCuteLoadingTitle');
  const msgEl = document.getElementById('aiCuteLoadingMsg');
  const barEl = document.getElementById('aiCuteLoadingBar');
  const progressEl = document.getElementById('aiCuteLoadingProgressText');

  if (titleEl) titleEl.textContent = title;
  if (msgEl) msgEl.textContent = message;
  if (barEl) {
    barEl.style.width = '45%';
    barEl.dataset.mode = 'indeterminate';
  }
  if (progressEl) progressEl.textContent = 'Sedang diproses…';
  if (modal) modal.classList.add('active');
}

function setCuteAiSceneProgress(completedScenes, totalScenes, processingPart = false) {
  const total = Math.max(1, Number(totalScenes) || 1);
  const completed = Math.max(0, Math.min(total, Number(completedScenes) || 0));
  const percent = Math.round((completed / total) * 100);
  const barEl = document.getElementById('aiCuteLoadingBar');
  const progressEl = document.getElementById('aiCuteLoadingProgressText');
  if (barEl) {
    barEl.dataset.mode = 'scene-progress';
    barEl.style.width = `${percent}%`;
  }
  if (progressEl) {
    progressEl.textContent = `${completed}/${total} scene selesai · ${percent}%${processingPart ? ' · part berikutnya sedang diproses' : ''}`;
  }
}

function hideCuteAiLoading() {
  const modal = document.getElementById('aiCuteLoadingModal');
  if (modal) modal.classList.remove('active');
}

function seoStorageKey(jobId) {
  // v6 invalidates SEO covers generated with a ratio that did not follow the source video.
  return `sinematica_seo_kit_v6_${jobId}`;
}

function bindSeoCopyActions(body, kit) {
  const copyWithToast = async (text, successMessage) => {
    try {
      await navigator.clipboard.writeText(String(text || ''));
      showToast(successMessage, 'success');
    } catch (err) {
      showToast('Gagal menyalin ke clipboard. Izinkan akses clipboard lalu coba lagi.', 'error');
    }
  };
  body.querySelector('#btnCopyAllSeo')?.addEventListener('click', () => {
    const allText = kit.copy_all_text || `JUDUL UTAMA:\n${(kit.seo_titles || [])[0] || ''}\n\nDESKRIPSI LENGKAP:\n${kit.description || ''}\n\nKOMENTAR TERSEMAT:\n${kit.pinned_comment || ''}\n\nTAGS:\n${kit.tags_csv || ''}`;
    copyWithToast(allText, 'Semua teks YouTube SEO (Judul, Deskripsi, Pinned, Tags) berhasil disalin!');
  });
  body.querySelector('#btnCopyPinnedComment')?.addEventListener('click', () =>
    copyWithToast(kit.pinned_comment, 'Komentar tersemat (Pinned Comment) berhasil disalin!'));
  body.querySelector('#btnCopyDescription')?.addEventListener('click', () =>
    copyWithToast(kit.description, 'Deskripsi YouTube berhasil tercopy!'));
  body.querySelectorAll('.btn-copy-seo-title').forEach(btn => {
    btn.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path></svg>';
    btn.addEventListener('click', () => {
      const title = (kit.seo_titles || [])[Number(btn.getAttribute('data-index'))] || '';
      copyWithToast(title, 'Judul SEO berhasil tercopy!');
    });
  });
  body.querySelector('#btnCopyThumbPrompt')?.addEventListener('click', () =>
    copyWithToast(kit.thumbnail_prompt, 'Prompt thumbnail berhasil tercopy!'));
  body.querySelector('#btnCopyTags')?.addEventListener('click', () =>
    copyWithToast(kit.tags_csv, 'Tag kata kunci berhasil tercopy!'));
  body.querySelector('#btnCopyHashtags')?.addEventListener('click', () =>
    copyWithToast((kit.hashtags || []).join(' '), 'Hashtag relevan berhasil tercopy!'));

  const genThumbBtn = body.querySelector('#btnGenerateThumbFlow');
  if (genThumbBtn) {
    genThumbBtn.addEventListener('click', async () => {
      const resultContainer = body.querySelector('#seoThumbImageResult');
      genThumbBtn.disabled = true;
      genThumbBtn.textContent = '⏳ Mengirim ke Google Flow...';
      if (resultContainer) resultContainer.innerHTML = '<p style="color:var(--neon-cyan);font-size:12px;margin-top:8px;">🚀 Mengirim prompt cover ke Google Flow...</p>';
      try {
        const res = await fetch('/api/storyboard/generate_thumbnail', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            prompt: kit.thumbnail_prompt,
            aspect_ratio: kit.thumbnail_aspect_ratio || '16:9',
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Gagal generate thumbnail di Flow');
        if (resultContainer) {
          resultContainer.innerHTML = `
            <div style="margin-top:12px; padding:12px; background:rgba(0,0,0,0.6); border:1px solid #34d399; border-radius:10px; text-align:center;">
              <p style="color:#34d399; font-weight:800; font-size:13px; margin:0 0 8px 0;">✅ Cover Thumbnail Berhasil Dibuat di Google Flow!</p>
              ${data.image_url ? `<img src="${data.image_url}" style="max-width:100%; max-height:260px; border-radius:8px; box-shadow:0 4px 16px rgba(0,0,0,0.5); margin-bottom:8px;" />` : ''}
              <div>
                ${data.image_url ? `<button type="button" id="btnDownloadGeneratedCover" class="btn-primary" style="display:inline-block; padding:6px 14px; font-size:12px; font-weight:800;">💾 Download Cover Image</button>` : ''}
              </div>
            </div>
          `;
          const downloadBtn = resultContainer.querySelector('#btnDownloadGeneratedCover');
          downloadBtn?.addEventListener('click', async () => {
            downloadBtn.disabled = true;
            downloadBtn.textContent = '⏳ Menyiapkan download...';
            try {
              const downloadRes = await fetch('/api/storyboard/download_thumbnail', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                  image_url: data.image_url,
                  instance_id: data.profile_instance_id || null,
                }),
              });
              if (!downloadRes.ok) {
                const errorData = await downloadRes.json().catch(() => ({}));
                throw new Error(errorData.detail || 'Gagal download cover image');
              }
              const blob = await downloadRes.blob();
              const objectUrl = URL.createObjectURL(blob);
              const anchor = document.createElement('a');
              anchor.href = objectUrl;
              anchor.download = 'youtube_thumbnail.png';
              document.body.appendChild(anchor);
              anchor.click();
              anchor.remove();
              setTimeout(() => URL.revokeObjectURL(objectUrl), 1000);
              downloadBtn.textContent = '✅ Berhasil Didownload';
            } catch (downloadErr) {
              showToast(downloadErr.message, 'error');
              downloadBtn.disabled = false;
              downloadBtn.textContent = '💾 Coba Download Lagi';
            }
          });
        }
        genThumbBtn.textContent = '✅ Sukses Dibuat!';
      } catch (err) {
        if (resultContainer) resultContainer.innerHTML = `<p style="color:#f43f5e;font-size:12px;margin-top:8px;">❌ ${escapeHtml(err.message)}</p>`;
        genThumbBtn.disabled = false;
        genThumbBtn.textContent = '⚡ Coba Buat Lagi';
      }
    });
  }
}

function initSeoKitModal() {
  const modal = document.getElementById('seoKitModal');
  const closeBtn = document.getElementById('closeSeoModalBtn');

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => modal.classList.remove('active'));
  }

  document.addEventListener('click', async (e) => {
    if (e.target && (e.target.classList.contains('btn-generate-seo') || e.target.classList.contains('btn-regenerate-seo'))) {
      const filmTitle = e.target.getAttribute('data-title') || 'Film Sinematik';
      const jobId = e.target.getAttribute('data-jobid') || '';
      const seoContext = gallerySeoContexts.get(String(jobId)) || {};
      const body = document.getElementById('seoModalBody');
      modal.classList.add('active');

      body.innerHTML = `
        <div class="seo-loading-state">
          <div class="seo-loader-orbit" aria-hidden="true">
            <span class="seo-loader-wand">🪄</span>
          </div>
          <h4>Meracik YouTube SEO & Marketing Kit<span class="seo-loading-dots"></span></h4>
          <p id="seoLoadingStatus">AI sedang membaca seluruh storyboard dan alur adegan</p>
          <div class="seo-loading-track"><span></span></div>
          <small id="seoLoadingElapsed">Berjalan 0 detik</small>
        </div>
      `;

      const loadingStartedAt = Date.now();
      const loadingMessages = [
        'AI sedang membaca judul dan premis film',
        'Menganalisis kata kunci dan daya tarik penonton',
        'Merancang judul, deskripsi, thumbnail, dan tags',
        'Merapikan hasil SEO agar siap disalin'
      ];
      let loadingStep = 0;
      const loadingTimer = window.setInterval(() => {
        const elapsed = Math.floor((Date.now() - loadingStartedAt) / 1000);
        const elapsedEl = document.getElementById('seoLoadingElapsed');
        const statusEl = document.getElementById('seoLoadingStatus');
        if (elapsedEl) elapsedEl.textContent = `Berjalan ${elapsed} detik`;
        if (statusEl && elapsed > 0 && elapsed % 4 === 0) {
          loadingStep = (loadingStep + 1) % loadingMessages.length;
          statusEl.textContent = loadingMessages[loadingStep];
        }
      }, 1000);

      try {
        const res = await fetch('/api/storyboard/seo_kit', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            title: filmTitle,
            premise: seoContext.story_context || seoContext.initial_prompt || filmTitle,
            storyboard: seoContext.storyboard || null,
            aspect_ratio: seoContext.aspect_ratio || seoContext.storyboard?.aspect_ratio || 'landscape',
            target_lang: seoContext.target_lang || 'Indonesia',
            target_country: seoContext.target_country || ''
          })
        });

        const data = await res.json();
        if (!res.ok) {
          const detail = data.detail;
          const message = Array.isArray(detail)
            ? detail.map(item => item.msg || JSON.stringify(item)).join('; ')
            : (typeof detail === 'object' && detail !== null ? JSON.stringify(detail) : detail);
          throw new Error(message || 'Gagal generate SEO kit');
        }

        const rawKit = data.seo_kit || {};
        let tagsVal = rawKit.tags_csv || rawKit.tags || rawKit.keywords || rawKit.long_tail_tags || rawKit.youtube_tags || '';
        if (Array.isArray(tagsVal)) tagsVal = tagsVal.join(', ');
        const thumbVal = rawKit.thumbnail_prompt || rawKit.thumbnailPrompt || rawKit.thumbnail || rawKit.prompt_thumbnail || rawKit.image_prompt || rawKit.thumbnail_concept || '-';
        const kit = {
          ...rawKit,
          seo_titles: rawKit.seo_titles || rawKit.titles || [],
          description: rawKit.description || rawKit.desc || '',
          thumbnail_prompt: thumbVal,
          tags_csv: tagsVal,
          thumbnail_aspect_ratio: rawKit.thumbnail_aspect_ratio || (seoContext.aspect_ratio === 'portrait' ? '9:16' : '16:9')
        };

        window.clearInterval(loadingTimer);

        body.innerHTML = `
          <div style="display: flex; flex-direction: column; gap: 16px;">
            <div style="background: linear-gradient(135deg, rgba(56,189,248,0.15), rgba(168,85,247,0.15)); border: 1px solid var(--neon-cyan); padding: 12px 16px; border-radius: 12px; display: flex; justify-content: space-between; align-items: center; gap: 12px;">
              <div>
                <span style="font-size: 13px; font-weight: 800; color: #fff;">⚡ YouTube Studio Instant Deployment</span>
                <p style="font-size: 11px; color: var(--text-secondary); margin: 2px 0 0 0;">Salin seluruh naskah SEO & metadata sekali klik untuk langsung ditempel ke YouTube Studio.</p>
              </div>
              <button type="button" class="btn-primary" id="btnCopyAllSeo" style="padding: 8px 16px; font-size: 12px; font-weight: 800; white-space: nowrap; box-shadow: 0 0 15px rgba(56,189,248,0.4);">📋 Salin Paket Lengkap</button>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <h4 style="color: var(--neon-cyan); font-size: 14px; margin-bottom: 8px;">🎯 3 Pilihan Judul YouTube SEO Natural:</h4>
              <ol style="margin: 0; padding-left: 20px; font-size: 13px; color: var(--text-primary); line-height: 1.6;">
                ${(kit.seo_titles || []).map((t, index) => `
                  <li class="seo-title-row">
                    <span><b>${escapeHtml(t)}</b> <span style="font-size: 11px; color: var(--text-muted);">(${t.length} kar)</span></span>
                    <button type="button" class="btn-copy-seo-title" data-index="${index}" title="Salin judul ${index + 1}" aria-label="Salin judul ${index + 1}">
                      <svg viewBox="0 0 24 24" aria-hidden="true"><rect x="8" y="8" width="11" height="11" rx="2"></rect><path d="M16 8V6a2 2 0 0 0-2-2H6a2 2 0 0 0-2 2v8a2 2 0 0 0 2 2h2"></path></svg>
                    </button>
                  </li>
                `).join('')}
              </ol>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">📝 Deskripsi Video (3 Paragraf + CTA & Hashtags):</h4>
                <button type="button" class="btn-secondary" id="btnCopyDescription" style="padding: 3px 8px; font-size: 11px;">📋 Copy Deskripsi</button>
              </div>
              <textarea id="seoDescriptionText" readonly style="width: 100%; height: 120px; background: rgba(0,0,0,0.5); border: 1px solid var(--glass-border); color: var(--text-secondary); border-radius: 6px; padding: 8px; font-size: 12px;">${kit.description || ''}</textarea>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">📌 Komentar Tersemat (Pinned Comment Engagement):</h4>
                <button type="button" class="btn-secondary" id="btnCopyPinnedComment" style="padding: 3px 8px; font-size: 11px;">📋 Copy Pinned Comment</button>
              </div>
              <p style="font-size: 12px; color: #fde047; background: rgba(0,0,0,0.5); padding: 8px; border-radius: 6px; margin: 0; line-height: 1.5;">${escapeHtml(kit.pinned_comment || 'Tulis pertanyaan pemantik diskusi di sini...')}</p>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">🖼️ Prompt Cover YouTube ${escapeHtml(kit.thumbnail_aspect_ratio)}:</h4>
                <div style="display: flex; gap: 6px;">
                  <button type="button" class="btn-secondary" id="btnCopyThumbPrompt" style="padding: 3px 8px; font-size: 11px;">📋 Copy Prompt</button>
                  <button type="button" class="btn-primary" id="btnGenerateThumbFlow" style="padding: 3px 10px; font-size: 11px; font-weight: 800; background: linear-gradient(135deg, #059669, #10b981);">⚡ Buat Gambar di Flow</button>
                </div>
              </div>
              <p style="font-size: 12px; color: var(--text-primary); background: rgba(0,0,0,0.5); padding: 8px; border-radius: 6px; margin: 0;" id="seoThumbText">${kit.thumbnail_prompt || '-'}</p>
              <div id="seoThumbImageResult"></div>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">#️⃣ 3 Hashtag Relevan:</h4>
                <button type="button" class="btn-secondary" id="btnCopyHashtags" style="padding: 3px 8px; font-size: 11px;">📋 Copy Hashtag</button>
              </div>
              <p style="font-size: 13px; color: #c4b5fd; margin:0;">${escapeHtml((kit.hashtags || []).join(' '))}</p>
            </div>

            <div style="background: rgba(4, 7, 16, 0.7); border: 1px solid var(--glass-border); padding: 14px; border-radius: 10px;">
              <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 6px;">
                <h4 style="color: var(--neon-cyan); font-size: 14px; margin: 0;">🏷️ Tag Kata Kunci Backend (Pendukung Ejaan/Pencarian):</h4>
                <button type="button" class="btn-primary" id="btnCopyTags" style="padding: 3px 10px; font-size: 11px;">📋 Copy Tags</button>
              </div>
              <input type="text" readonly id="seoTagsText" value="${kit.tags_csv || ''}" style="width: 100%; background: rgba(0,0,0,0.5); border: 1px solid var(--glass-border); color: var(--neon-green); border-radius: 6px; padding: 8px; font-size: 12px;" />
            </div>
          </div>
        `;

        bindSeoCopyActions(body, kit);
        if (jobId) {
          localStorage.setItem(seoStorageKey(jobId), JSON.stringify({ kit, html: body.innerHTML }));
          refreshGallery();
        }

      } catch (err) {
        window.clearInterval(loadingTimer);
        body.innerHTML = `<div style="color: #f43f5e; padding: 20px; text-align: center;">Gagal generate SEO kit: ${err.message}</div>`;
      }
    }

    if (e.target && e.target.classList.contains('btn-view-seo')) {
      const jobId = e.target.getAttribute('data-jobid') || '';
      const saved = JSON.parse(localStorage.getItem(seoStorageKey(jobId)) || 'null');
      if (!saved?.kit || !saved?.html) return;
      const body = document.getElementById('seoModalBody');
      body.innerHTML = saved.html;
      modal.classList.add('active');
      bindSeoCopyActions(body, saved.kit);
    }
  });
}

function saveStoryboardToHistory(sb) {
  if (!sb) return;
  if (!sb.film_asset_id) sb.film_asset_id = crypto.randomUUID();
  try {
    localStorage.setItem('sinematica_last_storyboard', JSON.stringify(sb));

    let history = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
    sb._timestamp = new Date().toLocaleString('id-ID');
    history = history.filter(h => h.film_title !== sb.film_title);
    history.unshift(sb);
    if (history.length > 20) history = history.slice(0, 20);
    localStorage.setItem('sinematica_storyboard_history', JSON.stringify(history));
  } catch (err) {
    console.warn('Gagal menyimpan storyboard ke history:', err);
  }
}

function loadLastStoryboard() {
  try {
    const saved = localStorage.getItem('sinematica_last_storyboard');
    if (saved) {
      currentStoryboard = JSON.parse(saved);
      renderStoryboardResult(currentStoryboard);
      const btnSend = document.getElementById('btnSendToExecution');
      if (btnSend) btnSend.disabled = false;
      console.log('Restored last storyboard from localStorage!');
    }
  } catch (err) {
    console.warn('Gagal memuat storyboard terakhir:', err);
  }
}

function initStoryboardHistoryModal() {
  const modal = document.getElementById('storyboardHistoryModal');
  const openBtn = document.getElementById('btnOpenHistoryModalBtn');
  const closeBtn = document.getElementById('closeHistoryModalBtn');
  const selectAll = document.getElementById('selectAllHistoryCheckbox');
  const deleteSelected = document.getElementById('deleteSelectedHistoryBtn');
  const refresh = document.getElementById('refreshHistoryTabBtn');

  if (closeBtn && modal) {
    closeBtn.addEventListener('click', () => modal.classList.remove('active'));
  }

  if (openBtn) {
    openBtn.addEventListener('click', () => {
      const navItem = document.querySelector('.nav-item[data-tab="tab-history"]');
      if (navItem) navItem.click();
    });
  }

  if (refresh) {
    refresh.addEventListener('click', () => {
      selectedHistoryIndexes.clear();
      renderHistoryTab();
    });
  }

  if (selectAll) {
    selectAll.addEventListener('change', () => {
      const cards = document.querySelectorAll('#historyTabBody .history-select-checkbox');
      selectedHistoryIndexes.clear();
      if (selectAll.checked) {
        cards.forEach(box => selectedHistoryIndexes.add(Number(box.dataset.index)));
      }
      cards.forEach(box => { box.checked = selectAll.checked; });
      updateHistorySelectionControls(cards.length);
    });
  }

  if (deleteSelected) {
    deleteSelected.addEventListener('click', () => {
      let history = [];
      try {
        history = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
      } catch (_) {}
      const indexes = StoryboardHistorySelection.normalizeSelectedIndexes(
        selectedHistoryIndexes, history.length
      );
      if (!indexes.length) return;

      showCustomConfirm(
        'Hapus Storyboard Terpilih',
        `Hapus permanen ${indexes.length} storyboard terpilih dari Scene Master?`,
        `Ya, Hapus ${indexes.length}`,
        '🗑️',
        () => {
          const remaining = StoryboardHistorySelection.removeSelectedHistory(history, indexes);
          localStorage.setItem('sinematica_storyboard_history', JSON.stringify(remaining));
          selectedHistoryIndexes.clear();
          showToast(`${indexes.length} storyboard berhasil dihapus.`, 'success');
          renderHistoryTab();
        }
      );
    });
  }
}

function updateHistorySelectionControls(totalItems) {
  const selectAll = document.getElementById('selectAllHistoryCheckbox');
  const deleteSelected = document.getElementById('deleteSelectedHistoryBtn');
  const selectedCount = selectedHistoryIndexes.size;
  if (selectAll) {
    selectAll.checked = totalItems > 0 && selectedCount === totalItems;
    selectAll.indeterminate = selectedCount > 0 && selectedCount < totalItems;
    selectAll.disabled = totalItems === 0;
  }
  if (deleteSelected) {
    deleteSelected.disabled = selectedCount === 0;
    deleteSelected.textContent = `🗑️ Hapus Terpilih (${selectedCount})`;
    deleteSelected.style.opacity = selectedCount ? '1' : '.45';
    deleteSelected.style.cursor = selectedCount ? 'pointer' : 'not-allowed';
  }
}

function renderHistoryTab() {
  const container = document.getElementById('historyTabBody');
  if (!container) return;

  let history = [];
  try {
    history = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
  } catch (_) {}

  const normalizedSelection = StoryboardHistorySelection.normalizeSelectedIndexes(
    selectedHistoryIndexes, history.length
  );
  selectedHistoryIndexes.clear();
  normalizedSelection.forEach(index => selectedHistoryIndexes.add(index));

  if (history.length === 0) {
    selectedHistoryIndexes.clear();
    updateHistorySelectionControls(0);
    container.innerHTML = `
      <div class="empty-state" style="padding: 60px 20px;">
        <div class="empty-icon" style="font-size: 48px; margin-bottom: 12px;">📜</div>
        <h4 style="color: #ffffff; font-size: 18px; margin-bottom: 6px;">Belum Ada Riwayat Storyboard Tersimpan</h4>
        <p style="color: var(--text-muted); font-size: 13px; max-width: 360px; margin: 0 auto;">Rancang storyboard baru di tab AI Storyboard untuk otomatis menyimpannya ke koleksi Scene Master studio ini.</p>
      </div>
    `;
    return;
  }

  container.innerHTML = `
    <div style="display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 24px;">
      ${history.map((item, idx) => `
        <div class="history-item-card" data-index="${idx}" style="position: relative; background: linear-gradient(145deg, rgba(12, 18, 36, 0.85), rgba(20, 29, 54, 0.75)); border: 1px solid ${selectedHistoryIndexes.has(idx) ? 'rgba(56, 189, 248, .85)' : 'rgba(56, 189, 248, 0.25)'}; padding: 24px; border-radius: 18px; box-shadow: 0 10px 30px rgba(0, 0, 0, 0.35); display: flex; flex-direction: column; justify-content: space-between; transition: all 0.3s ease; height: 100%;">
          <input type="checkbox" class="history-select-checkbox" data-index="${idx}" ${selectedHistoryIndexes.has(idx) ? 'checked' : ''} aria-label="Pilih ${escapeHtml(item.film_title || 'storyboard')}" style="position:absolute; top:20px; left:18px; width:17px; height:17px; accent-color:var(--neon-cyan); cursor:pointer; z-index:2;">
          
          <!-- Floating Top-Right Delete X Icon Button -->
          <button type="button" class="btn-delete-history-tab-item" data-index="${idx}" title="Hapus dari Riwayat" style="position: absolute; top: 16px; right: 16px; width: 30px; height: 30px; border-radius: 50%; background: rgba(244, 63, 94, 0.15); border: 1px solid rgba(244, 63, 94, 0.4); color: #f43f5e; font-size: 13px; font-weight: 800; display: flex; align-items: center; justify-content: center; cursor: pointer; transition: all 0.2s; box-shadow: 0 2px 8px rgba(0,0,0,0.3);">
            ✕
          </button>

          <div>
            <!-- Header: Title & Badges -->
            <div style="margin-bottom: 14px; border-bottom: 1px solid rgba(255, 255, 255, 0.08); padding-bottom: 12px; padding-right: 36px; padding-left: 28px;">
              <h4 style="color: #ffffff; font-size: 17px; font-weight: 800; margin: 0 0 8px 0; font-family: var(--font-heading); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;" title="${escapeHtml(item.film_title || 'Film Sinematik')}">🎬 ${escapeHtml(item.film_title || 'Film Sinematik')}</h4>
              
              <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap;">
                <span style="font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; background: rgba(56, 189, 248, 0.15); border: 1px solid rgba(56, 189, 248, 0.4); color: #38bdf8;">${item.aspect_ratio === 'portrait' ? '📱 Short 9:16' : '🖥️ Landscape 16:9'}</span>
                <span style="font-size: 11px; font-weight: 700; padding: 4px 10px; border-radius: 20px; background: rgba(168, 85, 247, 0.15); border: 1px solid rgba(168, 85, 247, 0.4); color: #c084fc;">🎬 ${(item.scenes || []).length} Scene (${(item.scenes || []).length * 10}s)</span>
                <span style="font-size: 11px; color: var(--text-muted); padding: 4px 10px; border-radius: 20px; background: rgba(255, 255, 255, 0.06); border: 1px solid rgba(255, 255, 255, 0.1);">📅 ${item._timestamp || 'Tersimpan'}</span>
              </div>
            </div>

            <!-- Clamped Character Description Box -->
            <div style="background: rgba(4, 7, 16, 0.6); padding: 12px 14px; border-radius: 12px; border: 1px solid rgba(255, 255, 255, 0.08); margin-bottom: 18px;">
              <span style="font-size: 11px; font-weight: 800; color: var(--neon-cyan); display: block; margin-bottom: 4px;">👤 KARAKTER & SEEDS:</span>
              <p style="font-size: 12px; color: var(--text-secondary); margin: 0; line-height: 1.5; display: -webkit-box; -webkit-line-clamp: 3; -webkit-box-orient: vertical; overflow: hidden; text-overflow: ellipsis;" title="${escapeHtml(item.consistent_characters || '-')}">
                ${escapeHtml(item.consistent_characters || 'Deskripsi karakter otomatis oleh AI...')}
              </p>
              <small style="display: block; font-size: 11px; color: #34d399; margin-top: 6px; font-weight: 700;">🌱 Seed Karakter: ${item.character_seed || 'Auto'}</small>
            </div>
          </div>

          <!-- Footer Actions Row: 100% Full Width Open Button -->
          <div style="margin-top: auto; border-top: 1px solid rgba(255, 255, 255, 0.08); padding-top: 14px;">
            <button type="button" class="btn-primary load-history-tab-btn" data-index="${idx}" style="width: 100%; padding: 12px; font-size: 14px; border-radius: 12px; font-weight: 800; background: linear-gradient(135deg, rgba(56, 189, 248, 0.2), rgba(168, 85, 247, 0.25)); border: 1px solid var(--neon-cyan); color: #ffffff; cursor: pointer; box-shadow: 0 4px 15px rgba(56, 189, 248, 0.25); transition: all 0.3s; display: flex; align-items: center; justify-content: center; gap: 8px;">
              <span>📂</span> Buka & Eksekusi di Studio
            </button>
          </div>
        </div>
      `).join('')}
    </div>
  `;

  container.querySelectorAll('.history-select-checkbox').forEach(box => {
    box.addEventListener('change', () => {
      const index = Number(box.dataset.index);
      if (box.checked) selectedHistoryIndexes.add(index);
      else selectedHistoryIndexes.delete(index);
      const card = box.closest('.history-item-card');
      if (card) card.style.borderColor = box.checked
        ? 'rgba(56, 189, 248, .85)'
        : 'rgba(56, 189, 248, .25)';
      updateHistorySelectionControls(history.length);
    });
  });

  container.querySelectorAll('.btn-delete-history-tab-item').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      const idx = parseInt(btn.getAttribute('data-index'));
      showCustomConfirm(
        'Hapus Riwayat Storyboard',
        'Apakah Anda yakin ingin menghapus storyboard ini dari riwayat tersimpan?',
        'Ya, Hapus',
        '🗑️',
        () => {
          try {
            let h = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
            h.splice(idx, 1);
            localStorage.setItem('sinematica_storyboard_history', JSON.stringify(h));
            selectedHistoryIndexes.clear();
            showToast('Item berhasil dihapus dari riwayat!', 'success');
            renderHistoryTab();
          } catch (err) {
            showToast('Gagal menghapus riwayat: ' + err.message, 'error');
          }
        }
      );
    });
  });

  container.querySelectorAll('.load-history-tab-btn').forEach(btn => {
    btn.addEventListener('click', () => {
      const index = parseInt(btn.getAttribute('data-index'));
      const selectedSb = history[index];
      if (selectedSb) {
        currentStoryboard = selectedSb;
        localStorage.setItem('sinematica_last_storyboard', JSON.stringify(selectedSb));
        renderStoryboardResult(selectedSb);
        showToast(`Storyboard "${selectedSb.film_title || 'Film'}" dimuat ke Studio!`, 'success');
        document.querySelector('.nav-item[data-tab="tab-storyboard"]').click();
      }
    });
  });
  updateHistorySelectionControls(history.length);
}

function initFleetTestPrompt() {
  const testBtn = document.getElementById('testSeedPromptBtn');
  const refreshBtn = document.getElementById('refreshFleetBtn');

  const checkCreditsBtn = document.getElementById('checkCreditsFleetBtn');
  if (refreshBtn) refreshBtn.addEventListener('click', fetchFleetStatus);
  if (checkCreditsBtn) checkCreditsBtn.addEventListener('click', fetchFleetCredits);

  if (testBtn) {
    testBtn.addEventListener('click', () => {
      showCustomPrompt(
        'Tes Prompt Seed Karakter ke Google Flow',
        'Ketikkan prompt gambar seed karakter yang ingin dikirim ke Flow:',
        'A handsome wise scholar character portrait, cinematic lighting, 8k',
        async (userPrompt) => {
          testBtn.disabled = true;
          testBtn.textContent = '⏳ Mengirim Prompt ke Flow...';
          showToast('Mengirim request gambar seed ke Google Flow...', 'info', 'Google Flow Bridge');

          try {
            const res = await fetch('/api/fleet/test_prompt', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ prompt: userPrompt })
            });

            const data = await res.json();
            if (!res.ok) throw new Error(data.detail || 'Gagal generate gambar');

            showCustomAlert(
              `✨ Status: ${data.message}\n\nProfil: ${data.profile_used}\nSeed: ${data.seed_used}\nURL Hasil: ${data.seed_image_url || 'Sukses!'}`,
              '🎉 Hasil Tes Google Flow Extension',
              '🎨'
            );
            showToast('Prompt seed karakter berhasil dikirim & diproses di Google Flow!', 'success');
          } catch (err) {
            showCustomAlert(err.message, 'Gagal Tes Google Flow', '❌');
          } finally {
            testBtn.disabled = false;
            testBtn.textContent = '🧪 Tes Kirim Prompt Seed Karakter ke Flow';
          }
        }
      );
    });
  }
}

// Navigation Tab Switching
function initNavigation() {
  const navItems = document.querySelectorAll('.nav-item');
  const pages = document.querySelectorAll('.tab-page');
  const pageTitle = document.getElementById('pageTitle');
  const pageSubtitle = document.getElementById('pageSubtitle');

  const pageMeta = {
    'tab-fleet': {
      title: 'Chrome Multi-Account Fleet Manager',
      sub: 'Kelola dan pantau status koneksi extension akun Google Flow di Chrome'
    },
    'tab-storyboard': {
      title: 'Gemini 3.6 Flash Storyboard Studio',
      sub: 'Susun alur adegan dan prompt konsistensi karakter dari gambar referensi'
    },
    'tab-history': {
      title: 'Scene Master Studio',
      sub: 'Kelola, tinjau, muat kembali, atau hapus seluruh storyboard adegan tersimpan'
    },
    'tab-execution': {
      title: 'Live Multi-Flow Video Execution Terminal',
      sub: 'Pantau proses render adegan video secara otomatis di Google Flow'
    },
    'tab-gallery': {
      title: 'Interactive Video Gallery & Film Director',
      sub: 'Kelola adegan video, atur urutan cerita, dan gabungkan menjadi film sinematik utuh'
    },
    'tab-ugc-affiliate': {
      title: 'UGC Affiliate Asset Lab',
      sub: 'Validasi aset dan bangun Character/Product Master sebelum membuat storyboard'
    },
    'tab-youtube-blueprint': {
      title: 'YouTube Blueprint Studio',
      sub: 'Rancang channel, konten, packaging, soundscape, QC, dan eksperimen analytics berbasis bukti'
    },
    'tab-content-universe': {
      title: 'Audience & Content Universe',
      sub: 'Mesin ide lintas usia berdasarkan fase hidup, kebutuhan emosional, dan tujuan menonton'
    },
    'tab-settings': {
      title: 'Sinematica Studio Settings',
      sub: 'Kelola Gemini API Key, model AI engine, Google Flow Project ID, dan template seed'
    }
  };

  document.addEventListener('click', (e) => {
    const navBtn = e.target.closest('.nav-item');
    if (!navBtn) return;

    const targetId = navBtn.getAttribute('data-tab');
    if (!targetId) return;

    document.querySelectorAll('.nav-item').forEach(i => i.classList.remove('active'));
    document.querySelectorAll('.tab-page').forEach(p => p.classList.remove('active'));

    navBtn.classList.add('active');
    const targetPage = document.getElementById(targetId);
    if (targetPage) targetPage.classList.add('active');

    if (pageMeta[targetId]) {
      if (pageTitle) pageTitle.textContent = pageMeta[targetId].title;
      if (pageSubtitle) pageSubtitle.textContent = pageMeta[targetId].sub;
    }

    if (targetId === 'tab-fleet') fetchFleetStatus();
    if (targetId === 'tab-history') renderHistoryTab();
    if (targetId === 'tab-gallery') refreshGallery();
    if (targetId === 'tab-settings') loadSettingsTab();
  });
}

// Status & Fleet Polling
function initStatusPolling() {
  fetchFleetStatus();
  setInterval(fetchFleetStatus, 5000);
}

let fleetCreditsMap = {};
const FLOW_CREDITS_PER_VIDEO = 15;

function estimateFlowVideosRemaining(creditsValue) {
  const match = String(creditsValue ?? '').replace(/,/g, '').match(/(\d+(?:\.\d+)?)/);
  if (!match) return null;
  const credits = Number(match[1]);
  return Number.isFinite(credits) ? Math.max(0, Math.floor(credits / FLOW_CREDITS_PER_VIDEO)) : null;
}

async function fetchFleetCredits() {
  const checkBtn = document.getElementById('checkCreditsFleetBtn');
  if (checkBtn) {
    checkBtn.disabled = true;
    checkBtn.innerHTML = '⌛ Memeriksa Kuota...';
  }
  try {
    const res = await fetch('/api/fleet_credits');
    if (res.ok) {
      const data = await res.json();
      fleetCreditsMap = data.credits || {};
      fetchFleetStatus();
    }
  } catch (err) {
    console.warn('Gagal mengambil credits fleet:', err);
  } finally {
    if (checkBtn) {
      checkBtn.disabled = false;
      checkBtn.innerHTML = '⚡ Cek Sisa Kuota Flow';
    }
  }
}

async function fetchFleetStatus() {
  try {
    const res = await fetch('/api/fleet');
    if (!res.ok) throw new Error('Backend Offline');
    const data = await res.json();

    const serverPill = document.getElementById('serverPill');
    const fleetPill = document.getElementById('fleetPill');
    const fleetCountBadge = document.getElementById('fleetCountBadge');
    const fleetGrid = document.getElementById('fleetGrid');

    const currentPort = window.location.port || '8888';
    serverPill.innerHTML = `<span class="dot green"></span> Backend: Online (${currentPort})`;

    const profiles = data.profiles || [];
    const readyProfiles = profiles.filter(p => p.connected && p.logged_in && p.ready !== false);

    fleetCountBadge.textContent = readyProfiles.length;
    fleetPill.innerHTML = `<span class="dot ${readyProfiles.length > 0 ? 'green' : 'red'}"></span> Fleet: ${readyProfiles.length} Profile Ready`;

    if (profiles.length === 0) {
      fleetGrid.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🔌</div>
          <h4>Belum Ada Profil Chrome Terhubung</h4>
          <p>Muat unpacked extension <code>engine/chrome-extension</code> di Chrome (chrome://extensions) dan login di flow.google.com</p>
        </div>
      `;
      return;
    }

    fleetGrid.innerHTML = profiles.map(p => {
      const credData = fleetCreditsMap[p.instance_id];
      const isReady = p.connected && p.logged_in && p.ready !== false;
      let credText = isReady ? '⚡ Unlimited' : (p.readiness_error || 'Belum Siap');
      let credBadgeColor = isReady ? 'rgba(16, 185, 129, 0.12)' : 'rgba(244, 63, 94, 0.1)';
      let credBorder = isReady ? 'rgba(16, 185, 129, 0.4)' : 'rgba(244, 63, 94, 0.3)';
      let credTextColor = isReady ? '#34d399' : '#f43f5e';
      let videoRemainingText = '';

      if (credData) {
        if (credData.success) {
          credText = `⚡ ${credData.credits}`;
          const remainingVideos = estimateFlowVideosRemaining(credData.credits);
          if (remainingVideos !== null) {
            videoRemainingText = `≈ ${remainingVideos} video (15 kredit/video)`;
          }
          credTextColor = '#34d399';
          credBadgeColor = 'rgba(16, 185, 129, 0.12)';
          credBorder = 'rgba(16, 185, 129, 0.4)';
        } else {
          credText = credData.credits || 'Gagal Cek Kuota';
          credTextColor = '#f43f5e';
          credBadgeColor = 'rgba(244, 63, 94, 0.1)';
          credBorder = 'rgba(244, 63, 94, 0.3)';
        }
      }

      return `
        <div class="profile-card" style="position: relative; background: rgba(12, 18, 36, 0.85); border: 1px solid rgba(255, 255, 255, 0.1); border-radius: 14px; padding: 18px; display: flex; flex-direction: column; justify-content: space-between; gap: 12px;">
          <div class="profile-header" style="display: flex; justify-content: space-between; align-items: center;">
            <span class="profile-title" style="font-weight: 800; font-size: 15px; color: #ffffff;">💻 ${p.name || p.instance_id}</span>
            <span class="badge-status ${isReady ? 'badge-ready' : 'badge-noauth'}">
              ${isReady ? 'Ready & Logged In' : (p.readiness_error || 'Need Flow Window/Login')}
            </span>
          </div>
          <div style="font-size: 12px; color: var(--text-muted); display: flex; flex-direction: column; gap: 4px;">
            <p style="margin:0;">Instance ID: <code style="color: var(--neon-cyan);">${p.instance_id}</code></p>
            <p style="margin:0;">Project ID: <code style="color: var(--text-secondary);">${p.project_id || 'Auto-detect'}</code></p>
          </div>
          <div style="background: ${credBadgeColor}; border: 1px solid ${credBorder}; border-radius: 10px; padding: 8px 12px; display: flex; justify-content: space-between; align-items: center; margin-top: 4px;">
            <span style="font-size: 12px; font-weight: 700; color: #ffffff;">💳 Sisa Kuota Flow:</span>
            <span style="font-size: 13px; font-weight: 800; color: ${credTextColor}; text-align:right;" id="cred-${p.instance_id}">${credText}${videoRemainingText ? `<small style="display:block; margin-top:3px; font-size:10px; font-weight:700; color:${credTextColor}; opacity:.9;">${videoRemainingText}</small>` : ''}</span>
          </div>
        </div>
      `;
    }).join('');

  } catch (err) {
    document.getElementById('serverPill').innerHTML = '<span class="dot red"></span> Backend: Offline';
    document.getElementById('fleetPill').innerHTML = '<span class="dot red"></span> Fleet: Offline';
  }
}

// Reference Image Dropzone
function initDropzone() {
  const dropzone = document.getElementById('dropzone');
  const fileInput = document.getElementById('refImageInput');

  dropzone.addEventListener('click', () => fileInput.click());

  fileInput.addEventListener('change', (e) => {
    selectedRefFiles = limitStoryboardReferenceFiles(Array.from(e.target.files));
    renderImagePreviews();
  });

  dropzone.addEventListener('dragover', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = 'var(--accent-cyan)';
  });

  dropzone.addEventListener('drop', (e) => {
    e.preventDefault();
    dropzone.style.borderColor = 'var(--glass-border)';
    if (e.dataTransfer.files.length) {
      selectedRefFiles = limitStoryboardReferenceFiles(Array.from(e.dataTransfer.files));
      fileInput.value = '';
      renderImagePreviews();
    }
  });
}

function limitStoryboardReferenceFiles(files) {
  const images = files.filter(file => !file.type || file.type.startsWith('image/'));
  if (images.length > MAX_STORYBOARD_REFERENCE_IMAGES) {
    showToast(`Maksimal ${MAX_STORYBOARD_REFERENCE_IMAGES} gambar referensi. Hanya 7 gambar pertama yang dipakai.`, 'warning');
  }
  return images.slice(0, MAX_STORYBOARD_REFERENCE_IMAGES);
}

function renderImagePreviews() {
  const list = document.getElementById('imagePreviewList');
  if (!list) return;
  list.innerHTML = '';

  selectedRefFiles.forEach((file, index) => {
    const wrapper = document.createElement('div');
    wrapper.className = 'reference-preview-item';
    wrapper.style.cssText = 'position:relative; display:inline-flex; flex:0 0 auto;';

    const removeBtn = document.createElement('button');
    removeBtn.type = 'button';
    removeBtn.className = 'reference-preview-remove';
    removeBtn.setAttribute('aria-label', `Hapus gambar referensi ${index + 1}`);
    removeBtn.title = 'Hapus gambar';
    removeBtn.textContent = '×';
    removeBtn.style.cssText = 'position:absolute; z-index:3; top:-8px; right:-8px; width:24px; height:24px; padding:0; border-radius:50%; border:2px solid #0f172a; background:#f43f5e; color:white; font-size:18px; font-weight:900; line-height:19px; cursor:pointer; box-shadow:0 3px 10px rgba(0,0,0,.45);';
    removeBtn.addEventListener('click', event => {
      event.preventDefault();
      event.stopPropagation();
      selectedRefFiles.splice(index, 1);
      const input = document.getElementById('refImageInput');
      if (input) input.value = '';
      renderImagePreviews();
      showToast('Gambar referensi dihapus.', 'info');
    });

    const reader = new FileReader();
    reader.onload = (e) => {
      const img = document.createElement('img');
      img.src = e.target.result;
      img.className = 'img-thumb';
      img.alt = `Referensi ${index + 1}: ${file.name}`;
      wrapper.appendChild(img);
    };
    wrapper.appendChild(removeBtn);
    list.appendChild(wrapper);
    reader.readAsDataURL(file);
  });
}

function compactStoryPartContext(storyboard) {
  if (!storyboard) return {};
  const scenes = Array.isArray(storyboard.scenes) ? storyboard.scenes : [];
  return {
    film_title: storyboard.film_title || '',
    logline: storyboard.logline || '',
    genre_style: storyboard.genre_style || '',
    emotional_arc: storyboard.emotional_arc || '',
    characters: storyboard.characters || [],
    consistent_characters: storyboard.consistent_characters || '',
    open_loops: storyboard.open_loops || storyboard.loop_ledger || [],
    last_scenes: scenes.slice(-3).map(scene => ({
      scene_number: scene.scene_number,
      title: scene.title,
      action_summary: scene.action_summary,
      dialogue: scene.dialogue,
      characters_in_scene: scene.characters_in_scene,
      start_state: scene.start_state,
      end_state: scene.end_state,
      transition_bridge: scene.transition_bridge,
      duration: scene.duration
    }))
  };
}

function mergeStoryPart(previous, nextPart) {
  if (!previous) return nextPart;
  const oldScenes = Array.isArray(previous.scenes) ? previous.scenes : [];
  const newScenes = Array.isArray(nextPart.scenes) ? nextPart.scenes : [];
  const merged = { ...previous, ...nextPart, scenes: [...oldScenes, ...newScenes] };
  const characterMap = new Map();
  [...(previous.characters || []), ...(nextPart.characters || [])].forEach(character => {
    const key = String(character.source_actor_id || character.id || character.name || '').toLowerCase();
    if (!key) return;
    characterMap.set(key, { ...(characterMap.get(key) || {}), ...character });
  });
  merged.characters = [...characterMap.values()];
  merged.character_references = {
    ...(nextPart.character_references || {}),
    ...(previous.character_references || {})
  };
  [
    'film_asset_id', 'film_title', 'logline', 'premise', 'character_seed', 'consistent_characters',
    'character_info', 'aspect_ratio', 'visual_style', 'visual_vibe', 'lighting_style',
    'color_palette', 'target_country', 'target_lang', 'dracin_theme', 'creative_brief'
  ].forEach(key => {
    if (previous[key] !== undefined && previous[key] !== null && previous[key] !== '') {
      merged[key] = previous[key];
    }
  });
  let elapsed = 0;
  merged.scenes.forEach((scene, index) => {
    const duration = parseInt(scene.duration, 10) || 10;
    const fmt = seconds => `${Math.floor(seconds / 60)}:${String(seconds % 60).padStart(2, '0')}`;
    scene.scene_number = index + 1;
    scene.time_range = `${fmt(elapsed)}–${fmt(elapsed + duration)}`;
    elapsed += duration;
  });
  merged.scene_count = merged.scenes.length;
  merged.story_parts = {
    ...(nextPart.story_parts || previous.story_parts || {}),
    generated_scene_count: merged.scenes.length,
    has_next_part: merged.scenes.length < Number(nextPart.story_parts?.total_scene_count || previous.story_parts?.total_scene_count || merged.scenes.length)
  };
  return merged;
}

// Gemini Storyboard Form
function initStoryboardForm() {
  const form = document.getElementById('storyboardForm');
  const btnSend = document.getElementById('btnSendToExecution');

  // Microdrama & UGC Lifestyle are alternate style presets — keep them mutually exclusive
  const chkMicro = document.getElementById('chkMicrodramaMode');
  const chkUgc = document.getElementById('chkUgcMode');
  const chkChildren = document.getElementById('chkChildrenMode');
  const chkScript = document.getElementById('chkScriptMode');
  const chkAffiliate = document.getElementById('chkAffiliateMode');
  const modeBoxes = [chkMicro, chkUgc, chkChildren].filter(Boolean);
  const storyAgeTarget = document.getElementById('storyAgeTarget');
  document.getElementById('briefAudienceInput')?.addEventListener('input', event => { event.target.dataset.ageAutofill = 'false'; });
  const ageAudienceLabels = {
    general: '', toddler: 'Balita usia 2–4 tahun', early_child: 'Anak awal usia 5–7 tahun',
    older_child: 'Anak besar usia 8–10 tahun', preteen: 'Praremaja usia 11–13 tahun',
    teen: 'Remaja usia 14–17 tahun', genz_young: 'Gen Z muda usia 18–24 tahun',
    genz_adult: 'Gen Z dewasa usia 25–29 tahun', millennial: 'Milenial usia 30–44 tahun',
    genx: 'Gen X usia 45–59 tahun', senior: 'Senior usia 60 tahun ke atas',
    family: 'Keluarga lintas generasi'
  };
  const applyStoryAgeTarget = () => {
    if (!storyAgeTarget) return;
    const audienceInput = document.getElementById('briefAudienceInput');
    if (audienceInput && (!audienceInput.value.trim() || audienceInput.dataset.ageAutofill === 'true')) {
      audienceInput.value = ageAudienceLabels[storyAgeTarget.value] || '';
      audienceInput.dataset.ageAutofill = 'true';
    }
    const childSafe = ['toddler', 'early_child', 'older_child', 'preteen'].includes(storyAgeTarget.value);
    if (chkChildren && chkChildren.checked !== childSafe && storyAgeTarget.value !== 'general') {
      chkChildren.checked = childSafe;
      chkChildren.dispatchEvent(new Event('change'));
    }
  };
  const storyUniverseSelect = document.getElementById('storyUniverseSelect');
  const storyConflictSelect = document.getElementById('storyConflictSelect');
  let aiStoryUniverseMap = new Map();
  const refreshStoryConflicts = () => {
    if (!storyConflictSelect) return;
    const conflicts = aiStoryUniverseMap.get(storyUniverseSelect?.value) || STORY_CONFLICTS[storyAgeTarget?.value || 'general'] || STORY_CONFLICTS.general;
    storyConflictSelect.innerHTML = '<option value="">-- Pilih konflik --</option>' + conflicts.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join('');
  };
  const refreshStoryUniverses = () => {
    if (!storyUniverseSelect) return;
    const profile = CONTENT_UNIVERSE_PROFILES[storyAgeTarget?.value];
    const universes = profile?.subjects || ['drama kehidupan', 'hubungan dan keluarga', 'perjuangan dan perubahan', 'misteri', 'komedi situasi'];
    storyUniverseSelect.innerHTML = '<option value="">-- Pilih universe --</option>' + universes.map(item => `<option value="${escapeHtml(item)}">${escapeHtml(item)}</option>`).join('');
    refreshStoryConflicts();
  };
  storyAgeTarget?.addEventListener('change', () => { aiStoryUniverseMap = new Map(); refreshStoryUniverses(); applyStoryAgeTarget(); });
  storyUniverseSelect?.addEventListener('change', refreshStoryConflicts);
  refreshStoryUniverses();
  document.getElementById('generateAudienceUniverseAi')?.addEventListener('click', async event => {
    const button = event.currentTarget;
    const status = document.getElementById('audienceUniverseAiStatus');
    const selectedPreset = document.getElementById('genreCatalogSelect')?.selectedOptions?.[0]?.textContent || '';
    const payload = {
      audience: ageAudienceLabels[storyAgeTarget?.value] || 'Audiens umum',
      country: document.getElementById('targetCountryInput')?.value || '',
      language: document.getElementById('targetLanguageInput')?.value || '',
      genre: selectedPreset,
      preset: document.getElementById('dracinThemeSelect')?.value || '',
      premise: (document.getElementById('premiseInput')?.value || '').slice(0, 1200)
    };
    button.disabled = true;
    button.textContent = '⏳ AI sedang meracik...';
    if (status) { status.textContent = 'Mencari sudut kehidupan dan konflik yang tidak generik...'; status.className = ''; }
    try {
      const response = await fetch('/api/storyboard/audience_universe', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload) });
      const data = await response.json();
      if (!response.ok || !data.success) throw new Error(data.detail || 'Provider AI tidak merespons');
      const packageData = data.package || {};
      aiStoryUniverseMap = new Map((packageData.universes || []).map(item => [item.name, item.conflicts || []]));
      storyUniverseSelect.innerHTML = '<option value="">-- Pilih universe racikan AI --</option>' + [...aiStoryUniverseMap.keys()].map(name => `<option value="${escapeHtml(name)}">${escapeHtml(name)}</option>`).join('');
      const emotionSelect = document.getElementById('storyEmotionSelect');
      if (emotionSelect) emotionSelect.innerHTML = (packageData.emotions || []).map(emotion => `<option value="${escapeHtml(emotion)}">${escapeHtml(emotion)}</option>`).join('');
      refreshStoryConflicts();
      if (status) { status.textContent = `Siap dari ${packageData.provider || 'AI'} · pilih universe untuk melihat konflik khususnya.`; status.className = 'ready'; }
      showToast('Universe, konflik, dan perjalanan emosi baru berhasil diracik AI.', 'success');
    } catch (error) {
      if (status) { status.textContent = `AI gagal: ${error.message}. Opsi lokal tetap dapat dipakai.`; status.className = 'warn'; }
      showToast('Racikan AI gagal; opsi lokal tidak dihapus.', 'warning');
    } finally {
      button.disabled = false;
      button.textContent = '✨ Racik Universe dengan AI';
    }
  });
  document.getElementById('genreCatalogSelect')?.addEventListener('change', event => {
    const option = event.target.selectedOptions?.[0];
    if (!option || !storyAgeTarget) return;
    const presetAge = option.dataset.ageGroup;
    if (presetAge === 'toddler') storyAgeTarget.value = 'toddler';
    else if (presetAge === 'preschool') storyAgeTarget.value = 'early_child';
    else if (presetAge === 'early-reader') storyAgeTarget.value = 'older_child';
    else if (option.dataset.children === 'true') storyAgeTarget.value = 'early_child';
    else return;
    applyStoryAgeTarget();
  });
  modeBoxes.forEach(box => {
    box.addEventListener('change', () => {
      // The three story modes carry conflicting rule sets, so only one may be active.
      if (box.checked) modeBoxes.forEach(other => { if (other !== box) other.checked = false; });
    });
  });
  if (chkChildren) {
    chkChildren.addEventListener('change', () => {
      const visualStyle = document.getElementById('visualStyleSelect');
      if (!visualStyle) return;
      if (chkChildren.checked) {
        // Recommend the preschool-friendly default, but keep the selector editable.
        visualStyle.value = '3d_cartoon';
        visualStyle.disabled = false;
        visualStyle.title = 'Kartun 3D hanya rekomendasi awal. Anda bebas memilih style visual lain.';
      } else {
        visualStyle.disabled = false;
        visualStyle.title = '';
      }
    });
  }

  if (chkScript) {
    chkScript.addEventListener('change', () => {
      const label = document.getElementById('premiseInputLabel');
      const input = document.getElementById('premiseInput');
      const hint = document.getElementById('scriptModeHint');
      const autoButton = document.getElementById('autoSuggestBtn');
      if (chkScript.checked) {
        if (label) label.textContent = '📄 Script Lengkap (alur & dialog tidak diubah):';
        if (input) {
          input.rows = 14;
          input.placeholder = 'Tempel script lengkap di sini: episode, lokasi, aksi, karakter, dan dialog...';
        }
        if (hint) hint.style.display = 'block';
        if (autoButton) autoButton.disabled = true;
        const submit = document.getElementById('generateStoryboardBtn');
        if (submit) submit.innerHTML = '📄 Format Script & Buat Storyboard Render';
      } else {
        if (label) label.textContent = '📝 Tema Singkat / Ide Utama Film (Bahasa Indonesia):';
        if (input) {
          input.rows = 5;
          input.placeholder = 'Ketik tema singkat di sini (contoh: Kisah petualangan pendekar wanita di kota cyberpunk berhujan neon)...';
        }
        if (hint) hint.style.display = 'none';
        if (autoButton) autoButton.disabled = false;
        const submit = document.getElementById('generateStoryboardBtn');
        if (submit) submit.innerHTML = '✨ Generate AI Storyboard (Gemini 3.6 Flash)';
      }
    });
  }

  if (chkAffiliate) {
    chkAffiliate.addEventListener('change', () => {
      const panel = document.getElementById('affiliateOptionsPanel');
      if (panel) panel.style.display = chkAffiliate.checked ? 'grid' : 'none';
    });
  }

  const affiliateImageInput = document.getElementById('affiliateImageInput');
  if (affiliateImageInput) {
    affiliateImageInput.addEventListener('change', event => {
      selectedAffiliateProductFiles = Array.from(event.target.files || []);
      const preview = document.getElementById('affiliateImagePreview');
      if (!preview) return;
      preview.innerHTML = selectedAffiliateProductFiles.map(file => {
        const src = URL.createObjectURL(file);
        return `<img src="${src}" alt="Referensi produk" title="${escapeHtml(file.name)}" style="width:54px; height:54px; object-fit:cover; border-radius:9px; border:1px solid rgba(251,146,60,.5);">`;
      }).join('');
    });
  }

  const presetSelect = document.getElementById('durationPresetSelect');
  const sceneInput = document.getElementById('sceneCountInput');
  const durationSelect = document.getElementById('durationPerSceneSelect');
  const totalLabel = document.getElementById('totalDurationLabel');
  const flowSceneSlotInput = document.getElementById('flowSceneSlotInput');
  const flowSceneSlotHint = document.getElementById('flowSceneSlotHint');
  const storyPartSizeInput = document.getElementById('storyPartSizeInput');
  const storyPartSizeHint = document.getElementById('storyPartSizeHint');

  function updateTotalDuration() {
    const scenes = parseInt(sceneInput.value) || 1;
    const flowCredits = scenes * 15;
    const isAuto = durationSelect.value === 'auto';
    // In Auto mode each scene picks its own 4/6/8/10s, so only a range can be shown.
    const dur = isAuto ? 7 : (parseInt(durationSelect.value) || 10);
    const fmt = (t) => {
      const m = Math.floor(t / 60), sc = t % 60;
      return m > 0 ? `${m} Menit ${sc > 0 ? sc + ' Detik' : ''}`.trim() : `${t} Detik`;
    };
    if (isAuto) {
      totalLabel.innerHTML = `⏱️ Estimasi: ${fmt(scenes * 4)}–${fmt(scenes * 10)} • Flow: ${scenes} × 15 = <b style="color:#c4b5fd;">${flowCredits} Kredit</b>`;
    } else {
      totalLabel.innerHTML = `⏱️ Total: ${fmt(scenes * dur)} (${scenes} Scene × ${dur}s) • Flow: ${scenes} × 15 = <b style="color:#c4b5fd;">${flowCredits} Kredit</b>`;
    }
    totalLabel.title = `Estimasi kredit Google Flow: ${scenes} scene × 15 kredit = ${flowCredits} kredit`;
    if (storyPartSizeHint) {
      const partSize = Math.max(1, Math.min(25, parseInt(storyPartSizeInput?.value, 10) || 15));
      const partCount = Math.ceil(scenes / partSize);
      const lastPart = scenes % partSize || partSize;
      storyPartSizeHint.innerHTML = scenes > partSize
        ? `Storyboard dibuat <b>${partCount} part</b>: maksimal ${partSize} scene per part, part terakhir ${lastPart} scene. Lanjutkan memakai tombol di Scene Master.`
        : `Total ${scenes} scene cukup dibuat dalam satu part.`;
    }
    if (flowSceneSlotHint) {
      const requestedSlots = parseInt(flowSceneSlotInput?.value, 10);
      const slots = Number.isFinite(requestedSlots) && requestedSlots > 0
        ? Math.min(requestedSlots, scenes)
        : scenes;
      const batches = Math.ceil(scenes / slots);
      flowSceneSlotHint.innerHTML = Number.isFinite(requestedSlots) && requestedSlots > 0
        ? `Batch ini maksimal <b>${slots}</b> scene baru. Total ${scenes} scene memerlukan sekitar <b>${batches} batch</b>; scene selesai tidak dihitung ulang saat Resume.`
        : `Kosong berarti semua <b>${scenes}</b> scene yang belum selesai akan dirender. Sisakan cadangan kuota untuk retry.`;
    }
  }

  if (presetSelect) {
    presetSelect.addEventListener('change', () => {
      const val = presetSelect.value;
      if (val !== 'custom') {
        const totalSecs = parseInt(val);
        const dur = durationSelect.value === 'auto' ? 7 : (parseInt(durationSelect.value) || 10);
        const scenes = Math.round(totalSecs / dur);
        sceneInput.value = scenes > 0 ? scenes : 1;
        updateTotalDuration();
      }
    });
  }

  if (sceneInput) sceneInput.addEventListener('input', updateTotalDuration);
  if (durationSelect) durationSelect.addEventListener('change', updateTotalDuration);
  if (flowSceneSlotInput) flowSceneSlotInput.addEventListener('input', updateTotalDuration);
  if (storyPartSizeInput) storyPartSizeInput.addEventListener('input', updateTotalDuration);

  const multiAngleChk = document.getElementById('chkMultiAngleShotFlow');
  if (multiAngleChk) {
    multiAngleChk.addEventListener('change', () => {
      if (multiAngleChk.checked) {
        showToast('🎬 Multi-Angle Shot Flow aktif: 4–6 variasi sudut kamera dinamis per adegan', 'info', 'Sinematografi Pro');
      } else {
        showToast('Multi-Angle dinonaktifkan (kamera standar)', 'info');
      }
    });
  }

  updateTotalDuration();

  const countryLanguageMap = {
    Indonesia: 'Indonesia', Malaysia: 'Melayu', Singapore: 'Inggris', Thailand: 'Thailand',
    Vietnam: 'Vietnam', Philippines: 'Tagalog', Japan: 'Jepang', 'South Korea': 'Korea',
    China: 'Mandarin', Taiwan: 'Mandarin', 'Saudi Arabia': 'Arab', 'United Arab Emirates': 'Arab',
    Qatar: 'Arab', Egypt: 'Arab', Turkey: 'Turki', Iran: 'Persia', India: 'Hindi',
    Pakistan: 'Urdu', Bangladesh: 'Bengali', 'United States': 'Inggris', 'United Kingdom': 'Inggris',
    France: 'Prancis', Germany: 'Jerman', Italy: 'Italia', Spain: 'Spanyol', Russia: 'Rusia',
    Brazil: 'Portugis', Mexico: 'Spanyol', Argentina: 'Spanyol', Canada: 'Inggris',
    'South Africa': 'Inggris', Nigeria: 'Inggris', Kenya: 'Inggris', Morocco: 'Arab',
    Australia: 'Inggris', 'New Zealand': 'Inggris'
  };

  const genreCatalog = document.getElementById('genreCatalogSelect');
  const btnRandomGenre = document.getElementById('btnRandomGenrePreset');
  const targetCountryInput = document.getElementById('targetCountryInput');
  const targetLanguageInput = document.getElementById('targetLanguageInput');
  const dracinThemeSelect = document.getElementById('dracinThemeSelect');
  const randomizeDracinThemes = (selectFirst = true) => {
    const group = document.getElementById('dracinRandomOptions');
    if (!group) return;
    const themes = generateDracinThemeOptions(8);
    group.innerHTML = themes.map((theme, index) => `<option value="${escapeHtml(theme)}">${index + 1}. ${escapeHtml(theme)}</option>`).join('');
    if (selectFirst && dracinThemeSelect && themes.length) dracinThemeSelect.value = themes[0];
    if (selectFirst) showToast('8 tema Dracin baru berhasil diracik. Klik lagi untuk kombinasi berbeda.', 'success');
  };
  document.getElementById('randomizeDracinThemes')?.addEventListener('click', () => randomizeDracinThemes(true));
  randomizeDracinThemes(false);

  if (targetCountryInput && targetLanguageInput) {
    targetCountryInput.addEventListener('change', () => {
      const countryVal = targetCountryInput.value;
      const matchedLanguage = countryLanguageMap[countryVal];
      if (matchedLanguage) targetLanguageInput.value = matchedLanguage;

      const charInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
      if (charInput && charInput.value.trim()) {
        showToast(`Negara target: ${countryVal} (${matchedLanguage || 'Inggris'}). Klik '🪄 Auto Concept AI' untuk meracik karakter lokal!`, 'info');
      }
    });
  }

  if (genreCatalog) {
    genreCatalog.addEventListener('change', () => {
      const val = genreCatalog.value;
      if (val === '__auto_reading__') {
        const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
        if (premiseInput) premiseInput.value = 'Buat materi belajar membaca baru yang interaktif dan bertahap untuk pembaca pemula. Pilih otomatis fokus fonik, huruf, suku kata, kata, kalimat, kosakata, urutan cerita, atau pemahaman bacaan yang belum berulang. Sesuaikan sepenuhnya dengan bahasa target dan hindari meminta generator video merender paragraf panjang.';
        const childrenBox = document.getElementById('chkChildrenMode');
        if (childrenBox) { childrenBox.checked = true; childrenBox.dispatchEvent(new Event('change')); }
        ['chkMicrodramaMode', 'chkUgcMode'].forEach(id => { const box = document.getElementById(id); if (box) box.checked = false; });
        const charInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
        if (charInput) charInput.value = '';
        showToast('Auto AI Literasi aktif: merancang latihan membaca baru sesuai bahasa target.', 'info');
        window.setTimeout(() => document.getElementById('autoSuggestBtn')?.click(), 0);
        return;
      }
      if (val === '__auto_ai__') {
        const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
        if (premiseInput) premiseInput.value = '';
        const charInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
        if (charInput) charInput.value = '';
        showToast('Auto AI aktif: sedang membuat niche dan premis baru, bukan mengambil template katalog.', 'info');
        window.setTimeout(() => document.getElementById('autoSuggestBtn')?.click(), 0);
        return;
      }
      if (val === '__auto_drama_series__') {
        const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
        if (premiseInput) premiseInput.value = '';
        const charInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
        if (charInput) charInput.value = '';
        ['chkChildrenMode', 'chkMicrodramaMode', 'chkUgcMode'].forEach(id => {
          const checkbox = document.getElementById(id);
          if (checkbox) checkbox.checked = false;
        });
        showToast('Auto Drama Series aktif: AI sedang membuat serial, episode, karakter tetap, dan cliffhanger baru.', 'info');
        window.setTimeout(() => document.getElementById('autoSuggestBtn')?.click(), 0);
        return;
      }
      if (val) {
        const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
        if (premiseInput) {
          premiseInput.value = val;

          const selectedOpt = genreCatalog.options[genreCatalog.selectedIndex];
          const isUgcPreset = selectedOpt && selectedOpt.getAttribute('data-ugc') === 'true';
          const isMicroPreset = selectedOpt && selectedOpt.getAttribute('data-micro') === 'true';
          const isChildrenPreset = selectedOpt && selectedOpt.getAttribute('data-children') === 'true';
          const childAgeGroup = selectedOpt ? selectedOpt.getAttribute('data-age-group') : '';
          const learningDomain = selectedOpt ? selectedOpt.getAttribute('data-learning-domain') : '';
          const countryAttr = selectedOpt ? selectedOpt.getAttribute('data-country') : '';
          const presetVisualStyle = selectedOpt ? selectedOpt.getAttribute('data-visual-style') : '';

          if (countryAttr && targetCountryInput) {
            targetCountryInput.value = countryAttr;
            if (targetLanguageInput && countryLanguageMap[countryAttr]) {
              targetLanguageInput.value = countryLanguageMap[countryAttr];
            }
          }

          const chkChildrenEl = document.getElementById('chkChildrenMode');
          if (chkChildrenEl) {
            chkChildrenEl.checked = !!isChildrenPreset;
            chkChildrenEl.dispatchEvent(new Event('change'));
          }
          if (presetVisualStyle) {
            const visualStyleSelect = document.getElementById('visualStyleSelect');
            if (visualStyleSelect) visualStyleSelect.value = presetVisualStyle;
          }
          const chkUgc = document.getElementById('chkUgcMode');
          const chkMicro = document.getElementById('chkMicrodramaMode');
          if (chkUgc) {
            chkUgc.checked = !!isUgcPreset && !isChildrenPreset;
            if (isUgcPreset && chkMicro) chkMicro.checked = false;
          }
          if (isChildrenPreset && chkMicro) chkMicro.checked = false;
          if (chkMicro && isMicroPreset && !isChildrenPreset) {
            chkMicro.checked = true;
            if (chkUgc) chkUgc.checked = false;
          }

          // Reset outdated character list when a new country/preset is chosen so old names do not contaminate new theme
          const charInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
          if (charInput && countryAttr) {
            charInput.value = '';
          }

          if (isChildrenPreset) {
            const ageLabel = childAgeGroup === 'toddler' ? 'Toddler 2–3 tahun' : childAgeGroup === 'early-reader' ? 'Pembaca pemula 5–8 tahun' : 'Prasekolah 4–6 tahun';
            const domainLabel = learningDomain ? ` • Fokus: ${learningDomain}` : '';
            showToast(`Preset: ${ageLabel}${domainLabel}.`, 'info');
          } else {
            const countryLabel = countryAttr ? ` (Negara: ${countryAttr})` : '';
            showToast(`✅ Preset dipilih${countryLabel}. Anda bisa sesuaikan Negara & Bahasa, lalu klik "🪄 Auto Concept AI" atau langsung "Generate AI Storyboard".`, 'success');
          }
        }
      }
    });
  }

  if (btnRandomGenre) {
    btnRandomGenre.addEventListener('click', () => {
      if (genreCatalog) {
        genreCatalog.value = '__auto_ai__';
        genreCatalog.dispatchEvent(new Event('change'));
      }
    });
  }

  const autoSuggestBtn = document.getElementById('autoSuggestBtn') || document.getElementById('btnAutoSuggestConcept');
  if (autoSuggestBtn) {
    autoSuggestBtn.addEventListener('click', async () => {
      const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
      let currentText = premiseInput ? premiseInput.value.trim() : '';
      const audienceContext = [ageAudienceLabels[storyAgeTarget?.value] || '', storyUniverseSelect?.value ? `universe ${storyUniverseSelect.value}` : '', storyConflictSelect?.value ? `konflik ${storyConflictSelect.value}` : '', document.getElementById('storyEmotionSelect')?.value ? `emosi utama ${document.getElementById('storyEmotionSelect').value}` : ''].filter(Boolean).join('; ');
      if (audienceContext) currentText = `${currentText || 'Buat konsep cerita baru'} untuk ${audienceContext}.`;

      autoSuggestBtn.disabled = true;
      autoSuggestBtn.textContent = '🪄 Memuat Ide AI...';

      const isMicrodrama = document.getElementById('chkMicrodramaMode') ? document.getElementById('chkMicrodramaMode').checked : false;
      const isChildrenAuto = document.getElementById('chkChildrenMode') ? document.getElementById('chkChildrenMode').checked : false;
      const isSeriesAuto = document.getElementById('genreCatalogSelect')?.value === '__auto_drama_series__';

      try {
        showCuteAiLoading(
          isMicrodrama ? '📱 Gemini AI Meracik Microdrama...' : '🤖 Gemini AI Memuat Ide...',
          isMicrodrama ? 'Sedang merancang formula 3-episode Microdrama / Dracin (Hook, Conflict, & Payoff)...' : 'Sedang meracik alur cerita sinematik super dramatis & konsistensi karakter...'
        );

        const targetCountryEl = document.getElementById('targetCountryInput');
        const targetCountry = targetCountryEl ? targetCountryEl.value.trim() : '';
        const targetLanguageEl = document.getElementById('targetLanguageInput');
        const targetLanguage = targetLanguageEl ? targetLanguageEl.value.trim() : '';
        const dracinThemeEl = document.getElementById('dracinThemeSelect');
        const dracinTheme = dracinThemeEl ? dracinThemeEl.value : '';

        let res, data;
        if (currentText) {
          res = await fetch('/api/storyboard/suggest', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ theme: currentText, microdrama_mode: isMicrodrama, children_mode: isChildrenAuto, series_mode: isSeriesAuto, target_country: targetCountry, target_lang: targetLanguage, dracin_theme: dracinTheme })
          });
        } else {
          res = await fetch(`/api/storyboard/auto_concept?microdrama_mode=${isMicrodrama}&children_mode=${isChildrenAuto}&series_mode=${isSeriesAuto}&target_country=${encodeURIComponent(targetCountry)}&target_lang=${encodeURIComponent(targetLanguage)}&dracin_theme=${encodeURIComponent(dracinTheme)}`);
        }

        data = await res.json();
        const suggested = data.concept || (data.suggestion && data.suggestion.suggested_premise);

        if (suggested && premiseInput) {
          premiseInput.value = suggested;
          showToast('Ide konsep sinematik berhasil dimuat dengan Gemini AI!', 'success');
        }

        if (data.suggestion) {
          const seedInput = document.getElementById('characterSeedInput') || document.getElementById('characterSeed');
          if (seedInput && data.suggestion.character_seed) seedInput.value = data.suggestion.character_seed;

          const charText = data.suggestion.suggested_character || data.suggestion.character_info || data.suggestion.suggested_characters;
          const charInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
          if (charInput && charText) charInput.value = charText;
        }

      } catch (err) {
        showToast('Gagal memuat ide konsep: ' + err.message, 'error');
      } finally {
        hideCuteAiLoading();
        autoSuggestBtn.disabled = false;
        autoSuggestBtn.textContent = '🪄 Auto Concept AI';
      }
    });
  }

  form.addEventListener('submit', async (e) => {
    e.preventDefault();

    const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
    const theme = premiseInput ? premiseInput.value.trim() : '';

    const sceneCount = sceneInput ? (parseInt(sceneInput.value) || 4) : 4;
    const partSizeInput = document.getElementById('storyPartSizeInput');
    const requestedPartSize = Math.max(1, Math.min(25, parseInt(partSizeInput?.value, 10) || 15));
    const canContinuePart = Boolean(
      storyPartContinuationRequested && currentStoryboard?.story_parts?.has_next_part
    );
    const totalStoryScenes = canContinuePart
      ? Number(currentStoryboard.story_parts.total_scene_count || sceneCount)
      : sceneCount;
    const storySceneOffset = canContinuePart ? (currentStoryboard.scenes || []).length : 0;
    const partSceneCount = Math.min(requestedPartSize, Math.max(0, totalStoryScenes - storySceneOffset));
    const storyPartNumber = canContinuePart
      ? Number(currentStoryboard.story_parts.part_number || 1) + 1
      : 1;

    const aspectSelect = document.getElementById('aspectSelect') || document.getElementById('aspectRatioSelect') || document.getElementById('settingAspectRatio');
    const aspectRatio = aspectSelect ? aspectSelect.value : 'portrait';

    const seedEl = document.getElementById('characterSeedInput') || document.getElementById('characterSeed');
    const seed = seedEl ? seedEl.value.trim() : '';

    const charEl = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
    const consistentChar = charEl ? charEl.value.trim() : '';
    const selectedAgeAudience = ageAudienceLabels[storyAgeTarget?.value] || '';
    const selectedUniverse = storyUniverseSelect?.value || '';
    const selectedConflict = storyConflictSelect?.value || '';
    const selectedEmotion = document.getElementById('storyEmotionSelect')?.value || '';
    const universeDirection = [selectedUniverse && `Universe: ${selectedUniverse}`, selectedConflict && `konflik: ${selectedConflict}`, selectedEmotion && `emosi utama: ${selectedEmotion}`].filter(Boolean).join('; ');
    const creativeBrief = {
      background: document.getElementById('briefBackgroundInput')?.value.trim() || '',
      result: document.getElementById('briefResultInput')?.value.trim() || '',
      audience: document.getElementById('briefAudienceInput')?.value.trim() || selectedAgeAudience,
      product_value: document.getElementById('briefProductValueInput')?.value.trim() || '',
      execution: [document.getElementById('briefExecutionInput')?.value.trim() || '', universeDirection].filter(Boolean).join('\n'),
      constraints: document.getElementById('briefConstraintsInput')?.value.trim() || ''
    };

    if (!theme) {
      showToast('Harap isi Tema / Ide Utama Film!', 'warning');
      return;
    }

    const isMicro = document.getElementById('chkMicrodramaMode') ? document.getElementById('chkMicrodramaMode').checked : false;
    const isUgc = document.getElementById('chkUgcMode') ? document.getElementById('chkUgcMode').checked : false;
    const isChildren = document.getElementById('chkChildrenMode') ? document.getElementById('chkChildrenMode').checked : false;
    const visualStyleEl = document.getElementById('visualStyleSelect');
    const visualStyle = visualStyleEl?.value || (isChildren ? '3d_cartoon' : 'live_action');
    const visualVibe = document.getElementById('visualVibeSelect')?.value || 'none';
    const lightingStyle = document.getElementById('lightingStyleSelect')?.value || 'none';
    const colorPalette = document.getElementById('colorPaletteSelect')?.value || 'none';
    const isScriptMode = chkScript ? chkScript.checked : false;
    const isAffiliate = chkAffiliate ? chkAffiliate.checked : false;
    const affiliateName = document.getElementById('affiliateProductName')?.value.trim() || '';
    const existingAffiliatePaths = currentStoryboard?.affiliate_product?.name === affiliateName
      ? (currentStoryboard.affiliate_product.reference_paths || [])
      : [];

    if (isAffiliate && !affiliateName) {
      showToast('Isi nama produk affiliate terlebih dahulu.', 'warning');
      return;
    }
    if (isAffiliate && !selectedAffiliateProductFiles.length && !existingAffiliatePaths.length) {
      showToast('Tambahkan minimal satu gambar referensi produk affiliate.', 'warning');
      return;
    }

    const targetCountryEl = document.getElementById('targetCountryInput');
    const targetCountry = targetCountryEl ? targetCountryEl.value.trim() : '';

    const targetLanguageEl = document.getElementById('targetLanguageInput');
    const targetLanguage = targetLanguageEl ? targetLanguageEl.value.trim() : 'Indonesia';

    const dracinThemeEl = document.getElementById('dracinThemeSelect');
    const dracinTheme = dracinThemeEl ? dracinThemeEl.value : '';

    const durModeEl = document.getElementById('durationPerSceneSelect');
    const durMode = durModeEl ? durModeEl.value : '10';

    const actorCheckboxes = document.querySelectorAll('#actorSelectionList_storyboard input[type="checkbox"]:checked');
    const actorIds = Array.from(actorCheckboxes).map(cb => cb.value).join(',');

    const formData = new FormData();
    formData.append('actor_ids', actorIds);
    formData.append('premise', theme);
    formData.append('creative_brief', JSON.stringify(creativeBrief));
    formData.append('scene_count', partSceneCount);
    formData.append('total_scene_count', totalStoryScenes);
    formData.append('story_part_number', storyPartNumber);
    formData.append('story_scene_offset', storySceneOffset);
    formData.append(
      'previous_part_context',
      JSON.stringify(canContinuePart ? compactStoryPartContext(currentStoryboard) : {})
    );
    formData.append('aspect_ratio', aspectRatio);
    formData.append('target_country', targetCountry);
    formData.append('target_lang', targetLanguage);
    formData.append('dracin_theme', dracinTheme);
    const multiAngle = document.getElementById('chkMultiAngleShotFlow')?.checked !== false;
    formData.append('multi_angle_shot_flow', multiAngle ? 'true' : 'false');
    formData.append('microdrama_mode', isMicro);
    formData.append('ugc_mode', isUgc);
    formData.append('ugc_variant', document.getElementById('ugcProductionMode')?.value || 'realism');
    formData.append('ugc_platform', document.getElementById('ugcPlatform')?.value || 'TikTok');
    formData.append('ugc_tone', document.getElementById('ugcTone')?.value.trim() || 'Natural, fresh, friendly');
    formData.append('ugc_emotional_arc', document.getElementById('ugcEmotionArc')?.value.trim() || '');
    const backgroundChoice = document.getElementById('ugcBackground')?.value || 'auto';
    const ugcEnvironment = backgroundChoice === 'custom' ? (document.getElementById('ugcCustomBackground')?.value.trim() || 'auto') : backgroundChoice;
    formData.append('ugc_environment', ugcEnvironment);
    const lightingChoice = document.getElementById('ugcLighting')?.value || 'auto';
    const ugcLighting = lightingChoice === 'custom' ? (document.getElementById('ugcCustomLighting')?.value.trim() || 'auto') : lightingChoice;
    formData.append('ugc_lighting', ugcLighting);
    formData.append('ugc_conversion_brief', JSON.stringify(getUgcConversionBrief()));
    formData.append('children_mode', isChildren);
    formData.append('visual_style', visualStyle);
    formData.append('visual_vibe', visualVibe);
    formData.append('lighting_style', lightingStyle);
    formData.append('color_palette', colorPalette);
    formData.append('script_mode', isScriptMode);
    formData.append('affiliate_enabled', isAffiliate);
    if (isAffiliate) {
      formData.append('affiliate_name', affiliateName);
      formData.append('affiliate_benefits', document.getElementById('affiliateBenefits')?.value.trim() || '');
      formData.append('affiliate_cta', document.getElementById('affiliateCta')?.value.trim() || '');
      formData.append('affiliate_style', document.getElementById('affiliateStyle')?.value || 'soft_selling');
      formData.append('affiliate_scene_position', document.getElementById('affiliateScenePosition')?.value || 'auto');
      const existingPaths = selectedAffiliateProductFiles.length
        ? []
        : existingAffiliatePaths;
      formData.append('affiliate_reference_paths', JSON.stringify(existingPaths));
      selectedAffiliateProductFiles.forEach(file => formData.append('affiliate_images', file));
    }
    if (seed) formData.append('character_seed', seed);
    if (consistentChar) formData.append('character_info', consistentChar);
    if (targetCountry) formData.append('target_country', targetCountry);
    if (dracinTheme) formData.append('dracin_theme', dracinTheme);
    // Tell the storyboard writer which pacing the user picked, so scene durations
    // match what will actually be rendered instead of drifting.
    if (durMode === 'auto') {
      formData.append('target_total_duration', String(totalStoryScenes * 7));
    } else {
      formData.append('fixed_scene_duration', durMode);
    }

    selectedRefFiles.forEach(f => formData.append('reference_images', f));

    const btn = form.querySelector('button[type="submit"]');
    btn.disabled = true;
    btn.innerHTML = isScriptMode
      ? '⚙️ Memformat Script Tanpa Mengubah Cerita...'
      : '⚡ Generating Storyboard (Gemini 3.6 Flash)...';

    try {
      showCuteAiLoading(
        isScriptMode ? '📄 Memformat Script untuk Render...' : '🎬 Generating Storyboard Sinematik...',
        isScriptMode
          ? `Membagi Part ${storyPartNumber} menjadi ${partSceneCount} adegan teknis tanpa mengubah alur atau dialog...`
          : `Sedang meracik Part ${storyPartNumber}: ${partSceneCount} scene (${storySceneOffset + 1}–${storySceneOffset + partSceneCount}) dari total ${totalStoryScenes}...`
      );
      const completedBeforeRequest = canContinuePart && currentStoryboard?.scenes
        ? currentStoryboard.scenes.length
        : 0;
      setCuteAiSceneProgress(completedBeforeRequest, totalStoryScenes, true);

      showToast('Merancang alur adegan dan prompt sinematik dengan Gemini 3.6 Flash...', 'info', 'Gemini AI Studio');
      const res = await fetch('/api/storyboard/generate', {
        method: 'POST',
        body: formData
      });

      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal generate storyboard');

      const previousStoryboard = canContinuePart ? currentStoryboard : null;
      currentStoryboard = mergeStoryPart(previousStoryboard, data.storyboard);
      setCuteAiSceneProgress(currentStoryboard.scenes?.length || 0, totalStoryScenes, false);
      const weakAssets = (data.asset_quality_report || []).filter(item => item.status !== 'production_ready');
      if (weakAssets.length) {
        showToast(`${weakAssets.length} aset referensi perlu diperbaiki. Detail audit disimpan di storyboard.`, 'warning', 'Asset Quality Gate');
      }
      // Remember how this storyboard was made so "Regenerate Storyboard" can reproduce the
      // exact same setup from any tab, without depending on the form still being filled in.
      currentStoryboard.aspect_ratio = aspectRatio;
      currentStoryboard.premise = theme;
      currentStoryboard.scene_count = currentStoryboard.scenes.length;
      currentStoryboard.story_parts = {
        ...(currentStoryboard.story_parts || {}),
        part_number: storyPartNumber,
        part_size: requestedPartSize,
        total_scene_count: totalStoryScenes,
        generated_scene_count: currentStoryboard.scenes.length,
        has_next_part: currentStoryboard.scenes.length < totalStoryScenes
      };
      currentStoryboard.character_info = consistentChar;
      currentStoryboard.target_country = targetCountry;
      currentStoryboard.target_lang = targetLanguage;
      currentStoryboard.dracin_theme = dracinTheme;
      currentStoryboard.duration_mode = durMode;
      currentStoryboard.microdrama_mode = isMicro;
      currentStoryboard.ugc_mode = isUgc;
      currentStoryboard.ugc_variant = document.getElementById('ugcProductionMode')?.value || 'realism';
      currentStoryboard.ugc_environment = ugcEnvironment;
      currentStoryboard.ugc_lighting = ugcLighting;
      currentStoryboard.children_mode = isChildren;
      currentStoryboard.visual_style = visualStyle;
      currentStoryboard.visual_vibe = visualVibe;
      currentStoryboard.lighting_style = lightingStyle;
      currentStoryboard.color_palette = colorPalette;
      currentStoryboard.script_mode = isScriptMode;
      currentStoryboard.creative_brief = currentStoryboard.creative_brief || creativeBrief;
      if (data.reference_images && data.reference_images.length) {
        currentStoryboard._theme_image_path = data.reference_images[0];
      }

      saveStoryboardToHistory(currentStoryboard);
      renderStoryboardResult(currentStoryboard);
      if (btnSend) btnSend.disabled = false;
      showToast(
        currentStoryboard.story_parts.has_next_part
          ? `Part ${storyPartNumber} selesai. ${currentStoryboard.scenes.length}/${totalStoryScenes} scene sudah tersusun.`
          : `Seluruh ${totalStoryScenes} scene storyboard berhasil disusun.`,
        'success'
      );

      const sceneMasterNav = document.querySelector('.nav-item[data-tab="tab-history"]');
      if (sceneMasterNav) sceneMasterNav.click();

    } catch (err) {
      showCustomAlert(err.message, 'Gagal Generate Storyboard', '❌');
    } finally {
      storyPartContinuationRequested = false;
      hideCuteAiLoading();
      btn.disabled = false;
      btn.innerHTML = isScriptMode
        ? '📄 Format Script & Buat Storyboard Render'
        : '✨ Generate AI Storyboard (Gemini 3.6 Flash)';
    }
  });

  if (btnSend) {
    btnSend.disabled = false; // Always enabled for user interaction!
    btnSend.addEventListener('click', async () => {
      if (!currentStoryboard) {
        const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
        if (premiseInput && premiseInput.value.trim()) {
          showToast('Merancang Storyboard terlebih dahulu sebelum dikirim ke Flow...', 'info');
          form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
          return;
        } else {
          showToast('Harap masukkan Tema Film terlebih dahulu!', 'warning');
          return;
        }
      }

      const aspectEl = document.getElementById('aspectSelect') || document.getElementById('settingAspectRatio');
      const aspect = (currentStoryboard && currentStoryboard.aspect_ratio) || (aspectEl ? aspectEl.value : 'portrait');
      const durSel = document.getElementById('durationPerSceneSelect').value;
      const isAutoDur = durSel === 'auto';
      const durPerScene = isAutoDur ? 10 : (parseInt(durSel) || 10);

      try {
        showToast('Mendaftarkan Job Eksekusi ke Google Flow...', 'info');
        const res = await fetch('/api/jobs/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            storyboard: currentStoryboard,
            theme_image_path: currentStoryboard._theme_image_path || null,
            aspect_ratio: aspect,
            duration: durPerScene,
            force_uniform_duration: !isAutoDur,
            render_scene_limit: (() => {
              const value = parseInt(document.getElementById('flowSceneSlotInput')?.value, 10);
              return Number.isFinite(value) && value > 0 ? value : null;
            })()
          })
        });

        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Gagal membuat job eksekusi');

        currentJobId = data.job_id;
        showToast(`Job ${currentJobId} didaftarkan! Mengalihkan ke Live Terminal...`, 'success');

        const stopBtn = document.getElementById('btnStopExecution');
        if (stopBtn) stopBtn.style.display = 'block';

        document.querySelector('.nav-item[data-tab="tab-execution"]').click();
        startJobPolling(currentJobId);

      } catch (err) {
        showCustomAlert(err.message, 'Gagal Memulai Eksekusi', '❌');
      }
    });
  }

  const stopExecutionBtn = document.getElementById('btnStopExecution');
  if (stopExecutionBtn) {
    stopExecutionBtn.addEventListener('click', () => {
      if (!currentJobId) return;
      showCustomConfirm(
        'Stop Eksekusi Video',
        'Apakah Anda yakin ingin menghentikan proses render video yang sedang berjalan?',
        '🛑 Stop Sekarang',
        '🛑',
        async () => {
          try {
            const res = await fetch(`/api/jobs/${currentJobId}/cancel`, { method: 'POST' });
            const data = await res.json();
            showToast(data.message || 'Job berhasil dihentikan!', 'warning');
            stopExecutionBtn.style.display = 'none';
            document.getElementById('executionStatusText').textContent = '🛑 Eksekusi dibatalkan oleh pengguna.';
          } catch (err) {
            showToast('Gagal menghentikan job: ' + err.message, 'error');
          }
        }
      );
    });
  }

  const resumeJobWithFeedback = async (targetJobId) => {
    let jid = targetJobId || currentJobId || localStorage.getItem('sinematica_last_job_id');
    if (!jid) {
      try {
        const listRes = await fetch('/api/jobs/list');
        if (listRes.ok) {
          const listData = await listRes.json();
          const jobs = listData.jobs || [];
          if (jobs.length > 0) jid = jobs[jobs.length - 1].job_id;
        }
      } catch (_) {}
    }
    if (!jid) {
      showToast('Belum ada job eksekusi yang tersimpan untuk dilanjutkan. Buat storyboard terlebih dahulu.', 'warning');
      return;
    }
    currentJobId = jid;
    try {
      localStorage.setItem('sinematica_last_job_id', jid);
    } catch (_) {}
    try {
      const slotValue = parseInt(document.getElementById('flowSceneSlotInput')?.value, 10);
      const res = await fetch(`/api/jobs/${jid}/resume`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          render_scene_limit: Number.isFinite(slotValue) && slotValue > 0 ? slotValue : null
        })
      });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal melanjutkan job');
      showToast(data.message || 'Job berhasil dilanjutkan!', 'success');
      document.querySelector('.nav-item[data-tab="tab-execution"]')?.click();
      const stopBtn = document.getElementById('btnStopExecution');
      if (stopBtn) stopBtn.style.display = 'block';
      startJobPolling(jid);
    } catch (err) {
      showToast('Gagal melanjutkan job: ' + err.message, 'error');
    }
  };

  const resumeExecutionBtn = document.getElementById('btnResumeExecution');
  if (resumeExecutionBtn) {
    resumeExecutionBtn.addEventListener('click', () => resumeJobWithFeedback());
  }

  const resumeMasterBtn = document.getElementById('btnResumeLastJobFromMaster');
  if (resumeMasterBtn) {
    resumeMasterBtn.addEventListener('click', () => resumeJobWithFeedback());
  }
}

function escapeHtml(str) {
  if (!str) return '';
  return String(str)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

let previewPlaylist = [];
let previewIndex = 0;

function showPreviewAt(i) {
  if (!previewPlaylist.length) return;
  // Wrap around so the last scene leads back to the first instead of dead-ending.
  previewIndex = (i + previewPlaylist.length) % previewPlaylist.length;
  const item = previewPlaylist[previewIndex];
  const overlay = document.getElementById('videoPreviewOverlay');
  if (!overlay || !item) return;

  const many = previewPlaylist.length > 1;
  overlay.querySelector('#videoPreviewTitle').textContent =
    (item.label || 'Preview Adegan') + (many ? `  (${previewIndex + 1}/${previewPlaylist.length})` : '');
  overlay.querySelector('#videoPreviewDownload').href = item.url;
  overlay.querySelector('#videoPreviewPlayer').src = item.url;
  overlay.querySelector('#videoPreviewPrev').style.visibility = many ? 'visible' : 'hidden';
  overlay.querySelector('#videoPreviewNext').style.visibility = many ? 'visible' : 'hidden';
}

function openVideoPreview(url, label, playlist, index) {
  let overlay = document.getElementById('videoPreviewOverlay');

  if (!overlay) {
    overlay = document.createElement('div');
    overlay.id = 'videoPreviewOverlay';
    overlay.style.cssText = 'position:fixed;inset:0;z-index:9999;display:none;align-items:center;justify-content:center;background:rgba(2,4,10,0.9);backdrop-filter:blur(6px);padding:24px;';
    const navBtn = 'cursor:pointer;flex-shrink:0;user-select:none;width:44px;height:64px;display:flex;align-items:center;justify-content:center;font-size:30px;font-weight:800;color:#fff;background:rgba(255,255,255,0.08);border:1px solid rgba(255,255,255,0.2);border-radius:12px;transition:background 0.2s;';
    overlay.innerHTML = `
      <div style="position:relative;display:flex;flex-direction:column;gap:10px;max-width:min(92vw,900px);">
        <div style="display:flex;align-items:center;gap:12px;">
          <span id="videoPreviewTitle" style="font-size:14px;font-weight:800;color:var(--neon-cyan);"></span>
          <a id="videoPreviewDownload" download class="btn-secondary" style="margin-left:auto;text-decoration:none;font-size:12px;padding:6px 12px;">⬇️ Download</a>
          <span id="videoPreviewClose" role="button" style="cursor:pointer;font-size:12px;font-weight:800;color:#fff;background:rgba(244,63,94,0.25);border:1px solid rgba(244,63,94,0.5);border-radius:8px;padding:6px 12px;">✕ Tutup</span>
        </div>
        <div style="display:flex;align-items:center;justify-content:center;gap:12px;">
          <span id="videoPreviewPrev" role="button" title="Adegan sebelumnya (←)" style="${navBtn}">‹</span>
          <video id="videoPreviewPlayer" controls autoplay playsinline style="max-width:100%;max-height:78vh;border-radius:12px;background:#000;"></video>
          <span id="videoPreviewNext" role="button" title="Adegan berikutnya (→)" style="${navBtn}">›</span>
        </div>
      </div>`;
    document.body.appendChild(overlay);

    // Stop playback on close so audio does not keep running behind the dashboard.
    const closePreview = () => {
      const player = document.getElementById('videoPreviewPlayer');
      try {
        player.pause();
        player.removeAttribute('src');
        player.load();
      } catch (_) {}
      overlay.style.display = 'none';
    };

    const prevEl = overlay.querySelector('#videoPreviewPrev');
    const nextEl = overlay.querySelector('#videoPreviewNext');
    [prevEl, nextEl].forEach(el => {
      el.addEventListener('mouseenter', () => { el.style.background = 'rgba(56,189,248,0.25)'; });
      el.addEventListener('mouseleave', () => { el.style.background = 'rgba(255,255,255,0.08)'; });
    });
    prevEl.addEventListener('click', (e) => { e.stopPropagation(); showPreviewAt(previewIndex - 1); });
    nextEl.addEventListener('click', (e) => { e.stopPropagation(); showPreviewAt(previewIndex + 1); });

    overlay.addEventListener('click', (e) => { if (e.target === overlay) closePreview(); });
    overlay.querySelector('#videoPreviewClose').addEventListener('click', closePreview);
    document.addEventListener('keydown', (e) => {
      if (overlay.style.display !== 'flex') return;
      if (e.key === 'Escape') closePreview();
      else if (e.key === 'ArrowLeft') showPreviewAt(previewIndex - 1);
      else if (e.key === 'ArrowRight') showPreviewAt(previewIndex + 1);
    });
  }

  previewPlaylist = (Array.isArray(playlist) && playlist.length) ? playlist : [{ url, label }];
  overlay.style.display = 'flex';
  showPreviewAt(typeof index === 'number' && index >= 0 ? index : 0);
}

// Shared cell styling for the per-scene storyboard breakdown table.
const SB_LABEL_CELL = 'display:flex;align-items:flex-start;gap:6px;padding:10px 12px;background:rgba(4,7,16,0.75);border-bottom:1px solid rgba(255,255,255,0.08);border-right:1px solid rgba(255,255,255,0.08);font-size:11px;font-weight:800;letter-spacing:0.4px;color:var(--text-secondary);white-space:nowrap;';
const SB_VALUE_CELL = 'padding:8px 10px;background:rgba(8,12,24,0.4);border-bottom:1px solid rgba(255,255,255,0.08);';
const SB_INPUT = 'width:100%;box-sizing:border-box;background:transparent;border:none;outline:none;font-size:13px;line-height:1.5;padding:2px 0;font-family:inherit;';

function renderStoryboardResult(storyboard) {
  currentStoryboard = storyboard;
  const btnSend = document.getElementById('btnSendToExecution');
  if (btnSend) btnSend.disabled = false;

  // Keep the aspect ratio dropdown in sync with the storyboard actually loaded,
  // so what the user sees matches what gets sent to Flow.
  const aspectSelectEl = document.getElementById('aspectSelect') || document.getElementById('settingAspectRatio');
  if (aspectSelectEl && storyboard && storyboard.aspect_ratio) {
    aspectSelectEl.value = storyboard.aspect_ratio;
  }

  const container = document.getElementById('storyboardOutput');
  if (!container) return;

  const scenes = storyboard.scenes || [];
  const storyParts = storyboard.story_parts || null;
  const totalStoryScenes = Number(storyParts?.total_scene_count || scenes.length);
  const hasNextStoryPart = Boolean(storyParts?.has_next_part && scenes.length < totalStoryScenes);

  let html = `
    <div style="margin-bottom: 24px; padding: 24px; background: linear-gradient(145deg, rgba(8, 14, 28, 0.9), rgba(16, 25, 48, 0.8)); border: 1px solid rgba(56, 189, 248, 0.3); border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.3);">
      
      <!-- Row 1: Judul Film & Action Buttons -->
      <div style="display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 18px; flex-wrap: wrap;">
        <div style="flex: 1; min-width: 280px;">
          <label style="font-size: 12px; color: var(--neon-cyan); font-weight: 800; display: block; margin-bottom: 6px; letter-spacing: 0.5px;">🎬 JUDUL FILM (EDITABLE):</label>
          <input type="text" id="editFilmTitle" value="${escapeHtml(storyboard.film_title || 'Film Sinematik')}" style="width: 100%; font-size: 18px; font-weight: 800; color: #ffffff; background: rgba(4, 7, 16, 0.85); border: 1px solid var(--neon-cyan); border-radius: 10px; padding: 10px 16px; font-family: var(--font-heading); box-shadow: 0 0 15px rgba(56, 189, 248, 0.2);" />
        </div>

        <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
          <span style="background: rgba(16, 185, 129, 0.15); color: #34d399; border: 1px solid rgba(16, 185, 129, 0.4); padding: 8px 16px; border-radius: 20px; font-size: 12px; font-weight: 700;">🌱 Seed: ${storyboard.character_seed || 'Auto'}</span>
          <span title="Rasio ini yang akan dipakai saat Kirim & Eksekusi ke Flow" style="background: rgba(56, 189, 248, 0.15); color: #38bdf8; border: 1px solid rgba(56, 189, 248, 0.4); padding: 8px 16px; border-radius: 20px; font-size: 12px; font-weight: 700;">${storyboard.aspect_ratio === 'portrait' ? '📱 Portrait 9:16' : '🖥️ Landscape 16:9'}</span>
          ${storyParts ? `<span style="background:rgba(167,139,250,.14);color:#ddd6fe;border:1px solid rgba(167,139,250,.4);padding:8px 14px;border-radius:20px;font-size:12px;font-weight:800;">🧩 Part ${storyParts.part_number || 1} · ${scenes.length}/${totalStoryScenes} Scene</span>` : ''}
          ${storyParts ? `<button type="button" class="btn-success" id="btnGenerateNextStoryPart" style="padding:9px 16px;font-size:12px;font-weight:800;border-radius:10px;height:40px;cursor:pointer;border:none;">${hasNextStoryPart ? '➕ Generate Part Berikutnya' : '➕ Tambah Part Baru'}</button>` : ''}
          <button type="button" class="btn-secondary" id="btnFullRegenerate" style="padding: 9px 16px; font-size: 12px; font-weight: 700; border-color: var(--neon-purple); color: #e9d5ff; border-radius: 10px; height: 40px; cursor: pointer;">🎲 Regenerate Storyboard</button>
          <button type="button" class="btn-secondary" id="btnCopyAllPrompts" style="padding: 9px 16px; font-size: 12px; font-weight: 700; border-color: var(--neon-cyan); color: var(--neon-cyan); border-radius: 10px; height: 40px; cursor: pointer;">📋 Copy untuk AI</button>
          <button type="button" class="btn-secondary" id="btnPasteReplaceStoryboard" style="padding: 9px 16px; font-size: 12px; font-weight: 700; border-color: #34d399; color: #6ee7b7; border-radius: 10px; height: 40px; cursor: pointer;">📥 Paste & Replace</button>
        </div>
      </div>

      <div class="ugc-board-summary">
        <div><b>LOGLINE</b><span>${escapeHtml(storyboard.logline || storyboard.premise || '')}</span></div>
        <div><b>TYPE</b><span>${escapeHtml(storyboard.video_type || (storyboard.ugc_mode ? 'UGC Review' : 'Story Content'))}</span></div>
        <div><b>PLATFORM</b><span>${escapeHtml(storyboard.platform || storyboard.ugc_platform || '-')}</span></div>
        <div><b>TONE</b><span>${escapeHtml(storyboard.tone || storyboard.ugc_tone || '-')}</span></div>
        <div class="wide"><b>EMOTIONAL ARC</b><span>${escapeHtml(storyboard.emotional_arc || '-')}</span></div>
        <div class="wide"><b>VISUAL NOTES</b><span>${escapeHtml(storyboard.visual_notes || storyboard.art_direction || '-')}</span></div>
        <div class="wide"><b>ENVIRONMENT</b><span>${escapeHtml(storyboard.environment_direction || storyboard.ugc_environment || 'AI recommendation')}</span></div>
        <div class="wide"><b>LIGHTING</b><span>${escapeHtml(storyboard.lighting_direction || storyboard.ugc_lighting || 'AI recommendation')}</span></div>
      </div>

      <!-- Row 2: Mood Visual & Karakter -->
      <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px;">
        <div style="background: rgba(4, 7, 16, 0.5); padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08);">
          <label style="font-size: 12px; color: var(--text-secondary); font-weight: 700; display: block; margin-bottom: 6px;">🎨 Mood Visual & Style:</label>
          <input type="text" id="editGenreStyle" value="${escapeHtml(storyboard.genre_style || '')}" style="width: 100%; font-size: 13px; color: #ffffff; background: rgba(4, 7, 16, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 8px 12px;" />
        </div>

        <div style="background: rgba(4, 7, 16, 0.5); padding: 12px 14px; border-radius: 10px; border: 1px solid rgba(255, 255, 255, 0.08);">
          <label style="font-size: 12px; color: var(--text-secondary); font-weight: 700; display: block; margin-bottom: 6px;">👤 Karakter & Seeds Konsisten:</label>
          <input type="text" id="editConsistentCharacters" value="${escapeHtml(storyboard.consistent_characters || '')}" style="width: 100%; font-size: 13px; color: #ffffff; background: rgba(4, 7, 16, 0.8); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 8px 12px;" />
        </div>
      </div>
    </div>
  `;

  scenes.forEach((sc, idx) => {
    const dur = sc.duration || 10;
    const isUgc = sc.time_range || (currentStoryboard && currentStoryboard.ugc_mode);
    const stepDur = isUgc ? 2 : dur;
    const durOf = (s) => {
      const d = parseInt(s && s.duration);
      return (d && d > 0) ? d : stepDur;
    };
    const startS = (storyboard.scenes || []).slice(0, idx).reduce((a, s) => a + durOf(s), 0);
    const endS = startS + durOf(sc);
    const fmt = s => `${Math.floor(s/60)}:${(s%60).toString().padStart(2,'0')}`;
    const timeRangeStr = sc.time_range || `${fmt(startS)}–${fmt(endS)}`;

    html += `
      <div class="scene-item-card" style="margin-bottom: 22px; padding: 22px; background: linear-gradient(145deg, rgba(12, 18, 36, 0.8), rgba(20, 29, 54, 0.7)); border: 1px solid rgba(56, 189, 248, 0.2); border-radius: 16px; box-shadow: 0 8px 24px rgba(0, 0, 0, 0.3); transition: all 0.3s;">
        
        <!-- Header Bar -->
        <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; border-bottom: 1px solid rgba(255, 255, 255, 0.06); padding-bottom: 12px;">
          <div style="display: flex; align-items: center; gap: 12px; flex: 1; min-width: 300px;">
            <span style="background: linear-gradient(135deg, var(--neon-cyan), var(--neon-purple)); color: #ffffff; font-weight: 800; font-size: 13px; padding: 6px 14px; border-radius: 20px; white-space: nowrap; box-shadow: 0 4px 12px rgba(56, 189, 248, 0.3);">
              Adegan ${sc.scene_number || (idx + 1)} (${timeRangeStr})
            </span>
            <input type="text" class="edit-sc-title" data-idx="${idx}" value="${escapeHtml(sc.title || '')}" placeholder="Judul Adegan..." style="flex: 1; font-size: 15px; font-weight: 800; color: #ffffff; background: rgba(4, 7, 16, 0.7); border: 1px solid rgba(255, 255, 255, 0.15); border-radius: 8px; padding: 8px 14px;" />
          </div>

          <div style="display: flex; gap: 10px; align-items: center; flex-wrap: wrap;">
            <select class="edit-sc-duration" data-idx="${idx}" title="Durasi klip adegan ini (Google Flow hanya mendukung 4/6/8/10 detik)" style="font-size: 12px; font-weight: 700; color: #fbbf24; background: rgba(251, 191, 36, 0.1); border: 1px solid rgba(251, 191, 36, 0.35); border-radius: 8px; padding: 6px 10px;">
              ${[4, 6, 8, 10].map(d => `<option value="${d}" ${durOf(sc) === d ? 'selected' : ''}>⏱️ ${d}s</option>`).join('')}
            </select>
            <button type="button" class="btn-secondary btn-regen-single-scene" data-idx="${idx}" data-scnum="${sc.scene_number || (idx + 1)}" style="padding: 6px 14px; font-size: 12px; font-weight: 700; border-color: rgba(236, 72, 153, 0.5); color: #f9a8d4; border-radius: 8px; cursor: pointer;">🎲 Regenerate</button>
          </div>
        </div>

        <!-- Storyboard breakdown table: one labelled row per field, like a production sheet -->
        <div style="display: grid; grid-template-columns: 132px 1fr; border: 1px solid rgba(255, 255, 255, 0.12); border-radius: 10px; overflow: hidden;">

          <div style="${SB_LABEL_CELL}">🎯 PURPOSE</div>
          <div style="${SB_VALUE_CELL}"><input type="text" class="edit-sc-meta" data-field="scene_purpose" data-idx="${idx}" value="${escapeHtml(sc.scene_purpose || '')}" placeholder="Hook / problem / demonstration / proof / payoff / CTA" style="${SB_INPUT} color:#f9a8d4;font-weight:700;"></div>

          <div style="${SB_LABEL_CELL}">🙂 EXPRESSION</div>
          <div style="${SB_VALUE_CELL}"><input type="text" class="edit-sc-meta" data-field="expression" data-idx="${idx}" value="${escapeHtml(sc.expression || '')}" placeholder="Perubahan ekspresi yang terlihat" style="${SB_INPUT} color:#fde68a;"></div>

          <div style="${SB_LABEL_CELL}">🧭 COMPOSITION</div>
          <div style="${SB_VALUE_CELL}"><textarea class="edit-sc-meta" data-field="visual_composition" data-idx="${idx}" rows="2" style="${SB_INPUT} color:#bae6fd;resize:vertical;">${sc.visual_composition || ''}</textarea></div>

          <div style="${SB_LABEL_CELL}">🔗 TRANSITION</div>
          <div style="${SB_VALUE_CELL}"><input type="text" class="edit-sc-meta" data-field="transition_bridge" data-idx="${idx}" value="${escapeHtml(sc.transition_bridge || '')}" placeholder="Aksi/prop/eyeline menuju scene berikutnya" style="${SB_INPUT} color:#a7f3d0;"></div>

          <div style="${SB_LABEL_CELL}">🎬 SHOT TYPE</div>
          <div style="${SB_VALUE_CELL}">
            <input type="text" class="edit-sc-shottype" data-idx="${idx}" value="${escapeHtml(sc.shot_type || '')}" placeholder="Close Up / Medium Shot / Wide Shot / OTS..." style="${SB_INPUT} color: #c4b5fd; font-weight: 700;" />
          </div>

          <div style="${SB_LABEL_CELL}">🎥 CAMERA</div>
          <div style="${SB_VALUE_CELL}">
            <input type="text" class="edit-sc-camera" data-idx="${idx}" value="${escapeHtml(sc.camera_movement || '')}" placeholder="Slow push-in / Handheld tracking / Static..." style="${SB_INPUT} color: var(--neon-cyan);" />
          </div>

          <div style="${SB_LABEL_CELL}">📝 ACTION</div>
          <div style="${SB_VALUE_CELL}">
            <textarea class="edit-sc-action" data-idx="${idx}" rows="2" placeholder="Ringkasan aksi adegan dalam Bahasa Indonesia..." style="${SB_INPUT} color: #e2e8f0; resize: vertical;">${sc.action_summary || ''}</textarea>
          </div>

          <div style="${SB_LABEL_CELL}">🎙️ VO</div>
          <div style="${SB_VALUE_CELL}">
            <textarea class="edit-sc-vo" data-idx="${idx}" rows="2" placeholder="Narasi dubbing Bahasa Indonesia (dipakai untuk subtitle SRT)..." style="${SB_INPUT} color: #a7f3d0; font-style: italic; resize: vertical;">${sc.narration_id || sc.voiceover_script || ''}</textarea>
          </div>

          <div style="${SB_LABEL_CELL}">💬 TEXT OVERLAY</div>
          <div style="${SB_VALUE_CELL}">
            <input type="text" class="edit-sc-overlay" data-idx="${idx}" value="${escapeHtml(sc.text_overlay || '')}" placeholder="Teks pendek di layar (maks 6 kata)..." style="${SB_INPUT} color: #fbbf24; font-weight: 700;" />
          </div>

          <div style="${SB_LABEL_CELL}">🎞️ SHOT FLOW</div>
          <div style="${SB_VALUE_CELL}">
            <div style="font-size: 11px; color: #a5f3fc; line-height: 1.6; padding: 4px 0;">
              ${Array.isArray(sc.shot_flow) && sc.shot_flow.length ? sc.shot_flow.map((sf, sfIdx) => `
                <div style="margin-bottom: 3px;">
                  <span style="color: var(--neon-cyan); font-weight: 800; font-family: monospace;">[${escapeHtml(sf.time || `S${sfIdx+1}`)}]</span>
                  <b style="color: #fde68a;">${escapeHtml(sf.angle || '')}:</b> ${escapeHtml(sf.description || '')}
                </div>
              `).join('') : '<span style="color:var(--text-muted); font-style:italic;">Otomatis disusun sebagai 4–6 transisi sudut kamera bertimestamp saat eksekusi</span>'}
            </div>
          </div>

          <div style="${SB_LABEL_CELL} border-bottom: none;">⚡ FLOW PROMPT</div>
          <div style="${SB_VALUE_CELL} border-bottom: none;">
            <textarea class="edit-sc-prompt" data-idx="${idx}" rows="4" style="${SB_INPUT} font-family: 'JetBrains Mono', 'Fira Code', Consolas, monospace; font-size: 12px; line-height: 1.6; color: #38bdf8; resize: vertical;">${sc.prompt_for_flow || ''}</textarea>
          </div>
        </div>
      </div>
    `;
  });

  container.innerHTML = html;

  bindStoryboardLiveEditing();
}

function bindStoryboardLiveEditing() {
  if (!currentStoryboard) return;

  const titleEl = document.getElementById('editFilmTitle');
  if (titleEl) titleEl.addEventListener('input', (e) => currentStoryboard.film_title = e.target.value);

  const genreEl = document.getElementById('editGenreStyle');
  if (genreEl) genreEl.addEventListener('input', (e) => currentStoryboard.genre_style = e.target.value);

  const charEl = document.getElementById('editConsistentCharacters');
  if (charEl) charEl.addEventListener('input', (e) => currentStoryboard.consistent_characters = e.target.value);

  const nextPartButton = document.getElementById('btnGenerateNextStoryPart');
  if (nextPartButton) {
    nextPartButton.addEventListener('click', () => {
      const meta = currentStoryboard?.story_parts || {};
      if (!meta.has_next_part) {
        const increment = Math.max(1, Number(meta.part_size || 15));
        meta.total_scene_count = (currentStoryboard.scenes || []).length + increment;
        meta.has_next_part = true;
        currentStoryboard.story_parts = meta;
      }
      const totalInput = document.getElementById('sceneCountInput');
      const partInput = document.getElementById('storyPartSizeInput');
      const premiseInput = document.getElementById('premiseInput') || document.getElementById('themeInput');
      const seedInput = document.getElementById('characterSeedInput') || document.getElementById('characterSeed');
      const characterInput = document.getElementById('characterInfoInput') || document.getElementById('consistentCharacterInput') || document.getElementById('characterInfo');
      if (totalInput) totalInput.value = meta.total_scene_count || currentStoryboard.scenes.length;
      if (partInput && meta.part_size) partInput.value = meta.part_size;
      if (premiseInput) premiseInput.value = currentStoryboard.premise || currentStoryboard.logline || '';
      if (seedInput && currentStoryboard.character_seed) seedInput.value = currentStoryboard.character_seed;
      if (characterInput) characterInput.value = currentStoryboard.character_info || currentStoryboard.consistent_characters || '';
      storyPartContinuationRequested = true;
      document.getElementById('storyboardForm')?.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
    });
  }

  document.querySelectorAll('.edit-sc-title').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].title = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-camera').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].camera_movement = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-shottype').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].shot_type = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-duration').forEach(el => {
    el.addEventListener('change', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (!currentStoryboard.scenes[idx]) return;
      currentStoryboard.scenes[idx].duration = parseInt(e.target.value) || 10;
      saveStoryboardToHistory(currentStoryboard);
      renderStoryboardResult(currentStoryboard); // refresh the cumulative timeline labels
    });
  });

  document.querySelectorAll('.edit-sc-action').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].action_summary = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-vo').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) {
        // Holds narration only — the text overlay has its own field, otherwise its label
        // would leak into narration_id and end up printed in the SRT subtitles.
        currentStoryboard.scenes[idx].narration_id = e.target.value;
        currentStoryboard.scenes[idx].voiceover_script = e.target.value;
      }
    });
  });

  document.querySelectorAll('.edit-sc-overlay').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx].text_overlay = e.target.value;
    });
  });

  document.querySelectorAll('.edit-sc-prompt').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      if (currentStoryboard.scenes[idx]) {
        currentStoryboard.scenes[idx].prompt_for_flow = e.target.value;
        currentStoryboard.scenes[idx].prompt = e.target.value;
      }
    });
  });

  // Copy the complete editable storyboard and strict JSON instructions for another AI.
  const btnCopy = document.getElementById('btnCopyAllPrompts');
  if (btnCopy) {
    btnCopy.addEventListener('click', async () => {
      const revisionPrompt = storyboardRevisionPrompt(currentStoryboard);
      try {
        await navigator.clipboard.writeText(revisionPrompt);
      } catch (_) {
        const helper = document.createElement('textarea');
        helper.value = revisionPrompt;
        document.body.appendChild(helper);
        helper.select();
        document.execCommand('copy');
        helper.remove();
      }
      const original = btnCopy.textContent;
      btnCopy.textContent = '✅ Siap Ditempel';
      setTimeout(() => { if (btnCopy.isConnected) btnCopy.textContent = original; }, 1800);
      showToast('Storyboard lengkap + instruksi JSON berhasil di-copy. Tempel ke Gemini atau GPT.', 'success');
    });
  }

  document.getElementById('btnPasteReplaceStoryboard')?.addEventListener('click', () => {
    if (!currentStoryboard) return showToast('Belum ada storyboard aktif untuk diganti.', 'warning');
    storyboardImportController?.openReplaceImport(currentStoryboard);
  });

  document.querySelectorAll('.edit-sc-meta').forEach(el => {
    el.addEventListener('input', (e) => {
      const idx = parseInt(e.target.getAttribute('data-idx'));
      const field = e.target.getAttribute('data-field');
      if (field && currentStoryboard.scenes[idx]) currentStoryboard.scenes[idx][field] = e.target.value;
    });
  });

  // Full Regenerate Storyboard button
  const btnFullRegenerate = document.getElementById('btnFullRegenerate');
  if (btnFullRegenerate) {
    btnFullRegenerate.addEventListener('click', () => {
      const form = document.getElementById('storyboardForm');
      if (!form) return;
      if (!currentStoryboard) {
        showToast('Belum ada storyboard yang dimuat untuk di-regenerate.', 'warning');
        return;
      }

      // This button can be pressed from Scene Master, where the storyboard form is not on
      // screen and may be empty. Restore every generation parameter from the storyboard
      // itself so the regenerate reproduces the same setup instead of failing validation.
      const setVal = (ids, value) => {
        if (value === undefined || value === null || value === '') return;
        for (const id of ids) {
          const el = document.getElementById(id);
          if (el) { el.value = value; return; }
        }
      };
      const setChecked = (id, value) => {
        const el = document.getElementById(id);
        if (el && typeof value === 'boolean') el.checked = value;
      };

      // Older storyboards were saved before the premise was recorded — rebuild one from
      // whatever the storyboard does carry so the button still works on them.
      let premise = currentStoryboard.premise;
      if (!premise || !String(premise).trim()) {
        const bits = [currentStoryboard.film_title, currentStoryboard.genre_style, currentStoryboard.consistent_characters]
          .filter(Boolean).join('. ');
        const firstAction = (currentStoryboard.scenes || []).map(s => s.action_summary).filter(Boolean)[0] || '';
        premise = [bits, firstAction].filter(Boolean).join(' ').trim();
      }

      if (!premise) {
        showToast('Storyboard ini tidak menyimpan tema. Isi Tema / Ide Utama Film di tab AI Storyboard dulu.', 'warning');
        document.querySelector('.nav-item[data-tab="tab-storyboard"]')?.click();
        return;
      }

      setVal(['premiseInput', 'themeInput'], premise);
      setVal(['aspectSelect', 'aspectRatioSelect', 'settingAspectRatio'], currentStoryboard.aspect_ratio);
      setVal(['sceneCountInput'], currentStoryboard.scene_count);
      setVal(['characterInfoInput', 'consistentCharacterInput', 'characterInfo'],
             currentStoryboard.character_info || currentStoryboard.consistent_characters);
      setVal(['characterSeedInput', 'characterSeed'], currentStoryboard.character_seed);
      setVal(['targetCountryInput'], currentStoryboard.target_country);
      setVal(['targetLanguageInput'], currentStoryboard.target_lang);
      setVal(['dracinThemeSelect'], currentStoryboard.dracin_theme);
      setVal(['durationPerSceneSelect'], currentStoryboard.duration_mode);
      setVal(['visualStyleSelect'], currentStoryboard.visual_style || (currentStoryboard.children_mode ? '3d_cartoon' : 'live_action'));
      setVal(['visualVibeSelect'], currentStoryboard.visual_vibe || 'none');
      setVal(['lightingStyleSelect'], currentStoryboard.lighting_style || 'none');
      setVal(['colorPaletteSelect'], currentStoryboard.color_palette || 'none');
      const brief = currentStoryboard.creative_brief || {};
      setVal(['briefBackgroundInput'], brief.background);
      setVal(['briefResultInput'], brief.result);
      setVal(['briefAudienceInput'], brief.audience);
      setVal(['briefProductValueInput'], brief.product_value);
      setVal(['briefExecutionInput'], brief.execution);
      setVal(['briefConstraintsInput'], brief.constraints);
      ['visualVibeSelect', 'lightingStyleSelect', 'colorPaletteSelect'].forEach(id =>
        document.getElementById(id)?.dispatchEvent(new Event('change'))
      );
      setChecked('chkMicrodramaMode', currentStoryboard.microdrama_mode);
      setChecked('chkUgcMode', currentStoryboard.ugc_mode);
      setVal(['ugcProductionMode'], currentStoryboard.ugc_variant || 'realism');
      setVal(['ugcPlatform'], currentStoryboard.ugc_platform || currentStoryboard.platform || 'TikTok');
      setVal(['ugcTone'], currentStoryboard.ugc_tone || currentStoryboard.tone || 'Natural, fresh, friendly');
      setVal(['ugcEmotionArc'], currentStoryboard.emotional_arc || '');
      setVal(['ugcLogline'], currentStoryboard.logline || '');
      const savedEnvironment = currentStoryboard.ugc_environment || 'auto';
      const environmentSelect = document.getElementById('ugcBackground');
      if (environmentSelect) {
        const known = [...environmentSelect.options].some(option => option.value === savedEnvironment);
        environmentSelect.value = known ? savedEnvironment : 'custom';
        const customEnvironment = document.getElementById('ugcCustomBackground');
        if (customEnvironment) { customEnvironment.disabled = known; customEnvironment.value = known ? '' : savedEnvironment; }
      }
      const savedUgcLighting = currentStoryboard.ugc_lighting || 'auto';
      const ugcLightingSelect = document.getElementById('ugcLighting');
      if (ugcLightingSelect) {
        const knownLighting = [...ugcLightingSelect.options].some(option => option.value === savedUgcLighting);
        ugcLightingSelect.value = knownLighting ? savedUgcLighting : 'custom';
        const customLighting = document.getElementById('ugcCustomLighting');
        if (customLighting) { customLighting.disabled = knownLighting; customLighting.value = knownLighting ? '' : savedUgcLighting; }
      }
      setChecked('chkChildrenMode', currentStoryboard.children_mode);
      setChecked('chkScriptMode', currentStoryboard.script_mode);
      document.getElementById('chkScriptMode')?.dispatchEvent(new Event('change'));
      const affiliate = currentStoryboard.affiliate_product || {};
      setChecked('chkAffiliateMode', !!affiliate.enabled);
      document.getElementById('chkAffiliateMode')?.dispatchEvent(new Event('change'));
      setVal(['affiliateProductName'], affiliate.name);
      setVal(['affiliateBenefits'], affiliate.benefits);
      setVal(['affiliateCta'], affiliate.cta);
      setVal(['affiliateStyle'], affiliate.style);
      if (affiliate.scene_position !== 'auto') setVal(['affiliateScenePosition'], affiliate.scene_position);

      form.dispatchEvent(new Event('submit', { cancelable: true, bubbles: true }));
      showToast('Memulai regenerate full storyboard baru...', 'info');
    });
  }

  // Single Scene Regenerate button
  document.querySelectorAll('.btn-regen-single-scene').forEach(btn => {
    btn.addEventListener('click', async (e) => {
      const idx = parseInt(btn.getAttribute('data-idx'));
      const scNum = parseInt(btn.getAttribute('data-scnum'));
      const sc = currentStoryboard.scenes[idx];
      if (!sc) return;

      btn.disabled = true;
      btn.textContent = '⏳ Regenerating...';

      try {
        showToast(`Regenerating varian baru Adegan ${scNum} dengan Gemini AI...`, 'info');
        const res = await fetch('/api/storyboard/regenerate_scene', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            film_title: currentStoryboard.film_title || 'Film Sinematik',
            scene_number: scNum,
            scene_title: sc.title || `Adegan ${scNum}`,
            consistent_characters: currentStoryboard.consistent_characters || '',
            genre_style: currentStoryboard.genre_style || '',
            target_lang: currentStoryboard.target_lang || (document.getElementById('targetLanguageInput') ? document.getElementById('targetLanguageInput').value.trim() : 'Indonesia')
          })
        });

        const data = await res.json();
        if (!res.ok || !data.scene) throw new Error(data.detail || 'Gagal regenerate adegan');

        const newSc = data.scene;
        sc.action_summary = newSc.action_summary || sc.action_summary;
        sc.prompt_for_flow = newSc.prompt_for_flow || sc.prompt_for_flow;
        sc.prompt = newSc.prompt_for_flow || sc.prompt;
        sc.camera_movement = newSc.camera_movement || sc.camera_movement;
        if (newSc.narration_id) {
          sc.narration_id = newSc.narration_id;
          sc.voiceover_script = newSc.narration_id;
        }

        renderStoryboardResult(currentStoryboard);
        saveStoryboardToHistory(currentStoryboard);
        showToast(`Adegan ${scNum} berhasil di-regenerate dengan prompt & aksi baru!`, 'success');

      } catch (err) {
        showToast(`Gagal regenerate adegan ${scNum}: ${err.message}`, 'error');
      } finally {
        btn.disabled = false;
        btn.textContent = '🎲 Regenerate Adegan Ini';
      }
    });
  });
}

// Execution Terminal Polling
function startJobPolling(jobId) {
  if (!jobId) return;
  currentJobId = jobId;
  try {
    localStorage.setItem('sinematica_last_job_id', jobId);
  } catch (_) {}
  if (pollTimer) clearInterval(pollTimer);
  pollTimer = setInterval(() => pollJobStatus(jobId), 3000);
  pollJobStatus(jobId);
}

async function restoreLastJobExecution() {
  let lastJobId = null;
  try {
    lastJobId = localStorage.getItem('sinematica_last_job_id');
  } catch (_) {}

  if (!lastJobId) {
    try {
      const res = await fetch('/api/jobs/list');
      if (res.ok) {
        const data = await res.json();
        const jobs = data.jobs || [];
        if (jobs.length > 0) {
          const latest = jobs[jobs.length - 1];
          if (latest && latest.job_id) {
            lastJobId = latest.job_id;
          }
        }
      }
    } catch (_) {}
  }

  if (lastJobId) {
    currentJobId = lastJobId;
    try {
      localStorage.setItem('sinematica_last_job_id', lastJobId);
    } catch (_) {}
    pollJobStatus(lastJobId);
    try {
      const checkRes = await fetch(`/api/jobs/${lastJobId}`);
      if (checkRes.ok) {
        const checkData = await checkRes.json();
        if (checkData.job && checkData.job.status === 'processing') {
          startJobPolling(lastJobId);
        }
      }
    } catch (_) {}
  }
}

async function pollJobStatus(jobId) {
  try {
    const res = await fetch(`/api/jobs/${jobId}`);
    if (res.status === 404) {
      if (pollTimer) {
        clearInterval(pollTimer);
        pollTimer = null;
      }
      if (currentJobId === jobId) currentJobId = null;
      const statusText = document.getElementById('executionStatusText');
      if (statusText) statusText.textContent = `Job ${jobId} sudah tidak tersedia — backend kemungkinan baru dimuat ulang.`;
      const stopBtn = document.getElementById('btnStopExecution');
      if (stopBtn) stopBtn.style.display = 'none';
      showToast('Polling dihentikan: job lama hilang setelah backend dimuat ulang.', 'warning');
      return;
    }
    if (!res.ok) {
      throw new Error(`Server mengembalikan HTTP ${res.status}`);
    }

    const data = await res.json();
    const job = data.job;
    const logs = data.logs || [];

    const timingText = job.processing_duration ? ` — Waktu proses: ${job.processing_duration}` : '';
    const sizeText = job.output_size_display ? ` — Ukuran: ${job.output_size_display}` : '';
    document.getElementById('executionStatusText').textContent = `Job ${job.job_id} — Status: ${job.status.toUpperCase()}${timingText}${sizeText}`;

    const stopBtn = document.getElementById('btnStopExecution');
    const resumeBtn = document.getElementById('btnResumeExecution');
    if (stopBtn) {
      stopBtn.style.display = job.status === 'processing' ? 'block' : 'none';
    }
    if (resumeBtn) {
      resumeBtn.style.display = job.status !== 'completed' ? 'inline-flex' : 'none';
    }

    const total = job.total_scenes || 1;
    const current = job.scenes ? job.scenes.filter(s => s.status === 'completed').length : 0;

    document.getElementById('jobProgressBadge').textContent = `${current} / ${total} Adegan Selesai`;
    document.getElementById('jobProgressBar').style.width = `${Math.round((current / total) * 100)}%`;

    // Render live scene cards
    const grid = document.getElementById('scenesLiveGrid');
    grid.innerHTML = (job.scenes || []).map(sc => `
      <div class="scene-item-card">
        <div class="scene-header">
          <span>Adegan ${sc.scene_number}: ${sc.title}</span>
          <span class="badge-status ${sc.status === 'completed' ? 'badge-ready' : 'badge-noauth'}">
            ${sc.status.toUpperCase()} (${sc.profile_used || 'Worker'})
          </span>
        </div>
        <p style="font-size: 13px;">${sc.prompt}</p>
        ${sc.relative_url ? `
        <div style="display: flex; align-items: center; gap: 10px; margin-top: 10px; padding: 8px 12px; border-radius: 8px; background: rgba(34, 197, 94, 0.1); border: 1px solid rgba(34, 197, 94, 0.35);">
          <span style="font-size: 14px;">✅</span>
          <span style="font-size: 12px; font-weight: 700; color: #4ade80;">Video tersimpan${sc.video_path ? ` — ${sc.video_path.split(/[\\/]/).pop()}` : ''}</span>
          <span style="font-size: 11px; color: var(--text-muted); margin-left: auto;">Tonton di tab Video Gallery</span>
        </div>` : ''}
        ${sc.status === 'failed' ? `
        <div style="display: flex; align-items: flex-start; gap: 10px; margin-top: 10px; padding: 8px 12px; border-radius: 8px; background: rgba(239, 68, 68, 0.1); border: 1px solid rgba(239, 68, 68, 0.35);">
          <span style="font-size: 14px;">❌</span>
          <span style="font-size: 12px; font-weight: 600; color: #f87171;">${sc.error ? String(sc.error).slice(0, 220) : 'Render adegan gagal.'}</span>
        </div>` : ''}
      </div>
    `).join('');

    // Update Terminal Logs
    const logBody = document.getElementById('terminalLogBody');
    logBody.innerHTML = logs.map(l => `
      <div class="log-line ${logLineCategory(l)}">[${l.timestamp}] [${l.profile}] ${l.message}</div>
    `).join('');
    logBody.scrollTop = logBody.scrollHeight;

    if (job.status === 'completed' || job.status === 'completed_partial' || job.status === 'failed' || job.status === 'cancelled') {
      clearInterval(pollTimer);
      pollTimer = null;
      if (job.status === 'completed') {
        showToast('Film sinematik berhasil digabungkan!', 'success', 'Render Selesai');
      }
    }

  } catch (err) {
    console.error('Job polling error:', err);
  }
}

document.getElementById('clearLogBtn').addEventListener('click', () => {
  document.getElementById('terminalLogBody').innerHTML = '';
});

const copyLogBtn = document.getElementById('copyLogBtn');
if (copyLogBtn) {
  copyLogBtn.addEventListener('click', () => {
    const logBody = document.getElementById('terminalLogBody');
    if (!logBody) return;
    const text = logBody.innerText || logBody.textContent;
    if (!text.trim()) {
      showToast('Belum ada log di terminal untuk disalin.', 'warning');
      return;
    }
    navigator.clipboard.writeText(text).then(() => {
      showToast('📋 Seluruh log terminal berhasil disalin ke clipboard! Siap ditempel.', 'success');
    }).catch(err => {
      showToast('Gagal menyalin log: ' + err.message, 'error');
    });
  });
}

// Gallery & Sequencer Studio
function initGallery() {
  const refreshBtn = document.getElementById('refreshGalleryBtn');
  const selectAllCb = document.getElementById('gallerySelectAllCheckbox');
  const deleteSelectedBtn = document.getElementById('deleteSelectedGalleryBtn');

  if (refreshBtn) refreshBtn.addEventListener('click', refreshGallery);

  if (selectAllCb) {
    selectAllCb.addEventListener('change', () => {
      const checkboxes = document.querySelectorAll('.gallery-item-checkbox');
      checkboxes.forEach(cb => cb.checked = selectAllCb.checked);
      updateGalleryDeleteSelectedButton();
    });
  }

  if (deleteSelectedBtn) {
    deleteSelectedBtn.addEventListener('click', () => {
      const selected = Array.from(document.querySelectorAll('.gallery-item-checkbox:checked')).map(cb => cb.getAttribute('data-jobid'));
      if (!selected.length) return;

      showCustomConfirm(
        'Hapus Pilihan Massal',
        `Apakah Anda yakin ingin menghapus ${selected.length} job yang dipilih secara permanen?`,
        `Ya, Hapus ${selected.length} Item`,
        '🗑️',
        async () => {
          try {
            const res = await fetch('/api/gallery/batch_delete', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ job_ids: selected })
            });
            const data = await res.json();
            showToast(data.message || 'Job berhasil dihapus!', 'success');
            refreshGallery();
          } catch (err) {
            showToast('Gagal menghapus job: ' + err.message, 'error');
          }
        }
      );
    });
  }

  const clearBtn = document.getElementById('autoRenderClearBtn');
  if (clearBtn) {
    clearBtn.addEventListener('click', () => {
      selectedRenderClips = [];
      document.querySelectorAll('.clip-render-checkbox:checked').forEach(cb => cb.checked = false);
      updateAutoRenderBar();
    });
  }

  const autoRenderBtn = document.getElementById('autoRenderBtn');
  if (autoRenderBtn) {
    autoRenderBtn.addEventListener('click', async () => {
      if (selectedRenderClips.length < 1) return;
      const transition = document.getElementById('autoRenderTransition').value;

      autoRenderBtn.disabled = true;
      autoRenderBtn.textContent = '⏳ Merender...';
      try {
        const res = await fetch('/api/gallery/render_selection', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            clips: selectedRenderClips.map(r => ({ job_id: r.job_id, filename: r.filename })),
            transition,
            title: `Sequencer Custom (${selectedRenderClips.length} klip)`
          })
        });
        const data = await res.json();
        if (!res.ok) throw new Error(data.detail || 'Gagal render.');

        showToast('🎬 Video hasil pilihan berhasil digabungkan! Cek di bagian atas Galeri.', 'success');
        selectedRenderClips = [];
        updateAutoRenderBar();
        refreshGallery();
      } catch (err) {
        showToast('Gagal auto-render: ' + err.message, 'error');
      } finally {
        autoRenderBtn.disabled = false;
        autoRenderBtn.textContent = '🚀 Auto Render Klip Terpilih';
      }
    });
  }
}

function updateAutoRenderBar() {
  const bar = document.getElementById('autoRenderBar');
  const countEl = document.getElementById('autoRenderCount');
  if (!bar || !countEl) return;

  if (selectedRenderClips.length > 0) {
    bar.style.display = 'flex';
    countEl.textContent = `🎬 ${selectedRenderClips.length} klip dipilih (urutan sesuai klik)`;
  } else {
    bar.style.display = 'none';
  }
}

function updateGalleryDeleteSelectedButton() {
  const selected = document.querySelectorAll('.gallery-item-checkbox:checked');
  const btn = document.getElementById('deleteSelectedGalleryBtn');
  const selectAllCb = document.getElementById('gallerySelectAllCheckbox');
  const allCbs = document.querySelectorAll('.gallery-item-checkbox');

  if (btn) {
    btn.disabled = selected.length === 0;
    btn.textContent = `🗑️ Hapus Pilihan (${selected.length})`;
  }
  if (selectAllCb && allCbs.length > 0) {
    selectAllCb.checked = selected.length === allCbs.length;
  }
}


function galleryVersionedMediaUrl(url, item = {}, extra = '') {
  if (!url) return '';
  const parts = [];
  if (item.completed_at != null) parts.push(`done=${encodeURIComponent(String(item.completed_at))}`);
  if (item.output_size_bytes != null) parts.push(`bytes=${encodeURIComponent(String(item.output_size_bytes))}`);
  if (item.job_id) parts.push(`job=${encodeURIComponent(String(item.job_id))}`);
  if (extra) parts.push(`clip=${encodeURIComponent(String(extra))}`);
  if (!parts.length) parts.push(`v=${Date.now()}`);
  return `${url}${url.includes('?') ? '&' : '?'}${parts.join('&')}`;
}

function installGalleryVideoRecovery(container) {
  container.querySelectorAll('video[data-gallery-src]').forEach(video => {
    const original = video.getAttribute('data-gallery-src');
    let recovered = false;
    const reloadWithFreshUrl = () => {
      if (recovered || !original) return;
      recovered = true;
      const fresh = `${original}${original.includes('?') ? '&' : '?'}reload=${Date.now()}`;
      video.src = fresh;
      video.load();
    };
    video.addEventListener('error', reloadWithFreshUrl, { once: true });
    video.addEventListener('loadedmetadata', () => {
      if (!Number.isFinite(video.duration) || video.duration <= 0) reloadWithFreshUrl();
    }, { once: true });
  });
}

async function refreshGallery() {
  try {
    const res = await fetch('/api/gallery');
    if (!res.ok) return;
    const data = await res.json();

    const container = document.getElementById('galleryContainer');
    const items = data.gallery || [];
    let storyboardHistory = [];
    try {
      storyboardHistory = JSON.parse(localStorage.getItem('sinematica_storyboard_history') || '[]');
    } catch (_) {}
    gallerySeoContexts = new Map(items.map(item => {
      const matchingStoryboard = storyboardHistory.find(sb => sb?.film_title === item.title) || null;
      return [String(item.job_id), {
        initial_prompt: item.initial_prompt || matchingStoryboard?.premise || '',
        story_context: item.seo_story_context || matchingStoryboard?.premise || item.initial_prompt || '',
        storyboard: item.seo_storyboard || matchingStoryboard,
        aspect_ratio: item.aspect_ratio || matchingStoryboard?.aspect_ratio || 'landscape',
        target_lang: item.target_lang || matchingStoryboard?.target_lang
          || document.getElementById('targetLanguageInput')?.value || 'Indonesia',
        target_country: item.target_country || matchingStoryboard?.target_country
          || document.getElementById('targetCountryInput')?.value || ''
      }];
    }));
    const galleryPrompts = new Map(items.map(item => [String(item.job_id), item.initial_prompt || '']));
    const selectAllCb = document.getElementById('gallerySelectAllCheckbox');
    if (selectAllCb) selectAllCb.checked = false;
    updateGalleryDeleteSelectedButton();

    if (items.length === 0) {
      container.innerHTML = `
        <div class="empty-state">
          <div class="empty-icon">🎥</div>
          <h4>Belum Ada Hasil Video di Galeri</h4>
          <p>Jalankan job pembuatan video di tab Storyboard untuk mulai menghasilkan klip adegan.</p>
        </div>
      `;
      return;
    }

    container.innerHTML = `<div class="gallery-grid">` + items.map(item => {
      const fullMovieUrl = galleryVersionedMediaUrl(item.cinematic_film_url, item, 'full');
      return `
      <div class="film-card" style="position: relative;">
        <!-- Header Row 1: Title, Checkbox & Quick Edit/Delete Actions -->
        <div style="display: flex; justify-content: space-between; align-items: center; gap: 10px; margin-bottom: 8px;">
          <div style="display: flex; align-items: center; gap: 10px; flex: 1; min-width: 0;">
            <input type="checkbox" class="gallery-item-checkbox" data-jobid="${item.job_id}" style="cursor: pointer; width: 16px; height: 16px; flex-shrink: 0;" />
            <h4 class="film-card-title" title="${escapeHtml(item.title || 'Film Sinematik')}" style="margin: 0; font-size: 15px; font-weight: bold; color: var(--neon-cyan); overflow: hidden; text-overflow: ellipsis; white-space: nowrap;">${escapeHtml(item.title || 'Film Sinematik')}</h4>
          </div>
          <div style="display: flex; gap: 6px; align-items: center; flex-shrink: 0;">
            <span role="button" class="icon-action-btn btn-edit-single-job" data-jobid="${item.job_id}" data-title="${escapeHtml(item.title || 'Film Sinematik')}" title="Edit Judul Film" style="background: rgba(255, 255, 255, 0.08) !important; border: 1px solid rgba(255, 255, 255, 0.15) !important; color: #ffffff !important; display: inline-flex !important; align-items: center !important; justify-content: center !important; width: 28px !important; height: 28px !important; border-radius: 6px !important; cursor: pointer !important;">✏️</span>
            <span role="button" class="icon-action-btn icon-action-btn-danger btn-delete-single-job" data-jobid="${item.job_id}" title="Hapus Item Galeri" style="background: rgba(244, 63, 94, 0.2) !important; border: 1px solid rgba(244, 63, 94, 0.4) !important; color: #ffffff !important; display: inline-flex !important; align-items: center !important; justify-content: center !important; width: 28px !important; height: 28px !important; border-radius: 6px !important; cursor: pointer !important;">🗑️</span>
          </div>
        </div>

        <!-- Header Row 2: Badges & Timestamp -->
        <div style="display: flex; gap: 8px; align-items: center; flex-wrap: wrap; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px solid rgba(255, 255, 255, 0.08);">
          <span class="badge-status badge-ready" style="font-size: 10px; padding: 2px 7px; background: rgba(56, 189, 248, 0.15); border-color: rgba(56, 189, 248, 0.3); color: #38bdf8;">${item.aspect_ratio === 'portrait' ? '📱 Short 9:16' : '🖥️ Landscape 16:9'}</span>
          <span class="badge-status ${item.status === 'completed' ? 'badge-ready' : 'badge-noauth'}" style="font-size: 10px; padding: 2px 7px;">${(item.status || 'UNKNOWN').toUpperCase()}</span>
          ${item.total_duration != null ? `<span class="gallery-meta-chip">🎞️ ${Number(item.total_duration)}s</span>` : ''}
          ${item.output_size_display ? `<span class="gallery-meta-chip">💾 ${escapeHtml(item.output_size_display)}</span>` : ''}
          ${item.processing_duration ? `<span class="gallery-meta-chip">⏱️ ${escapeHtml(item.processing_duration)}</span>` : ''}
          ${item.postproduction_qc ? `<span class="gallery-meta-chip" style="color:${item.postproduction_qc.status === 'automatic_checks_passed' ? '#6ee7b7' : '#fbbf24'}">${item.postproduction_qc.status === 'automatic_checks_passed' ? '✅ QC otomatis lolos' : `⚠️ QC: ${(item.postproduction_qc.findings || []).length} temuan`}</span>` : ''}
          <span style="font-size: 11px; color: var(--text-muted); margin-left: auto;">📅 ${item.created_at_formatted || 'Tersimpan'}</span>
        </div>

        ${item.postproduction_qc ? `<details class="gallery-qc-panel">
          <summary>🔬 Color, lighting & artifact QC</summary>
          <p>${escapeHtml(item.postproduction_qc.reference_policy || '')}</p>
          ${(item.postproduction_qc.findings || []).length ? `<ul>${item.postproduction_qc.findings.map(f => `<li>Adegan ${f.scene}: ${escapeHtml(String(f.issue || '').replaceAll('_', ' '))}${f.delta != null ? ` (delta ${f.delta})` : ''}</li>`).join('')}</ul>` : '<p class="qc-pass">Tidak ditemukan outlier exposure/white balance/flicker oleh pemeriksaan otomatis.</p>'}
          <p><b>Tetap wajib manual:</b> putar 0.5×; cek tangan, mulut, wajah, rambut, tepi produk, ghosting, dan lipsync. Dengarkan dengan headphone.</p>
          ${item.postproduction_qc_url ? `<a href="${item.postproduction_qc_url}" download class="btn-secondary">⬇️ Unduh laporan QC JSON</a>` : ''}
        </details>` : ''}

        <div class="gallery-idea-box">
          <div class="gallery-idea-heading">
            <span>💡 Prompt / Ide Awal</span>
            <button type="button" class="btn-copy-gallery-prompt" data-jobid="${item.job_id}" ${item.initial_prompt ? '' : 'disabled'}>📋 Salin</button>
          </div>
          <p title="${escapeHtml(item.initial_prompt || '')}">${escapeHtml(item.initial_prompt || 'Ide awal belum tersimpan untuk video lama ini.')}</p>
        </div>

        ${item.cinematic_film_url ? `
          <div style="margin-bottom: 12px; background: rgba(52, 211, 153, 0.1); padding: 12px; border-radius: 8px; border: 1px solid rgba(52, 211, 153, 0.3);">
            <b style="color: var(--neon-green); font-size: 13px;">🎬 Full Cinematic Movie:</b>
            <video src="${fullMovieUrl}" data-gallery-src="${item.cinematic_film_url}" controls preload="auto" playsinline style="margin-top: 6px; width: 100%; max-height: 300px; object-fit: contain; background: #000; border-radius: 8px;"></video>
            <div style="display: flex; gap: 8px; margin-top: 10px;">
              <a href="${fullMovieUrl}" download class="btn-primary" style="flex: 1; text-align: center; text-decoration: none; font-size: 13px;">⬇️ Download Movie MP4</a>
              ${item.srt_subtitles_url ? `<a href="${item.srt_subtitles_url}" download class="btn-secondary" style="text-align: center; text-decoration: none; font-size: 13px;">💬 Subtitle SRT</a>` : ''}
            </div>
            ${localStorage.getItem(seoStorageKey(item.job_id)) ? `
              <div class="gallery-seo-actions">
                <button type="button" class="btn-secondary btn-view-seo" data-jobid="${item.job_id}">👁️ View SEO</button>
                <button type="button" class="btn-secondary btn-regenerate-seo" data-jobid="${item.job_id}" data-title="${escapeHtml(item.title || 'Film Sinematik')}">🔄 Regenerate</button>
              </div>
            ` : `
              <button type="button" class="btn-secondary btn-generate-seo" data-jobid="${item.job_id}" data-title="${escapeHtml(item.title || 'Film Sinematik')}" style="margin-top: 10px; width: 100%; border-color: var(--neon-purple); color: #e9d5ff; font-size: 13px;">🚀 Generate YouTube SEO</button>
            `}
          </div>
        ` : ''}

        <h5 style="margin-top: 14px; font-size: 13px; color: var(--neon-cyan);">🎞️ Klip Adegan (${(item.clips || []).length} Scene) — klik untuk preview:</h5>
        <div class="gallery-clips-grid" style="--clip-row-height: ${item.aspect_ratio === 'portrait' ? '172px' : '96px'};">
          ${(item.clips || []).map((c, i) => `
            <div class="clip-thumb" data-url="${galleryVersionedMediaUrl(c.url, item, c.filename || i + 1)}" data-label="${escapeHtml(item.title || 'Film')} — Adegan ${i + 1}" title="Klik untuk preview Adegan ${i + 1}"
                 style="position: relative; cursor: pointer; border: 1px solid var(--glass-border); border-radius: 8px; overflow: hidden; background: #04070f; aspect-ratio: ${item.aspect_ratio === 'portrait' ? '9 / 16' : '16 / 9'};">
              <video src="${galleryVersionedMediaUrl(c.url, item, c.filename || i + 1)}#t=0.5" data-gallery-src="${c.url}" preload="metadata" muted playsinline style="width: 100%; height: 100%; object-fit: cover; pointer-events: none;"></video>
              <div style="position: absolute; inset: 0; display: flex; align-items: center; justify-content: center; background: linear-gradient(180deg, rgba(0,0,0,0.05), rgba(0,0,0,0.6));">
                <span style="font-size: 18px; opacity: 0.9;">▶️</span>
              </div>
              <input type="checkbox" class="clip-render-checkbox" data-jobid="${item.job_id}" data-filename="${c.filename}" data-url="${c.url}" data-label="${item.title || 'Film'} - Adegan ${i + 1}"
                     title="Pilih untuk digabung di Sequencer" style="position: absolute; top: 5px; left: 5px; cursor: pointer; width: 14px; height: 14px; z-index: 2;" />
              <span style="position: absolute; bottom: 4px; left: 6px; font-size: 10px; font-weight: 800; color: #fff; text-shadow: 0 1px 4px #000;">Adegan ${i + 1}</span>
            </div>
          `).join('')}
        </div>
      </div>
    `;
    }).join('') + `</div>`;

    installGalleryVideoRecovery(container);

    // Keep only the first gallery row visible (three films on desktop). Additional
    // films scroll inside the gallery instead of making the whole page very long.
    const clampGalleryToFirstRow = () => {
      const grid = container.querySelector('.gallery-grid');
      const cards = [...(grid?.querySelectorAll('.film-card') || [])];
      if (!grid || !cards.length) return;
      const gridRect = grid.getBoundingClientRect();
      const firstTop = cards[0].getBoundingClientRect().top;
      const firstRow = cards.filter(card => Math.abs(card.getBoundingClientRect().top - firstTop) < 3);
      if (cards.length <= firstRow.length) {
        container.classList.remove('gallery-scroll-active');
        container.style.maxHeight = '';
        return;
      }
      const rowBottom = Math.max(...firstRow.map(card => card.getBoundingClientRect().bottom));
      container.style.maxHeight = `${Math.ceil(rowBottom - gridRect.top)}px`;
      container.classList.add('gallery-scroll-active');
    };
    requestAnimationFrame(clampGalleryToFirstRow);
    // Video metadata can settle card height shortly after initial paint.
    window.setTimeout(clampGalleryToFirstRow, 400);

    // Thumbnail opens the preview; the sequencer checkbox on top of it must not.
    container.querySelectorAll('.clip-thumb').forEach(thumb => {
      thumb.addEventListener('click', (e) => {
        if (e.target.classList.contains('clip-render-checkbox')) return;
        // Scenes of the same film become the playlist, so ‹ › steps through that film only.
        const siblings = [...thumb.parentElement.querySelectorAll('.clip-thumb')];
        const playlist = siblings.map(t => ({
          url: t.getAttribute('data-url'),
          label: t.getAttribute('data-label')
        }));
        openVideoPreview(thumb.getAttribute('data-url'), thumb.getAttribute('data-label'),
                         playlist, siblings.indexOf(thumb));
      });
    });

    // Attach listeners for single job edit, deletion and checkbox change
    container.querySelectorAll('.gallery-item-checkbox').forEach(cb => {
      cb.addEventListener('change', updateGalleryDeleteSelectedButton);
    });

    container.querySelectorAll('.btn-copy-gallery-prompt').forEach(btn => {
      btn.addEventListener('click', async () => {
        const prompt = galleryPrompts.get(String(btn.getAttribute('data-jobid'))) || '';
        if (!prompt) return;
        await navigator.clipboard.writeText(prompt);
        showToast('Prompt / ide awal berhasil disalin!', 'success');
      });
    });

    // Auto Render sequencer: clip selection preserves click order across jobs
    container.querySelectorAll('.clip-render-checkbox').forEach(cb => {
      const isSelected = selectedRenderClips.some(r => r.job_id === cb.getAttribute('data-jobid') && r.filename === cb.getAttribute('data-filename'));
      cb.checked = isSelected;
      cb.addEventListener('change', () => {
        const ref = { job_id: cb.getAttribute('data-jobid'), filename: cb.getAttribute('data-filename'), label: cb.getAttribute('data-label') };
        if (cb.checked) {
          selectedRenderClips.push(ref);
        } else {
          selectedRenderClips = selectedRenderClips.filter(r => !(r.job_id === ref.job_id && r.filename === ref.filename));
        }
        updateAutoRenderBar();
      });
    });

    container.querySelectorAll('.btn-edit-single-job').forEach(btn => {
      btn.addEventListener('click', () => {
        const jobId = btn.getAttribute('data-jobid');
        const currentTitle = btn.getAttribute('data-title');

        showCustomPrompt(
          'Ubah Judul Film Sinematik',
          'Ketikkan judul baru untuk film ini:',
          currentTitle,
          async (newTitle) => {
            if (!newTitle || newTitle === currentTitle) return;
            try {
              const res = await fetch(`/api/gallery/${jobId}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ title: newTitle })
              });
              const data = await res.json();
              showToast(data.message || 'Judul film berhasil diperbarui!', 'success');
              refreshGallery();
            } catch (err) {
              showToast('Gagal memperbarui judul film: ' + err.message, 'error');
            }
          }
        );
      });
    });

    container.querySelectorAll('.btn-delete-single-job').forEach(btn => {
      btn.addEventListener('click', () => {
        const jobId = btn.getAttribute('data-jobid');
        if (!jobId) return;

        showCustomConfirm(
          'Hapus Item Galeri',
          'Apakah Anda yakin ingin menghapus item galeri film ini secara permanen?',
          'Ya, Hapus',
          '🗑️',
          async () => {
            try {
              const res = await fetch(`/api/gallery/${jobId}`, { method: 'DELETE' });
              const data = await res.json();
              showToast(data.message || 'Job berhasil dihapus!', 'success');
              refreshGallery();
            } catch (err) {
              showToast('Gagal menghapus job: ' + err.message, 'error');
            }
          }
        );
      });
    });

    updateAutoRenderBar();
  } catch (err) {
    console.error('Gallery refresh error:', err);
  }
}

// Studio Settings Dashboard Tab
const DEFAULT_V41_TEMPLATE = `CHARACTER SHEET MASTER PROMPT V4.1

Studio Portfolio Edition
Clean • Elegant • Professional • AI Optimized

Create a clean, elegant, studio-quality Character Sheet for {char_name} (Character Seed: {char_seed}): {char_desc}.

Transform the subject into a consistent original character design while preserving the overall appearance, proportions, hairstyle, outfit style, silhouette, and recognizable visual language.

The layout should resemble a professional concept art portfolio page with generous white space, minimal typography, thin divider lines, and a balanced editorial composition.

LAYOUT:
Large "CHARACTER SHEET" title | Character Name: {char_name} | Soft beige or warm white background | Thin black divider lines | Minimal editorial typography | Spacious composition | Balanced margins | Professional portfolio presentation.

TURNAROUND:
Front View | Side View | Back View
Use identical character proportions, hairstyle, clothing design, silhouette, and visual appearance across all three views.

FACIAL EXPRESSIONS:
Three close-up portraits only: Neutral, Smile, Thoughtful. Expressions should modify only facial muscles while maintaining the same character appearance.

DYNAMIC POSES:
Three natural full-body poses only: Walking, Standing, Sitting. Keep body proportions, clothing behavior, hairstyle, and overall design consistent.

REFERENCE PORTRAIT:
One clean portrait showing the definitive appearance of {char_name}. Centered composition. Natural expression. Soft studio lighting.

CONSISTENCY:
Maintain a single coherent character design across every panel. Keep consistent: Facial structure | Hairstyle | Body proportions | Clothing construction | Accessories | Colors | Silhouette | Fabric behavior | Visual style.

RENDER STYLE:
Ultra photorealistic | Editorial fashion photography | Premium concept art | Soft studio lighting | Clean shadows | High detail | Natural skin texture | Accurate anatomy | Realistic fabric | Elegant presentation | Minimalistic portfolio design.

NEGATIVE PROMPT:
Busy layout, cluttered composition, excessive annotations, technical blueprint, production diagram, material callouts, color palette, measurement chart, camera reference, lighting reference, oversized text, crowded design, duplicate panels, inconsistent character design, different hairstyle, different clothing, different proportions, low quality, blurry textures, AI artifacts, cartoon style, anime style, painterly rendering, distorted anatomy.`;

async function loadSettingsTab() {
  try {
    const res = await fetch('/api/settings');
    const data = await res.json();
    const s = data.settings || {};
    const keys = s.gemini_api_keys && s.gemini_api_keys.length ? s.gemini_api_keys : (s.gemini_api_key ? [s.gemini_api_key] : []);
    
    const keyTabEl = document.getElementById('settingGeminiKeyTab') || document.getElementById('settingGeminiKey');
    if (keyTabEl && keys.length) keyTabEl.value = keys.join('\n');

    const modelTabEl = document.getElementById('settingGeminiModelTab') || document.getElementById('settingGeminiModel');
    if (modelTabEl && s.gemini_model) modelTabEl.value = s.gemini_model;

    const providerRadio = document.querySelector(`input[name="defaultTextProvider"][value="${s.default_text_provider || 'gemini'}"]`);
    if (providerRadio) providerRadio.checked = true;
    const openAIKeys = s.openai_api_keys?.length ? s.openai_api_keys : (s.openai_api_key ? [s.openai_api_key] : []);
    const deepSeekKeys = s.deepseek_api_keys?.length ? s.deepseek_api_keys : (s.deepseek_api_key ? [s.deepseek_api_key] : []);
    const xaiKeys = s.xai_api_keys?.length ? s.xai_api_keys : (s.xai_api_key ? [s.xai_api_key] : []);
    const nineRouterKeys = s.nine_router_api_keys?.length ? s.nine_router_api_keys : (s.nine_router_api_key ? [s.nine_router_api_key] : []);
    const openAIKeyEl = document.getElementById('settingOpenAIKeyTab');
    const deepSeekKeyEl = document.getElementById('settingDeepSeekKeyTab');
    const xaiKeyEl = document.getElementById('settingXAIKeyTab');
    const nineRouterKeyEl = document.getElementById('setting9RouterKeyTab');
    if (openAIKeyEl) openAIKeyEl.value = openAIKeys.join('\n');
    if (deepSeekKeyEl) deepSeekKeyEl.value = deepSeekKeys.join('\n');
    if (xaiKeyEl) xaiKeyEl.value = xaiKeys.join('\n');
    if (nineRouterKeyEl) nineRouterKeyEl.value = nineRouterKeys.join('\n');
    const openAIModelEl = document.getElementById('settingOpenAIModelTab');
    const deepSeekModelEl = document.getElementById('settingDeepSeekModelTab');
    const xaiModelEl = document.getElementById('settingXAIModelTab');
    const xaiBaseUrlEl = document.getElementById('settingXAIBaseUrlTab');
    const nineRouterModelEl = document.getElementById('setting9RouterModelTab');
    const nineRouterBaseUrlEl = document.getElementById('setting9RouterBaseUrlTab');
    if (openAIModelEl) openAIModelEl.value = s.openai_model || 'gpt-4.1-mini';
    if (deepSeekModelEl) deepSeekModelEl.value = s.deepseek_model || 'deepseek-chat';
    if (xaiModelEl) xaiModelEl.value = s.xai_model || 'grok-4.3';
    if (xaiBaseUrlEl) xaiBaseUrlEl.value = s.xai_base_url || 'https://api.x.ai/v1';
    if (nineRouterModelEl) nineRouterModelEl.value = s.nine_router_model || 'premium-coding';
    if (nineRouterBaseUrlEl) nineRouterBaseUrlEl.value = s.nine_router_base_url || 'http://127.0.0.1:20128/v1';

    const projTabEl = document.getElementById('settingFlowProjectIdTab') || document.getElementById('settingFlowProjectId');
    if (projTabEl && (s.default_flow_project_id || s.flow_project_id)) {
      projTabEl.value = s.default_flow_project_id || s.flow_project_id;
    }
    
    const enableTabCb = document.getElementById('settingEnableSeedImageTab') || document.getElementById('settingEnableSeedImage');
    if (enableTabCb) enableTabCb.checked = s.enable_character_seed_image !== false;

    const templateTabArea = document.getElementById('settingSeedTemplateTab') || document.getElementById('settingSeedTemplate');
    if (templateTabArea) templateTabArea.value = s.character_seed_template || DEFAULT_V41_TEMPLATE;
  } catch (err) {
    console.error('Gagal memuat settings tab:', err);
  }
}

function initSettingsModal() {
  initSettingsTab();
}

function initSettingsTab() {
  const saveBtn = document.getElementById('saveSettingsTabBtn') || document.getElementById('saveSettingsBtn');
  const testBtn = document.getElementById('testGeminiKeyTabBtn') || document.getElementById('testGeminiKeyBtn');
  const resetBtn = document.getElementById('resetSeedTemplateTabBtn') || document.getElementById('resetSeedTemplateBtn');
  const openAITestBtn = document.getElementById('testOpenAIKeyTabBtn');
  const deepSeekTestBtn = document.getElementById('testDeepSeekKeyTabBtn');
  const xaiTestBtn = document.getElementById('testXAIKeyTabBtn');
  const nineRouterTestBtn = document.getElementById('test9RouterKeyTabBtn');

  const statusLabels = {
    valid: '✅ Valid & terhubung',
    quota_limited: '⚠️ Valid, tetapi kuota habis/terbatas',
    invalid: '❌ API key tidak sah',
    unreachable: '🌐 Tidak dapat terhubung',
    model_unavailable: '🧩 Key dikenali, tetapi model belum aktif/dibeli di workspace ini'
  };

  async function testProviderKeys(provider, keyElement, modelElement, button, resultElement, baseUrlElement = null) {
    const rawKeys = keyElement?.value.trim() || '';
    if (!rawKeys) return showToast(`Harap masukkan API key ${provider}!`, 'warning');
    const oldText = button.textContent;
    const keyCount = rawKeys.split(/[\n,]+/).map(key => key.trim()).filter(Boolean).length;
    const startedAt = Date.now();
    button.disabled = true;
    button.textContent = `⏳ Menguji ${provider}... 0s`;
    if (resultElement) resultElement.textContent = `Menguji ${keyCount} key secara paralel...`;
    const progressTimer = window.setInterval(() => {
      button.textContent = `⏳ Menguji ${provider}... ${Math.floor((Date.now() - startedAt) / 1000)}s`;
    }, 1000);
    try {
      const response = await fetch('/api/settings/test_ai_keys', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider,
          api_keys: rawKeys,
          model: modelElement?.value || null,
          base_url: baseUrlElement?.value?.trim() || null
        })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data.detail || 'Pengujian gagal');
      const summary = data.results.map(item => {
        const diagnostic = item.detail ? `<br><small style="color:var(--text-muted)">HTTP ${item.http_status || '-'} — ${escapeHtml(item.detail)}</small>` : '';
        return `Key #${item.index} (${item.key_preview}): ${statusLabels[item.status] || item.status}${diagnostic}`;
      }).join('<br>');
      if (resultElement) resultElement.innerHTML = summary;
      const validCount = data.results.filter(item => item.status === 'valid').length;
      showToast(`${provider}: ${validCount}/${data.results.length} key valid`, validCount ? 'success' : 'warning');
    } catch (error) {
      if (resultElement) resultElement.textContent = `❌ ${error.message}`;
      showToast(`Gagal menguji ${provider}: ${error.message}`, 'error');
    } finally {
      window.clearInterval(progressTimer);
      button.disabled = false;
      button.textContent = oldText;
    }
  }

  if (resetBtn) {
    resetBtn.addEventListener('click', () => {
      const templateArea = document.getElementById('settingSeedTemplateTab') || document.getElementById('settingSeedTemplate');
      if (templateArea) {
        templateArea.value = DEFAULT_V41_TEMPLATE;
        showToast('Template Character Sheet V4.1 di-reset ke default!', 'info');
      }
    });
  }

  if (testBtn) {
    testBtn.addEventListener('click', async () => {
      const keyEl = document.getElementById('settingGeminiKeyTab') || document.getElementById('settingGeminiKey');
      const modelEl = document.getElementById('settingGeminiModelTab') || document.getElementById('settingGeminiModel');
      await testProviderKeys('gemini', keyEl, modelEl, testBtn, document.getElementById('testGeminiKeyResult'));
    });
  }

  if (openAITestBtn) openAITestBtn.addEventListener('click', () => testProviderKeys(
    'openai', document.getElementById('settingOpenAIKeyTab'), document.getElementById('settingOpenAIModelTab'),
    openAITestBtn, document.getElementById('testOpenAIKeyResult')));
  if (deepSeekTestBtn) deepSeekTestBtn.addEventListener('click', () => testProviderKeys(
    'deepseek', document.getElementById('settingDeepSeekKeyTab'), document.getElementById('settingDeepSeekModelTab'),
    deepSeekTestBtn, document.getElementById('testDeepSeekKeyResult')));
  if (xaiTestBtn) xaiTestBtn.addEventListener('click', () => testProviderKeys(
    'xai', document.getElementById('settingXAIKeyTab'), document.getElementById('settingXAIModelTab'),
    xaiTestBtn, document.getElementById('testXAIKeyResult'), document.getElementById('settingXAIBaseUrlTab')));
  if (nineRouterTestBtn) nineRouterTestBtn.addEventListener('click', () => testProviderKeys(
    '9router', document.getElementById('setting9RouterKeyTab'), document.getElementById('setting9RouterModelTab'),
    nineRouterTestBtn, document.getElementById('test9RouterKeyResult'), document.getElementById('setting9RouterBaseUrlTab')));

  if (saveBtn) {
    saveBtn.addEventListener('click', async () => {
      const keyEl = document.getElementById('settingGeminiKeyTab') || document.getElementById('settingGeminiKey');
      const modelEl = document.getElementById('settingGeminiModelTab') || document.getElementById('settingGeminiModel');
      const projEl = document.getElementById('settingFlowProjectIdTab') || document.getElementById('settingFlowProjectId');
      const enableEl = document.getElementById('settingEnableSeedImageTab') || document.getElementById('settingEnableSeedImage');
      const templateEl = document.getElementById('settingSeedTemplateTab') || document.getElementById('settingSeedTemplate');
      const defaultProviderEl = document.querySelector('input[name="defaultTextProvider"]:checked');
      const openAIKeyEl = document.getElementById('settingOpenAIKeyTab');
      const deepSeekKeyEl = document.getElementById('settingDeepSeekKeyTab');
      const openAIModelEl = document.getElementById('settingOpenAIModelTab');
      const deepSeekModelEl = document.getElementById('settingDeepSeekModelTab');
      const xaiKeyEl = document.getElementById('settingXAIKeyTab');
      const xaiModelEl = document.getElementById('settingXAIModelTab');
      const xaiBaseUrlEl = document.getElementById('settingXAIBaseUrlTab');
      const nineRouterKeyEl = document.getElementById('setting9RouterKeyTab');
      const nineRouterModelEl = document.getElementById('setting9RouterModelTab');
      const nineRouterBaseUrlEl = document.getElementById('setting9RouterBaseUrlTab');

      const rawKeys = keyEl ? keyEl.value.trim() : '';
      const model = modelEl ? modelEl.value : 'gemini-2.5-flash';
      const projId = projEl ? projEl.value.trim() : '';
      const enableSeed = enableEl ? enableEl.checked : true;
      const seedTemplate = templateEl ? templateEl.value : DEFAULT_V41_TEMPLATE;

      const keyArray = rawKeys.split(/[\n,]+/).map(k => k.trim()).filter(Boolean);

      try {
        const res = await fetch('/api/settings', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            gemini_api_keys: keyArray,
            gemini_model: model,
            openai_api_keys: (openAIKeyEl?.value || '').split(/[\n,]+/).map(k => k.trim()).filter(Boolean),
            openai_model: openAIModelEl?.value.trim() || 'gpt-4.1-mini',
            deepseek_api_keys: (deepSeekKeyEl?.value || '').split(/[\n,]+/).map(k => k.trim()).filter(Boolean),
            deepseek_model: deepSeekModelEl?.value.trim() || 'deepseek-chat',
            xai_api_keys: (xaiKeyEl?.value || '').split(/[\n,]+/).map(k => k.trim()).filter(Boolean),
            xai_model: xaiModelEl?.value.trim() || 'grok-4.3',
            xai_base_url: xaiBaseUrlEl?.value.trim() || 'https://api.x.ai/v1',
            nine_router_api_keys: (nineRouterKeyEl?.value || '').split(/[\n,]+/).map(k => k.trim()).filter(Boolean),
            nine_router_model: nineRouterModelEl?.value.trim() || 'premium-coding',
            nine_router_base_url: nineRouterBaseUrlEl?.value.trim() || 'http://127.0.0.1:20128/v1',
            default_text_provider: defaultProviderEl?.value || 'gemini',
            default_flow_project_id: projId,
            enable_character_seed_image: enableSeed,
            character_seed_template: seedTemplate
          })
        });

        const data = await res.json();
        if (!res.ok || data.detail) throw new Error(data.detail || 'Gagal menyimpan pengaturan');
        showToast('Pengaturan studio berhasil disimpan ke server!', 'success');
      } catch (err) {
        showToast('Gagal menyimpan pengaturan: ' + err.message, 'error');
      }
    });
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const mvForm = document.getElementById('mvForm');
  if (mvForm) {
    mvForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      
      const audioFile = document.getElementById('mvAudioFile').files[0];
      const lyrics = document.getElementById('mvLyrics').value;
      const aspect = document.getElementById('mvAspectRatio').value;
      const charInfo = document.getElementById('mvCharacterInfo').value;
      const btn = document.getElementById('btnGenerateMV');
      
      if (!audioFile) {
        showToast('Pilih file audio lagu terlebih dahulu.', 'error');
        return;
      }
      
      btn.disabled = true;
      btn.innerHTML = '<span class="icon">⏳</span> Menganalisa Lagu & Generating MV Storyboard...';
      
      try {
        const actorCheckboxes = document.querySelectorAll('#actorSelectionList_mv input[type="checkbox"]:checked');
        const actorIds = Array.from(actorCheckboxes).map(cb => cb.value).join(',');
        
        const formData = new FormData();
        formData.append('actor_ids', actorIds);
        formData.append('audio_file', audioFile);
        formData.append('lyrics', lyrics);
        formData.append('aspect_ratio', aspect);
        formData.append('character_info', charInfo);
        const targetLangEl = document.getElementById('targetLanguageInput');
        if (targetLangEl) formData.append('target_lang', targetLangEl.value.trim());
        
        const res = await fetch('/api/storyboard/generate-mv', {
          method: 'POST',
          body: formData
        });
        
        const data = await res.json();
        if (!res.ok || !data.success) throw new Error(data.detail || 'Gagal generate MV storyboard');
        
        // Auto-save the generated MV storyboard to Scene Master so it is not lost
        if (data.storyboard) {
          saveStoryboardToHistory(data.storyboard);
          // Optionally set it as current so the Scene Master studio panel displays it
          if (typeof currentStoryboard !== 'undefined') currentStoryboard = data.storyboard;
        }
        
        showToast('Music Video Storyboard berhasil di-generate! Memulai proses render...', 'success');
        
        const executeRes = await fetch('/api/jobs/create', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({
            storyboard: data.storyboard,
            aspect_ratio: aspect,
            force_uniform_duration: true,
            render_scene_limit: (() => {
              const value = parseInt(document.getElementById('flowSceneSlotInput')?.value, 10);
              return Number.isFinite(value) && value > 0 ? value : null;
            })()
          })
        });
        
        const execData = await executeRes.json();
        if(execData.success) {
            showToast('Proses render Music Video dimulai!', 'success');
            document.querySelector('[data-tab="tab-execution"]').click();
            
            startJobPolling(execData.job_id);
        } else {
            throw new Error(execData.detail || 'Gagal memulai job');
        }
      } catch (err) {
        showToast(err.message, 'error');
      } finally {
        btn.disabled = false;
        btn.innerHTML = '<span class="icon">✨</span> Generate MV Storyboard';
      }
    });
  }
  
  // Actor Registry Logic
  const MAX_ACTOR_REFERENCE_IMAGES = 4;
  let selectedActorReferenceFiles = [];
  let actorPreviewUrls = [];

  const actorImagesInput = document.getElementById('actorImages');
  const actorImagePreview = document.getElementById('actorImagePreview');
  const actorImageCount = document.getElementById('actorImageCount');

  const renderActorImagePreview = () => {
      actorPreviewUrls.forEach(url => URL.revokeObjectURL(url));
      actorPreviewUrls = [];
      if (actorImageCount) actorImageCount.textContent = `${selectedActorReferenceFiles.length}/${MAX_ACTOR_REFERENCE_IMAGES}`;
      if (!actorImagePreview) return;
      actorImagePreview.innerHTML = selectedActorReferenceFiles.map((file, index) => {
          const url = URL.createObjectURL(file);
          actorPreviewUrls.push(url);
          return `<div class="actor-reference-preview-item">
              <img src="${url}" alt="Referensi ${index + 1}">
              ${index === 0 ? '<span class="actor-reference-primary">Utama</span>' : ''}
              <button type="button" class="actor-reference-remove" data-index="${index}" title="Hapus gambar">×</button>
          </div>`;
      }).join('');
  };

  if (actorImagesInput) {
      actorImagesInput.addEventListener('change', () => {
          const chosen = Array.from(actorImagesInput.files || []);
          if (chosen.length > MAX_ACTOR_REFERENCE_IMAGES) {
              showToast(`Maksimal ${MAX_ACTOR_REFERENCE_IMAGES} gambar untuk satu karakter.`, 'warning');
          }
          selectedActorReferenceFiles = chosen.slice(0, MAX_ACTOR_REFERENCE_IMAGES);
          renderActorImagePreview();
      });
  }
  if (actorImagePreview) {
      actorImagePreview.addEventListener('click', (event) => {
          const button = event.target.closest('.actor-reference-remove');
          if (!button) return;
          selectedActorReferenceFiles.splice(Number(button.dataset.index), 1);
          if (actorImagesInput) actorImagesInput.value = '';
          renderActorImagePreview();
      });
  }

  const fetchActors = async () => {
      try {
          const res = await fetch('/api/actors');
          const data = await res.json();
          if (data.success) {
              renderActors(data.actors);
              renderActorCheckboxes(data.actors);
          }
      } catch (err) {
          console.error("Gagal load aktor:", err);
      }
  };
  
  const renderActors = (actors) => {
      const grid = document.getElementById('actorsGrid');
      if (!grid) return;
      grid.innerHTML = '';
      
      if (actors.length === 0) {
          grid.innerHTML = '<div class="empty-state"><h4>Belum Ada Aktor</h4><p>Daftarkan wajah baru untuk menggunakannya di storyboard.</p></div>';
          return;
      }
      
      actors.forEach(actor => {
          const actorImages = (actor.images && actor.images.length)
              ? actor.images
              : (actor.image_url ? [{ url: actor.image_url, primary: true }] : []);
          const primaryImage = actorImages[0] ? actorImages[0].url : '';
          const secondaryImages = actorImages.slice(1, 4);
          const card = document.createElement('div');
          card.style = "background: rgba(0,0,0,0.2); border: 1px solid rgba(255,255,255,0.1); border-radius: 12px; overflow: hidden; display: flex; flex-direction: column;";
          card.innerHTML = `
            <img src="${primaryImage}" alt="${actor.name}" style="width: 100%; height: 200px; object-fit: cover;">
            ${secondaryImages.length ? `<div class="actor-card-reference-strip">${secondaryImages.map((image, index) =>
                `<img src="${image.url}" alt="Referensi ${index + 2} ${actor.name}">`).join('')}</div>` : ''}
            <div style="padding: 16px;">
                <h4 style="margin: 0 0 8px 0; color: #fff;">${actor.name}</h4>
                <span class="actor-reference-count">${actorImages.length} Referensi</span>
                <p style="margin: 0 0 12px 0; color: #aaa; font-size: 13px; min-height: 40px;">${actor.description}</p>
                <div style="display: flex; justify-content: space-between; align-items: center;">
                    <span style="background: rgba(56, 189, 248, 0.2); color: #38bdf8; padding: 4px 8px; border-radius: 6px; font-size: 12px; font-family: monospace;">Seed: ${actor.seed}</span>
                    <button class="btn-secondary" onclick="deleteActor('${actor.id}')" style="padding: 4px 10px; font-size: 12px; border-color: #ef4444; color: #ef4444;">Hapus</button>
                </div>
            </div>
          `;
          grid.appendChild(card);
      });
  };
  
  const renderActorCheckboxes = (actors) => {
      const containerSB = document.getElementById('actorSelectionList_storyboard');
      const containerMV = document.getElementById('actorSelectionList_mv');
      
      let html = '';
      if (actors.length === 0) {
          html = '<span style="color: #aaa; font-size: 13px;">Belum ada aktor tersimpan.</span>';
      } else {
          actors.forEach(actor => {
              html += `
              <label style="display: flex; align-items: center; gap: 6px; background: rgba(0,0,0,0.3); padding: 6px 12px; border-radius: 20px; cursor: pointer;">
                  <input type="checkbox" value="${actor.id}" style="accent-color: #38bdf8;">
                  <img src="${(actor.images && actor.images[0] ? actor.images[0].url : actor.image_url)}" style="width: 20px; height: 20px; border-radius: 50%; object-fit: cover;">
                  <span style="color: #fff; font-size: 13px;">${actor.name}</span>
              </label>
              `;
          });
      }
      
      if (containerSB) containerSB.innerHTML = html;
      if (containerMV) containerMV.innerHTML = html;
  };
  
  window.deleteActor = async (actorId) => {
      if(!confirm("Yakin ingin menghapus aktor ini?")) return;
      try {
          const res = await fetch('/api/actors/' + actorId, { method: 'DELETE' });
          if(res.ok) {
              showToast("Aktor berhasil dihapus!", "success");
              fetchActors();
          }
      } catch (err) {
          showToast("Gagal menghapus aktor", "error");
      }
  };
  
  const addActorForm = document.getElementById('addActorForm');
  if (addActorForm) {
      addActorForm.addEventListener('submit', async (e) => {
          e.preventDefault();
          const name = document.getElementById('actorName').value;
          const desc = document.getElementById('actorDesc').value;
          const seed = document.getElementById('actorSeed').value;
          if(!selectedActorReferenceFiles.length) return showToast("Minimal satu gambar referensi karakter wajib diunggah", "error");
          
          const formData = new FormData();
          formData.append('name', name);
          formData.append('description', desc);
          selectedActorReferenceFiles.forEach(image => formData.append('image_files', image));
          if (seed) formData.append('seed', parseInt(seed));
          
          try {
              const res = await fetch('/api/actors', { method: 'POST', body: formData });
              if (res.ok) {
                  showToast("Aktor berhasil didaftarkan!", "success");
                  document.getElementById('addActorModal').classList.remove('active');
                  addActorForm.reset();
                  selectedActorReferenceFiles = [];
                  renderActorImagePreview();
                  fetchActors();
              }
          } catch(err) {
              showToast("Gagal mendaftarkan aktor", "error");
          }
      });
  }
  
  // Audience & Content Universe
  document.getElementById('generateContentUniverse')?.addEventListener('click', () => {
      const value = id => document.getElementById(id)?.value?.trim?.() || '';
      const ideas = buildContentUniverse({ audience: value('universeAudience'), emotion: value('universeEmotion'), goal: value('universeGoal'), genre: value('universeGenre'), format: value('universeFormat'), complexity: value('universeComplexity'), context: value('universeContext'), country: value('universeCountry'), language: value('universeLanguage') });
      selectedUniverseIdea = null;
      const send = document.getElementById('sendUniverseToStoryboard'); if (send) send.disabled = true;
      const results = document.getElementById('universeResults');
      if (results) results.innerHTML = ideas.map((idea, index) => `<button type="button" class="universe-card" data-idea-index="${index}"><span>${String(index + 1).padStart(2, '0')}</span><h4>${escapeHtml(idea.title)}</h4><p>${escapeHtml(idea.premise)}</p><small><b>Hook:</b> ${escapeHtml(idea.hook)}</small><small><b>Arc:</b> ${escapeHtml(idea.arc)}</small><em>${escapeHtml(idea.audience)} · ${escapeHtml(idea.genre)} · ${escapeHtml(idea.format)}</em></button>`).join('');
      results?.querySelectorAll('.universe-card').forEach(card => card.addEventListener('click', () => {
          results.querySelectorAll('.universe-card').forEach(node => node.classList.remove('selected'));
          card.classList.add('selected'); selectedUniverseIdea = ideas[Number(card.dataset.ideaIndex)];
          if (send) send.disabled = false;
          const status = document.getElementById('universeStatus'); if (status) status.textContent = `Terpilih: ${selectedUniverseIdea.title}`;
      }));
      const status = document.getElementById('universeStatus'); if (status) status.textContent = '10 ide siap · pilih satu untuk diteruskan.';
  });

  document.getElementById('sendUniverseToStoryboard')?.addEventListener('click', () => {
      if (!selectedUniverseIdea) return showToast('Pilih satu ide terlebih dahulu.', 'warning');
      document.querySelector('.nav-item[data-tab="tab-storyboard"]')?.click();
      const idea = selectedUniverseIdea;
      const premise = document.getElementById('premiseInput'); if (premise) premise.value = `${idea.hook}\n\n${idea.premise}\n\nALUR: ${idea.arc}`;
      const audience = document.getElementById('briefAudienceInput'); if (audience) audience.value = idea.audience;
      const ageTarget = document.getElementById('storyAgeTarget'); if (ageTarget && CONTENT_UNIVERSE_PROFILES[document.getElementById('universeAudience')?.value]) { ageTarget.value = document.getElementById('universeAudience').value; ageTarget.dispatchEvent(new Event('change')); }
      const country = document.getElementById('targetCountryInput'); if (country) country.value = idea.country;
      const language = document.getElementById('targetLanguageInput'); if (language) language.value = idea.language;
      const execution = document.getElementById('briefExecutionInput'); if (execution) execution.value = `CONTENT UNIVERSE DIRECTION\nAudience: ${idea.audience}. Genre: ${idea.genre}. Format: ${idea.format}. Complexity: ${idea.complexity}.\nVoice/dialogue: ${idea.voice}.\nCamera/audio: ${idea.direction}.\nSafety & dignity: ${idea.guard}.\nKeep the hook, conflict, actions, and payoff causally coherent. Do not stereotype the age group.`;
      const children = document.getElementById('chkChildrenMode'); if (children) { children.checked = idea.children; children.dispatchEvent(new Event('change')); }
      document.getElementById('creativeBriefPanel')?.setAttribute('open', '');
      showToast('Ide dan arahan audiens dikirim ke AI Storyboard.', 'success');
  });

  // AI YouTube Blueprint Generator & Randomizer
  const TRENDING_YT_TOPICS = [
      'The Dark Psychology Behind Mega Corporations and Consumer Manipulation',
      'The 1983 Soviet Submarine Mystery That Almost Triggered World War 3',
      'Ancient Megastructures That Modern Engineering Still Cannot Explain',
      'How Quantum Computing Will Break All Modern Encryption by 2028',
      'Victorian Midnight Library Thunderstorm Ambience with Crackling Fireplace',
      'Cyberpunk Rainy Ramen Shop in Neo Tokyo with Subtle Lo-Fi Jazz',
      '3 FBI Interrogation Tactics to Detect Lies in 30 Seconds',
      'The Million-Dollar Diamond Heist with Zero Alarms Triggered',
      'How Medieval Doctors Survived the Black Plague Against All Odds',
      'Deep Oceanic Trench Anomalies Caught on Deep-Sea Submersibles',
      'The Philosophy of Solitude: Why High Achievers Walk Alone',
      'How Neuralink Brain Interfaces Will Transform Human Memory'
  ];

  document.getElementById('btnRandomizeYtAiTopic')?.addEventListener('click', () => {
      const topicInput = document.getElementById('ytAiTopicInput');
      if (topicInput) {
          const randomTopic = TRENDING_YT_TOPICS[Math.floor(Math.random() * TRENDING_YT_TOPICS.length)];
          topicInput.value = randomTopic;
          showToast('🎲 Topik tren dipilih: ' + randomTopic, 'info');
      }
  });

  document.getElementById('btnGenerateYtAiBlueprint')?.addEventListener('click', async () => {
      const topicInput = document.getElementById('ytAiTopicInput');
      const topic = topicInput ? topicInput.value.trim() : '';
      const format = document.getElementById('ytFormat')?.value || 'cinematic_storytelling';
      const market = document.getElementById('ytMarket')?.value || 'United States';
      const language = document.getElementById('ytLanguage')?.value || 'Native US English';

      const btn = document.getElementById('btnGenerateYtAiBlueprint');
      const statusEl = document.getElementById('ytAiGeneratingStatus');

      if (btn) btn.disabled = true;
      if (statusEl) statusEl.style.display = 'flex';
      showCuteAiLoading('✨ AI Meracik YouTube Blueprint...', 'Sedang merancang positioning, niche, audience, hook 3s, dan 7 modul produksi...');

      try {
          const res = await fetch('/api/storyboard/suggest_youtube_blueprint', {
              method: 'POST',
              headers: { 'Content-Type': 'application/json' },
              body: JSON.stringify({ topic, format, market, language })
          });
          const data = await res.json();
          if (!res.ok || !data.success || !data.blueprint) {
              throw new Error(data.detail || 'Gagal meracik blueprint AI');
          }
          const bp = data.blueprint;

          const setVal = (id, val) => {
              const el = document.getElementById(id);
              if (el && val !== undefined && val !== null) {
                  el.value = val;
                  el.dispatchEvent(new Event('input'));
                  el.dispatchEvent(new Event('change'));
              }
          };

          if (bp.format) setVal('ytFormat', bp.format);
          if (bp.market) setVal('ytMarket', bp.market);
          if (bp.language) setVal('ytLanguage', bp.language);
          setVal('ytMicroNiche', bp.micro_niche);
          setVal('ytAudience', bp.core_audience);
          setVal('ytPromise', bp.channel_promise);
          setVal('ytDemand', bp.demand_evidence);
          setVal('ytGap', bp.competitor_gap);
          setVal('ytAngle', bp.original_angle);
          setVal('ytHook', bp.hook_cold_open);
          setVal('ytOpenLoop', bp.macro_open_loop);
          setVal('ytPayoff', bp.payoff_next_view);
          if (bp.brand_architecture) setVal('ytBrand', bp.brand_architecture);
          setVal('ytColors', bp.colors);
          setVal('ytFont', bp.font);
          setVal('ytMainKeyword', bp.main_keyword);
          setVal('ytRelevantKeywords', bp.relevant_keywords);
          setVal('ytLongTail', bp.long_tail_intent);
          setVal('ytSources', bp.sources_and_licensing);

          // 7 modules
          setVal('ytEditorialThesis', bp.editorial_thesis);
          setVal('ytContentMoat', bp.content_moat);
          setVal('ytFleetGovernance', bp.fleet_governance);
          setVal('ytProductionCost', bp.production_cost);
          if (bp.ai_disclosure) setVal('ytAiDisclosure', bp.ai_disclosure);
          setVal('ytHumanContribution', bp.human_contribution);
          setVal('ytLocalizationQa', bp.localization_qa);
          setVal('ytAudioQa', bp.audio_qa);
          setVal('ytContinuityLedger', bp.continuity_ledger);
          setVal('ytLoopLedger', bp.loop_ledger);
          setVal('ytRiskRegister', bp.risk_register);

          // Auto-check quality gates
          ['ytGateEvidence', 'ytGateOriginality', 'ytGateRights', 'ytGatePromise', 'ytGateTechnical'].forEach(id => {
              const el = document.getElementById(id);
              if (el) el.checked = true;
          });

          // Build final blueprint text
          buildYoutubeBlueprint();
          showToast('✨ Blueprint YouTube berhasil diracik dan diisi otomatis oleh AI!', 'success');
      } catch (err) {
          console.error(err);
          showToast('Gagal meracik blueprint AI: ' + err.message, 'error');
      } finally {
          hideCuteAiLoading();
          if (btn) btn.disabled = false;
          if (statusEl) statusEl.style.display = 'none';
      }
  });

  // UGC Affiliate Asset Lab
  const buildYoutubeBlueprint = () => {
      const data = getYoutubeBlueprintInput();
      const required = [['microNiche', 'micro-niche'], ['audience', 'core audience'], ['promise', 'janji channel'], ['demand', 'demand evidence'], ['angle', 'angle original'], ['hook', 'hook'], ['sources', 'sumber/lisensi']];
      const missing = required.filter(([key]) => !data[key]).map(([, label]) => label);
      const status = document.getElementById('ytBlueprintStatus');
      if (missing.length) {
          if (status) { status.textContent = `Belum siap: ${missing.join(', ')}.`; status.className = 'warn'; }
          showToast(`Lengkapi ${missing.join(', ')}.`, 'warning');
          return '';
      }
      const formatPlans = {
          cinematic_storytelling: 'Cold open → mystery → evidence-led micro-chapters → nested open loops → verified payoff → next-view bridge. Vary pacing by meaning; use AI visuals, licensed real B-roll, and attributable evidence only when available—not a forced ratio.',
          ambience: 'Design one coherent thematic room for a stated use case. Continuous room tone, seamless ambience crossfades, restrained licensed music, sparse contextual micro-SFX, slow non-repetitive environmental movement; no medical promises.',
          shorts: 'Immediate first-frame event and promise, one idea, readable progression, proof/payoff, seamless ending or relevant long-form bridge. No unrelated Shorts used to pollute another audience.',
      };
      const blueprint = [
        'YOUTUBE EVIDENCE-FIRST PRODUCTION BLUEPRINT',
        `POSITIONING: ${data.microNiche} for ${data.audience} in ${data.market}, delivered in ${data.language}. Channel promise: ${data.promise}.`,
        `VALIDATION TRIANGLE: Demand evidence — ${data.demand}. Competitor information gap — ${data.gap || 'not supplied; research before production'}. Original angle/value — ${data.angle}.`,
        `FORMAT SYSTEM: ${formatPlans[data.format] || formatPlans.cinematic_storytelling}`,
        `RETENTION CONTRACT: Cold open — ${data.hook}. Macro loop — ${data.openLoop || 'must be defined before scripting'}. Payoff/next view — ${data.payoff || 'resolve every promise before a relevant next-view bridge'}. No deceptive clickbait or artificial dead-air removal that makes speech unnatural.`,
        `BRAND DNA: ${data.brand}; primary colours ${data.colors || 'define two accessible colours'}; signature font ${data.font || 'define a licensed readable font'}. Keep identity stable; thumbnail and title complement rather than repeat each other.`,
        `SEMANTIC DISCOVERY: Main keyword “${data.mainKeyword || 'research required'}”; related context “${data.relevantKeywords || '-'}”; long-tail intent “${data.longTail || '-'}”. Use naturally in title/lead/script only when factually relevant; no keyword stuffing.`,
        `PRODUCTION QC: original script and commentary; source ledger; asset licences; character/object continuity; color/exposure match; natural VO; ambience + selective foley + ducked music; artifact review at 0.5×; first 30 seconds reviewed against title/thumbnail promise.`,
        `SOURCES & RIGHTS: ${data.sources}. Never fabricate citations, claims, testimonials, footage ownership, fair-use certainty, or monetization outcomes. Flag altered/synthetic media when platform rules require it.`,
        `EDITORIAL ORIGINALITY: Thesis — ${data.editorialThesis || 'define before scripting'}. Human contribution — ${data.humanContribution || 'document research, analysis, commentary, and editorial decisions'}. Content moat — ${data.contentMoat || 'define a defensible repeatable advantage'}.`,
        `FLEET GOVERNANCE: ${data.fleetGovernance || 'assign owner, editor, fact-checker, rights reviewer, and publisher; enable 2FA and backups'}. Estimated production cost/video: ${data.productionCost || 'not supplied'}. Scale capacity and quality, never identity/account evasion.`,
        `MARKET & AUDIO QA: Localization — ${data.localizationQa || 'native idiom, pronunciation, units, currency, and cultural review required'}. Soundscape — ${data.audioQa || 'verify audio licence, ambience, selective foley, ducking, loudness, true peak, and seamless loops'}.`,
        `CONTINUITY & LOOP LEDGERS: ${data.continuityLedger || 'record character, time, location, props, wardrobe, and lighting'} | ${data.loopLedger || 'record every question opened and its evidence-backed payoff'}. Use semantic pacing—not a forced cut interval.`,
        `IRON SHIELD: ${data.riskRegister || 'classify copyright, privacy/likeness, claims, invalid traffic, and policy risks before publish'}. Preserve notices and evidence; choose edit, dispute, appeal, or takedown by issue type—never promise recovery odds.`,
        `AI DISCLOSURE REVIEW: ${data.aiDisclosure || 'review_required'}. Disclosure does not replace consent or likeness rights.`,
        `QUALITY GATES: ${data.gates.length}/5 passed — ${data.gates.join(', ') || 'none confirmed'}. A checked gate is a human attestation, not automatic proof.`,
        'EXPERIMENT: Prepare title/thumbnail hypotheses before publish. Change one variable per test, log time window and traffic source, then diagnose from actual CTR and retention—not universal thresholds.',
      ].join('\n\n');
      document.getElementById('ytBlueprintOutput').value = blueprint;
      if (status) { status.textContent = data.gates.length === 5 ? 'Siap · semua 5 quality gates dikonfirmasi.' : `Blueprint dibuat · ${data.gates.length}/5 gate dikonfirmasi.`; status.className = data.gates.length === 5 ? 'ready' : 'warn'; }
      return blueprint;
  };

  document.getElementById('buildYoutubeBlueprint')?.addEventListener('click', () => {
      if (buildYoutubeBlueprint()) showToast('YouTube Production Blueprint berhasil dibangun.', 'success');
  });

  document.getElementById('sendYoutubeToStoryboard')?.addEventListener('click', () => {
      const blueprint = document.getElementById('ytBlueprintOutput')?.value.trim() || buildYoutubeBlueprint();
      if (!blueprint) return;
      const data = getYoutubeBlueprintInput();
      document.querySelector('.nav-item[data-tab="tab-storyboard"]')?.click();
      const premise = document.getElementById('premiseInput');
      if (premise) premise.value = `${data.hook}\n\n${data.angle}\n\n${data.openLoop}\n\n${data.payoff}`.trim();
      const targetCountry = document.getElementById('targetCountryInput'); if (targetCountry) targetCountry.value = data.market;
      const targetLanguage = document.getElementById('targetLanguageInput'); if (targetLanguage) targetLanguage.value = data.language;
      const execution = document.getElementById('briefExecutionInput'); if (execution) execution.value = blueprint;
      document.getElementById('creativeBriefPanel')?.setAttribute('open', '');
      showToast('Blueprint dikirim ke Storyboard. Atur jumlah scene dan durasi sebelum generate.', 'success');
  });

  document.getElementById('diagnoseYoutubeData')?.addEventListener('click', () => {
      const optionalNumber = id => { const raw = document.getElementById(id)?.value; return raw === '' ? null : Math.max(0, Math.min(100, Number(raw))); };
      const nonNegative = id => { const raw = document.getElementById(id)?.value; return raw === '' ? null : Math.max(0, Number(raw)); };
      const notes = diagnoseYoutubeMetrics({ ctr: optionalNumber('ytCtr'), hookRetention: optionalNumber('ytHookRetention'), avd: optionalNumber('ytAvd'), endRetention: optionalNumber('ytEndRetention'), shape: document.getElementById('ytRetentionShape')?.value || 'unknown', trafficSource: document.getElementById('ytTrafficSource')?.value || 'unknown', newViewers: nonNegative('ytNewViewers'), returningViewers: nonNegative('ytReturningViewers'), revenue: nonNegative('ytRevenue'), hours: nonNegative('ytHours'), cost: nonNegative('ytProductionCost') });
      document.getElementById('ytAnalyticsResult').innerHTML = `<ol>${notes.map(note => `<li>${escapeHtml(note)}</li>`).join('')}</ol>`;
  });

  const assetPrompt = document.getElementById('assetMasterPrompt');
  const characterAssetInput = document.getElementById('ugcCharacterAsset');
  const productAssetInput = document.getElementById('ugcProductAsset');
  const ugcBackground = document.getElementById('ugcBackground');
  ugcBackground?.addEventListener('change', () => {
      const custom = document.getElementById('ugcCustomBackground');
      if (custom) custom.disabled = ugcBackground.value !== 'custom';
  });
  const ugcLightingSelect = document.getElementById('ugcLighting');
  ugcLightingSelect?.addEventListener('change', () => {
      const custom = document.getElementById('ugcCustomLighting');
      if (custom) custom.disabled = ugcLightingSelect.value !== 'custom';
  });
  const ugcProductionMode = document.getElementById('ugcProductionMode');
  ugcProductionMode?.addEventListener('change', () => {
      if (ugcProductionMode.value !== 'raw_amateur') return;
      const tone = document.getElementById('ugcTone');
      if (tone) tone.value = 'Raw, candid, socially alive, imperfect amateur smartphone footage';
      const lighting = document.getElementById('ugcLighting');
      if (lighting && lighting.value === 'auto') lighting.value = 'natural_window';
  });

  document.getElementById('buildUgcFormula')?.addEventListener('click', () => {
      const who = document.getElementById('ugcFormulaWho')?.value.trim();
      const action = document.getElementById('ugcFormulaAction')?.value.trim();
      const where = document.getElementById('ugcFormulaWhere')?.value.trim();
      const need = document.getElementById('ugcFormulaNeed')?.value.trim();
      const hook = document.getElementById('ugcFormulaHook')?.value.trim();
      const emotionSelect = document.getElementById('ugcFormulaEmotion');
      const emotion = emotionSelect?.selectedOptions?.[0]?.textContent || 'Relate';
      if (!who || !action || !where) return showToast('Isi SIAPA, NGAPAIN, dan DI MANA terlebih dahulu.', 'warning');
      const idea = `${who} ${action} di ${where}${need ? `; produk dibutuhkan ketika ${need}` : ''}.`;
      const completeHook = hook || `Masalah kecil ini pasti pernah kamu alami.`;
      const formulaPrompt = `Read and follow all attached references carefully before generating.\n${idea}\nBuka dalam 3 detik dengan hook: "${completeHook}" Fokus pada satu emosi utama: ${emotion}. Buat satu pesan yang mudah dicerna, tunjukkan masalah melalui aksi nyata, hadirkan produk tepat saat dibutuhkan, buktikan hanya manfaat yang terlihat atau diizinkan, lalu akhiri dengan CTA natural. Jangan memakai pembuka formal, klaim berlebihan, atau iklan tempelan.`;
      const output = document.getElementById('ugcFormulaPrompt');
      if (output) output.value = formulaPrompt;
      const logline = document.getElementById('ugcLogline');
      if (logline) logline.value = `${idea} Hook: ${completeHook} Emosi: ${emotion}.`;
      showToast('Konsep SIAPA + NGAPAIN + DI MANA sudah disusun.', 'success');
  });

  document.getElementById('buildConversionBrief')?.addEventListener('click', () => {
      const brief = getUgcConversionBrief();
      const audit = auditUgcConversionBrief(brief);
      const status = document.getElementById('ugcConversionStatus');
      if (!audit.ready) {
          if (status) { status.textContent = `Belum siap: isi ${audit.missing.join(', ')}.`; status.className = 'warn'; }
          return showToast(`Brief belum lengkap: ${audit.missing.join(', ')}.`, 'warning');
      }
      const awarenessLabels = { unaware: 'edukasi/cerita', problem_aware: 'solusi & harapan', solution_aware: 'diferensiasi terbukti', product_aware: 'proof, offer & CTA' };
      const output = [
        `OBJECTIVE: Gerakkan ${brief.audience} untuk ${brief.objective}.${brief.why_now ? ` Alasan sekarang: ${brief.why_now}.` : ' Tanpa urgensi buatan.'}`,
        `AWARENESS: ${brief.awareness_level} — ${awarenessLabels[brief.awareness_level] || ''}.`,
        `HOOK 0–3s (${brief.hook_type}): “${brief.hook}”`,
        `PAS: Problem — ${brief.problem} | Agitate — ${brief.agitate || 'tunjukkan dampak nyata secara wajar'} | Solution — ${brief.solution}`,
        `PROOF: ${brief.proof}. CTA: ${brief.cta}.`,
        `RETENTION: tanpa intro; perubahan visual bermakna tiap 2–3 detik; open loop wajib dituntaskan sebelum CTA.`,
        `TEST PLAN: buat ${brief.variant_count} versi dan ubah hanya ${brief.test_variable}; produk, isi utama, offer, durasi, dan variabel lain tetap.`,
        `GUARDRAIL: jangan mengarang hasil, testimoni, harga, diskon, stok, bonus, klaim kesehatan, before-after, atau urgensi.`,
      ].join('\n');
      document.getElementById('ugcConversionOutput').value = output;
      if (status) { status.textContent = 'Siap dipakai · struktur dan proof lengkap.'; status.className = 'ready'; }
      const formulaHook = document.getElementById('ugcFormulaHook');
      if (formulaHook && !formulaHook.value.trim()) formulaHook.value = brief.hook;
      showToast('Brief konversi siap. Sistem akan mengunci satu variabel per variasi.', 'success');
  });

  document.getElementById('calculateUgcMetrics')?.addEventListener('click', () => {
      const number = id => Math.max(0, Number(document.getElementById(id)?.value || 0));
      const metrics = calculateUgcFunnelMetrics({
          impressions: number('metricImpressions'), threeSecond: number('metric3s'),
          completed: number('metricCompleted'), clicks: number('metricClicks'),
          purchases: number('metricPurchases'), spend: number('metricSpend'), revenue: number('metricRevenue'),
      });
      const show = (value, suffix = '%') => value == null ? '—' : `${value}${suffix}`;
      document.getElementById('ugcMetricResults').innerHTML = [
          ['Hook Rate', show(metrics.hookRate)], ['Hold Rate', show(metrics.holdRate)],
          ['CTR', show(metrics.ctr)], ['CVR', show(metrics.cvr)], ['ROAS', show(metrics.roas, '×')],
      ].map(([label, value]) => `<div><span>${label}</span><strong>${value}</strong></div>`).join('');
  });

  async function auditAsset(file, output, type) {
      if (!file || !output) return null;
      const bitmap = await createImageBitmap(file);
      const canvas = document.createElement('canvas');
      const scale = Math.min(1, 320 / Math.max(bitmap.width, bitmap.height));
      canvas.width = Math.max(1, Math.round(bitmap.width * scale));
      canvas.height = Math.max(1, Math.round(bitmap.height * scale));
      const context = canvas.getContext('2d', { willReadFrequently: true });
      context.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
      const pixels = context.getImageData(0, 0, canvas.width, canvas.height).data;
      let brightness = 0, edge = 0, samples = 0;
      const gray = i => (pixels[i] * .299) + (pixels[i + 1] * .587) + (pixels[i + 2] * .114);
      for (let y = 1; y < canvas.height; y += 2) {
          for (let x = 1; x < canvas.width; x += 2) {
              const i = (y * canvas.width + x) * 4;
              brightness += gray(i);
              edge += Math.abs(gray(i) - gray(i - 4)) + Math.abs(gray(i) - gray(i - canvas.width * 4));
              samples++;
          }
      }
      brightness /= Math.max(1, samples);
      edge /= Math.max(1, samples * 2);
      const issues = [];
      if (bitmap.width * bitmap.height < 1000000 || Math.min(bitmap.width, bitmap.height) < 720) issues.push('resolusi rendah');
      if (brightness < 48) issues.push('terlalu gelap');
      if (brightness > 218) issues.push('terlalu terang');
      if (edge < 7) issues.push('terindikasi blur/detail rendah');
      if (file.size < 100000) issues.push('ukuran file sangat kecil');
      const status = issues.length ? 'Perlu diperbaiki' : 'Layak untuk produksi';
      output.className = `asset-audit ${issues.length ? 'warn' : 'good'}`;
      output.innerHTML = `<strong>${issues.length ? '⚠️' : '✅'} ${status}</strong><br>${bitmap.width}×${bitmap.height}px · ${(file.size / 1048576).toFixed(2)} MB · exposure ${Math.round(brightness)} · detail ${edge.toFixed(1)}${issues.length ? `<br>Masalah: ${issues.join(', ')}.` : ''}<br>${type === 'product' ? 'Pastikan logo/label terbaca dan kemasan tidak terpotong.' : 'Pastikan wajah frontal terlihat, natural, dan tidak tertutup.'}`;
      bitmap.close();
      return { issues, width: bitmap.width, height: bitmap.height };
  }

  characterAssetInput?.addEventListener('change', () => auditAsset(characterAssetInput.files?.[0], document.getElementById('ugcCharacterAudit'), 'character'));
  productAssetInput?.addEventListener('change', () => auditAsset(productAssetInput.files?.[0], document.getElementById('ugcProductAudit'), 'product'));

  document.getElementById('generateCharacterSheetPrompt')?.addEventListener('click', () => {
      const identity = document.getElementById('ugcCharacterIdentity')?.value.trim() || 'preserve every visible identity feature from the reference';
      const outfit = document.getElementById('ugcOutfitRequest')?.value.trim();
      assetPrompt.value = outfit
        ? `Edit the supplied 3x3 character master contact sheet. Replace clothing only with: ${outfit}. Preserve the exact identity in all nine panels: ${identity}. Lock the grid, panel order, camera angles, crops, pose, expression, head position, lighting, neutral studio background, body proportions and image quality. Preserve realistic garment fit, fabric weight and folds. This is an outfit-only edit, not a new person or photoshoot. No face reconstruction, identity drift, re-posing, beautification, plastic skin, angle change, framing change or repeated panels.`
        : `Create one vertical 9:16 ultra-photorealistic 3x3 character master contact sheet from the supplied reference. The same identity must appear in every panel: ${identity}. Use nine distinct views: front portrait, three-quarter portrait, left profile, low angle, gentle top-down, waist-up, tight facial close-up, over-shoulder, and full body. Keep identical bone structure, eyes, nose, lips, skin tone, hairline, hairstyle and body proportions. Natural skin micro-texture, individual hair strands, realistic fabric, neutral grey studio background, controlled studio lighting and consistent lens language. No beautification, face change, stylization, plastic skin, blur, identity drift, repeated angle, extra person, text or watermark.`;
      showToast('Prompt Character Master siap digunakan.', 'success');
  });

  document.getElementById('generateProductSheetPrompt')?.addEventListener('click', () => {
      const name = document.getElementById('ugcProductName')?.value.trim() || 'the supplied product';
      const identity = document.getElementById('ugcProductIdentity')?.value.trim() || 'derive exact geometry, colors, materials, cap, label and scale only from the reference';
      assetPrompt.value = `Create a clean 3x3 product master contact sheet for ${name} from the supplied product photo. Product identity lock: ${identity}. Show nine useful views: front hero, left three-quarter, right three-quarter, left side, right side, back, top detail, label/package detail and scale-context view. Preserve exact package geometry, proportions, color values, material, cap, logo placement and label layout in every panel. Use even studio lighting, neutral background, sharp edges, realistic reflections and consistent scale. Do not redesign, simplify, invent claims, move the logo, alter label layout, change color, crop the package, hide it behind a hand, duplicate an angle, add props, text or watermark.`;
      showToast('Prompt Product Master siap digunakan.', 'success');
  });

  document.getElementById('copyAssetPrompt')?.addEventListener('click', async () => {
      if (!assetPrompt?.value.trim()) return showToast('Buat prompt asset terlebih dahulu.', 'warning');
      await navigator.clipboard.writeText(assetPrompt.value);
      showToast('Prompt asset berhasil tercopy.', 'success');
  });

  document.getElementById('sendCharacterToCasting')?.addEventListener('click', () => {
      const file = characterAssetInput?.files?.[0];
      if (!file) return showToast('Pilih foto karakter terlebih dahulu.', 'warning');
      const transfer = new DataTransfer(); transfer.items.add(file); actorImagesInput.files = transfer.files;
      actorImagesInput.dispatchEvent(new Event('change'));
      document.getElementById('actorDesc').value = document.getElementById('ugcCharacterIdentity')?.value.trim() || 'Identitas mengikuti Character Master';
      document.getElementById('addActorModal')?.classList.add('active');
      showToast('Aset dipindahkan ke Casting. Lengkapi nama lalu simpan.', 'success');
  });

  document.getElementById('sendProductToStoryboard')?.addEventListener('click', () => {
      const file = productAssetInput?.files?.[0];
      if (!file) return showToast('Pilih foto produk terlebih dahulu.', 'warning');
      selectedAffiliateProductFiles = [file];
      const transfer = new DataTransfer(); transfer.items.add(file);
      const affiliateInput = document.getElementById('affiliateImageInput');
      if (affiliateInput) { affiliateInput.files = transfer.files; affiliateInput.dispatchEvent(new Event('change')); }
      document.querySelector('.nav-item[data-tab="tab-storyboard"]')?.click();
      const toggle = document.getElementById('chkAffiliateMode'); if (toggle) { toggle.checked = true; toggle.dispatchEvent(new Event('change')); }
      const ugcToggle = document.getElementById('chkUgcMode'); if (ugcToggle) ugcToggle.checked = true;
      document.getElementById('affiliateProductName').value = document.getElementById('ugcProductName')?.value.trim() || '';
      document.getElementById('briefProductValueInput').value = document.getElementById('ugcProductIdentity')?.value.trim() || '';
      const logline = document.getElementById('ugcLogline')?.value.trim() || '';
      if (logline) document.getElementById('premiseInput').value = logline;
      const productionMode = document.getElementById('ugcProductionMode')?.value || 'realism';
      const productionLabel = productionMode === 'commercial' ? 'commercial premium' : productionMode === 'raw_amateur' ? 'raw amateur smartphone anti-AI' : 'UGC natural';
      document.getElementById('briefResultInput').value = `Video ${productionLabel} untuk ${document.getElementById('ugcPlatform')?.value || 'TikTok'}, format mengikuti rasio produksi.`;
      const viralFormula = document.getElementById('ugcFormulaPrompt')?.value.trim() || '';
      const conversionBrief = document.getElementById('ugcConversionOutput')?.value.trim() || '';
      document.getElementById('briefExecutionInput').value = `Tone: ${document.getElementById('ugcTone')?.value || 'natural'}. Emotional arc: ${document.getElementById('ugcEmotionArc')?.value || ''}. Environment: ${document.getElementById('ugcBackground')?.selectedOptions?.[0]?.textContent || 'AI recommendation'}. Lighting: ${document.getElementById('ugcLighting')?.selectedOptions?.[0]?.textContent || 'AI recommendation'}. Setiap scene wajib memiliki purpose, aktivitas, ekspresi, komposisi, camera direction, dan transition bridge.${viralFormula ? ` Viral formula: ${viralFormula}` : ''}${conversionBrief ? ` Conversion brief: ${conversionBrief}` : ''}`;
      document.getElementById('creativeBriefPanel')?.setAttribute('open', '');
      showToast('Product Master sudah dipasang ke Storyboard dan Creative Brief.', 'success');
  });

  document.getElementById('runTrendRadar')?.addEventListener('click', async () => {
    const input = document.getElementById('trendRadarInput');
    const status = document.getElementById('trendRadarStatus');
    const button = document.getElementById('runTrendRadar');
    const catalogTheme = document.getElementById('genreCatalogSelect')?.selectedOptions?.[0]?.value?.trim() || '';
    const source = input?.value.trim() || catalogTheme;
    if (!source || source === '__auto_ai__') { if (status) status.textContent = 'Ketik tema/kata kunci atau pilih tema dari katalog terlebih dahulu.'; showToast('Tema pencarian belum diisi.', 'warning'); return; }
    if (button) { button.disabled = true; button.textContent = '⏳ Menganalisis…'; }
    if (status) status.textContent = 'AI sedang membaca pola hook, konflik, dan SEO…';
    try {
      const res = await fetch('/api/storyboard/trend_radar', { method: 'POST', headers: {'Content-Type':'application/json'}, body: JSON.stringify({ theme: `TREND RADAR. Sumber judul/pola: ${source}. Buat 8 judul SEO baru berbahasa Indonesia, masing-masing dengan logline singkat dan hook episode 1. Pertahankan genre dan emosi yang sedang diminati, tetapi jangan menyalin judul, karakter, dialog, atau plot spesifik karya sumber.`, series_mode: true, target_lang: 'Indonesia' }) });
      const data = await res.json();
      if (!res.ok) throw new Error(data.detail || 'Gagal menganalisis tren');
      const concept = data.concept || data.suggestion?.suggested_premise || '';
      const premise = document.getElementById('premiseInput');
      if (premise && concept) premise.value = concept;
      if (status) status.textContent = 'Selesai. Konsep AI sudah dikirim ke kolom premis; Anda dapat mengedit sebelum generate.';
      showToast('Trend Radar selesai membuat konsep baru.', 'success');
    } catch (err) {
      if (status) status.textContent = `Trend Radar gagal: ${err.message}`;
      showToast(err.message, 'error');
    } finally { if (button) { button.disabled = false; button.textContent = '✨ Analisis Tren & Buat Judul Baru'; } }
  });

  // Initial load
  fetchActors();
});

