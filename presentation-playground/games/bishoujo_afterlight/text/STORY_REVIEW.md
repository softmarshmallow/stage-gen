# Afterlight story text review

P99 preserves every English/Korean display line. Ambient Particles now run
through the lounge scenes (warm dust), Eira's relay (cool dust), and the infernal
hall (smoke, rising embers and sparks), returning to quiet dust with Nami.
Eira's four voiced lines in each language use Transmission Voice while she is
projected; the courier's two replies remain explicitly unvoiced. These runtime
cues do not change recording source revisions or request regeneration.

## The Address Beyond / 건너편의 주소

An unnamed male courier delivers an unusual letter to Afterlight House. Nami,
Yuzu, Sena, and Riko enter through a shared station-ward emergency. Riko returns
from the station in person with a ward monitor. While the others prepare the
repair, the courier steps into a dedicated relay laboratory and speaks privately
with Eira, a researcher at the central exchange, through a floating framed
display. The laboratory treats memory glass as an engineered relay medium.
Her instructions help the group
repair the circuit before the letter's seal answers again and pulls the courier
into the Hall of Unclaimed Names. The Keeper demands his name; Nami reaches him
through the seal and helps him return. The episode remains a bishōjo ensemble
adventure, with one playful reconverging response choice and no romance routes
or affection scores.

The runtime sources are [ko.json](ko.json), [en.json](en.json), and the authored
[story_beats.gd](../story_beats.gd). Quote a stable text key when giving wording
feedback. This sheet reflects their current 57-beat order, including both
available choices and replies; it does not define a shared story language.

## Cast and pacing

| Character | Role |
| --- | --- |
| Nami / 나미 | Welcomes the courier, opens the bypass, and reaches him across the seal |
| Yuzu / 유즈 | Reads the warning and checks the repair sequence |
| Sena / 세나 | Repairs the station feed before the otherworld incident |
| Riko / 리코 | Returns physically with the ward monitor, calls the repair signal, and starts the kettle |
| Eira / 에이라 | A remote relay researcher whose portrait appears inside a floating framed display during the private call |
| The Keeper / 문지기 | A dedicated villain who controls the space between missing addresses |
| Courier / 배달원 | Helps the group, speaks with Eira alone, resists the Keeper, and finds his way back |

The black monologue `hold_the_message` (beat 23) covers the move into the relay
laboratory. Beats 24–29 contain four Eira turns and two courier replies, with
Eira's portrait as the sole visible character throughout. The floating frame
contains her image and its Hologram treatment while the courier speaks.
`relay_return` (beat 30) ends the transmission, clears its
treatment, and restores the reading-room background under another black
monologue. Yuzu, Sena, and Riko return on beat 31. Eira's scene establishes a
specific remote conversation; Riko is never projected in the main episode.

The retained IDs `riko_on_the_glass` and `riko_signs_off` are historical text and
checkpoint identifiers. Their current cues show Riko's physical introduction
and her departure to put the kettle on, respectively. No remote-presence claim
remains in those lines.

The repair finishes at `the_reroute` (beat 34). Nami's `the_seal_answers` setup is
beat 35; the excursion and return occupy beats 36–48. All four heroine
introductions, Eira's consultation, and the repair precede that change. The
Keeper remains a distinct supporting actor. Its infernal hall is revealed after
the black `between_addresses` intertitle; the return restores the reading room.
The conservatory, reading room, infernal hall, and relay laboratory each serve their
own authored setting. Story intent comes first; environment assets follow it.

## Direction and effects

