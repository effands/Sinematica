"""Dynamic narrative pacing, tension waves, and multi-cultural genre archetypes."""

from typing import Any, Dict, List, Optional
import re
import json


CINEMATIC_ARCHETYPES = {
    "preschool": {
        "id": "preschool",
        "name": "Pra-Sekolah & Edukasi Ramah Anak",
        "scene_1_principle": "Buka dengan rasa ingin tahu ceria (wonder & curiosity), warna lembut, dan interaksi hangat. 100% DILARANG amarah, kekerasan, makian, atau ketakutan.",
        "camera_style": "Eye-level warm tracking, steady medium shot, gentle panning, soft focal transitions.",
        "audio_atmosphere": "Cheerful acoustic instruments (xylophone, acoustic guitar, pizzicato strings), bright nature sounds, gentle giggles.",
        "escalation_style": "Mulai dari penemuan lucu -> mencoba bersama -> hambatan kecil yang diselesaikan dengan kerja sama -> tawa dan perayaan gembira.",
        "forbidden_tropes": "Kekerasan fisik/verbal, bentakan, tokoh menakutkan, kesedihan berlarut, intimidasi.",
    },
    "elderly_nostalgia": {
        "id": "elderly_nostalgia",
        "name": "Kisah Lansia / Nostalgia / Heartwarming Slice-of-Life",
        "scene_1_principle": "Buka dengan suasana reflektif dan penuh kehangatan (uap teh, tangan keriput memegang kenangan, jendela bersinar keemasan / golden hour). Jangan terburu-buru.",
        "camera_style": "Intimate slow push-in, shallow depth of field, warm side-lighting, macro focus on sentimental objects.",
        "audio_atmosphere": "Mellow cello/piano melody, ticking wooden clock, soft breathing, gentle ambient wind.",
        "escalation_style": "Kenangan masa lalu -> dialog bijak atau rahasia yang lama tersimpan -> momen haru bersama generasi muda -> resolusi yang menyejukkan hati.",
        "forbidden_tropes": "Marah-marah histeris, aksi tergesa-gesa tanpa kedalaman emosi, stereotip kasar.",
    },
    "horror": {
        "id": "horror",
        "name": "Cinematic Horror & Supernatural Thriller",
        "scene_1_principle": "Buka dengan ketenangan yang ganjil (The Uncanny / anomali kecil di dunia normal). DILARANG langsung jumpscare atau teriak di scene 1; bangun rasa merinding (creeping dread) perlahan.",
        "camera_style": "Slow creeping dolly push-in, low-angle shadows, negative space framing, Dutch angle halus saat rasa takut mulai masuk.",
        "audio_atmosphere": "Room tone hening yang mencekam, lantai berderit pelan, detak jam terdengar terlalu keras, bisikan angin samar.",
        "escalation_style": "Anomali kecil -> kejanggalan tak terbantahkan -> isolasi/jebakan -> penampakan penuh/klimaks teror -> kesunyian pasca-kejadian.",
        "forbidden_tropes": "Jumpscare instan di detik awal, teriak-teriak tanpa sebab yang jelas, pencahayaan terlalu terang.",
    },
    "mythology": {
        "id": "mythology",
        "name": "Mitologi, Folklore & Legenda Epik",
        "scene_1_principle": "Buka dengan keagungan kosmik dan pertanda sakral (kabut pegunungan mistis, kuil kuno, relief bercahaya, ramalan kuno).",
        "camera_style": "High-angle epic wide shot, slow drone drift over misty landscapes, dramatic low-angle hero framing.",
        "audio_atmosphere": "Deep ancient choral chants, low resonant bronze gong/percussion, echoing wind and thunder.",
        "escalation_style": "Pertanda alam/sumpah kuno -> pelanggaran batas terlarang -> kebangkitan kekuatan magis -> pertarungan takdir kosmik -> warisan abadi.",
        "forbidden_tropes": "Dialog bahasa gaul modern, drama receh tanpa bobot mitologis, efek magis tanpa alasan naratif.",
    },
    "telenovela": {
        "id": "telenovela",
        "name": "Telenovela & Latin High Melodrama",
        "scene_1_principle": "Buka dengan elegansi, kemewahan, dan ketegangan gairah/harga diri (tatapan mata beradu tajam di aula pesta atau tangga hacienda mewah).",
        "camera_style": "Dramatic crash-zoom pada mata/bibir, sweeping crane shot mengelilingi karakter, lighting kontras tinggi dan kaya warna.",
        "audio_atmosphere": "Flamenco acoustic guitar, heavy orchestral strings dengan aksen dramatis, langkah sepatu hak tinggi di lantai marmer.",
        "escalation_style": "Sindiran berkelas berbalut senyum -> tuduhan pengkhianatan -> konfrontasi verbal meledak -> rahasia keluarga terbongkar.",
        "forbidden_tropes": "Karakter pasif tanpa reaksi, setting murahan tanpa karakter visual, dialog dingin tanpa emosi.",
    },
    "crime_noir": {
        "id": "crime_noir",
        "name": "Kriminal, Noir & Mafia Thriller",
        "scene_1_principle": "Buka dengan ketenangan dingin dan kalkulatif. Orang paling berbahaya berbicara paling pelan. Asap rokok, jalanan basah hujan malam, berkas rahasia.",
        "camera_style": "Chiaroscuro lighting, siluet tajam di balik kaca berbayang venetian blinds, steady handheld follow shot.",
        "audio_atmosphere": "Suara rintik hujan di aspal, denting pemantik zippo logam, bass drone rendah, desah napas dingin.",
        "escalation_style": "Kesepakatan bisnis rahasia -> ketidakcocokan data/kecurigaan -> jebakan terselubung -> baku tembak/sergapan taktis -> penyelesaian dingin.",
        "forbidden_tropes": "Teriak histeris tanpa strategi, aksi sembrono tanpa motif kekuasaan/uang.",
    },
    "scifi": {
        "id": "scifi",
        "name": "Sci-Fi, Cyberpunk & Space Opera",
        "scene_1_principle": "Buka dengan rasa takjub akan skala teknologi dan kesunyian masa depan (pantulan hologram neon, kapsul hibernasi, menatap galaksi tak berujung).",
        "camera_style": "Anamorphic lens flares, smooth mechanical slider pans, symmetry framing, tech-hud overlay perspectives.",
        "audio_atmosphere": "Low reactor core hum, synthetic electronic clicks, telemetry beeps, pressurized air release.",
        "escalation_style": "Anomali data/sinyal asing -> kegagalan protokol keselamatan -> ancaman eksistensial -> pertarungan teknologi tingkat tinggi -> batas baru kemanusiaan.",
        "forbidden_tropes": "Alat futuristik tanpa fungsi jelas, sihir tanpa landasan teknologi fiksi.",
    },
    "turkish_dizi": {
        "id": "turkish_dizi",
        "name": "Drama Turki (Dizi Melodrama)",
        "scene_1_principle": "Buka dengan tatapan mata mendalam yang sarat makna (Bakışlar 3-5 detik), hening yang sarat rahasia, di tepi Bosphorus atau ruang keluarga terpandang.",
        "camera_style": "Slow emotional push-in pada tatapan mata, shallow depth of field, golden hour atau nuansa melankolis Istanbul.",
        "audio_atmosphere": "Petikan dawai Bağlama / tiupan seruling Ney yang menyayat hati, denting sendok teh di gelas kaca Çay.",
        "escalation_style": "Pertemuan dingin penuh tata krama -> rahasia lama tercium -> konfrontasi kehormatan keluarga -> sumpah cinta atau pembalasan berkelas.",
        "forbidden_tropes": "Langsung memaki di scene 1 tanpa tradisi kehormatan, editing terburu-buru yang merusak momen emosional.",
    },
    "arab_musalsalat": {
        "id": "arab_musalsalat",
        "name": "Drama Timur Tengah & Arab (Musalsalat)",
        "scene_1_principle": "Buka dengan wibawa kehormatan keluarga (Sharaf), jabat tangan formal bermakna ganda, jamuan kopi Arab (Gahwa) dengan bahasa tubuh berbobot.",
        "camera_style": "Majestic wide architecture, stately eye-level dialogue framing, rich golden interior lighting.",
        "audio_atmosphere": "Oud acoustic strings, pouring of Gahwa from dallah, deep authoritative vocal resonance.",
        "escalation_style": "Diplomasi berwibawa antar klan -> penolakan kesepakatan berprinsip -> ketegangan hukum dan moral -> pengadilan keluarga / penyelesaian agung.",
        "forbidden_tropes": "Kurang sopan santun di awal, hilangnya martabat karakter utama.",
    },
    "anime_manga": {
        "id": "anime_manga",
        "name": "Anime & Manga (Filosofi Jo-Ha-Kyū & Ma)",
        "scene_1_principle": "Buka dengan konsep Ma (keheningan alam / jeda visual) dan inner monologue sebelum aksi. Dedaunan tertiup angin, mata menyipit fokus.",
        "camera_style": "Dynamic Japanese anime angles, low-angle diagonal framing, dramatic eye cutaways, speed lines pada akselerasi.",
        "audio_atmosphere": "Desir angin tajam, detak jantung karakter, hening total sesaat sebelum benturan jurus.",
        "escalation_style": "Jo (pembukaan tenang & filosofi) -> Ha (retakan ideologi & tarikan senjata) -> Kyū (ledakan sakuga aksi kilat).",
        "forbidden_tropes": "Aksi rusuh tanpa motif ideologi/prinsip, dialog datar tanpa emosi khas anime.",
    },
    "manhwa": {
        "id": "manhwa",
        "name": "Korean Manhwa & Webtoon (Aura Dominasi)",
        "scene_1_principle": "Buka dengan tekanan sosial/sistem yang menindas secara dingin, atau kemunculan sosok ber-aura menakutkan dengan tatapan mata berpendar.",
        "camera_style": "Vertical high-contrast tilt, shadow covering upper face with glowing eyes, dynamic speed tracking.",
        "audio_atmosphere": "Low ominous sub-bass pulse, sudden silence of crowds, sharp cloth fluttering in high wind.",
        "escalation_style": "Underdog tertekan -> kebangkitan/awakening -> dominasi aura mutlak -> pembalasan tak terhentikan.",
        "forbidden_tropes": "Karakter utama pasrah selamanya, lawan yang kalah tanpa ekspresi terkejut yang memuaskan.",
    },
    "manhua": {
        "id": "manhua",
        "name": "Chinese Manhua & Xianxia Cultivation",
        "scene_1_principle": "Buka dengan lanskap sekte kultivasi di atas awan, perdebatan etika Dao, atau jamuan teh beracun antar klan persilatan.",
        "camera_style": "Sweeping panoramic mountain mist, floating sword perspective, celestial lighting arrays.",
        "audio_atmosphere": "Guzheng & Guqin traditional strings, flowing water, sword resonance vibration (Jian Ming).",
        "escalation_style": "Perdebatan aturan Dao & Mianzi (harga diri) -> niat membunuh terasa -> formasi pedang dilepaskan -> benturan jurus langit & bumi.",
        "forbidden_tropes": "Makian jalanan murahan, pertarungan fisik tanpa konsep Qi atau energi kultivasi.",
    },
    "cdrama_duanju": {
        "id": "cdrama_duanju",
        "name": "C-Drama Micro-Drama / Duanju (ReelShort/DramaBox)",
        "scene_1_principle": "Buka dengan ketidakadilan yang menusuk (Chicui) atau misteri identitas tersembunyi. Tensi langsung terasa cepat dan adiktif.",
        "camera_style": "Tight vertical medium close-up, snappy punch-in on disdainful expression, rapid eye shifts.",
        "audio_atmosphere": "Sharp violin sting, dramatic door slam, tense percussion pulse.",
        "escalation_style": "Penghinaan/penolakan instan -> bukti misterius mulai terungkap -> pembalasan menusuk (Dalian) -> kemenangan mutlak (Shuang).",
        "forbidden_tropes": "Pacing lambat bertele-tele yang membuat penonton swipe.",
    },
    "cdrama_palace_xianxia": {
        "id": "cdrama_palace_xianxia",
        "name": "C-Drama Sinematik Istana & Kerajaan",
        "scene_1_principle": "Buka dengan tata krama istana yang anggun namun penuh racun intrik. Senyum di bibir, pisau di balik jubah sutra.",
        "camera_style": "Symmetrical imperial palace architecture, slow tracking through sheer silk curtains, elegant close-up on tea pouring.",
        "audio_atmosphere": "Delicate Erhu melody, rustle of heavy embroidered robes, gentle ceramic cup clink.",
        "escalation_style": "Percakapan formal bersandi -> jebakan taktik mulai menutup -> pengungkapan konspirasi -> vonis kekaisaran yang tak terbantahkan.",
        "forbidden_tropes": "Teriak-teriak kasar di depan kaisar/bangsawan tanpa etika istana.",
    },
    "bollywood": {
        "id": "bollywood",
        "name": "Bollywood & Indian Epic Cinema (Navarasa Drama)",
        "scene_1_principle": "Buka dengan pengenalan sosok berkarisma besar, ikatan tradisi/keluarga, atau dilema moral Dharma.",
        "camera_style": "Multi-angle dramatic cut, slow-motion hero entrance with windswept fabric, bold golden rim lighting.",
        "audio_atmosphere": "Powerful Dholak rhythm, soaring vocal alaap, heavy orchestral brass accents.",
        "escalation_style": "Janji kehormatan -> pengkhianatan/benturan prinsip -> konfrontasi dramatis bergelora -> kemenangan keadilan dan restu keluarga.",
        "forbidden_tropes": "Akting datar tanpa ekspresi, visual suram tanpa kontras emosi.",
    },
    "hollywood_cinematic": {
        "id": "hollywood_cinematic",
        "name": "Hollywood / Universal Cinematic Drama (3-Act Organic Arc)",
        "scene_1_principle": "Buka dengan Status Quo & 'Save the Cat' (membangun empati pada tokoh di dunia normalnya sebelum masalah menghantam).",
        "camera_style": "Motivated cinematic camera movement, 35mm anamorphic framing, natural lighting with soft fill.",
        "audio_atmosphere": "Authentic room tone & environment foley, subtle orchestral underscore.",
        "escalation_style": "Setup dunia & empati -> Inciting Incident -> komplikasi bertahap -> Krisis titik terendah -> Puncak klimaks -> Resolusi bermakna.",
        "forbidden_tropes": "Langsung histeris di detik ke-1 tanpa alasan yang bisa dirasakan penonton.",
    },
}


