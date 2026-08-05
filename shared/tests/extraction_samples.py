"""Five project descriptions of deliberately varying quality.

Each sample pairs a description with the CPM collections an LLM would
plausibly return for it, so the extraction pipeline can be exercised end to end
without a model. The scripted output is what the *model* produces; everything
the tests assert is about what the *service* does with it.

The vague sample is the important one. It is over 200 words on purpose — a
twenty-word input being rejected proves nothing, because length alone catches
it. Two hundred words of confident, substance-free product copy is the case
where a model reaches for User, System and Dashboard to look useful, and where
the completeness floor has to hold (R1).
"""

import json
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class Sample:
    key: str
    description: str
    llm_output: dict[str, Any]

    @property
    def word_count(self) -> int:
        return len(self.description.split())

    def as_json(self) -> str:
        return json.dumps(self.llm_output)


LIBRARY = Sample(
    key="library_management",
    description="""
    We need a library management system for our college library. The library holds
    books, and each book has an ISBN, a title, an author, a publication year and a
    number of physical copies. Students register as members of the library. A member
    has a membership number, a name, an email address, a joining date and a borrowing
    limit that caps how many books they may hold at once.

    A librarian issues a book to a member, which creates a loan. A loan records which
    book was taken, which member took it, the date it was borrowed and the date it is
    due back. When a member returns a book the loan is closed and the return date is
    recorded. If the book comes back after its due date the system raises a fine
    against that loan. A fine has an amount, a reason and a payment date once it is
    settled.

    If every copy of a book is already out on loan, a member can place a reservation
    instead. A reservation records the member, the book, the date it was placed and
    the date it expires. When a copy is returned and a reservation is waiting, the
    system notifies the next member in the queue.

    Books are grouped into categories such as fiction, reference or periodicals, and
    a librarian can search the catalogue by title, author, ISBN or category.
    Administrators register new members, suspend members who repeatedly return books
    late, and manage the staff accounts.
    """,
    llm_output={
        "actors": [
            {"id": "member", "name": "Member", "isPrimary": True},
            {"id": "librarian", "name": "Librarian", "isPrimary": True},
            {"id": "administrator", "name": "Administrator", "isPrimary": False},
        ],
        "entities": [
            {
                "id": "book",
                "name": "Book",
                "attributes": [
                    {"name": "isbn", "type": "string", "isKey": True, "isRequired": True},
                    {"name": "title", "type": "string", "isRequired": True},
                    {"name": "author", "type": "string", "isRequired": True},
                    {"name": "publicationYear", "type": "integer"},
                    {"name": "copies", "type": "integer", "isRequired": True},
                ],
            },
            {
                "id": "member",
                "name": "Member",
                "attributes": [
                    {
                        "name": "membershipNumber",
                        "type": "string",
                        "isKey": True,
                        "isRequired": True,
                    },
                    {"name": "name", "type": "string", "isRequired": True},
                    {"name": "email", "type": "string", "isRequired": True},
                    {"name": "joinedOn", "type": "date", "isRequired": True},
                    {"name": "borrowingLimit", "type": "integer", "isRequired": True},
                ],
            },
            {
                "id": "loan",
                "name": "Loan",
                "attributes": [
                    {"name": "loanId", "type": "string", "isKey": True, "isRequired": True},
                    {"name": "borrowedOn", "type": "date", "isRequired": True},
                    {"name": "dueOn", "type": "date", "isRequired": True},
                    {"name": "returnedOn", "type": "date"},
                ],
            },
            {
                "id": "fine",
                "name": "Fine",
                "attributes": [
                    {"name": "amount", "type": "decimal", "isRequired": True},
                    {"name": "reason", "type": "string", "isRequired": True},
                    {"name": "paidOn", "type": "date"},
                ],
            },
            {
                "id": "reservation",
                "name": "Reservation",
                "attributes": [
                    {"name": "placedOn", "type": "date", "isRequired": True},
                    {"name": "expiresOn", "type": "date", "isRequired": True},
                ],
            },
            {
                "id": "category",
                "name": "Category",
                "attributes": [{"name": "name", "type": "string", "isRequired": True}],
            },
        ],
        "relationships": [
            {
                "id": "r-member-loan",
                "from": "member",
                "to": "loan",
                "type": "association",
                "cardinality": "1..*",
                "label": "borrows",
            },
            {
                "id": "r-book-loan",
                "from": "book",
                "to": "loan",
                "type": "association",
                "cardinality": "1..*",
                "label": "issued as",
            },
            {
                "id": "r-loan-fine",
                "from": "loan",
                "to": "fine",
                "type": "composition",
                "cardinality": "0..1",
                "label": "incurs",
            },
            {
                "id": "r-member-reservation",
                "from": "member",
                "to": "reservation",
                "type": "association",
                "cardinality": "0..*",
                "label": "places",
            },
            {
                "id": "r-category-book",
                "from": "category",
                "to": "book",
                "type": "aggregation",
                "cardinality": "1..*",
                "label": "groups",
            },
        ],
        "useCases": [
            {
                "id": "uc-borrow-book",
                "name": "Borrow Book",
                "actors": ["member", "librarian"],
                "mainFlow": ["The librarian scans the book.", "The system creates a loan."],
            },
            {
                "id": "uc-return-book",
                "name": "Return Book",
                "actors": ["member", "librarian"],
                "mainFlow": [
                    "The librarian scans the returned book.",
                    "The system closes the loan.",
                ],
            },
            {
                "id": "uc-manage-members",
                "name": "Manage Members",
                "actors": ["administrator"],
                "mainFlow": ["The administrator registers or suspends a member."],
            },
        ],
        "flows": [
            {
                "id": "flow-borrow",
                "name": "Borrow a book",
                "participants": ["member", "librarian", "book", "loan"],
                "steps": [
                    {
                        "from": "member",
                        "to": "librarian",
                        "message": "requestBook(isbn)",
                        "order": 1,
                    },
                    {
                        "from": "librarian",
                        "to": "book",
                        "message": "checkAvailability()",
                        "order": 2,
                    },
                    {"from": "librarian", "to": "loan", "message": "createLoan()", "order": 3},
                ],
            },
        ],
        "states": [
            {
                "id": "s-book-available",
                "entityRef": "book",
                "name": "Available",
                "isInitial": True,
                "transitions": [{"to": "s-book-on-loan", "trigger": "borrow"}],
            },
            {
                "id": "s-book-on-loan",
                "entityRef": "book",
                "name": "On Loan",
                "transitions": [{"to": "s-book-available", "trigger": "return"}],
            },
        ],
        "components": [
            {
                "id": "comp-catalogue",
                "name": "Catalogue Service",
                "type": "service",
                "provides": ["CatalogueAPI"],
            },
            {
                "id": "comp-lending",
                "name": "Lending Service",
                "type": "service",
                "provides": ["LendingAPI"],
                # Slug-shaped, not the "Catalogue Service" spelling used on that
                # component's own `name` — the extractor writes the same
                # reference two ways, and normalise() is what makes them agree.
                "requires": ["catalogue-service"],
            },
        ],
        "nodes": [
            {
                "id": "node-app-server",
                "name": "Application Server",
                "type": "server",
                "deployedComponents": ["comp-catalogue", "comp-lending"],
            },
        ],
        "requirements": [
            {
                "id": "req-issue",
                "type": "functional",
                "text": "The system shall allow a librarian to issue a book to an active member.",
                "priority": "P0",
            },
            {
                "id": "req-fine",
                "type": "functional",
                "text": "The system shall raise a fine when a loan is returned late.",
                "priority": "P1",
            },
        ],
    },
)


