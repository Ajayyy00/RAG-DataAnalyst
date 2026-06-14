"""
seed_db.py
==========
Synthetic clinical data seeder for Healthcare Copilot using Faker.
"""

import asyncio
import random
from datetime import date, timedelta

from faker import Faker
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models import (
    Department,
    Diagnosis,
    Encounter,
    Facility,
    LabResult,
    Patient,
    Provider,
)
from app.db.session import AsyncSessionLocal

fake = Faker()


async def clear_db(db: AsyncSession):
    await db.execute(
        text(
            "TRUNCATE TABLE lab_results, diagnoses, encounters, patients, providers, departments, facilities CASCADE;"
        )
    )
    await db.commit()


async def seed_data():
    async with AsyncSessionLocal() as db:
        print("Clearing existing data...")
        await clear_db(db)

        print("Seeding facilities and departments...")
        fac1 = Facility(name="General Hospital", facility_type="Hospital", state="CA")
        fac2 = Facility(name="Westside Clinic", facility_type="Clinic", state="CA")
        db.add_all([fac1, fac2])
        await db.flush()

        dep1 = Department(name="Cardiology", facility_id=fac1.id)
        dep2 = Department(name="Endocrinology", facility_id=fac1.id)
        dep3 = Department(name="General Practice", facility_id=fac2.id)
        db.add_all([dep1, dep2, dep3])
        await db.flush()

        print("Seeding providers...")
        providers = [
            Provider(
                npi=str(fake.unique.random_number(digits=10)),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                specialty="Cardiologist",
                department_id=dep1.id,
            ),
            Provider(
                npi=str(fake.unique.random_number(digits=10)),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                specialty="Endocrinologist",
                department_id=dep2.id,
            ),
            Provider(
                npi=str(fake.unique.random_number(digits=10)),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                specialty="General Practitioner",
                department_id=dep3.id,
            ),
        ]
        db.add_all(providers)
        await db.flush()

        print("Seeding patients (this might take a few seconds)...")
        patients = []
        for _ in range(50):
            dob = fake.date_of_birth(minimum_age=20, maximum_age=90)
            p = Patient(
                mrn=str(fake.unique.random_number(digits=8)),
                first_name=fake.first_name(),
                last_name=fake.last_name(),
                date_of_birth=dob,
                gender=random.choice(["M", "F"]),
                zip_code=fake.zipcode()[:5],
            )
            patients.append(p)
        db.add_all(patients)
        await db.flush()

        print("Seeding encounters, diagnoses, and labs...")
        for p in patients:
            # 1-3 encounters per patient
            for _ in range(random.randint(1, 3)):
                enc_date = fake.date_time_between(start_date="-2y", end_date="now")
                enc_type = random.choice(["inpatient", "outpatient", "emergency"])
                # Add random discharge date 1-14 days after admit date
                disc_date = enc_date + timedelta(days=random.randint(1, 14))
                enc = Encounter(
                    patient_id=p.id,
                    provider_id=random.choice(providers).id,
                    department_id=random.choice([dep1, dep2, dep3]).id,
                    admit_date=enc_date,
                    discharge_date=disc_date,
                    encounter_type=enc_type,
                )
                db.add(enc)
                await db.flush()

                # Force some readmissions
                if enc_type == "inpatient" and random.random() > 0.6:
                    re_admit = disc_date + timedelta(days=random.randint(2, 25))
                    re_disc = re_admit + timedelta(days=random.randint(1, 7))
                    re_enc = Encounter(
                        patient_id=p.id,
                        provider_id=random.choice(providers).id,
                        department_id=random.choice([dep1, dep2, dep3]).id,
                        admit_date=re_admit,
                        discharge_date=re_disc,
                        encounter_type="inpatient",
                    )
                    db.add(re_enc)
                    await db.flush()
                    from app.db.models import Readmission

                    readmission = Readmission(
                        index_encounter_id=enc.id,
                        readmit_encounter_id=re_enc.id,
                        patient_id=p.id,
                        days_to_readmit=(re_admit.date() - disc_date.date()).days,
                    )
                    db.add(readmission)
                    await db.flush()

                # Maybe a diagnosis
                if random.random() > 0.3:
                    icd_map = {
                        "E11.9": "Type 2 Diabetes",
                        "I10": "Hypertension",
                        "I25.10": "Heart Disease",
                        "J45.909": "Asthma",
                        "E78.5": "Hyperlipidemia",
                        "K21.9": "GERD",
                    }
                    code = random.choice(list(icd_map.keys()))
                    diag = Diagnosis(
                        encounter_id=enc.id,
                        patient_id=p.id,
                        icd10_code=code,
                        icd10_desc=icd_map[code],
                        diagnosis_type="Primary",
                    )
                    db.add(diag)

                # Maybe some medications
                if random.random() > 0.4:
                    med_map = [
                        ("Metformin", "500 mg"),
                        ("Lisinopril", "10 mg"),
                        ("Atorvastatin", "20 mg"),
                        ("Albuterol", "90 mcg"),
                        ("Omeprazole", "40 mg"),
                        ("Aspirin", "81 mg"),
                    ]
                    med_name, dose = random.choice(med_map)
                    from app.db.models import Medication

                    med = Medication(
                        encounter_id=enc.id,
                        patient_id=p.id,
                        drug_name=med_name,
                        dose=dose,
                        route="Oral",
                        frequency="Daily",
                    )
                    db.add(med)

                # Maybe some labs
                if random.random() > 0.5:
                    # Glucose test
                    lab1 = LabResult(
                        patient_id=p.id,
                        encounter_id=enc.id,
                        loinc_code="2345-7",
                        test_name="Glucose",
                        numeric_value=random.uniform(70.0, 200.0),  # > 125 is high
                        unit="mg/dL",
                        result_date=enc_date,
                    )
                    # A1C test
                    lab2 = LabResult(
                        patient_id=p.id,
                        encounter_id=enc.id,
                        loinc_code="4548-4",
                        test_name="HbA1c",
                        numeric_value=random.uniform(4.0, 9.0),
                        unit="%",
                        result_date=enc_date,
                    )
                    db.add_all([lab1, lab2])

        print("Committing to database...")
        await db.commit()
        print("Database seeded successfully with synthetic data!")


if __name__ == "__main__":
    asyncio.run(seed_data())
