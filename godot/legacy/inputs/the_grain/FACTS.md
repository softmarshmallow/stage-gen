# Episode One — the fact ledger

Status: **fixed by the lead at 05:48 on 2026-09-03, first thirty minutes of Pilot 01.**

Every boolean that crosses a beat boundary in Episode One, with its canonical
`lower_snake_case` identifier. **These ids are frozen.** The case declares every one of
them once; each scenario declares as a flag only the ones it sets or reads; each room
names them in `set_flag` effects. The consumer's autosave keys on them, so a rename after
the first commit costs a save-compatibility break — if a writer needs an id this table
does not have, they add a row here and tell the lead, they do not invent one privately.

Derived from the board table in `story/snapshot-2026-09-03/adaptation/episode-01-the-winter-room.md`.

Column `how` is the outline's own vocabulary: **look** (the player chose to look),
**attention** (the player watched this strand and not another), **heard** (said in the
room, unmissable), **given** (the scene hands it over), **act** (the player did
something), **checkpoint** (what Henry chose to say to Ward).

## Movement II — the motor court, before (`e1_motor_court`, room)

| id | how | source | what it buys |
|---|---|---|---|
| `window_before` | look | Sc2 | six figures, an empty seventh place, the paper moon whole. Ward: it was whole at a quarter to eight |
| `gallery_open` | look | Sc2 | the short black rectangle already open above the moon. Carried to Sc9 |
| `chalk_and_scissors` | look | Sc2 | a seamstress's chalk and scissors on the display floor. Nothing tonight |
| `rang_the_bell` | exit | Sc2 | the room's win flag. Set by ringing the service bell |

## Movement II — the way in (`e1_way_in`, scenario)

| id | how | source | what it buys |
|---|---|---|---|
| `suitcase_unopened` | given | Sc2 | one unopened suitcase beside the service bar |
| `place_card_moved_twice` | given | Sc2 | Edwin: "Miss Shaw has moved your place card twice." |

## Movement III — the table (`e1_table`, scenario)

| id | how | source | what it buys |
|---|---|---|---|
| `eighth_card` | look | Sc3 | seven names face outward; the eighth is turned toward Lydia. Lets "Her reaction said no" be report, not guess |
| `would_you_have_come_first` | heard | Sc3 | Lydia to Ruth. The first of the three countings of "Would you have come?" |
| `hand_in_the_door` | fixed | Sc3 | Henry stops the closing lift door. Not a choice. Ward will ask why; the answer is "I don't know." |
| `ruth_roll` | attention | Sc4 | Ruth tears a roll and puts half on Paul's plate, and knows it only when her hand is empty |
| `marian_salt` | attention | Sc4 | Marian's salt, taken and not used, set down by Robert's hand |
| `dark_blue_door` | attention | Sc4 | dark blue, a house, "Mine, beginning Thursday" |
| `pocketknife_lent` | act | Sc5 | Henry offers his pocketknife for Paul's string; Paul closes it and returns it |
| `ruth_knife_on_plate` | look | Sc5 | Ruth's knife touches her plate when Lydia says June's sentence. Opens "June's sentence" at coffee |
| `brass_key_after_dessert` | look | Sc5 | Edwin lays the brass key beside Paul's fork: "After dessert." The key's origin, for Ward |
| `envelope_hear_it` | heard | Sc5 | the cream envelope, Nell's name upside down, "Hear it," "Then put the letter away." |

## Movement IV — coffee (`e1_coffee`, scenario)

