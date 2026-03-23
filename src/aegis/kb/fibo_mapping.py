# SPDX-License-Identifier: MIT
"""FIBO (Financial Industry Business Ontology) alignment mappings.

Maps internal Aegis finance knowledge graph node and edge types to their corresponding
FIBO IRIs (Internationalized Resource Identifiers) or equivalent concepts.
"""

from __future__ import annotations

from aegis.kb.ontology import GraphNodeType, GraphEdgeType


FIBO_NAMESPACE = "https://spec.edmcouncil.org/fibo/ontology/"


FIBO_NODE_MAPPING: dict[GraphNodeType, str] = {
    GraphNodeType.LEGAL_PERSON: f"{FIBO_NAMESPACE}BE/LegalEntities/LegalPersons/LegalPerson",
    GraphNodeType.SECURITY: f"{FIBO_NAMESPACE}FBC/FinancialInstruments/FinancialInstruments/Security",
    GraphNodeType.DEBT_INSTRUMENT: f"{FIBO_NAMESPACE}FBC/FinancialInstruments/FinancialInstruments/DebtInstrument",
    GraphNodeType.ACCOUNT: f"{FIBO_NAMESPACE}FBC/ProductsAndServices/FinancialProductsAndServices/FinancialAccount",
    # Argentine-specific extensions mapped to broader or specialized concepts:
    GraphNodeType.CEDEAR: f"{FIBO_NAMESPACE}SEC/Equities/DepositaryReceipts/DepositaryReceipt",
    GraphNodeType.BOPREAL: f"{FIBO_NAMESPACE}SEC/Debt/SovereignDebt/SovereignBond",
    GraphNodeType.BONO_CER: f"{FIBO_NAMESPACE}SEC/Debt/SovereignDebt/SovereignBond",  # Inflation-linked
    GraphNodeType.PLAZO_FIJO: f"{FIBO_NAMESPACE}FBC/ProductsAndServices/FinancialProductsAndServices/CertificateOfDeposit",
    GraphNodeType.CURRENCY_NODE: f"{FIBO_NAMESPACE}FND/Accounting/CurrencyAmount/Currency",
    GraphNodeType.REGULATORY_EVENT: f"{FIBO_NAMESPACE}FND/Law/Jurisdiction/RegulatoryEvent",
    GraphNodeType.ACTION_NODE: f"{FIBO_NAMESPACE}FND/Law/LegalCapacity/LegalAction",
    # Legacy fallbacks:
    GraphNodeType.CONCEPT: f"{FIBO_NAMESPACE}FND/Arrangements/Arrangements/Concept",
    GraphNodeType.REGULATION: f"{FIBO_NAMESPACE}FND/Law/Jurisdiction/StatuteLaw",
    GraphNodeType.ASSET: f"{FIBO_NAMESPACE}FBC/FinancialInstruments/FinancialInstruments/FinancialInstrument",
    GraphNodeType.INSTITUTION: f"{FIBO_NAMESPACE}BE/LegalEntities/LegalPersons/LegalEntity",
    GraphNodeType.TAX_RULE: f"{FIBO_NAMESPACE}FND/Law/Jurisdiction/Regulation",
}


FIBO_EDGE_MAPPING: dict[GraphEdgeType, str] = {
    GraphEdgeType.IS_ISSUED_BY: f"{FIBO_NAMESPACE}FBC/FinancialInstruments/FinancialInstruments/isIssuedBy",
    GraphEdgeType.REPRESENTS: f"{FIBO_NAMESPACE}FND/Relations/Relations/represents",
    GraphEdgeType.IS_HEDGED_BY: f"{FIBO_NAMESPACE}FBC/FinancialInstruments/FinancialInstruments/isHedgedBy",
    GraphEdgeType.AMENDS: f"{FIBO_NAMESPACE}FND/Law/Jurisdiction/amends",
    GraphEdgeType.SUPERSEDES: f"{FIBO_NAMESPACE}FND/Law/Jurisdiction/supersedes",
    GraphEdgeType.TRIGGERS: f"{FIBO_NAMESPACE}FND/Relations/Relations/triggers",
    GraphEdgeType.HAS_CONVERSION_RATIO: f"{FIBO_NAMESPACE}SEC/Equities/DepositaryReceipts/hasConversionRatio",
    GraphEdgeType.VALID_DURING: f"{FIBO_NAMESPACE}FND/DatesAndTimes/FinancialDates/isValidDuring",
    # Legacy fallbacks:
    GraphEdgeType.RELATES_TO: f"{FIBO_NAMESPACE}FND/Relations/Relations/relatesTo",
    GraphEdgeType.REGULATES: f"{FIBO_NAMESPACE}FND/Law/Jurisdiction/governs",
    GraphEdgeType.DEPENDS_ON: f"{FIBO_NAMESPACE}FND/Relations/Relations/dependsOn",
    GraphEdgeType.TAXED_BY: f"{FIBO_NAMESPACE}FND/Law/Jurisdiction/isAssessedBy",
    GraphEdgeType.ISSUED_BY: f"{FIBO_NAMESPACE}FBC/FinancialInstruments/FinancialInstruments/isIssuedBy",
}


def get_fibo_iri(node_or_edge_type: GraphNodeType | GraphEdgeType) -> str | None:
    """Returns the FIBO IRI for a given graph node or edge type."""
    if isinstance(node_or_edge_type, GraphNodeType):
        return FIBO_NODE_MAPPING.get(node_or_edge_type)
    elif isinstance(node_or_edge_type, GraphEdgeType):
        return FIBO_EDGE_MAPPING.get(node_or_edge_type)
    return None
