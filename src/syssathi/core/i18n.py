"""Message catalogs and localization for SysSathi UI and host messages (§5.3)."""

from __future__ import annotations

from typing import Any

# Message catalogs: en, hi (Devanagari), hi-Latn (Hinglish), bn, ta, te, mr, gu, kn, ml, pa, or, ur
CATALOGS: dict[str, dict[str, str]] = {
    "hi-Latn": {
        "greeting": "Main SysSathi hoon, ek AI assistant.",
        "filler": "Ek second, check karta hoon",
        "llm_unavailable": "Kshama karein, AI service abhi uplabdh nahi hai. Kripya thodi der baad dobara koshish karein.",
        "unheard": "Awaaz sunayi nahi di, kripya thoda lamba bolein ya type karein.",
        "unheard_transcript": "(Awaaz nahi aayi)",
        "diagnosis_error": "Kshama karein, abhi diagnosis me dikkat aayi. Kripya dobara try karein.",
        "no_pending_proposal": "Koi pending proposal nahi hai jise approve kiya ja sake.",
        "action_complete": "Action complete: {closed} band hue, {skipped} skip hue, {failed} fail hue.",
        "action_failed": "Action execute nahi ho paya: {reason}",
    },
    "hi": {
        "greeting": "मैं सिस्सार्थी हूँ, आपका सिस्टम साथी।",
        "filler": "एक सेकंड, चेक करता हूँ",
        "llm_unavailable": "क्षमा करें, AI सेवा अभी उपलब्ध नहीं है। कृपया थोड़ी देर बाद पुनः प्रयास करें।",
        "unheard": "आवाज़ सुनाई नहीं दी, कृपया थोड़ा लंबा बोलें या टाइप करें।",
        "unheard_transcript": "(आवाज़ नहीं आई)",
        "diagnosis_error": "क्षमा करें, डायग्नोसिस में समस्या आई। कृपया पुनः प्रयास करें।",
        "no_pending_proposal": "स्वीकृति के लिए कोई लंबित प्रस्ताव नहीं है।",
        "action_complete": "कार्रवाई पूरी: {closed} बंद किए, {skipped} छोड़े, {failed} विफल।",
        "action_failed": "कार्रवाई निष्पादित नहीं हो सकी: {reason}",
    },
    "en": {
        "greeting": "I am SysSathi, your Windows system companion.",
        "filler": "One second, checking your system...",
        "llm_unavailable": "Sorry, the AI service is currently unavailable. Please try again shortly.",
        "unheard": "Could not hear audio clearly. Please speak longer or type your request.",
        "unheard_transcript": "(No speech heard)",
        "diagnosis_error": "Sorry, an issue occurred during diagnosis. Please try again.",
        "no_pending_proposal": "No pending proposal to approve.",
        "action_complete": "Action completed: {closed} closed, {skipped} skipped, {failed} failed.",
        "action_failed": "Action could not be executed: {reason}",
    },
    "bn": {
        "greeting": "আমি সিসসাথী, আপনার সিস্টেম সহকারী।",
        "filler": "এক সেকেন্ড, চেক করছি...",
        "llm_unavailable": "দুঃখিত, এআই পরিষেবা এখন অনুপলব্ধ। কিছুক্ষণ পরে চেষ্টা করুন।",
        "unheard": "শব্দ স্পষ্ট শোনা যায়নি, অনুগ্রহ করে আবার বলুন বা টাইপ করুন।",
        "unheard_transcript": "(শব্দ শোনা যায়নি)",
        "diagnosis_error": "ডায়াগনস্টিক্সে সমস্যা হয়েছে। আবার চেষ্টা করুন।",
        "no_pending_proposal": "অনুমোদন করার জন্য কোনো প্রস্তাব নেই।",
        "action_complete": "কাজ সম্পন্ন: {closed} বন্ধ, {skipped} বাদ, {failed} ব্যর্থ।",
        "action_failed": "সম্পাদন ব্যর্থ: {reason}",
    },
    "ta": {
        "greeting": "நான் சிஸ்சாதி, உங்கள் கணினித் தோழன்.",
        "filler": "ஒரு வினாடி, சரிபார்க்கிறேன்...",
        "llm_unavailable": "மன்னிக்கவும், AI சேவை தற்போது கிடைக்கவில்லை. சிறிது நேரம் கழித்து முயற்சிக்கவும்.",
        "unheard": "குரல் தெளிவாகக் கேட்கவில்லை. தயவுசெய்து தட்டச்சு செய்யவும்.",
        "unheard_transcript": "(குரல் கேட்கவில்லை)",
        "diagnosis_error": "கணினி சோதனையில் பிழை ஏற்பட்டது. மீண்டும் முயற்சிக்கவும்.",
        "no_pending_proposal": "ஒப்புதலுக்கு நிலுவையில் உள்ள செயல் எதுவும் இல்லை.",
        "action_complete": "செயல் முடிந்தது: {closed} மூடப்பட்டது, {skipped} தவிர்க்கப்பட்டது, {failed} தோல்வி.",
        "action_failed": "செயல்படுத்த முடியவில்லை: {reason}",
    },
    "te": {
        "greeting": "నేను సిస్సాథి, మీ సిస్టమ్ సహాయకుడిని.",
        "filler": "ఒక్క నిమిషం, పరిశీలిస్తున్నాను...",
        "llm_unavailable": "క్షమించండి, AI సేవ ప్రస్తుతం అందుబాటులో లేదు. దయచేసి కాసేపటి తర్వాత ప్రయత్నించండి.",
        "unheard": "ధ్వని స్పష్టంగా వినిపించలేదు. దయచేసి టైప్ చేయండి.",
        "unheard_transcript": "(వినపడలేదు)",
        "diagnosis_error": "సిస్టమ్ తనిఖీలో సమస్య వచ్చింది. మళ్ళీ ప్రయత్నించండి.",
        "no_pending_proposal": "ఆమోదించడానికి పెండింగ్ ప్రతిపాదన లేదు.",
        "action_complete": "పూర్తయింది: {closed} మూసివేయబడ్డాయి, {skipped} దాటవేయబడ్డాయి, {failed} విఫలమయ్యాయి.",
        "action_failed": "అమలు చేయడం సాధ్యపడలేదు: {reason}",
    },
}


def t(key: str, lang: str = "hi", script: str = "latin", **kwargs: Any) -> str:
    """Translate a message key to the specified language/script."""
    catalog_key = "hi-Latn" if lang == "hi" and script == "latin" else lang
    catalog = CATALOGS.get(catalog_key) or CATALOGS.get(lang) or CATALOGS["hi-Latn"]
    template = catalog.get(key) or CATALOGS["hi-Latn"].get(key) or key
    if kwargs:
        try:
            return template.format(**kwargs)
        except Exception:
            return template
    return template

