"""
Generate 100 synthetic Iovance stakeholder interview transcripts.

Each transcript mimics raw discovery-interview notes (see the attached
Mekonos/Phoenix example for the style): a short metadata header, a bit of
background, then 5-7 pain points raised by the stakeholder, plus closing notes.

Pain points are tagged internally as AI-addressable or not so we can produce a
realistic mix ("some we cannot address as an AI transformation function, but
many that we can"). The addressable flags are NOT printed into the transcript
files themselves (those stay raw, like real notes) but are written to an index
CSV so the corpus is auditable and ready for the Lens pipeline.

Synthetic data only. Decision-support, not production. No em-dashes.
"""

import csv
import os
import random
import textwrap

random.seed(20260616)

OUT_DIR = os.path.join(os.path.dirname(__file__), "transcripts")

# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------

FIRST_NAMES = [
    "Priya", "Marco", "Daniel", "Lena", "Aisha", "Sofia", "Ravi", "Hannah",
    "Diego", "Mei", "Tomas", "Grace", "Omar", "Yuki", "Nadia", "Caleb",
    "Ingrid", "Rohan", "Camila", "Andre", "Fatima", "Liam", "Noor", "Elena",
    "Kenji", "Beatriz", "Samuel", "Anika", "Hassan", "Maya", "Lucas", "Imani",
    "Viktor", "Leila", "Patrick", "Dana", "Felix", "Rosa", "Connor", "Amara",
    "Jin", "Carla", "Mateo", "Zara", "Wesley", "Nina", "Gabriel", "Tara",
    "Dmitri", "Selene", "Oscar", "Priscilla", "Aaron", "Bianca", "Theo",
    "Renata", "Kofi", "Linnea", "Pablo", "Joan",
]

LAST_NAMES = [
    "Shah", "Reyes", "Okafor", "Whitfield", "Bello", "Romano", "Patel",
    "Brennan", "Castillo", "Lin", "Novak", "Adeyemi", "Haddad", "Tanaka",
    "Rahimi", "Fischer", "Sorensen", "Mehta", "Vargas", "Laurent", "Khan",
    "Doyle", "Abboud", "Petrova", "Watanabe", "Costa", "Friedman", "Iyer",
    "Mansour", "Delgado", "Carver", "Okonkwo", "Sokolov", "Nasser", "Boyle",
    "Klein", "Moreau", "Santos", "Walsh", "Eze", "Park", "Russo", "Aguilar",
    "Voss", "Hartman", "Bauer", "Mwangi", "Sandberg", "Ferreira", "Quinn",
]

INTERVIEWERS = [
    "J. Lin (AI Strategy)",
    "AI Strategy & Ops",
    "AI Transformation team",
    "J. Lin + intern (discovery)",
]

# ---------------------------------------------------------------------------
# Functions and roles
# ---------------------------------------------------------------------------
# weight roughly approximates headcount / interview density at a commercial
# cell-therapy company. Manufacturing, Quality, and Supply Chain dominate.

