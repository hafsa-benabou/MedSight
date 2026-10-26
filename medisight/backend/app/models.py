"""Modèle relationnel MEDISIGHT. Chaque donnée métier porte sa provenance (source_id) et un statut :
official (autorité publique), reference (source scientifique tierce), unverified (non vérifiée), simulated (démo)."""
from __future__ import annotations

import uuid
from datetime import date, datetime
from decimal import Decimal
from typing import Any

from sqlalchemy import (JSON, Boolean, CheckConstraint, Date, DateTime, Float, ForeignKey, Index, Integer,
                        LargeBinary, Numeric, String, Text, UniqueConstraint, Uuid, func)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

JSONType = JSON().with_variant(JSONB(), "postgresql")
DATA_STATUSES = ("official", "reference", "unverified", "simulated")
STATUS_RANK = {"simulated": 0, "unverified": 1, "reference": 2, "official": 3}


def _status_check() -> CheckConstraint:
    return CheckConstraint("data_status IN ('official','reference','unverified','simulated')", name="data_status_valid")


def _created() -> Mapped[datetime]:
    return mapped_column(DateTime(timezone=True), server_default=func.now())


def _status() -> Mapped[str]:
    return mapped_column(String(16), default="unverified")


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(64), unique=True)
    name: Mapped[str] = mapped_column(String(255))
    publisher: Mapped[str | None] = mapped_column(String(255))
    url: Mapped[str | None] = mapped_column(String(500))
    license: Mapped[str | None] = mapped_column(String(255))
    license_url: Mapped[str | None] = mapped_column(String(500))
    reuse_conditions: Mapped[str | None] = mapped_column(Text)
    is_official: Mapped[bool] = mapped_column(Boolean, default=False)
    default_data_status: Mapped[str] = mapped_column(String(16), default="unverified")
    market: Mapped[str | None] = mapped_column(String(8))  # MA | FR | US | INT : jamais de fusion entre marchés
    notes: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _created()


class DataImport(Base):
    __tablename__ = "data_imports"
    id: Mapped[int] = mapped_column(primary_key=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    status: Mapped[str] = mapped_column(String(16))  # running | success | partial | failed
    method: Mapped[str] = mapped_column(String(32), default="file")  # file | manual_transcription | api | seed
    file_name: Mapped[str | None] = mapped_column(String(255))
    file_sha256: Mapped[str | None] = mapped_column(String(64))
    source_version_date: Mapped[date | None] = mapped_column(Date)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    rows_read: Mapped[int] = mapped_column(Integer, default=0)
    rows_inserted: Mapped[int] = mapped_column(Integer, default=0)
    rows_updated: Mapped[int] = mapped_column(Integer, default=0)
    rows_rejected: Mapped[int] = mapped_column(Integer, default=0)
    report: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    triggered_by: Mapped[str | None] = mapped_column(String(64))
    source: Mapped[DataSource] = relationship()


class Laboratory(Base):
    __tablename__ = "laboratories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    name_normalized: Mapped[str] = mapped_column(String(255), index=True)


class PharmaceuticalForm(Base):
    __tablename__ = "pharmaceutical_forms"
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(255), unique=True)
    canonical: Mapped[str | None] = mapped_column(String(64), index=True)


class TherapeuticClass(Base):
    __tablename__ = "therapeutic_classes"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    atc_code: Mapped[str | None] = mapped_column(String(16))


class ActiveIngredient(Base):
    __tablename__ = "active_ingredients"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255), unique=True)
    name_normalized: Mapped[str] = mapped_column(String(255), unique=True)
    inn_en: Mapped[str | None] = mapped_column(String(255))
    name_ar: Mapped[str | None] = mapped_column(String(255))
    synonyms: Mapped[list[str] | None] = mapped_column(JSONType, default=list)  # résolution à l'import (même entité)
    # Termes de recherche uniquement (ex. sels issus de la BDPM) : jamais utilisés pour résoudre une substance à
    # l'import, car un dosage exprimé en sel (bésilate d'amlodipine) n'est pas un dosage en base (amlodipine).
    search_terms: Mapped[list[str] | None] = mapped_column(JSONType, default=list)
    external_codes: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # ex. {"bdpm_substance": "39727"}