def detect_cinematic_archetype(
    genre: str = "",
    premise: str = "",
    target_country: str = "",
    is_children: bool = False,
    is_microdrama: bool = False,
) -> Dict[str, Any]:
    """Detect the most accurate storytelling archetype based on genre, premise, country, and mode."""
    if is_children:
        return CINEMATIC_ARCHETYPES["preschool"]

    genre_lower = str(genre or "").lower()
    country_lower = str(target_country or "").lower()
    premise_lower = str(premise or "").lower()
    combined = f"{genre_lower} {country_lower} {premise_lower}"

    # 1. Preschool / Kids check
    if any(k in combined for k in ("anak", "preschool", "balita", "paud", "cocomelon", "kartun anak")):
        return CINEMATIC_ARCHETYPES["preschool"]

    # 2. Anime & Manga check (Priority if explicit in genre, country, or premise)
    if any(k in genre_lower for k in ("anime", "manga", "shonen", "seinen", "sakuga", "mecha")) or "japan" in country_lower or "jepang" in country_lower or "anime" in premise_lower:
        return CINEMATIC_ARCHETYPES["anime_manga"]

    # 3. Manhwa (Korean Webtoon) check
    if any(k in genre_lower for k in ("manhwa", "webtoon", "solo leveling")) or "manhwa" in premise_lower or "webtoon" in premise_lower:
        return CINEMATIC_ARCHETYPES["manhwa"]

    # 4. Manhua / Cultivation check
    if any(k in genre_lower for k in ("manhua", "kultivasi", "cultivation", "xianxia", "wuxia", "sekte", "dao")) or any(k in premise_lower for k in ("manhua", "kultivasi", "cultivation", "xianxia", "wuxia", "sekte langit")):
        return CINEMATIC_ARCHETYPES["manhua"]

    # 5. Turkish Dizi check
    if any(k in country_lower for k in ("turki", "turkey", "turkish")) or any(k in genre_lower for k in ("dizi", "turkish drama")) or "dizi" in premise_lower:
        return CINEMATIC_ARCHETYPES["turkish_dizi"]

    # 6. Arab / Middle East (Musalsalat) check
    if any(k in country_lower for k in ("arab", "saudi", "emirates", "qatar", "egypt", "morocco", "timur tengah", "middle east")) or "musalsalat" in genre_lower or "musalsalat" in premise_lower:
        return CINEMATIC_ARCHETYPES["arab_musalsalat"]

    # 7. Bollywood / Indian Cinema check
    if any(k in country_lower for k in ("india", "bollywood", "hindi", "pakistan", "bangladesh")) or any(k in genre_lower for k in ("bollywood", "masala", "tollywood", "kollywood")):
        return CINEMATIC_ARCHETYPES["bollywood"]

    # 8. Telenovela check
    if any(k in genre_lower for k in ("telenovela", "latin")) or any(k in country_lower for k in ("mexico", "spanyol", "spain", "argentina", "colombia")) or "telenovela" in premise_lower:
        return CINEMATIC_ARCHETYPES["telenovela"]

    # 9. Elderly / Nostalgia check
    if any(k in combined for k in ("kakek", "nenek", "lansia", "elderly", "nostalgia", "masa tua", "pensiun", "kenangan lama")):
        return CINEMATIC_ARCHETYPES["elderly_nostalgia"]

    # 10. Horror check
    if any(k in combined for k in ("horror", "horor", "hantu", "ghost", "setan", "pesugihan", "creepy", "haunted", "teror gaib")):
        return CINEMATIC_ARCHETYPES["horror"]

    # 11. Mythology check
    if any(k in combined for k in ("mitologi", "mythology", "folklore", "wayang", "dewa", "legend", "legenda", "kutukan kuno", "kerajaan siluman")):
        return CINEMATIC_ARCHETYPES["mythology"]

    # 12. Sci-Fi check
    if any(k in combined for k in ("sci-fi", "scifi", "cyberpunk", "robot", "cyborg", "alien", "antariksa", "space", "futuristik", "dystopia", "ai apocalypse")):
        return CINEMATIC_ARCHETYPES["scifi"]

    # 13. Crime / Noir check
    if any(k in combined for k in ("kriminal", "crime", "noir", "mafia", "gangster", "detektif", "investigasi", "baku tembak", "narkoba", "perampokan")):
        return CINEMATIC_ARCHETYPES["crime_noir"]

    # 14. C-Drama Palace vs Duanju
    if any(k in country_lower for k in ("china", "mandarin", "tiongkok")) or any(k in combined for k in ("kerajaan cina", "istana kaisar", "selir", "dinasti")):
        return CINEMATIC_ARCHETYPES["cdrama_palace_xianxia"]

    if is_microdrama or any(k in combined for k in ("dracin", "microdrama", "dramabox", "reelshort", "shortmax", "pewaris menyamar", "mertua jahat")):
        return CINEMATIC_ARCHETYPES["cdrama_duanju"]

    return CINEMATIC_ARCHETYPES["hollywood_cinematic"]


