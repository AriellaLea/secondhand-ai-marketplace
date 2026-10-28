# tests.md – Second-Hand Marketplace with AI Agent

Oct 22, 2026 · @Ariella

## 1. Approach

Every test checks one rule from the PRD or one design choice from architecture.md, so a passing test proves a requirement is met.

- **IDs:** a test is named after its feature, for example T-F2-1 for the first scenario of F2. Sections 3 to 5 use their own prefixes (T-ROLE, T-ARCH, T-AGENT).
- **Method:** run the app and the agent locally, follow each scenario by hand, and tick the result. Where easy, the code agent also writes automated tests with pytest.
- **Test data:** two seller accounts, one moderator account created by script, and about 30 sample listings already loaded in the vector database.
- **Result column:** each row ends with a Pass / Fail box to fill in before the submission on 30 October.

## 2. Feature tests

| ID | Feature | Scenario | Expected result | Result |
| --- | --- | --- | --- | --- |
| T-F1-1 | F1 Authentication | A new visitor registers with a valid email and password | A seller account is created and saved in the database, and the user can log in | ☐ |
| T-F1-2 | F1 Authentication | Login with a wrong password | Login is refused with a clear message | ☐ |
| T-F1-3 | F1 Authentication | A moderator logs in on the same login page | Access to moderator pages only | ☐ |
| T-F1-4 | F1 Authentication | Open a protected page without logging in | Redirect to the login page | ☐ |
| T-F2-1 | F2 Publish listing | A seller submits title, description, price and category | The listing is saved with status Pending evaluation | ☐ |
| T-F2-2 | F2 Publish listing | Submit with a missing required field or a negative price | The form is refused and nothing is saved | ☐ |
| T-F3-1 | F3 Search | Search by a word from a title | Only matching listings are shown | ☐ |
| T-F3-2 | F3 Search | Filter by category | Only that category is shown | ☐ |
| T-F3-3 | F3 Search | Search with no match | An empty-result message is shown | ☐ |
| T-F4-1 | F4 Details | Open an approved listing | Title, description, price, category, seller name, date and status are shown | ☐ |
| T-F4-2 | F4 Details | A seller opens a listing that is not theirs and not approved | The listing is not shown in the seller's pages, so it cannot be clicked; opening its address directly is refused | ☐ |
| T-F4-3 | F4 Details | A seller opens their own rejected listing | The rejection reason is shown | ☐ |
| T-F4-4 | F4 Details | A moderator opens a listing that was created, evaluated and decided | The event history shows each event in order, with Israel date and time, who did it and the rejection reason; a seller never sees it | ☐ |
| T-F5-1 | F5 Listings table | A seller opens the table | Approved listings of others plus all of their own, with statuses, sorted from newest to oldest | ☐ |
| T-F5-2 | F5 Listings table | A moderator opens the table | All listings, including Pending evaluation | ☐ |
| T-F6-1 | F6 Dashboard | Open the dashboard | Counts by status and by category match the listings table | ☐ |
| T-F8-1 | F8 Moderator decision | A moderator approves an Evaluated listing | Status becomes Approved, an Approved event is recorded, and the seller sees it | ☐ |
| T-F8-2 | F8 Moderator decision | A moderator rejects an Evaluated listing with a reason | Status becomes Rejected, the reason is stored and a Rejected event is recorded | ☐ |
| T-F8-3 | F8 Moderator decision | A moderator opens a listing whose AI evaluation is still Pending | The Approve and Reject buttons are not displayed until the evaluation is finished; sending the action directly is refused | ☐ |
| T-F8-4 | F8 Moderator decision | Decide a listing that was already approved or rejected (or two moderators at once) | Refused with "the listing was already handled"; there is only one decision event | ☐ |
| T-F8-5 | F8 Moderator decision | A seller or a visitor sends approve or reject directly; a moderator sends a reason shorter than 5 characters | Refused, nothing saved; the moderator gets the form back with the error and the text typed | ☐ |
| T-F8-6 | F8 Moderator decision | Approve with Ollama stopped, then run `scripts/index_approved_listings.py` | The approval stands with a warning; the script adds the listing to the vector database | ☐ |

| T-MCP-1 | Phase 7 MCP tools | Call `get_pending_listing` with two Pending listings, then with the first one in `exclude_ids` | The oldest Pending listing is returned, then the next one; null when none is left; nothing is written | ☐ |
| T-MCP-2 | Phase 7 MCP tools | Call `save_assessment` with valid sub-scores, price range and similar ids | A Listing evaluated event with the agent as actor; an assessment with the computed score, recommendation and confidence; status Evaluated | ☐ |
| T-MCP-3 | Phase 7 MCP tools | Call `save_assessment` with a sub-score out of range, an empty reason, min above max, a new price outside the range, or only some of the three market prices | A tool error is returned; no event, no assessment, status stays Pending evaluation (no market price at all is accepted, with low confidence) | ☐ |
| T-MCP-4 | Phase 7 MCP tools | Call `save_assessment` twice for the same listing | The second call is refused; there is only one Listing evaluated event | ☐ |
| T-MCP-5 | Phase 7 MCP tools | Try to log in with the agent account | Login is refused | ☐ |
| T-MCP-6 | Phase 7 MCP tools | After `save_assessment`, open the listing as moderator and as seller | The moderator sees score, sub-scores, reasons, recommendation, confidence, price range and reasoning, and the score in the table; the seller sees none of it | ☐ |
| T-MCP-7 | Phase 7 MCP tools | Open the server in MCP Inspector and call both tools | Both tools are listed with their parameters and work over stdio | ☐ |

