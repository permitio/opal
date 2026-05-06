package risk.enforcement.action.deny.policy_0272

# Auto-generated policy 272 (Rego v1 syntax)
# Package: risk.enforcement.action.deny

# Metadata
metadata := {
    "policy_id": "0272",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0272_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0272_allowed if {
    data.policies.risk.enabled
}