FUNCTIONS = {
    "Patient Services & Reimbursement": {
        "id": "FN-patient-services",
        "weight": 9,
        "roles": [
            ("Manager, Benefit Verification", "manager"),
            ("Senior Patient Coordinator", "ic"),
            ("Director, Patient Access", "director"),
            ("Case Manager, Cell Therapy", "ic"),
            ("Reimbursement Specialist", "ic"),
            ("VP, Patient Services", "vp"),
        ],
    },
    "Manufacturing Operations (iCTC)": {
        "id": "FN-mfg-ops",
        "weight": 13,
        "roles": [
            ("Manager, Production Scheduling", "manager"),
            ("Manufacturing Associate III", "ic"),
            ("Shift Lead, TIL Expansion", "ic"),
            ("Director, Manufacturing Operations", "director"),
            ("Manufacturing Supervisor", "manager"),
            ("VP, Manufacturing", "vp"),
        ],
    },
    "Manufacturing Sciences (MSAT)": {
        "id": "FN-msat",
        "weight": 7,
        "roles": [
            ("Scientist II, Process Development", "ic"),
            ("Manager, MSAT", "manager"),
            ("Principal Engineer, Tech Transfer", "ic"),
            ("Director, Manufacturing Sciences", "director"),
        ],
    },
    "Quality Assurance": {
        "id": "FN-qa",
        "weight": 11,
        "roles": [
            ("QA Specialist, Batch Disposition", "ic"),
            ("Manager, Quality Assurance", "manager"),
            ("QA Associate, Deviations", "ic"),
            ("Director, Quality Assurance", "director"),
            ("Senior Manager, QA Compliance", "manager"),
            ("VP, Quality", "vp"),
        ],
    },
    "Quality Control": {
        "id": "FN-qc",
        "weight": 9,
        "roles": [
            ("QC Analyst II", "ic"),
            ("Manager, QC Operations", "manager"),
            ("Senior QC Analyst, Flow Cytometry", "ic"),
            ("Director, Quality Control", "director"),
        ],
    },
    "Supply Chain & Cold Chain Logistics": {
        "id": "FN-supply-chain",
        "weight": 9,
        "roles": [
            ("Coordinator, Cell Orchestration", "ic"),
            ("Manager, Logistics", "manager"),
            ("Cold Chain Specialist", "ic"),
            ("Director, Supply Chain", "director"),
            ("Planner, Materials Management", "ic"),
        ],
    },
    "Regulatory Affairs": {
        "id": "FN-regulatory",
        "weight": 6,
        "roles": [
            ("Regulatory Affairs Associate", "ic"),
            ("Manager, Regulatory Affairs", "manager"),
            ("Director, Regulatory CMC", "director"),
            ("Senior Manager, Global Reg", "manager"),
        ],
    },
    "Clinical Operations": {
        "id": "FN-clinical-ops",
        "weight": 7,
        "roles": [
            ("Clinical Trial Associate", "ic"),
            ("Clinical Trial Manager", "manager"),
            ("Manager, Clinical Data", "manager"),
            ("Director, Clinical Operations", "director"),
            ("CRA (Clinical Research Associate)", "ic"),
        ],
    },
    "Commercial (Sales & Marketing)": {
        "id": "FN-commercial",
        "weight": 7,
        "roles": [
            ("Sales Operations Analyst", "ic"),
            ("Manager, Market Access", "manager"),
            ("Brand Manager, Amtagvi", "manager"),
            ("Director, Commercial Operations", "director"),
            ("Field Reimbursement Manager", "ic"),
        ],
    },
    "Medical Affairs & Pharmacovigilance": {
        "id": "FN-medical-affairs",
        "weight": 6,
        "roles": [
            ("Medical Science Liaison", "ic"),
            ("Manager, Medical Information", "manager"),
            ("Drug Safety Associate (PV)", "ic"),
            ("Director, Medical Affairs", "director"),
            ("Pharmacovigilance Scientist", "ic"),
        ],
    },
    "Finance & FP&A": {
        "id": "FN-finance",
        "weight": 6,
        "roles": [
            ("Manager, FP&A", "manager"),
            ("Director, Controllership", "director"),
            ("Senior Financial Analyst", "ic"),
            ("Cost Accountant, COGS", "ic"),
            ("VP, Finance", "vp"),
        ],
    },
    "Human Resources": {
        "id": "FN-hr",
        "weight": 4,
        "roles": [
            ("HR Business Partner", "manager"),
            ("Talent Acquisition Specialist", "ic"),
            ("Manager, People Operations", "manager"),
            ("Director, Human Resources", "director"),
        ],
    },
    "IT, Data & Digital": {
        "id": "FN-it",
        "weight": 5,
        "roles": [
            ("IT Service Desk Lead", "ic"),
            ("Business Systems Analyst", "ic"),
            ("Manager, Enterprise Applications", "manager"),
            ("Director, IT & Data", "director"),
            ("CSV Specialist (Computer System Validation)", "ic"),
        ],
    },
    "Legal & Compliance": {
        "id": "FN-legal",
        "weight": 4,
        "roles": [
            ("Contracts Manager", "manager"),
            ("Compliance Analyst", "ic"),
            ("Paralegal", "ic"),
            ("Director, Legal Operations", "director"),
        ],
    },
    "Procurement & Sourcing": {
        "id": "FN-procurement",
        "weight": 5,
        "roles": [
            ("Procurement Analyst", "ic"),
            ("Category Manager, Raw Materials", "manager"),
            ("Buyer, Consumables", "ic"),
            ("Director, Strategic Sourcing", "director"),
        ],
    },
}

# ---------------------------------------------------------------------------
# Background / intro lines per function (non-pain context)
# ---------------------------------------------------------------------------

