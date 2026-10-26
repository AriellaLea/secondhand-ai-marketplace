# PRD – Second-Hand Marketplace with AI Agent

Oct 20, 2026 · @Ariella

## 1. Vision

Sellers publish second-hand listings, and an AI agent checks each listing before it goes live: is the price reasonable and is the description credible? A moderator reads the agent's assessment and approves or rejects the listing.

**Problem:** second-hand listings often have unrealistic prices and misleading descriptions, and checking each one by hand is slow and inconsistent.

**Value:**

- The moderator saves time, because the agent prepares a reasoned recommendation for every listing.
- The seller sees the status of their listing and, if it is rejected, the reason for the rejection.
- Buyers only see listings that have been checked.

## 2. Users and roles

There are two user types. The role is stored in the database and checked on every request.

| Role | Can do | Cannot do |
| --- | --- | --- |
| Seller | Publish listings; search and view approved listings from all sellers; follow the status of their own listings and, if one is rejected, see the reason for the rejection | See the agent’s assessment, approve or reject listings, see the dashboard, edit another seller’s listing |
| Moderator | See all listings, read the agent's assessment, approve or reject, view the dashboard | Publish listings in a seller's name |

Self-registration creates a seller account only. A moderator account is created directly in the database, so nobody can promote themselves to moderator.

## 3. Scope

**In scope:**

- Registration, login (authentication) and two roles: seller and moderator.
- Publishing a listing: title, description, price, category.
- Listing search, a listing detail page, a listings table and a dashboard.
- An AI agent that assesses each listing (web price check and comparison with similar listings).
- Moderator decision: approve or reject.

**Out of scope:**

- Payment or delivery.
- Messaging between buyer and seller.
- A mobile app.
- A third-party buyer account.

## 4. Features

A listing moves through these statuses: Pending evaluation → Evaluated → Approved or Rejected. Each feature has a user story and acceptance criteria that can be checked.

### F1 – Registration and login (authentication)

**User story:** As a seller or moderator, I want to log in with a username and password so that only I can reach the data I am allowed to see.

**Acceptance criteria:**

- Registration requires a name, an email and a password of at least 8 characters; an existing email cannot register twice.
- The password is stored as a hash, never as plain text.
- A valid login leads to the home page for the user's role; invalid credentials show an error message.
- A visitor who is not logged in cannot open any page except login and registration.
- A seller cannot open moderator pages, and a moderator cannot publish a listing.

### F2 – Publish a listing (data entry)

**User story:** As a seller, I want to publish a listing with a title, description, price and category so that I can sell my item.

**Acceptance criteria:**

- Only a logged-in seller can open the form.
- Title, description, price and category are required; the price is a positive number in shekels.
- After submission the listing is created with the status Pending evaluation and does not appear in public search.
- A "listing created" event is stored in the database (Event Sourcing).
- The seller sees a confirmation and is returned to their own listings list.

### F3 – Search listings

**User story:** As a user, I want to search listings by keyword and category so that I can quickly find what I am looking for.

**Acceptance criteria:**

- Search matches a keyword in the title and the description, and can be combined with a category filter.
- A logged-in seller sees only Approved listings in search results; a moderator sees listings in every status.
- If nothing matches, the page shows a "no listings found" message.
- Results appear within a few seconds on the demo data.

### F4 – Listing details

**User story:** As a user, I want to open a listing from the results and see all its details so that I understand what is offered.

**Acceptance criteria:**

- The page shows title, description, price, category, seller name, publication date and status.
- Only the moderator also sees the agent's assessment: score, market price range found, similar listings and the reasoning.
- A seller, including the one who published the listing, never sees the agent's assessment.
- The seller who published a rejected listing sees the reason for the rejection.
- A seller can open any Approved listing and their own listings in any status, but not another seller's listing that is not yet Approved. A moderator can open any listing.
- The moderator sees the event history of the listing (created, evaluated, approved or rejected).