F7 (the AI agent) is tested in section 5.

## 3. Role and visibility tests

These check that the server enforces the rules, not only the screens: each case is also tried by typing the address directly in the browser.

| ID | Scenario | Expected result | Result |
| --- | --- | --- | --- |
| T-ROLE-1 | A seller views any page | The agent's assessment and reasoning never appear | ☐ |
| T-ROLE-2 | A seller types the address of the approve or reject action | Access is refused | ☐ |
| T-ROLE-3 | A seller looks at another seller's Pending or Rejected listing | It is not visible | ☐ |
| T-ROLE-4 | A moderator opens an Evaluated listing | Score, sub-scores, recommendation, price range and reasoning are shown, along with the Approve and Reject buttons | ☐ |
| T-ROLE-5 | Someone registers on the sign-up form | The account is always a seller, never a moderator | ☐ |

## 4. Architecture tests

These prove the three patterns are really used, which is what the oral exam asks about.

| ID | Pattern | Scenario | Expected result | Result |
| --- | --- | --- | --- | --- |
| T-ARCH-1 | Event Sourcing | Publish a listing, then look at the events table | A Listing created event exists with the seller as actor | ☐ |
| T-ARCH-2 | Event Sourcing | Follow one listing through evaluation and approval | Events appear in order: created, evaluated, approved | ☐ |
| T-ARCH-3 | Event Sourcing | Replay the events of a listing | The rebuilt status equals the status in the listings table | ☐ |
| T-ARCH-4 | Event Sourcing | Try to edit or delete an event through the app | No such route exists; events are only appended | ☐ |
| T-ARCH-5 | CQRS | Load search, details, table and dashboard pages | The events table is unchanged afterwards (queries write nothing) | ☐ |
| T-ARCH-6 | CQRS | Empty the listings table and rebuild it from the events | The read model is identical to before | ☐ |
| T-ARCH-7 | MVC | Read the code of one controller | It contains no SQL and no business rules, only a call to a handler and a view | ☐ |

## &#32;5. AI agent tests (F7)

| ID | Scenario | Expected result | Result |
| --- | --- | --- | --- |
| T-AGENT-1 | Start the agent while a listing is Pending evaluation | The agent picks it up without the web app being involved | ☐ |
| T-AGENT-2 | The agent finishes a listing | An assessment is saved with score, three sub-scores, recommendation, price range, similar listing ids, reasoning and confidence; status becomes Evaluated | ☐ |
| T-AGENT-3 | Publish a clearly fair listing and a clearly overpriced one | The fair one scores higher than the overpriced one, and the reasoning explains why | ☐ |
| T-AGENT-4 | Publish an item similar to one of the sample listings | That sample appears in the similar listing ids (RAG works) | ☐ |
| T-AGENT-5 | Disconnect the internet or remove the Tavily key | The listing stays Pending evaluation, no assessment is saved, and the agent evaluates it again later | ☐ |
| T-AGENT-6 | Stop the agent and publish two listings | Both stay Pending evaluation until the agent restarts, then both get evaluated | ☐ |
| T-AGENT-7 | Check the agent's actions after an evaluation | It never approved or rejected anything; the only new event is Listing evaluated | ☐ |
| T-AGENT-8 | The agent calls its tools | Both own MCP tools and the Tavily service are used, visible in the agent log | ☐ |
| T-AGENT-9 | The model reports a price that is not in the web results (for example a similar listing's price) | That price is ignored and logged; the new-item price is the median of the others | ☐ |
| T-AGENT-10 | No web price can be verified | The model is asked once to search again; if still none, the price vs market is 25 of 50 with "no prices were found on the internet" and the confidence is low | ☐ |
| T-AGENT-11 | The model searches the web without any word of the listing title | The search is refused and not counted; the model searches again | ☐ |

## 6. Non-functional checklist

One line per requirement of the assignment, to tick before submitting.

- [ ] Development is based on the MD documents (PRD, architecture, tests) kept in `docs/`
- [ ] At least one Skill from Skills.sh is installed and used
- [ ] At least one own Skill and one own Rule are written
- [ ] The web app runs on Flask
- [ ] The data is in a cloud database
- [ ] The data is vectorized in a vector database
- [ ] CQRS and MVC are visible in the code (T-ARCH-5 to T-ARCH-7)
- [ ] Event Sourcing is visible in the code (T-ARCH-1 to T-ARCH-4)
- [ ] At least two Tools are built through MCP Studio
- [ ] The agent uses a Deep Agent infrastructure with RAG and Tavily
- [ ] The agent runs as an independent process
- [ ] The interface is in Hebrew, right-to-left, and looks professional
- [ ] The GitHub repository contains everything, with no secrets committed

## 7. Demo script

A five-minute path through the app that shows every requirement in order.

1. Register a new seller and log in.
2. Publish a listing; show that its status is Pending evaluation.
3. Start the agent; show that it evaluates the listing on its own.
4. As the seller, show that the assessment is not visible.
5. Log in as the moderator; open the listing and show the score, reasoning and price range.
6. Approve the listing; show it in the seller's table and in the search results.
7. Open the dashboard and check the counts.
8. Open the events table and show the created, evaluated and approved events for that listing.
9. Show one controller, one command handler and one query handler to explain MVC and CQRS.