BACKGROUND = {
    "FN-patient-services": [
        "Team owns the patient journey from referral through scheduled infusion at the Authorized Treatment Center (ATC).",
        "We sit between the prescribing center, the payer, and manufacturing. Nothing moves until benefits are confirmed.",
        "Volume is climbing fast as more ATCs come online for Amtagvi.",
    ],
    "FN-mfg-ops": [
        "Autologous TIL, so every batch is one patient. Tumor tissue comes in, we expand to billions of cells, cryopreserve, ship back.",
        "Second-gen process, turnaround down around 22-34 days. The slot is the constraint, not the chemistry on a good day.",
        "Internalizing all manufacturing in-house at the iCTC, so volume is ramping hard.",
    ],
    "FN-msat": [
        "We own the process: characterization, tech transfer from dev into GMP, and investigation support when a batch misbehaves.",
        "Bridge between R&D and the floor. We translate a process that works at bench into something that survives at commercial scale.",
    ],
    "FN-qa": [
        "Quality owns batch disposition, deviations, change control, and audit readiness. For a personalized product the paperwork is the product.",
        "Every batch is patient-specific so the documentation burden per unit is brutal compared to small molecule.",
    ],
    "FN-qc": [
        "We run release and in-process testing: identity, potency, sterility, flow panels. Everything funnels through LIMS.",
        "Turnaround on testing is on the critical path to disposition, so any delay in QC delays a patient.",
    ],
    "FN-supply-chain": [
        "We orchestrate the cold chain both directions: fresh tumor inbound, cryopreserved product outbound to the ATC.",
        "Chain of identity and chain of custody is everything. A single mislabeled handoff is a patient-impacting event.",
    ],
    "FN-regulatory": [
        "We own submissions and health-authority interactions across the markets where Amtagvi is approved or pending.",
        "Lots of parallel markets now: US approved, Australia conditional, EMA resubmission in progress, Switzerland pending.",
    ],
    "FN-clinical-ops": [
        "We run the trials: the sarcoma registrational study, endometrial, and the next-gen gene-edited TIL programs.",
        "Oversight of CROs and sites, plus all the trial documentation that has to be inspection-ready.",
    ],
    "FN-commercial": [
        "We support the field team selling Amtagvi into ATCs, plus market access and the brand work.",
        "Small specialized field force calling on a defined set of treatment centers, not a primary-care blitz.",
    ],
    "FN-medical-affairs": [
        "MSLs in the field, medical information desk, and the drug-safety/PV group handling adverse events.",
        "We field the scientific questions the commercial team is not allowed to answer, plus case processing for safety.",
    ],
    "FN-finance": [
        "Controllership, FP&A, and cost accounting. COGS per batch is a huge focus given the gross-margin push.",
        "Leadership wants COGS down and margin up, so finance is under the microscope on cost per patient.",
    ],
    "FN-hr": [
        "We staff a very tight cell-therapy talent market: manufacturing associates, QC analysts, all hard to find.",
        "Headcount is growing with the manufacturing ramp, so recruiting and onboarding volume is high.",
    ],
    "FN-it": [
        "We run the enterprise systems: MES, LIMS, ERP, the orchestration platform, and the validated-state paperwork around all of it.",
        "Everything we touch in GxP space needs computer-system validation, which slows every change down.",
    ],
    "FN-legal": [
        "Contracts, compliance, and policy. Heavy CDA/MSA volume with CROs, ATCs, suppliers, and academic collaborators.",
        "Small team, very high contract throughput, plus the healthcare-compliance overhead of a commercial pharma.",
    ],
    "FN-procurement": [
        "We source everything from GMP raw materials and media to consumables and lab services.",
        "A lot of single-source critical materials, which makes supply risk our constant background worry.",
    ],
}

# ---------------------------------------------------------------------------
# Pain banks. Each item: (text_in_stakeholder_voice, addressable_bool)
# addressable = plausibly solvable by an internal AI transformation function
# ---------------------------------------------------------------------------