class Medicine(Base):
    """Spécialité = nom commercial + dosage + forme. Les prix sont portés par les présentations."""
    __tablename__ = "medicines"
    __table_args__ = (
        UniqueConstraint("source_record_key", name="uq_medicines_source_record_key"),
        _status_check(),
        Index("ix_medicines_search_trgm", "search_text", postgresql_using="gin",
              postgresql_ops={"search_text": "gin_trgm_ops"}),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    brand_name: Mapped[str] = mapped_column(String(255))
    brand_normalized: Mapped[str] = mapped_column(String(255), index=True)
    dosage_text: Mapped[str | None] = mapped_column(String(255))
    form_id: Mapped[int | None] = mapped_column(ForeignKey("pharmaceutical_forms.id"))
    laboratory_id: Mapped[int | None] = mapped_column(ForeignKey("laboratories.id"))
    therapeutic_class_id: Mapped[int | None] = mapped_column(ForeignKey("therapeutic_classes.id"))
    atc_code: Mapped[str | None] = mapped_column(String(16))
    amm_status: Mapped[str | None] = mapped_column(String(64))
    marketing_status: Mapped[str | None] = mapped_column(String(64))
    is_marketed: Mapped[bool | None] = mapped_column(Boolean)
    princeps_status: Mapped[str | None] = mapped_column(String(4))  # P | G | I
    rcp_url: Mapped[str | None] = mapped_column(String(500))
    source_url: Mapped[str | None] = mapped_column(String(500))  # fiche ou page source de l'enregistrement
    search_text: Mapped[str] = mapped_column(Text, default="")
    data_status: Mapped[str] = _status()
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_record_key: Mapped[str] = mapped_column(String(400))
    created_at: Mapped[datetime] = _created()
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    form: Mapped[PharmaceuticalForm | None] = relationship()
    laboratory: Mapped[Laboratory | None] = relationship()
    therapeutic_class: Mapped[TherapeuticClass | None] = relationship()
    source: Mapped[DataSource] = relationship()
    ingredients: Mapped[list[MedicineIngredient]] = relationship(
        back_populates="medicine", cascade="all, delete-orphan", order_by="MedicineIngredient.position")
    presentations: Mapped[list[MedicinePresentation]] = relationship(
        back_populates="medicine", cascade="all, delete-orphan", order_by="MedicinePresentation.id")
    aliases: Mapped[list[MedicineAlias]] = relationship(back_populates="medicine", cascade="all, delete-orphan",
                                                        order_by="MedicineAlias.id")


class MedicineAlias(Base):
    """Variante d'un nom commercial (écriture arabe, graphie de l'emballage, variante OCR), toujours sourcée."""
    __tablename__ = "medicine_aliases"
    __table_args__ = (UniqueConstraint("medicine_id", "alias_normalized", name="uq_medicine_alias"), _status_check(),
                      CheckConstraint("kind IN ('brand_variant','arabic_script','packaging_text','ocr_variant')",
                                      name="alias_kind_valid"))
    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), index=True)
    alias: Mapped[str] = mapped_column(String(255))
    alias_normalized: Mapped[str] = mapped_column(String(255), index=True)
    language: Mapped[str | None] = mapped_column(String(12))  # fr | ar | en | lat
    kind: Mapped[str] = mapped_column(String(24))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_reference: Mapped[str | None] = mapped_column(String(500))
    data_status: Mapped[str] = _status()
    created_at: Mapped[datetime] = _created()
    medicine: Mapped[Medicine] = relationship(back_populates="aliases")