HOSTEL_MESS = Sample(
    key="hostel_mess_billing",
    description="""
    Our hostel needs a mess billing system. Every student staying in the hostel is
    allocated a room and registered with the mess. A student record holds a roll
    number, a name, a room number and the date they joined the mess.

    The mess serves three meals a day. For each meal a student either eats or is
    marked absent, and the mess supervisor records attendance for every meal. At the
    end of the month the system totals the meals each student actually ate and
    generates a bill. A bill has a billing month, the number of meals consumed, the
    per-meal rate and the total amount payable.

    Students pay their bills at the hostel office. A payment records the amount paid,
    the date and the mode of payment, and a bill is marked settled once payments
    cover the full amount. Partial payments are allowed, so a bill can be partly
    settled.

    Students may apply for a mess rebate when they are away from the hostel for four
    or more consecutive days. A rebate application records the start date, the end
    date and the reason, and the warden approves or rejects it. An approved rebate
    removes those meals from the next bill.

    The warden can see how many students are eating each day so the kitchen can plan
    purchases, and the accounts office can see which bills are outstanding.
    """,
    llm_output={
        "actors": [
            {"id": "student", "name": "Student", "isPrimary": True},
            {"id": "mess-supervisor", "name": "Mess Supervisor", "isPrimary": True},
            {"id": "warden", "name": "Warden", "isPrimary": False},
        ],
        "entities": [
            {
                "id": "student",
                "name": "Student",
                "attributes": [
                    {"name": "rollNumber", "type": "string", "isKey": True, "isRequired": True},
                    {"name": "name", "type": "string", "isRequired": True},
                    {"name": "roomNumber", "type": "string", "isRequired": True},
                ],
            },
            {
                "id": "meal-attendance",
                "name": "Meal Attendance",
                "attributes": [
                    {"name": "date", "type": "date", "isRequired": True},
                    {"name": "meal", "type": "string", "isRequired": True},
                    {"name": "present", "type": "boolean", "isRequired": True},
                ],
            },
            {
                "id": "bill",
                "name": "Bill",
                "attributes": [
                    {"name": "billingMonth", "type": "string", "isKey": True, "isRequired": True},
                    {"name": "mealsConsumed", "type": "integer", "isRequired": True},
                    {"name": "amountPayable", "type": "decimal", "isRequired": True},
                ],
            },
            {
                "id": "payment",
                "name": "Payment",
                "attributes": [
                    {"name": "amount", "type": "decimal", "isRequired": True},
                    {"name": "paidOn", "type": "date", "isRequired": True},
                ],
            },
            {
                "id": "rebate",
                "name": "Rebate",
                "attributes": [
                    {"name": "startDate", "type": "date", "isRequired": True},
                    {"name": "endDate", "type": "date", "isRequired": True},
                ],
            },
        ],
        "relationships": [
            {
                "id": "r-student-attendance",
                "from": "student",
                "to": "meal-attendance",
                "type": "association",
                "cardinality": "1..*",
                "label": "records",
            },
            {
                "id": "r-student-bill",
                "from": "student",
                "to": "bill",
                "type": "association",
                "cardinality": "1..*",
                "label": "is billed",
            },
            {
                "id": "r-bill-payment",
                "from": "bill",
                "to": "payment",
                "type": "composition",
                "cardinality": "0..*",
                "label": "settled by",
            },
            {
                "id": "r-student-rebate",
                "from": "student",
                "to": "rebate",
                "type": "association",
                "cardinality": "0..*",
                "label": "applies for",
            },
        ],
        "useCases": [
            {
                "id": "uc-record-attendance",
                "name": "Record Attendance",
                "actors": ["mess-supervisor"],
                "mainFlow": ["The supervisor marks each student."],
            },
            {
                "id": "uc-generate-bill",
                "name": "Generate Monthly Bill",
                "actors": ["warden"],
                "mainFlow": ["The system totals meals and produces a bill."],
            },
        ],
        "flows": [],
        "states": [
            {
                "id": "s-bill-unpaid",
                "entityRef": "bill",
                "name": "Unpaid",
                "isInitial": True,
                "transitions": [{"to": "s-bill-settled", "trigger": "paymentCoversTotal"}],
            },
            {"id": "s-bill-settled", "entityRef": "bill", "name": "Settled", "isFinal": True},
        ],
        "components": [],
        "nodes": [],
        "requirements": [
            {
                "id": "req-attendance",
                "type": "functional",
                "text": "The system shall record per-meal attendance for every registered student.",
                "priority": "P0",
            },
        ],
    },
)