| id | how | source | what it buys |
|---|---|---|---|
| `bar_said_it_badly` | attention | Sc6 | "—if I say it badly." "Then you said it." "Not this one." Ruth's account already half known |
| `paul_cup_for_edwin` | attention | Sc6 | Paul pours a cup and leaves it beside Edwin's hand. His last kindness |
| `saucers_crossed_out` | attention | Sc6 | the place cards fanned; a number in green ink crossed out twice; the card torn once under a saucer |
| `roof_panel_i_heard` | attention | Sc6 | the orange ice repeated for Nell. "I heard." "Good." Nell and Paul's last exchange |
| `lydia_alone_pile` | attention | Sc6 | Lydia at the emptied table, gathering nothing into a very small pile |
| `ruth_two_fingers` | look | Sc6 | Ruth pushes the rising envelope back down with two fingers as Paul passes. Corroborates that it was in his pocket when they went down |
| `asked_paul_sentence` | act | Sc6 | Henry asked Paul about June's sentence and was deflected. Ruth said no; he asked anyway |
| `indicator_at_three` | look | Sc6 | Henry watches the floor indicator descend to three. The last he saw of them |
| `lift_rising_seen` | look | Sc7 | the service lift begins to rise; Henry looks at the indicator, Nell does not |
| `handbag_under_arm` | look | Sc7 | she has her handbag under her arm instead of on it |
| `smear_on_shoe` | look | Sc7 | a pale smear along the outside of one shoe. Henry takes it for dust from the carton |
| `key_returned_to_edwin` | given | Sc7 | Ruth places the brass key beside Edwin's hand |
| `coffee_not_drunk` | look | Sc7 | she touches the coffee to her mouth and sets it down. The model exchange with Ward |
| `paul_not_to_wait` | heard | Sc7 | "He said not to wait." — said to Nell |
| `paul_needed_to_think` | heard | Sc7 | "He said he needed to think." — said to Henry, the same minute |

## Movement V — the window (`e1_window`, room)

| id | how | source | what it buys |
|---|---|---|---|
| `window_changed` | look | Sc9 | the paper moon split and sagged inward |
| `saw_body` | look | Sc9 | the man beneath it, a shoe in the light, one hand palm down. **Required by the exit** |
| `stage_door_locked` | Bell | Sc9 | locked; Bell opened it far enough to see a face, locked it, called upstairs |
| `touched_neck` | act | Sc9 | two fingers under the jaw. What Henry touched, for the officer's question |
| `carton_on_gallery` | look | Sc9 | the shallow carton still on the gallery beside the open rail |
| `marks_under_lip` | look | Sc9 | pale horizontal marks beneath the steel lip |
| `scrape` | look | Sc9 | one long scrape across the painted wall, lower down |
| `red_button` | look | Sc9 | a red button mounted beside the open rail. Ward will order it traced |
| `heading_int_bedroom` | look | Sc9 | the torn typed piece under his right hand; the top edge reads INT. BEDROOM — NIGHT. Not a letter |
| `pulled_the_paper` | act | Sc9 | Henry pulled the paper free. **He does not, in the novel.** One line of new narration in Henry's voice; sets `touched_more_than_said` |
| `touched_more_than_said` | act | Sc9 | Henry touched something he will have to account for |
| `access_door_unlocked` | Bell | Sc9 | DISPLAY ACCESS, "not while a window is unfinished" |
| `whiting_on_treads` | look | Sc9 | something white tracked down the lower treads of the enclosed stair |
| `bell_key_path` | Bell | Sc9 | "He needed both hands, so he gave her the lift key." |
| `bell_in_receiving` | Bell | Sc9 | "I went into receiving to make the closing call." |
| `court_door_never_opened` | Bell | Sc9 | "Did you open the motor-court door for him?" "No." |
| `left_the_room` | exit | Sc9 | the room's win flag. Set by returning to the lift. **Requires `saw_body`** |

## Movement VI — the statement (`e1_statements`, scenario)

What Henry chose to say. Each beat sets exactly one of a told / thought / kept triple.