PAINS = {
    "FN-patient-services": [
        ("Biggest time sink is benefit verification. Before we can schedule anyone a coordinator pulls status out of the payer portal, our case system, and the copay tool and hand-assembles one picture of the case. Call it 30-40 min each and we're running thousands of cases a year, and it's error prone if one source is stale.", True),
        ("Denial appeals are brutal. When a payer denies we draft the appeal more or less from scratch every time, people keep a few old letters and rewrite them, 45 min easy, and we do hundreds a year.", True),
        ("We burn hours just chasing prior-auth status, calling payers and sitting on hold to find out if something got approved. Pure waiting.", True),
        ("Patients and centers ask coverage questions constantly and we dig through plan policy PDFs to find the exact clause. The answer exists, finding it takes forever.", True),
        ("Scheduling a patient is calendar tetris: ATC availability, a manufacturing slot, the lymphodepletion window, and IL-2, all coordinated by hand across teams. One slip and the whole sequence reshuffles.", True),
        ("There's no single tracker of which payers cover Amtagvi and under what criteria. Policies change and we find out the hard way when something gets denied.", True),
        ("Honestly we just don't have enough coordinators for the case volume coming. More ATCs onboarding means more cases and we're already maxed. We need heads.", False),
        ("A lot of this job is emotional support for patients who are out of options. That's human work, you can't automate sitting with someone through a terminal diagnosis.", False),
        ("Reimbursement rates and the payer mix are what they are. The economics of a given case aren't something my team can fix, that's set above us.", False),
    ],
    "FN-mfg-ops": [
        ("Batch record review is the slog. For every patient batch someone reviews the electronic batch record line by line for completeness before it goes to QA, and any blank or transcription miss bounces it back. It's hours per batch and every batch is a patient.", True),
        ("Deviation writeups eat the floor. When something goes off-script the associate documents it in detail, and they're doing it mid-shift trying to remember exactly what happened. Slow and inconsistent.", True),
        ("Shift handoff is all manual notes. Night shift writes up where each batch stands and day shift re-reads it, and stuff gets lost in the translation.", True),
        ("Scheduling manufacturing slots against incoming tumor tissue is a constant puzzle. Tissue arrives in tight windows, suites and staff are fixed, and we re-plan by hand whenever anything shifts.", True),
        ("Chain-of-identity checks are manual label reconciliation at every step. Necessary, but a person is eyeballing IDs and initialing, over and over.", True),
        ("We can't run more suites without more qualified operators, and qualifying an operator takes months. That's a people-and-time problem, not a software one.", False),
        ("Some of our incubators and equipment are aging and we get unplanned downtime. That needs capital and new hardware, not an app.", False),
        ("Yield still varies batch to batch because it's living cells from a sick patient. No model fixes the underlying biology, the starting material is what it is.", False),
        ("Environmental monitoring generates a mountain of data entry, readings keyed in by hand into the system every shift.", True),
    ],
    "FN-msat": [
        ("Tech transfer documentation is endless. Moving a process from dev into GMP means re-authoring batch records, risk assessments, and control strategies, and most of it is reformatting and cross-referencing existing material.", True),
        ("When we investigate a process deviation we manually trend across dozens of historical batches to find the root cause, pulling data out of MES and LIMS into spreadsheets by hand.", True),
        ("Comparability protocols and reports take weeks, and a lot of it is assembling data and writing the narrative around it.", True),
        ("Pulling process data into the monthly process-monitoring reports is brutal, the data lives in three systems and we stitch it together by hand every time.", True),
        ("Process characterization is wet-lab work. You have to run the experiments at the bench, there's no shortcut around generating the actual data.", False),
        ("Scale-up is a physical engineering problem, equipment, footprint, single-use hardware. Software helps document it but doesn't build it.", False),
    ],
    "FN-qa": [
        ("Deviations and CAPAs are the bottleneck. Authoring and reviewing them is a backlog that never clears, each one is a structured writeup and we have hundreds open at any time.", True),
        ("Batch disposition review means a QA person re-reads the entire batch record and supporting docs before release. For a patient-specific product that's enormous and it's on the patient's critical path.", True),
        ("Change control documentation is heavy, every change needs an impact assessment written, routed, and tracked, and the writing is repetitive.", True),
        ("We have hundreds of SOPs on periodic-review cycles. Someone has to read each one, decide if it still reflects practice, and document the review. It's relentless.", True),
        ("Audit and inspection prep is a fire drill every time, we scramble to gather documents and build the narrative from scattered sources.", True),
        ("Annual Product Quality Review compilation is a multi-week effort pulling data from everywhere into one report.", True),
        ("Supplier quality complaints need trending and we do it manually across a year of records.", True),
        ("We genuinely need more trained QA reviewers, the volume is outpacing the team and review can't be skipped. That's headcount.", False),
        ("Inspection readiness is also a culture and behavior thing on the floor, that's leadership and training, not a tool.", False),
    ],
    "FN-qc": [
        ("Reviewing certificates of analysis and transcribing results into LIMS is constant, and any transcription error is a deviation, so it gets double-checked, doubling the work.", True),
        ("Analysts spend hours on manual data analysis for assays, exporting from instruments, reformatting, and calculating in spreadsheets.", True),
        ("Out-of-spec investigations are big writeups and we do a lot of them. Documenting the investigation is most of the effort.", True),
        ("Stability tracking is a manual calendar and spreadsheet exercise, what's due to pull, what was tested, what's trending.", True),
        ("Sample login gets backed up at peak, everything keyed in manually before testing can even start.", True),
        ("Qualifying a new assay is bench science, you run the validation experiments, there's no automating the wet work.", False),
        ("Instrument calibration and maintenance is physical and on a fixed schedule, that's metrology, not analytics.", False),
    ],
    "FN-supply-chain": [
        ("We monitor cold-chain shipments across multiple couriers and there's no single dashboard, so coordinators watch portals and emails and phone for status all day, both directions.", True),
        ("Inbound tumor tissue has to land in a tight window and we hand-coordinate every pickup against the manufacturing slot. Constant re-planning.", True),
        ("Every temperature excursion triggers a documented investigation, and writing those up and chasing the data is a recurring drain.", True),
        ("Materials and consumables inventory never reconciles cleanly between the warehouse system and the ERP, so someone goes line by line monthly.", True),
        ("Demand forecasting for consumables is basically a person's gut plus a spreadsheet, and when we're wrong we either stock out or sit on expensive expiring material.", True),
        ("Courier and vendor performance reporting is manual every quarter, pulling shipment data and building the scorecards by hand.", True),
        ("Flights, weather, and customs are out of our hands. No model makes a grounded plane fly, that's physical-world risk we just manage.", False),
        ("We're capacity-limited on LN2 dry shippers and qualified packaging. That's procurement and hardware, you can't software your way to more shippers.", False),
    ],
    "FN-regulatory": [
        ("Assembling submissions is heavy lifting, compiling modules, cross-referencing, formatting to each authority's spec. Hours of assembly per submission.", True),
        ("Health-authority queries come in with tight clocks and we draft responses pulling from prior submissions and source docs every time.", True),
        ("Tracking regulatory commitments across all our markets is a spreadsheet that's always slightly out of date, and missing one is a serious problem.", True),
        ("Labeling changes have to be managed across regions and reconciled against local requirements, very manual cross-checking.", True),
        ("Keeping up with new guidances and summarizing what they mean for us is a reading-and-writing job nobody has time for.", True),
        ("The actual timing of FDA and EMA decisions is completely outside our control, we can prepare but we can't move their calendar.", False),
        ("Some ex-US submissions need certified translations and local agent work that's inherently external and manual.", False),
    ],
    "FN-clinical-ops": [
        ("Reviewing monitoring visit reports from CRAs is a steady load, reading long reports and pulling out the issues that need action.", True),
        ("Protocol deviation tracking across sites is manual reconciliation, and rolling it up for the sponsor oversight meeting takes a CTA most of a week.", True),
        ("Reconciling CRO-delivered data against our own trackers is endless, the numbers never quite match and we chase the differences.", True),
        ("Trial master file completeness is a constant audit risk, someone is forever checking which documents are missing or expired across thousands of files.", True),
        ("Drafting adverse-event narratives for the safety database is repetitive structured writing, and we do a lot of them.", True),
        ("Enrollment forecasting is guesswork in a spreadsheet, and when a model would help, the underlying problem is still that these are rare tumors.", True),
        ("Slow enrollment is fundamentally a biology and epidemiology problem, the patients are rare and you can't manufacture eligible patients.", False),
        ("Site startup drags on IRB and contract timelines that are external, no internal tool speeds up another institution's committee.", False),
    ],
    "FN-commercial": [
        ("Reps need a current picture of each ATC account, and today an analyst compiles it by hand from the CRM, ordering data, and emails before every cycle.", True),
        ("Field territory reporting is a manual monthly build, exporting from the CRM and reformatting into the deck leadership wants.", True),
        ("Promotional material has to clear medical-legal-regulatory review and the cycle is slow, lots of back-and-forth and version chasing.", True),
        ("CRM data hygiene is a mess, duplicate accounts, stale contacts, and someone is always cleaning it manually.", True),
        ("Market-access dossiers and payer value decks are assembled from scratch each time even though 70% of the content repeats.", True),
        ("Competitive intelligence is a person reading press releases and conference coverage and writing it up, it's never current.", True),
        ("KOL relationships are built on trust over years of in-person time. That's human, you can't automate a relationship with a thought leader.", False),
        ("If we want more ATC coverage we need more field people on the ground, that's a headcount and territory decision.", False),
    ],
    "FN-medical-affairs": [
        ("The medical information desk drafts responses to HCP inquiries, and most questions repeat but each response is researched and written fresh against approved sources.", True),
        ("Literature surveillance for safety is a firehose, someone screens new publications weekly for anything relevant to our product.", True),
        ("Adverse-event intake and case triage is high volume, reading in cases, coding them, and prioritizing, and the clock is regulatory so we can't fall behind.", True),
        ("MSLs build their own slide decks for every center visit, pulling from the master deck and tailoring it, hours each.", True),
        ("After every congress we summarize the relevant abstracts and presentations into a readout, and it's a manual scramble.", True),
        ("Actual safety signal detection takes clinical judgment, you can surface candidates but a human has to make the medical call.", False),
        ("Off-label questions from HCPs are a compliance minefield, how we respond is a judgment and legal line, not something to fully automate.", False),
    ],
    "FN-finance": [
        ("Month-end account reconciliation is where it hurts, an analyst ties ERP balances to subledgers and spreadsheets and chases every variance. A material account is 90 min and we do 500-600 a close.", True),
        ("Building the management reporting pack is its own slog, copying numbers out of five sources into a deck every month.", True),
        ("Vendor and SaaS spend review is quarterly and manual, I go invoice by invoice looking for duplicate tools and licenses we forgot to cancel, and I'm sure we miss savings.", True),
        ("Every contract that comes up I write a summary memo, pulling key terms, renewal dates, and pricing out of a long PDF into a one-pager.", True),
        ("COGS per batch is the number leadership cares about most and allocating cost to each patient batch is a painful manual exercise across systems.", True),
        ("Budget-versus-actual variance commentary is written from scratch each month even though half the explanations recur.", True),
        ("Headcount approvals and the hiring-justification process are a governance flow that's slow by design, that's policy, not a tool gap.", False),
        ("Revenue recognition for a personalized therapy has genuine judgment calls that I'm not handing to a model.", False),
    ],
    "FN-hr": [
        ("Recruiting volume is high and screening resumes for manufacturing and QC roles is a huge manual sift, hundreds of applicants per req.", True),
        ("Onboarding is a documentation checklist nightmare, every new hire in a GxP role has a stack of forms and trainings to track to completion.", True),
        ("Employees constantly ask the same policy questions, PTO, benefits, travel, and HR answers them one at a time from documents that exist but nobody reads.", True),
        ("Training compliance tracking is manual, chasing people to complete required trainings and reconciling the LMS records.", True),
        ("Writing and updating job descriptions is slow and they drift out of date, every manager wants a custom one.", True),
        ("Interview scheduling across panels is pure coordination overhead, back-and-forth on calendars all day.", True),
        ("Retention in this talent market is the real problem, people get poached and that's about comp, culture, and career, not automation.", False),
        ("Comp benchmarking decisions are judgment calls with real equity implications, I won't outsource that to a tool.", False),
    ],
    "FN-it": [
        ("Service-desk tickets pour in and a person triages and routes every one, and a big share are the same handful of password and access issues.", True),
        ("Pulling data across our siloed systems for any cross-functional report is painful, MES, LIMS, ERP, and the orchestration platform don't talk, so we extract and join by hand.", True),
        ("Computer-system validation documentation is enormous, every system change in GxP needs validation protocols and reports written and executed.", True),
        ("There's spreadsheet sprawl everywhere, shadow tools doing critical work with no controls, and we spend time hunting them down.", True),
        ("Master data is maintained by hand across systems and it drifts, so reports disagree depending on the source.", True),
        ("Access provisioning is partly approvals and partly judgment about least-privilege, some of it has to stay human for compliance.", False),
        ("Integrating the legacy systems properly needs real capital and a platform program, not a quick automation.", False),
    ],
    "FN-legal": [
        ("Contract review eats the team, redlining standard CDAs, MSAs, and work orders against our playbook, most of it the same edits over and over.", True),
        ("NDA and CDA turnaround is a bottleneck for the whole company, partners wait on us and they're 80% boilerplate.", True),
        ("Drafting and updating policies and SOPs is slow, lots of cross-referencing and consistency-checking.", True),
        ("Compliance training content has to be built and refreshed constantly, and it's mostly assembling and rewording existing material.", True),
        ("Finding a prior contract or a specific clause in the repository is a nightmare, the search is bad so we re-draft things we already have.", True),
        ("Monitoring healthcare-compliance obligations like Sunshine Act reporting is partly tracking we could speed up and partly judgment.", True),
        ("Actual negotiation and litigation strategy is judgment and relationships, that's the core lawyering and it stays human.", False),
        ("A real privacy or HIPAA incident is a judgment-and-liability call, you escalate to people, you don't let a model decide.", False),
    ],
    "FN-procurement": [
        ("Purchase-order processing and three-way matching is high volume and manual, exceptions kicked out for a human to chase down all day.", True),
        ("Supplier onboarding and qualification is a paperwork marathon, collecting documents, quality questionnaires, and risk assessments for every new vendor.", True),
        ("Spend analysis across categories is a quarterly manual build, and without it we can't see where to consolidate or negotiate.", True),
        ("Contract renewals sneak up on us because tracking them is a spreadsheet, and auto-renewals slip through and cost us.", True),
        ("Building RFPs and comparing bids is slow, assembling the requirements and then normalizing wildly different vendor responses by hand.", True),
        ("Supplier risk monitoring is reactive, we find out a supplier had a problem when a shipment is already late.", True),
        ("A lot of our critical GMP materials are single-source, and that supply risk is a market and qualification reality no software removes.", False),
        ("With sole suppliers we have almost no negotiating leverage, that's a market-structure problem, not an analytics one.", False),
    ],
}

