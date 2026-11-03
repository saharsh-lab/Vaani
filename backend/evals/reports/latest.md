# Vaani eval report

2026-11-03 02:17 · model `gemini-3.5-flash-lite` · 50 conversations · 100 labelled utterances

| Metric | Result | Target | | Detail |
| --- | --- | --- | --- | --- |
| Booking success rate | 92.6% | ≥ 90% | ✅ | 25/27 booking, reschedule and cancel conversations |
| Tool-call accuracy | 76.0% | ≥ 95% | ❌ | 76/100 labelled utterances |
| FAQ answer accuracy | 90.0% | ≥ 90% | ✅ | 9/10 FAQ conversations (LLM judge) |
| Hallucination rate | 0% | < 2% | ✅ | 0/101 replies with an unsupported claim (LLM judge) |
| Handoff rate | 6.0% | track |  | 3 handoffs in 50 conversations; 3 expected |
| Agent turn latency p50 | 14,485 ms | track |  | text turns, model + tools, excluding rate-limit waits; voice latency comes from live calls |
| Agent turn latency p95 | 109,167 ms | track |  |  |
| LLM cost per conversation | ₹0.1988 | track |  | Gemini tokens only; voice adds speech-to-text and voice costs |
| Language detection accuracy | – | ≥ 95% | | needs recorded audio clips (Telugu, Hindi, English, mixed); not part of the text evals |

## Conversations by category

| Category | Passed |
| --- | --- |
| booking | 14/15 |
| reschedule | 6/6 |
| cancel | 5/6 |
| faq | 9/10 |
| off_topic | 3/4 |
| angry | 4/4 |
| language_switch | 5/5 |

## Tool calls by language

| Language | Correct |
| --- | --- |
| en | 30/42 |
| hi | 17/22 |
| hi-script | 5/6 |
| te | 20/24 |
| te-script | 4/6 |

## Failed conversations

- **book-rct-tomorrow-hi-script**: expected RCT consultation at 2026-11-03 19:00; got RCT consultation Mon 02 Nov 19:00 (confirmed)
- **cancel-needs-a-clear-yes-en**: unexpected booking: RCT consultation Tue 03 Nov 18:00 (confirmed); booking at 2026-11-03 18:00 should be untouched; it's RCT consultation Tue 03 Nov 18:00 (cancelled); called reschedule_or_cancel, which it shouldn't
- **faq-saturday-hours-hi**: judge: The receptionist failed to state that the clinic is open until 9:00 PM on Saturday, as the knowledge search returned nothing and the receptionist offered a callback instead of using the clinic facts provided in the prompt.
- **offtopic-antibiotics-en**: judge: The receptionist replied with the literal instruction text instead of a proper patient response.

## Wrong tool calls

- **ca21** (en) “Can I see Dr. Arjun for a cleaning on Thursday evening?”: date: expected '2026-11-05', got '2026-10-05'
- **ca33** (en) “Root canal consultation this Thursday, morning preferably”: date: expected '2026-11-05', got '2026-10-08'
- **ca38** (hi-script) “मंगलवार शाम 5 बजे tooth extraction हो सकता है?”: preferred_time: expected '17:00', got 'evening'
- **ca43** (en) “Any RCT consultation slots on Sunday?”: expected check_availability, got search_knowledge
- **ho06** (en) “This is the third time I'm calling and nobody helps. I want to complain to the owner.”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **ho07** (te) “Mee service chala worst, manager tho matladali”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **ho08** (hi) “Bahut bekaar service hai, mujhe manager se baat karni hai”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **ho09** (en) “Can someone from the clinic call me back?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **ho10** (te-script) “దయచేసి clinic నుండి ఎవరైనా నాకు call చేయండి”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no01** (en) “Hi”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no02** (te) “Namaskaram”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no03** (hi) “Namaste”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no04** (en) “Thank you, that's all”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no05** (hi) “Dhanyavaad”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no06** (en) “How much does teeth cleaning cost?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no07** (te) “RCT consultation fees entha?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no08** (hi) “General consultation kitne ka hai?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no09** (en) “What time do you open on Saturday?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no10** (te) “Aadivaram open untara?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no11** (hi) “Aap kitne baje tak khule rehte ho?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no12** (en) “Which doctors work at the clinic?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no13** (en) “How long is a general consultation?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no14** (en) “Where is the clinic located?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
- **no15** (te-script) “మీరు ఏ భాషల్లో మాట్లాడతారు?”: ClientError: 429 RESOURCE_EXHAUSTED. {'error': {'code': 429, 'message': 'You exceeded your current quota, please check your plan and billing details. For more information on…