| id | beat | what it means |
|---|---|---|
| `told_reaction` | Ruth and the card | "Her reaction said no," given as report (needs `eighth_card`) |
| `thought_reaction` | Ruth and the card | the same, given as a guess |
| `kept_reaction` | Ruth and the card | nothing given |
| `told_key_origin` | the key | Edwin, before coffee, "after dessert" (needs `brass_key_after_dessert`) |
| `kept_key_origin` | the key | only that Paul had it |
| `told_coffee` | her return | "She didn't drink the coffee." (needs `coffee_not_drunk`) |
| `thought_frightened` | her return | "Yes." |
| `kept_frightened` | her return | "I don't think so." |
| `told_paul_words` | what Paul said | both "not to wait" and "needed to think" (needs both) |
| `told_paul_words_one` | what Paul said | one of the two |
| `kept_paul_words` | what Paul said | neither |
| `told_shoe` | the shoe | "There was dust on her shoe from the carton." (needs `smear_on_shoe`) |
| `kept_shoe` | the shoe | nothing |
| `offered_sentence` | June's sentence | Henry offers it unasked (needs `ruth_knife_on_plate`) |
| `offered_envelope` | the envelope | Nell's name upside down, "Hear it" (needs `envelope_hear_it`) |
| `ward_regard` | Ward's close | set by the close's branch when enough was given as seen. **The episode's verdict** |
| `told_ruth_after_one` | Sc13 | what Henry gave Ruth beside the passenger elevators: "That you didn't drink your coffee." It breaks Ward's instruction and tells her he watches her cup |
| `told_ruth_what_i_saw` | Sc13 | **added by writer B, 2026-09-03.** The middle answer at the elevators, "What I saw." Sc13 offers three and the ledger carried one id; the novel's deflection records nothing, and the other two are different things for Thursday to answer |
| `told_nell_in_the_court` | Sc14 | what Henry said to Nell about the window |
| `ruth_said_needed_time` | Sc13 | Ruth's third account: "He said he needed time." One word off what she said upstairs. Henry may notice or not |
| `would_you_have_come_second` | Sc14 | Lydia to Nell, in the motor court. **The second counting.** Nell's reply — "You already used that excuse tonight." — is the count being kept out loud, so the two cannot be collapsed |

## Ward's close

The close branches on what Henry gave **as seen** rather than as opinion. The beats that
carry weight, from the outline: the coffee, the shoe, what Paul said, and the stage door.
Write the threshold as the specific combinations that matter, not as an enumeration of
all of them:

```renpy
label ward_close:
    if told_coffee and told_shoe and told_paul_words:
        jump ward_close_kept_looking
    if told_coffee and told_shoe:
        jump ward_close_regard
    if told_coffee and told_paul_words:
        jump ward_close_regard
    jump ward_close_plain
```

`ward_close_kept_looking` and `ward_close_regard` both `set ward_regard`;
`ward_close_plain` does not.

## Rules

- An id appears in exactly one "set by" movement. Later movements read it.
- A fact a scenario reads but no earlier beat can set must still be declared, and the
  case proof will require it to default to false. Facts are false until set.
- Nothing else crosses a beat boundary. No inventory. The pocketknife is a fact, not an item.

## Amendment, 06:22 — "Would you have come?" is counted twice in Episode One

Added after QA's line audit. The sentence appears **twice** inside this episode's span,
both times spoken by Lydia: to Ruth in Sc3 (`chapter-02:425`) and to Nell in Sc14
(`chapter-06:471`). This ledger originally declared only the first.

It is not a repetition to tidy. Nell answers the second with "You already used that excuse
tonight." — the count is being kept inside the fiction, by a character, out loud. Collapsing
the two, or dropping Sc14's, would delete a line that only works because the earlier one
happened. `would_you_have_come_second` is therefore a fact in its own right, written by
`e1_statements`, and the third counting belongs to a later episode.

## Amendment, 06:22 — Ward's line is "That isn't what I asked."

`fixed-sentences-glossary.md` renders Ward's line as "That's not what I asked." The novel
(`chapter-06-names-and-addresses.fountain:310`) has **"That isn't what I asked."**, and so
do the brief and the episode outline. The novel is the authority; the glossary is a
translation aid and is wrong here. Filed for the director in `adaptation/returns.md`.