# Cross-cutting pains that recur across many functions (drive dedup/overlap)
CROSS_CUTTING = [
    ("Finding the right SOP or work instruction is a daily hunt, they're scattered across SharePoint and shared drives and the search never finds the current version.", True),
    ("Every week I stitch together a status report from three or four different sources by hand, it's the same format every time and it still takes hours.", True),
    ("Onboarding and keeping training material current is a constant background task, the documents go stale and nobody owns updating them.", True),
    ("So much knowledge is locked in people's heads and old email threads, when someone is out or leaves we lose the answer.", True),
    ("My inbox is a part-time job, triaging and routing email and pulling out the few things that actually need me.", True),
]

# Adjacent-function map for occasional cross-functional pain injection
ADJACENT = {
    "FN-mfg-ops": ["FN-qa", "FN-qc", "FN-supply-chain", "FN-msat"],
    "FN-qa": ["FN-mfg-ops", "FN-qc", "FN-regulatory"],
    "FN-qc": ["FN-qa", "FN-mfg-ops"],
    "FN-msat": ["FN-mfg-ops", "FN-qa"],
    "FN-supply-chain": ["FN-mfg-ops", "FN-procurement"],
    "FN-patient-services": ["FN-commercial", "FN-supply-chain"],
    "FN-commercial": ["FN-patient-services", "FN-medical-affairs"],
    "FN-regulatory": ["FN-qa", "FN-clinical-ops"],
    "FN-clinical-ops": ["FN-regulatory", "FN-medical-affairs"],
    "FN-medical-affairs": ["FN-clinical-ops", "FN-commercial"],
    "FN-finance": ["FN-procurement"],
    "FN-procurement": ["FN-finance", "FN-supply-chain"],
    "FN-it": ["FN-finance", "FN-qa"],
    "FN-legal": ["FN-procurement", "FN-finance"],
    "FN-hr": ["FN-it"],
}