### F5 – Listings table

**User story:** As a moderator, I want to see all listings in a table with the agent's score so that I can decide what to handle first. As a seller, I want a table of all my own listings and the approved listings of other sellers.

**Acceptance criteria:**

- Each row shows title, seller, category, price, status and publication date. The moderator's table also shows the agent score.
- The table includes listings the agent has not evaluated yet (status Pending evaluation). For these, the agent score column is empty and shows "Not evaluated yet".
- A moderator cannot approve or reject a listing that is still Pending evaluation (see F8).
- The table can be sorted by a column and filtered by status.
- Clicking a row opens the listing details (F4).
- A seller sees all of their own listings, in every status, plus the Approved listings of other sellers.

### F6 – Dashboard

**User story:** As a moderator, I want a general overview so that I know where to focus first.

**Acceptance criteria:**

- The dashboard shows the number of listings for each status: Pending evaluation, Evaluated, Approved, Rejected.
- The dashboard shows the number of listings for each category.
- The numbers are updated when a status changes, without a manual count.
- The dashboard is available to moderators only.

### F7 – AI agent assessment

**User story:** As a moderator, I want every listing to be checked automatically so that I receive a reasoned assessment and save time. Details are in section 6.

**Acceptance criteria:**

- The agent runs as an independent process, separate from the web server, and reads listings with the status Pending evaluation from the database.
- For each listing it creates an assessment: a score from 0 to 100 (see Scoring in section 6), a recommendation (approve, reject or manual review), the market price range found on the web, similar listings from the vector database and a short reasoning in Hebrew.
- The assessment is saved, the status changes to Evaluated and an "evaluated" event is stored (Event Sourcing).
- The agent never approves or rejects a listing by itself; the decision belongs to the moderator.
- If the internet search fails, the assessment states that the search did not work, and no market price is shown.

### F8 – Moderator decision

**User story:** As a moderator, I want to approve or reject a listing after reading the agent's assessment so that only listings that passed a check are published.

**Acceptance criteria:**

- The Approve and Reject buttons appear only on a listing with the status Evaluated and only for a moderator.
- A rejection requires a reason in text, which is stored and shown to the seller.
- The decision is stored as an event (who decided and when), and the status becomes Approved or Rejected.
- An approved listing appears immediately in public search (F3).

## 5. Data

Three main entities plus an event log. The status of a listing is built from the events recorded for it (Event Sourcing), and the events update a separate read model that search and the dashboard read from (CQRS).

| Entity | Main fields |
| --- | --- |
| User | id, name, email, password (hashed), role (seller or moderator) |
| Listing | id, seller id, title, description, price (ILS), category, status, publication date |
| Agent assessment | listing id, score (0–100) and its three sub-scores, recommendation, market price range, similar listing ids, reasoning, confidence |
| Event | id, listing id, event type, event data, actor, timestamp |

**Event types:** listing created, listing evaluated, listing approved, listing rejected.

**Categories (initial list):** electronics, furniture, sports, clothing, books, other.

## 6. AI agent

The agent runs as an independent process, reads listings from the database, checks them against similar listings and the web, and writes an assessment. It is built with the Deep Agents infrastructure, the model runs locally through Ollama, and external services are called through MCP.

**Steps for each listing:**

1. **Read:** the agent fetches a listing with the status Pending evaluation from the database (it checks every few seconds).
2. **Vector database (RAG):** the title and description are turned into an embedding, and the agent searches the vector database for the most similar listings and their prices.
3. **Web search:** through Tavily (over MCP), the agent looks up the market price of the item.
4. **Assessment:** the model compares the listing price with the market prices and with similar listings, checks that the description and category match, and returns a score, a recommendation and its reasoning.
5. **Save:** the agent stores the assessment through one of our own MCP tools, and the listing moves to Evaluated.

**Output:** score 0–100, recommendation (approve, reject or manual review), market price range, similar listing ids, and a short reasoning in Hebrew.