class MedicineIngredient(Base):
    __tablename__ = "medicine_ingredients"
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), primary_key=True)
    position: Mapped[int] = mapped_column(Integer, primary_key=True)
    ingredient_id: Mapped[int] = mapped_column(ForeignKey("active_ingredients.id"), index=True)
    strength_text: Mapped[str | None] = mapped_column(String(128))
    strength_value: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    strength_unit: Mapped[str | None] = mapped_column(String(32))
    strength_mg: Mapped[Decimal | None] = mapped_column(Numeric(16, 6))
    medicine: Mapped[Medicine] = relationship(back_populates="ingredients")
    ingredient: Mapped[ActiveIngredient] = relationship()


class MedicinePresentation(Base):
    __tablename__ = "medicine_presentations"
    __table_args__ = (UniqueConstraint("medicine_id", "label_normalized", name="uq_presentation_label"), _status_check())
    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), index=True)
    label: Mapped[str] = mapped_column(String(500))
    label_normalized: Mapped[str] = mapped_column(String(500))
    ean13: Mapped[str | None] = mapped_column(String(14), index=True)
    ean_status: Mapped[str | None] = mapped_column(String(24))
    # Conditionnement structuré, déduit du libellé seulement quand il est sans ambiguïté (« BOITE DE 28 » -> 28, None ;
    # « TUBE DE 15 G » -> 15, g). « BOITE DE 1 FLACON DE 120 » reste à None : jamais de valeur devinée.
    pack_quantity: Mapped[Decimal | None] = mapped_column(Numeric(12, 3))
    pack_unit: Mapped[str | None] = mapped_column(String(16))
    ppv_mad: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ph_mad: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    pfht_mad: Mapped[Decimal | None] = mapped_column(Numeric(12, 4))
    price_status: Mapped[str] = mapped_column(String(16), default="unknown")  # priced | no_price | unknown
    price_as_of: Mapped[date | None] = mapped_column(Date)
    data_status: Mapped[str] = _status()
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = _created()
    medicine: Mapped[Medicine] = relationship(back_populates="presentations")
    source: Mapped[DataSource] = relationship()


class Reimbursement(Base):
    __tablename__ = "reimbursements"
    __table_args__ = (_status_check(),)
    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int | None] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), index=True)
    presentation_id: Mapped[int | None] = mapped_column(ForeignKey("medicine_presentations.id", ondelete="SET NULL"))
    raw_name: Mapped[str] = mapped_column(String(500))
    raw_presentation: Mapped[str | None] = mapped_column(String(500))
    base_remboursement_mad: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    taux_remboursement: Mapped[Decimal | None] = mapped_column(Numeric(5, 2))
    princeps_generique: Mapped[str | None] = mapped_column(String(32))
    ppv_reference_mad: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    ph_reference_mad: Mapped[Decimal | None] = mapped_column(Numeric(12, 2))
    valid_as_of: Mapped[date | None] = mapped_column(Date)
    match_method: Mapped[str] = mapped_column(String(16))
    data_status: Mapped[str] = _status()
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = _created()
    source: Mapped[DataSource] = relationship()


class GenericGroup(Base):
    __tablename__ = "generic_groups"
    __table_args__ = (_status_check(),)
    id: Mapped[int] = mapped_column(primary_key=True)
    label: Mapped[str] = mapped_column(String(500))
    label_normalized: Mapped[str] = mapped_column(String(500), unique=True)
    route: Mapped[str | None] = mapped_column(String(64))
    register_edition: Mapped[str | None] = mapped_column(String(128))
    data_status: Mapped[str] = _status()
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    created_at: Mapped[datetime] = _created()
    members: Mapped[list[GenericGroupMember]] = relationship(back_populates="group", cascade="all, delete-orphan",
                                                             order_by="GenericGroupMember.id")
    source: Mapped[DataSource] = relationship()