CLOSERS = [
    "If I could wave a wand and kill one thing, it's the manual report stitching.",
    "Asked what they'd hand off first: the repetitive writing, no question.",
    "Open to piloting something if it's reliable and stays inside our validated systems.",
    "Skeptical that a tool can handle the GxP documentation rigor, wants to see it before trusting it.",
    "Says the team would welcome the help but worries about anything touching release decisions.",
    "Wants any solution to keep a human in the loop for anything patient-impacting.",
    "Flagged that whatever we build has to play nice with the validated systems or it won't get approved.",
    "Noted the volume is only going up as manufacturing internalizes and more markets come online.",
]

# ---------------------------------------------------------------------------
# Build
# ---------------------------------------------------------------------------

def weighted_function_order(n):
    """Produce a list of n function names distributed by weight."""
    bag = []
    for name, meta in FUNCTIONS.items():
        bag.extend([name] * meta["weight"])
    out = []
    while len(out) < n:
        random.shuffle(bag)
        out.extend(bag)
    return out[:n]


def used_name_factory():
    used = set()

    def pick():
        while True:
            nm = f"{random.choice(FIRST_NAMES)} {random.choice(LAST_NAMES)}"
            if nm not in used:
                used.add(nm)
                return nm

    return pick


def date_pool():
    # weekdays across a ~6 week diagnostic window in 2026
    days = []
    for month, start, end in [(4, 20, 30), (5, 1, 31), (6, 1, 12)]:
        for d in range(start, end + 1):
            days.append(f"2026-{month:02d}-{d:02d}")
    return days


