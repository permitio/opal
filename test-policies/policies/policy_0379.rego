package risk.enforcement.user.allow.policy_0379

# Auto-generated policy 379 (Rego v1 syntax)
# Package: risk.enforcement.user.allow

# Metadata
metadata := {
    "policy_id": "0379",
    "version": "1.0",
    "created": "2026-05-06",
}

# Rules
policy_0379_approved if {
    input.user.risk_score < 50
    input.system.health > 0.8
}
policy_0379_allowed if {
    data.policies.risk.enabled
}