PARKING_LOT = Sample(
    key="parking_lot",
    description="""
    A parking lot management system for a shopping mall. The lot has parking slots,
    each with a slot number and a size such as compact or large. When a vehicle
    enters, the attendant records the registration number and the system allocates a
    free slot and issues a ticket with the entry time. When the vehicle leaves, the
    system calculates the fee from the time parked and marks the slot free again.
    """,
    llm_output={
        "actors": [
            {"id": "driver", "name": "Driver", "isPrimary": True},
            {"id": "attendant", "name": "Attendant", "isPrimary": True},
        ],
        "entities": [
            {
                "id": "parking-slot",
                "name": "Parking Slot",
                "attributes": [
                    {"name": "slotNumber", "type": "string", "isKey": True, "isRequired": True},
                    {"name": "size", "type": "string", "isRequired": True},
                ],
            },
            {
                "id": "vehicle",
                "name": "Vehicle",
                "attributes": [
                    {
                        "name": "registrationNumber",
                        "type": "string",
                        "isKey": True,
                        "isRequired": True,
                    },
                ],
            },
            {
                "id": "ticket",
                "name": "Ticket",
                "attributes": [
                    {"name": "entryTime", "type": "datetime", "isRequired": True},
                    {"name": "exitTime", "type": "datetime"},
                    {"name": "fee", "type": "decimal"},
                ],
            },
        ],
        "relationships": [
            {
                "id": "r-vehicle-ticket",
                "from": "vehicle",
                "to": "ticket",
                "type": "association",
                "cardinality": "1..*",
                "label": "issued",
            },
            {
                "id": "r-slot-ticket",
                "from": "parking-slot",
                "to": "ticket",
                "type": "association",
                "cardinality": "0..*",
                "label": "allocated to",
            },
        ],
        "useCases": [
            {
                "id": "uc-park-vehicle",
                "name": "Park Vehicle",
                "actors": ["driver", "attendant"],
                "mainFlow": ["The attendant records the registration number."],
            },
        ],
        "flows": [],
        "states": [],
        "components": [],
        "nodes": [],
        "requirements": [],
    },
)