def pick_pains(fid):
    """Return list of (text, addressable, source_fid) for one interview."""
    own = PAINS[fid][:]
    random.shuffle(own)
    n = random.randint(5, 7)

    chosen = []
    # reserve slots for occasional cross-cutting and cross-functional items
    add_cross_cutting = random.random() < 0.45
    add_adjacent = random.random() < 0.30 and fid in ADJACENT

    base_needed = n - (1 if add_cross_cutting else 0) - (1 if add_adjacent else 0)
    base_needed = max(base_needed, 3)

    for text, addr in own[:base_needed]:
        chosen.append((text, addr, fid))

    if add_cross_cutting:
        text, addr = random.choice(CROSS_CUTTING)
        chosen.append((text, addr, "cross-cutting"))

    if add_adjacent:
        adj = random.choice(ADJACENT[fid])
        text, addr = random.choice(PAINS[adj])
        chosen.append((text, addr, adj))

    random.shuffle(chosen)
    return chosen[:n]


# ---------------------------------------------------------------------------
# Messy mode: render a subset like real, raw, shorthand-heavy notes
# ---------------------------------------------------------------------------

MESSY_SUBS = [
    ("because", "bc"), ("Because", "bc"), ("without", "w/o"), ("with ", "w/ "),
    ("With ", "w/ "), ("manufacturing", "mfg"), ("Manufacturing", "mfg"),
    ("management", "mgmt"), ("Management", "mgmt"), ("approximately", "~"),
    ("about ", "abt "), ("number", "#"), ("and ", "n "), ("really", "rly"),
    (" you ", " u "), ("everything", "evrythng"), ("documentation", "docs"),
    ("document", "doc"), ("reconciliation", "recon"), ("reconcile", "recon"),
    ("information", "info"), ("system", "sys"), ("between", "btwn"),
    (" people", " ppl"), ("something", "smth"), ("probably", "prob"),
    ("constantly", "constntly"), ("never", "nvr"), ("through", "thru"),
    ("every time", "evry time"), ("a lot of", "lotta"), ("them", "em"),
]

# light, deterministic-ish typos
MESSY_TYPOS = [
    ("the ", "teh "), ("ing ", "ign "), ("tion", "toin"), ("our ", "ovr "),
    ("ent ", "etn "), ("for ", "fro "),
]


def messify(text):
    t = text
    for a, b in MESSY_SUBS:
        if random.random() < 0.7:
            t = t.replace(a, b)
    # drop most apostrophes
    t = t.replace("'", "")
    # lowercase the start, kill some capitalization
    t = t[0].lower() + t[1:] if t else t
    # sprinkle a couple typos
    for a, b in MESSY_TYPOS:
        if random.random() < 0.18 and a in t:
            t = t.replace(a, b, 1)
    # occasionally drop the final period / trail off
    if random.random() < 0.5 and t.endswith("."):
        t = t[:-1]
    if random.random() < 0.15:
        t = t.rstrip(".") + " ->"
    # collapse some commas into nothing or dashes
    if random.random() < 0.3:
        t = t.replace(", ", " ", 1)
    return t


def render_messy(intv):
    """Raw shorthand notes, no neat sections, like a fast typist on a call."""
    lines = []
    lines.append(f"{intv['function']} // {intv['name']} ({intv['role']})")
    lines.append(f"{intv['date']} - {intv['interviewer']} - {intv['id']}")
    lines.append("")
    lines.append("current role / context:")
    for b in intv["background"]:
        lines.append(f"- {messify(b)}")
    lines.append("")
    lines.append("pain points / where time goes:")
    for text, _addr, _src in intv["pains"]:
        m = messify(text)
        wrapped = textwrap.wrap(m, random.choice([84, 96, 110]))
        lines.append(f"- {wrapped[0]}")
        for w in wrapped[1:]:
            lines.append(f"  {w}")
    # occasional dangling/abandoned bullets like the example PDF
    if random.random() < 0.6:
        lines.append("-")
        if random.random() < 0.5:
            lines.append("-")
    lines.append("")
    lines.append(messify(intv["closer"]))
    lines.append("")
    return "\n".join(lines)