| Story situation | Composed presentation |
| --- | --- |
| Arrival and recovery from the first flash | Walking Approach, Waking Eye-Opening (brief peek, blink shut, full opening), Nami's close portrait |
| Warning, planning, and the playful offer | Multi-actor dialogue, focus/manpu, close-up camera, explicit two-option choice |
| Reading the letter in window light | Portrait Detail Shot, Camera Drift, Actor Halo |
| Nami leaves and Sena arrives | Walk-Away, sequential handoff, survivor translation |
| Reading-room work and Riko's physical arrival | Establishing Shot, Restless Bounce, ward-monitor report |
| Private call with Eira | Dedicated laboratory and researcher portrait, floating display frame, sustained Hologram treatment, solo dialogue, close-up camera |
| Entering and leaving the relay laboratory | Protagonist monologues on black cover the location changes; the return ends the transmission |
| The repaired seal answers | Barrier refraction, Heat Haze, corruption, finite Impact Shake |
| The Keeper encounter | Background-only Waking Eye-Opening into the hall, dedicated actor, alpha-masked corruption, environmental/screen treatment, close-up |
| Return and relief | Field fade-out, Waking Eye-Opening onto Nami, explicit fingertip contact, after-reveal Sigh Puff |
| Riko leaves to make tea | Silhouette Fade departure |
| Group reunion | Four-actor staging and final story hook |

Five intertitles show the courier's internal monologues. The host pauses world
clocks while they are displayed. The four Sigh Puff cues wait for the text to
finish revealing. Text Reveal Audio supplies a typing fallback or a host-provided
voice; generated TTS, transmission voice processing, and general Ambient
Particles remain deferred. Shader mist and analytic motes belong to the current
corruption effect, not a particle-system module.

P85 strengthens the infernal section's visual direction: wider red aura and
black mist, more visible background heat, and brief heavier impacts on arrival,
resistance and return. The close conversation keeps her expression readable;
the normal room returns after a 1.8-second effect fade. Story wording and beat
order are unchanged. The intensity target is an artistic judgment, not a score
computed by the renderer.
P86 attaches the ember/mist patterns to the world camera and gives the embers
varied glowing fleck shapes. P87 uses the waking blink when the hall is first
revealed without characters, and when the courier returns to Nami. At that point, the same
56 beats and bilingual lines remained; only their presentation cues change.

P88 replaces the static sparkle mark at `the_reroute` with a brief Radial Sprite
Burst behind Sena. It begins 0.85 seconds into the line after the camera settles,
expands and fades over 1.35 seconds, and clears when the player advances. The
comic repair line and all episode wording remain unchanged.

P89 isolates Yuzu for `the_warning`. Once the shot settles, only the background
fades to black over 0.45 seconds, beginning 1.0 second into the line. Her
position and appearance stay fixed; the black background holds until advance.
The next beat restores the scenery and the two-character conversation.

P90 uses `the_useful_kind` after Sena has fully arrived. Yuzu takes a quick step
toward her while answering the toolbox remark, then holds the closer position.
The 0.25-second delay and 0.32-second movement keep the response brisk; Sena
stays still. The next establishing shot clears this pair. This is Quick Approach
under Actor Blocking, with unchanged dialogue wording.

P91 holds the reading-room background fixed during `riko_on_the_glass`,
`two_green_lamps` and `waiting_for_the_signal`. Cast Pan slides the whole group
to center Riko, then Yuzu, then Riko. Their local positions and existing speaker
bounces remain independent. The next monologue clears the group framing as
composition changes. No episode wording is changed.

P92 adds Stepped Transform Loops to `no_ordinary_post`, `riko_on_the_glass`,
and `everyone_accounted_for`. Their existing sweat, anger and sparkle images
alternate held rotation/scale poses while the line is active. The first loop
appears immediately after Nami's initial close portrait, Riko's loop follows the
Cast Pan, and the reunion uses the same mechanism with a different image.
Episode wording and the four after-reveal Sigh Puff events remain unchanged.

P93 changes the static sweat marks at `a_modest_name` and `a_proper_hello`
into one-shot Sweat Drop Fall cues. They wait for completed text reveal, slide
down from the temple, and fade. Sena's embarrassed boast and Riko's belated
introduction supply the context. All four Sigh Puff events remain; both effects
use the same animation and event lifecycle. Episode wording is unchanged.

P94 adds `a_touch_that_stays` immediately after the waking return and before
`only_a_second`. Nami holds out a finger in a dedicated contact portrait. Once
her words finish revealing, clicking or touching the fingertip confirms contact;
a brief ring response leads into her existing relief and Sigh Puff. Space and
clicks elsewhere leave the contact pending. The preceding courier line now
introduces her outstretched hand. This adds one beat, for 57 in total.