def calculate_pacing_tier(scene_count: int) -> Dict[str, Any]:
    """Calculate dramatic tension waves, scene-by-scene budget, and opening requirements."""
    n = max(1, int(scene_count))
    if n <= 4:
        beats = {
            1: ["Langsung aksi/keputusan inti dan akibat emosionalnya dalam satu scene; konteks tersirat lewat properti/dialog singkat."],
            2: ["Langsung konflik inti dan keputusan klimaks, tanpa prolog.", "Akibat keputusan dan ending happy/sad sesuai premis."],
            3: ["Langsung konflik inti yang sudah berlangsung; konteks tampak dalam tindakan.", "Klimaks: pilihan atau pengungkapan penentu.", "Akibat dan ending happy/sad yang tuntas sesuai premis."],
            4: ["Langsung konflik inti, tanpa rutinitas pembuka.", "Satu komplikasi atau bukti yang mengubah pilihan.", "Klimaks: tindakan/keputusan penentu.", "Konsekuensi dan ending happy/sad sesuai premis."],
        }[n]
        return {
            "tier": 1,
            "name": "Ultra-Short Fast-Hook Arc (1–4 Scene)",
            "description": "Durasi sangat pendek. Diizinkan In Medias Res (langsung masuk ke percikan masalah/kejanggalan di detik awal), lalu eskalasi cepat menuju payoff.",
            "scene_1_tension": "Tension Level 6–7 (Instant Hook / Sudden Intrigue)",
            "structure_guide": f"STRUKTUR {n} SCENE (FAST-HOOK ARC):\n" + "\n".join(
                f"- Scene {i}: {beat}" for i, beat in enumerate(beats, 1)
            ),
        }

    if n <= 8:
        mid1 = max(3, n // 2)
        climax = max(mid1 + 1, n - 1)
        return {
            "tier": 2,
            "name": "Kishōtenketsu / Mini 3-Act Arc (5–8 Scene)",
            "description": "Durasi medium. DILARANG langsung marah-marah/menampar di Scene 1! Bangun dunia normal dan ketegangan halus terlebih dahulu.",
            "scene_1_tension": "Tension Level 2–3 (Status Quo & Subtle Curiosity/Tension)",
            "structure_guide": f"""STRUKTUR GELOMBANG TENSI ({n} SCENE):
- Scene 1 (Setup & Mood - Tensi 2-3): Dunia normal, suasana atmosferik, relasi karakter. DILARANG LANGSUNG BENTAK/MENAMPAR!
- Scene 2 (Inciting Spark - Tensi 4): Muncul anomali, surat rahasia, tatapan ganjil, atau gesekan kecil.
- Scene 3–{climax - 1} (Rising Tension - Tensi 6-7): Perdebatan terbuka, kecurigaan menguat, batas kesabaran diuji.
- Scene {climax} (Climax / Emotional Peak - Tensi 9-10): Puncak ledakan emosi, konfrontasi total, atau aksi penentu.
- Scene {n} (Aftermath & Twist - Tensi 3-4): Dampak keputusan, keheningan berbobot, atau kejutan penutup.""",
        }

    # n >= 9
    # Non-overlapping inclusive spans, including small 9/10-scene stories.
    stages = (
        (max(1, int(n * .20)), 'Latar, sejarah hubungan, empati dan tujuan tokoh'),
        (max(2, int(n * .30)), 'Pemicu yang mengganggu kehidupan tokoh'),
        (max(3, int(n * .55)), 'Upaya, hambatan dan konsekuensi yang membangun konflik'),
        (max(4, int(n * .75)), 'Rahasia/krisis dan pilihan dengan ruang bernapas'),
        (max(5, n - max(1, int(n * .10))), 'Klimaks: tindakan penentu yang sudah dibangun sebab-akibatnya'),
        (n, 'Dampak keputusan dan ending happy/sad sesuai premis, bukan cliffhanger wajib'),
    )
    spans = []
    previous = 0
    for end, label in stages:
        if end > previous:
            spans.append(f'- Scene {previous + 1}–{end}: {label}.')
            previous = end
    return {
        "tier": 3,
        "name": "Full Cinematic Tension Wave (9–16+ Scene)",
        "description": "Durasi panjang / film sinematik utuh. Pacing harus bergelombang alami (Tension Waves) dengan ruang bernapas (Breathing Room / Ma).",
        "scene_1_tension": "Tension Level 2 (World Building, Character Empathy & Atmospheric Setup)",
            "structure_guide": f"STRUKTUR GELOMBANG TENSI SINEMATIK PANJANG ({n} SCENE):\n" + '\n'.join(spans),
    }


def build_dynamic_narrative_rules(
    scene_count: int,
    genre: str = "",
    premise: str = "",
    target_country: str = "",
    is_children: bool = False,
    is_microdrama: bool = False,
) -> str:
    """Build the definitive cinematic pacing & dramatic density rule block for prompt injection."""
    archetype = detect_cinematic_archetype(
        genre=genre,
        premise=premise,
        target_country=target_country,
        is_children=is_children,
        is_microdrama=is_microdrama,
    )
    pacing = calculate_pacing_tier(scene_count)
    short_story = int(scene_count) <= 4
    opening = (
        "Langsung tampilkan aksi/masalah inti; sejarah tersirat dalam bukti dan reaksi, tanpa prolog terpisah. "
        "Ini mengatur kepadatan cerita, bukan memaksa gerakan tergesa, bentakan atau kekerasan."
        if short_story else archetype['scene_1_principle']
    )
    opening_rules = (
        "Untuk 1–4 scene, langsung konflik/aksi inti dan sisakan akibat/ending; jangan menunda klimaks demi setup. "
        "Pertahankan batas keamanan dan nada genre, terutama cerita anak."
        if short_story else
        "Jika jumlah scene >= 5, DILARANG KERAS membuka Scene 1 dengan teriakan, makian, tamparan, atau amarah meledak-ledak tanpa latar belakang emosional! "
        "Bangun sejarah hubungan, empati dan tujuan sebelum klimaks; gunakan bukti atau interaksi, bukan eksposisi panjang."
    )

    return f"""
ATURAN KEPADATAN DRAMATIS & GELOMBANG TENSI SINEMATIK (WAJIB DIPATUHI SECARA MUTLAK):
0. **KONTRAK RETENSI PENONTON (BERLAKU UNTUK SEMUA DURASI)**:
   - Tentukan sejak awal alasan penonton harus lanjut menonton: pertanyaan, ancaman, keinginan, rahasia,
     rasa lucu/haru, bukti yang ditunggu, atau janji payoff.
   - Setiap scene harus membayar sebagian janji itu atau memperumitnya. Dilarang membuat scene yang hanya
     indah, berjalan, menatap, pindah ruangan, atau menjelaskan ulang informasi yang sama.
   - Tulis sebab-akibat jelas: karena scene sebelumnya terjadi, tokoh memilih/kehilangan/menemukan sesuatu
     di scene ini; akibat scene ini memaksa scene berikutnya.
   - Ending wajib memberi payoff emosional: jawaban, hukuman, restu, perpisahan, kemenangan, pelajaran,
     kejutan penutup, CTA, atau resolusi sesuai format.

1. **ARKETIPE DRAMA TERDETEKSI: {archetype['name'].upper()}**
   - **Prinsip Scene 1**: {opening}
   - **Gaya Kamera Sinematik**: {archetype['camera_style']}
   - **Audio & Atmosfer Suara**: {archetype['audio_atmosphere']}
   - **Pola Eskalasi Emosi**: {archetype['escalation_style']}
   - **Hal yang DILARANG**: {archetype['forbidden_tropes']}

2. **PANDUAN PACING {pacing['name'].upper()} (Total {scene_count} Scene)**:
   - Level Tensi Scene 1: {pacing['scene_1_tension']}
   {pacing['structure_guide']}
   - Untuk cerita lengkap non-anak, JANGAN membuat rangkaian observasi datar. Setiap scene wajib mengubah
     keadaan cerita: informasi baru, keputusan baru, tekanan baru, kehilangan, bukti, konfrontasi, pengorbanan,
     kemenangan, atau konsekuensi.
   - Wajib ada empat beat yang terbaca di judul/action_summary/scene_purpose:
     INCITING CONFLICT di 20-35% awal cerita, RISING COMPLICATION di tengah, CLIMAX/CONFRONTATION di 70-90%,
     dan RESOLUTION/ENDING di scene terakhir. Bila salah satu hilang, storyboard dianggap gagal.

3. **ATURAN PEMBUKAAN FILM (ANTI MARAH-MARAH TANPA ALASAN)**:
   - {opening_rules}
   - Akhiri keseluruhan cerita dengan konsekuensi happy/sad sesuai premis atau naskah; bila belum ditentukan,
     pilih satu hasil emosional yang masuk akal. Jangan mengganti sad ending dengan kemenangan wajib.
     Cliffhanger antarpart boleh, tetapi ending film terakhir harus menyelesaikan konflik kecuali diminta serial terbuka.

4. **VARIASI KATA KERJA AKSI DRAMATIS**:
   Gunakan kata kerja fisik yang ekspresif dan bervariasi sesuai adegan:
   - *Tensi Rendah / Setup*: menatap lekat, menyeduh perlahan, mengamati dari kejauhan, menyembunyikan dokumen, menarik napas berat, tersenyum tertahan.
   - *Eskalasi*: melangkah mendekat, meletakkan benda dengan tegas, memalingkan muka, berbisik dingin, menolak jabat tangan, menyodorkan bukti.
   - *Klimaks*: merenggut bukti, membanting segel, berdiri menantang, merangkul haru, melepaskan kekuatan/jurus, menangis lega.
""".strip()


def story_phase_for_range(scene_offset: int, part_scene_count: int, total_scene_count: int) -> Dict[str, Any]:
    """Map a storyboard part onto a feature-film arc without forcing a local climax."""
    total = max(1, int(total_scene_count or part_scene_count or 1))
    start = max(0, int(scene_offset or 0))
    end = min(total, start + max(1, int(part_scene_count or 1)))
    if start == 0 and end == total:
        return {"id": "complete", "name": "Complete Story Arc", "tension": "sesuai jumlah scene", "climax_allowed": True}
    midpoint = ((start + end) / 2) / total
    if midpoint <= 0.15:
        return {"id": "setup", "name": "Status Quo, Atmosphere & Empathy", "tension": "1-3", "climax_allowed": False}
    if midpoint <= 0.27:
        return {"id": "inciting", "name": "Inciting Incident & Reluctant Response", "tension": "3-5", "climax_allowed": False}
    if midpoint <= 0.52:
        return {"id": "rising", "name": "Rising Complications & First Attempts", "tension": "4-7", "climax_allowed": False}
    if midpoint <= 0.72:
        return {"id": "midpoint", "name": "Midpoint Reversal, Discovery & Consequences", "tension": "5-8", "climax_allowed": False}
    if midpoint <= 0.86:
        return {"id": "crisis", "name": "Crisis, Loss & Final Preparation", "tension": "6-9", "climax_allowed": False}
    if midpoint <= 0.96:
        return {"id": "climax", "name": "Earned Climax & Decisive Confrontation", "tension": "8-10", "climax_allowed": True}
    return {"id": "resolution", "name": "Aftermath, Emotional Resolution & Epilogue", "tension": "2-5", "climax_allowed": False}


def build_story_part_rules(
    scene_offset: int,
    part_scene_count: int,
    total_scene_count: int,
    part_number: int = 1,
    previous_context: Optional[Dict[str, Any]] = None,
) -> str:
    """Prompt contract for one independently generated part of a longer film."""
    total = max(1, int(total_scene_count or part_scene_count or 1))
    start = max(0, int(scene_offset or 0)) + 1
    end = min(total, start + max(1, int(part_scene_count or 1)) - 1)
    phase = story_phase_for_range(start - 1, part_scene_count, total)
    prior = json.dumps(previous_context or {}, ensure_ascii=False)[:12000]
    if phase['id'] == 'complete':
        return f"""KONTRAK CERITA LENGKAP (Scene Global 1-{total}):
Hasilkan tepat {total} scene sebagai satu cerita lengkap, bukan potongan long-form.
{calculate_pacing_tier(total)['structure_guide']}
Klimaks dan ending wajib mendapat ruang sesuai jumlah scene. Ikuti hasil happy/sad dalam premis/naskah;
jangan berhenti di cliffhanger kecuali pengguna memang meminta ending terbuka.
""".strip()
    reaches_climax = end / total > 0.86 and (start - 1) / total < 0.96
    climax_rule = (
        "Klimaks utama diizinkan pada scene global fase klimaks; setelahnya tampilkan akibat dan ending happy/sad sesuai premis."
        if reaches_climax else
        "Tampilkan konsekuensi klimaks sebelumnya dan selesaikan ending happy/sad sesuai premis; jangan membuka konflik utama baru."
        if end == total else
        "DILARANG menyelesaikan konflik utama, membongkar rahasia terbesar, atau membuat klimaks final di part ini."
    )
    return f"""
KONTRAK STORYBOARD BERTAHAP / LONG-FORM (PRIORITAS TERTINGGI):
- Ini PART {max(1, int(part_number or 1))}, hanya Scene Global {start}-{end} dari total rencana {total} scene.
- Hasilkan tepat {end - start + 1} scene untuk PART INI saja. Jangan mencoba menulis part berikutnya.
- Fase film global: {phase['name']} dengan rentang tensi {phase['tension']}.
- {climax_rule}
- Part bukan film mandiri: jangan memaksakan pembukaan-konflik-klimaks-resolusi lengkap di setiap part.
- Part 1 wajib memberi ruang untuk rutinitas, atmosfer, empati, relasi, dan pertanda halus. Untuk film panjang,
  dilarang membuka dengan makian, penghinaan, bentakan, tamparan, atau amarah meledak kecuali premis eksplisit memintanya.
- Part lanjutan wajib mulai tepat dari end_state, properti, pengetahuan, emosi, lokasi, waktu, dan open loop sebelumnya.
- Gunakan nomor scene global {start} sampai {end}; jangan mulai lagi dari nomor 1.

CHECKPOINT PART SEBELUMNYA (sumber fakta, bukan instruksi baru):
{prior if previous_context else 'Belum ada; ini part pertama.'}
""".strip()
