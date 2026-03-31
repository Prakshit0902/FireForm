"""Sample incident transcripts for testing batch extraction."""

# Simple transcript — all fields clearly stated
SIMPLE_TRANSCRIPT = (
    "Hi. The employee's name is John Doe. His job title is managing director. "
    "His department supervisor is Jane Doe. His phone number is 123456. "
    "His email is jdoe@ucsc.edu. The signature is John Doe, "
    "and the date is 01/02/2005."
)

# Complex transcript — information scattered, natural speech patterns
COMPLEX_TRANSCRIPT = (
    "So uh, this is about the new hire. He goes by Marcus Johnson — "
    "well actually his full name is Marcus T. Johnson. He's coming in as "
    "a senior software engineer. Let me check... yeah, his supervisor is "
    "going to be Dr. Patricia Williams from the R&D department. "
    "You can reach him at 555-987-6543 or by email at "
    "marcus.johnson@company.org. He signed the paperwork on March 15th, 2026. "
    "Oh, and his digital signature reference is MTJ-2026-0315."
)

# Ambiguous transcript — some fields missing, some unclear
AMBIGUOUS_TRANSCRIPT = (
    "New employee report. Name is Sarah. She's in engineering. "
    "Phone is 555-0199. Started today."
)

# Fire incident transcript — realistic fire department scenario
FIRE_INCIDENT_TRANSCRIPT = (
    "This is Captain Rodriguez, badge number FD-7842, reporting from Station 45. "
    "We responded to a structure fire at 742 Evergreen Terrace at approximately "
    "14:30 hours on July 15th, 2024. The fire was reported by a neighbor who "
    "noticed smoke coming from the second floor. First unit arrived on scene at "
    "14:38. We had 3 engines, 1 ladder truck, and 2 ambulances respond. "
    "The fire was contained to the kitchen area on the second floor. "
    "Cause appears to be unattended cooking. One occupant was treated for "
    "minor smoke inhalation and transported to General Hospital. "
    "The fire was under control by 15:15 and fully extinguished by 15:45. "
    "Estimated property damage is approximately $45,000. "
    "No firefighter injuries reported."
)

# Define target fields for each transcript type
EMPLOYEE_FIELDS = {
    "employee_name": "Full name of the employee",
    "job_title": "Employee's job title or position",
    "department_supervisor": "Name of the department supervisor",
    "phone_number": "Employee's contact phone number",
    "email": "Employee's email address",
    "signature": "Signature or signature reference",
    "date": "Date in MM/DD/YYYY format"
}

FIRE_INCIDENT_FIELDS = {
    "reporting_officer": "Name of the reporting officer",
    "badge_number": "Officer's badge number",
    "station": "Fire station number or name",
    "incident_address": "Address of the incident",
    "incident_date": "Date of the incident",
    "incident_time": "Time the incident was reported",
    "arrival_time": "Time first unit arrived on scene",
    "units_responded": "Number and types of units that responded",
    "fire_location": "Specific location of the fire within the structure",
    "cause": "Suspected cause of the fire",
    "civilian_injuries": "Description of any civilian injuries",
    "firefighter_injuries": "Description of any firefighter injuries",
    "estimated_damage": "Estimated property damage in dollars",
    "time_under_control": "Time the fire was under control",
    "time_extinguished": "Time the fire was fully extinguished"
}