## Paired episode text

There are 57 beats. Beat 07 offers two options, beat 08 shows the selected reply,
and both continue into beat 09. Cue labels below describe authored direction;
UI, wrapping, and effect ordering remain owned by this game's host.

| # / Stable text key | Speaker · cue | Korean | English |
| --- | --- | --- | --- |
| 01 · `episode.undeliverable` | You / 나 · monologue | 주소는 있었다. 보낸 사람은 없었다.<br>그날 마지막 배달이었다. 나는 편지를 들고 애프터라이트 하우스로 들어섰다. | The address existed. The sender did not.<br>On my last delivery of the day, I carried the letter into Afterlight House. |
| 02 · `episode.across_the_threshold` | You / 나 · walk | 온실에서 따뜻한 공기가 흘러나왔다. 문턱을 넘는 순간, 봉투에 붙은 유리 봉인이 새하얗게 빛났다. | Warm air drifted out of the conservatory. As I crossed the threshold, the glass seal on the envelope flashed white. |
| 03 · `episode.eyes_on_nami` | Nami / 나미 · eye · Waking Eye-Opening | 천천히. 꽤 눈부셨지?<br>나 보여? 다행이다. 애프터라이트 하우스에 온 걸 환영해. | Easy. That was quite a flash.<br>Can you see me? Good. Welcome to Afterlight House. |
| 04 · `episode.no_ordinary_post` | Nami / 나미 · dialogue · wide · sweat_drop  · Stepped Transform Loop | 난 나미. 이 집을 돌보고 있어.<br>이상한 우편물은 유즈 담당인데… 네 편지가 방금 복도를 통째로 밝히려 들더라. | I'm Nami. I look after the house.<br>Yuzu handles the odd mail—and yours just tried to light up my hallway. |
| 05 · `episode.a_glass_record` | Yuzu / 유즈 · dialogue · close | 기억 유리네. 정해진 장소에 닿을 때까지 새겨진 메시지를 보관하지.<br>주소는 우리 독서실이야. | Memory glass. It holds a message until it reaches the right place.<br>The address says our reading room. |
| 06 · `episode.no_forwarding_address` | Nami / 나미 · dialogue · wide · Sigh Puff after reveal | 그럴 줄 알았어. 하필 오늘 아침에 봉쇄한 그 방이네.<br>부엌으로 오면 어디 덧나나? | Of course it does. The one room we sealed this morning.<br>Couldn't it have wanted the kitchen? |
| 07 · `episode.courier_offer` | Nami / 나미 · choice · wide | 저 봉인, 아직 우리한테 할 말이 있나 봐.<br>배달원님, 조금 더 남아서 같이 해결해 줄래? | That seal isn't done with us.<br>Staying for the trouble, courier? |
| 07a · `episode.choice.help_first` | You / 나 · help_first · option | 도울게. 어디부터 손대면 돼? | I'll help. Point me at the trouble. |
| 07b · `episode.choice.tea_first` | You / 나 · tea_first · option | 비상근무하면 차도 주는 거지? | Does emergency duty come with tea? |
| 08a · `episode.courier_reply.help_first` | Nami / 나미 · help_first reply · dialogue · close · sparkle · Sigh Puff after reveal | 고마워. 우편물이랑 나 혼자 씨름해야 하나 했네.<br>옆에 있어 줘. 뭘 원하는지 같이 알아보자. | Thanks. I thought I'd have to argue with the mail alone.<br>Stay close. We'll find out what it wants. |
| 08b · `episode.courier_reply.tea_first` | Nami / 나미 · tea_first reply · dialogue · close · sparkle · Sigh Puff after reveal | 차에 비스킷까지. 좋아, 우리 비상예산이 딱 들켰네.<br>해결만 도와주면 네 몫은 내가 지켜 줄게. | Tea and biscuits. Fine, you've found my emergency budget.<br>Help us untangle this, and I'll guard your share. |
| 09 · `episode.one_more_minute` | You / 나 · monologue | 편지만 전하고 돌아갈 생각이었다.<br>그런데 유리 봉인은 여전히, 조금씩 더 밝아지고 있었다. | I had planned to hand it over and leave.<br>Then I noticed the seal was still getting brighter. |
| 10 · `episode.a_second_line` | Yuzu / 유즈 · dialogue · close · confusion | 주소 아래에 경고문이 있어. 너무 희미해서 안 읽혀.<br>나미, 창가 쪽으로 들어 봐. | There's a warning under the address. Too faint to read.<br>Nami, hold it near the window. |
| 11 · `episode.caught_in_the_light` | Nami / 나미 · detail | 자. 이제 빛을 받네.<br>봉투는 그대로 들고 있어. 유즈, 글자 좀 보이니? | Here. The light's catching it now.<br>Don't move the envelope. Yuzu, can you make out the words? |
| 12 · `episode.the_warning` | Yuzu / 유즈 · dialogue · solo · close · surprise · Background Blackout | 유리 속에 든 건 기억이 아니야. 초대장이지.<br>옛 기록에는 그 발신자를 ‘주인 없는 이름의 문지기’라고 부르더라. | This is no memory in the glass. It's an invitation.<br>The old records call its sender the Keeper of Unclaimed Names. |
| 13 · `episode.verified_trouble` | Nami / 나미 · dialogue · wide | 그럼 거절이야. 아주 단호하게.<br>그리고 그 봉인은 아무도 열지 마. 주소 문제는 다 같이 해결하자. | Then we decline. Firmly.<br>And nobody opens that seal. We deal with the address together. |
| 14 · `episode.keep_the_wards_lit` | Yuzu / 유즈 · dialogue · close | 역의 결계가 양쪽을 갈라 놓고 있는데, 등 두 개가 꺼져 가고 있어.<br>선을 고치면 문지기가 우리한테 닿으려고 쓴 주소도 사라져. | The station wards keep both sides apart. Two of their lamps are failing.<br>If we repair the line, the Keeper loses the address it used to reach us. |
| 15 · `episode.divide_the_work` | Nami / 나미 · dialogue · wide | 레버는 내가 맡을게. 유즈, 세나랑 독서실로 가.<br>그리고 배달원님, 편지는 계속 들고 있어. 아직 할 일이 남았거든. | I'll take the lever. Yuzu, get Sena to the reading room.<br>And courier—keep that letter with you. We're not done with it. |
| 16 · `episode.sena_takes_over` | Sena / 세나 · handoff · walk_away · wide · sparkle | “봉쇄된 방”이라길래 달려왔어.<br>제발 공구함으로 해결할 수 있는 종류의 비상상황이라고 해 줘. | I heard "sealed room" and came running.<br>Please tell me this is the kind of emergency that needs a toolbox. |
| 17 · `episode.the_useful_kind` | Yuzu / 유즈 · dialogue · wide · Quick Approach toward Sena · sweat_drop | 그 쓸모 있는 종류 맞아. 역으로 가는 전력을 우회시킬 거야.<br>결계등이 깜빡거리지 않게 되면 그때 네 작품을 감상해. | The useful kind. We're rerouting the station feed.<br>You can admire your work after the lamps stop flickering. |
| 18 · `episode.reading_room` | You / 나 · establish | 봉인이 풀린 문 너머로 독서실이 모습을 드러냈다.<br>오후의 햇빛이 탁자에 길게 걸렸고, 책장 너머에서는 경고등이 깜박였다. | The reading room waited behind its unsealed door.<br>Afternoon light lay across the tables; a warning lamp blinked beyond the shelves. |
| 19 · `episode.a_live_line` | Sena / 세나 · dialogue · wide | 패널 열었어. 리코도 결계 감시기를 들고 역에서 돌아왔네.<br>배달원님, 봉인은 내 공구랑 좀 떨어뜨려 줘. 마법 안 걸린 게 쓰기 편하거든. | Panel's open. Riko is back from the station with the ward monitor.<br>Keep that seal off my tools, courier. I like them unenchanted. |
| 20 · `episode.riko_on_the_glass` | Riko / 리코 · dialogue · restless_bounce · wide · Cast Pan to Riko · anger_vein  · Stepped Transform Loop | 리코야. 승강장 비우고 곧장 왔어.<br>남쪽 결계는 아직도 박수라도 받고 싶은지 계속 깜박이네. 그쪽 계획은? | Riko. I cleared the platform and came straight here.<br>The south ward is still blinking like it wants applause. What's your plan? |
| 21 · `episode.two_green_lamps` | Yuzu / 유즈 · dialogue · wide · Cast Pan to Yuzu | 나미가 우회 회로를 여는 중이야. 감시기의 초록 등 두 개를 봐.<br>둘 다 계속 켜져 있으면 세나가 손상된 선을 끊을 수 있어. | Nami is opening the bypass. Watch the two green lamps on your monitor.<br>When both hold steady, Sena can disconnect the damaged feed. |
| 22 · `episode.waiting_for_the_signal` | Riko / 리코 · dialogue · wide · Cast Pan to Riko · sweat_drop | 하나는 초록. 복귀 통신로는 아직 잠겨 있어.<br>배달원님, 편지 들고 중계 연구실에 가 봐. 전용 회선으로 에이라가 읽어 줄 거야. | One green. The return channel is still locked.<br>Courier, take the letter into the relay laboratory. Eira can read it on the private line. |
| 23 · `episode.hold_the_message` | You / 나 · monologue | 독서실 너머 중계 연구실에서는 기억 유리 장비가 낮게 울리고 있었다.<br>작업대 위에 테두리가 있는 화면이 떠오른다. 그 안의 여자가 고개를 든다. | Beyond the reading room, the relay laboratory hums around its memory-glass instruments.<br>A framed display floats above the bench. The woman on it looks up. |
| 24 · `episode.eira_on_the_relay` | Eira / 에이라 · projection · wide · Hologram | 중앙 교환소에서 중계 기술을 연구하는 에이라야.<br>화면이 깜빡여도 놀라지 마. 회선이 길어서 그래. 귀신은 아니니까. | I'm Eira, a relay researcher at the central exchange.<br>Don't startle if my picture flickers. That's the long line, not a haunting. |
| 25 · `episode.a_voice_in_the_glass` | You / 나 · dialogue · Hologram held | 그거 다행이네요. 이 편지가 자꾸 제 주소를 바꾸거든요.<br>복귀 통신로가 원래 어디로 이어져야 하는지 알 수 있을까요? | That is reassuring. The letter has been changing its own address.<br>Can you tell us where the return channel is supposed to go? |
| 26 · `episode.the_return_channel` | Eira / 에이라 · dialogue · close · Hologram held | 손상된 결계를 거꾸로 통과하고 있어. 여기서 잠금을 풀 수 있겠어.<br>세나에게 전해 줘. 남쪽 공급선부터 빼고, 그다음 복귀선. 초록 등 두 개가 안정될 때까지 기다려. | It runs backwards through the damaged ward. I can release it from here.<br>Tell Sena: south feed out, then return. Wait for two steady green lamps. |
| 27 · `episode.one_private_question` | You / 나 · dialogue · Hologram held | 그 안에 든 초대장은요?<br>누군가 제 대답을 기다리고 있는 건가요? | And the invitation inside it?<br>Is someone waiting for me to answer? |
| 28 · `episode.follow_the_pulse` | Eira / 에이라 · dialogue · Hologram held | 초대장을 받았다고 손님이 되는 건 아니야. 넌 가겠다고 한 적 없잖아.<br>봉인이 널 끌어당기면, 실제로 네 곁에 있는 사람의 온기를 따라가. | An invitation doesn't make you anyone's guest. You haven't agreed to go.<br>If the seal pulls, follow the warmth of someone who is actually beside you. |
| 29 · `episode.eira_signs_off` | Eira / 에이라 · dialogue · wide · Hologram held | 됐어. 통신로 열렸고, 나머지는 네 친구들 몫이야.<br>평범한 날에도 전화해, 배달원님. 다음 인사는 대피 방송 없이 나누고 싶네. | There. The channel is open; the rest is in your friends' hands.<br>Call again on an ordinary day, courier. I'd like an introduction without an evacuation. |
| 30 · `episode.relay_return` | You / 나 · monologue · transmission ends | 떠 있던 화면이 꺼졌다. 문밖에서는 리코가 경고등이 깜빡이는 횟수를 세고 있었다.<br>에이라의 작업 순서와 잊지 말아야 할 경고 하나를 안고, 일행에게 돌아갔다. | The floating display goes dark. Beyond the door, Riko is counting the lamp flashes.<br>I return to the others with Eira's instructions, and one warning I intend to remember. |
| 31 · `episode.follow_the_diagram` | Sena / 세나 · dialogue · close | 에이라가 통신로 열어 줬어? 좋아. 편지는 거기 들고 있어. 안쪽 선들이 이 단자랑 맞아.<br>유즈, 확인해 줘. 남쪽 공급선, 그다음 복귀선. | Eira cleared the channel? Good. Hold the letter there; its lines match these terminals.<br>Yuzu, check me: south feed, then return. |
| 32 · `episode.checked_twice` | Yuzu / 유즈 · dialogue · wide | 남쪽 공급선, 그다음 복귀선. 맞아.<br>리코가 신호할 때까지 손 떼고 있어. 숨 한 번 고를 시간은 있으니까. | South feed, then return. That's correct.<br>Hands off until Riko gives the signal. We can afford one careful breath. |
| 33 · `episode.the_signal` | Riko / 리코 · dialogue · close · surprise | 둘 다 초록. 에이라의 통신로도 나미의 우회 회로도 안정적이야.<br>그대로… 그대로… 지금이야, 세나! | Two green. Eira's channel and Nami's bypass are holding.<br>Steady... steady... now, Sena! |
| 34 · `episode.the_reroute` | Sena / 세나 · dialogue · wide · Radial Sprite Burst | 남쪽 공급선 분리. 복귀선 연결.<br>됐다. 아주 훌륭한 수리야. 폭발도 단 한 번 없었고. | South feed out. Return connected.<br>There. A perfectly respectable repair, with absolutely no explosions. |
| 35 · `episode.the_seal_answers` | Nami / 나미 · dialogue · wide | 결계등 두 개 다 초록색이네. 역시 해낼 줄 알았어.<br>편지는 내가 받을게—잠깐. 봉인이 왜 다시 뜨거워지지? | Two green lamps. I knew you could do it.<br>Let me take the letter—wait. Why is the seal getting warm again? |
| 36 · `episode.scarlet_pressure` | You / 나 · rift · wide · Heat Haze 0.8 · Barrier 0.88 · Scene Corruption 0.68 · Impact Shake | 손바닥 위의 봉인이 뜨거워진다.<br>방이 숨을 들이마신 채 멈춘 것처럼, 공기가 안쪽으로 휘어진다. | The seal warms against my palm.<br>The air bends inward, as if the room has taken a breath and forgotten to let go. |
| 37 · `episode.between_addresses` | You / 나 · monologue | 있을 수 없는 한 걸음 동안, 바닥이 사라졌다.<br>다시 발이 닿았을 때, 내 손을 잡고 있던 온기만 돌아오지 않았다. | For one impossible step, there is no floor.<br>Then my feet find it again. The hand holding mine does not. |
| 38 · `episode.the_unlit_house` | You / 나 · eye · Waking Eye-Opening (background only) · wide · Heat Haze 0.92 · Scene Corruption 0.9 · Area Corruption | 사슬로 잠긴 철문들이 어둠 속으로 끝없이 이어진다.<br>바닥의 쇠창살 틈으로 열기가 새어 나온다. 저 끝의 붉은 창은 하늘도 없이 타오른다. | A hall of chained iron doors stretches into the dark.<br>Heat seeps through the floor grilles. At the far end, a red window burns without a sky. |
| 39 · `episode.the_keeper` | The Keeper / 문지기 · dialogue · wide · Heat Haze 0.85 · Barrier 0.32 · Scene Corruption 0.85 · Actor Corruption · Impact Shake | 드디어. 존재하지 않는 주소까지 건너오는 배달부라.<br>나는 문지기다. 네가 끝내 찾지 못한 모든 문 사이에, 지금 네가 서 있지. | At last. A courier who can cross an address that does not exist.<br>I am the Keeper. You are standing in the space between every door you failed to find. |
| 40 · `episode.the_price_of_return` | The Keeper / 문지기 · dialogue · close · Heat Haze 0.8 · Barrier 0.28 · Scene Corruption 0.82 · Actor Corruption | 내 장부에 네 이름을 남기면 돌아갈 문을 열어 주마.<br>서명 하나. 문 하나의 값으로는 싸지 않느냐? | Leave your name in my ledger, and I will open the way home.<br>One signature. A small price for a door. |
| 41 · `episode.a_name_is_not_consent` | You / 나 · dialogue · wide · Heat Haze 0.9 · Barrier 0.42 · Scene Corruption 0.88 · Actor Corruption · Impact Shake | 보낸 사람도 없는 편지를 보내 놓고요.<br>그쪽 이름부터 알려 주기 전까지는, 제 이름은 제가 갖고 있겠습니다. | You sent a letter with no sender.<br>I think I will keep my name until you offer yours. |
| 42 · `episode.the_room_refuses` | You / 나 · rift · wide · Heat Haze 1.0 · Barrier 0.97 · Scene Corruption 1.0 · Actor Corruption · Impact Shake | 문지기의 미소가 날카로워졌다. 잠긴 문들이 일제히 떨린다.<br>무언가가 공기 저편에서 이쪽을 누르고 있다. | The Keeper's smile sharpens. Every locked door shudders at once.<br>Something presses against the far side of the air. |
| 43 · `episode.nami_beyond_the_wall` | Nami / 나미 · dialogue · Heat Haze 0.75 · Barrier 0.38 · Scene Corruption 0.8 · Actor Corruption | 들려? 거기서 뭘 묻든 대답하지 마.<br>봉인을 꽉 쥐어. 따뜻한 쪽을 따라와. 나 아직 안 놓았어. | Can you hear me? Do not answer anything in there.<br>Squeeze the seal. Follow the warmth. I am still holding on. |
| 44 · `episode.follow_the_warmth` | You / 나 · dialogue · Heat Haze 0.62 · Barrier 0.58 · Scene Corruption 0.68 · Area Corruption | 찾았다. 바닥 밑의 열기와는 다른, 부드러운 온기.<br>나는 문지기에게서 등을 돌리고 나미의 손길을 따라간다. | There. A gentle warmth, nothing like the heat beneath this floor.<br>I turn away from the Keeper and follow Nami's grip. |
| 45 · `episode.the_return` | You / 나 · rift · wide · Heat Haze 0.85 · Barrier 0.95 · Scene Corruption 0.82 · Impact Shake · effects fade out | 끝없는 전당이 한 줄기 붉은 빛으로 접혔다.<br>그러고는 독서실 바닥이 내 발을 받아 주었다. | The endless hall folds into a line of red light.<br>Then the reading-room floor rises to meet my feet. |
| 46 · `episode.a_hand_to_hold` | Nami / 나미 · eye · Waking Eye-Opening | 눈앞에 나미가 있다. 내게 내민 손만이 이상할 만큼 선명했다. | Nami is right in front of me. Her outstretched hand is the only thing that feels real. |
| 47 · `episode.a_touch_that_stays` | Nami / 나미 · contact · fingertip confirmation | 손끝만, 여기.<br>편지가 또 널 끌고 가면, 이번엔 내가 더 세게 잡아당길 거야. | Just your fingertip. Right here.<br>If that letter pulls you away again, I'll pull you back. |
| 48 · `episode.only_a_second` | Nami / 나미 · dialogue · wide · Sigh Puff after reveal | 일 초였어. 딱 일 초 동안 사라졌다고!<br>다음에 편지가 널 훔쳐 가려고 하면, 적어도 나도 같이 가게 해 줘. | You were gone for a second. One second!<br>Next time a letter tries to steal you, at least let me come along. |
| 49 · `episode.steady_at_last` | Yuzu / 유즈 · dialogue · close | 주소가 닫히기 직전에 널 끌어당긴 거야. 마지막 발악이었어.<br>이제 경고등은 꺼졌어. 리코, 결계는 괜찮아? | It pulled you through just before the address closed. One last attempt.<br>The warning lamp is off now. Riko, does the ward hold? |
| 50 · `episode.all_clear` | Riko / 리코 · dialogue · wide · Sigh Puff after reveal | 밝고 안정적이야. 역에서도 이상 없대.<br>세나가 이 수리에 자기 이름 붙이기 전에 감시기 좀 내려놔도 될까? | Bright and steady. The station has given the all-clear.<br>Can we put this monitor down before Sena names the repair after herself? |
| 51 · `episode.riko_signs_off` | Riko / 리코 · exit · wide | 내가 찻물 올리고 올게.<br>그리고 우리 배달원님 보내지 마. 경고등 안 보고 제대로 인사할 차례잖아. | I'm putting the kettle on.<br>And don't lose our courier. I still owe him a hello without warning lamps. |
| 52 · `episode.a_modest_name` | Sena / 세나 · dialogue · wide · Sweat Drop Fall after reveal | "세나 방식"이면 아주 겸손한 이름이었을 텐데.<br>그래도 차 한 잔에 우리 모두 이름을 지켰으니, 그걸로 만족할게. | "The Sena Method" would have been very modest.<br>But I will settle for tea, and all of us keeping our names. |
| 53 · `episode.back_to_the_house` | You / 나 · establish | 돌아왔을 때는 온실 유리창이 금빛으로 물들어 있었다.<br>리코는 벌써 탁자에 앉아 첫 번째 비스킷을 슬쩍 집어 가고 있었다. | By the time we returned, the conservatory windows had turned gold.<br>Riko was already at the table, stealing the first biscuit. |
| 54 · `episode.everyone_accounted_for` | Nami / 나미 · dialogue · wide · sparkle  · Stepped Transform Loop | 우회 회로 잠금 확인. 전원 무사 귀환.<br>배달원님도 포함이야. 누가 또 일 맡기기 전에 앉아. | Bypass secured. Everyone accounted for.<br>That includes you, courier. Sit down before somebody gives you another job. |
| 55 · `episode.a_proper_hello` | Riko / 리코 · dialogue · close · Sweat Drop Fall after reveal | 리코야. 이번에는 비상사태 빼고 다시 인사할게.<br>날 잘 골랐네. 보통 손님들한테는 차부터 대접하고 소동을 보여 주거든. | Riko. Let's try that again, with fewer emergencies.<br>You picked a good day to visit. Usually we make guests wait until after tea for the trouble. |
| 56 · `episode.the_unsigned_entry` | Yuzu / 유즈 · dialogue · wide · confusion | 내일 방문 장부에 한 줄이 더 생겼어. 도착 시각만 있고 이름은 없어.<br>이 잉크는 따뜻해. 문지기가 쓴 건 아닌 것 같아. | Tomorrow's visitor ledger has a new line. An arrival time, but no name.<br>This ink is warm. I do not think the Keeper wrote it. |
| 57 · `episode.the_next_arrival` | You / 나 · ending | 결계는 버텼다. 편지는 끝내 서명되지 않았다.<br>내일이면 다른 누군가가 문을 두드릴 것이다. 이번에는 함께 열어 주기로 했다. | The wards hold. The letter stays unsigned.<br>Tomorrow, someone else will knock. This time, we will open the door together. |

## Dedicated scene labels

| Stable key | Korean | English |
| --- | --- | --- |
| `guest.eira.name` | 에이라 | Eira |
| `location.relay_alcove` | 중계 연구실 | Relay laboratory |
| `episode.place.beyond` | 주인 없는 이름의 전당 | Hall of Unclaimed Names |
| `location.keeper_hall` | 주인 없는 이름의 전당 | Hall of Unclaimed Names |

## Retained study fixtures

Non-episode text keys continue to supply the independent Presentation Lab
studies. Changing an `episode.*` line does not rewrite those samples. The
Hologram remains a reusable visual treatment; Eira, the floating display, and
the private relay laboratory call are this game's cast and story decisions,
not requirements of that effect. The stable background ID `relay_alcove`
continues to identify the revised laboratory setting.