# The model returned duplicates, an orphan relationship, and a state pointing at
# an entity it never declared. All three are ordinary LLM output, and all three
# are the normaliser's job — not the user's.
CLINIC = Sample(
    key="clinic_appointments",
    description="""
    A clinic appointment system for a small private practice. Patients book
    appointments with doctors. A patient has a patient id, a name, a date of birth
    and a phone number. A doctor has a registration number, a name and a speciality
    such as paediatrics or dermatology.

    An appointment records the patient, the doctor, the date and time of the slot and
    the reason for the visit. The receptionist books appointments over the phone or
    at the desk, and can reschedule or cancel an appointment if the patient calls
    back. A doctor can see the list of appointments for the day.

    After the consultation the doctor writes a prescription. A prescription lists the
    medicines prescribed, the dosage for each and the duration of the course. It is
    linked to the appointment it came from, so the patient's history can be pulled up
    at their next visit.

    The clinic also issues an invoice for each consultation, recording the
    consultation fee and any charges for tests carried out. Patients pay at the desk
    and the receptionist marks the invoice paid. The practice manager wants a report
    of how many appointments each doctor handled in a month and how much was
    collected.
    """,
    llm_output={
        "actors": [
            {"id": "patient", "name": "Patient", "isPrimary": True},
            {"id": "doctor", "name": "Doctor", "isPrimary": True},
            {"id": "receptionist", "name": "receptionist", "isPrimary": True},
        ],
        "entities": [
            {
                "id": "patient",
                "name": "Patient",
                "attributes": [
                    {"name": "patientId", "type": "string", "isKey": True, "isRequired": True},
                    {"name": "name", "type": "string", "isRequired": True},
                ],
            },
            # Same concept, three spellings — the classic extraction artefact.
            {
                "id": "patients",
                "name": "Patients",
                "attributes": [
                    {"name": "dateOfBirth", "type": "date"},
                ],
            },
            {
                "id": "patient-record",
                "name": "patient",
                "attributes": [
                    {"name": "phoneNumber", "type": "string"},
                ],
            },
            {
                "id": "doctor",
                "name": "Doctor",
                "attributes": [
                    {
                        "name": "registrationNumber",
                        "type": "string",
                        "isKey": True,
                        "isRequired": True,
                    },
                    {"name": "speciality", "type": "string", "isRequired": True},
                ],
            },
            {
                "id": "appointment",
                "name": "appointment",
                "attributes": [
                    {"name": "slotTime", "type": "datetime", "isRequired": True},
                    {"name": "reason", "type": "string"},
                ],
            },
            {
                "id": "prescription",
                "name": "Prescription",
                "attributes": [
                    {"name": "dosage", "type": "string", "isRequired": True},
                ],
            },
            {
                "id": "invoice",
                "name": "Invoice",
                "attributes": [
                    {"name": "consultationFee", "type": "decimal", "isRequired": True},
                ],
            },
        ],
        "relationships": [
            {
                "id": "r-patient-appointment",
                "from": "patient",
                "to": "appointment",
                "type": "association",
                "cardinality": "1..*",
                "label": "books",
            },
            {
                "id": "r-doctor-appointment",
                "from": "doctor",
                "to": "appointment",
                "type": "association",
                "cardinality": "1..*",
                "label": "attends",
            },
            {
                "id": "r-appointment-prescription",
                "from": "appointment",
                "to": "prescription",
                "type": "composition",
                "cardinality": "0..1",
                "label": "results in",
            },
            {
                "id": "r-appointment-invoice",
                "from": "appointment",
                "to": "invoice",
                "type": "composition",
                "cardinality": "0..1",
                "label": "billed as",
            },
            # Endpoint that was never declared as an entity.
            {
                "id": "r-orphan-lab",
                "from": "appointment",
                "to": "lab-test",
                "type": "association",
                "label": "orders",
            },
            # Merged-away duplicate as an endpoint; must survive by being repointed.
            {
                "id": "r-patients-invoice",
                "from": "patients",
                "to": "invoice",
                "type": "dependency",
                "label": "pays",
            },
        ],
        "useCases": [
            {
                "id": "uc-book-appointment",
                "name": "Book Appointment",
                "actors": ["patient", "receptionist", "nurse"],
                "mainFlow": ["The receptionist finds a free slot."],
            },
        ],
        "flows": [
            {
                "id": "flow-consultation",
                "name": "Consultation",
                "participants": ["patient", "doctor", "prescription", "pharmacy"],
                "steps": [
                    {
                        "from": "patient",
                        "to": "doctor",
                        "message": "describeSymptoms()",
                        "order": 1,
                    },
                    {"from": "doctor", "to": "prescription", "message": "write()", "order": 2},
                    {"from": "doctor", "to": "pharmacy", "message": "sendScript()", "order": 3},
                ],
            },
        ],
        "states": [
            {
                "id": "s-appt-booked",
                "entityRef": "appointment",
                "name": "Booked",
                "isInitial": True,
                "transitions": [
                    {"to": "s-appt-completed", "trigger": "consultationDone"},
                    {"to": "s-nonexistent", "trigger": "somethingUndeclared"},
                ],
            },
            {
                "id": "s-appt-completed",
                "entityRef": "appointment",
                "name": "Completed",
                "isFinal": True,
            },
            # entityRef the model never declared.
            {"id": "s-labtest-pending", "entityRef": "lab-test", "name": "Pending"},
        ],
        "components": [],
        "nodes": [
            {
                "id": "node-desk",
                "name": "Reception Desk",
                "type": "device",
                "deployedComponents": ["comp-that-does-not-exist"],
            },
        ],
        "requirements": [],
    },
)