class GenericGroupMember(Base):
    __tablename__ = "generic_group_members"
    __table_args__ = (UniqueConstraint("group_id", "raw_label_normalized", name="uq_group_member"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    group_id: Mapped[int] = mapped_column(ForeignKey("generic_groups.id", ondelete="CASCADE"), index=True)
    medicine_id: Mapped[int | None] = mapped_column(ForeignKey("medicines.id", ondelete="SET NULL"), index=True)
    presentation_id: Mapped[int | None] = mapped_column(ForeignKey("medicine_presentations.id", ondelete="SET NULL"))
    member_type: Mapped[str] = mapped_column(String(4))  # P (princeps) | G (générique) | I (non documenté)
    raw_label: Mapped[str] = mapped_column(String(500))
    raw_label_normalized: Mapped[str] = mapped_column(String(500))
    laboratory_raw: Mapped[str | None] = mapped_column(String(255))
    ean13: Mapped[str | None] = mapped_column(String(14), index=True)
    ean_status: Mapped[str | None] = mapped_column(String(24))
    match_method: Mapped[str] = mapped_column(String(16))
    group: Mapped[GenericGroup] = relationship(back_populates="members")
    medicine: Mapped[Medicine | None] = relationship()


class ClinicalSection(Base):
    __tablename__ = "clinical_sections"
    __table_args__ = (UniqueConstraint("medicine_id", "section_code", "source_id", name="uq_clinical_section"), _status_check())
    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int] = mapped_column(ForeignKey("medicines.id", ondelete="CASCADE"), index=True)
    section_code: Mapped[str] = mapped_column(String(32))
    title: Mapped[str] = mapped_column(String(255))
    content: Mapped[str] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_url: Mapped[str | None] = mapped_column(String(500))
    document_date: Mapped[date | None] = mapped_column(Date)
    extraction_method: Mapped[str] = mapped_column(String(32))
    data_status: Mapped[str] = _status()
    created_at: Mapped[datetime] = _created()
    source: Mapped[DataSource] = relationship()


class DrugInteraction(Base):
    __tablename__ = "drug_interactions"
    __table_args__ = (
        UniqueConstraint("ingredient_a_id", "ingredient_b_id", "source_id", name="uq_interaction_pair"),
        CheckConstraint("ingredient_a_id < ingredient_b_id", name="ordered_pair"),
        CheckConstraint("severity IN ('contraindicated','major','moderate','minor','unknown')", name="severity_valid"),
        _status_check(),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    ingredient_a_id: Mapped[int] = mapped_column(ForeignKey("active_ingredients.id"), index=True)
    ingredient_b_id: Mapped[int] = mapped_column(ForeignKey("active_ingredients.id"), index=True)
    severity: Mapped[str] = mapped_column(String(16))
    severity_raw: Mapped[str | None] = mapped_column(String(64))
    description: Mapped[str | None] = mapped_column(Text)
    management: Mapped[str | None] = mapped_column(Text)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_reference: Mapped[str | None] = mapped_column(String(500))
    data_status: Mapped[str] = _status()
    created_at: Mapped[datetime] = _created()
    source: Mapped[DataSource] = relationship()


class Pharmacy(Base):
    __tablename__ = "pharmacies"
    __table_args__ = (UniqueConstraint("source_record_key", name="uq_pharmacies_source_record_key"), _status_check(),
                      Index("ix_pharmacies_city_name", "city_normalized", "name_normalized"))
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(255))
    name_normalized: Mapped[str] = mapped_column(String(255))
    address: Mapped[str | None] = mapped_column(String(500))
    city: Mapped[str | None] = mapped_column(String(128))
    city_normalized: Mapped[str | None] = mapped_column(String(128))
    district: Mapped[str | None] = mapped_column(String(128))
    region: Mapped[str | None] = mapped_column(String(128))
    latitude: Mapped[float | None] = mapped_column(Float)
    longitude: Mapped[float | None] = mapped_column(Float)
    phone: Mapped[str | None] = mapped_column(String(64))
    opening_hours: Mapped[str | None] = mapped_column(String(255))
    in_ammps_registry: Mapped[bool | None] = mapped_column(Boolean)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_record_key: Mapped[str] = mapped_column(String(255))
    data_status: Mapped[str] = _status()
    created_at: Mapped[datetime] = _created()
    source: Mapped[DataSource] = relationship()


class PharmacyDutyShift(Base):
    __tablename__ = "pharmacy_duty_shifts"
    __table_args__ = (CheckConstraint("shift_type IN ('jour','nuit','24h')", name="shift_type_valid"),
                      CheckConstraint("ends_at > starts_at", name="period_valid"), _status_check())
    id: Mapped[int] = mapped_column(primary_key=True)
    pharmacy_id: Mapped[int | None] = mapped_column(ForeignKey("pharmacies.id", ondelete="SET NULL"))
    pharmacy_name: Mapped[str] = mapped_column(String(255))
    city: Mapped[str] = mapped_column(String(128))
    city_normalized: Mapped[str] = mapped_column(String(128), index=True)
    district: Mapped[str | None] = mapped_column(String(128))
    address: Mapped[str | None] = mapped_column(String(500))
    phone: Mapped[str | None] = mapped_column(String(64))
    shift_type: Mapped[str] = mapped_column(String(8))
    starts_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    ends_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_url: Mapped[str | None] = mapped_column(String(500))
    data_status: Mapped[str] = _status()
    created_at: Mapped[datetime] = _created()
    source: Mapped[DataSource] = relationship()


class PharmacyInventory(Base):
    """Stock : affiché comme vérifié uniquement si issu d'un flux réel (data_status official/reference, non simulé)."""
    __tablename__ = "pharmacy_inventory"
    __table_args__ = (UniqueConstraint("pharmacy_id", "presentation_id", "source_id", name="uq_inventory_item"),
                      CheckConstraint("stock_status IN ('in_stock','low','out_of_stock')", name="stock_status_valid"),
                      _status_check())
    id: Mapped[int] = mapped_column(primary_key=True)
    pharmacy_id: Mapped[int] = mapped_column(ForeignKey("pharmacies.id", ondelete="CASCADE"), index=True)
    presentation_id: Mapped[int] = mapped_column(ForeignKey("medicine_presentations.id", ondelete="CASCADE"), index=True)
    stock_status: Mapped[str] = mapped_column(String(16))
    quantity: Mapped[int | None] = mapped_column(Integer)
    observed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    is_simulated: Mapped[bool] = mapped_column(Boolean, default=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    data_status: Mapped[str] = _status()


class MedicineImage(Base):
    """Photo de référence pour le Pill Identifier : rattachée de préférence à une présentation (boîte + EAN-13)."""
    __tablename__ = "medicine_images"
    __table_args__ = (CheckConstraint("kind IN ('box','pill','blister')", name="kind_valid"), _status_check(),
                      CheckConstraint("view IS NULL OR view IN ('front','back','side','top','bottom','inside','other')",
                                      name="view_valid"),
                      UniqueConstraint("sha256", name="uq_medicine_images_sha256"))
    id: Mapped[int] = mapped_column(primary_key=True)
    medicine_id: Mapped[int | None] = mapped_column(ForeignKey("medicines.id", ondelete="SET NULL"), index=True)
    presentation_id: Mapped[int | None] = mapped_column(ForeignKey("medicine_presentations.id", ondelete="SET NULL"))
    kind: Mapped[str] = mapped_column(String(16))
    file_path: Mapped[str] = mapped_column(String(500))
    sha256: Mapped[str] = mapped_column(String(64))
    license: Mapped[str] = mapped_column(String(255))
    attribution: Mapped[str | None] = mapped_column(String(500))
    is_moroccan_reference: Mapped[bool] = mapped_column(Boolean, default=False)
    view: Mapped[str | None] = mapped_column(String(16))  # face photographiée
    packaging_languages: Mapped[list[str] | None] = mapped_column(JSONType)  # ex. ["fr", "ar"]
    origin: Mapped[str | None] = mapped_column(String(32))  # team_photo | manufacturer | public_dataset | user_consented
    width_px: Mapped[int | None] = mapped_column(Integer)
    height_px: Mapped[int | None] = mapped_column(Integer)
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    features: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    embedding: Mapped[bytes | None] = mapped_column(LargeBinary)
    embedding_model: Mapped[str | None] = mapped_column(String(64))
    metadata_json: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    data_status: Mapped[str] = _status()
    created_at: Mapped[datetime] = _created()
    annotations: Mapped[list[ImageAnnotation]] = relationship(back_populates="image", cascade="all, delete-orphan",
                                                              order_by="ImageAnnotation.id")


class ImageAnnotation(Base):
    """Annotation d'une photo (vérité terrain humaine ou sortie OCR/détecteur) : texte, code-barres, zone."""
    __tablename__ = "image_annotations"
    __table_args__ = (CheckConstraint("annotation_type IN ('ocr_text','brand','dosage','barcode','pack_size','lot',"
                                      "'expiry','bbox_box','bbox_pill','other')", name="annotation_type_valid"),
                      CheckConstraint("annotator IN ('human','model')", name="annotator_valid"))
    id: Mapped[int] = mapped_column(primary_key=True)
    image_id: Mapped[int] = mapped_column(ForeignKey("medicine_images.id", ondelete="CASCADE"), index=True)
    annotation_type: Mapped[str] = mapped_column(String(16))
    value: Mapped[str | None] = mapped_column(Text)
    language: Mapped[str | None] = mapped_column(String(12))
    bbox: Mapped[dict[str, Any] | None] = mapped_column(JSONType)  # {"x":..,"y":..,"w":..,"h":..} en pixels
    confidence: Mapped[float | None] = mapped_column(Float)
    annotator: Mapped[str] = mapped_column(String(8))
    model_name: Mapped[str | None] = mapped_column(String(64))
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _created()
    image: Mapped[MedicineImage] = relationship(back_populates="annotations")


class IdentificationResult(Base):
    """Trace d'identification : l'image n'est jamais stockée par défaut (seulement son empreinte SHA-256)."""
    __tablename__ = "identification_results"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = _created()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    image_sha256: Mapped[str | None] = mapped_column(String(64))
    image_stored: Mapped[bool] = mapped_column(Boolean, default=False)
    hints: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    extracted: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    candidates: Mapped[list[Any] | None] = mapped_column(JSONType)
    best_score: Mapped[float | None] = mapped_column(Float)
    reliability: Mapped[str] = mapped_column(String(8))


class Conversation(Base):
    __tablename__ = "conversations"
    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    created_at: Mapped[datetime] = _created()
    last_activity_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    language: Mapped[str | None] = mapped_column(String(12))
    context_medicine_id: Mapped[int | None] = mapped_column(ForeignKey("medicines.id", ondelete="SET NULL"))
    messages: Mapped[list[Message]] = relationship(back_populates="conversation", cascade="all, delete-orphan",
                                                   order_by="Message.id")


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    conversation_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("conversations.id", ondelete="CASCADE"), index=True)
    role: Mapped[str] = mapped_column(String(16))
    content: Mapped[str] = mapped_column(Text)
    analysis: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    sources: Mapped[list[Any] | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _created()
    conversation: Mapped[Conversation] = relationship(back_populates="messages")


class NlpUtterance(Base):
    """Corpus conversationnel annoté (structure « Données conversationnelles » de la fiche)."""
    __tablename__ = "nlp_utterances"
    __table_args__ = (UniqueConstraint("utterance", "split", name="uq_utterance_split"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    utterance: Mapped[str] = mapped_column(Text)
    language: Mapped[str] = mapped_column(String(12))
    intent: Mapped[str] = mapped_column(String(48))
    entities: Mapped[dict[str, Any] | None] = mapped_column(JSONType)
    origin: Mapped[str] = mapped_column(String(32))
    split: Mapped[str] = mapped_column(String(8))
    created_at: Mapped[datetime] = _created()
