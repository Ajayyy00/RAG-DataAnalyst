"""
Dataset scale presets.
======================
Each preset is the target row count for the *entities the user requests*.
Child clinical tables (diagnoses/labs/meds/claims/procedures/vitals) are sized
relative to encounters so totals land near these targets while concentrating
records on inpatient/ED encounters (clinically realistic).

The full ``prod`` preset reproduces the requested platform volume:

    Patients 100K · Doctors 5K · Nurses 10K · Hospitals 500 ·
    Diagnoses 500K · Lab Results 2M · Prescriptions 1M ·
    Appointments (encounters) 2M · Claims 500K

Pick a smaller preset for quick validation; the pipeline is identical.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Scale:
    name: str
    facilities: int  # "Hospitals"
    physicians: int  # "Doctors"
    nurses: int  # "Nurses"
    patients: int
    encounters: int  # "Appointments"
    diagnoses: int
    lab_results: int
    medications: int  # "Prescriptions"
    claims: int
    procedures: int  # supplementary (keeps table populated)
    vital_signs: int  # supplementary

    @property
    def providers(self) -> int:
        return self.physicians + self.nurses

    @property
    def total_rows(self) -> int:
        return (
            self.facilities
            + self.providers
            + self.patients
            + self.encounters
            + self.diagnoses
            + self.lab_results
            + self.medications
            + self.claims
            + self.procedures
            + self.vital_signs
        )


SCALES: dict[str, Scale] = {
    # Tiny: fast smoke test / CI (seconds).
    "demo": Scale(
        "demo",
        facilities=10,
        physicians=40,
        nurses=80,
        patients=500,
        encounters=2_000,
        diagnoses=1_500,
        lab_results=4_000,
        medications=2_000,
        claims=1_000,
        procedures=1_200,
        vital_signs=3_000,
    ),
    # Small: realistic local dev (~1 min).
    "small": Scale(
        "small",
        facilities=50,
        physicians=500,
        nurses=1_000,
        patients=10_000,
        encounters=50_000,
        diagnoses=20_000,
        lab_results=80_000,
        medications=40_000,
        claims=20_000,
        procedures=24_000,
        vital_signs=60_000,
    ),
    # Medium: 1M-class dataset for meaningful benchmarks.
    "medium": Scale(
        "medium",
        facilities=200,
        physicians=2_500,
        nurses=5_000,
        patients=50_000,
        encounters=1_000_000,
        diagnoses=250_000,
        lab_results=1_000_000,
        medications=500_000,
        claims=250_000,
        procedures=200_000,
        vital_signs=300_000,
    ),
    # Prod: the full requested platform volume (~6.6M rows).
    "prod": Scale(
        "prod",
        facilities=500,
        physicians=5_000,
        nurses=10_000,
        patients=100_000,
        encounters=2_000_000,
        diagnoses=500_000,
        lab_results=2_000_000,
        medications=1_000_000,
        claims=500_000,
        procedures=400_000,
        vital_signs=600_000,
    ),
}

DEFAULT_SCALE = "small"