**Scoring:** the model rates three criteria and the program adds them up. The model returns each sub-score with a one-line justification, so the moderator can see why a listing got its score.

| Criterion | What the agent compares | Points |
| --- | --- | --- |
| Price vs market | The listing price and the price range found on the internet | 50 |
| Price vs similar listings | The listing price and the prices of similar listings in the vector database | 25 |
| Listing quality | Title, description and category are consistent and detailed enough | 25 |

**Recommendation from the score:** 70 or more: approve; 40 to 69: manual review; below 40: reject. These thresholds are a starting point and will be adjusted during testing.

**Vector database:** filled from two sources: sample listings loaded at the start (about 30 are enough for testing), and every listing approved afterwards.

**Errors:** if the internet search or the model fails, the assessment states what went wrong and the agent moves on to the next listing.

## 7. Non-functional requirements

These come from the assignment. The technical detail of each goes into architecture.md.

| # | Requirement | How the project meets it |
| --- | --- | --- |
| 1 | Development based on organized Markdown documents | A docs folder with the PRD, the architecture and a test plan |
| 2 | At least one Skill from Skills.sh | A Skill from the site, used during development (to be chosen) |
| 3 | At least one Skill and one Rule of our own | A Skill for building a feature; a Rule that separates commands from queries and requires tests |
| 4 | Flask application server | A Flask web app in Python |
| 5 | Cloud database | A database on Somee.com (or another cloud service) |
| 6 | Textual data vectorized into a vector database | Each listing's title and description is embedded and stored for semantic search of similar listings |
| 7 | Server services follow CQRS and MVC | Commands (writes) separated from queries (reads); Model-View-Controller structure |
| 8 | Data stored in a cloud service with Event Sourcing | A listing's status is rebuilt from its event log |
| 9 | External services consumed through MCP | Web search through Tavily.com |
| 10 | At least two Tools built with MCP Studio | Two Tools of our own, for example "fetch a listing for evaluation" and "save an assessment" |
| 11 | Evaluation agent built on Deep Agents | An agent using the vector database (RAG) and a search tool such as Tavily |
| 12 | Code managed in GitHub | A private repository shared with the team; keys and passwords only in a .env file, never in the repository |
| 13 | Professional UX/UI | Consistent Hebrew interface, right-to-left layout and clear navigation |

## 8. Development phases

The work is built one feature at a time, so every phase leaves a working system. Each phase goes through plan, implementation and validation.

1. **Infrastructure:** GitHub repository, Flask project, Somee database, configuration and secrets (.env).
2. **F1 – Registration and login** with two roles, in an MVC and CQRS structure.
3. **F2 – Publish a listing**, recording events (Event Sourcing).
4. **F3, F4, F5 – Search, listing details and table**, using a separate read model.
5. **F6 – Dashboard.**
6. **Vector database:** embed the sample listings and store them.
7. **Two Tools in MCP Studio.**
8. **F7 – AI agent** (Deep Agents, RAG, Tavily) as a separate process.
9. **F8 – Moderator decision.**
10. **Review and tests:** end-to-end tests, interface polish and updating the documents.

## 9. Assumptions and open questions

**Assumptions:**

- The dashboard shows listings by status and by category, instead of "registrants per job" from the assignment, because listings have no registrants.
- Listings do not require payment or a buyer account.
- The agent advises and does not decide: the final decision is the moderator's.

**Still to decide:**

- [x] Ollama models: `qwen2.5:3b` for the assessment and `bge-m3` for embeddings (multilingual, handles Hebrew; the same model is used for indexing and for searching). Both are small enough for a Mac with 8 GB of RAM.
- [x] Vector store: Chroma, saved in a local folder (`data/chroma/`, not committed).
- [ ] Whether the documents must be written in Hebrew or English.
- [ ] Which Skill from Skills.sh, and what our own Skill and Rule are.
- [ ] Whether a seller needs a screen to edit a listing after publishing.
