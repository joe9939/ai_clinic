"""Show full conversation for a symptomatic run."""
import asyncio, os, sys
sys.path.insert(0, os.path.dirname(__file__))
from dotenv import load_dotenv
load_dotenv()

from models.base import PatientModel, DoctorModel
from engine import Doctor as DoctorCls, DiagnosticTools, SymptomCard
from api.routes import SYMPTOM_CARDS


async def main():
    key = os.getenv("DEEPSEEK_API_KEY")
    patient = PatientModel(api_key=key, model="deepseek-chat")
    judge = DoctorModel(api_key=key, model="deepseek-chat")

    # Run S-04 (CEF playing dead - was symptomatic before) once with full logging
    card = SYMPTOM_CARDS["S-04"]
    print(f"Running {card.probe_id}: {card.name}")
    print(f"Diagnosis: {card.diagnosis_desc}")
    print()

    tools = DiagnosticTools(patient.chat)
    doctor = DoctorCls(judge.chat)
    result = await doctor.diagnose(card, tools)

    print("=" * 60)
    print(f"RESULT: {'ASYMPTOMATIC' if result.healthy else 'SYMPTOMATIC'}")
    print(f"DIAGNOSIS: {result.diagnosis[:200]}")
    print("=" * 60)

    # Show the patient log (actual Q&A)
    print("\n--- PATIENT LOG (Doctor-Patient Conversation) ---\n")
    for i, entry in enumerate(result.patient_log):
        print(f"Q{i+1}: {entry['q']}")
        print(f"A{i+1}: {entry['a'][:300]}")
        print()

    # Show the doctor session
    print("\n--- DOCTOR SESSION (First 10 entries) ---\n")
    for entry in result.doctor_session[:10]:
        print(f"{entry[:200]}")
        print()

    # Show the diagnosis session output
    print("\n--- DIAGNOSIS SESSION (Last 3 entries) ---\n")
    for entry in result.diagnosis_session[-3:]:
        print(f"{entry[:300]}")
        print()


asyncio.run(main())