# Over 200 words, and says nothing a diagram could be drawn from.
VAGUE = Sample(
    key="vague_startup",
    description="""
    We are building a next-generation platform that will fundamentally transform how
    people work together in the modern digital workplace. Our solution is designed
    from the ground up to be intuitive, powerful and delightful, delivering a
    seamless experience across every device and touchpoint that our users care about.

    The platform will leverage cutting-edge technology to unlock unprecedented value
    for our customers and their stakeholders. We believe deeply that software should
    adapt to people rather than forcing people to adapt to software, and every design
    decision we make flows from that conviction. Performance, reliability and
    security are not features we bolt on at the end; they are foundational
    commitments woven through everything we ship.

    Our target users are busy professionals who are frustrated by the fragmented,
    clunky tools they are forced to use today. They want something that just works,
    that gets out of their way, and that makes them measurably more productive from
    the very first day. We will delight them with thoughtful details, fast response
    times and a beautiful interface that feels effortless.

    We plan to iterate rapidly based on continuous user feedback, shipping
    improvements weekly and building a genuine community around the product. Scale,
    extensibility and a rich ecosystem of integrations are core to the long-term
    vision, and we intend to become the default choice in our category within three
    years of launch.
    """,
    # An honest model returns almost nothing here, because there is almost
    # nothing to return.
    llm_output={
        "actors": [{"id": "user", "name": "User", "isPrimary": True}],
        "entities": [
            {"id": "user", "name": "User", "attributes": []},
        ],
        "relationships": [],
        "useCases": [],
        "flows": [],
        "states": [],
        "components": [],
        "nodes": [],
        "requirements": [],
    },
)


SAMPLES = [LIBRARY, HOSTEL_MESS, PARKING_LOT, CLINIC, VAGUE]
BY_KEY = {sample.key: sample for sample in SAMPLES}
