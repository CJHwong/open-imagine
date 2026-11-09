# ruff: noqa: RUF001 -- Traditional Chinese punctuation is intentional.
"""Traditional Chinese AuK template content; wire IDs and choice values stay stable."""

from studio.l1_entities.template_translation import TemplateFieldTranslation as F
from studio.l3_interface_adapters.gateways.template_translations import TemplateTranslationSource

TRANSLATIONS: dict[str, TemplateTranslationSource] = {
    "Voice profile": {
        "name": "聲音輪廓",
        "hint": "設定說話者、音色、速度與表達方式",
        "text": "一位{speaker}以{texture}的聲音說話。語速{pace}，表達方式{delivery}。",
        "fields": (
            F("speaker", "說話者", "旁白員"),
            F("texture", "音色", "溫暖而清晰"),
            F("pace", "語速", "平穩、適中"),
            F("delivery", "表達方式", "自然、沉穩而精確"),
        ),
    },
    "Conversation": {
        "name": "對話",
        "hint": "描述說話者、聽者、場景與情緒",
        "text": "一位{speaker}在{context}中對{listener}說話。聲音傳達{emotion}，具有自然的對話停頓和清晰、生動的語句。",
        "fields": (
            F("speaker", "說話者", "親切的說話者"),
            F("listener", "聽者", "一位好友"),
            F("context", "場景", "家中安靜的談話"),
            F("emotion", "情緒", "溫暖與輕柔的關懷"),
        ),
    },
    "Narration": {
        "name": "旁白",
        "hint": "設定旁白員、主題、速度與語氣",
        "text": "一位{speaker}敘述{subject}。採用{pace}的語速和{tone}的語氣，咬字清晰、音量平衡，句尾收得從容而明確。",
        "fields": (
            F("speaker", "說話者", "紀錄片旁白員"),
            F("subject", "主題", "日常生活中的發現"),
            F("pace", "語速", "穩健、不急促"),
            F("tone", "語氣", "溫暖而深思熟慮"),
        ),
    },
    "Commanding delivery": {
        "name": "堅定表達",
        "hint": "選擇說話者、聽眾、速度與重點",
        "text": "一位{speaker}自信而清晰地對{audience}說話。採用{pace}的語速，{emphasis}，句尾堅定且收放自如。",
        "fields": (
            F("speaker", "說話者", "自信的領導者"),
            F("audience", "聽眾", "一個小團隊"),
            F("pace", "語速", "從容且富有變化"),
            F("emphasis", "重點", "明確強調關鍵字"),
        ),
    },
    "Dramatic character": {
        "name": "戲劇角色",
        "hint": "建立角色、場景、音色與情緒轉折",
        "text": "一位{character}在{scene}中說話。聲音具有{texture}的質感。傳達{emotion}，運用刻意的停頓、精確的咬字與富有表現力的強弱變化。",
        "fields": (
            F("character", "角色", "富有戲劇感的說書人"),
            F("scene", "場景", "出乎意料的真相揭曉時"),
            F("texture", "音色", "飽滿且具有共鳴"),
            F("emotion", "情緒", "從平靜的自信逐漸轉為興奮"),
        ),
    },
    "Emotional delivery": {
        "name": "情感表達",
        "hint": "設定說話者、情緒、速度與表達方式",
        "text": "一位{speaker}表達{emotion}。採用{pace}的語速和{delivery}的表達方式。讓情緒影響呼吸、停頓和句尾，同時保持字句清楚。",
        "fields": (
            F("speaker", "說話者", "沉思的說話者"),
            F("emotion", "情緒", "克制的悲傷"),
            F("pace", "語速", "緩慢、穩健"),
            F("delivery", "表達方式", "輕柔而略帶顫抖"),
        ),
    },
    "Replace words": {
        "name": "替換字詞",
        "hint": "更改錄音中的字詞或片語",
        "text": "將「{original}」替換成「{new}」。",
        "fields": (F("original", "原本的字詞"), F("new", "新的字詞")),
    },
    "Insert words": {
        "name": "插入字詞",
        "hint": "在指定片語前加入字詞",
        "text": "在「{anchor}」前加入「{text}」。",
        "fields": (F("text", "加入的字詞"), F("anchor", "定位片語")),
    },
    "Remove words": {
        "name": "移除字詞",
        "hint": "刪除片語，並檢查剪接前後的字詞",
        "text": "移除「{text}」。",
        "fields": (F("text", "移除的字詞"),),
    },
    "Pitch": {
        "name": "音高",
        "hint": "提高一到三個半音",
        "text": "將音高提高 {semitones} 個半音。",
        "fields": (F("semitones", "半音數"),),
    },
    "Speed": {
        "name": "速度",
        "hint": "放慢或加快，長度也會跟著改變",
        "text": "將說話速度調整為 {speed} 倍。",
        "fields": (F("speed", "速度"),),
    },
    "Volume": {
        "name": "音量",
        "hint": "提高 5、10 或 15 dB，最適合安靜的錄音",
        "text": "將音量提高 {decibels} dB。",
        "fields": (F("decibels", "分貝數"),),
    },
    "Emotion": {
        "name": "情緒",
        "hint": "改變說話方式，保留內容",
        "text": "將情緒改為{emotion}。",
        "fields": (
            F(
                "emotion",
                "情緒",
                choices=(
                    ("happy", "開心"),
                    ("angry", "憤怒"),
                    ("sad", "悲傷"),
                    ("fearful", "害怕"),
                    ("surprised", "驚訝"),
                    ("disgusted", "厭惡"),
                    ("calm", "平靜"),
                    ("excited", "興奮"),
                ),
            ),
        ),
    },
    "Timbre": {
        "name": "音色",
        "hint": "以文字描述聲音，保留說話內容",
        "text": "保持說話內容不變，將音色改為：「{description}」。",
        "fields": (F("description", "聲音描述"),),
    },
    "To whisper": {
        "name": "改為耳語",
        "hint": "同一位說話者，輕聲說話",
        "text": "將這段語音改為輕柔的耳語，保留說話者與內容。",
    },
    "From whisper": {
        "name": "改為正常說話",
        "hint": "同一位說話者，以正常音量說話",
        "text": "將這段耳語改為正常的說話聲，保留說話者與內容。",
    },
    "Remove accent": {"name": "移除口音", "hint": "保留聲音與字詞", "text": "移除地區口音，保留說話者的聲音與內容。"},
    "Remove sounds": {
        "name": "移除聲響",
        "hint": "呼吸、笑聲、咳嗽或哼唱",
        "text": "移除音訊中所有的{sounds}。",
        "fields": (
            F(
                "sounds",
                "聲響",
                choices=(("breaths", "呼吸聲"), ("laughs", "笑聲"), ("coughs", "咳嗽聲"), ("humming", "哼唱聲")),
            ),
        ),
    },
    "Add a sound": {
        "name": "加入聲響",
        "hint": "在開頭或結尾加入笑聲、咳嗽或嘆氣",
        "text": "在語音的{position}加入一聲{sound}。",
        "fields": (
            F("sound", "聲響", choices=(("laugh", "笑聲"), ("cough", "咳嗽聲"), ("sigh", "嘆氣聲"))),
            F("position", "位置", choices=(("beginning", "開頭"), ("end", "結尾"))),
        ),
    },
    "Denoise": {
        "name": "降噪",
        "hint": "移除背景噪音，保留其餘內容",
        "text": "只移除背景噪音，保留其餘一切，並輸出與原錄音等長的音訊。",
    },
    "Dereverberate": {
        "name": "去除殘響",
        "hint": "移除空間回音，保留其餘內容",
        "text": "只移除房間殘響，保留其餘一切，並輸出與原錄音等長的音訊。",
    },
    "Enhance": {
        "name": "增強音質",
        "hint": "同時去除噪音與回音，適合品質不佳的錄音",
        "text": "保留所有說話者，移除噪音和殘響，輸出乾淨且與原錄音等長的語音。",
    },
    "Fix muffled or clipped audio": {
        "name": "修復悶聲或削波",
        "hint": "修復聲音悶濁或削波失真的錄音",
        "text": "修復{defect}，恢復自然、清晰的語音。",
        "fields": (F("defect", "問題", choices=(("muffling", "悶濁"), ("clipping", "削波失真"))),),
    },
    "Keep one speaker": {
        "name": "保留一位說話者",
        "hint": "填入那位說話者在錄音中說的字詞",
        "text": "只保留說出「{content}」的說話者，移除其他所有說話者。",
        "fields": (F("content", "說話內容"),),
    },
    "Voices only": {
        "name": "只保留人聲",
        "hint": "保留說話與歌聲，移除音樂",
        "text": "保留所有人聲，包括說話和歌聲，移除其餘一切。",
    },
    "Vocals only": {"name": "只保留歌聲", "hint": "保留歌聲，移除伴奏", "text": "只保留歌唱聲，移除其餘一切。"},
    "Music only": {"name": "只保留伴奏", "hint": "保留音樂，移除人聲", "text": "移除歌唱和說話聲，保留其餘一切。"},
}