def render(intv):
    lines = []
    lines.append("IOVANCE BIOTHERAPEUTICS")
    lines.append("AI Transformation Diagnostic | Stakeholder Interview Notes")
    lines.append("=" * 64)
    lines.append("")
    lines.append(f"Interview ID:   {intv['id']}")
    lines.append(f"Interviewee:    {intv['name']}")
    lines.append(f"Title:          {intv['role']}")
    lines.append(f"Function:       {intv['function']}")
    lines.append(f"Date:           {intv['date']}")
    lines.append(f"Interviewer:    {intv['interviewer']}")
    lines.append("Format:         ~45 min discovery call (raw notes, lightly cleaned)")
    lines.append("")
    lines.append("-" * 64)
    lines.append("Background / current role")
    lines.append("-" * 64)
    for b in intv["background"]:
        for w in textwrap.wrap(b, 92):
            lines.append(f"- {w}" if w == textwrap.wrap(b, 92)[0] else f"  {w}")
    lines.append("")
    lines.append("-" * 64)
    lines.append("Pain points / friction raised (in their words)")
    lines.append("-" * 64)
    for i, (text, _addr, _src) in enumerate(intv["pains"], 1):
        wrapped = textwrap.wrap(text, 90)
        lines.append(f"{i}. {wrapped[0]}")
        for w in wrapped[1:]:
            lines.append(f"   {w}")
        lines.append("")
    lines.append("-" * 64)
    lines.append("Closing note")
    lines.append("-" * 64)
    for w in textwrap.wrap(intv["closer"], 92):
        lines.append(f"- {w}" if w == textwrap.wrap(intv['closer'], 92)[0] else f"  {w}")
    lines.append("")
    return "\n".join(lines)


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    # clear prior output so re-runs do not leave stale files behind
    for f in os.listdir(OUT_DIR):
        if f.startswith("INT-") and f.endswith(".txt"):
            os.remove(os.path.join(OUT_DIR, f))

    N = 100
    fn_order = weighted_function_order(N)
    pick_name = used_name_factory()
    dates = date_pool()

    # ~22 of the 100 come out as raw shorthand notes, like real fast-typed
    # interview notes (see the Mekonos example). Deterministic given the seed.
    messy_ids = set(random.sample(range(N), k=22))

    index_rows = []
    addr_total = 0
    pain_total = 0

    for i in range(N):
        fname = fn_order[i]
        meta = FUNCTIONS[fname]
        fid = meta["id"]
        role, seniority = random.choice(meta["roles"])
        intv = {
            "id": f"INT-{i + 1:03d}",
            "name": pick_name(),
            "role": role,
            "seniority": seniority,
            "function": fname,
            "function_id": fid,
            "date": random.choice(dates),
            "interviewer": random.choice(INTERVIEWERS),
            "background": random.sample(BACKGROUND[fid], k=min(2, len(BACKGROUND[fid]))),
            "pains": pick_pains(fid),
            "closer": random.choice(CLOSERS),
        }

        style = "messy" if i in messy_ids else "clean"
        text = render_messy(intv) if style == "messy" else render(intv)
        slug = fname.split("(")[0].strip().replace(" & ", "-").replace(", ", "-").replace(" ", "")
        last = intv["name"].split()[-1]
        path = os.path.join(OUT_DIR, f"{intv['id']}_{slug}_{last}.txt")
        with open(path, "w") as fh:
            fh.write(text)

        n_addr = sum(1 for _, a, _ in intv["pains"] if a)
        addr_total += n_addr
        pain_total += len(intv["pains"])
        index_rows.append({
            "interview_id": intv["id"],
            "file": os.path.basename(path),
            "style": style,
            "stakeholder": intv["name"],
            "role": intv["role"],
            "seniority": intv["seniority"],
            "function": fname,
            "function_id": fid,
            "date": intv["date"],
            "n_pain_points": len(intv["pains"]),
            "n_ai_addressable": n_addr,
            "n_not_addressable": len(intv["pains"]) - n_addr,
        })

    with open(os.path.join(OUT_DIR, "_INDEX.csv"), "w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(index_rows[0].keys()))
        writer.writeheader()
        writer.writerows(index_rows)

    # function distribution summary
    from collections import Counter
    dist = Counter(r["function"] for r in index_rows)
    print(f"Wrote {N} transcripts to {OUT_DIR}")
    print(f"Total pain points: {pain_total} | AI-addressable: {addr_total} "
          f"({addr_total * 100 // pain_total}%) | not addressable: {pain_total - addr_total}")
    print("\nFunction distribution:")
    for fn, c in sorted(dist.items(), key=lambda x: -x[1]):
        print(f"  {c:>3}  {fn}")


if __name__ == "__main__":
    main()
